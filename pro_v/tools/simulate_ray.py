"""
Ray-based Simulation Tools

This module provides distributed simulation capabilities using Ray.
"""

import os
import subprocess
import time
from typing import Dict, Any, Optional, List, Union, Tuple
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed


class RaySimulator:
    """Ray-based simulator for parallel RTL simulation"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the Ray simulator
        
        Args:
            config: Configuration dictionary for the simulator
        """
        self.config = config or {}
        self.num_workers = self.config.get("num_workers", 4)
        self.timeout = self.config.get("timeout", 600)
        self.work_dir = Path(self.config.get("work_dir", "simulation_work"))
        self.work_dir.mkdir(exist_ok=True)
        
    def simulate_single_task(self, task_id: int, rtl_code: str, testbench: str) -> Dict[str, Any]:
        """Simulate a single task
        
        Args:
            task_id: Task identifier
            rtl_code: RTL code to simulate
            testbench: Testbench code
            
        Returns:
            Simulation result dictionary
        """
        start_time = time.time()
        
        # Create task-specific directory
        task_dir = self.work_dir / f"task_{task_id}"
        task_dir.mkdir(exist_ok=True)
        
        # Write RTL and testbench files
        rtl_file = task_dir / "design.v"
        tb_file = task_dir / "testbench.v"
        
        with open(rtl_file, 'w') as f:
            f.write(rtl_code)
            
        with open(tb_file, 'w') as f:
            f.write(testbench)
            
        # Run simulation
        result = self._run_iverilog_simulation(task_dir, rtl_file, tb_file)
        
        # Calculate latency
        latency = time.time() - start_time
        result["latency"] = latency
        result["task_id"] = task_id
        
        return result
        
    def _run_iverilog_simulation(self, work_dir: Path, rtl_file: Path, tb_file: Path) -> Dict[str, Any]:
        """Run Icarus Verilog simulation
        
        Args:
            work_dir: Working directory for simulation
            rtl_file: RTL file path
            tb_file: Testbench file path
            
        Returns:
            Simulation result dictionary
        """
        result = {
            "simulation_success": False,
            "compile_success": False,
            "run_success": False,
            "output": "",
            "error": "",
            "exit_code": -1
        }
        
        try:
            # Compile with iverilog
            compile_cmd = [
                "iverilog",
                "-o", str(work_dir / "simulation"),
                str(rtl_file),
                str(tb_file)
            ]
            
            compile_process = subprocess.run(
                compile_cmd,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            result["compile_success"] = compile_process.returncode == 0
            
            if not result["compile_success"]:
                result["error"] = compile_process.stderr
                result["exit_code"] = compile_process.returncode
                return result
                
            # Run simulation
            run_cmd = ["vvp", str(work_dir / "simulation")]
            
            run_process = subprocess.run(
                run_cmd,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            result["run_success"] = run_process.returncode == 0
            result["output"] = run_process.stdout
            result["error"] = run_process.stderr
            result["exit_code"] = run_process.returncode
            
            result["simulation_success"] = result["compile_success"] and result["run_success"]
            
        except subprocess.TimeoutExpired:
            result["error"] = f"Simulation timeout after {self.timeout} seconds"
            result["exit_code"] = -2
        except Exception as e:
            result["error"] = f"Simulation error: {str(e)}"
            result["exit_code"] = -3
            
        return result
        
    def simulate_batch(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Simulate multiple tasks in parallel
        
        Args:
            tasks: List of task dictionaries with 'task_id', 'rtl_code', 'testbench'
            
        Returns:
            List of simulation results
        """
        results = []
        
        with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
            # Submit all tasks
            future_to_task = {}
            for task in tasks:
                future = executor.submit(
                    self.simulate_single_task,
                    task["task_id"],
                    task["rtl_code"],
                    task["testbench"]
                )
                future_to_task[future] = task
                
            # Collect results
            for future in as_completed(future_to_task):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    task = future_to_task[future]
                    error_result = {
                        "task_id": task["task_id"],
                        "simulation_success": False,
                        "error": f"Task execution error: {str(e)}",
                        "latency": 0
                    }
                    results.append(error_result)
                    
        # Sort results by task_id
        results.sort(key=lambda x: x["task_id"])
        return results
        
    def cleanup_work_dir(self) -> None:
        """Clean up simulation working directory"""
        import shutil
        if self.work_dir.exists():
            shutil.rmtree(self.work_dir)
            
    def get_simulation_stats(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate simulation statistics
        
        Args:
            results: List of simulation results
            
        Returns:
            Statistics dictionary
        """
        if not results:
            return {
                "total_tasks": 0,
                "success_rate": 0.0,
                "average_latency": 0.0,
                "total_time": 0.0
            }
            
        total_tasks = len(results)
        successful_tasks = sum(1 for r in results if r.get("simulation_success", False))
        success_rate = successful_tasks / total_tasks
        
        latencies = [r.get("latency", 0) for r in results]
        average_latency = sum(latencies) / len(latencies) if latencies else 0.0
        total_time = sum(latencies)
        
        return {
            "total_tasks": total_tasks,
            "successful_tasks": successful_tasks,
            "success_rate": success_rate,
            "average_latency": average_latency,
            "total_time": total_time,
            "min_latency": min(latencies) if latencies else 0.0,
            "max_latency": max(latencies) if latencies else 0.0
        }


def simulate_task(task_id: int, rtl_code: str, testbench: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Convenience function for single task simulation
    
    Args:
        task_id: Task identifier
        rtl_code: RTL code to simulate
        testbench: Testbench code
        config: Optional configuration
        
    Returns:
        Simulation result dictionary
    """
    simulator = RaySimulator(config)
    return simulator.simulate_single_task(task_id, rtl_code, testbench)


def simulate_batch(tasks: List[Dict[str, Any]], config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Convenience function for batch simulation
    
    Args:
        tasks: List of task dictionaries
        config: Optional configuration
        
    Returns:
        List of simulation results
    """
    simulator = RaySimulator(config)
    return simulator.simulate_batch(tasks)

