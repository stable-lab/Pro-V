CMB_SYSTEM_PROMPT = """You are an expert in RTL design and Python programming. You can always write correct Python code to verify RTL functionality."""

# =============================================================================
# Generation Prompt for Combinational Circuits (Detailed for API calls)
# =============================================================================
# Purpose: This prompt is sent to the LLM API during INFERENCE to generate outputs.
# Contains: Detailed instructions with golden RTL code for better generation.
# Use when: Calling the LLM API to maximize generation quality.
# Storage: NOT stored in training dataset (includes golden RTL).
# =============================================================================
CMB_GENERATION_PROMPT = r"""
You are implementing a Python class "GoldenDUT" for combinational logic.

<description>
{description}
</description>

<module_header>
{module_header}
</module_header>

The <dut> below is the RTL code of the DUT.
<dut>
{golden_rtl}
</dut>

Your task: Write equivalent Python code that realizes the SAME functionality as the golden RTL above.

## CRITICAL Rules

1. **Signal Names**: Use EXACT names from module_header - DO NOT invent names
2. **Bit Widths**: `[m:n]` → width = m-n+1, no range → 1 bit
3. **Output Format**: ONLY return '0' and '1' binary strings - NEVER 'X', 'Z', 'd', or any other characters
4. **Masking**: ALWAYS mask outputs: `result & ((1 << width) - 1)` before returning
5. **Formatting**: Multi-bit outputs must use: `format(result, f'0{{{{width}}}}b')`
6. **Complete Implementation**: NO placeholders, NO "TODO", analyze the RTL to understand the logic

## Common Operations

- Parse input: `data = int(inputs["data"], 2)`
- NOT: `(~a) & mask`
- Shift: `(a << n) & mask`, `a >> n`
- Concat: `(upper << lower_width) | lower`
- Slice: `(data >> start_bit) & ((1 << num_bits) - 1)`
- K-map: Use Gray code (00, 01, 11, 10)

## Output Format

```
<think>
1. Analyze the golden RTL to understand the logic
2. Extract signal names and widths from module_header
3. Plan Python implementation with proper masking
</think>

```python
class GoldenDUT:
    def __init__(self):
        pass
    
    def load(self, inputs: Dict[str, str]) -> Dict[str, str]:
        # Implementation
        pass
```
```

**REMEMBER**: Output ONLY binary strings with '0' and '1' - NEVER return 'X', 'Z', or other values!
"""

# =============================================================================
# SFT Training Prompt for Combinational Circuits (Simplified for Dataset)
# =============================================================================
# Purpose: This prompt is stored in the SFT training DATASET and used for testing.
# Contains: Simple, concise instructions without golden RTL.
# Use when: Storing data for model training or testing model capabilities.
# Storage: YES - this is what goes into the training dataset.
# =============================================================================
CMB_SFT_TRAINING_PROMPT = r"""
You are implementing a Python class "GoldenDUT" for combinational logic.

<description>
{description}
</description>

<module_header>
{module_header}
</module_header>

## Requirements

1. Use EXACT signal names from module_header
2. Bit widths: `[m:n]` → width = m-n+1, no range → 1 bit
3. Output ONLY '0' and '1' binary strings - NEVER 'X', 'Z', 'd'
4. Always mask outputs: `result & ((1 << width) - 1)`
5. Multi-bit format: `format(result, f'0{{{{width}}}}b')`

## Implementation

```python
class GoldenDUT:
    def __init__(self):
        pass
    
    def load(self, inputs: Dict[str, str]) -> Dict[str, str]:
        # Parse inputs: data = int(inputs["data"], 2)
        # Return: {{"out": str(result)}} or {{"out": format(result, f'0{{width}}b')}}
        pass
```

**REMEMBER**: Output ONLY binary strings with '0' and '1'!
"""

CMB_PythonHeader = """
import json
from typing import Dict, List, Union, Any
"""






# ============================================================================
# SEQ (Sequential) Circuit Configuration
# ============================================================================

SEQ_SYSTEM_PROMPT = """You are an expert in RTL design and Python programming. You can always write correct Python code to verify RTL functionality."""

# =============================================================================
# Generation Prompt for Sequential Circuits (Detailed for API calls)
# =============================================================================
# Purpose: This prompt is sent to the LLM API during INFERENCE to generate outputs.
# Contains: Detailed instructions with golden RTL code for better generation.
# Use when: Calling the LLM API to maximize generation quality.
# Storage: NOT stored in training dataset (includes golden RTL).
# =============================================================================
SEQ_GENERATION_PROMPT = r"""
You are implementing a Python class "GoldenDUT" for sequential logic.

<description>
{description}
</description>

<module_header>
{module_header}
</module_header>

<golden_rtl>
{golden_rtl}
</golden_rtl>

Your task: Write equivalent Python code that realizes the SAME functionality as the golden RTL above.

## CRITICAL Rules

1. **Signal Names**: Use EXACT names from module_header (exclude 'clk') - DO NOT invent names
2. **Bit Widths**: `[m:n]` → width = m-n+1, no range → 1 bit
3. **Output Format**: ONLY return '0' and '1' binary strings - NEVER 'X', 'Z', 'd', or any other characters
4. **Masking**: ALWAYS mask outputs: `result & ((1 << width) - 1)` before returning
5. **Formatting**: Multi-bit outputs must use: `format(result, f'0{{{{width}}}}b')`
6. **Complete Implementation**: NO placeholders, NO "TODO", analyze the RTL to understand the logic
7. **State Updates**: ONLY update state when `clk == 1` (rising edge)

## Sequential Logic Basics

**Initialize state in `__init__`**:
```python
def __init__(self):
    self.state = 0  # Initialize ALL registers to 0
```

**Reset handling**:
- Async reset: Check before `if clk == 1`
- Sync reset: Check inside `if clk == 1`

**Moore vs Mealy**:
- Moore: Output depends ONLY on state → register output
- Mealy: Output depends on state AND input → NO output register, calculate combinationally

## Common Operations

- Counter: `self.count = (self.count + 1) & ((1 << width) - 1)`
- Shift register: `self.reg = ((self.reg << 1) | data_in) & mask`
- Parse input: `data = int(inputs["data"], 2)`

## Output Format

```
<think>
1. Analyze the golden RTL to understand the sequential logic
2. Extract signal names and widths from module_header
3. Identify FSM type (Moore/Mealy) or logic type and plan state variables
</think>

```python
class GoldenDUT:
    def __init__(self):
        pass
    
    def load(self, clk: int, inputs: Dict[str, str]) -> Dict[str, str]:
        # Implementation
        pass
```
```

**REMEMBER**: Output ONLY binary strings with '0' and '1' - NEVER return 'X', 'Z', or other values!
"""

# =============================================================================
# SFT Training Prompt for Sequential Circuits (Simplified for Dataset)
# =============================================================================
# Purpose: This prompt is stored in the SFT training DATASET and used for testing.
# Contains: Simple, concise instructions without golden RTL.
# Use when: Storing data for model training or testing model capabilities.
# Storage: YES - this is what goes into the training dataset.
# =============================================================================
SEQ_SFT_TRAINING_PROMPT = r"""
You are implementing a Python class "GoldenDUT" for sequential logic.

<description>
{description}
</description>

<module_header>
{module_header}
</module_header>

## Requirements

1. Use EXACT signal names from module_header (exclude 'clk')
2. Bit widths: `[m:n]` → width = m-n+1, no range → 1 bit
3. Output ONLY '0' and '1' binary strings - NEVER 'X', 'Z', 'd'
4. Always mask outputs: `result & ((1 << width) - 1)`
5. Multi-bit format: `format(result, f'0{{{{width}}}}b')`
6. Update state ONLY when `clk == 1` (rising edge)

## Implementation

```python
class GoldenDUT:
    def __init__(self):
        # Initialize state variables to 0
        pass
    
    def load(self, clk: int, inputs: Dict[str, str]) -> Dict[str, str]:
        # Parse inputs: data = int(inputs["data"], 2)
        # Update state on clk == 1
        # Return: {{"out": str(result)}} or {{"out": format(result, f'0{{width}}b')}}
        pass
```

**REMEMBER**: Output ONLY binary strings with '0' and '1'!
"""

SEQ_PythonHeader = """
import json
from typing import Dict, List, Union

"""
CMB_CHECKER_TAIL = """
if __name__ == "__main__":
    import os
    import sys

    # Check if stimulus.json exists
    if not os.path.exists("stimulus.json"):
        print("Error: stimulus.json not found in current directory")
        print(f"Current directory: {os.getcwd()}")
        print(f"Files in current directory: {os.listdir('.')}")
        sys.exit(1)

    with open("stimulus.json", "r") as f:
        test_vectors = json.load(f)

    dut = GoldenDUT()
    testbench = []

    for test_vector in test_vectors:
        try:
            output = dut.load(test_vector)
            testbench.append({
                "inputs": test_vector,
                "expected_outputs": output
            })
        except Exception as e:
            print(f"Error in test vector: {e}")
            testbench.append({
                "inputs": test_vector,
                "expected_outputs": {}
            })

    with open("testbench.json", "w") as f:
        json.dump(testbench, f, indent=2)

    print("Testbench generation successful")
"""

SEQ_CHECKER_TAIL = """
if __name__ == "__main__":
    import os
    import sys

    # Check if stimulus.json exists
    if not os.path.exists("stimulus.json"):
        print("Error: stimulus.json not found in current directory")
        print(f"Current directory: {os.getcwd()}")
        print(f"Files in current directory: {os.listdir('.')}")
        sys.exit(1)

    with open("stimulus.json", "r") as f:
        test_scenarios = json.load(f)

    testbench = []

    for scenario in test_scenarios:
        dut = GoldenDUT()

        clock_cycles = scenario.get("clock_cycles", 0)
        input_signals = {k: v for k, v in scenario.items() if k != "clock_cycles"}

        scenario_outputs = []
        for cycle in range(clock_cycles):
            cycle_inputs = {sig: vals[cycle] for sig, vals in input_signals.items()}

            cycle_output = {}
            try:
                rising_output = dut.load(1, cycle_inputs)
                cycle_output["rising_edge"] = rising_output
            except Exception as e:
                print(f"Error in rising edge cycle {cycle}: {e}")
                cycle_output["rising_edge"] = {}

            try:
                falling_output = dut.load(0, cycle_inputs)
                cycle_output["falling_edge"] = falling_output
            except Exception as e:
                print(f"Error in falling edge cycle {cycle}: {e}")
                cycle_output["falling_edge"] = {}

            scenario_outputs.append(cycle_output)

        test_case = {"clock_cycles": clock_cycles}
        for sig_name, sig_values in input_signals.items():
            test_case[sig_name] = sig_values
        test_case["expected_outputs"] = scenario_outputs
        testbench.append(test_case)

    with open("testbench.json", "w") as f:
        json.dump(testbench, f, indent=2)

    print("Testbench generation successful")
"""

PythonHeader = """
import json
from typing import Dict, List, Union

"""

# ============================================================================
# Prompt Selection Helper Functions
# ============================================================================

def get_prompt_for_mode(circuit_type: str, mode: str = "test") -> tuple:
    """
    Get the appropriate system and generation prompts based on circuit type and mode.

    Args:
        circuit_type: "CMB" for combinational or "SEQ" for sequential circuits
        mode: "api" or "generation" for detailed prompts with golden RTL (for API calls),
              "sft_training" or "test" for simpler prompts (for training dataset and testing)

    Returns:
        Tuple of (system_prompt, generation_prompt)

    Examples:
        # For API calls - detailed prompts with golden RTL
        sys_prompt, gen_prompt = get_prompt_for_mode("SEQ", mode="api")
        
        # For SFT training dataset - simpler prompts without golden RTL
        sys_prompt, gen_prompt = get_prompt_for_mode("SEQ", mode="sft_training")

        # For testing - simpler prompts
        sys_prompt, gen_prompt = get_prompt_for_mode("SEQ", mode="test")
    """
    if circuit_type == "CMB":
        if mode in ["api", "generation"]:
            # Use detailed GENERATION_PROMPT with golden RTL for API calls
            return CMB_SYSTEM_PROMPT, CMB_GENERATION_PROMPT
        else:  # mode in ["sft_training", "test", "collect"]
            # Use simple SFT_TRAINING_PROMPT for training data and testing
            return CMB_SYSTEM_PROMPT, CMB_SFT_TRAINING_PROMPT
    else:  # SEQ
        if mode in ["api", "generation"]:
            # Use detailed GENERATION_PROMPT with golden RTL for API calls
            return SEQ_SYSTEM_PROMPT, SEQ_GENERATION_PROMPT
        else:  # mode in ["sft_training", "test", "collect"]
            # Use simple SFT_TRAINING_PROMPT for training data and testing
            return SEQ_SYSTEM_PROMPT, SEQ_SFT_TRAINING_PROMPT


def format_prompt(description: str, module_header: str, circuit_type: str = "CMB", mode: str = "test", golden_rtl: str = "") -> str:
    """
    Format a complete prompt for Python GoldenDUT generation.

    Args:
        description: Problem description/specification
        module_header: Verilog module header
        circuit_type: "CMB" or "SEQ"
        mode: "sft_training" or "test"/"collect"
        golden_rtl: Golden RTL code (optional, used in sft_training mode)

    Returns:
        Formatted prompt string ready for LLM
    """
    system_prompt, generation_prompt = get_prompt_for_mode(circuit_type, mode)

    # Check if the prompt template expects golden_rtl parameter
    if '{golden_rtl}' in generation_prompt:
        formatted_generation = generation_prompt.format(
            description=description,
            module_header=module_header,
            golden_rtl=golden_rtl
        )
    else:
        # For prompts without golden_rtl (like GENERATION_PROMPT)
        formatted_generation = generation_prompt.format(
            description=description,
            module_header=module_header
        )

    return f"{system_prompt}\n\n{formatted_generation}"

