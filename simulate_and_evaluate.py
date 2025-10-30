#!/usr/bin/env python3
"""
Simulation and Evaluation System for Generated Testbenches

This script simulates generated testbenches against:
1. module_code (correct implementation)
2. mutants (incorrect implementations)

Evaluation Metrics:
- eval0: Compilation success
- eval1: Module code passes the testbench
- eval2: Mutant detection rate (80%, 90%, 100% thresholds)
"""

import json
import os
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime
import logging

# Setup logging
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
    mutant_agreement_80: bool = False  # 80% of mutants match expected
    mutant_agreement_90: bool = False  # 90% of mutants match expected
    mutant_agreement_100: bool = False  # 100% of mutants match expected

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
    """Handle Verilog compilation and simulation using Verilator"""

    def __init__(self, work_dir: Optional[Path] = None):
        self.work_dir = work_dir or Path(tempfile.mkdtemp(prefix="veril_sim_"))
        self.work_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Initialized simulator with work directory: {self.work_dir}")

    def compile_and_simulate(
        self,
        module_code: str,
        testbench: str,
        timeout: int = 60
    ) -> SimulationResult:
        """
        Compile and simulate Verilog code with testbench using Verilator

        Args:
            module_code: The Verilog module code to test
            testbench: The testbench code
            timeout: Simulation timeout in seconds

        Returns:
            SimulationResult with compilation and simulation status
        """
        result = SimulationResult()

        # Create temporary files
        source_file = self.work_dir / "testbench.v"
        obj_dir = self.work_dir / "obj_dir"
        sim_exe = obj_dir / "Vtestbench"

        try:
            # Write module and testbench to file
            with open(source_file, 'w') as f:
                f.write(module_code)
                f.write("\n\n")
                f.write(testbench)

            # Compile with Verilator
            compile_cmd = [
                "verilator",
                "--binary",  # Generate executable directly
                "-Wall",
                "--timing",  # Enable timing features
                "-Wno-fatal",  # Don't stop on warnings
                str(source_file)
            ]

            compile_proc = subprocess.run(
                compile_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.work_dir
            )

            result.stdout = compile_proc.stdout
            result.stderr = compile_proc.stderr

            # Verilator returns 0 even with some warnings
            # Check if executable was created
            if not sim_exe.exists():
                result.compile_success = False
                result.error_message = f"Compilation failed: executable not created\n{compile_proc.stderr}"
                logger.debug(f"Compilation failed: {result.error_message}")
                return result

            result.compile_success = True

            # Run simulation
            sim_cmd = [str(sim_exe)]

            sim_proc = subprocess.run(
                sim_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.work_dir
            )

            result.stdout += "\n" + sim_proc.stdout
            result.stderr += "\n" + sim_proc.stderr

            if sim_proc.returncode != 0:
                result.simulation_success = False
                result.error_message = f"Simulation failed with return code {sim_proc.returncode}: {sim_proc.stderr}"
                logger.debug(f"Simulation failed: {result.error_message}")
                return result

            result.simulation_success = True

            # Check if testbench passed (no mismatches)
            # Look for "Mismatches: 0 in" in output
            output_text = sim_proc.stdout + sim_proc.stderr
            if "Mismatches: 0 in" in output_text or "Mismatches: 0" in output_text:
                result.passed = True
            else:
                result.passed = False
                # Extract mismatch info
                for line in output_text.split('\n'):
                    if "Mismatches:" in line or "mismatch" in line.lower():
                        result.error_message = line.strip()
                        break
                if not result.error_message:
                    result.error_message = "Testbench execution completed but no mismatch info found"

            logger.debug(f"Simulation completed: passed={result.passed}")

        except subprocess.TimeoutExpired:
            result.error_message = f"Simulation timed out after {timeout}s"
            logger.warning(result.error_message)
        except Exception as e:
            result.error_message = f"Unexpected error: {str(e)}"
            logger.error(result.error_message, exc_info=True)
        finally:
            # Cleanup temporary files
            if obj_dir.exists():
                try:
                    shutil.rmtree(obj_dir)
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

    def __init__(self, benchmark_file: str, testbench_dir: Optional[str] = None):
        """
        Initialize evaluator

        Args:
            benchmark_file: Path to test_benchmark_new.json
            testbench_dir: Directory containing generated testbenches
        """
        self.benchmark_file = Path(benchmark_file)
        self.testbench_dir = Path(testbench_dir) if testbench_dir else None

        # Load benchmark data
        with open(self.benchmark_file, 'r') as f:
            self.benchmark_data = json.load(f)

        logger.info(f"Loaded {len(self.benchmark_data)} tasks from benchmark")

        self.simulator = VerilogSimulator()
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

        # Step 1: Test compilation with module_code
        logger.info(f"  Testing compilation...")
        result = self.simulator.compile_and_simulate(module_code, testbench)
        metrics.compile_success = result.compile_success

        if not result.compile_success:
            logger.warning(f"  Compilation failed: {result.error_message}")
            return metrics

        # Step 2: Test if module_code passes testbench (eval1)
        logger.info(f"  Testing module_code...")
        metrics.module_passes = result.passed

        if not result.passed:
            logger.warning(f"  Module failed testbench: {result.error_message}")
        else:
            logger.info(f"  Module passed testbench!")

        # Step 3: Test mutants (eval2)
        logger.info(f"  Testing {len(mutants)} mutants...")
        for i, mutant_code in enumerate(mutants):
            mutant_result = self.simulator.compile_and_simulate(mutant_code, testbench)

            # Mutant should fail (not pass) if it's correctly detected
            mutant_detected = not mutant_result.passed
            metrics.mutant_results.append(mutant_detected)

            if mutant_detected:
                metrics.mutants_detected += 1

            # Log if result differs from expected
            expected = expected_results[i] if i < len(expected_results) else None
            if expected is not None:
                # expected_results contains whether mutant FAILS (False = fails, True = passes)
                # We store whether mutant is DETECTED (True = fails)
                actual_fails = mutant_detected
                expected_fails = not expected

                if actual_fails == expected_fails:
                    status = "✓ Match"
                else:
                    status = "✗ Mismatch"

                logger.debug(
                    f"    Mutant {i}: detected={mutant_detected}, "
                    f"expected_fail={expected_fails}, {status}"
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
        logger.info("\n" + "="*60)
        logger.info("EVALUATION REPORT")
        logger.info("="*60)
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
        logger.info("="*60)

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
        self.simulator.cleanup()


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Evaluate generated testbenches against module and mutants"
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
