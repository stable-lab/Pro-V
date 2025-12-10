#!/usr/bin/env python3
"""
Simplified Parallel Simulation and Evaluation System for Mutant Detection
"""

import json
import logging
import subprocess
import re
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [PID %(process)d] - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class SimulationResult:
    """Store simulation results for a single test"""
    compile_success: bool = False
    passed: bool = False
    error_message: str = ""
    mismatch_count: int = -1
    total_samples: int = 0
    stdout: str = ""
    stderr: str = ""


@dataclass
class EvaluationMetrics:
    """Evaluation metrics for a task"""
    task_id: str
    task_number: int
    compile_success: bool = False
    module_passes: bool = False
    total_mutants: int = 0
    mutants_detected: int = 0
    mutant_results: List[bool] = field(default_factory=list)
    expected_mutant_results: List[bool] = field(default_factory=list)
    mutant_agreement_80: bool = False
    mutant_agreement_90: bool = False
    mutant_agreement_100: bool = False
    overall_success: bool = False

    def calculate_agreement(self):
        """Calculate mutant detection agreement"""
        if self.total_mutants == 0:
            return

        # mutant_results: True = detected (mutant failed), False = not detected (mutant passed)
        # expected_mutant_results: False = should be detected, True = should pass
        # So we need: actual_detected == (not expected_pass)
        agreement_count = sum(
            1 for actual, expected in zip(self.mutant_results, self.expected_mutant_results)
            if actual == (not expected)
        )
        agreement_rate = agreement_count / self.total_mutants

        self.mutant_agreement_80 = agreement_rate >= 0.80
        self.mutant_agreement_90 = agreement_rate >= 0.90
        self.mutant_agreement_100 = agreement_rate >= 1.00
        self.overall_success = (
            self.compile_success and
            self.module_passes and
            self.mutant_agreement_80
        )

        logger.info(
            f"Task {self.task_id}: Agreement rate: {agreement_rate:.2%} "
            f"({agreement_count}/{self.total_mutants})"
        )


def run_simulation(module_code: str, sim_dir: Path, timeout: int = 60) -> SimulationResult:
    """
    Run simulation by replacing module and running make

    Args:
        module_code: Verilog module code to test
        sim_dir: Existing simulation directory
        timeout: Simulation timeout in seconds

    Returns:
        SimulationResult
    """
    result = SimulationResult()

    # Replace top_module.v
    module_file = sim_dir / "top_module.v"
    with open(module_file, 'w') as f:
        f.write(module_code)

    # Clean previous build
    subprocess.run("make clean", shell=True, cwd=sim_dir, capture_output=True, timeout=10)

    # Run make to compile and simulate
    try:
        proc = subprocess.run(
            "make -j1",
            shell=True,
            cwd=sim_dir,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        result.stdout = proc.stdout
        result.stderr = proc.stderr
        result.compile_success = (proc.returncode == 0)

        if not result.compile_success:
            result.error_message = f"Compilation failed: {proc.stderr[:500]}"
            return result
    except subprocess.TimeoutExpired as e:
        result.compile_success = False
        result.passed = False
        result.error_message = f"Simulation timed out after {timeout}s"
        result.stdout = e.stdout.decode() if e.stdout else ""
        result.stderr = e.stderr.decode() if e.stderr else ""
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
        alt_pattern = r'Total mismatched samples is\s*(\d+)\s*out of\s*(\d+)\s*samples'
        match2 = re.search(alt_pattern, log_content)
        if match2:
            result.mismatch_count = int(match2.group(1))
            result.total_samples = int(match2.group(2))
            result.passed = (result.mismatch_count == 0)
        elif "All tests passed" in log_content or "✓ All tests passed" in log_content:
            result.passed = True
            result.mismatch_count = 0
        elif "Test failed" in log_content or "✗ Test failed" in log_content or "error(s)" in log_content:
            result.passed = False
            error_match = re.search(r'(\d+)\s+error\(s\)', log_content)
            if error_match:
                result.mismatch_count = int(error_match.group(1))
        else:
            unpass_match = re.search(r'Unpass:\s*(\d+)', log_content)
            if unpass_match:
                result.mismatch_count = int(unpass_match.group(1))
                result.passed = (result.mismatch_count == 0)
            else:
                result.passed = False
                result.error_message = "Could not determine pass/fail status"

    return result


def save_mutant_log(sim_dir: Path, mutant_idx: int, task_id: str, task_number: int, result: SimulationResult):
    """Save mutant simulation log to file"""
    log_dir = sim_dir / "mutant_logs"
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / f"sim_{mutant_idx}_log.txt"
    with open(log_file, 'w') as f:
        f.write(f"=== Mutant {mutant_idx} Simulation Log ===\n")
        f.write(f"Task: {task_id} (#{task_number})\n")
        f.write(f"Mutant Index: {mutant_idx}\n")
        f.write(f"Compile Success: {result.compile_success}\n")
        f.write(f"Passed: {result.passed}\n")
        f.write(f"Mismatch Count: {result.mismatch_count}\n")
        f.write(f"Total Samples: {result.total_samples}\n")
        f.write(f"\n=== STDOUT ===\n{result.stdout}\n")
        f.write(f"\n=== STDERR ===\n{result.stderr}\n")


def evaluate_single_task(task_data: Dict, experiment_dir: Path, mutant_only: bool, timeout: int = 120) -> EvaluationMetrics:
    """
    Evaluate a single task with all its mutants

    Args:
        task_data: Task data from benchmark
        experiment_dir: Experiment outputs directory
        mutant_only: Skip module_code testing if True

    Returns:
        EvaluationMetrics
    """
    task_id = task_data['task_id']
    task_number = task_data['task_number']

    logger.info(f"[Task #{task_number}] Evaluating {task_id}")

    metrics = EvaluationMetrics(task_id=task_id, task_number=task_number)

    # Find simulation directory
    task_dir = experiment_dir / f"task_{task_number}"
    task_result_path = task_dir / "task_result.json"

    sim_type = "cmb"
    if task_result_path.exists():
        with open(task_result_path, 'r') as f:
            task_result = json.load(f)
            sim_type = task_result.get('circuit_type', 'cmb').lower()

    sim_dir = task_dir / f"sim_{sim_type}"
    if not sim_dir.exists():
        logger.warning(f"[Task #{task_number}] No sim directory found at: {sim_dir}")
        return metrics

    logger.info(f"[Task #{task_number}] Using sim directory: {sim_dir}")

    module_code = task_data['module_code']
    mutants = task_data.get('mutants', [])
    expected_results = task_data.get('result', [])

    metrics.total_mutants = len(mutants)
    metrics.expected_mutant_results = expected_results

    # Test module_code (skip if mutant_only)
    if not mutant_only:
        logger.info(f"[Task #{task_number}] Testing module_code...")
        result = run_simulation(module_code, sim_dir, timeout=timeout)

        metrics.compile_success = result.compile_success
        metrics.module_passes = result.passed

        if not result.passed:
            logger.warning(f"[Task #{task_number}] Compilation failed: {result.error_message}")
            return metrics

        if result.passed:
            logger.info(f"[Task #{task_number}] Module passed testbench!")
        else:
            logger.warning(f"[Task #{task_number}] Module failed (mismatches: {result.mismatch_count})")
            logger.warning(f"[Task #{task_number}] Skipping mutant evaluation - module did not pass")
            return metrics
    else:
        logger.info(f"[Task #{task_number}] Skipping module_code testing (mutant_only mode)")
        metrics.compile_success = True
        metrics.module_passes = True

    # Test mutants (only if module passed)
    logger.info(f"[Task #{task_number}] Testing {len(mutants)} mutants...")
    for i, mutant_code in enumerate(mutants):
        logger.info(f"[Task #{task_number}] Simulating mutant #{i+1}/{len(mutants)}...")

        mutant_result = run_simulation(mutant_code, sim_dir, timeout=timeout)

        # Save log
        if mutant_result.stdout:
            save_mutant_log(sim_dir, i, task_id, task_number, mutant_result)

        # Mutant detected if it fails
        mutant_detected = not mutant_result.passed
        metrics.mutant_results.append(mutant_detected)

        if mutant_detected:
            metrics.mutants_detected += 1

        # Compare with expected
        if i < len(expected_results):
            expected = expected_results[i]
            actual_fails = mutant_detected
            expected_fails = not expected
            status = "✓" if actual_fails == expected_fails else "✗"
            logger.debug(f"  Mutant {i}: detected={mutant_detected}, expected_fail={expected_fails} {status}")

    # Calculate metrics
    metrics.calculate_agreement()

    logger.info(
        f"[Task #{task_number}] Results: compile={metrics.compile_success}, "
        f"module_passes={metrics.module_passes}, "
        f"mutants_detected={metrics.mutants_detected}/{metrics.total_mutants}, "
        f"agreement_80={metrics.mutant_agreement_80}, "
        f"agreement_90={metrics.mutant_agreement_90}, "
        f"agreement_100={metrics.mutant_agreement_100}"
    )

    return metrics


def worker_function(args):
    """Worker function for parallel execution"""
    task_data, experiment_dir, mutant_only, timeout = args
    return evaluate_single_task(task_data, Path(experiment_dir), mutant_only, timeout=timeout)


def evaluate_all_tasks(
    benchmark_file: str,
    experiment_dir: str,
    mutant_only: bool = False,
    limit: Optional[int] = None,
    start_idx: int = 0,
    num_workers: Optional[int] = None,
    timeout: int = 120
) -> List[EvaluationMetrics]:
    """
    Evaluate all tasks in parallel

    Args:
        benchmark_file: Path to test_benchmark_new.json
        experiment_dir: Path to experiment outputs directory
        mutant_only: Skip module_code testing if True
        limit: Maximum number of tasks to evaluate
        start_idx: Starting index in benchmark
        num_workers: Number of parallel workers (default: CPU count - 1)

    Returns:
        List of EvaluationMetrics
    """
    # Load benchmark
    with open(benchmark_file, 'r') as f:
        benchmark_data = json.load(f)

    logger.info(f"Loaded {len(benchmark_data)} tasks from benchmark")
    logger.info(f"Using experiment outputs from: {experiment_dir}")
    if mutant_only:
        logger.info(f"Mutant-only mode: Will skip module_code testing")

    # Select tasks to evaluate
    tasks_to_eval = benchmark_data[start_idx:]
    if limit:
        tasks_to_eval = tasks_to_eval[:limit]

    logger.info(f"Evaluating {len(tasks_to_eval)} tasks (starting from {start_idx})")

    # Determine number of workers
    if num_workers is None:
        num_workers = max(1, multiprocessing.cpu_count() - 1)

    logger.info(f"Using {num_workers} parallel workers")

    # Prepare worker arguments
    worker_args = [
        (task_data, experiment_dir, mutant_only, timeout)
        for task_data in tasks_to_eval
    ]

    # Run parallel evaluation
    results = []
    completed_count = 0

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        # Submit all tasks
        future_to_task = {
            executor.submit(worker_function, args): args[0]['task_number']
            for args in worker_args
        }

        # Collect results as they complete
        for future in as_completed(future_to_task):
            task_number = future_to_task[future]
            try:
                metrics = future.result()
                results.append(metrics)
                completed_count += 1
                logger.info(f"Progress: {completed_count}/{len(tasks_to_eval)} tasks completed")
            except Exception as e:
                logger.error(f"Task #{task_number} failed with exception: {e}")
                completed_count += 1

    # Sort by task_number
    results.sort(key=lambda x: x.task_number)

    return results


def generate_report(results: List[EvaluationMetrics], output_file: Optional[str] = None) -> Dict:
    """
    Generate evaluation report

    Args:
        results: List of EvaluationMetrics
        output_file: Optional file to save report

    Returns:
        Report dictionary
    """
    if not results:
        logger.warning("No results to report")
        return {}

    total_tasks = len(results)

    # Calculate success rates
    compile_success_count = sum(1 for r in results if r.compile_success)
    module_passes_count = sum(1 for r in results if r.module_passes)
    agreement_80_count = sum(1 for r in results if r.mutant_agreement_80)
    agreement_90_count = sum(1 for r in results if r.mutant_agreement_90)
    agreement_100_count = sum(1 for r in results if r.mutant_agreement_100)
    overall_success_count = sum(1 for r in results if r.overall_success)

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
            for r in results
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


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Evaluate generated testbenches with mutant detection (parallel)"
    )

    parser.add_argument(
        "--output", "-o",
        default="evaluation_report.json",
        help="Output report file (default: evaluation_report.json)"
    )
    parser.add_argument(
        "--experiment_dir", "-e",
        default="outputs/pro_v_rl",
        help="Path to experiment outputs directory (e.g., outputs/fine_thinking_8B)"
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
    parser.add_argument(
        "--mutant-only", "-m",
        action="store_true",
        help="Only test mutants, skip module_code testing"
    )
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=None,
        help="Number of parallel workers (default: CPU count - 1)"
    )
    parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=180,
        help="Simulation timeout in seconds (default: 180)"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Run evaluation
    results = evaluate_all_tasks(
        #benchmark_file="verilog-eval/HDLBits/test_benchmark_new.json",
        benchmark_file="verilog-eval/HDLBits/merged_benchmark.json",
        experiment_dir=args.experiment_dir,
        mutant_only=args.mutant_only,
        limit=args.limit,
        start_idx=args.start,
        num_workers=args.workers,
        timeout=args.timeout
    )

    # Generate report
    generate_report(results, output_file=args.output)


if __name__ == "__main__":
    main()
