"""
Evaluation Logger Utilities

This module provides utilities for evaluation result tracking and analysis.
"""

import json
import csv
from datetime import datetime
from typing import Dict, Any, Optional, List, Union
from pathlib import Path


class EvalLogger:
    """Logger for evaluation results and metrics"""
    
    def __init__(self, output_dir: Optional[Union[str, Path]] = None):
        """Initialize the evaluation logger
        
        Args:
            output_dir: Directory to save evaluation results
        """
        self.output_dir = Path(output_dir) if output_dir else Path("evaluation_results")
        self.output_dir.mkdir(exist_ok=True)
        
        self.results = []
        self.summary = {}
        
    def log_task_result(self, task_id: int, result: Dict[str, Any]) -> None:
        """Log result for a single task
        
        Args:
            task_id: Task identifier
            result: Task result dictionary
        """
        task_result = {
            "task_id": task_id,
            "timestamp": datetime.now().isoformat(),
            **result
        }
        
        self.results.append(task_result)
        
    def log_batch_results(self, results: List[Dict[str, Any]]) -> None:
        """Log results for multiple tasks
        
        Args:
            results: List of task results
        """
        for i, result in enumerate(results):
            task_id = result.get("task_id", i + 1)
            self.log_task_result(task_id, result)
            
    def calculate_summary(self) -> Dict[str, Any]:
        """Calculate summary statistics from logged results
        
        Returns:
            Summary statistics dictionary
        """
        if not self.results:
            return {
                "total_tasks": 0,
                "overall_metrics": {},
                "timestamp": datetime.now().isoformat()
            }
            
        total_tasks = len(self.results)
        
        # Calculate overall metrics
        metrics = {}
        
        # Common metrics to track
        metric_keys = [
            "simulation_success",
            "golden_accuracy", 
            "mutant_detection_100",
            "mutant_detection_90",
            "mutant_detection_80"
        ]
        
        for key in metric_keys:
            values = [r.get(key, 0) for r in self.results if key in r]
            if values:
                metrics[key] = sum(values) / len(values)
            else:
                metrics[key] = 0.0
                
        # Calculate latency statistics if available
        latencies = [r.get("latency", 0) for r in self.results if "latency" in r]
        latency_stats = {}
        
        if latencies:
            latency_stats = {
                "total_tasks": len(latencies),
                "average_latency": sum(latencies) / len(latencies),
                "min_latency": min(latencies),
                "max_latency": max(latencies),
                "total_time": sum(latencies)
            }
            
        # Separate by task type if available
        cmb_results = [r for r in self.results if r.get("task_type") == "cmb"]
        seq_results = [r for r in self.results if r.get("task_type") == "seq"]
        
        cmb_metrics = self._calculate_type_metrics(cmb_results)
        seq_metrics = self._calculate_type_metrics(seq_results)
        
        self.summary = {
            "total_tasks": total_tasks,
            "overall_metrics": metrics,
            "latency_statistics": latency_stats,
            "cmb_metrics": cmb_metrics,
            "seq_metrics": seq_metrics,
            "timestamp": datetime.now().isoformat()
        }
        
        return self.summary
        
    def _calculate_type_metrics(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate metrics for a specific task type
        
        Args:
            results: Results for specific task type
            
        Returns:
            Metrics dictionary for the task type
        """
        if not results:
            return {
                "total_tasks": 0,
                "simulation_success": 0.0,
                "golden_accuracy": 0.0,
                "mutant_detection_100": 0.0,
                "mutant_detection_90": 0.0,
                "mutant_detection_80": 0.0
            }
            
        total_tasks = len(results)
        
        metrics = {
            "total_tasks": total_tasks
        }
        
        metric_keys = [
            "simulation_success",
            "golden_accuracy",
            "mutant_detection_100", 
            "mutant_detection_90",
            "mutant_detection_80"
        ]
        
        for key in metric_keys:
            values = [r.get(key, 0) for r in results if key in r]
            if values:
                metrics[key] = sum(values) / len(values)
            else:
                metrics[key] = 0.0
                
        return metrics
        
    def save_results(self, filename: Optional[str] = None) -> None:
        """Save evaluation results to file
        
        Args:
            filename: Optional filename (defaults to timestamp-based name)
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"evaluation_results_{timestamp}.json"
            
        filepath = self.output_dir / filename
        
        data = {
            "summary": self.calculate_summary(),
            "per_task_results": self.results
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
    def save_summary(self, filename: Optional[str] = None) -> None:
        """Save evaluation summary to file
        
        Args:
            filename: Optional filename (defaults to evaluation_summary.json)
        """
        if not filename:
            filename = "evaluation_summary.json"
            
        filepath = self.output_dir / filename
        summary = self.calculate_summary()
        summary["per_task_results"] = self.results
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
            
    def save_csv_summary(self, filename: Optional[str] = None) -> None:
        """Save evaluation summary as CSV
        
        Args:
            filename: Optional filename (defaults to evaluation_summary.csv)
        """
        if not filename:
            filename = "evaluation_summary.csv"
            
        filepath = self.output_dir / filename
        
        if not self.results:
            return
            
        # Get all unique keys from results
        all_keys = set()
        for result in self.results:
            all_keys.update(result.keys())
            
        all_keys = sorted(list(all_keys))
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=all_keys)
            writer.writeheader()
            writer.writerows(self.results)
            
    def load_results(self, filepath: Union[str, Path]) -> None:
        """Load evaluation results from file
        
        Args:
            filepath: Path to results file
        """
        filepath = Path(filepath)
        
        if not filepath.exists():
            raise FileNotFoundError(f"Results file not found: {filepath}")
            
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        if "per_task_results" in data:
            self.results = data["per_task_results"]
        elif isinstance(data, list):
            self.results = data
        else:
            self.results = [data]
            
        if "summary" in data:
            self.summary = data["summary"]


def create_eval_logger(output_dir: Optional[Union[str, Path]] = None) -> EvalLogger:
    """Convenience function to create evaluation logger
    
    Args:
        output_dir: Directory to save evaluation results
        
    Returns:
        EvalLogger instance
    """
    return EvalLogger(output_dir)


def log_evaluation_result(task_id: int, result: Dict[str, Any], output_dir: Optional[Union[str, Path]] = None) -> None:
    """Convenience function to log a single evaluation result
    
    Args:
        task_id: Task identifier
        result: Task result dictionary
        output_dir: Directory to save results
    """
    logger = EvalLogger(output_dir)
    logger.log_task_result(task_id, result)
    logger.save_results()

