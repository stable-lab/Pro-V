# Analyse the DUT verilog files
# 1> generate rfuzz harness to fuzzing method
# 2> generate explicit signal prompt to LLM method

from __future__ import absolute_import, print_function

import json
import os
import sys

# the next line can be removed after installation
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# import pyverilog
# from pyverilog.dataflow.dataflow_analyzer import VerilogDataflowAnalyzer


def main():

    test_file = "testbench.json"
    datas = []
    try:
        with open(test_file, "r") as f:
            # 尝试读取整个文件作为一个JSON对象
            datas = json.load(f)
    except json.JSONDecodeError:
        try:
            # 如果上面失败，尝试按行读取JSON
            with open(test_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:  # 跳过空行
                        data = json.loads(line)
                        datas.append(data)
        except Exception as e:
            print(f"Error reading JSON file: {e}")
            return

    ###############################################
    # Generate Harness with JSON testbench
    ###############################################
    cpp_code = """
#include "rfuzz-harness.h"
#include <vector>
#include <string>
#include <memory>
#include <iostream>
#include <verilated.h>
#include "Vtop_module.h"

int fuzz_poke() {
    VerilatedContext* contextp;
    Vtop_module* top;
"""

    # 获取datas[0]["input variable"][0]中的所有变量名和width
    signal_width = {}

    for name, value in datas[0]["input variable"][0].items():

        if name == "clock cycles":
            continue
        else:
            signal_width[name] = len(value[0])
            if len(value[0]) > 32:
                # print("input",name,value)
                # 对于大数值，使用 VL_WORDS_I 处理
                width = len(value[0])
                n_words = (width + 31) // 32
                cpp_code += (
                    f"""    VlWide<{n_words}> {name}_wide;\n"""
                )
                
    for name, value in datas[0]["output variable"][0].items():
        check_out="printf(\"output_vars:\\n\");\n"

        if name == "clock cycles":
            continue
        else:
            signal_width[name] = len(value[0])

            if len(value[0]) > 32:
                #print("output", name, value)
                # 对于大数值，使用 VL_WORDS_I 处理
                cpp_code += (
                    f"""   VlWide<{int((len(value[0])+31) // 32)}> {name}_wide;\n"""
                )
                for i in range(int(((len(value[0])+31) // 32))):
                    check_out+=f"printf(\"for i=%d in %d\\n\",{i},{int(((len(value[0])+31) // 32))});\n"
                    check_out+=f"printf(\"expected %x\\n\",{name}_wide[{i}]);\n"
                    check_out+=f"printf(\"actual %x\\n\",top->{name}[{i}]);\n"
                check_out+="\n"
            else:
                
                check_out=f"printf(\"actual %x\\n\",top->{name});\n"

    cpp_code += f"""        int unpass_total = 0;\n"""
    cpp_code += f"""        int unpass = 0;\n"""
    context_idx = 0
    for data in datas:
        cpp_code += f"""       ////////////////////////////scenario {data['scenario']}////////////////////////////\n"""

        stimulus = data["input variable"]
        expected = data["output variable"]


        cpp_code += f"""        unpass = 0;\n"""
        
        for idd, input in enumerate(stimulus):
            clock_cycles = input["clock cycles"]
            # Create a new VerilatedContext for each top
            cpp_code += """    const std::unique_ptr<VerilatedContext> contextp_%d {new VerilatedContext};\n""" % (context_idx)
            cpp_code += """    contextp = contextp_%d.get();\n""" % (context_idx)
            # 设置随机种子为0，确保重置为确定性的0值
            cpp_code += """    contextp->randReset(0);\n"""
            context_idx += 1
            # 单独使用DUT
            # if(i == 0):
            #     cpp_code += f"""    Vtop_module* top = new Vtop_module;\n"""
            # else:
            cpp_code += f"""    top = new Vtop_module(contextp);\n"""
            # 初始化所有变量为0
            cpp_code += """    top->eval();\n"""
            cpp_code += f"""    top->clk = 0;\n"""
            
            # 将top中的output变量全部清空  ----------------------------
            # for name, value in expected[i].items():
            #     if name == "clock cycles":
            #         continue
            #     else:
            #         if isinstance(value[0], str) and len(value[0]) > 16:
            #             cpp_code += f"""        for (int word_idx = 0; word_idx < {int(((len(value[0])/4) + 7) // 8)}; word_idx++) {{
            #                         {name}_wide[word_idx] = 0x0;
            #                     }}
            #                     top->{name} = {name}_wide;
            #             """
            #         else:
            #             cpp_code += f"""        top->{name} = 0x0;\n"""
            # ------------------------------------------------


            
        
            

            # input 中除了clock cycles 之外的变量
            input_vars = {k: v for k, v in input.items() if k != "clock cycles"}
            check = """printf("input_vars:\\n");\n"""
            for name, value in input_vars.items():
                check += f"""printf("top->%s = 0x%s\\n", "{name}", "{value}");\n"""
            check += "\n"

            check=""
            
            for circle in range(clock_cycles):

                

                check=f"printf(\"===Scenario: {data.get('scenario', 'unnamed')}, clock cycle: {circle}=====\\n\");\n"

                for name, value in input_vars.items():
                    #如果value中有除了0和1之外的值，则不进行赋值
                    if any(char not in '01' for char in value[circle]):
                        continue
                    else:
                        

                        temp = str(value[circle])
                        hex_len = (len(temp) + 3) // 4  # 计算需要的十六进制位数
                        hex_value = hex(int(temp, 2))[2:].zfill(hex_len)
                        if len(str(value[circle])) <= 32:
                            cpp_code += f"""        top->{name} = 0;\n"""
                        else:
                            width = len(temp)
                            n_words = (width + 31) // 32
                            # 补全 value，使其长度是32的倍数（前面补0）
                            padded = temp.zfill(n_words * 32)

                            # 切割成32位chunk，从高位到低位排列
                            chunks = [
            int(padded[-32 * (j + 1): -32 * j or None], 2)
            for j in range(n_words)
        ]
                            for j, c in enumerate(chunks):
                                
                                cpp_code += f""" top->{name}[{j}]  = 0;\n"""


                
                
                cpp_code += """        top->eval();\n"""
                cpp_code += """        contextp->timeInc(1);  \n"""

                
                for name, value in input_vars.items():
                    #如果value中有除了0和1之外的值，则不进行赋值
                    if any(char not in '01' for char in value[circle]):
                        continue
                    else:
                        check+= """printf("input_vars:\\n");\n"""
            
                        check += f"""printf("top->%s = 0x%s\\n", "{name}", "{value[circle][:signal_width[name]]}");\n"""
                        check += "\n"

                        temp = str(value[circle][:signal_width[name]])
                        hex_len = (len(temp) + 3) // 4  # 计算需要的十六进制位数
                        hex_value = hex(int(temp, 2))[2:].zfill(hex_len)
                        if len(str(value[circle])) <= 32:
                            cpp_code += f"""        top->{name} = 0x{hex_value};\n"""
                        else:
                            width = len(temp)
                            n_words = (width + 31) // 32
                            # 补全 value，使其长度是32的倍数（前面补0）
                            padded = temp.zfill(n_words * 32)

                            # 切割成32位chunk，从高位到低位排列
                            chunks = [
            int(padded[-32 * (j + 1): -32 * j or None], 2)
            for j in range(n_words)
        ]
                            for j, c in enumerate(chunks):
                                cpp_code+= f"{name}_wide[{j}] = 0x{c:08X}u;\n"
                                cpp_code += f""" top->{name}[{j}]  = {name}_wide[{j}];\n"""


               

                cpp_code += f"""        top->clk = !top->clk;\n"""
                cpp_code += """         top->eval();\n"""
                for name, value in expected[idd].items():
                    if name == "clock cycles":
                        continue
                    if any(char not in '01' for char in value[circle]):
                        continue
                    
                    else:
                        
                        temp = str(value[circle])
                        hex_len = (len(temp) + 3) // 4  # 计算需要的十六进制位数
                        hex_value = hex(int(temp, 2))[2:].zfill(hex_len)
                        if len(str(value[circle])) <= 32:
                            #print("value",str(value[j]))
                            
                            cpp_code += f"""        if (top->{name} != 0x{hex_value}) {{
            unpass++;\n"""
                            #cpp_code += f"""        if (1) {{
            #unpass++;\n"""
                            cpp_code += check+check_out
                            cpp_code += f"""            printf("At %d clock cycle of %d, top->%s, expected = 0x%s\\n", {circle},{clock_cycles}, "{name}", "0x{hex_value}");\n"""
                            cpp_code += f"""        }}\n"""

                        else:
                            
                            temp = str(value[circle])
                            width = len(temp)
                            n_words = (width + 31) // 32
                            # 补全 value，使其长度是32的倍数（前面补0）
                            padded = temp.zfill(n_words * 32)

                            # 切割成32位chunk，从高位到低位排列
                            chunks = [
            int(padded[-32 * (j + 1): -32 * j or None], 2)
            for j in range(n_words)
        ]
                            for m in range(0, len(hex_value), 8):
                                segment = hex_value[
                                    max(0, len(hex_value) - m - 8) : len(hex_value) - m
                                ]
                                if segment:
                                    cpp_code += f"""        {name}_wide[{m//8}] = 0x{segment};\n"""
                            
                            cpp_code += f"""        if (top->{name} != {name}_wide) {{
            unpass++;
            {check}\n {check_out}
            printf("At %d clock cycle of %d, wide value mismatch for %s\\n \\n", {j}, {clock_cycles}, "{name}");
        }}\n"""
                            cpp_code += f"""    // Checking wide signal {name}\n"""
                            width = len(value[circle])
                            n_words = (width + 31) // 32
                            # 补全 value，使其长度是32的倍数（前面补0）
                            padded = value[circle].zfill(n_words * 32)

                            # 切割成32位chunk，从高位到低位排列
                            chunks = [
            int(padded[-32 * (i + 1): -32 * i or None], 2)
            for i in range(n_words)
        ]
                            for i, c in enumerate(chunks):
                                cpp_code+= f"{name}_wide[{i}] = 0x{c:08X}u;\n"
                            check_code = (
                                f"""    if (top->{name} != {name}_wide)"""
                            )
                            cpp_code += f"""{check_code} {{
        unpass++\n;""" + check + f"""   
        printf("Mismatch at %s: expected \\n", "{name}");
    }}\n"""

                cpp_code += """         contextp->timeInc(1);\n"""
                cpp_code += f"""        top->clk = !top->clk;\n"""

            #cpp_code += f"""        top->final();"""
            #cpp_code += f"""        top = new Vtop_module;"""
                
                
                

        cpp_code += f"""

        if (unpass == 0) {{
            std::cout << "Test passed for scenario {data['scenario']}" << std::endl;
        }} else {{
            std::cout << "Test failed,unpass = " << unpass << " for scenario {data['scenario']}" << std::endl;
            unpass_total += unpass;
        }}
"""

    cpp_code += """
    return unpass_total;
}
"""

    with open("rfuzz-harness.cpp", "w") as file:
        file.write(cpp_code)


if __name__ == "__main__":
    main()
