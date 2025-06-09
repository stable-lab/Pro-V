import json
from typing import Dict, List

from llama_index.core.base.llms.types import ChatMessage, ChatResponse, MessageRole
from utils.gen_config import get_llm
from utils.log_utils import get_logger
from utils.prompts import ORDER_PROMPT
from utils.token_counter import TokenCounter, TokenCounterCached
from pydantic import BaseModel
import utils.python_call as py
import os
logger = get_logger(__name__)


## CMB
SYSTEM_PROMPT = """
You are an expert in RTL design. You can always write SystemVerilog code with no syntax errors and always reach correct functionality. You can always generate correct testbenches for your RTL designs.
"""

GENERATION_PROMPT = """
Your task is to generate Python method named "stimulus_gen" to produce a list of Dictionary-formatted stimulus sequences for testing a given DUT (Device Under Test). If necessary, write any additional methods that may be called within the load method to organize the code and handle specific sub-tasks. The information you have is:

1. The problem description that guides student to write the RTL code (DUT)
2. The header of the "DUT"
3. The instruction for writing the testbench
4. The list of testbench scenarios description

The object of the stimulus list format should strictly follow the dictionary structure below:
{{
  "scenario": "scenario_name1",
  "input variable": [
    {{"variable_name": variable_value}},
    {{"variable_name": variable_value}},
    {{"variable_name": variable_value}}
  ]
}}

Each input variable sequence should be customized based on the given specific scenario description, typically including:

a. Typical operations
b. Edge cases and corner cases
c. Boundary conditions
d. Error handling
e. Random cases as much as possible
f. Timing verification requirements

Please follow these steps:

1. First, analyze the given test scenarios description.

2. Generate Python method named "stimulus_gen" follow the instruction:
<instruction>
{instruction}
</instruction>



Here is the information you have:
1. <problem_description>
{description}
</problem_description>

2. <module_header>
{module_header}
</module_header>



3. If spec does not have invalid input, you can generate more than 20 random test cases using python loop. It is a good way to cover all the possible cases.
Each input variable sequence should be customized based on the given specific scenario description, typically including:

a. Typical operations
b. Edge cases and corner cases
c. Boundary conditions
d. Error handling
e. Random cases (it is based on the input variable are all valid, then you can use loop to generate at least 10 cases )
f. Timing verification requirements

Please generate the testbench following the format in the example below:
<example>
{example}
</example>
"""

Instructions_for_Python_Code = """
[important]Instructions for the Python Code:
0.[Most importantly] Every variable (signal) must be represented explicitly as a binary sequence (e.g., '101001'). Only binary digits '0' and '1' are allowed; do NOT include any other characters. 
1. The output should be a list of dictionaries, each dictionary is a stimulus sequence following the format:{{
  "scenario": "scenario_name",
  "input variable": [
    {{"variable_name1": (a binary sequence string)variable_value1,
    "variable_name2": (a binary sequence string)variable_value2,
    "variable_name3": (a binary sequence string)variable_value3}},
    {{"variable_name1": (a binary sequence string)variable_value1,
    "variable_name2": (a binary sequence string)variable_value2,
    "variable_name3": (a binary sequence string)variable_value3}}

  ]}}
[important]The variable names in the "input variable" should include all the input variables in the DUT module header.
3 . Carefully read and interpret each description in the list of testbench scenarios. Write a Python method named stimulus_gen that returns a list of dictionary-formatted stimulus sequences. Ensure the length of the generated list matches exactly the number of provided testbench scenarios.
5. The stimulus_gen method can call and rely on any additional helper methods or sub-methods as needed to generate the stimulus sequences clearly and efficiently.
6. Clearly define and document any helper methods that you use.


[Some hints for combinational circuits]
0. For combinational circuits specifically:
   - Ensure each test vector specifies a complete set of input values
   - For exhaustive testing, consider generating all possible input combinations when feasible
   - For targeted testing, focus on edge cases and boundary conditions
   - Remember that unlike sequential circuits, combinational circuits have no memory or state
1. Truth Table Exploration: Consider generating stimuli that cover the entire truth table for small input spaces, or use strategic input selection for larger spaces.

2. Special Cases: Pay special attention to:
   - All zeros/all ones inputs
   - Alternating bit patterns (101010...)
   - Single bit changes (walking ones/zeros)
   - Corner cases specific to the circuit functionality

3. Techniques for Generating Binary Values in Python:
   - Integer conversion: format(42, '08b')  # '00101010'
   - Bitwise operations: format((1 << 3) | (1 << 0), '08b')  # '00001001'
   - Systematic patterns: format((2**i), f'0{width}b') for i in range(width)
4. When handling inputs containing Karnaugh maps, 01 sequences, or logic diagrams: Recognize that Karnaugh map columns often follow Gray code ordering (00, 01, 11, 10). Always convert outputs to standard binary sequence (00, 01, 10, 11) unless explicitly instructed otherwise. Example: If input columns are [00, 01, 11, 10], process/output using [00, 01, 10, 11] ordering.

Perform bitwise consistency checks for all 01 sequences: Confirm input/output bit lengths match. Verify no duplicate minterms in truth tables. Cross-check Karnaugh map groupings against standard adjacency rules.

When detecting non-standard ordering in inputs, check the order of outputs.
Remember that for combinational circuits, there is no concept of clock cycles or sequential behavior - the output is purely a function of the current inputs.

[Return Value Format]
The stimulus_gen function should either:
1. Return a JSON-formatted string directly, or
2. Return a list/dictionary that can be JSON serialized




Special Instructions for Karnaugh Map-based Circuits:

When analyzing the function from the Karnaugh map, !!!explicitly avoid generating test scenarios for input combinations marked as don't care (d or unspecified in the map). These inputs do not affect functional correctness and should not be interpreted or tested unless they are necessary for minimizing the logic expression.

!!! Focus only on input combinations with defined outputs (0 or 1). Do not describe scenarios involving ambiguous or undefined behavior from the Karnaugh map.

In test case scenario descriptions, clearly explain which variables are being controlled and ensure all variables involved are fully specified.

[Return Value Format]
The stimulus_gen function should either:
1. Return a JSON-formatted string directly, or
2. Return a list/dictionary that can be JSON serialized
The function's output will be automatically converted to a JSON string before writing to file.

[important]The variable names in the "input variable" should include all the input variables, including reset signal(rst or areset) in the DUT module header, except the clock signal(clk).

Follow these steps to create the stimulus_gen method:

1. Analyze the inputs:
   - Extract the input variable names from the DUT header
   - Identify the required scenarios from the testbench scenarios

2. Create the stimulus_gen method structure:
   - Define the method signature: def stimulus_gen()
   - Initialize an empty list to store the stimulus sequences

3. Process each scenario:
   - For each scenario in the testbench scenarios:
     a. Create a dictionary with the scenario name
     b. Create a list of input dictionaries for each set of input variables
     c. For each set of input variables:
        - Create a dictionary with "clock cycles" and input variable names as keys
        - Generate binary sequence strings for each input variable based on the number of clock cycles
     d. Add the input list to the scenario dictionary
     e. Append the scenario dictionary to the main stimulus list

4. Handle error cases and edge conditions:
   - Ensure that the number of binary sequence strings matches the specified clock cycles
   - Validate that all required input variables are present
   - Handle any potential errors gracefully

Remember to follow Python best practices, use meaningful variable names, and include comments to explain your code.

Important notes:
- Pay close attention to the functionality described in the problem description and testbench instruction.
- Ensure that your method can handle various scenarios and input combinations.
- The cycle time for each scenario is typically longer than 10 clock cycles, so plan your binary sequence generation accordingly.
- Focus more on exploring and implementing the required functionality rather than spending too much time on initial setup or probing.


6. Ensure and ensure the length of the generated list matches exactly the number of provided testbench scenarios.
7. The stimulus_gen method can call and rely on any additional helper methods or sub-methods as needed to generate the stimulus sequences clearly and efficiently.
8. Clearly define and document any helper methods that you use.
9. You must not generate testbench stimuli that are labeled as "never occur", "do not care", "not applicable", or "not required to check", etc.


[Some hints]
1. Input Variable Conformance: Ensure all input variables in the stimulus sequence strictly conform to the DUT module header definition (variable names, bit widths, data types). Clearly indicate variable types (binary, integer, etc.) and bit widths according to the DUT module header.

2 Code Clarity and Maintainability: Clearly document each step and scenario in comments.Consider edge cases involving timing and synchronization relevant to the RTL module's operation.

### 3. Techniques for Generating Binary Stimulus Strings in Python

When working with RTL simulation and verification, generating appropriate binary stimulus sequences is crucial. Here are several Python-based techniques you can use to generate such sequences efficiently:

#### 3.1. Integer-to-Binary Conversion for Functional Testing
For deterministic logic testing, you can convert integers to binary strings. This is useful when you need predictable patterns for verification.

```python
# Convert integer to binary string with zero-padding to fixed width
stimulus = format(42, '08b')  # Output: '00101010'
```

You can use this to systematically generate all combinations for a given bit width:

```python
width = 4
stimuli = [format(i, f'0{width}b') for i in range(2**width)]
```

#### 3.2. Random Binary Sequences
For more stochastic testing, Python's `random` module provides convenient tools:

```python
import random

# Generate a random 32-bit binary string
in = format(random.getrandbits(32), '032b')
```

Or, to generate a list of such random binary strings:

```python
x=16
in=format(x, '04b')   # Convert x to a 4-bit binary string
```

#### 3.3. Custom-Length Random Sequences
You can generate arbitrarily long binary strings using list comprehension and `join`:

```python
# Generate a width-bit random binary string
in = ''.join([str(random.randint(0, 1)) for _ in range(width)])
```

This approach is flexible and allows for insertion of patterns or controlled distributions.

```


```


4. Specific Recommendations for stimulus_gen Module:

Leverage Python loops (for, while) to efficiently generate repetitive or sequential test inputs. Use parameterized functions or loops to cover various input ranges and boundary conditions systematically. Ensure scalability by avoiding hard-coded scenarios; instead, use loop-driven generation for comprehensive coverage.

[Return Value Format]
The stimulus_gen function should either:
1. Return a JSON-formatted string directly, or
2. Return a list/dictionary that can be JSON serialized
The function's output will be automatically converted to a JSON string before writing to file.
"""

python_code_header = """
import json
import random
"""
EXAMPLE_OUTPUT = {
    "reasoning": "Analyze the scenario description and think how to generate the stimulus sequence",
    "input_signal_information": "input signal name, width, and data type",
    "input_signal_format": "input signal dictionary format",
    "stimulus_gen_code": "python code to generate stimulus sequence",
}
ONE_SHOT_EXAMPLE = """
Here are some examples of SystemVerilog testbench code:
Example 1:
<input_spec>
    <description>
  For the following Karnaugh map, implement the Boolean function using exactly one 4-to-1 multiplexer and as few 2-to-1 multiplexers as needed. You are not allowed to use any other logic gates. Use variables a and b as the selector inputs for the 4-to-1 multiplexer, as shown in the diagram below.

        // ab
// cd 00 01 11 10
// 00 | 1 | 0 | 1 | 1 |
// 01 | d | d | 0 | 1 |
// 11 | 1 | d | 0 | 0 |
// 10 | 1 | 0 | d | 0 |

Your task is to write RTL code to implement this function using the given constraints. All inputs (a, b, c, d) are Boolean (0 or 1), and the circuit is purely combinational.


    </description>
</input_spec>
<python_code>


def stimulus_gen():

    #Generate stimulus sequences for testing the DUT based on predefined Karnaugh-map scenarios.

    # Define the input patterns for each scenario (a, b, c, d in that order)
    # Since abcd=0000, 0101, 1111,1 110 is the don't care input, we don't need to generate it
    scenario_patterns = {
        "FIRSTVALIDINPUT": ["0000"],
        "SECONDVALIDINPUT": ["0001"],
        "THIRDVALIDINPUT": ["0010"],
        "FOURTHVALIDINPUT": ["0011"],
        "FIFTHVALIDINPUT": ["0100"],
        "SIXTHVALIDINPUT": ["0101"],
        "SEVENTHVALIDINPUT": ["0110"],
        "EIGHTHVALIDINPUT": ["0111"],
        "NINTHVALIDINPUT": ["1000"],
        "TENTHVALIDINPUT": ["1001"],
        "ELEVENTHVALIDINPUT": ["1010"],
        "TWELFTHVALIDINPUT": ["1011"],
        "THIRTEENTHVALIDINPUT": ["1100"],
        "FOURTEENTHVALIDINPUT": ["1101"],
        "FIFTEENTHVALIDINPUT": ["1110"],
        "SIXTEENTHVALIDINPUT": ["1111"],
    }

    stimuli = []
    for scenario, patterns in scenario_patterns.items():
        input_list = []
        for bits in patterns:
            # Decompose the 4-bit string into individual signals
            input_vars = {
                "a": bits[0],
                "b": bits[1],
                "c": bits[2],
                "d": bits[3]
            }
            input_list.append(input_vars)
        stimuli.append({
            "scenario": scenario,
            "input variable": input_list
        })

    return stimuli


# Example usage:
if __name__ == "__main__":
    for stimulus in stimulus_gen():
        print(stimulus)

</python_code>

Example 2:
<example>
    <input_spec>
       Implement the boolean function z = (x|y) & (~x).
    </input_spec>

    <stimulus_gen_code>
   def stimulus_gen() -> list[dict]:
    scenarios = [
        {
            "scenario": "AllZeroInputs",
            "input variable": [{"x": "0", "y": "0"}]
        },
        {
            "scenario": "AllOneInputs",
            "input variable": [{"x": "1", "y": "1"}]
        },
        {
            "scenario": "InputXOnlyHigh",
            "input variable": [{"x": "1", "y": "0"}]
        },
        {
            "scenario": "InputYOnlyHigh",
            "input variable": [{"x": "0", "y": "1"}]
        },
        {
            "scenario": "ToggleXKeepYLow",
            "input variable": [
                {"x": "0", "y": "0"},
                {"x": "1", "y": "0"},
                {"x": "0", "y": "0"},
                {"x": "1", "y": "0"}
            ]
        },
        {
            "scenario": "KeepXLowToggleY",
            "input variable": [
                {"x": "0", "y": "0"},
                {"x": "0", "y": "1"},
                {"x": "0", "y": "0"},
                {"x": "0", "y": "1"}
            ]
        },
        {
            "scenario": "ToggleXKeepYHigh",
            "input variable": [
                {"x": "0", "y": "1"},
                {"x": "1", "y": "1"},
                {"x": "0", "y": "1"},
                {"x": "1", "y": "1"}
            ]
        },
        {
            "scenario": "ComplexSequence",
            "input variable": [
                {"x": "0", "y": "0"},
                {"x": "0", "y": "1"},
                {"x": "1", "y": "0"},
                {"x": "1", "y": "1"},
                {"x": "0", "y": "1"}
            ]
        }
    ]
    return scenarios

</stimulus_gen_code>
</example>
"""
tail = """
if __name__ == "__main__":
    result = stimulus_gen()
    # Convert result to JSON string
    if isinstance(result, list):
        result = json.dumps(result, indent=4)
    elif not isinstance(result, str):
        result = json.dumps(result, indent=4)

    with open("stimulus.json", "w") as f:
        f.write(result)
"""






### SEQ
SEQ_SYSTEM_PROMPT = """
You are an expert in RTL design. You can always write SystemVerilog code with no syntax errors and always reach correct functionality. You can always generate correct testbenches for your RTL designs.
"""

SEQ_GENERATION_PROMPT = """
You are tasked with generating a Python method named "stimulus_gen" to produce a list of Dictionary-formatted stimulus sequences for testing a given Device Under Test (DUT). You will be provided with several pieces of information to help you create this method. Your goal is to analyze the inputs, create the method structure, process each scenario, handle error cases, and return the generated stimulus list.

Here is the information you'll be working with:

<instruction>
{instruction}
</instruction>



Here is the information you have:
1. <description>
{description}
</description>

2. <module_header>
{module_header}
</module_header>






Each input variable sequence should be customized based on the given specific scenario description, typically including:

a. Typical operations
b. Edge cases and corner cases
c. Boundary conditions
d. Error handling
e. Random cases (at least 10 cases you can use loop to generate)
f. Timing verification requirements

Please follow these steps:

1. First, analyze the given test scenarios description.

2. Generate Python method named "stimulus_gen" follow the instruction:



Please generate the testbench following the format in the example below:
<example>
{example}
</example>
"""


SEQ_Instructions_for_Python_Code = """
[important]Instructions for the Python Code:
0.[Most importantly] Every variable (signal) must be represented explicitly as a binary sequence (e.g., '101001'). Only binary digits '0' and '1' are allowed; do NOT include any undefined ('X') or high-impedance ('Z') states. 
[Most importantly] The length of the generated variable list mustbe equal to the clock cycles!
1. The output should be a list of dictionaries, each dictionary is a stimulus sequence following the format:

{
  "scenario": "scenarioNameNoPunctuation",
  "input variable": [
    {
      "clock cycles": "integer specifying number of clock cycles",
      "input_variable_name1":["binary_string_1","binary_string_2","binary_string_3"](a list of binary sequence strings,length is equal to the clock cycles),
      "input_variable_name2": ["binary_string_1","binary_string_2","binary_string_3"](a list of binary sequence strings,length is equal to the clock cycles),
      "input_variable_name3": ["binary_string_1","binary_string_2","binary_string_3"](a list of binary sequence strings,length is equal to the clock cycles)
    },
    {
      "clock cycles": "integer specifying number of clock cycles",
      "input_variable_name1": ["binary_string_1","binary_string_2","binary_string_3"](a list of binary sequence strings,length is equal to the clock cycles),
      "input_variable_name2": ["binary_string_1","binary_string_2","binary_string_3"](a list of binary sequence strings,length is equal to the clock cycles),
      "input_variable_name3": ["binary_string_1","binary_string_2","binary_string_3"](a list of binary sequence strings,length is equal to the clock cycles)
    }
  ]
}

[important]The variable names in the "input variable" should include all the input variables, including reset signal(rst or areset) in the DUT module header, except the clock signal(clk).

Follow these steps to create the stimulus_gen method:

1. Analyze the inputs:
   - Extract the input variable names from the DUT header
   - Identify the required scenarios from the testbench scenarios

2. Create the stimulus_gen method structure:
   - Define the method signature: def stimulus_gen()
   - Initialize an empty list to store the stimulus sequences

3. Process each scenario:
   - For each scenario in the testbench scenarios:
     a. Create a dictionary with the scenario name
     b. Create a list of input dictionaries for each set of input variables
     c. For each set of input variables:
        - Create a dictionary with "clock cycles" and input variable names as keys
        - Generate binary sequence strings for each input variable based on the number of clock cycles
     d. Add the input list to the scenario dictionary
     e. Append the scenario dictionary to the main stimulus list

4. Handle error cases and edge conditions:
   - Ensure that the number of binary sequence strings matches the specified clock cycles
   - Validate that all required input variables are present
   - Handle any potential errors gracefully

Remember to follow Python best practices, use meaningful variable names, and include comments to explain your code.

Important notes:
- Pay close attention to the functionality described in the problem description and testbench instruction.
- Ensure that your method can handle various scenarios and input combinations.
- The cycle time for each scenario is typically longer than 10 clock cycles, so plan your binary sequence generation accordingly.
- Focus more on exploring and implementing the required functionality rather than spending too much time on initial setup or probing.


6. Ensure and ensure the length of the generated list matches exactly the number of provided testbench scenarios.
7. The stimulus_gen method can call and rely on any additional helper methods or sub-methods as needed to generate the stimulus sequences clearly and efficiently.
8. Clearly define and document any helper methods that you use.
9. You must not generate testbench stimuli that are labeled as "never occur", "do not care", "not applicable", or "not required to check", etc.


[Some hints]
1. Input Variable Conformance: Ensure all input variables in the stimulus sequence strictly conform to the DUT module header definition (variable names, bit widths, data types). Clearly indicate variable types (binary, integer, etc.) and bit widths according to the DUT module header.

2 Code Clarity and Maintainability: Clearly document each step and scenario in comments.Consider edge cases involving timing and synchronization relevant to the RTL module's operation.

### 3. Techniques for Generating Binary Stimulus Strings in Python

When working with RTL simulation and verification, generating appropriate binary stimulus sequences is crucial. Here are several Python-based techniques you can use to generate such sequences efficiently:

#### 3.1. Integer-to-Binary Conversion for Functional Testing
For deterministic logic testing, you can convert integers to binary strings. This is useful when you need predictable patterns for verification.

```python
# Convert integer to binary string with zero-padding to fixed width
stimulus = format(42, '08b')  # Output: '00101010'
```

You can use this to systematically generate all combinations for a given bit width:

```python
width = 4
stimuli = [format(i, f'0{width}b') for i in range(2**width)]
```

#### 3.2. Random Binary Sequences
For more stochastic testing, Python's `random` module provides convenient tools:

```python
import random

# Generate a random 32-bit binary string
in = format(random.getrandbits(32), '032b')
```

Or, to generate a list of such random binary strings:

```python
x=16
in=format(x, '04b')   # Convert x to a 4-bit binary string
```

#### 3.3. Custom-Length Random Sequences
You can generate arbitrarily long binary strings using list comprehension and `join`:

```python
# Generate a 1000-bit random binary string
in = ''.join([str(random.randint(0, 1)) for _ in range(1000)])
```

This approach is flexible and allows for insertion of patterns or controlled distributions.

```


```


4. Specific Recommendations for stimulus_gen Module:

Leverage Python loops (for, while) to efficiently generate repetitive or sequential test inputs. Use parameterized functions or loops to cover various input ranges and boundary conditions systematically. Ensure scalability by avoiding hard-coded scenarios; instead, use loop-driven generation for comprehensive coverage.

[Return Value Format]
The stimulus_gen function should either:
1. Return a JSON-formatted string directly, or
2. Return a list/dictionary that can be JSON serialized
The function's output will be automatically converted to a JSON string before writing to file.
"""

SEQ_python_code_header = """
import json
import random
"""
SEQ_EXAMPLE_OUTPUT = {
    "reasoning": "Analyze the scenario description and think how to generate the stimulus sequence",
    "stimulus_gen_code": "python code to generate stimulus sequence",
}


SEQ_ONE_SHOT_EXAMPLE = """
Here are some examples of SystemVerilog testbench code:
Example 1:
<example>
    <input_spec>
        Design a 4‑bit synchronous binary up‑counter with an asynchronous active‑high reset.

Functional requirements  
• On each rising edge of clk, if en = 1, the counter increments by 1 (mod 16).  
• If en = 0 the counter holds its current value.  
• Whenever rst = 1, the counter resets to 0000 on the very next clock edge, regardless of en.  
• A carry output asserts high for exactly one cycle whenever the counter wraps from 1111 to 0000.  
Timing assumptions  
• clk is free‑running; rst may change asynchronously but will be de‑asserted synchronously.  
• All inputs are stable for the entire high half‑cycle of clk.
    </input_spec>
    <dut_header>
module up_counter_4bit (
    input  wire clk,   // system clock, rising‑edge sensitive
    input  wire rst,   // asynchronous active‑high reset
    input  wire en,    // synchronous enable
    output reg  [3:0] count, // current count value
    output wire carry         // one‑cycle wrap‑around pulse
);
</dut_header>

    <stimulus_gen_code>
    import json
    import random

import random

def stimulus_gen():
    
    stim_list = []  # Final list of test scenarios

    # ---------- 1. Functional test scenarios ----------------------------------

    # Scenario: Continuous counting with enable high for 20 clock cycles
    stim_list.append({
        "scenario": "NormalCounting",
        "input variable": [
            {
                "clock cycles": 20,
                "rst": ["0"] * 20,     # No reset
                "en" : ["1"] * 20      # Always enabled
            }
        ]
    })

    # Scenario: Enable is low, counter should hold value
    stim_list.append({
        "scenario": "HoldWhenDisabled",
        "input variable": [
            {
                "clock cycles": 12,
                "rst": ["0"] * 12,
                "en" : ["0"] * 12
            }
        ]
    })

    # ---------- 2. Edge and timing-sensitive scenarios ------------------------

    # Scenario: Asynchronous reset pulse while enabled
    before, pulse, after = 5, 1, 14
    stim_list.append({
        "scenario": "AsynchronousResetWhileEnabled",
        "input variable": [
            { "clock cycles": before, "rst": ["0"*before], "en": ["1"*before] },
            { "clock cycles": pulse,  "rst": ["1"*pulse],  "en": ["1"*pulse] },
            { "clock cycles": after,  "rst": ["0"*after],  "en": ["1"*after] }
        ]
    })

    # Scenario: Reset immediately after a carry occurs
    seg = lambda n, rst_bit, en_bit: {
        "clock cycles": n,
        "rst": [rst_bit] * n,
        "en" : [en_bit] * n
    }
    stim_list.append({
        "scenario": "ResetImmediatelyAfterWrap",
        "input variable": [
            seg(16, "0", "1"),   # Count from 0000 to 1111 (carry occurs)
            seg( 1, "0", "1"),   # Wraps to 0000
            seg( 1, "1", "1"),   # Reset asserted
            seg(12, "0", "1")    # Continue normal counting
        ]
    })

    # ---------- 3. Randomized test scenarios ----------------------------------

    # Generate 20 randomized sequences for broader test coverage
    for idx in range(20):
        clock_cycles = random.randint(16, 32)

        # Random enable sequence with at least one '1'
        en_seq = [random.choice("01") for _ in range(clock_cycles)]
        if "1" not in en_seq:
            en_seq = en_seq[:-1] + "1"  # Ensure at least one '1'

        # Random reset pulses injected
        rst_seq=[]
        rst_bits = ["0"] * clock_cycles
        pulse_cnt = random.randint(1, max(1, clock_cycles // 8))
        while pulse_cnt > 0:
            pos = random.randrange(clock_cycles)
            rst_bits[pos] = "1"
            if pos + 1 < clock_cycles and random.random() < 0.5:
                rst_bits[pos + 1] = "1"  # Optional 2-cycle pulse
            pulse_cnt -= 1
        rst_seq.extend(rst_bits)

        # Append the random scenario
        stim_list.append({
            "scenario": f"RandomScenario{idx}",
            "input variable": [
                {
                    "clock cycles": clock_cycles,
                    "rst": rst_seq,
                    "en" : en_seq
                }
            ]
        })

    # ---------- 4. Return the complete stimulus list --------------------------

    return stim_list

</stimulus_gen_code>
</example>
"""

SEQ_tail = """
if __name__ == "__main__":
    result = stimulus_gen()
    # Convert result to JSON string
    if isinstance(result, list):
        result = json.dumps(result, indent=4)
    elif not isinstance(result, str):
        result = json.dumps(result, indent=4)

    with open("stimulus.json", "w") as f:
        f.write(result)
"""


class TBOutputFormat(BaseModel):
    reasoning: str
    stimulus_gen_code: str


class TB_Generator:
    def __init__(
        self,
        model: str,
        max_token: int,
        provider: str,
        cfg_path: str,
        dir_path: str,
        temperature: float,
        top_p: float,
    ):
        self.model = model
        self.llm = get_llm(
            model=model,
            max_token=max_token,
            provider=provider,
            cfg_path=cfg_path,
            temperature=temperature,
            top_p=top_p,
        )
        self.token_counter = (
            TokenCounterCached(self.llm)
            if TokenCounterCached.is_cache_enabled(self.llm)
            else TokenCounter(self.llm)
        )

        self.dir_path = dir_path

    def parse_output(self, response: ChatResponse) -> TBOutputFormat:
        try:
            output_json_obj: Dict = json.loads(response.message.content, strict=False)
            print(output_json_obj)
            ret = TBOutputFormat(
                reasoning=output_json_obj["reasoning"],
                stimulus_gen_code=output_json_obj["stimulus_gen_code"],
            )
            return ret
        except json.decoder.JSONDecodeError:
            return TBOutputFormat(reasoning="", stimulus_gen_code="")

    def generate(self, messages: List[ChatMessage]) -> ChatResponse:
        logger.info(f" input message: {messages}")
        resp, token_cnt = self.token_counter.count_chat(messages)
        logger.info(f"Token count: {token_cnt}")
        logger.info(f"{resp.message.content}")
        return resp

    def run(
        self,
        input_spec: str,
        header: str,
        circuit_type: str = "SEQ",
        stimuli_sampling_size: int = 1,
    ) -> str:
        stimulus_result=[]
        for i in range(stimuli_sampling_size):
            if circuit_type == "SEQ":
                msg = [
                    ChatMessage(content=SEQ_SYSTEM_PROMPT, role=MessageRole.SYSTEM),
                    ChatMessage(
                    content=SEQ_GENERATION_PROMPT.format(
                        description=input_spec,
                        module_header=header,
                        example=SEQ_ONE_SHOT_EXAMPLE,
                        instruction=SEQ_Instructions_for_Python_Code,
                       
                    ),
                    role=MessageRole.USER,
                ),
            ]
            
                msg.append(
                    ChatMessage(
                        content=ORDER_PROMPT.format(
                            output_format="".join(json.dumps(SEQ_EXAMPLE_OUTPUT, indent=4))
                        ),
                        role=MessageRole.USER,
                    )
                )

                response = self.generate(msg)
            # Ensure necessary imports are added before generating code
                stimulus_py_code = (
                SEQ_python_code_header+ "\n" + self.parse_output(response).stimulus_gen_code + SEQ_tail
            )
            
            else:
                msg = [
                    ChatMessage(content=SYSTEM_PROMPT, role=MessageRole.SYSTEM),
                    ChatMessage(content=GENERATION_PROMPT.format(
                        description=input_spec,
                        module_header=header,   
                        example=ONE_SHOT_EXAMPLE,
                        instruction=Instructions_for_Python_Code
                       
                    ),
                    role=MessageRole.USER,
                ),
            ]   
                msg.append(
                    ChatMessage(
                        content=ORDER_PROMPT.format(
                            output_format="".join(json.dumps(EXAMPLE_OUTPUT, indent=4))
                        ),
                        role=MessageRole.USER,
                    )
                )
                response = self.generate(msg)
            
                
            # Ensure necessary imports are added before generating code
                stimulus_py_code = (
                python_code_header+ "\n" + self.parse_output(response).stimulus_gen_code + tail
            )
            print(f"Response: {response.message.content}")
            sampling_stimulus_python_path = self.dir_path+f"/stimulus.py"
            print(f"stimulus_py_code: {stimulus_py_code}")
            with open(sampling_stimulus_python_path, "w") as f:
                f.write(stimulus_py_code)
            py.python_call_and_save(
                f"{sampling_stimulus_python_path}", silent=True
            )
            with open(sampling_stimulus_python_path.replace(".py", ".json"), "r") as f:
                stimulus_result= stimulus_result+json.load(f)
            
        with open(self.dir_path+"/stimulus.json", "w") as f:
            json.dump(stimulus_result, f, indent=4)
        logger.info(f"Get response from {self.model}: {response}")
        return stimulus_result
