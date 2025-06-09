import json
import logging
import ast
import os   
import subprocess
from datetime import datetime

logger = logging.getLogger(__name__)


def get_prob_spec(file_dir_path,task_number):
    # give the file path and task_number, return the problem specification and the header in verilog-eval/HDLBits/HDLBits_data_backup0304.jsonl
    with open("../verilog-eval/HDLBits/HDLBits_data_backup0304.jsonl", "r") as f:
        for line in f:
            data = json.loads(line)
            if data["task_number"] == task_number:
                # print(f"data: {data}")
                spec_ = data["description"]
                header_ = data["header"]
                top_ = data["module_code"]
                break
    spec_file_path = os.path.join(file_dir_path, f"spec.txt")
    header_file_path = os.path.join(file_dir_path, f"module_header.txt")
    top_file_path = os.path.join(file_dir_path, f"top.v")
    if os.path.exists(spec_file_path):
        with open(spec_file_path, "r") as f:
            spec = f.read()
    else:
        spec = spec_
    if os.path.exists(header_file_path):
        with open(header_file_path, "r") as f:
            header = f.read()
    else:
        header = header_

    if os.path.exists(top_file_path):
        with open(top_file_path, "r") as f:
            top = f.read()
    else:
        top = top_
   
    return spec, header, top

def process_testbench(json_file):
    # Read JSON file
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    # Convert to required dictionary format
    testbench = []
    for scenario in data:
        for i in range(len(scenario['input variable'])):
            #print(f"{scenario['output variable'][i]}: {scenario['input variable'][i]}")
            scenario_name = scenario['scenario']+str(i)
            testbench.append({
                'scenario': scenario_name,
                'input variable':[ scenario['input variable'][i]],
                'output variable': [scenario['output variable'][i]]
            })
    
    return testbench

def create_testbench_json(stimulus_file, output_file, index_list):
   
    # Read stimulus.json to get input data
    with open(stimulus_file, "r") as f:
        stimulus_data = json.load(f)

    # Read our_output.txt to get output data
    with open(output_file, "r") as f:
        output_lines = f.readlines()

    # Parse output data
    
    for idx,line in enumerate(output_lines):
        all_outputs = []

        parsed = ast.literal_eval(line)
        if parsed[0] and "out" in parsed[1]:
            # Parse JSON string
            try:
                output_str = parsed[1]["out"].strip()
                # If output is a list-formatted string, remove leading and trailing brackets
                if output_str.startswith('[') and output_str.endswith(']'):
                    output_str = output_str[1:-1]
                # Try to parse as JSON
                output_data = json.loads(f"[{output_str}]")
                all_outputs.extend(output_data)  # Expand output data list
            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing error: {e}")
                logger.error(f"Problematic data: {output_str}")
                continue

        # If no valid output, exit
        if not all_outputs:
            print("No valid output data found")
            return

        # Use the last complete output as standard result
        standard_output = all_outputs  # Use the last output
        # Merge input and output
        combined_data = []

        # Iterate through each test scenario
        for i, stimulus_scenario in enumerate(stimulus_data):
            scenario_name = stimulus_scenario["scenario"]
            # Create merged scenario data
            for j in stimulus_scenario["input variable"]:
                for key,item in j.items():
                    if key!="clock cycles":
                        if len(item) < j["clock cycles"]:
                            print(f"item: {item} is less than clock cycles: {j['clock cycles']}")
                            item.extend([item[-1]]*(j["clock cycles"]-len(item)))
            
            combined_scenario = {
                "scenario": scenario_name,
                "input variable": stimulus_scenario["input variable"],
            }
            combined_scenario["output variable"] = []
            
            for x, j in enumerate(combined_scenario["input variable"]):
                temp_output = {}
                temp_output["clock cycles"] = j["clock cycles"]
                temp_output.update(standard_output[i][x])
                combined_scenario["output variable"].append(temp_output)
            combined_data.append(combined_scenario)
        if idx in index_list:
            output_dir = os.path.dirname(output_file)
            output_json_file = os.path.join(output_dir, f"testbench_{idx}.json")

            # Write merged data to JSON file
            with open(output_json_file, "w", encoding="utf-8") as f:
                json.dump(combined_data, f, indent=2, ensure_ascii=False)

            print(f"Successfully merged stimulus and output data to {output_json_file}")


def create_testbench_json_cmb(stimulus_file, output_file,index_list):
    """
    Merge stimulus.json and our_output.txt into a complete testbench.json file
    
    Parameters:
    stimulus_file -- stimulus.json file path
    output_file -- our_output.txt file path
    output_json_file -- output testbench.json file path
    """
    #get the directory of the output_file
    output_dir = os.path.dirname(output_file)
    
    # Read stimulus.json to get input data
    with open(stimulus_file, 'r') as f:
        stimulus_data = json.load(f)
    
    # Read our_output.txt to get output data
    with open(output_file, 'r') as f:
        output_lines = f.readlines()
    
    for idx,line in enumerate(output_lines):
        all_outputs = []
        parsed = ast.literal_eval(line)
        if parsed[0] and "out" in parsed[1]:
            # Parse JSON string
            try:
                output_str = parsed[1]["out"].strip()
                # If output is a list-formatted string, remove leading and trailing brackets
                if output_str.startswith('[') and output_str.endswith(']'):
                    output_str = output_str[1:-1]
                # Try to parse as JSON
                output_data = json.loads(f"[{output_str}]")
                all_outputs.extend(output_data)  # Expand output data list
            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing error: {e}")
                logger.error(f"Problematic data: {output_str}")
                continue
        if idx in index_list:
            
              
    

    # If no valid output, exit
            if not all_outputs:
                print("No valid output data found")
                continue
            
            # Check if there are inconsistencies in all output groups
            # Only use the first output group as standard result
            standard_output = all_outputs
            #print(f"standard_output: {standard_output}")
            
            # Merge input and output
            combined_data = []
            
            # Iterate through each test scenario
            for i, stimulus_scenario in enumerate(stimulus_data):
                scenario_name = stimulus_scenario['scenario']
                
                # Find corresponding scenario in output data
                output_scenario = standard_output[i]
                
                if output_scenario:
                    # Create merged scenario data
                    combined_scenario = {
                        "scenario": scenario_name,
                        "input variable": stimulus_scenario['input variable'],
                        "output variable": output_scenario
                    }
                    combined_data.append(combined_scenario)
                else:
                    print(f"Warning: Scenario '{scenario_name}' not found in output data")
                    # Add scenario without output
                    combined_scenario = {
                        "scenario": scenario_name,
                        "input variable": stimulus_scenario['input variable'],
                        "output variable": []
                    }
                    combined_data.append(combined_scenario)
            
            # Write merged data to JSON file
            with open(os.path.join(output_dir, f"testbench_{idx}.json"), "w") as f:
                json.dump(combined_data, f, indent=2, ensure_ascii=False)
            testbench_dict = process_testbench(f"{output_dir}/testbench_{idx}.json")
            #print(testbench_dict)
            with open(f"{output_dir}/testbench_{idx}.json", 'w') as f:
                json.dump(testbench_dict, f, indent=2, ensure_ascii=False)
            
            print(f"Successfully merged stimulus and output data to {os.path.join(output_dir, f'testbench_{idx}.json')}")


def simulate_dut_seq(output_dir):
    # Get the absolute path of the current script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sim_dir = os.path.join(current_dir, "sim_seq")
    
    # Source file paths
    dut_path = os.path.join(output_dir, "top.v")
    test_path = os.path.join(output_dir, "testbench_0.json")
    
    # Ensure target directory exists
    os.makedirs(sim_dir, exist_ok=True)
    
    # Clean and copy files
    subprocess.run(f"cd {sim_dir} && make clean > /dev/null 2>&1", shell=True)
    subprocess.run(f"rm -f {sim_dir}/top_module.v", shell=True)
    subprocess.run(f"rm -f {sim_dir}/testbench.json", shell=True)
    
    # Copy files to simulation working directory
    subprocess.run(f"cp {dut_path} {sim_dir}/top_module.v", shell=True)
    subprocess.run(f"cp {test_path} {sim_dir}/testbench.json", shell=True)
    
    # Execute simulation command and capture output
    cmd = f"cd {sim_dir} && python harness-generator.py && make"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    # Save output to log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(output_dir, f"simulate_seq.log")
    with open(log_file, "w") as f:
        f.write(f"Command: {cmd}\n")
        f.write(f"Return code: {result.returncode}\n")
        f.write("\n=== STDOUT ===\n")
        f.write(result.stdout)
        f.write("\n=== STDERR ===\n")
        f.write(result.stderr)

def simulate_dut_cmb(output_dir):
    # Get the absolute path of the current script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sim_dir = os.path.join(current_dir, "sim_cmb")
    
    # Source file paths
    dut_path = os.path.join(output_dir, "top.v")
    test_path = os.path.join(output_dir, "testbench_0.json")
    
    # Ensure target directory exists
    os.makedirs(sim_dir, exist_ok=True)
    
    # Clean and copy files
    subprocess.run(f"cd {sim_dir} && make clean > /dev/null 2>&1", shell=True)
    subprocess.run(f"rm -f {sim_dir}/top_module.v", shell=True)
    subprocess.run(f"rm -f {sim_dir}/testbench.json", shell=True)
    
    # Check if files exist
    if not os.path.exists(dut_path):
        print(f"Error: DUT path {dut_path} does not exist")
        return
    if not os.path.exists(test_path):
        print(f"Error: Test path {test_path} does not exist")
        return
        
    # Copy files to simulation working directory
    subprocess.run(f"cp {dut_path} {sim_dir}/top_module.v", shell=True)
    subprocess.run(f"cp {test_path} {sim_dir}/testbench.json", shell=True)
    
    # Execute simulation command and capture output
    cmd = f"cd {sim_dir} && python harness-generator.py && make"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    # Save output to log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(output_dir, f"simulate_cmb.log")
    with open(log_file, "w") as f:
        f.write(f"Command: {cmd}\n")
        f.write(f"Return code: {result.returncode}\n")
        f.write("\n=== STDOUT ===\n")
        f.write(result.stdout)
        f.write("\n=== STDERR ===\n")
        f.write(result.stderr)

def split_test_cases(line):
    """Split a line containing multiple test cases into individual test cases."""
    # Find all occurrences of [True, {'out': ...}]
    start = 0
    test_cases = []
    while True:
        # Find the start of a test case
        start = line.find('[True, {', start)
        if start == -1:
            break
            
        # Find the matching closing bracket
        bracket_count = 1
        pos = start + 1
        while bracket_count > 0 and pos < len(line):
            if line[pos] == '[':
                bracket_count += 1
            elif line[pos] == ']':
                bracket_count -= 1
            pos += 1
            
        if bracket_count == 0:
            test_case = line[start:pos]
            test_cases.append(test_case)
            start = pos
        else:
            break
            
    return test_cases


def filter_inconsistencies(inconsistencies):
    

    if not inconsistencies:
        return [0]  # If no inconsistencies, return the first index
        
    # Collect all inconsistent group pairs
    all_group_pairs = set()
    for scenario_inconsistencies in inconsistencies.values():
        for inconsistency in scenario_inconsistencies:
            all_group_pairs.add(tuple(inconsistency['group_pair']))
            
    if not all_group_pairs:
        return [0]  # If no inconsistent group pairs, return the first index
        
    # Count occurrences of each index
    index_count = {}
    for pair in all_group_pairs:
        for idx in pair:
            index_count[idx] = index_count.get(idx, 0) + 1
            
   
    # Find indices with the highest occurrence count
    max_count = max(index_count.values())
    most_common_indices = [idx for idx, count in index_count.items() if count == max_count]
    
    # If only one index has a different count, return the first of the other indices
    if len(most_common_indices) == len(index_count) - 1:
        different_idx = [idx for idx in index_count if idx not in most_common_indices][0]
        return [idx for idx in most_common_indices][:1]
        
    # Otherwise return deduplicated index list
    return sorted(list(set(index_count.keys())))

def compare_scenarios_cmb(output_address):
    # Read file content
    with open(output_address, 'r') as f:
        lines = f.readlines()
    
    # Parse each line of data
    all_scenarios = []
    for line in lines:
        try:
            # Use ast.literal_eval to parse outer data
            parsed = ast.literal_eval(line)
            if not isinstance(parsed, list) or len(parsed) < 2:
                continue
                
            if parsed[0] and isinstance(parsed[1], dict) and 'out' in parsed[1]:
                # Use json.loads to parse inner data
                scenarios = json.loads(parsed[1]['out'])
                if not isinstance(scenarios, list):
                    continue
                    
                # Extract output values for each scenario
                scenario_outputs = {}
                for scenario_idx, scenario in enumerate(scenarios):
                    if not isinstance(scenario, list) or not scenario:
                        continue
                        
                    # Use scenario index as scenario name
                    scenario_name = f"scenario_{scenario_idx}"
                    outputs = {}
                    
                    # Process all variables in each state
                    for state_idx, state in enumerate(scenario):
                        if isinstance(state, dict):
                            # Add each variable's value to outputs
                            for var_name, var_value in state.items():
                                output_key = f"{var_name}_{state_idx}"
                                outputs[output_key] = var_value
                            
                    if outputs:  # Only add if there is valid data
                        scenario_outputs[scenario_name] = outputs
                        
                if scenario_outputs:  # Only add if there are valid scenarios
                    all_scenarios.append(scenario_outputs)
                        
        except (json.JSONDecodeError, SyntaxError, ValueError) as e:
            print(f"Parse error: {e}")
            continue
        except Exception as e:
            print(f"Error processing data: {e}")
            continue

    if not all_scenarios:
        print("Warning: No test scenarios were successfully parsed")
        return {}

    # Compare outputs of all scenarios
    inconsistencies = {}
    
    # Get all scenario names
    all_scenario_names = set()
    for scenario_group in all_scenarios:
        all_scenario_names.update(scenario_group.keys())
    
    # Compare each scenario
    for scenario_name in all_scenario_names:
        scenario_inconsistencies = []
        
        # Compare all combinations
        for i in range(len(all_scenarios)):
            for j in range(i+1, len(all_scenarios)):
                # Check if both groups have this scenario
                if scenario_name in all_scenarios[i] and scenario_name in all_scenarios[j]:
                    # Compare output values
                    if all_scenarios[i][scenario_name] != all_scenarios[j][scenario_name]:
                        scenario_inconsistencies.append({
                            'group_pair': [i, j],
                            'values': {
                                'group1': all_scenarios[i][scenario_name],
                                'group2': all_scenarios[j][scenario_name]
                            }
                        })
        
        if scenario_inconsistencies:
            inconsistencies[scenario_name] = scenario_inconsistencies
    
    # Add filtering before returning inconsistencies
    filtered_indices = filter_inconsistencies(inconsistencies)
    print(f"After filtering: {filtered_indices}")
    
    return inconsistencies


def compare_scenarios_seq(output_address):
    # Read file content
    with open(output_address, 'r') as f:
        lines = f.readlines()
    
    # Parse each line of data
    all_scenarios = []
    for line in lines:
        try:
            # Use ast.literal_eval to parse outer data
            parsed = ast.literal_eval(line)
            if not isinstance(parsed, list) or len(parsed) < 2:
                continue
                
            if parsed[0] and isinstance(parsed[1], dict) and 'out' in parsed[1]:
                # Use json.loads to parse inner data
                scenarios = json.loads(parsed[1]['out'])
                if not isinstance(scenarios, list):
                    continue
                    
                # Extract output values for each scenario
                scenario_outputs = {}
                for scenario_idx, scenario in enumerate(scenarios):
                    if not isinstance(scenario, list) or not scenario:
                        continue
                        
                    scenario_data = scenario[0]  # Take the first element
                    if not isinstance(scenario_data, dict):
                        continue
                        
                    # Use scenario index as scenario name
                    scenario_name = f"scenario_{scenario_idx}"
                    outputs = {}
                    
                    # Process all variables except clock_cycles
                    for key, value in scenario_data.items():
                        if key != "clock cycles":
                            if isinstance(value, list):
                                # If value is a list (like z), save as list
                                outputs[key] = value
                            else:
                                # Otherwise save value directly
                                outputs[key] = value
                            
                    if outputs:  # Only add if there is valid data
                        scenario_outputs[scenario_name] = outputs
                        
                if scenario_outputs:  # Only add if there are valid scenarios
                    all_scenarios.append(scenario_outputs)
                        
        except (json.JSONDecodeError, SyntaxError, ValueError) as e:
            print(f"Parse error: {e}")
            continue
        except Exception as e:
            print(f"Error processing data: {e}")
            continue

    if not all_scenarios:
        print("Warning: No test scenarios were successfully parsed")
        return {}

    # Compare outputs of all scenarios
    inconsistencies = {}
    
    # Get all scenario names
    all_scenario_names = set()
    for scenario_group in all_scenarios:
        all_scenario_names.update(scenario_group.keys())
    
    # Compare each scenario
    for scenario_name in all_scenario_names:
        scenario_inconsistencies = []
        
        # Compare all combinations
        for i in range(len(all_scenarios)):
            for j in range(i+1, len(all_scenarios)):
                # Check if both groups have this scenario
                if scenario_name in all_scenarios[i] and scenario_name in all_scenarios[j]:
                    # Compare output values
                    if all_scenarios[i][scenario_name] != all_scenarios[j][scenario_name]:
                        scenario_inconsistencies.append({
                            'group_pair': [i, j],
                            'values': {
                                'group1': all_scenarios[i][scenario_name],
                                'group2': all_scenarios[j][scenario_name]
                            }
                        })
        
        if scenario_inconsistencies:
            inconsistencies[scenario_name] = scenario_inconsistencies
    
    # Add filtering before returning inconsistencies
    filtered_indices = filter_inconsistencies(inconsistencies)
    print(f"Filtered indices: {filtered_indices}")
    
    return inconsistencies

