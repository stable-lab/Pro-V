# Analyse the DUT verilog files
# 1> generate rfuzz harness to fuzzing method
# 2> generate explicit signal prompt to LLM method

from __future__ import absolute_import, print_function

import json
import os
import sys


def process_sequence(sequence):
    """Process input/output sequence"""
    if isinstance(sequence, list) and len(sequence) > 0:
        if isinstance(sequence[0], dict) and "clock cycles" in sequence[0]:
            return sequence[0].get("Q", [])
    return sequence


def main():
    test_file = "testbench.json"
    datas = []

    with open(test_file, "r") as f:
            datas = json.load(f)
            # Process data format


    ###############################################
    # Generate Harness with JSON testbench (CMB)
    ###############################################
    cpp_code = """
#include "rfuzz-harness.h"
#include <vector>
#include <string>
#include <memory>
#include <iostream>
#include <verilated.h>
#include "Vtop_module.h"
#include <sstream>

int fuzz_poke() {
    int unpass_total = 0;
    int unpass = 0;
    
    // For combinational logic, create instances once and reuse
    const std::unique_ptr<VerilatedContext> contextp{new VerilatedContext};
    const std::unique_ptr<Vtop_module> top{new Vtop_module};

"""

    # Collect all wide signals (both input and output) from first data
    wide_input_signals = {}
    wide_output_signals = {}
    
    if datas and datas[0]["input variable"] and datas[0]["output variable"]:
        # Handle input wide signals
        for name, value in datas[0]["input variable"][0].items():
            if isinstance(value, str) and len(value) > 16:
                width = len(value)
                n_words = (width + 31) // 32
                wide_input_signals[name] = n_words
                cpp_code += f"""    VlWide<{n_words}> {name}_wide;\n"""
        
        print("datas", datas[0]["output variable"][0])

        # Handle output wide signals
        for name, value in datas[0]["output variable"][0].items():
            if isinstance(value, str) and len(str(value)) > 16:
                width = len(value)
                n_words = (width + 31) // 32
                wide_output_signals[name] = n_words
                cpp_code += f"""    VlWide<{n_words}> {name}_wide;\n"""
    
    cpp_code += "\n"
    
    # Generate test logic
    for data in datas:
        stimulus = data["input variable"]
        expected = data["output variable"]

        cpp_code += f"""    // Scenario: {data.get('scenario', 'unnamed')}\n"""
        cpp_code += f"""    unpass = 0;\n"""

        for i, input_step in enumerate(stimulus):
            print("input", i, input_step)
            
            # Print scenario header
            cpp_code += f"""    printf("===Scenario: {data.get('scenario', 'unnamed')} - Test %d=====\\n", {i});\n"""
            cpp_code += """    printf("input_vars:\\n");\n"""
            
            # Set all input values
            for name, value in input_step.items():
                if isinstance(value, str):
                    # Print input value
                    cpp_code += f"""    printf("  {name} = 0b{value}\\n");\n"""
                    
                    hex_value = hex(int(str(value), 2))[2:]
                    if len(str(value)) <= 16:
                        # Regular signal (<=16 bits)
                        cpp_code += f"""    top->{name} = 0x{hex_value};\n"""
                    else:
                        # Wide signal (>16 bits)
                        width = len(str(value))
                        n_words = (width + 31) // 32
                        padded = str(value).zfill(n_words * 32)

                        chunks = [
                            int(padded[-32 * (j + 1): -32 * j or None], 2)
                            for j in range(n_words)
                        ]
                        for j, c in enumerate(chunks):
                            cpp_code += f"""    {name}_wide[{j}] = 0x{c:08X}u;\n"""
                            cpp_code += f"""    top->{name}[{j}] = {name}_wide[{j}];\n"""

            # Evaluate the combinational logic (may need multiple evals for complex circuits)
            cpp_code += """    top->eval();\n"""
            cpp_code += """    top->eval();  // Second eval for complex combinational logic\n"""
            cpp_code += """\n"""
            
            # Check outputs
            cpp_code += """    printf("output_vars:\\n");\n"""
            print("expected", expected, i)
            
            for name, value in expected[i].items():
                if isinstance(value, str):
                    hex_value = hex(int(str(value), 2))[2:]
                    
                    if len(value) <= 16:
                        # Regular output signal
                        cpp_code += f"""    printf("  {name}: expected=0x{hex_value}, actual=0x%llx\\n", (unsigned long long)top->{name});\n"""
                        cpp_code += f"""    if (top->{name} != 0x{hex_value}) {{\n"""
                        cpp_code += f"""        unpass++;\n"""
                        cpp_code += f"""        printf("  [FAIL] Mismatch at {name}\\n");\n"""
                        cpp_code += f"""    }} else {{\n"""
                        cpp_code += f"""        printf("  [PASS] {name} matched\\n");\n"""
                        cpp_code += f"""    }}\n"""
                    else:
                        # Wide output signal
                        cpp_code += f"""    // Checking wide signal {name}\n"""
                        width = len(value)
                        n_words = (width + 31) // 32
                        padded = value.zfill(n_words * 32)

                        chunks = [
                            int(padded[-32 * (k + 1): -32 * k or None], 2)
                            for k in range(n_words)
                        ]
                        
                        # Set expected values
                        for k, c in enumerate(chunks):
                            cpp_code += f"""    {name}_wide[{k}] = 0x{c:08X}u;\n"""
                        
                        # Print and compare
                        cpp_code += f"""    printf("  {name} (wide):\\n");\n"""
                        for k in range(n_words):
                            cpp_code += f"""    printf("    [{k}] expected=0x%08X, actual=0x%08X\\n", {name}_wide[{k}], top->{name}[{k}]);\n"""
                        
                        cpp_code += f"""    bool {name}_match = true;\n"""
                        for k in range(n_words):
                            cpp_code += f"""    if (top->{name}[{k}] != {name}_wide[{k}]) {name}_match = false;\n"""
                        
                        cpp_code += f"""    if (!{name}_match) {{\n"""
                        cpp_code += f"""        unpass++;\n"""
                        cpp_code += f"""        printf("  [FAIL] Mismatch at {name}\\n");\n"""
                        cpp_code += f"""    }} else {{\n"""
                        cpp_code += f"""        printf("  [PASS] {name} matched\\n");\n"""
                        cpp_code += f"""    }}\n"""
            
            cpp_code += """\n"""

        # Summary for this scenario
        cpp_code += f"""
    if (unpass == 0) {{
        std::cout << "✓ Test passed for scenario {data.get('scenario', 'unnamed')}" << std::endl;
    }} else {{
        std::cout << "✗ Test failed, unpass = " << unpass << " for scenario {data.get('scenario', 'unnamed')}" << std::endl;
        unpass_total += unpass;
    }}
    std::cout << std::endl;

"""

    # Final cleanup and return
    cpp_code += """
    // Cleanup is handled by unique_ptr automatically
    if (unpass_total == 0) {
        std::cout << "========================================" << std::endl;
        std::cout << "All tests passed!" << std::endl;
        std::cout << "========================================" << std::endl;
    } else {
        std::cout << "========================================" << std::endl;
        std::cout << "Total failures: " << unpass_total << std::endl;
        std::cout << "========================================" << std::endl;
    }
    
    return unpass_total;
}
"""
    with open("rfuzz-harness.cpp", "w") as file:
        file.write(cpp_code)


if __name__ == "__main__":
    main()
