#!/usr/bin/env python3
"""
Simulation and Evaluation System for Generated Testbenches with Mutant Detection

This script evaluates generated testbenches by:
1. Testing compilation success (eval0)
2. Testing module_code passes testbench (eval1)
3. Testing mutant detection rate (eval2) at 80%, 90%, 100% thresholds

Uses the existing simulation infrastructure from pro_v/tools/pychecker_worker.py
"""

import os
import json
import logging
import subprocess
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime
import re

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class SimulationResult:
    """Store simulation results for a single test"""
    compile_success: bool = False
    simulation_success: bool = False
    passed: bool = False
    error_message: str = ""
    stdout: str = ""
    stderr: str = ""
    mismatch_count: int = -1
    total_samples: int = 0


@dataclass
class EvaluationMetrics:
    """Evaluation metrics for a task"""
    task_id: str
    task_number: int

    # eval0: Compilation success
    compile_success: bool = False

    # eval1: Module code passes testbench
    module_passes: bool = False

    # eval2: Mutant detection metrics
    total_mutants: int = 0
    mutants_detected: int = 0
    mutant_results: List[bool] = field(default_factory=list)
    expected_mutant_results: List[bool] = field(default_factory=list)

    # Mutant agreement rate
    mutant_agreement_80: bool = False
    mutant_agreement_90: bool = False
    mutant_agreement_100: bool = False

    # Overall success
    overall_success: bool = False

    def calculate_agreement(self):
        """Calculate mutant detection agreement"""
        if self.total_mutants == 0:
            return

        # Count how many mutants have results matching expected results
        agreement_count = sum(
            1 for actual, expected in zip(self.mutant_results, self.expected_mutant_results)
            if actual == expected
        )

        agreement_rate = agreement_count / self.total_mutants

        self.mutant_agreement_80 = agreement_rate >= 0.80
        self.mutant_agreement_90 = agreement_rate >= 0.90
        self.mutant_agreement_100 = agreement_rate >= 1.00

        # Overall success: compile + module passes + at least 80% mutant agreement
        self.overall_success = (
            self.compile_success and
            self.module_passes and
            self.mutant_agreement_80
        )

        logger.info(
            f"Task {self.task_id}: Agreement rate: {agreement_rate:.2%} "
            f"({agreement_count}/{self.total_mutants})"
        )


class VerilogSimulator:
    """Handle Verilog simulation using the existing sim_cmb/sim_seq infrastructure"""

    def __init__(self, work_dir: Optional[Path] = None, sim_type: str = "cmb"):
        """
        Initialize simulator

        Args:
            work_dir: Base working directory for simulations
            sim_type: "cmb" or "seq" for combinational or sequential circuits
        """
        self.work_dir = work_dir or Path(f"/tmp/mutant_eval_{sim_type}")
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.sim_type = sim_type

        # Get simulation template directory
        current_dir = Path(__file__).parent
        self.sim_template_dir = current_dir / "pro_v" / "tools" / f"sim_{sim_type}"

        if not self.sim_template_dir.exists():
            # Fallback to hardcoded path
            self.sim_template_dir = Path(f"/home/lah003/workspace/verl_efficient/pettingllms/multi_agent_env/pychecker_rl/sim_{sim_type}")

        if not self.sim_template_dir.exists():
            raise RuntimeError(f"Simulation template directory not found: {self.sim_template_dir}")

        logger.info(f"Using simulation template directory: {self.sim_template_dir}")

    def simulate(
        self,
        module_code: str,
        testbench_code: str,
        task_id: str,
        timeout: int = 60
    ) -> SimulationResult:
        """
        Simulate Verilog module with testbench

        Args:
            module_code: Verilog module code
            testbench_code: Testbench code
            task_id: Unique task identifier
            timeout: Simulation timeout in seconds

        Returns:
            SimulationResult
        """
        result = SimulationResult()

        # Create task-specific work directory
        task_work_dir = self.work_dir / task_id
        task_work_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Write module code
            module_file = task_work_dir / "top_module.v"
            with open(module_file, 'w') as f:
                f.write(module_code)

            # Write testbench code
            testbench_file = task_work_dir / "testbench.v"
            with open(testbench_file, 'w') as f:
                f.write(testbench_code)

            # Create dummy testbench.json (required by harness-generator)
            testbench_json = task_work_dir / "testbench.json"
            with open(testbench_json, 'w') as f:
                json.dump({"scenarios": []}, f)

            # Copy simulation framework files
            files_to_copy = [
                "Makefile", "input.vc",
                "sim-main.cpp", "rfuzz-harness.h"
            ]
            for file_name in files_to_copy:
                src = self.sim_template_dir / file_name
                if src.exists():
                    shutil.copy(src, task_work_dir / file_name)

            # Copy harness generator if it exists
            harness_gen = self.sim_template_dir / "harness-generator.py"
            if harness_gen.exists():
                harness_gen_dest = task_work_dir / "harness-generator.py"
                shutil.copy(harness_gen, harness_gen_dest)

                # Run harness generator
                subprocess.run(
                    ["python", str(harness_gen_dest)],
                    cwd=task_work_dir,
                    capture_output=True,
                    timeout=10
                )

            # Run make to compile and simulate
            make_cmd = f"cd {task_work_dir} && make -j1"

            compile_proc = subprocess.run(
                make_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            result.stdout = compile_proc.stdout
            result.stderr = compile_proc.stderr

            # Check compilation success
            if compile_proc.returncode == 0:
                result.compile_success = True
                result.simulation_success = True
            else:
                result.compile_success = False
                result.error_message = f"Compilation/simulation failed: {compile_proc.stderr[:500]}"
                return result

            # Parse simulation results
            log_content = result.stdout + "\n" + result.stderr

            # Check for mismatch information
            mismatch_pattern = r'Mismatches:\s*(\d+)\s*in\s*(\d+)\s*samples'
            match = re.search(mismatch_pattern, log_content)
            if match:
                result.mismatch_count = int(match.group(1))
                result.total_samples = int(match.group(2))
                result.passed = (result.mismatch_count == 0)
            else:
                # Alternative pattern
                alt_pattern = r'Total mismatched samples is\s*(\d+)\s*out of\s*(\d+)\s*samples'
                match2 = re.search(alt_pattern, log_content)
                if match2:
                    result.mismatch_count = int(match2.group(1))
                    result.total_samples = int(match2.group(2))
                    result.passed = (result.mismatch_count == 0)
                else:
                    # Check for "Unpass:" pattern used in existing code
                    unpass_match = re.search(r'Unpass:\s*(\d+)', log_content)
                    if unpass_match:
                        unpass_count = int(unpass_match.group(1))
                        result.passed = (unpass_count == 0)
                        result.mismatch_count = unpass_count
                    else:
                        # No clear pass/fail indicator found
                        result.passed = False
                        result.error_message = "Could not determine pass/fail status from simulation output"

            logger.debug(f"Task {task_id}: compile={result.compile_success}, passed={result.passed}, mismatches={result.mismatch_count}")

        except subprocess.TimeoutExpired:
            result.error_message = f"Simulation timed out after {timeout}s"
            logger.warning(result.error_message)
        except Exception as e:
            result.error_message = f"Simulation error: {str(e)}"
            logger.error(result.error_message, exc_info=True)
        finally:
            # Cleanup task work directory
            if task_work_dir.exists():
                try:
                    shutil.rmtree(task_work_dir)
                except:
                    pass

        return result

    def cleanup(self):
        """Remove work directory"""
        if self.work_dir.exists():
            try:
                shutil.rmtree(self.work_dir)
                logger.info(f"Cleaned up work directory: {self.work_dir}")
            except Exception as e:
                logger.warning(f"Failed to cleanup work directory: {e}")


class TestbenchEvaluator:
    """Evaluate generated testbenches against module and mutants"""

    def __init__(self, benchmark_file: str):
        """
        Initialize evaluator

        Args:
            benchmark_file: Path to test_benchmark_new.json
        """
        self.benchmark_file = Path(benchmark_file)

        # Load benchmark data
        with open(self.benchmark_file, 'r') as f:
            self.benchmark_data = json.load(f)

        logger.info(f"Loaded {len(self.benchmark_data)} tasks from benchmark")

        self.simulator_cmb = VerilogSimulator(sim_type="cmb")
        self.simulator_seq = VerilogSimulator(sim_type="seq")
        self.results: List[EvaluationMetrics] = []

    def evaluate_task(
        self,
        task_data: Dict,
        generated_testbench: Optional[str] = None
    ) -> EvaluationMetrics:
        """
        Evaluate a single task

        Args:
            task_data: Task data from benchmark
            generated_testbench: Generated testbench code (if None, use task_data['testbench'])

        Returns:
            EvaluationMetrics for the task
        """
        task_id = task_data['task_id']
        task_number = task_data['task_number']

        logger.info(f"Evaluating task {task_id} (#{task_number})")

        metrics = EvaluationMetrics(
            task_id=task_id,
            task_number=task_number
        )

        # Use provided testbench or fall back to benchmark testbench
        testbench = generated_testbench or task_data.get('testbench', '')

        if not testbench:
            logger.warning(f"No testbench available for task {task_id}")
            return metrics

        module_code = task_data['module_code']
        mutants = task_data.get('mutants', [])
        expected_results = task_data.get('result', [])

        metrics.total_mutants = len(mutants)
        metrics.expected_mutant_results = expected_results

        # Determine circuit type (assume CMB for now, could be extracted from task_data if available)
        simulator = self.simulator_cmb

        # Step 1 & 2: Test module_code compilation and passing (eval0 + eval1)
        logger.info(f"  Testing module_code...")
        result = simulator.simulate(module_code, testbench, f"{task_id}_module", timeout=60)

        metrics.compile_success = result.compile_success
        metrics.module_passes = result.passed

        if not result.compile_success:
            logger.warning(f"  Compilation failed: {result.error_message}")
            return metrics

        if not result.passed:
            logger.warning(f"  Module failed testbench (mismatches: {result.mismatch_count})")
        else:
            logger.info(f"  Module passed testbench!")

        # Step 3: Test mutants (eval2)
        logger.info(f"  Testing {len(mutants)} mutants...")
        for i, mutant_code in enumerate(mutants):
            mutant_result = simulator.simulate(mutant_code, testbench, f"{task_id}_mutant_{i}", timeout=60)

            # Mutant should fail (not pass) if it's correctly detected
            mutant_detected = not mutant_result.passed
            metrics.mutant_results.append(mutant_detected)

            if mutant_detected:
                metrics.mutants_detected += 1

            # Log if result differs from expected
            expected = expected_results[i] if i < len(expected_results) else None
            if expected is not None:
                # expected_results contains whether mutant FAILS (False = fails/detected, True = passes)
                # We store whether mutant is DETECTED (True = fails)
                actual_fails = mutant_detected
                expected_fails = not expected

                if actual_fails == expected_fails:
                    status = "✓"
                else:
                    status = "✗"

                logger.debug(
                    f"    Mutant {i}: detected={mutant_detected}, "
                    f"expected_fail={expected_fails} {status}"
                )

        # Calculate agreement metrics
        metrics.calculate_agreement()

        logger.info(
            f"  Results: compile={metrics.compile_success}, "
            f"module_passes={metrics.module_passes}, "
            f"mutants_detected={metrics.mutants_detected}/{metrics.total_mutants}, "
            f"agreement_80={metrics.mutant_agreement_80}, "
            f"agreement_90={metrics.mutant_agreement_90}, "
            f"agreement_100={metrics.mutant_agreement_100}"
        )

        return metrics

    def evaluate_all(
        self,
        limit: Optional[int] = None,
        start_idx: int = 0
    ) -> List[EvaluationMetrics]:
        """
        Evaluate all tasks in benchmark

        Args:
            limit: Maximum number of tasks to evaluate
            start_idx: Starting index in benchmark

        Returns:
            List of EvaluationMetrics
        """
        tasks_to_eval = self.benchmark_data[start_idx:]
        if limit:
            tasks_to_eval = tasks_to_eval[:limit]

        logger.info(f"Evaluating {len(tasks_to_eval)} tasks (starting from {start_idx})")

        for task_data in tasks_to_eval:
            metrics = self.evaluate_task(task_data)
            self.results.append(metrics)

        return self.results

    def generate_report(self, output_file: Optional[str] = None) -> Dict:
        """
        Generate evaluation report

        Args:
            output_file: Optional file to save report

        Returns:
            Report dictionary
        """
        if not self.results:
            logger.warning("No results to report")
            return {}

        total_tasks = len(self.results)

        # Calculate success rates
        compile_success_count = sum(1 for r in self.results if r.compile_success)
        module_passes_count = sum(1 for r in self.results if r.module_passes)
        agreement_80_count = sum(1 for r in self.results if r.mutant_agreement_80)
        agreement_90_count = sum(1 for r in self.results if r.mutant_agreement_90)
        agreement_100_count = sum(1 for r in self.results if r.mutant_agreement_100)
        overall_success_count = sum(1 for r in self.results if r.overall_success)

        report = {
            "evaluation_date": datetime.now().isoformat(),
            "summary": {
                "total_tasks": total_tasks,
                "eval0_compile_success": {
                    "count": compile_success_count,
                    "rate": compile_success_count / total_tasks
                },
                "eval1_module_passes": {
                    "count": module_passes_count,
                    "rate": module_passes_count / total_tasks
                },
                "eval2_mutant_agreement": {
                    "80_percent": {
                        "count": agreement_80_count,
                        "rate": agreement_80_count / total_tasks
                    },
                    "90_percent": {
                        "count": agreement_90_count,
                        "rate": agreement_90_count / total_tasks
                    },
                    "100_percent": {
                        "count": agreement_100_count,
                        "rate": agreement_100_count / total_tasks
                    }
                },
                "overall_success": {
                    "count": overall_success_count,
                    "rate": overall_success_count / total_tasks
                }
            },
            "detailed_results": [
                {
                    "task_id": r.task_id,
                    "task_number": r.task_number,
                    "compile_success": r.compile_success,
                    "module_passes": r.module_passes,
                    "mutants_detected": f"{r.mutants_detected}/{r.total_mutants}",
                    "mutant_agreement_80": r.mutant_agreement_80,
                    "mutant_agreement_90": r.mutant_agreement_90,
                    "mutant_agreement_100": r.mutant_agreement_100,
                    "overall_success": r.overall_success
                }
                for r in self.results
            ]
        }

        # Print summary
        logger.info("\n" + "="*80)
        logger.info("EVALUATION REPORT")
        logger.info("="*80)
        logger.info(f"Total Tasks: {total_tasks}")
        logger.info(f"")
        logger.info(f"eval0 - Compilation Success: {compile_success_count}/{total_tasks} ({compile_success_count/total_tasks:.1%})")
        logger.info(f"eval1 - Module Passes: {module_passes_count}/{total_tasks} ({module_passes_count/total_tasks:.1%})")
        logger.info(f"eval2 - Mutant Agreement:")
        logger.info(f"  80%+: {agreement_80_count}/{total_tasks} ({agreement_80_count/total_tasks:.1%})")
        logger.info(f"  90%+: {agreement_90_count}/{total_tasks} ({agreement_90_count/total_tasks:.1%})")
        logger.info(f"  100%: {agreement_100_count}/{total_tasks} ({agreement_100_count/total_tasks:.1%})")
        logger.info(f"")
        logger.info(f"Overall Success Rate: {overall_success_count}/{total_tasks} ({overall_success_count/total_tasks:.1%})")
        logger.info("="*80)

        # Save report
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                json.dump(report, f, indent=2)
            logger.info(f"Report saved to: {output_path}")

        return report

    def cleanup(self):
        """Cleanup resources"""
        self.simulator_cmb.cleanup()
        self.simulator_seq.cleanup()


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Evaluate generated testbenches with mutant detection analysis"
    )
    parser.add_argument(
        "benchmark_file",
        help="Path to test_benchmark_new.json"
    )
    parser.add_argument(
        "--output", "-o",
        default="evaluation_report.json",
        help="Output report file (default: evaluation_report.json)"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        help="Limit number of tasks to evaluate"
    )
    parser.add_argument(
        "--start", "-s",
        type=int,
        default=0,
        help="Starting task index (default: 0)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Create evaluator
    evaluator = TestbenchEvaluator(args.benchmark_file)

    try:
        # Run evaluation
        evaluator.evaluate_all(limit=args.limit, start_idx=args.start)

        # Generate report
        evaluator.generate_report(output_file=args.output)

    finally:
        evaluator.cleanup()


if __name__ == "__main__":
    main()
