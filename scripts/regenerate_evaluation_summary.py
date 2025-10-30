#!/usr/bin/env python3
"""
Regenerate evaluation_summary.json with correct total_tasks count (156)
- Collects all evaluation_results.json from task directories
- Uses 156 as the total task count for percentage calculations
"""

import json
import os
import sys

# CMB and SEQ task definitions
CMB_TASKS = [80, 81, 83, 84, 87, 89, 90, 91, 94, 95, 96, 101, 102, 103, 108, 111, 
             113, 115, 116, 117, 119, 122, 123, 124, 125, 126, 128, 129, 130, 
             132, 133, 134, 135, 136, 138, 139, 143, 5, 4, 17, 16, 1, 9, 24, 18, 
             2, 3, 21, 20, 22, 26, 8, 10, 19, 25, 23, 11, 12, 35, 38, 82, 85, 
             112, 114, 121, 140, 100, 104, 105, 109, 127, 131, 146, 154, 155, 156]

SEQ_TASKS = [6, 7, 13, 14, 15, 27, 28, 29, 30, 31, 32, 33, 34, 36, 37, 39, 40, 41, 
             42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 
             59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 
             76, 77, 78, 79, 86, 88, 92, 93, 97, 98, 99, 106, 107, 110, 118, 120, 
             137, 141, 142, 144, 145, 147, 148, 149, 150, 151, 152, 153]

TOTAL_BENCHMARK_TASKS = 156

def collect_evaluation_results(output_dir):
    """Collect all evaluation_results.json from task directories"""
    evaluation_results = []
    
    for item in sorted(os.listdir(output_dir)):
        item_path = os.path.join(output_dir, item)
        if os.path.isdir(item_path) and item.isdigit():
            eval_file = os.path.join(item_path, "evaluation_results.json")
            if os.path.exists(eval_file):
                try:
                    with open(eval_file, 'r') as f:
                        result = json.load(f)
                        evaluation_results.append(result)
                except Exception as e:
                    print(f"Warning: Failed to load {eval_file}: {e}")
    
    return evaluation_results


def calculate_metrics(results, total_benchmark_tasks):
    """
    Calculate metrics from evaluation results
    Metrics are calculated as: success_count / total_benchmark_tasks
    This means unevaluated tasks count as failures
    """
    if not results:
        return {
            'simulation_success': 0,
            'golden_accuracy': 0,
            'mutant_detection_100': 0,
            'mutant_detection_90': 0,
            'mutant_detection_80': 0
        }
    
    # Count absolute successes
    success_counts = {
        'simulation_success': sum(r['metrics']['simulation_success'] for r in results),
        'golden_accuracy': sum(r['metrics']['golden_accuracy'] for r in results),
        'mutant_detection_100': sum(r['metrics']['mutant_detection_100'] for r in results),
        'mutant_detection_90': sum(r['metrics']['mutant_detection_90'] for r in results),
        'mutant_detection_80': sum(r['metrics']['mutant_detection_80'] for r in results)
    }
    
    # Calculate as percentage of total benchmark tasks
    return {
        key: count / total_benchmark_tasks 
        for key, count in success_counts.items()
    }


def calculate_latency_stats(results):
    """Calculate latency statistics"""
    latencies = [r['latency'] for r in results if 'latency' in r]
    
    if not latencies:
        return {
            'total_tasks': 0,
            'average_latency': 0,
            'min_latency': 0,
            'max_latency': 0,
            'total_time': 0
        }
    
    return {
        'total_tasks': len(latencies),
        'average_latency': sum(latencies) / len(latencies),
        'min_latency': min(latencies),
        'max_latency': max(latencies),
        'total_time': sum(latencies)
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python regenerate_evaluation_summary.py <output_dir>")
        print("Example: python regenerate_evaluation_summary.py outputs/tb_gen_tb_fine_thinking_32B")
        sys.exit(1)
    
    output_dir = sys.argv[1]
    
    if not os.path.exists(output_dir):
        print(f"Error: Directory {output_dir} does not exist")
        sys.exit(1)
    
    print(f"Collecting evaluation results from {output_dir}...")
    evaluation_results = collect_evaluation_results(output_dir)
    
    print(f"Found {len(evaluation_results)} tasks with evaluation results")
    
    # Separate CMB and SEQ tasks
    cmb_results = [r for r in evaluation_results if r['task_number'] in CMB_TASKS]
    seq_results = [r for r in evaluation_results if r['task_number'] in SEQ_TASKS]
    
    print(f"  CMB tasks: {len(cmb_results)}")
    print(f"  SEQ tasks: {len(seq_results)}")
    
    # Calculate overall metrics based on total benchmark tasks
    overall_metrics = calculate_metrics(evaluation_results, TOTAL_BENCHMARK_TASKS)
    
    # For CMB and SEQ, use their respective totals
    total_cmb_tasks = len(CMB_TASKS)
    total_seq_tasks = len(SEQ_TASKS)
    
    cmb_metrics = calculate_metrics(cmb_results, total_cmb_tasks)
    seq_metrics = calculate_metrics(seq_results, total_seq_tasks)
    
    # Add total_tasks and evaluated_tasks to metrics
    cmb_metrics['total_tasks'] = total_cmb_tasks
    cmb_metrics['evaluated_tasks'] = len(cmb_results)
    seq_metrics['total_tasks'] = total_seq_tasks
    seq_metrics['evaluated_tasks'] = len(seq_results)
    
    # Calculate latency statistics
    latency_stats = calculate_latency_stats(evaluation_results)
    cmb_latency_stats = calculate_latency_stats(cmb_results)
    seq_latency_stats = calculate_latency_stats(seq_results)
    
    # Create summary with TOTAL_BENCHMARK_TASKS as the base
    summary = {
        'total_tasks': TOTAL_BENCHMARK_TASKS,
        'evaluated_tasks': len(evaluation_results),
        'overall_metrics': overall_metrics,
        'cmb_metrics': cmb_metrics,
        'seq_metrics': seq_metrics,
        'latency_statistics': latency_stats,
        'cmb_latency_statistics': cmb_latency_stats,
        'seq_latency_statistics': seq_latency_stats,
        'per_task_results': evaluation_results
    }
    
    # Save summary
    summary_path = os.path.join(output_dir, "evaluation_summary.json")
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\nRegenerated evaluation summary:")
    print(f"  Total benchmark tasks: {TOTAL_BENCHMARK_TASKS}")
    print(f"  Evaluated tasks: {len(evaluation_results)}")
    print(f"  Missing tasks: {TOTAL_BENCHMARK_TASKS - len(evaluation_results)}")
    print(f"\nOverall metrics:")
    print(f"  Simulation success: {overall_metrics['simulation_success']:.2%}")
    print(f"  Golden accuracy: {overall_metrics['golden_accuracy']:.2%}")
    print(f"  100% mutant detection: {overall_metrics['mutant_detection_100']:.2%}")
    print(f"  90%+ mutant detection: {overall_metrics['mutant_detection_90']:.2%}")
    print(f"  80%+ mutant detection: {overall_metrics['mutant_detection_80']:.2%}")
    print(f"\nSaved to: {summary_path}")


if __name__ == "__main__":
    main()

