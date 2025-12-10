#!/usr/bin/env python3
"""
Pro-V Top Agent - Simplified Version

This simplified version only performs:
1. GenTBAgent: Generate stimulus.json
2. PyCheckerAgent: Generate golden_dut.py and testbench.json
3. Validation: Check if testbench.json is correctly generated
"""

import argparse
import json
import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pro_v.agent.gen_tb import GenTBAgent
from pro_v.agent.pychecker import PyCheckerAgent
from pro_v.tools.pychecker_worker import get_ray_pychecker_worker_cls
from pro_v.utils.llm_client import (
    create_llm_client_from_config,
    create_pychecker_llm_client_from_config
)
from pro_v.utils.llm_worker import create_distributed_llm_client

def get_circuit_type(rtl_code: str) -> str:
    """
    Determine circuit type by analyzing RTL code.
    Sequential circuits use clock edges (posedge/negedge).
    Combinational circuits do not.
    
    Args:
        rtl_code: RTL code to analyze
        
    Returns:
        "seq" if sequential (contains posedge/negedge), "cmb" if combinational
    """
    
    
    rtl_lower = rtl_code.lower()
    if "posedge" in rtl_lower or "negedge" in rtl_lower:
        return "SEQ"
    else:
        return "CMB"


def load_benchmark_data(benchmark_path: str) -> Dict[int, Dict[str, Any]]:
    """Load benchmark data from test_benchmark_new.json

    Args:
        benchmark_path: Path to test_benchmark_new.json

    Returns:
        Dictionary mapping task_number to task data
    """
    print(f"Loading benchmark data from: {benchmark_path}")

    if not os.path.exists(benchmark_path):
        print(f"ERROR: Benchmark file not found: {benchmark_path}")
        return {}

    try:
        with open(benchmark_path, 'r') as f:
            benchmark_list = json.load(f)

        # Create mapping from task_number to task data
        task_map = {}
        for task in benchmark_list:
            task_number = task.get("task_number")
            if task_number is not None:
                task_map[task_number] = task

        print(f"Loaded {len(task_map)} tasks from benchmark")
        return task_map

    except Exception as e:
        print(f"ERROR: Failed to load benchmark data: {e}")
        import traceback
        traceback.print_exc()
        return {}


def process_single_task(
    task_number: int,
    rtl_code: str,
    description: str,
    header: str,
    output_base_dir: str,
    gen_tb_agent: GenTBAgent,
    pychecker_agent: PyCheckerAgent,
    task_id: str = None,
    worker=None
) -> Dict[str, Any]:
    """Process a single task: GenTB -> PyChecker -> Validation

    Args:
        task_number: Task number
        rtl_code: RTL code
        specification: Specification description
        output_base_dir: Base output directory
        gen_tb_agent: GenTB agent instance
        pychecker_agent: PyChecker agent instance
        task_id: Task identifier

    Returns:
        Processing result dictionary
    """
    start_time = time.time()
    latency_breakdown = {}  # Track latency for each stage

    print(f"\n{'='*60}")
    print(f"Processing Task {task_number}")
    print(f"{'='*60}")

    # Determine circuit type by analyzing RTL code
    circuit_type = get_circuit_type(rtl_code)
    print(f"Circuit type: {circuit_type}")

    # Create output directory for this task
    # Convert to absolute path to avoid issues with different working directories
    output_dir = os.path.abspath(os.path.join(output_base_dir, f"task_{task_number}"))
    os.makedirs(output_dir, exist_ok=True)

    # Save task metadata
    task_info = {
        "task_number": task_number,
        "task_id": task_id or f"task_{task_number}",
        "circuit_type": circuit_type,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    with open(os.path.join(output_dir, "task_info.json"), "w") as f:
        json.dump(task_info, f, indent=2)

    # Save RTL code and specification
    if rtl_code:
        with open(os.path.join(output_dir, "module_code.v"), "w") as f:
            f.write(rtl_code)

    if description:
        with open(os.path.join(output_dir, "description.txt"), "w") as f:
            f.write(description)

    result = {
        "task_number": task_number,
        "circuit_type": circuit_type,
        "success": False,
        "error": None
    }

    # Step 1: Run GenTBAgent to generate stimulus.json
    print(f"\n[Step 1] Running GenTBAgent...")
    gen_tb_start = time.time()
    gen_tb_result = gen_tb_agent.run(
        description=description,
        header=header,
        circuit_type=circuit_type,
        output_dir=output_dir
    )
    latency_breakdown["gen_tb"] = time.time() - gen_tb_start

    if not gen_tb_result["success"]:
        result["error"] = f"GenTB failed: {gen_tb_result.get('error', 'Unknown')}"
        result["gen_tb_result"] = gen_tb_result
        result["latency_breakdown"] = latency_breakdown
        print(f"✗ GenTBAgent FAILED: {result['error']}")
        result["total_time"] = time.time() - start_time
        return result

    print(f"✓ GenTBAgent succeeded (attempt {gen_tb_result['attempt']}) - {latency_breakdown['gen_tb']:.2f}s")
    print(f"  Generated {gen_tb_result['num_test_cases']} test cases")
    result["gen_tb_result"] = gen_tb_result
    stimulus_json_path = gen_tb_result["stimulus_json_path"]

    # Step 2: Run PyCheckerAgent to generate golden_dut.py and testbench.json
    print(f"\n[Step 2] Running PyCheckerAgent...")
    pychecker_start = time.time()
    pychecker_result = pychecker_agent.run(
        description=description,
        header=header,
        circuit_type=circuit_type,
        stimulus_json_path=stimulus_json_path,
        output_dir=output_dir
    )
    latency_breakdown["pychecker"] = time.time() - pychecker_start

    if not pychecker_result["success"]:
        result["error"] = f"PyChecker failed: {pychecker_result.get('error', 'Unknown')}"
        result["pychecker_result"] = pychecker_result
        result["latency_breakdown"] = latency_breakdown
        print(f"✗ PyCheckerAgent FAILED: {result['error']}")
        result["total_time"] = time.time() - start_time
        return result

    print(f"✓ PyCheckerAgent succeeded (attempt {pychecker_result['attempt']}) - {latency_breakdown['pychecker']:.2f}s")
    print(f"  Generated testbench with {pychecker_result['num_test_cases']} test cases")
    result["pychecker_result"] = pychecker_result

    # Step 3: Run Verilog simulation
    print(f"\n[Step 3] Running Verilog simulation...")
    simulation_start = time.time()

    if not worker:
        print(f"  No worker available, skipping simulation")
        result["validation_result"] = {"skipped": True, "reason": "No worker available"}
        result["success"] = True
        latency_breakdown["simulation"] = 0.0
    else:
        try:
            import ray
            # Pass output_dir (task root directory) to worker
            # Worker will handle all file copying and simulation setup internally
            # Increased timeout to 600s for complex simulations
            obj_ref = worker.run_verilog_simulation.remote(
                task_folder=output_dir,
                circuit_type=circuit_type,
                timeout=600.0
            )
            # Set ray.get timeout to 1800s (30 min) to allow worker + Ray overhead
            sim_success, sim_error, sim_results = ray.get(obj_ref, timeout=1800.0)
            latency_breakdown["simulation"] = time.time() - simulation_start

            # Extract key simulation results
            compile_success = sim_results.get("compile_success", False)
            all_tests_passed = sim_results.get("all_tests_passed", False)
            reward = sim_results.get("reward", 0.0)

            # Build validation result
            result["validation_result"] = {
                "compile_success": compile_success,
                "all_tests_passed": all_tests_passed,
                "reward": reward,
                "error": sim_error if not sim_success else None
            }
            result["simulation_results"] = sim_results

            # Display results
            if compile_success:
                test_status = "PASSED" if all_tests_passed else "FAILED"
                symbol = "✓" if all_tests_passed else "⚠"
                print(f"{symbol} Compilation: SUCCESS | Tests: {test_status} | Reward: {reward:.2f} - {latency_breakdown['simulation']:.2f}s")
                result["success"] = True
            else:
                print(f"✗ Compilation: FAILED - {latency_breakdown['simulation']:.2f}s")
                if sim_error:
                    print(f"  Error: {sim_error}")
                result["error"] = f"Compilation failed: {sim_error or 'Unknown error'}"
                result["success"] = False

        except Exception as e:
            latency_breakdown["simulation"] = time.time() - simulation_start
            print(f"✗ Simulation error: {str(e)} - {latency_breakdown['simulation']:.2f}s")
            result["validation_result"] = {"error": str(e)}
            result["error"] = f"Simulation exception: {str(e)}"
            result["success"] = False

    # Save result with latency breakdown
    result["total_time"] = time.time() - start_time
    result["latency_breakdown"] = latency_breakdown
    result_path = os.path.join(output_dir, "task_result.json")
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2)

    status = "SUCCESS" if result["success"] else "FAILED"
    print(f"\nTask {task_number} {status} in {result['total_time']:.2f}s")
    print(f"  Latency breakdown: GenTB={latency_breakdown.get('gen_tb', 0):.2f}s | "
          f"PyChecker={latency_breakdown.get('pychecker', 0):.2f}s | "
          f"Simulation={latency_breakdown.get('simulation', 0):.2f}s")
    print(f"{'='*60}\n")

    return result



def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Pro-V Top Agent - Simplified Version")

    parser.add_argument("--model", type=str, required=True, help="Model name to use")
    parser.add_argument("--vllm_endpoints", type=str, required=True, help="Comma-separated vLLM endpoints")
    parser.add_argument("--experiment_name", type=str, required=True, help="Experiment name")
    parser.add_argument("--task_numbers", type=str, help="Comma-separated task numbers to process")
    parser.add_argument("--benchmark_path", type=str,
                        default="verilog-eval/HDLBits/test_benchmark_new.json",
                        help="Path to benchmark file")
    parser.add_argument("--max_concurrency", type=int, default=8,
                        help="Maximum number of tasks to process concurrently (default: auto-detect GPUs, max 100)")
    parser.add_argument("--use_gpu_workers", action="store_true",
                        help="Use Ray GPU workers for LLM inference (one worker per GPU)")

    args = parser.parse_args()

    # Validate max_concurrency
    max_concurrency = min(max(1, args.max_concurrency), 100)
    if args.max_concurrency != max_concurrency:
        print(f"WARNING: max_concurrency adjusted from {args.max_concurrency} to {max_concurrency} (max 100)")

    print(f"\n{'='*70}")
    print(f"Pro-V Simplified Pipeline: {args.experiment_name}")
    print(f"Max Concurrency: {max_concurrency}")
    print(f"{'='*70}\n")

    # Load benchmark data first
    benchmark_data = load_benchmark_data(args.benchmark_path)

    if not benchmark_data:
        print("ERROR: Failed to load benchmark data. Exiting.")
        return 1

    # Determine which tasks to process
    if args.task_numbers:
        task_numbers = [int(t.strip()) for t in args.task_numbers.split(',')]
    else:
        # Get all task numbers from benchmark data
        task_numbers = sorted(benchmark_data.keys())
        print(f"Loaded {len(task_numbers)} tasks from benchmark")

    print(f"Processing {len(task_numbers)} tasks: {task_numbers}")

    # Detect available GPUs
    import subprocess
    try:
        gpu_count_output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index", "--format=csv,noheader"],
            text=True
        )
        available_gpus = len(gpu_count_output.strip().split('\n'))
        print(f"\nDetected {available_gpus} GPUs")
    except Exception as e:
        available_gpus = 0
        print(f"\nWARNING: Could not detect GPUs: {e}")

    # Adjust max_concurrency based on available GPUs
    if available_gpus > 0 and max_concurrency < available_gpus:
        print(f"INFO: Adjusting max_concurrency from {max_concurrency} to {available_gpus} to utilize all GPUs")
        max_concurrency = available_gpus

    # Create LLM clients
    print(f"\nInitializing LLM clients...")

    if args.use_gpu_workers and available_gpus > 0:
        # Use GPU-aware Ray workers for LLM inference
        print(f"  Using Ray GPU workers for LLM inference...")
        print(f"  Creating {available_gpus} LLM workers (one per GPU)...")

        llm_client = create_distributed_llm_client(
            num_gpus=available_gpus,
            endpoints_csv=args.vllm_endpoints,
            model_name=args.model,
            temperature=0.0,
            top_p=0.1,
            max_tokens=20000
        )

        pychecker_llm_client = create_distributed_llm_client(
            num_gpus=available_gpus,
            endpoints_csv=args.vllm_endpoints,
            model_name=args.model,
            temperature=0.6,
            top_p=0.95,
            max_tokens=20000
        )

        print(f"  ✓ Created {available_gpus} GPU workers for GenTB (T=0.0)")
        print(f"  ✓ Created {available_gpus} GPU workers for PyChecker (T=0.6)")
    else:
        # Use standard vLLM clients (vLLM handles load balancing)
        if args.use_gpu_workers:
            print(f"  WARNING: --use_gpu_workers specified but no GPUs detected")
            print(f"  Falling back to standard vLLM clients...")

        llm_client = create_llm_client_from_config(
            endpoints_csv=args.vllm_endpoints,
            model_name=args.model
        )

        pychecker_llm_client = create_pychecker_llm_client_from_config(
            endpoints_csv=args.vllm_endpoints,
            model_name=args.model
        )

        print(f"  - GenTB LLM: {args.model} (T={llm_client.temperature})")
        print(f"  - PyChecker LLM: {args.model} (T={pychecker_llm_client.temperature})")

    # Create worker pool for executing Python code and simulations
    print(f"\nInitializing worker pool...")
    
    # Check if Ray is available
    try:
        import ray
        ray_available = True
        print(f"  Ray is available: {ray.__version__}")
    except ImportError:
        ray_available = False
        print(f"  WARNING: Ray is not installed. Workers will not be available.")
        print(f"  To enable simulation validation, install ray: pip install ray")
    
    # Create CPU workers for Verilog simulation
    # CRITICAL FIX: Create 2 workers per task (one for GenTB, one for PyChecker)
    # to avoid worker contention and timeout issues
    sim_workers = []
    num_sim_workers_to_create = max_concurrency * 2  # 2 workers per concurrent task

    print(f"  Creating {num_sim_workers_to_create} CPU workers (2 per task) for Python execution & simulation...")
    worker_cls = get_ray_pychecker_worker_cls(num_workers=num_sim_workers_to_create)

    if worker_cls is not None:
        for i in range(num_sim_workers_to_create):
            worker = worker_cls.remote(worker_id=i, timeout=600)
            sim_workers.append(worker)
            if (i+1) % 10 == 0 or i == num_sim_workers_to_create - 1:
                print(f"    Created {i+1}/{num_sim_workers_to_create} workers...")
        print(f"✓ Created {len(sim_workers)} CPU workers for Python execution & simulation")
    else:
        print("WARNING: Ray workers not available, will skip simulation validation")

    # Keep backwards compatibility
    workers = sim_workers
       
    
    if not workers:
        print(f"\n{'='*70}")
        print(f"WARNING: No workers available - simulation validation will be skipped")
        print(f"Tasks will complete GenTB and PyChecker steps only")
        print(f"{'='*70}\n")

    print(f"Agents will be created per-task for proper worker assignment\n")

    # Create output directory
    # Use absolute path to avoid issues with different working directories
    output_base_dir = os.path.abspath(f"outputs/{args.experiment_name}")
    os.makedirs(output_base_dir, exist_ok=True)

    # Prepare tasks for processing
    tasks_to_process = []
    for task_num in task_numbers:
        if task_num not in benchmark_data:
            print(f"WARNING: Task {task_num} not found in benchmark data. Skipping.")
            continue
        tasks_to_process.append((task_num, benchmark_data[task_num]))

    print(f"Processing {len(tasks_to_process)} tasks with max_concurrency={max_concurrency}\n")

    # Process tasks concurrently
    all_results = []
    start_time = time.time()

    if max_concurrency == 1:
        # Sequential processing - use first worker if available
        worker = workers[0] if workers else None
        for task_num, task in tasks_to_process:
            # Create task-specific agents with worker
            task_gen_tb_agent = GenTBAgent(llm_client=llm_client, max_retries=3, worker=worker)
            task_pychecker_agent = PyCheckerAgent(llm_client=pychecker_llm_client, max_retries=3, worker=worker)
            
            result = process_single_task(
                task_number=task_num,
                rtl_code=task.get("module_code", ""),
                description=task.get("description", ""),
                header=task.get("header", ""),
                output_base_dir=output_base_dir,
                gen_tb_agent=task_gen_tb_agent,
                pychecker_agent=task_pychecker_agent,
                task_id=task.get("task_id", f"task_{task_num}"),
                worker=worker
            )
            all_results.append(result)
    else:
        # Concurrent processing - assign 2 workers per task
        # CRITICAL FIX: Each agent gets its own worker to avoid contention
        worker_index = 0

        def get_workers_for_task():
            """Get 2 workers for a task (one for GenTB, one for PyChecker)"""
            nonlocal worker_index
            # Get 2 consecutive workers for this task
            gentb_worker = workers[worker_index % len(workers)]
            pychecker_worker = workers[(worker_index + 1) % len(workers)]
            worker_index += 2
            return gentb_worker, pychecker_worker

        with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
            # Submit all tasks
            future_to_task = {}
            for task_num, task in tasks_to_process:
                # Assign 2 dedicated workers to this task
                gentb_worker, pychecker_worker = get_workers_for_task()
                # Create task-specific agents with dedicated workers
                # GenTBAgent gets gentb_worker, PyCheckerAgent gets pychecker_worker
                task_gen_tb_agent = GenTBAgent(llm_client=llm_client, max_retries=3, worker=gentb_worker)
                task_pychecker_agent = PyCheckerAgent(llm_client=pychecker_llm_client, max_retries=3, worker=pychecker_worker)
                
                future = executor.submit(
                    process_single_task,
                    task_number=task_num,
                    rtl_code=task.get("module_code", ""),
                    description=task.get("description", ""),
                    header=task.get("header", ""),
                    output_base_dir=output_base_dir,
                    gen_tb_agent=task_gen_tb_agent,
                    pychecker_agent=task_pychecker_agent,
                    task_id=task.get("task_id", f"task_{task_num}"),
                    worker=pychecker_worker  # Use pychecker_worker for simulation validation
                )
                future_to_task[future] = task_num

            # Collect results as they complete
            completed = 0
            for future in as_completed(future_to_task):
                task_num = future_to_task[future]
                completed += 1
                try:
                    result = future.result()
                    all_results.append(result)
                    print(f"[Progress] Completed {completed}/{len(tasks_to_process)} tasks")
                except Exception as e:
                    print(f"ERROR: Task {task_num} raised exception: {e}")
                    import traceback
                    traceback.print_exc()
                    all_results.append({
                        "task_number": task_num,
                        "success": False,
                        "error": f"Exception: {str(e)}",
                        "total_time": 0
                    })

    total_elapsed = time.time() - start_time
    print(f"\nAll tasks completed in {total_elapsed:.2f}s")

    # Calculate statistics
    total_tasks = len(all_results)
    successful_tasks = sum(1 for r in all_results if r["success"])

    # Sort results by task_number for consistent output
    all_results.sort(key=lambda x: x.get("task_number", 0))

    # Calculate compile and simulation statistics
    compile_success_count = sum(
        1 for r in all_results
        if r.get("validation_result", {}).get("compile_success", False)
    )
    simulation_pass_count = sum(
        1 for r in all_results
        if r.get("validation_result", {}).get("all_tests_passed", False)
    )

    # Calculate latency statistics
    total_gen_tb_time = sum(r.get("latency_breakdown", {}).get("gen_tb", 0) for r in all_results)
    total_pychecker_time = sum(r.get("latency_breakdown", {}).get("pychecker", 0) for r in all_results)
    total_simulation_time = sum(r.get("latency_breakdown", {}).get("simulation", 0) for r in all_results)

    avg_gen_tb_latency = total_gen_tb_time / total_tasks if total_tasks > 0 else 0.0
    avg_pychecker_latency = total_pychecker_time / total_tasks if total_tasks > 0 else 0.0
    avg_simulation_latency = total_simulation_time / total_tasks if total_tasks > 0 else 0.0
    avg_total_latency = sum(r.get("total_time", 0) for r in all_results) / total_tasks if total_tasks > 0 else 0.0

    # Collect per-task latencies for detailed analysis
    task_latencies = []
    for r in all_results:
        task_latencies.append({
            "task_number": r.get("task_number"),
            "total_time": r.get("total_time", 0),
            "gen_tb": r.get("latency_breakdown", {}).get("gen_tb", 0),
            "pychecker": r.get("latency_breakdown", {}).get("pychecker", 0),
            "simulation": r.get("latency_breakdown", {}).get("simulation", 0)
        })

    overall_stats = {
        "experiment_name": args.experiment_name,
        "max_concurrency": max_concurrency,
        "total_tasks": total_tasks,
        "successful_tasks": successful_tasks,
        "failed_tasks": total_tasks - successful_tasks,
        "success_rate": successful_tasks / total_tasks if total_tasks > 0 else 0.0,
        "compile_success_count": compile_success_count,
        "compile_success_rate": compile_success_count / total_tasks if total_tasks > 0 else 0.0,
        "simulation_pass_count": simulation_pass_count,
        "simulation_pass_rate": simulation_pass_count / total_tasks if total_tasks > 0 else 0.0,
        "total_wall_time": total_elapsed,
        "total_cpu_time": sum(r.get("total_time", 0) for r in all_results),
        "avg_time_per_task": avg_total_latency,
        "latency_stats": {
            "avg_gen_tb_latency": avg_gen_tb_latency,
            "avg_pychecker_latency": avg_pychecker_latency,
            "avg_simulation_latency": avg_simulation_latency,
            "avg_total_latency": avg_total_latency,
            "total_gen_tb_time": total_gen_tb_time,
            "total_pychecker_time": total_pychecker_time,
            "total_simulation_time": total_simulation_time
        },
        "per_task_latencies": task_latencies
    }

    # Save results
    with open(os.path.join(output_base_dir, "overall_stats.json"), "w") as f:
        json.dump(overall_stats, f, indent=2)

    with open(os.path.join(output_base_dir, "all_results.json"), "w") as f:
        json.dump(all_results, f, indent=2)

    # Save separate latency report for easier analysis
    latency_report = {
        "experiment_name": args.experiment_name,
        "total_tasks": total_tasks,
        "average_latencies": {
            "gen_tb": avg_gen_tb_latency,
            "pychecker": avg_pychecker_latency,
            "simulation": avg_simulation_latency,
            "total": avg_total_latency
        },
        "total_latencies": {
            "gen_tb": total_gen_tb_time,
            "pychecker": total_pychecker_time,
            "simulation": total_simulation_time,
            "total": sum(r.get("total_time", 0) for r in all_results)
        },
        "per_task_latencies": task_latencies
    }

    with open(os.path.join(output_base_dir, "latency_report.json"), "w") as f:
        json.dump(latency_report, f, indent=2)

    # Print summary
    print(f"\n{'='*70}")
    print(f"EVALUATION COMPLETED")
    print(f"{'='*70}")
    print(f"Total tasks:       {total_tasks}")
    print(f"Successful tasks:  {successful_tasks} ({overall_stats['success_rate']:.1%})")
    print(f"Failed tasks:      {overall_stats['failed_tasks']}")
    print(f"\nCompile & Simulation Results:")
    print(f"  Compile Success: {overall_stats['compile_success_count']}/{total_tasks} ({overall_stats['compile_success_rate']:.1%})")
    print(f"  Simulation Pass: {overall_stats['simulation_pass_count']}/{total_tasks} ({overall_stats['simulation_pass_rate']:.1%})")
    print(f"\nTiming:")
    print(f"  Max concurrency: {max_concurrency}")
    print(f"  Total wall time: {overall_stats['total_wall_time']:.2f}s")
    print(f"  Total CPU time:  {overall_stats['total_cpu_time']:.2f}s")
    print(f"  Avg time/task:   {overall_stats['avg_time_per_task']:.2f}s")
    print(f"\nLatency Statistics (Average per task):")
    print(f"  GenTB:       {avg_gen_tb_latency:.2f}s")
    print(f"  PyChecker:   {avg_pychecker_latency:.2f}s")
    print(f"  Simulation:  {avg_simulation_latency:.2f}s")
    print(f"  Total:       {avg_total_latency:.2f}s")
    print(f"\nLatency Statistics (Total across all tasks):")
    print(f"  GenTB:       {total_gen_tb_time:.2f}s")
    print(f"  PyChecker:   {total_pychecker_time:.2f}s")
    print(f"  Simulation:  {total_simulation_time:.2f}s")
    print(f"{'='*70}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
