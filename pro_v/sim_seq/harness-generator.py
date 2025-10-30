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
    # Generate Harness with JSON testbench (Sequential Logic)
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
    int unpass_total = 0;
    int unpass = 0;
    
"""

    # Collect all wide signals (input and output) from first data
    wide_input_signals = {}
    wide_output_signals = {}
    
    for name, value in datas[0]["input variable"][0].items():
        if name == "clock cycles":
            continue
        else:
            if len(value[0]) > 64:
                width = len(value[0])
                n_words = (width + 31) // 32
                wide_input_signals[name] = n_words
                cpp_code += f"""    VlWide<{n_words}> {name}_wide;\n"""
    
    for name, value in datas[0]["output variable"][0].items():
        if name == "clock cycles":
            continue
        else:
            if len(value[0]) > 64:
                width = len(value[0])
                n_words = (width + 31) // 32
                wide_output_signals[name] = n_words
                cpp_code += f"""    VlWide<{n_words}> {name}_wide;\n"""
    
    cpp_code += "\n"
    # Generate test logic for each scenario
    scenario_idx = 0
    for data in datas:
        stimulus = data["input variable"]
        expected = data["output variable"]
        scenario_name = data.get('scenario', 'unnamed')
        
        cpp_code += f"""    ///////////////////////////////////////////////////////////\n"""
        cpp_code += f"""    // Scenario: {scenario_name}\n"""
        cpp_code += f"""    ///////////////////////////////////////////////////////////\n"""
        cpp_code += f"""    printf("\\n========== Testing Scenario: {scenario_name} ==========\\n");\n"""
        cpp_code += f"""    unpass = 0;\n"""
        cpp_code += f"""    \n"""
        
        # Create new instance for this scenario (to reset state)
        cpp_code += f"""    // Create new instance for scenario {scenario_name}\n"""
        cpp_code += f"""    const std::unique_ptr<VerilatedContext> contextp_{scenario_idx}{{new VerilatedContext}};\n"""
        cpp_code += f"""    const std::unique_ptr<Vtop_module> top_{scenario_idx}{{new Vtop_module}};\n"""
        cpp_code += f"""    auto* contextp = contextp_{scenario_idx}.get();\n"""
        cpp_code += f"""    auto* top = top_{scenario_idx}.get();\n"""
        cpp_code += f"""    \n"""
        
        # Initialize clock to 0
        cpp_code += f"""    // Initialize clock\n"""
        cpp_code += f"""    top->clk = 0;\n"""
        cpp_code += f"""    top->eval();\n"""
        cpp_code += f"""    \n"""
        
        # Process each test phase (each element in stimulus list)
        for phase_idx, input_phase in enumerate(stimulus):
            clock_cycles = input_phase["clock cycles"]
            
            # Get input variables (excluding "clock cycles")
            input_vars = {k: v for k, v in input_phase.items() if k != "clock cycles"}
            output_vars = {k: v for k, v in expected[phase_idx].items() if k != "clock cycles"}
            
            cpp_code += f"""    // Phase {phase_idx}: {clock_cycles} clock cycles\n"""
            
            # For each clock cycle in this phase
            for cycle in range(clock_cycles):
                cpp_code += f"""    \n"""
                cpp_code += f"""    // Clock cycle {cycle}\n"""
                cpp_code += f"""    printf("--- Cycle {cycle} ---\\n");\n"""
                
                # Set input signals at clock low (before rising edge)
                cpp_code += f"""    // Set inputs before rising edge\n"""
                for name, values in input_vars.items():
                    temp = str(values[cycle])
                    hex_len = (len(temp) + 3) // 4
                    hex_value = hex(int(temp, 2))[2:].zfill(hex_len)
                    
                    cpp_code += f"""    printf("  Input {name} = 0b{temp}\\n");\n"""
                    
                    if len(temp) <= 64:
                        # Regular signal
                        cpp_code += f"""    top->{name} = 0x{hex_value};\n"""
                    else:
                        # Wide signal
                        width = len(temp)
                        n_words = (width + 31) // 32
                        padded = temp.zfill(n_words * 32)
                        chunks = [
                            int(padded[-32 * (j + 1): -32 * j or None], 2)
                            for j in range(n_words)
                        ]
                        for j, c in enumerate(chunks):
                            cpp_code += f"""    {name}_wide[{j}] = 0x{c:08X}u;\n"""
                            cpp_code += f"""    top->{name}[{j}] = {name}_wide[{j}];\n"""
                
                # Rising edge: clk 0->1
                cpp_code += f"""    \n"""
                cpp_code += f"""    // Rising edge\n"""
                cpp_code += f"""    top->clk = 1;\n"""
                cpp_code += f"""    top->eval();\n"""
                cpp_code += f"""    contextp->timeInc(1);\n"""
                cpp_code += f"""    \n"""
                
                # Check outputs after rising edge
                cpp_code += f"""    // Check outputs\n"""
                for name, values in output_vars.items():
                    temp = str(values[cycle])
                    hex_len = (len(temp) + 3) // 4
                    hex_value = hex(int(temp, 2))[2:].zfill(hex_len)
                    
                    if len(temp) <= 64:
                        # Regular output signal
                        cpp_code += f"""    printf("  Output {name}: expected=0x{hex_value}, actual=0x%llx\\n", (unsigned long long)top->{name});\n"""
                        cpp_code += f"""    if (top->{name} != 0x{hex_value}) {{\n"""
                        cpp_code += f"""        unpass++;\n"""
                        cpp_code += f"""        printf("  [FAIL] Mismatch at {name} in cycle {cycle}\\n");\n"""
                        cpp_code += f"""    }} else {{\n"""
                        cpp_code += f"""        printf("  [PASS] {name} matched\\n");\n"""
                        cpp_code += f"""    }}\n"""
                    else:
                        # Wide output signal
                        width = len(temp)
                        n_words = (width + 31) // 32
                        padded = temp.zfill(n_words * 32)
                        chunks = [
                            int(padded[-32 * (k + 1): -32 * k or None], 2)
                            for k in range(n_words)
                        ]
                        
                        # Set expected values
                        for k, c in enumerate(chunks):
                            cpp_code += f"""    {name}_wide[{k}] = 0x{c:08X}u;\n"""
                        
                        # Compare and print
                        cpp_code += f"""    printf("  Output {name} (wide):\\n");\n"""
                        cpp_code += f"""    bool {name}_match_{cycle} = true;\n"""
                        for k in range(n_words):
                            cpp_code += f"""    printf("    [{k}] expected=0x%08X, actual=0x%08X\\n", {name}_wide[{k}], top->{name}[{k}]);\n"""
                            cpp_code += f"""    if (top->{name}[{k}] != {name}_wide[{k}]) {name}_match_{cycle} = false;\n"""
                        
                        cpp_code += f"""    if (!{name}_match_{cycle}) {{\n"""
                        cpp_code += f"""        unpass++;\n"""
                        cpp_code += f"""        printf("  [FAIL] Mismatch at {name} in cycle {cycle}\\n");\n"""
                        cpp_code += f"""    }} else {{\n"""
                        cpp_code += f"""        printf("  [PASS] {name} matched\\n");\n"""
                        cpp_code += f"""    }}\n"""
                
                # Falling edge: clk 1->0
                cpp_code += f"""    \n"""
                cpp_code += f"""    // Falling edge\n"""
                cpp_code += f"""    top->clk = 0;\n"""
                cpp_code += f"""    top->eval();\n"""
                cpp_code += f"""    contextp->timeInc(1);\n"""
        
        # Summary for this scenario
        cpp_code += f"""
    // Scenario summary
    if (unpass == 0) {{
        std::cout << "✓ All tests passed for scenario {scenario_name}" << std::endl;
    }} else {{
        std::cout << "✗ Test failed with " << unpass << " error(s) for scenario {scenario_name}" << std::endl;
        unpass_total += unpass;
    }}
    std::cout << std::endl;

"""
        scenario_idx += 1

    # Final summary
    cpp_code += """
    // Final test summary
    if (unpass_total == 0) {
        std::cout << "========================================" << std::endl;
        std::cout << "✓ All scenarios passed!" << std::endl;
        std::cout << "========================================" << std::endl;
    } else {
        std::cout << "========================================" << std::endl;
        std::cout << "✗ Total failures: " << unpass_total << std::endl;
        std::cout << "========================================" << std::endl;
    }
    
    return unpass_total;
}
"""

    with open("rfuzz-harness.cpp", "w") as file:
        file.write(cpp_code)
    
    print("Generated rfuzz-harness.cpp successfully!")


if __name__ == "__main__":
    main()
