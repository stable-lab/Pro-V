import json
import os
import re
import shutil


def move_ref_files():
    # 源目录和目标目录
    source_file = "../verilog-eval/HDLBits/HDLBits_data_backup0304.jsonl"
    # target_base_dir = "sim/testcase"
    target_base_dir = "output_tb_gen_tb_20250408"
    target_filename = "top.v"
    target_filename_spec = "spec.txt"

    # 确保目标基础目录存在
    if not os.path.exists(target_base_dir):
        os.makedirs(target_base_dir)

    # 遍历源文件
    datas = []
    with open(source_file, "r") as file:
        for line in file:
            data = json.loads(line)
            datas.append(data)
    
    for data in datas:
        prob_num = data["task_number"]
        # 查找符合模式的文件 (Prob{数字}_*_ref.sv)
        rtl_code = data["module_code"]
        spec = data["description"]

        # 只处理31以后的文件
        if prob_num >30:
            # 创建目标目录
            target_dir = os.path.join(target_base_dir, str(prob_num))
            if os.path.exists(target_dir):
                

                with open(os.path.join(target_dir, target_filename), "w") as file:
                    file.write(rtl_code)
                with open(os.path.join(target_dir, target_filename_spec), "w") as file:
                    file.write(spec)

                print(f"已将文件 {prob_num} 复制到 {target_dir}")
import ast
import json


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

        parsed = ast.literal_eval(line)
        if parsed[0] and "out" in parsed[1]:
            # 解析JSON字符串
            output_data = json.loads(parsed[1]["out"])
            all_outputs.append(output_data)  # 展开输出数据列表

    # 如果没有有效输出，退出
    if not all_outputs:
        print("没有找到有效的输出数据")
        return

    # 使用最后一个完整的输出作为标准结果
    standard_output = all_outputs[1]  # 使用最后一个输出
    print(standard_output)
    # 合并输入和输出
    combined_data = []

    # 遍历每个测试场景
    for i, stimulus_scenario in enumerate(stimulus_data):
        scenario_name = stimulus_scenario["scenario"]
        # print(stimulus_scenario['input variable'][i]['clock cycles'])
        print(standard_output[i])
        # 创建合并后的场景数据
        combined_scenario = {
            "scenario": scenario_name,
            "input variable": stimulus_scenario["input variable"],
        }
        combined_scenario["output variable"] = []
        for x, j in enumerate(combined_scenario["input variable"]):
            print("j", j)
            temp_output = {}
            temp_output["clock cycles"] = j["clock cycles"]
            print("standard_output[i][x]", standard_output[i][x])
            temp_output.update(standard_output[i][x])
            combined_scenario["output variable"].append(temp_output)
        combined_data.append(combined_scenario)

    # 将合并后的数据写入JSON文件
    with open(output_json_file, "w", encoding="utf-8") as f:
        json.dump(combined_data, f, indent=2, ensure_ascii=False)

    print(f"已成功将stimulus和output数据合并到 {output_json_file}")





if __name__ == "__main__":

    taskids = [97]
    root_die="output_tb_gen_tb_20250408"
    for taskid in taskids:
        create_testbench_json(
            f"{root_die}/{taskid}/stimulus.json",
            f"{root_die}/{taskid}/our_output.txt",
            f"{root_die}/{taskid}/testbench.json",
        )
    move_ref_files()
