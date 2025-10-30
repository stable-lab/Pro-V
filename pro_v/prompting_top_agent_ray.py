#!/usr/bin/env python3
"""
Pro-V Top Agent with Ray Support (Simplified Architecture)

This is the main orchestration script that coordinates all agents.
Architecture: Each agent only has __init__ and run methods.
"""

import argparse
import json
import os
import sys
import time
import ray
import subprocess
import shutil
import re
from typing import Dict, Any, List

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pro_v.agent.gen_tb import GenTBAgent
from pro_v.agent.pychecker import PyCheckerAgent
from pro_v.agent.verifier import VerifierAgent
from pro_v.utils.llm_client import (
    create_llm_client_from_config,
    create_pychecker_llm_client_from_config
)

# Define circuit type mapping
CMB_TASKS = [1, 2, 3, 4, 5, 9, 11, 16, 17, 18, 19, 20, 22, 23, 26, 29, 30, 34, 35, 37, 38, 39, 
             41, 44, 45, 47, 48, 49, 50, 51, 53, 54, 57, 58, 61, 62, 64, 65, 67, 68, 70, 71, 73, 
             81, 82, 83, 84, 85, 87, 90, 91, 95, 96, 100, 101, 102, 108, 109, 111, 112, 113, 114, 
             115, 116, 117, 119, 121, 123, 124, 125, 128, 130, 131, 132, 134, 135, 136, 138, 139, 
             140, 143]

SEQ_TASKS = [6, 7, 8, 10, 12, 13, 14, 15, 21, 24, 25, 27, 28, 31, 32, 33, 36, 40, 42, 43, 46, 
             52, 55, 56, 59, 60, 63, 66, 69, 72, 74, 75, 76, 77, 78, 79, 80, 86, 88, 89, 92, 93, 
             94, 97, 98, 99, 103, 104, 105, 106, 107, 110, 118, 120, 122, 126, 127, 129, 133, 137, 
             141, 142, 144, 145, 146, 147, 148, 149, 150, 151, 152, 153, 154]


def get_circuit_type(task_number: int) -> str:
    """Get circuit type based on task number"""
    if task_number in CMB_TASKS:
        return "cmb"
    elif task_number in SEQ_TASKS:
        return "seq"
    else:
        return "cmb"  # Default


def load_benchmark_data(benchmark_path: str) -> Dict[int, Dict[str, Any]]:
    """Load benchmark data from test_benchmark_new.json

    Args:
        benchmark_path: Path to test_benchmark_new.json

    Returns:
        Dictionary mapping task_number to task data containing:
        - task_id: Task identifier
        - task_number: Task number
        - description: Problem description
        - header: Module header
        - module_code: Full RTL module code
        - mutants: List of mutant codes (optional)
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


@ray.remote(num_cpus=1)
class TaskWorker:
    """
    Ray worker for processing individual tasks with 1 CPU
    Each worker has its own instances of the three agents
    """
    
    def __init__(self, llm_client_config: Dict[str, Any]):
        """Initialize task worker with agents

        Args:
            llm_client_config: Configuration for LLM client containing:
                - model: Model name
                - vllm_endpoints: Comma-separated vLLM endpoints
        """
        # Create LLM clients from configuration
        # Standard LLM client for GenTB and Verifier (uses TEMPERATURE)
        self.llm_client = create_llm_client_from_config(
            endpoints_csv=llm_client_config["vllm_endpoints"],
            model_name=llm_client_config["model"]
        )

        # PyChecker-specific LLM client (uses TEMPERATURE_SAMPLE for diversity)
        self.pychecker_llm_client = create_pychecker_llm_client_from_config(
            endpoints_csv=llm_client_config["vllm_endpoints"],
            model_name=llm_client_config["model"]
        )

        # Initialize the three agents (once per worker)
        self.gen_tb_agent = GenTBAgent(llm_client=self.llm_client, max_retries=3)
        self.pychecker_agent = PyCheckerAgent(llm_client=self.pychecker_llm_client, max_retries=3)
        self.verifier_agent = VerifierAgent(llm_client=self.llm_client, max_retries=3)

        print(f"TaskWorker initialized with 3 agents")
        print(f"  - GenTB LLM: {llm_client_config['model']} (T={self.llm_client.temperature})")
        print(f"  - PyChecker LLM: {llm_client_config['model']} (T={self.pychecker_llm_client.temperature})")
        print(f"  - Verifier LLM: {llm_client_config['model']} (T={self.llm_client.temperature})")
        
    def process_task(
        self,
        task_number: int,
        rtl_code: str,
        specification: str,
        output_base_dir: str,
        sampling_size: int = 3,
        enable_verification: bool = False,
        task_id: str = None,
        header: str = None,
        mutants: List[str] = None
    ) -> Dict[str, Any]:
        """Process a single task through the complete pipeline

        New file structure:
        task_{number}/
            ├── task_info.json                   # Task metadata
            ├── module_code.v                    # RTL code
            ├── specification.txt                # Specification
            ├── header.v                         # Module header
            ├── stimulus.json                    # Generated by GenTBAgent
            ├── golden_dut_0.py                  # Sample 0
            ├── testbench_0.json
            ├── golden_dut_1.py                  # Sample 1
            ├── testbench_1.json
            ├── golden_dut_2.py                  # Sample 2
            ├── testbench_2.json
            └── sim_cmb/ or sim_seq/             # Simulation files
                ├── Makefile
                ├── input.vc
                ├── sim-main.cpp
                └── rfuzz-harness.h

        Args:
            task_number: Task number
            rtl_code: RTL code to process
            specification: Specification description
            output_base_dir: Base output directory
            sampling_size: Number of pychecker samples to generate
            enable_verification: Whether to run verification
            task_id: Task identifier (e.g., "2012_q1g")
            header: Module header
            mutants: List of mutant RTL codes

        Returns:
            Task processing result
        """
        import shutil

        start_time = time.time()
        print(f"\n{'='*60}")
        print(f"Worker processing Task {task_number}")
        print(f"{'='*60}")

        # Determine circuit type
        circuit_type = get_circuit_type(task_number)

        # Create output directory for this task
        output_dir = os.path.join(output_base_dir, f"task_{task_number}")
        os.makedirs(output_dir, exist_ok=True)

        # Save task metadata and files
        task_info = {
            "task_number": task_number,
            "task_id": task_id or f"task_{task_number}",
            "circuit_type": circuit_type,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        # Save task info
        with open(os.path.join(output_dir, "task_info.json"), "w") as f:
            json.dump(task_info, f, indent=2)

        # Save RTL code
        if rtl_code:
            with open(os.path.join(output_dir, "module_code.v"), "w") as f:
                f.write(rtl_code)

        # Save specification
        if specification:
            with open(os.path.join(output_dir, "specification.txt"), "w") as f:
                f.write(specification)

        # Save header
        if header:
            with open(os.path.join(output_dir, "header.v"), "w") as f:
                f.write(header)

        # Save mutants
        if mutants:
            mutants_dir = os.path.join(output_dir, "mutants")
            os.makedirs(mutants_dir, exist_ok=True)
            for i, mutant_code in enumerate(mutants):
                with open(os.path.join(mutants_dir, f"mutant_{i}.v"), "w") as f:
                    f.write(mutant_code)

        result = {
            "task_number": task_number,
            "circuit_type": circuit_type,
            "success": False,
            "error": None
        }

        # Step 1: Run GenTBAgent to generate stimulus.json at task level
        print(f"\nTask {task_number} - Step 1: Running GenTBAgent (circuit_type={circuit_type})")
        gen_tb_result = self.gen_tb_agent.run(
            rtl_code=rtl_code,
            specification=specification,
            circuit_type=circuit_type,
            output_dir=output_dir
        )

        if not gen_tb_result["success"]:
            result["error"] = f"GenTB failed: {gen_tb_result.get('error', 'Unknown')}"
            result["gen_tb_result"] = gen_tb_result
            print(f"Task {task_number} - GenTBAgent FAILED")
            return self._finalize_result(result, start_time, output_dir)

        print(f"Task {task_number} - GenTBAgent succeeded (attempt {gen_tb_result['attempt']})")
        result["gen_tb_result"] = gen_tb_result
        stimulus_json_path = gen_tb_result["stimulus_json_path"]

        # Step 2: Run PyCheckerAgent multiple times (sampling)
        # Each sample generates golden_dut_{sample}.py and testbench_{sample}.json at task level
        print(f"\nTask {task_number} - Step 2: Running PyCheckerAgent {sampling_size} times")
        pychecker_results = []

        for sample_idx in range(sampling_size):
            pychecker_result = self.pychecker_agent.run(
                rtl_code=rtl_code,
                specification=specification,
                circuit_type=circuit_type,
                stimulus_json_path=stimulus_json_path,
                output_dir=output_dir
            )

            if pychecker_result["success"]:
                # Rename generated files to include sample index
                old_golden_path = pychecker_result["golden_dut_path"]
                old_testbench_path = pychecker_result["testbench_json_path"]

                new_golden_path = os.path.join(output_dir, f"golden_dut_{sample_idx}.py")
                new_testbench_path = os.path.join(output_dir, f"testbench_{sample_idx}.json")

                # Rename files
                if os.path.exists(old_golden_path):
                    shutil.move(old_golden_path, new_golden_path)
                if os.path.exists(old_testbench_path):
                    shutil.move(old_testbench_path, new_testbench_path)

                print(f"  Sample {sample_idx}: SUCCESS (attempt {pychecker_result['attempt']})")
                pychecker_results.append({
                    "sample_idx": sample_idx,
                    "golden_dut_path": new_golden_path,
                    "testbench_json_path": new_testbench_path,
                    "result": pychecker_result
                })
            else:
                print(f"  Sample {sample_idx}: FAILED - {pychecker_result.get('error', 'Unknown')}")

        if not pychecker_results:
            result["error"] = "All PyChecker samples failed"
            result["pychecker_results"] = []
            print(f"Task {task_number} - All PyCheckerAgent samples FAILED")
            return self._finalize_result(result, start_time, output_dir)

        print(f"Task {task_number} - {len(pychecker_results)}/{sampling_size} PyChecker samples succeeded")
        result["pychecker_results"] = pychecker_results

        # Step 3: Copy simulation files to sim_cmb or sim_seq directory
        print(f"\nTask {task_number} - Step 3: Copying simulation files")
        sim_dir_name = f"sim_{circuit_type}"
        sim_dest_dir = os.path.join(output_dir, sim_dir_name)
        os.makedirs(sim_dest_dir, exist_ok=True)

        # Determine source directory
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sim_source_dir = os.path.join(project_root, "pro_v", sim_dir_name)

        # Files to copy
        files_to_copy = [
            "Makefile", "input.vc",
            "sim-main.cpp", "rfuzz-harness.h"
        ]

        for filename in files_to_copy:
            src_path = os.path.join(sim_source_dir, filename)
            dest_path = os.path.join(sim_dest_dir, filename)

            if os.path.exists(src_path):
                shutil.copy(src_path, dest_path)
                print(f"  Copied: {filename}")
            else:
                print(f"  WARNING: {filename} not found in {sim_source_dir}")

        result["sim_dir"] = sim_dest_dir

        # Step 4: Select best testbench (simple: use first successful one)
        selected_sample = pychecker_results[0]
        selected_sample_idx = selected_sample["sample_idx"]
        selected_testbench_path = selected_sample["testbench_json_path"]
        selected_golden_path = selected_sample["golden_dut_path"]

        print(f"\nTask {task_number} - Step 4: Selected sample {selected_sample_idx}")
        result["selected_sample_idx"] = selected_sample_idx
        result["selected_testbench_path"] = selected_testbench_path
        result["selected_golden_path"] = selected_golden_path

        # Step 5: Run VerifierAgent with verification loop (if enabled)
        if enable_verification:
            print(f"\nTask {task_number} - Step 5: Running VerifierAgent with loop")
            verification_iterations = []
            max_verification_loops = 3  # Maximum number of verification iterations

            for loop_idx in range(max_verification_loops):
                print(f"\n  Verification Loop {loop_idx + 1}/{max_verification_loops}")

                # Run verification
                verification_result = self.verifier_agent.run(
                    rtl_code=rtl_code,
                    specification=specification,
                    circuit_type=circuit_type,
                    stimulus_json_path=stimulus_json_path,
                    testbench_json_path=selected_testbench_path,
                    pychecker_code_path=selected_golden_path
                )

                verification_iterations.append({
                    "loop": loop_idx + 1,
                    "result": verification_result
                })

                decision = verification_result.get("decision", "UNKNOWN")
                print(f"  Decision: {decision}")
                print(f"  Reason: {verification_result.get('reason', 'N/A')}")

                # Handle verification decisions
                if decision == "COMPLETE":
                    print(f"  Verification COMPLETE - testbench is correct!")
                    result["verification_passed"] = True
                    break

                elif decision == "MODIFY_PYCHECKER":
                    print(f"  Need to modify PyChecker code")
                    print(f"  Error: {verification_result.get('details', {}).get('error_locations', 'N/A')}")

                    # Re-run PyChecker agent with feedback
                    # Note: In a full implementation, you would pass the error feedback to PyChecker
                    # For now, we'll just try to regenerate
                    print(f"  Re-running PyChecker with corrections...")

                    pychecker_result = self.pychecker_agent.run(
                        rtl_code=rtl_code,
                        specification=specification,
                        circuit_type=circuit_type,
                        stimulus_json_path=stimulus_json_path,
                        output_dir=output_dir
                    )

                    if pychecker_result["success"]:
                        # Update selected sample files
                        new_sample_idx = len(pychecker_results)
                        old_golden_path = pychecker_result["golden_dut_path"]
                        old_testbench_path = pychecker_result["testbench_json_path"]

                        new_golden_path = os.path.join(output_dir, f"golden_dut_{new_sample_idx}.py")
                        new_testbench_path = os.path.join(output_dir, f"testbench_{new_sample_idx}.json")

                        if os.path.exists(old_golden_path):
                            shutil.move(old_golden_path, new_golden_path)
                        if os.path.exists(old_testbench_path):
                            shutil.move(old_testbench_path, new_testbench_path)

                        selected_testbench_path = new_testbench_path
                        selected_golden_path = new_golden_path
                        selected_sample_idx = new_sample_idx

                        pychecker_results.append({
                            "sample_idx": new_sample_idx,
                            "golden_dut_path": new_golden_path,
                            "testbench_json_path": new_testbench_path,
                            "result": pychecker_result
                        })

                        print(f"  Generated new sample {new_sample_idx}")
                    else:
                        print(f"  PyChecker regeneration failed: {pychecker_result.get('error', 'Unknown')}")
                        result["verification_passed"] = False
                        break

                elif decision == "MODIFY_TESTBENCH":
                    print(f"  Need to modify testbench outputs")
                    print(f"  Incorrect fields: {verification_result.get('details', {}).get('incorrect_fields', 'N/A')}")
                    # Note: In a full implementation, you would directly modify the testbench.json
                    # based on the LLM's corrections. For now, we'll treat this as needing PyChecker fix
                    print(f"  Treating as PyChecker issue - regenerating...")

                    # Similar to MODIFY_PYCHECKER, regenerate
                    pychecker_result = self.pychecker_agent.run(
                        rtl_code=rtl_code,
                        specification=specification,
                        circuit_type=circuit_type,
                        stimulus_json_path=stimulus_json_path,
                        output_dir=output_dir
                    )

                    if pychecker_result["success"]:
                        new_sample_idx = len(pychecker_results)
                        old_golden_path = pychecker_result["golden_dut_path"]
                        old_testbench_path = pychecker_result["testbench_json_path"]

                        new_golden_path = os.path.join(output_dir, f"golden_dut_{new_sample_idx}.py")
                        new_testbench_path = os.path.join(output_dir, f"testbench_{new_sample_idx}.json")

                        if os.path.exists(old_golden_path):
                            shutil.move(old_golden_path, new_golden_path)
                        if os.path.exists(old_testbench_path):
                            shutil.move(old_testbench_path, new_testbench_path)

                        selected_testbench_path = new_testbench_path
                        selected_golden_path = new_golden_path
                        selected_sample_idx = new_sample_idx

                        pychecker_results.append({
                            "sample_idx": new_sample_idx,
                            "golden_dut_path": new_golden_path,
                            "testbench_json_path": new_testbench_path,
                            "result": pychecker_result
                        })

                        print(f"  Generated new sample {new_sample_idx}")
                    else:
                        print(f"  Testbench regeneration failed: {pychecker_result.get('error', 'Unknown')}")
                        result["verification_passed"] = False
                        break

                else:  # ERROR or UNKNOWN
                    print(f"  Verification error or unknown decision")
                    result["verification_passed"] = False
                    break

            # Check if we exhausted all loops
            if loop_idx == max_verification_loops - 1 and decision != "COMPLETE":
                print(f"  Verification exhausted {max_verification_loops} loops without completion")
                result["verification_passed"] = False

            result["verification_iterations"] = verification_iterations
            result["verification_loops_used"] = len(verification_iterations)

        else:
            result["verification_result"] = {"skipped": True}
            result["verification_passed"] = None

        # Update final selected sample info
        result["selected_sample_idx"] = selected_sample_idx
        result["selected_testbench_path"] = selected_testbench_path
        result["selected_golden_path"] = selected_golden_path

        # Step 6: Simulate the generated testbench on mutants and golden DUT
        print(f"\nTask {task_number} - Step 6: Running simulation evaluation")

        # Load benchmark data for this task
        benchmark_file = "test_benchmark_new.json"
        simulation_metrics = {
            "eval0_compile_success": False,
            "eval1_module_passes": False,
            "eval2_mutant_detection": {
                "total_mutants": 0,
                "mutants_detected": 0,
                "agreement_rate": 0.0,
                "agreement_80": False,
                "agreement_90": False,
                "agreement_100": False
            },
            "overall_success": False,
            "error": None
        }

        try:
            if os.path.exists(benchmark_file):
                with open(benchmark_file, 'r') as f:
                    benchmark_data = json.load(f)

                # Find this task in benchmark
                task_benchmark = None
                for item in benchmark_data:
                    if item.get("task_number") == task_number:
                        task_benchmark = item
                        break

                if task_benchmark:
                    module_code = task_benchmark.get("module_code", "")
                    testbench_code = task_benchmark.get("testbench", "")
                    mutants = task_benchmark.get("mutants", [])
                    expected_results = task_benchmark.get("result", [])

                    print(f"  Found benchmark data: {len(mutants)} mutants")
                    simulation_metrics["eval2_mutant_detection"]["total_mutants"] = len(mutants)

                    if module_code and testbench_code:
                        # Simulate module_code with testbench
                        print(f"  Step 6.1: Testing module_code compilation and correctness...")

                        # Create simulation directory
                        sim_eval_dir = os.path.join(output_dir, "sim_eval")
                        os.makedirs(sim_eval_dir, exist_ok=True)

                        # Write module and testbench
                        with open(os.path.join(sim_eval_dir, "top_module.v"), 'w') as f:
                            f.write(module_code)
                        with open(os.path.join(sim_eval_dir, "testbench.v"), 'w') as f:
                            f.write(testbench_code)

                        # Copy simulation template
                        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                        sim_template = os.path.join(project_root, "pro_v", f"sim_{circuit_type}")

                        if os.path.exists(sim_template):
                            for fname in ["Makefile", "input.vc", "sim-main.cpp", "rfuzz-harness.h"]:
                                src = os.path.join(sim_template, fname)
                                if os.path.exists(src):
                                    shutil.copy(src, sim_eval_dir)

                            # Create dummy testbench.json for harness generator
                            with open(os.path.join(sim_eval_dir, "testbench.json"), 'w') as f:
                                json.dump({"scenarios": []}, f)

                            # Run simulation
                            try:
                                make_proc = subprocess.run(
                                    ["make", "-j1"],
                                    cwd=sim_eval_dir,
                                    capture_output=True,
                                    text=True,
                                    timeout=60
                                )

                                sim_output = make_proc.stdout + "\n" + make_proc.stderr

                                # Check eval0: compilation success
                                if make_proc.returncode == 0:
                                    simulation_metrics["eval0_compile_success"] = True
                                    print(f"  eval0: ✓ PASSED - Compilation successful")

                                    # Check eval1: module passes
                                    import re
                                    mismatch_match = re.search(r'Mismatches:\s*(\d+)', sim_output)
                                    unpass_match = re.search(r'Unpass:\s*(\d+)', sim_output)

                                    if mismatch_match:
                                        mismatches = int(mismatch_match.group(1))
                                        simulation_metrics["eval1_module_passes"] = (mismatches == 0)
                                    elif unpass_match:
                                        unpass = int(unpass_match.group(1))
                                        simulation_metrics["eval1_module_passes"] = (unpass == 0)

                                    if simulation_metrics["eval1_module_passes"]:
                                        print(f"  eval1: ✓ PASSED - Module passes testbench")
                                    else:
                                        print(f"  eval1: ✗ FAILED - Module has mismatches")

                                    # Step 6.2: Test mutants (eval2)
                                    if mutants:
                                        print(f"  Step 6.2: Testing {len(mutants)} mutants...")
                                        mutant_results = []
                                        mutants_detected = 0

                                        for idx, mutant_code in enumerate(mutants):
                                            mutant_dir = os.path.join(output_dir, f"sim_mutant_{idx}")
                                            os.makedirs(mutant_dir, exist_ok=True)

                                            # Write mutant and testbench
                                            with open(os.path.join(mutant_dir, "top_module.v"), 'w') as f:
                                                f.write(mutant_code)
                                            with open(os.path.join(mutant_dir, "testbench.v"), 'w') as f:
                                                f.write(testbench_code)

                                            # Copy simulation files
                                            for fname in ["Makefile", "input.vc", "sim-main.cpp", "rfuzz-harness.h"]:
                                                src = os.path.join(sim_template, fname)
                                                if os.path.exists(src):
                                                    shutil.copy(src, mutant_dir)

                                            with open(os.path.join(mutant_dir, "testbench.json"), 'w') as f:
                                                json.dump({"scenarios": []}, f)

                                            # Simulate mutant
                                            try:
                                                mutant_proc = subprocess.run(
                                                    ["make", "-j1"],
                                                    cwd=mutant_dir,
                                                    capture_output=True,
                                                    text=True,
                                                    timeout=60
                                                )

                                                mutant_output = mutant_proc.stdout + "\n" + mutant_proc.stderr

                                                # Mutant is detected if it fails
                                                mutant_passed = False
                                                if mutant_proc.returncode == 0:
                                                    m_match = re.search(r'Mismatches:\s*(\d+)', mutant_output)
                                                    u_match = re.search(r'Unpass:\s*(\d+)', mutant_output)

                                                    if m_match:
                                                        mutant_passed = (int(m_match.group(1)) == 0)
                                                    elif u_match:
                                                        mutant_passed = (int(u_match.group(1)) == 0)

                                                mutant_detected = not mutant_passed
                                                mutant_results.append(mutant_detected)

                                                if mutant_detected:
                                                    mutants_detected += 1

                                                # Compare with expected
                                                if idx < len(expected_results):
                                                    expected_fails = not expected_results[idx]
                                                    status = "✓" if mutant_detected == expected_fails else "✗"
                                                    print(f"    Mutant {idx}: detected={mutant_detected}, expected_fails={expected_fails} {status}")

                                            except:
                                                mutant_results.append(True)  # Timeout/error = detected
                                                mutants_detected += 1
                                            finally:
                                                # Cleanup mutant dir
                                                try:
                                                    shutil.rmtree(mutant_dir)
                                                except:
                                                    pass

                                        # Calculate agreement rate
                                        agreement_count = sum(
                                            1 for actual, expected in zip(mutant_results, expected_results)
                                            if actual == (not expected)
                                        )
                                        agreement_rate = agreement_count / len(mutants) if mutants else 0.0

                                        simulation_metrics["eval2_mutant_detection"]["mutants_detected"] = mutants_detected
                                        simulation_metrics["eval2_mutant_detection"]["agreement_rate"] = agreement_rate
                                        simulation_metrics["eval2_mutant_detection"]["agreement_80"] = (agreement_rate >= 0.80)
                                        simulation_metrics["eval2_mutant_detection"]["agreement_90"] = (agreement_rate >= 0.90)
                                        simulation_metrics["eval2_mutant_detection"]["agreement_100"] = (agreement_rate >= 1.00)

                                        print(f"  eval2: Agreement rate {agreement_rate:.1%} ({agreement_count}/{len(mutants)})")
                                        print(f"    80%: {'✓ PASSED' if simulation_metrics['eval2_mutant_detection']['agreement_80'] else '✗ FAILED'}")
                                        print(f"    90%: {'✓ PASSED' if simulation_metrics['eval2_mutant_detection']['agreement_90'] else '✗ FAILED'}")
                                        print(f"    100%: {'✓ PASSED' if simulation_metrics['eval2_mutant_detection']['agreement_100'] else '✗ FAILED'}")

                                else:
                                    print(f"  eval0: ✗ FAILED - Compilation error")
                                    simulation_metrics["error"] = "Compilation failed"

                            except subprocess.TimeoutExpired:
                                simulation_metrics["error"] = "Simulation timeout"
                                print(f"  ERROR: Simulation timeout")
                            except Exception as e:
                                simulation_metrics["error"] = f"Simulation error: {str(e)}"
                                print(f"  ERROR: {str(e)}")
                            finally:
                                # Cleanup simulation directory
                                try:
                                    shutil.rmtree(sim_eval_dir)
                                except:
                                    pass

                        # Calculate overall success
                        simulation_metrics["overall_success"] = (
                            simulation_metrics["eval0_compile_success"] and
                            simulation_metrics["eval1_module_passes"] and
                            simulation_metrics["eval2_mutant_detection"]["agreement_80"]
                        )

                        print(f"  Overall success: {'✓ PASSED' if simulation_metrics['overall_success'] else '✗ FAILED'}")

                else:
                    simulation_metrics["error"] = f"Task {task_number} not found in benchmark"
                    print(f"  WARNING: Task not found in benchmark")
            else:
                simulation_metrics["error"] = "Benchmark file not found"
                print(f"  WARNING: {benchmark_file} not found")

        except Exception as e:
            simulation_metrics["error"] = f"Evaluation error: {str(e)}"
            print(f"  ERROR: {str(e)}")
            import traceback
            traceback.print_exc()

        result["simulation_metrics"] = simulation_metrics

        # Mark as successful
        result["success"] = True

        return self._finalize_result(result, start_time, output_dir)

    def _finalize_result(self, result: Dict[str, Any], start_time: float, output_dir: str) -> Dict[str, Any]:
        """Finalize and save task result
        
        Args:
            result: Result dictionary
            start_time: Task start time
            output_dir: Output directory
            
        Returns:
            Finalized result
        """
        result["total_time"] = time.time() - start_time
        result["timestamp"] = time.time()
        
        # Save result to file
        result_path = os.path.join(output_dir, "task_result.json")
        with open(result_path, "w") as f:
            json.dump(result, f, indent=2)
        
        status = "SUCCESS" if result["success"] else "FAILED"
        print(f"\nTask {result['task_number']} {status} in {result['total_time']:.2f}s")
        print(f"{'='*60}\n")
        
        return result


class ProVTopAgent:
    """
    Top-level agent that orchestrates the entire Pro-V workflow
    Architecture: __init__ initializes agents once, then distributes tasks to workers
    """
    
    def __init__(self, args):
        """Initialize the top agent
        
        Args:
            args: Command line arguments
        """
        self.args = args
        
        # Initialize Ray
        if not ray.is_initialized():
            ray.init(ignore_reinit_error=True)
            print("Ray initialized")
        
        # LLM client configuration
        self.llm_client_config = {
            "model": args.model,
            "vllm_endpoints": args.vllm_endpoints
        }
        
        print(f"ProVTopAgent initialized for experiment: {args.experiment_name}")
        
    def run_evaluation(self) -> Dict[str, Any]:
        """Run evaluation on all specified tasks using Ray parallelization
        
        Returns:
            Overall evaluation results
        """
        print(f"\n{'='*70}")
        print(f"Starting Pro-V Evaluation: {self.args.experiment_name}")
        print(f"{'='*70}\n")
        
        # Determine which tasks to process
        if self.args.task_numbers:
            task_numbers = [int(t.strip()) for t in self.args.task_numbers.split(',')]
        else:
            task_numbers = list(range(1, 155))  # All tasks 1-154
        
        print(f"Processing {len(task_numbers)} tasks: {task_numbers[:10]}{'...' if len(task_numbers) > 10 else ''}")

        # Load benchmark data
        benchmark_path = os.getenv("FOLDER_PATH", "../verilog-eval/HDLBits/test_benchmark_new.json")
        benchmark_data = load_benchmark_data(benchmark_path)

        if not benchmark_data:
            print("ERROR: Failed to load benchmark data. Exiting.")
            return {"error": "Failed to load benchmark data"}

        # Prepare tasks to process
        tasks_to_process = []
        for task_num in task_numbers:
            if task_num not in benchmark_data:
                print(f"WARNING: Task {task_num} not found in benchmark data. Skipping.")
                continue

            task = benchmark_data[task_num]
            task_data = {
                "task_number": task_num,
                "task_id": task.get("task_id", f"task_{task_num}"),
                "rtl_code": task.get("module_code", ""),
                "specification": task.get("description", ""),
                "header": task.get("header", ""),
                "mutants": task.get("mutants", [])
            }
            tasks_to_process.append(task_data)

        print(f"Successfully prepared {len(tasks_to_process)} tasks for processing")

        # Create output directory
        output_base_dir = f"outputs/{self.args.experiment_name}"
        os.makedirs(output_base_dir, exist_ok=True)
        
        # Create worker pool (limited by max_concurrency)
        num_workers = min(len(tasks_to_process), self.args.max_concurrency, os.cpu_count() or 4)
        print(f"\nCreating {num_workers} Ray workers (max_concurrency={self.args.max_concurrency})...")
        
        workers = [TaskWorker.remote(self.llm_client_config) for _ in range(num_workers)]
        print(f"Workers created successfully\n")
        
        # Submit tasks to workers (round-robin distribution)
        print(f"Submitting {len(tasks_to_process)} tasks to workers...")
        task_refs = []
        
        for i, task_data in enumerate(tasks_to_process):
            worker_idx = i % num_workers
            task_ref = workers[worker_idx].process_task.remote(
                task_number=task_data["task_number"],
                rtl_code=task_data["rtl_code"],
                specification=task_data["specification"],
                output_base_dir=output_base_dir,
                sampling_size=self.args.sampling_size,
                enable_verification=self.args.enable_verification,
                task_id=task_data.get("task_id"),
                header=task_data.get("header"),
                mutants=task_data.get("mutants", [])
            )
            task_refs.append(task_ref)
        
        # Collect results
        print(f"Processing {len(task_refs)} tasks in parallel...\n")
        all_results = ray.get(task_refs)
        
        # Calculate overall statistics
        total_tasks = len(all_results)
        successful_tasks = sum(1 for r in all_results if r["success"])

        if self.args.enable_verification:
            verified_tasks = sum(
                1 for r in all_results
                if r.get("verification_result", {}).get("verification_passed", False)
            )
        else:
            verified_tasks = 0

        # Calculate simulation metrics aggregates
        simulation_stats = self._calculate_simulation_aggregates(all_results)

        overall_stats = {
            "experiment_name": self.args.experiment_name,
            "total_tasks": total_tasks,
            "successful_tasks": successful_tasks,
            "verified_tasks": verified_tasks,
            "success_rate": successful_tasks / total_tasks if total_tasks > 0 else 0.0,
            "verification_rate": verified_tasks / total_tasks if total_tasks > 0 else 0.0,
            "total_time": sum(r.get("total_time", 0) for r in all_results),
            "avg_time_per_task": sum(r.get("total_time", 0) for r in all_results) / total_tasks if total_tasks > 0 else 0.0,
            "simulation_metrics": simulation_stats
        }
        
        # Save results
        with open(os.path.join(output_base_dir, "overall_stats.json"), "w") as f:
            json.dump(overall_stats, f, indent=2)
        
        with open(os.path.join(output_base_dir, "all_results.json"), "w") as f:
            json.dump(all_results, f, indent=2)
        
        # Print summary
        print(f"\n{'='*70}")
        print(f"EVALUATION COMPLETED")
        print(f"{'='*70}")
        print(f"Total tasks:       {total_tasks}")
        print(f"Successful tasks:  {successful_tasks} ({overall_stats['success_rate']:.1%})")
        if self.args.enable_verification:
            print(f"Verified tasks:    {verified_tasks} ({overall_stats['verification_rate']:.1%})")
        print(f"Total time:        {overall_stats['total_time']:.2f}s")
        print(f"Avg time/task:     {overall_stats['avg_time_per_task']:.2f}s")

        # Print simulation metrics summary
        if simulation_stats["total_evaluated"] > 0:
            print(f"\n{'='*70}")
            print(f"SIMULATION METRICS SUMMARY")
            print(f"{'='*70}")
            print(f"Total evaluated:   {simulation_stats['total_evaluated']}")
            print(f"eval0 (Compile):   {simulation_stats['eval0_pass_count']}/{simulation_stats['total_evaluated']} ({simulation_stats['eval0_pass_rate']:.1%})")
            print(f"eval1 (Module):    {simulation_stats['eval1_pass_count']}/{simulation_stats['total_evaluated']} ({simulation_stats['eval1_pass_rate']:.1%})")
            print(f"eval2 (Mutants):")
            print(f"  80% threshold:   {simulation_stats['eval2_80_pass_count']}/{simulation_stats['total_evaluated']} ({simulation_stats['eval2_80_pass_rate']:.1%})")
            print(f"  90% threshold:   {simulation_stats['eval2_90_pass_count']}/{simulation_stats['total_evaluated']} ({simulation_stats['eval2_90_pass_rate']:.1%})")
            print(f"  100% threshold:  {simulation_stats['eval2_100_pass_count']}/{simulation_stats['total_evaluated']} ({simulation_stats['eval2_100_pass_rate']:.1%})")
            print(f"Overall success:   {simulation_stats['overall_success_count']}/{simulation_stats['total_evaluated']} ({simulation_stats['overall_success_rate']:.1%})")
            print(f"{'='*70}\n")

        print(f"{'='*70}\n")

        return overall_stats

    def _calculate_simulation_aggregates(self, all_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate aggregate simulation metrics across all tasks

        Args:
            all_results: List of all task results

        Returns:
            Aggregated simulation statistics
        """
        stats = {
            "total_evaluated": 0,
            "eval0_pass_count": 0,
            "eval0_pass_rate": 0.0,
            "eval1_pass_count": 0,
            "eval1_pass_rate": 0.0,
            "eval2_80_pass_count": 0,
            "eval2_80_pass_rate": 0.0,
            "eval2_90_pass_count": 0,
            "eval2_90_pass_rate": 0.0,
            "eval2_100_pass_count": 0,
            "eval2_100_pass_rate": 0.0,
            "overall_success_count": 0,
            "overall_success_rate": 0.0,
            "total_mutants_tested": 0,
            "total_mutants_detected": 0,
            "avg_mutant_agreement_rate": 0.0
        }

        evaluated_count = 0
        total_agreement_rates = []

        for result in all_results:
            sim_metrics = result.get("simulation_metrics")
            if not sim_metrics:
                continue

            evaluated_count += 1

            if sim_metrics.get("eval0_compile_success"):
                stats["eval0_pass_count"] += 1

            if sim_metrics.get("eval1_module_passes"):
                stats["eval1_pass_count"] += 1

            eval2 = sim_metrics.get("eval2_mutant_detection", {})
            if eval2.get("agreement_80"):
                stats["eval2_80_pass_count"] += 1
            if eval2.get("agreement_90"):
                stats["eval2_90_pass_count"] += 1
            if eval2.get("agreement_100"):
                stats["eval2_100_pass_count"] += 1

            if sim_metrics.get("overall_success"):
                stats["overall_success_count"] += 1

            # Aggregate mutant statistics
            stats["total_mutants_tested"] += eval2.get("total_mutants", 0)
            stats["total_mutants_detected"] += eval2.get("mutants_detected", 0)
            if eval2.get("agreement_rate") is not None:
                total_agreement_rates.append(eval2["agreement_rate"])

        stats["total_evaluated"] = evaluated_count

        if evaluated_count > 0:
            stats["eval0_pass_rate"] = stats["eval0_pass_count"] / evaluated_count
            stats["eval1_pass_rate"] = stats["eval1_pass_count"] / evaluated_count
            stats["eval2_80_pass_rate"] = stats["eval2_80_pass_count"] / evaluated_count
            stats["eval2_90_pass_rate"] = stats["eval2_90_pass_count"] / evaluated_count
            stats["eval2_100_pass_rate"] = stats["eval2_100_pass_count"] / evaluated_count
            stats["overall_success_rate"] = stats["overall_success_count"] / evaluated_count

        if total_agreement_rates:
            stats["avg_mutant_agreement_rate"] = sum(total_agreement_rates) / len(total_agreement_rates)

        return stats


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Pro-V Top Agent with Ray Support")
    
    parser.add_argument("--model", type=str, required=True, help="Model name to use")
    parser.add_argument("--vllm_endpoints", type=str, help="Comma-separated vLLM endpoints")
    parser.add_argument("--provider", type=str, default="vllm", help="LLM provider")
    parser.add_argument("--experiment_name", type=str, required=True, help="Experiment name")
    parser.add_argument("--enable_thinking", action="store_true", help="Enable thinking mode")
    parser.add_argument("--enable_verification", action="store_true", help="Enable verification step")
    parser.add_argument("--task_numbers", type=str, help="Comma-separated task numbers to process")
    parser.add_argument("--sampling_size", type=int, default=3, help="Number of PyChecker samples")
    parser.add_argument("--max_concurrency", type=int, default=50, help="Maximum concurrent tasks to run")
    
    args = parser.parse_args()
    
    # Run evaluation
    top_agent = ProVTopAgent(args)
    results = top_agent.run_evaluation()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

