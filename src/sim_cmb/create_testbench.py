import ast
import json

from cocotb.binary import BinaryValue


def create_testbench_json(stimulus_file, output_file, output_json_file):
    """
    将stimulus.json和our_output.txt合并为一个完整的testbench.json文件

    参数:
    stimulus_file -- stimulus.json文件路径
    output_file -- our_output.txt文件路径
    output_json_file -- 输出的testbench.json文件路径
    """
    # 读取stimulus.json获取输入数据
    with open(stimulus_file, "r") as f:
        stimulus_data = json.load(f)

    # 读取our_output.txt获取输出数据
    with open(output_file, "r") as f:
        output_lines = f.readlines()

    # 解析输出数据
    all_outputs = []
    for line in output_lines:
        try:
            # 将字符串转换为Python对象
            parsed = ast.literal_eval(line)
            if parsed[0] and "out" in parsed[1]:
                # 解析JSON字符串
                output_data = json.loads(parsed[1]["out"])
                # 将二进制字符串转换为整数（如果需要）
                for scenario in output_data:
                    for output_var in scenario["output variable"]:
                        for key in output_var:
                            # 保持字符串格式，不转换为整数
                            pass
                all_outputs.append(output_data)
        except Exception as e:
            print(f"解析输出数据时出错：{e}")
            continue

    # 如果没有有效输出，退出
    if not all_outputs:
        print("没有找到有效的输出数据")
        return

    # 检查所有输出组中是否存在不一致
    # 只使用第一组输出作为标准结果
    standard_output = all_outputs[0]

    # 合并输入和输出
    combined_data = []

    # 遍历每个测试场景
    for stimulus_scenario in stimulus_data:
        scenario_name = stimulus_scenario["scenario"]

        # 在输出数据中查找对应的场景
        output_scenario = next(
            (s for s in standard_output if s["scenario"] == scenario_name), None
        )

        if output_scenario:
            # 创建合并后的场景数据
            combined_scenario = {
                "scenario": scenario_name,
                "input variable": stimulus_scenario["input variable"],
                "output variable": output_scenario["output variable"],
            }
            combined_data.append(combined_scenario)
        else:
            print(f"警告：在输出数据中未找到场景 '{scenario_name}'")
            # 添加没有输出的场景
            combined_scenario = {
                "scenario": scenario_name,
                "input variable": stimulus_scenario["input variable"],
                "output variable": [],
            }
            combined_data.append(combined_scenario)

    # 将合并后的数据写入JSON文件
    with open(output_json_file, "w", encoding="utf-8") as f:
        json.dump(combined_data, f, indent=2, ensure_ascii=False)

    print(f"已成功将stimulus和output数据合并到 {output_json_file}")
