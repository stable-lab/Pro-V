import json
import ast
import cocotb
from cocotb.binary import BinaryValue

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
    """
    根据不一致性分析结果过滤场景索引：
    1. 如果所有场景的索引都一样，返回 [0]
    2. 如果只有一个场景的索引和别的都不一样，返回其他场景的索引中的第一个
    3. 否则返回去重后的索引列表
    """
    if not inconsistencies:
        return [0]  # 如果没有不一致，返回第一个索引
        
    # 收集所有不一致的组对
    all_group_pairs = set()
    for scenario_inconsistencies in inconsistencies.values():
        for inconsistency in scenario_inconsistencies:
            all_group_pairs.add(tuple(inconsistency['group_pair']))
            
    if not all_group_pairs:
        return [0]  # 如果没有不一致的组对，返回第一个索引
        
    # 统计每个索引出现的次数
    index_count = {}
    for pair in all_group_pairs:
        for idx in pair:
            index_count[idx] = index_count.get(idx, 0) + 1
            
   
    # 找出出现次数最多的索引
    max_count = max(index_count.values())
    most_common_indices = [idx for idx, count in index_count.items() if count == max_count]
    
    # 如果只有一个索引出现次数不同，返回其他索引中的第一个
    if len(most_common_indices) == len(index_count) - 1:
        different_idx = [idx for idx in index_count if idx not in most_common_indices][0]
        return [idx for idx in most_common_indices][:1]
        
    # 否则返回去重后的索引列表
    return sorted(list(set(index_count.keys())))

def compare_scenarios_cmb(output_address):
    # Read file contents
    with open(output_address, 'r') as f:
        lines = f.readlines()
    
    # Parse data from each line
    all_scenarios = []
    for line in lines:
        #print('line:', line)  # 打印每一行
        try:
            # Parse outer data using ast.literal_eval
            parsed = ast.literal_eval(line)
            if not isinstance(parsed, list) or len(parsed) < 2:
                continue
                
            if parsed[0] and isinstance(parsed[1], dict) and 'out' in parsed[1]:
                # Parse inner data using json.loads
                scenarios = json.loads(parsed[1]['out'])
                if not isinstance(scenarios, list):
                    continue
                    
                # Extract output values for each scenario
                scenario_outputs = {}
                for scenario_idx, scenario in enumerate(scenarios):
                    if not isinstance(scenario, list) or not scenario:
                        continue
                        
                    scenario_data = scenario[0]  # 取第一个元素
                    if not isinstance(scenario_data, dict) or 'q' not in scenario_data:
                        continue
                        
                    # Use scenario index as scenario name
                    scenario_name = f"scenario_{scenario_idx}"
                    outputs = {}
                    
                    # 这里假设 q 是一个 list，每个元素是字符串
                    for state_idx, state_value in enumerate(scenario_data['q']):
                        try:
                            outputs[f'q_{state_idx}'] = int(state_value, 2)  # 假设是二进制字符串
                        except Exception:
                            outputs[f'q_{state_idx}'] = state_value  # 保底，直接存字符串
                            
                    if outputs:  # Only add if there is valid data
                        scenario_outputs[scenario_name] = outputs
                        
                if scenario_outputs:  # Only add if there are valid scenarios
                    all_scenarios.append(scenario_outputs)
                        
        except (json.JSONDecodeError, SyntaxError, ValueError) as e:
            print(f"Parsing error: {e}")
            continue
        except Exception as e:
            print(f"Error processing data: {e}")
            continue

    if not all_scenarios:
        print("Warning: No test scenarios were successfully parsed")
        return {}

    # Compare outputs for all scenarios
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
    
    # 在返回 inconsistencies 之前添加过滤
    filtered_indices = filter_inconsistencies(inconsistencies)
    print(f"Filtered indices: {filtered_indices}")
    
    return inconsistencies


def compare_scenarios_seq(output_address):
    # 读取文件内容
    with open(output_address, 'r') as f:
        lines = f.readlines()
    
    # 解析每行数据
    all_scenarios = []
    for line in lines:
        try:
            # 使用ast.literal_eval解析外层数据
            parsed = ast.literal_eval(line)
            if not isinstance(parsed, list) or len(parsed) < 2:
                continue
                
            if parsed[0] and isinstance(parsed[1], dict) and 'out' in parsed[1]:
                # 使用json.loads解析内层数据
                scenarios = json.loads(parsed[1]['out'])
                if not isinstance(scenarios, list):
                    continue
                    
                # 提取每个场景的输出值
                scenario_outputs = {}
                for scenario_idx, scenario in enumerate(scenarios):
                    if not isinstance(scenario, list) or not scenario:
                        continue
                        
                    scenario_data = scenario[0]  # 取第一个元素
                    if not isinstance(scenario_data, dict):
                        continue
                        
                    # 使用场景索引作为场景名称
                    scenario_name = f"scenario_{scenario_idx}"
                    outputs = {}
                    
                    # 处理除了clock_cycles之外的所有变量
                    for key, value in scenario_data.items():
                        if key != "clock cycles":
                            if isinstance(value, list):
                                # 如果值是列表（如z），保存为列表
                                outputs[key] = value
                            else:
                                # 其他情况直接保存值
                                outputs[key] = value
                            
                    if outputs:  # 只有在有有效数据时才添加
                        scenario_outputs[scenario_name] = outputs
                        
                if scenario_outputs:  # 只有在有有效场景时才添加
                    all_scenarios.append(scenario_outputs)
                        
        except (json.JSONDecodeError, SyntaxError, ValueError) as e:
            print(f"解析错误: {e}")
            continue
        except Exception as e:
            print(f"处理数据时出错: {e}")
            continue

    if not all_scenarios:
        print("警告: 没有成功解析到测试场景")
        return {}

    # 比较所有场景的输出
    inconsistencies = {}
    
    # 获取所有场景名称
    all_scenario_names = set()
    for scenario_group in all_scenarios:
        all_scenario_names.update(scenario_group.keys())
    
    # 比较每个场景
    for scenario_name in all_scenario_names:
        scenario_inconsistencies = []
        
        # 比较所有组合
        for i in range(len(all_scenarios)):
            for j in range(i+1, len(all_scenarios)):
                # 检查两个组是否都有这个场景
                if scenario_name in all_scenarios[i] and scenario_name in all_scenarios[j]:
                    # 比较输出值
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
    
    # 在返回inconsistencies之前添加过滤
    filtered_indices = filter_inconsistencies(inconsistencies)
    print(f"过滤后的索引: {filtered_indices}")
    
    return inconsistencies

