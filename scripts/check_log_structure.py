#!/usr/bin/env python3
"""
Script to display and verify the new log structure

New Log Structure:
==================
logs/
├── [run_name]/
│   ├── system/                    # System-wide logs
│   │   ├── agent/                 # Not used at system level
│   │   ├── system/                # Main process logs
│   │   │   ├── __main__.log
│   │   │   └── _all_system.log
│   │   └── ...
│   ├── tasks/                     # Per-task logs
│   │   ├── [task_id]/
│   │   │   ├── agent/            # Agent logs (TB generation, PyChecker, etc.)
│   │   │   │   ├── pro_v.agent.gen_tb.log
│   │   │   │   ├── pro_v.agent.pychecker.log
│   │   │   │   ├── pro_v.agent.refine_python_agent.log
│   │   │   │   └── _all_agent.log
│   │   │   ├── simulation/       # Simulation logs
│   │   │   │   ├── simulate_cmb.log  or  simulate_seq.log
│   │   │   │   └── ...
│   │   │   └── evaluation/       # Evaluation logs
│   │   │       ├── evaluation_results.json
│   │   │       └── ...
│   │   └── ...
│   └── evaluation_results/        # Aggregated evaluation results
│       ├── evaluation_summary.csv    # Quick overview in CSV format
│       ├── overall_summary.json      # Overall summary
│       └── task_[N].json             # Individual task evaluation details

Benefits:
=========
1. Clear separation of log types (agent, simulation, evaluation, system)
2. Evaluation results are centralized and easy to find
3. Per-task logs are organized in subdirectories by type
4. CSV summary for quick analysis in Excel/spreadsheet tools
5. Each log type has a unified log file (_all_*.log) for easier searching
"""

import os
import sys
import json
from pathlib import Path


def display_log_structure(log_base_dir: str):
    """Display the log directory structure"""
    log_path = Path(log_base_dir)
    
    if not log_path.exists():
        print(f"Log directory not found: {log_base_dir}")
        return
    
    print(f"\nLog Structure for: {log_base_dir}")
    print("=" * 80)
    
    # Check system logs
    system_dir = log_path / "system"
    if system_dir.exists():
        print("\nSystem Logs:")
        print("-" * 80)
        for item in sorted(system_dir.rglob("*")):
            if item.is_file():
                rel_path = item.relative_to(log_path)
                size = item.stat().st_size
                print(f"  {rel_path} ({size:,} bytes)")
    
    # Check evaluation results
    eval_dir = log_path / "evaluation_results"
    if eval_dir.exists():
        print("\nEvaluation Results:")
        print("-" * 80)
        for item in sorted(eval_dir.iterdir()):
            if item.is_file():
                size = item.stat().st_size
                print(f"  {item.name} ({size:,} bytes)")
        
        # Show CSV summary if exists
        csv_file = eval_dir / "evaluation_summary.csv"
        if csv_file.exists():
            print(f"\nEvaluation Summary (first 10 lines):")
            with open(csv_file, 'r') as f:
                for i, line in enumerate(f):
                    if i >= 10:
                        print("  ...")
                        break
                    print(f"  {line.rstrip()}")
    
    # Check task logs
    tasks_dir = log_path / "tasks"
    if tasks_dir.exists():
        task_dirs = sorted([d for d in tasks_dir.iterdir() if d.is_dir()])
        print(f"\nTask Logs: ({len(task_dirs)} tasks)")
        print("-" * 80)
        
        # Show structure for first 3 tasks as examples
        for task_dir in task_dirs[:3]:
            print(f"\n  Task {task_dir.name}:")
            
            # Agent logs
            agent_dir = task_dir / "agent"
            if agent_dir.exists():
                agent_files = list(agent_dir.glob("*.log"))
                print(f"    agent/ ({len(agent_files)} files)")
                for f in sorted(agent_files)[:5]:
                    print(f"      - {f.name}")
            
            # Simulation logs
            sim_dir = task_dir / "simulation"
            if sim_dir.exists():
                sim_files = list(sim_dir.glob("*.log"))
                print(f"    simulation/ ({len(sim_files)} files)")
                for f in sorted(sim_files):
                    print(f"      - {f.name}")
            
            # Evaluation logs
            eval_dir_task = task_dir / "evaluation"
            if eval_dir_task.exists():
                eval_files = list(eval_dir_task.glob("*"))
                print(f"    evaluation/ ({len(eval_files)} files)")
                for f in sorted(eval_files):
                    print(f"      - {f.name}")
        
        if len(task_dirs) > 3:
            print(f"\n  ... and {len(task_dirs) - 3} more tasks")
    
    print("\n" + "=" * 80)


def check_evaluation_summary(log_base_dir: str):
    """Check and display evaluation summary statistics"""
    log_path = Path(log_base_dir)
    eval_dir = log_path / "evaluation_results"
    
    if not eval_dir.exists():
        print("\nNo evaluation results found")
        return
    
    summary_file = eval_dir / "overall_summary.json"
    if not summary_file.exists():
        print("\nNo overall summary found")
        return
    
    with open(summary_file, 'r') as f:
        summary = json.load(f)
    
    print("\n" + "=" * 80)
    print("EVALUATION SUMMARY")
    print("=" * 80)
    print(f"Total tasks evaluated: {summary['total_tasks']}")
    print(f"Timestamp: {summary.get('timestamp', 'N/A')}")
    print("\nOverall Metrics:")
    print("-" * 80)
    
    metrics = summary.get('overall_metrics', {})
    print(f"  Metric 0 - Simulation success rate: {metrics.get('simulation_success', 0):.2%}")
    print(f"  Metric 1 - Golden code accuracy:    {metrics.get('golden_accuracy', 0):.2%}")
    print(f"  Metric 2 - 100% mutant detection:   {metrics.get('mutant_detection_100', 0):.2%}")
    print(f"  Metric 3 - 90%+ mutant detection:   {metrics.get('mutant_detection_90', 0):.2%}")
    print(f"  Metric 4 - 80%+ mutant detection:   {metrics.get('mutant_detection_80', 0):.2%}")
    print("=" * 80)


def main():
    if len(sys.argv) < 2:
        print("Usage: python check_log_structure.py <log_directory>")
        print("\nExample:")
        print("  python check_log_structure.py logs/tb_gen_tb_20250511_ray")
        sys.exit(1)
    
    log_base_dir = sys.argv[1]
    display_log_structure(log_base_dir)
    check_evaluation_summary(log_base_dir)


if __name__ == "__main__":
    main()

