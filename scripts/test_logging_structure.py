#!/usr/bin/env python3
"""
Test script to verify the new logging structure works correctly
"""

import os
import sys
import tempfile
import shutil

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pro_v.utils.log_utils import get_logger, set_log_dir, set_base_log_dir
from pro_v.utils.eval_logger import EvaluationLogger


def test_structured_logging():
    """Test the structured logging system"""
    print("Testing structured logging system...")
    
    # Create temporary directory for testing
    test_dir = tempfile.mkdtemp(prefix="test_logs_")
    print(f"Test directory: {test_dir}")
    
    try:
        # Test 1: Set base log directory
        set_base_log_dir(test_dir)
        print("\n1. Base log directory set")
        
        # Test 2: Create system logs
        system_log_dir = os.path.join(test_dir, "system")
        os.makedirs(system_log_dir, exist_ok=True)
        set_log_dir(system_log_dir, log_type="system")
        
        system_logger = get_logger("test_system", log_type="system")
        system_logger.info("System log test message")
        print("2. System logs created")
        
        # Test 3: Create task logs
        task_log_dir = os.path.join(test_dir, "tasks", "1")
        os.makedirs(task_log_dir, exist_ok=True)
        
        # Agent logs
        set_log_dir(task_log_dir, log_type="agent")
        agent_logger = get_logger("test_agent", log_type="agent")
        agent_logger.info("Agent log test message")
        print("3. Agent logs created")
        
        # Simulation logs
        sim_log_dir = os.path.join(task_log_dir, "simulation")
        os.makedirs(sim_log_dir, exist_ok=True)
        with open(os.path.join(sim_log_dir, "simulate_test.log"), "w") as f:
            f.write("Simulation log test\n")
        print("4. Simulation logs created")
        
        # Test 4: Create evaluation logger and log results
        eval_logger = EvaluationLogger(test_dir)
        
        test_eval_result = {
            'task_number': 1,
            'simulation_success': True,
            'golden_pass': True,
            'mutant_results': [True, True, False, True],
            'metrics': {
                'simulation_success': 1,
                'golden_accuracy': 1,
                'mutants_detected': 3,
                'mutants_total': 4,
                'mutant_detection_100': 0,
                'mutant_detection_90': 0,
                'mutant_detection_80': 1
            }
        }
        
        eval_logger.log_task_evaluation(1, test_eval_result)
        print("5. Evaluation logs created")
        
        # Test 5: Generate summary
        eval_logger.generate_summary([test_eval_result])
        print("6. Evaluation summary generated")
        
        # Verify structure
        print("\n" + "=" * 80)
        print("Verifying log structure...")
        print("=" * 80)
        
        expected_paths = [
            "system/system/test_system.log",
            "system/system/_all_system.log",
            "tasks/1/agent/test_agent.log",
            "tasks/1/agent/_all_agent.log",
            "tasks/1/simulation/simulate_test.log",
            "evaluation_results/evaluation_summary.csv",
            "evaluation_results/overall_summary.json",
            "evaluation_results/task_1.json"
        ]
        
        all_exist = True
        for path in expected_paths:
            full_path = os.path.join(test_dir, path)
            exists = os.path.exists(full_path)
            status = "✓" if exists else "✗"
            print(f"{status} {path}")
            if not exists:
                all_exist = False
        
        print("=" * 80)
        
        if all_exist:
            print("\n✓ All tests passed! Logging structure is correct.")
            
            # Show CSV content
            csv_path = os.path.join(test_dir, "evaluation_results", "evaluation_summary.csv")
            print("\nCSV Summary:")
            print("-" * 80)
            with open(csv_path, 'r') as f:
                print(f.read())
            
            return True
        else:
            print("\n✗ Some tests failed. Check the output above.")
            return False
    
    finally:
        # Cleanup
        print(f"\nCleaning up test directory: {test_dir}")
        shutil.rmtree(test_dir)


if __name__ == "__main__":
    success = test_structured_logging()
    sys.exit(0 if success else 1)

