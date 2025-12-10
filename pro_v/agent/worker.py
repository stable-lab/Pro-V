"""
Worker utilities for PyChecker RL simulation execution.

This module contains Ray worker implementations for parallel Verilog simulation
with proper timeout handling and resource management.
"""

import asyncio
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from typing import Any, Dict, List, Tuple
from pro_v.agent.utils import check_compile_success, check_simulation_pass

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Configure logging to console with basic configuration
console = logging.StreamHandler()
console.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console.setFormatter(formatter)
logger.addHandler(console)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SIM_SEQ_TEMPLATE_DIR = os.path.join(BASE_DIR, "sim_seq")
SIM_CMB_TEMPLATE_DIR = os.path.join(BASE_DIR, "sim_cmb")

try:
    import ray
    RAY_AVAILABLE = True
except ImportError:
    RAY_AVAILABLE = False
    ray = None


_RAY_TASK_HANDLE = None
_RAY_PYCHECKER_ACTOR_POOL: List[Any] | None = None


async def _await_ray_object_ref(obj_ref, timeout_seconds: float = 120.0):
    """
    Await a Ray object reference with timeout.
    
    Args:
        obj_ref: Ray object reference to await
        timeout_seconds: Maximum time to wait
        
    Returns:
        Result from Ray task
        
    Raises:
        asyncio.TimeoutError: If task exceeds timeout
    """
    if not RAY_AVAILABLE:
        raise RuntimeError("Ray is not available")
        
    import ray
    import time
    
    start_time = time.time()
    while True:
        ready, _ = ray.wait([obj_ref], timeout=0.1)
        if ready:
            return ray.get(obj_ref)
        
        elapsed = time.time() - start_time
        if elapsed > timeout_seconds:
            raise asyncio.TimeoutError(f"Ray task timed out after {timeout_seconds}s")
        
        await asyncio.sleep(0.01)


def _ensure_ray_initialized() -> None:
    """
    Ensure Ray is initialized with proper configuration.

    First tries to connect to an existing Ray cluster (started by shell script),
    and falls back to initializing a new cluster if needed.
    """
    if not RAY_AVAILABLE:
        raise RuntimeError("Ray is not available")

    import ray

    if ray.is_initialized():
        logger.info("Ray already initialized")
        return

    # Try to connect to existing Ray cluster first
    try:
        logger.info("Attempting to connect to existing Ray cluster...")
        ray.init(
            address='auto',
            ignore_reinit_error=True
        )
        logger.info("✅ Connected to existing Ray cluster successfully")

        # Log Ray cluster resources
        resources = ray.available_resources()
        logger.info(f"Ray cluster resources: CPU={resources.get('CPU', 0)}, "
                   f"memory={resources.get('memory', 0) / 1e9:.2f}GB")
        return
    except Exception as e:
        logger.warning(f"Could not connect to existing Ray cluster: {e}")
        logger.info("Will try to initialize a new Ray cluster...")

    # Fallback: Initialize new Ray cluster
    # Clean up old Ray sessions to prevent GCS overload
    ray_tmp_dir = "/tmp/verl_ray"
    ray_spill_dir = "/tmp/verl_spill"

    logger.info("Cleaning up old Ray sessions...")
    try:
        # Remove old session directories
        if os.path.exists(ray_tmp_dir):
            for item in os.listdir(ray_tmp_dir):
                if item.startswith("session_"):
                    session_path = os.path.join(ray_tmp_dir, item)
                    shutil.rmtree(session_path, ignore_errors=True)

        # Clean spill directory
        if os.path.exists(ray_spill_dir):
            shutil.rmtree(ray_spill_dir, ignore_errors=True)

        logger.info("Old Ray sessions cleaned up")
    except Exception as e:
        logger.warning(f"Failed to clean up old sessions: {e}")

    os.makedirs(ray_tmp_dir, exist_ok=True)
    os.makedirs(ray_spill_dir, exist_ok=True)

    init_kwargs = {
        "ignore_reinit_error": True,
        "include_dashboard": False,
        "logging_level": "ERROR",
    }

    # Configure num_cpus - default to physical cores if not specified
    num_cpus_env = os.getenv("RAY_NUM_CPUS")
    if num_cpus_env:
        try:
            num_cpus = float(num_cpus_env)
            if num_cpus > 0:
                init_kwargs["num_cpus"] = num_cpus
                logger.info(f"Setting Ray num_cpus to {num_cpus}")
            else:
                logger.warning(f"RAY_NUM_CPUS must be positive, got {num_cpus_env}")
        except (ValueError, TypeError):
            logger.warning(f"Invalid RAY_NUM_CPUS value: {num_cpus_env}, using default")

    try:
        logger.info("Initializing new Ray cluster in distributed mode...")
        ray.init(**init_kwargs)
        logger.info("✅ Ray initialized successfully in distributed mode")

        # Log Ray cluster resources
        resources = ray.available_resources()
        logger.info(f"Ray cluster resources: CPU={resources.get('CPU', 0)}, "
                   f"memory={resources.get('memory', 0) / 1e9:.2f}GB")
    except Exception as init_error:
        logger.error("❌ Ray initialization failed: %s", init_error)
        logger.error("Please check your Ray configuration and resources")
        raise RuntimeError(
            f"Ray initialization failed. This is required for parallel worker execution. "
            f"Error: {init_error}"
        ) from init_error

def get_ray_pychecker_worker_cls(num_workers=None):
    """
    Get or create the Ray PyChecker worker class.

    Returns a Ray remote actor class that can execute PyChecker simulations
    with timeout handling. Uses caching to avoid recreating the class.

    Args:
        num_workers: Expected number of workers to create (used for auto CPU calculation)

    Returns:
        Ray remote actor class for PyChecker simulation execution
    """
    if not RAY_AVAILABLE:
        return None

    _ensure_ray_initialized()

    if hasattr(get_ray_pychecker_worker_cls, "_cls"):
        return getattr(get_ray_pychecker_worker_cls, "_cls")

    # Configure for CPU-intensive Verilog compilation tasks
    # Key insight: Different tasks use different workers (assigned randomly in execution engine)
    # So we need many workers running in parallel, each handling one compilation task
    #
    # Auto-calculate num_cpus_per_worker based on available CPUs and desired workers
    # Formula: num_cpus_per_worker = total_cpus / num_workers
    # This ensures we can actually create all requested workers

    # Get total available CPUs from Ray
    import ray
    total_cpus = ray.available_resources().get("CPU", os.cpu_count())

    # Allow environment variable override, but use auto-calculation by default
    if "PYCHECKER_WORKER_CPUS" in os.environ:
        num_cpus_per_worker = float(os.getenv("PYCHECKER_WORKER_CPUS"))
        logger.info(f"Using PYCHECKER_WORKER_CPUS from environment: {num_cpus_per_worker}")
    elif num_workers is not None and num_workers > 0:
        # Auto-calculate: divide total CPUs by desired workers
        # Add small buffer (0.9) to avoid over-subscription
        num_cpus_per_worker = (total_cpus * 0.9) / num_workers
        # Clamp to reasonable range [0.1, 2.0]
        num_cpus_per_worker = max(0.1, min(2.0, num_cpus_per_worker))
        logger.info(f"Auto-calculated num_cpus_per_worker: {num_cpus_per_worker:.2f} (total_cpus={total_cpus}, num_workers={num_workers})")
    else:
        # Fallback to default
        num_cpus_per_worker = 0.4
        logger.warning(f"Using default num_cpus_per_worker: {num_cpus_per_worker} (num_workers not provided)")

    max_concurrent_tasks = int(os.getenv("PYCHECKER_WORKER_CONCURRENCY", "1"))

    logger.info(f"Creating PyChecker worker class with num_cpus={num_cpus_per_worker:.2f}, max_concurrency={max_concurrent_tasks}")
    
    @ray.remote(num_cpus=num_cpus_per_worker, max_concurrency=max_concurrent_tasks)
    class _RayPyCheckerWorker:
        def __init__(self, idx=None, worker_id=None, num_jobs=1, timeout=300):
            # Support both idx (legacy) and worker_id (new) parameters
            if worker_id is not None:
                self.idx = int(worker_id)
            elif idx is not None:
                if isinstance(idx, (int, float)):
                    self.idx = int(idx)
                elif isinstance(idx, str) and re.fullmatch(r"\s*-?\d+\s*", idx):
                    self.idx = int(idx)
                else:
                    self.idx = 0
            else:
                self.idx = 0

            self.num_jobs = num_jobs
            self.timeout = timeout

        def get_idx(self):
            """Get the actor's index"""
            return self.idx

        def run_python_file(
            self,
            python_file_path: str,
            working_directory: str,
            timeout: float = 60.0
        ) -> Tuple[bool, str]:
            try:
                # If no directory in path, use working_directory
                file_dir = os.path.dirname(python_file_path) or working_directory
                file_name = os.path.basename(python_file_path)

                # Execute: cd to file directory, then run python filename
                result = subprocess.run(
                    ["python", file_name],
                    cwd=file_dir,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )

                if result.returncode != 0:
                    return False, f"Python execution failed: {result.stderr}"
                
                return True, ""
            except subprocess.TimeoutExpired:
                return False, f"Python execution timeout after {timeout} seconds"
            except Exception as e:
                return False, f"Python execution error: {str(e)}"

        

        def simulate_dut_seq_ray(self, output_dir: str) -> Tuple[int, str, str, float]:
            """
            Ray remote function: Execute sequential circuit simulation in separate process
            
            Args:
                output_dir: Output directory path
                
            Returns:
                (returncode, stdout, stderr, reward) tuple
            """
            
            sim_template_dir = SIM_SEQ_TEMPLATE_DIR
            
            work_dir = os.path.join(output_dir, f"sim_seq")
            
            # Try to find the DUT file - could be module_code.v or top.v
            dut_path = os.path.join(output_dir, "module_code.v")
            if not os.path.exists(dut_path):
                dut_path = os.path.join(output_dir, "top.v")
            
            test_path = os.path.join(output_dir, "testbench.json")
            
            # Check if source files exist
            if not os.path.exists(dut_path):
                logger.error(f"DUT file does not exist: {dut_path}")
                return 1, "", f"DUT file not found: {dut_path}", 0.0
            if not os.path.exists(test_path):
                logger.error(f"Test file does not exist: {test_path}")
                return 1, "", f"Test file not found: {test_path}", 0.0
            
            os.makedirs(work_dir, exist_ok=True)

            # Copy simulation framework files
            framework_files = [
                "Makefile", "input.vc", 
                "sim-main.cpp", "rfuzz-harness.h",
                "harness-generator.py"
            ]
            for file_name in framework_files:
                src = os.path.join(sim_template_dir, file_name)
                dest = os.path.join(work_dir, file_name)
                if os.path.exists(src):
                    shutil.copy(src, dest)
                else:
                    logger.warning(f"Missing framework file: {src}")
            
            # Copy task-specific files
            shutil.copy(dut_path, os.path.join(work_dir, "top_module.v"))
            shutil.copy(test_path, os.path.join(work_dir, "testbench.json"))
            
            # Execute compilation and simulation
            make_jobs = os.getenv("PYCHECKER_MAKE_JOBS", "1")
            cmd = f"cd {work_dir} && python harness-generator.py && make -j{make_jobs}"
            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            except subprocess.TimeoutExpired:
                print(f"SEQ simulation timeout after 60s for {output_dir}")
                result = subprocess.CompletedProcess(
                    args=cmd, returncode=1, 
                    stdout="", stderr="Simulation timeout after 60 seconds"
                )
            
            # Save log
            log_file = os.path.join(output_dir, f"simulate_seq.log")
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            with open(log_file, "w") as f:
                f.write(f"Command: {cmd}\n")
                f.write(f"Work directory: {work_dir}\n")
                f.write(f"Return code: {result.returncode}\n")
                f.write("\n=== STDOUT ===\n")
                f.write(result.stdout)
                f.write("\n=== STDERR ===\n")
                f.write(result.stderr)
            
            # Calculate reward based on log content
            log_content = f"Command: {cmd}\nWork directory: {work_dir}\nReturn code: {result.returncode}\n=== STDOUT ===\n{result.stdout}\n=== STDERR ===\n{result.stderr}"
            reward = 0.0
            if check_compile_success(log_content):
                reward = 0.3
                if check_simulation_pass(log_content):
                    reward = 1.0
            
           
            return result.returncode, result.stdout, result.stderr, reward


        def simulate_dut_cmb_ray(self, output_dir: str) -> Tuple[int, str, str, float]:
            """
            Ray remote function: Execute combinational circuit simulation in separate process
            
            Args:
                output_dir: Output directory path
                
            Returns:
                (returncode, stdout, stderr, reward) tuple
            """
            #current_dir = os.path.dirname(os.path.abspath(__file__))
            sim_template_dir = SIM_CMB_TEMPLATE_DIR
            
            #task_id = os.path.basename(os.path.normpath(output_dir))
            work_dir = os.path.join(output_dir, f"sim_cmb")
            
            # Try to find the DUT file - could be module_code.v or top.v
            dut_path = os.path.join(output_dir, "module_code.v")
            if not os.path.exists(dut_path):
                dut_path = os.path.join(output_dir, "top.v")
            
            test_path = os.path.join(output_dir, "testbench.json")
            
            # Check if source files exist
            if not os.path.exists(dut_path):
                logger.error(f"DUT file does not exist: {dut_path}")
                return 1, "", f"DUT file not found: {dut_path}", 0.0
            if not os.path.exists(test_path):
                logger.error(f"Test file does not exist: {test_path}")
                return 1, "", f"Test file not found: {test_path}", 0.0
            
            os.makedirs(work_dir, exist_ok=True)
            
            # Copy simulation framework files
            framework_files = [
                "Makefile", "input.vc", 
                "sim-main.cpp", "rfuzz-harness.h",
                "harness-generator.py"
            ]
            for file_name in framework_files:
                src = os.path.join(sim_template_dir, file_name)
                dest = os.path.join(work_dir, file_name)
                if os.path.exists(src):
                    shutil.copy(src, dest)
                else:
                    logger.warning(f"Missing framework file: {src}")
            
            # Copy task-specific files
            shutil.copy(dut_path, os.path.join(work_dir, "top_module.v"))
            shutil.copy(test_path, os.path.join(work_dir, "testbench.json"))
            
            # Execute compilation and simulation
            make_jobs = os.getenv("PYCHECKER_MAKE_JOBS", "1")
            cmd = f"cd {work_dir} && python harness-generator.py && make -j{make_jobs}"
            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            except subprocess.TimeoutExpired:
                logger.error(f"CMB simulation timeout after 180s for {output_dir}")
                result = subprocess.CompletedProcess(
                    args=cmd, returncode=1, 
                    stdout="", stderr="Simulation timeout after 180 seconds"
                )

            # Save log
            log_file = os.path.join(output_dir, f"simulate_cmb.log")
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            with open(log_file, "w") as f:
                f.write(f"Command: {cmd}\n")
                f.write(f"Work directory: {work_dir}\n")
                f.write(f"Return code: {result.returncode}\n")
                f.write("\n=== STDOUT ===\n")
                f.write(result.stdout)
                f.write("\n=== STDERR ===\n")
                f.write(result.stderr)

            # Calculate reward based on log content
            log_content = f"Command: {cmd}\nWork directory: {work_dir}\nReturn code: {result.returncode}\n=== STDOUT ===\n{result.stdout}\n=== STDERR ===\n{result.stderr}"
            reward = 0.0
            if check_compile_success(log_content):
                reward = 0.3
                if check_simulation_pass(log_content):
                    reward = 1.0

       
            
            return result.returncode, result.stdout, result.stderr, reward

        def run_verilog_simulation(
            self,
            task_folder: str,
            circuit_type: str,
            timeout: float = 30.0
        ) -> Tuple[bool, str, Dict[str, Any]]:
            """
            Execute Verilog simulation and return result with reward.

            Args:
                task_folder: Task folder containing all artifacts
                circuit_type: "CMB" or "SEQ"
                timeout: Execution timeout

            Returns:
                (success, error_message, results_dict) tuple
            """
            try:
                # Normalize circuit type for robust comparison
                normalized_type = (circuit_type or "").strip().upper()

                # Call appropriate simulation function based on circuit type
                if normalized_type == "SEQ":
                    returncode, stdout, stderr, reward = self.simulate_dut_seq_ray(task_folder)
                elif normalized_type == "CMB":
                    returncode, stdout, stderr, reward = self.simulate_dut_cmb_ray(task_folder)
                else:
                    raise ValueError(f"Unsupported circuit type: {circuit_type}")

                # Prepare results dictionary
                results_dict = {
                    'returncode': returncode,
                    'stdout': stdout,
                    'stderr': stderr,
                    'reward': reward,
                    'compile_success': reward >= 0.3,
                    'all_tests_passed': reward >= 1.0
                }

                if returncode == 0:
                    return True, "", results_dict
                else:
                    error_msg = f"Simulation failed with return code {returncode}: {stderr}"
                    return False, error_msg, results_dict

            except Exception as e:
                error_msg = f"Verilog simulation error: {str(e)}"
                results_dict = {
                    'returncode': 1,
                    'stdout': "",
                    'stderr': str(e),
                    'reward': 0.0,
                    'compile_success': False,
                    'all_tests_passed': False
                }
                return False, error_msg, results_dict

        def run_stimulus_generation(
            self,
            stimulus_py_path: str,
            task_folder: str,
            timeout: float = 20.0
        ) -> Tuple[bool, str]:
            try:
                # Ensure task_folder exists before using it as cwd
                os.makedirs(task_folder, exist_ok=True)
                
                # Normalize task_folder to absolute path
                task_folder = os.path.abspath(task_folder)
                
                # Resolve stimulus_py_path
                basename = os.path.basename(stimulus_py_path)
                
                if os.path.isabs(stimulus_py_path):
                    # Already absolute, normalize it
                    stimulus_py_path_abs = os.path.abspath(stimulus_py_path)
                    # If absolute path doesn't exist, try to find file in task_folder
                    if not os.path.exists(stimulus_py_path_abs):
                        potential_path_in_task = os.path.join(task_folder, basename)
                        if os.path.exists(potential_path_in_task):
                            stimulus_py_path_abs = os.path.abspath(potential_path_in_task)
                else:
                    # Relative path - try to resolve it relative to task_folder
                    # First try just the basename in task_folder
                    potential_path_in_task = os.path.join(task_folder, basename)
                    if os.path.exists(potential_path_in_task):
                        stimulus_py_path_abs = os.path.abspath(potential_path_in_task)
                    else:
                        # Join with task_folder and normalize
                        stimulus_py_path_abs = os.path.abspath(os.path.join(task_folder, stimulus_py_path))
                
                # Check if file exists
                if not os.path.exists(stimulus_py_path_abs):
                    return False, f"Stimulus file not found: {stimulus_py_path_abs} (original path: {stimulus_py_path}, task_folder: {task_folder})"
                
                # If stimulus_py_path is in task_folder, use relative path
                # Otherwise use absolute path
                try:
                    rel_path = os.path.relpath(stimulus_py_path_abs, task_folder)
                    if not rel_path.startswith('..'):
                        script_path = rel_path
                    else:
                        script_path = stimulus_py_path_abs
                except ValueError:
                    # If paths are on different drives (Windows), use absolute path
                    script_path = stimulus_py_path_abs
                
                # Execute stimulus generation script
                result = subprocess.run(
                    ["python", script_path],
                    cwd=task_folder,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )

                if result.returncode != 0:
                    return False, f"Stimulus execution failed: {result.stderr}"

                return True, ""
            except subprocess.TimeoutExpired:
                return False, f"Stimulus execution timeout after {timeout} seconds"
            except Exception as e:
                return False, f"Stimulus execution error: {str(e)}"

    RayPyCheckerWorker = _RayPyCheckerWorker
    setattr(get_ray_pychecker_worker_cls, "_cls", RayPyCheckerWorker)
    return RayPyCheckerWorker


# Alias for compatibility with the registration system
def get_ray_docker_worker_cls(num_workers=None):
    """Alias for get_ray_pychecker_worker_cls to match the expected interface"""
    return get_ray_pychecker_worker_cls(num_workers=num_workers)



async def get_stimulus_generation_result(
    stimulus_py_path: str,
    task_folder: str,
    timeout: float = 60.0,
    ray_actor: Any | None = None,
) -> Tuple[bool, str]:
    """
    Execute stimulus generation and return the result.

    Uses Ray worker for execution with proper timeout handling for concurrent rollouts.

    Args:
        stimulus_py_path: Path to the stimulus generation Python file
        task_folder: Task folder for execution
        timeout: Execution timeout in seconds
        ray_actor: Ray actor for execution

    Returns:
        (success, error_message) tuple

    Raises:
        ValueError: If ray_actor is None
    """
    try:
        if ray_actor is None:
            raise ValueError("ray_actor is required")

        timeout_buffer = max(timeout * 1.5, 30.0)
        total_timeout = timeout + timeout_buffer

        obj_ref = ray_actor.run_stimulus_generation.remote(
            stimulus_py_path, task_folder, timeout
        )
        result = await _await_ray_object_ref(obj_ref, total_timeout)

        return result

    except asyncio.TimeoutError as e:
        error_msg = f"Stimulus generation timed out after {total_timeout}s"
        print(f"Error: {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = f"Stimulus generation failed: {e}"
        print(f"Error: {error_msg}")
        return False, error_msg


def cleanup_ray():
    """
    Shutdown Ray and clean up temporary directories.

    This function should be called when the program exits or encounters errors.
    """
    if not RAY_AVAILABLE:
        return

    try:
        import ray
        if ray.is_initialized():
            logger.info("Shutting down Ray...")
            ray.shutdown()
            logger.info("Ray shut down successfully")
    except Exception as e:
        logger.warning(f"Error during Ray shutdown: {e}")

    # Clean up temporary directories
    try:
        logger.info("Cleaning up Ray temporary directories...")
        ray_tmp_dir = "/tmp/verl_ray"
        ray_spill_dir = "/tmp/verl_spill"

        if os.path.exists(ray_tmp_dir):
            for item in os.listdir(ray_tmp_dir):
                if item.startswith("session_"):
                    session_path = os.path.join(ray_tmp_dir, item)
                    shutil.rmtree(session_path, ignore_errors=True)

        if os.path.exists(ray_spill_dir):
            for item in os.listdir(ray_spill_dir):
                item_path = os.path.join(ray_spill_dir, item)
                if os.path.isfile(item_path):
                    os.remove(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path, ignore_errors=True)

        logger.info("Ray cleanup completed")
    except Exception as e:
        logger.warning(f"Error during Ray cleanup: {e}")


# Export PyCheckerWorker as an alias to the Ray worker class
# This allows direct usage like: PyCheckerWorker.remote(worker_id=0, ...)
# Note: This will be initialized lazily when first accessed after Ray is initialized
_PyCheckerWorker = None

class _PyCheckerWorkerProxy:
    """
    Proxy class that lazily initializes the Ray worker class.
    This allows the module to be imported before Ray is initialized.
    """
    def __init__(self):
        self._cls = None

    def _ensure_initialized(self):
        """Ensure the Ray worker class is initialized"""
        if self._cls is None:
            if not RAY_AVAILABLE:
                raise RuntimeError("Ray is not available. Please install Ray to use PyCheckerWorker.")
            self._cls = get_ray_pychecker_worker_cls()
        return self._cls

    def remote(self, *args, **kwargs):
        """Create a remote instance of the worker"""
        cls = self._ensure_initialized()
        return cls.remote(*args, **kwargs)

    def __getattr__(self, name):
        """Forward all other attributes to the actual Ray worker class"""
        cls = self._ensure_initialized()
        return getattr(cls, name)

# Create a proxy instance that will be lazily initialized
PyCheckerWorker = _PyCheckerWorkerProxy()
