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
#include <sstream>

int fuzz_poke() {
    int unpass_total = 0;
    int unpass = 0;
    VerilatedContext* contextp;
    Vtop_module* top;

"""

    # Handle large value signal declarations
    if datas and datas[0]["input variable"] and datas[0]["output variable"]:
        for name, value in datas[0]["input variable"][0].items():
            if isinstance(value, str) and len(value) > 64:
                
                width = len(value)
                n_words = (width + 31) // 32
                cpp_code += (
                    f"""    VlWide<{n_words}> {name}_wide;\n"""
                )
        print("datas", datas[0]["output variable"][0])

        for name, value in datas[0]["output variable"][0].items():
            
            check_out="printf(\"output_vars:\\n\");\n"
            if isinstance(value, str) and len(str(value)) > 64:
                
                cpp_code += (
                    f"""    VlWide<{int(((len(value)/4) + 7) // 8)}> {name}_wide;\n"""
                )
                
                for i in range(int(((len(value)/4) + 7) // 8)):
                    check_out+=f"printf(\"expected %x\\n\",{name}_wide[{i}]);\n"
                    check_out+=f"printf(\"actual %x\\n\",top->{name}[{i}]);\n"
            else:
                check_out=f"printf(\"%x\\n\",top->{name});\n"
    context_idx = 0
    # Generate test logic
    for data in datas:
        stimulus = data["input variable"]
        expected = data["output variable"]

        cpp_code += f"""    // Scenario: {data.get('scenario', 'unnamed')}\n"""
        cpp_code += f"""        unpass = 0;\n"""

        for i, input_step in enumerate(stimulus):
            print("input", i,input_step)
            cpp_code += """    const std::unique_ptr<VerilatedContext> contextp_%d {new VerilatedContext};\n""" % (context_idx)
            test="""    contextp = contextp_%d.get();\n""" % (context_idx)
            
            cpp_code += test
            cpp_code += f"""    top = new Vtop_module;\n"""
            
            context_idx = context_idx + 1
            check=f"printf(\"===Scenario: {data.get('scenario', 'unnamed')}=====\\n\");\n"
            for name, value in input_step.items():
                
                check+= """printf("input_vars:\\n");\n"""
        
                check += f"""printf("top->%s = 0x%s\\n", "{name}", "{value}");\n"""
                check += "\n"
                if isinstance(value, str):
                    hex_value = hex(int(str(value), 2))[2:]
                    if len(str(value)) <= 64:
                        cpp_code += f"""    top->{name} = 0x{hex_value};\n"""
                    else:
                        width = len(str(value))
                        n_words = (width + 31) // 32
                        # Pad value to make its length a multiple of 32 (pad with leading zeros)
                        padded = str(value).zfill(n_words * 32)

                        # Split into 32-bit chunks, arranged from high to low bits
                        chunks = [
        int(padded[-32 * (j + 1): -32 * j or None], 2)
        for j in range(n_words)
    ]
                        for j, c in enumerate(chunks):
                            cpp_code+= f"{name}_wide[{j}] = 0x{c:08X}u;\n"
                            cpp_code += f""" top->{name}[{j}]  = {name}_wide[{j}];\n"""

                        
                        
                     

            cpp_code += """    top->eval();\n"""
            #check=""
            print("expected", expected,i)
            for name, value in expected[i].items():
                
                if isinstance(value, str):
                    hex_value = hex(int(str(value), 2))[2:]
                    if len(value) <= 64:
                            cpp_code += f"""    if (top->{name} != 0x{hex_value}) {{
        unpass++;\n""" + check + check_out + f"""
        printf("Mismatch at %s: expected 0x%s\\n", "{name}", "{hex_value}");
    }}\n"""
                    else:
                            cpp_code += f"""    // Checking wide signal {name}\n"""
                            width = len(value)
                            n_words = (width + 31) // 32
                            # Pad value to make its length a multiple of 32 (pad with leading zeros)
                            padded = value.zfill(n_words * 32)

                            # Split into 32-bit chunks, arranged from high to low bits
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
        unpass++\n;""" + check + check_out + f"""
        printf("Mismatch at %s: expected 0x%s\\n", "{name}", "{hex_value}");
    }}\n"""

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
