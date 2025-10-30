"""
PyChecker Agent - Python Golden DUT Agent (Simplified Architecture)

This agent generates Python golden reference models and testbench files.
Architecture: Only __init__ and run methods.
"""

import json
import logging
import os
import subprocess
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# CMB (Combinational) Circuit Prompts
# ============================================================================

CMB_SYSTEM_PROMPT = """You are an expert in RTL design and Python programming. You can always write correct Python code to verify RTL functionality."""

CMB_GENERATION_PROMPT = r"""
You are implementing a Python class named "GoldenDUT" that realizes the functionality described in a hardware problem.

<description>
{description}
</description>

<module_header>
{module_header}
</module_header>

## Input/Output Format



Your GoldenDUT class should:
1. Initialize any internal state (if needed) in `__init__()`
2. Implement `load(self, inputs: Dict[str, str]) -> Dict[str, str]` that:
   - Takes a single test vector (dictionary of input signals)
   - Returns a dictionary of output signals
   - All values are binary strings (e.g., "0", "1", "101")

## Implementation Requirements

### 1. Initialization
```python
def __init__(self):
    # Initialize any internal state if needed
    pass
```

### 2. Load Method
```python
def load(self, inputs: Dict[str, str]) -> Dict[str, str]:
    # inputs: {"signal_name": "binary_string", ...}
    # Returns: {"output_name": "binary_string", ...}
    pass
```

## Important Notes

1. **Bit indexing**: For signals like `x[4:0]`, the string "11100" maps to:
   - x[4]=1 (leftmost/MSB)
   - x[3]=1
   - x[2]=1
   - x[1]=0
   - x[0]=0 (rightmost/LSB)

2. **Output format**: Only return '0' and '1' binary strings. No 'X', 'Z', or other values.

3. **Karnaugh Maps**: If the spec contains K-maps, remember Gray code ordering (00, 01, 11, 10).

## Example

For a simple AND gate (z = a & b):

```python
class GoldenDUT:
    def __init__(self):
        pass
    
    def load(self, inputs: Dict[str, str]) -> Dict[str, str]:
        a = int(inputs["a"])
        b = int(inputs["b"])
        z = str(a & b)
        return {"z": z}
```

Now implement the GoldenDUT class for the given specification.  Please first think carefully and provide the code of the GoldenDUT class in the format:

```python
class GoldenDUT:
    def __init__(self):
        pass
    
    def load(self, inputs: Dict[str, str]) -> Dict[str, str]:
        pass
```

"""

CMB_PythonHeader = """
import json
from typing import Dict, List, Union, Any
"""






# ============================================================================
# SEQ (Sequential) Circuit Configuration
# ============================================================================

SEQ_SYSTEM_PROMPT = """You are an expert in RTL design and Python programming. You can always write correct Python code to verify RTL functionality."""

SEQ_GENERATION_PROMPT = r"""
You are implementing a Python class named "GoldenDUT" that realizes the sequential functionality described in a hardware problem.

<description>
{description}
</description>

<module_header>
{module_header}
</module_header>

## CRITICAL: Signal Consistency Requirements

**You MUST use EXACTLY the same signal names as specified in the module_header above.**

- Input signals: Extract from module_header inputs (excluding clock signals like 'clk')
- Output signals: Extract from module_header outputs
- DO NOT add extra signals
- DO NOT omit any signals
- DO NOT rename signals

## Implementation Requirements

### 1. Initialization
```python
def __init__(self):
    # Initialize all state registers to their default values
    self.state = 0
    self.counter = 0
    # etc.
```

### 2. Load Method
```python
def load(self, clk: int, inputs: Dict[str, str]) -> Dict[str, str]:
    # clk: 1 = rising edge (0->1), 0 = falling edge (1->0)
    # inputs: {"signal_name": "binary_string", ...}
    # Returns: {"output_name": "binary_string", ...}
    
    # Handle rising edge and falling edge appropriately
    # Update state based on inputs and clock edge
    # Return current outputs
    pass
```

## Clock Edge Behavior

The `load` method will be called **TWICE per clock cycle**:

1. **Rising Edge** (clk=1): Called when clock transitions from 0 to 1
   - This is where most sequential logic updates state (e.g., flip-flops capture inputs)
   
2. **Falling Edge** (clk=0): Called when clock transitions from 1 to 0
   - Some designs may have falling-edge triggered logic
   - Most designs only update on rising edge

**Asynchronous Reset (check OUTSIDE clock edge):**
```python
def load(self, clk: int, inputs: Dict[str, str]) -> Dict[str, str]:
    aresetn = int(inputs["aresetn"], 2)
    
    # Asynchronous reset - check regardless of clock
    if aresetn == 0:  # active low
        self.state = 0
        self.output = 0
    else:
        # Normal operation on clock edge
        if clk == 1:
            # state transitions
            pass
    
    return {"output": str(self.output)}
```

**Synchronous Reset (check INSIDE clock edge):**
```python
def load(self, clk: int, inputs: Dict[str, str]) -> Dict[str, str]:
    reset = int(inputs["reset"], 2)
    
    # Synchronous reset - only check on clock edge
    if clk == 1:
        if reset == 1:  # active high
            self.state = 0
            self.output = 0
        else:
            # state transitions
            pass
    
    return {"output": str(self.output)}
```

### Mealy Machine (Output depends on BOTH current state AND current input)

**CRITICAL DIFFERENCES:**
- Output is combinational logic, NOT a register
- Output must be calculated based on CURRENT state (before transition) and CURRENT input
- Output can change immediately when input changes, without waiting for clock edge
- **NEVER store Mealy output in a register - calculate it each time**

**Example - Mealy FSM detecting "101" sequence:**
```python
class GoldenDUT:
    def __init__(self):
        self.state = 0  # States: 0=S0, 1=S1, 2=S10
        # NO self.z register! Output is combinational for Mealy
    
    def load(self, clk: int, inputs: Dict[str, str]) -> Dict[str, str]:
        aresetn = int(inputs["aresetn"], 2)
        x = int(inputs["x"], 2)
        
        # Asynchronous reset
        if aresetn == 0:
            self.state = 0
        elif clk == 1:
            # State transitions based on CURRENT state and input
            current_state = self.state
            if current_state == 0:
                self.state = 1 if x == 1 else 0
            elif current_state == 1:
                self.state = 1 if x == 1 else 2
            elif current_state == 2:
                self.state = 1 if x == 1 else 0
        
        # MEALY OUTPUT: Calculate based on CURRENT state and CURRENT input
        # Do NOT use self.state directly after update - save current_state first
        current_state = self.state
        z_output = 0
        if current_state == 2 and x == 1:  # In S10 state with input 1
            z_output = 1
        
        return {"z": str(z_output)}
```

**Common MISTAKE for Mealy machines:**
```python
# WRONG - Don't do this for Mealy!
if clk == 1:
    # ... state transitions ...
    self.z = 1 if (self.state == 2 and x == 1) else 0  # WRONG: storing in register

return {"z": str(self.z)}  # WRONG: output is registered
```

## State Machine Completeness


## Output Timing for State Machines

**When does output become valid?**

Read the description carefully:
- "Output is valid when done=1" means output only matters when done signal is high
- "Output immediately after third byte received" means output appears same cycle as state transition
- "Output on next cycle" means register the output for one cycle delay

**Example with conditional output:**
```python
# Output valid only when done=1, otherwise don't care
def load(self, clk: int, inputs: Dict[str, str]) -> Dict[str, str]:
    # ... state transitions ...
    
    if clk == 1:
        if self.state == 3:
            self.done = 1
            self.out_bytes = (self.byte1 << 16) | (self.byte2 << 8) | self.byte3
        else:
            self.done = 0
            # out_bytes doesn't matter when done=0
    
    # Return current values
    return {
        "done": str(self.done),
        "out_bytes": format(self.out_bytes, '024b') if self.done else '0'*24
    }
```

## CRITICAL: Signal Bit Width and Formatting

**Always check module_header for exact bit widths!**

From module_header, you can determine bit widths:
- `input [7:0] data` means 8 bits (from bit 7 to bit 0)
- `input x` means 1 bit
- `output [23:0] out_bytes` means 24 bits
- `output reg [15:0] counter` means 16 bits

### Reading Input Signals

**CORRECT way to read inputs:**
```python
# For multi-bit signal [7:0] in
in_val = int(inputs["in"], 2)  # "10110011" -> 179

# For single-bit signal x
x = int(inputs["x"], 2)  # "1" -> 1 or "0" -> 0

# Extract specific bit (e.g., bit 3 of in[7:0])
bit3 = (in_val >> 3) & 0x1  # Shift right 3 bits and mask
```

**NOTE: Verilog vs Python bit indexing:**
- **Verilog `[7:0]`**: Bit 7 = MSB (leftmost), Bit 0 = LSB (rightmost)
- **Python**: Use right-shift to access specific bit position
- To access **Verilog bit N**: use `(value >> N) & 0x1`

Example:
```
Verilog: in = 8'b10110011, in[3] accesses bit 3
         Bit [7][6][5][4][3][2][1][0]
             [ 1][ 0][ 1][ 1][ 0][ 0][ 1][ 1]
                            ^
                         bit 3 = 0
                         
Python:  in_val = 0b10110011 = 179
         (179 >> 3) & 0x1 = 0b00010110 & 1 = 0  ✓ Correct!
```


Now implement the GoldenDUT class for the given specification. 

Please think carefully and provide the code of the GoldenDUT class in the format:

```python
class GoldenDUT:
    def __init__(self):
        pass
    
    def load(self, clk: int, inputs: Dict[str, str]) -> Dict[str, str]:
        pass
```
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
            cycle_inputs = {sig: vals[cycle] if cycle < len(vals) else "0" for sig, vals in input_signals.items()}

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

class PyCheckerAgent:
    """
    Agent for generating testbench files with expected outputs
    Simplified architecture: only __init__ and run
    """
    
    def __init__(self, llm_client=None, max_retries: int = 3):
        """Initialize the PyChecker Agent
        
        Args:
            llm_client: LLM client for making API calls
            max_retries: Maximum number of retries on failure
        """
        self.llm_client = llm_client
        self.max_retries = max_retries
        logger.info(f"PyCheckerAgent initialized with max_retries={max_retries}")
        
    def run(
        self,
        rtl_code: str,
        specification: str,
        circuit_type: str,
        stimulus_json_path: str,
        output_dir: str
    ) -> Dict[str, Any]:
        """Generate testbench.json file

        This method:
        1. Sends LLM request with appropriate prompt based on circuit_type
        2. Gets response (Python code)
        3. Executes Python code to generate testbench.json
        4. Retries up to max_retries times on failure

        Args:
            rtl_code: RTL code
            specification: Specification description
            circuit_type: Circuit type ("cmb" or "seq")
            stimulus_json_path: Path to stimulus.json file
            output_dir: Directory to save testbench.json

        Returns:
            Dictionary with success status and paths
        """
        logger.info(f"PyCheckerAgent.run started for circuit_type={circuit_type}")

        # Load stimulus sample for prompt
        try:
            with open(stimulus_json_path, 'r') as f:
                stimulus_data = json.load(f)
                # Get first few samples for context
                stimulus_sample = json.dumps(stimulus_data[:3] if len(stimulus_data) > 3 else stimulus_data, indent=2)
        except Exception as e:
            logger.error(f"Failed to load stimulus.json: {e}")
            return {
                "success": False,
                "error": f"Failed to load stimulus.json: {e}"
            }

        # Track previous attempts for error feedback
        previous_code = None
        previous_error = None

        for attempt in range(self.max_retries):
            try:
                # Step 1: Extract module header from RTL code
                # The module header is typically the first few lines before the module body
                module_header = ""
                if rtl_code:
                    lines = rtl_code.split('\n')
                    for i, line in enumerate(lines):
                        module_header += line + '\n'
                        if ');' in line or (i > 0 and ');' in lines[i-1]):
                            break
                    module_header = module_header.strip()

                # Step 2: Prepare prompt based on circuit type
                if circuit_type.lower() == "seq":
                    system_prompt = SEQ_SYSTEM_PROMPT
                    user_prompt = SEQ_GENERATION_PROMPT.format(
                        description=specification,
                        module_header=module_header
                    )
                else:  # cmb
                    system_prompt = CMB_SYSTEM_PROMPT
                    user_prompt = CMB_GENERATION_PROMPT.format(
                        description=specification,
                        module_header=module_header
                    )

                # For retry attempts, append previous code and error information
                if attempt > 0 and previous_code and previous_error:
                    user_prompt += f"\n\n---\n\n**RETRY ATTEMPT {attempt + 1}**\n\n"
                    user_prompt += "The previous GoldenDUT code generated has errors. Please fix the issues.\n\n"
                    user_prompt += f"<previous_code>\n```python\n{previous_code}\n```\n</previous_code>\n\n"
                    user_prompt += f"<error_message>\n{previous_error}\n</error_message>\n\n"
                    user_prompt += "Please analyze the error and provide corrected GoldenDUT class code."

                # Step 2: Send LLM request
                logger.info(f"Attempt {attempt + 1}/{self.max_retries}: Sending LLM request")
                response = self._call_llm(system_prompt, user_prompt)

                if not response:
                    logger.warning(f"Attempt {attempt + 1} failed: Empty LLM response")
                    previous_error = "Empty LLM response"
                    continue

                # Step 3: Extract Python code from response
                python_code = self._extract_code(response)

                if not python_code:
                    logger.warning(f"Attempt {attempt + 1} failed: No Python code extracted")
                    previous_error = "No Python code extracted from LLM response"
                    continue

                # Step 4: Construct complete Python file
                if circuit_type.lower() == "seq":
                    complete_code = SEQ_PythonHeader + "\n\n" + python_code + "\n\n" + SEQ_CHECKER_TAIL
                else:
                    complete_code = CMB_PythonHeader + "\n\n" + python_code + "\n\n" + CMB_CHECKER_TAIL

                # Store current code for potential retry
                previous_code = python_code

                # Step 5: Save Python code to file
                golden_dut_path = os.path.join(output_dir, "golden_dut.py")

                with open(golden_dut_path, 'w') as f:
                    f.write(complete_code)

                # Step 6: Execute Python code to generate testbench.json
                logger.info(f"Executing Python code: {golden_dut_path}")
                result = subprocess.run(
                    ["python", "golden_dut.py"],
                    cwd=output_dir,
                    capture_output=True,
                    text=True,
                    timeout=60
                )

                if result.returncode != 0:
                    error_msg = f"Python execution error:\nSTDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
                    logger.warning(f"Attempt {attempt + 1} failed: {error_msg}")
                    previous_error = error_msg
                    continue

                # Step 7: Check if testbench.json was created
                testbench_json_path = os.path.join(output_dir, "testbench.json")

                if not os.path.exists(testbench_json_path):
                    logger.warning(f"Attempt {attempt + 1} failed: testbench.json not created")
                    previous_error = "testbench.json was not created after execution"
                    continue

                # Validate JSON format
                with open(testbench_json_path, 'r') as f:
                    testbench_data = json.load(f)

                # Success!
                logger.info(f"PyCheckerAgent.run succeeded on attempt {attempt + 1}")
                return {
                    "success": True,
                    "testbench_json_path": testbench_json_path,
                    "golden_dut_path": golden_dut_path,
                    "num_test_cases": len(testbench_data),
                    "attempt": attempt + 1
                }

            except subprocess.TimeoutExpired:
                error_msg = "Python execution timeout (exceeded 60 seconds)"
                logger.error(f"Attempt {attempt + 1} failed: {error_msg}")
                previous_error = error_msg
            except json.JSONDecodeError as e:
                error_msg = f"Invalid JSON format: {str(e)}"
                logger.error(f"Attempt {attempt + 1} failed: {error_msg}")
                previous_error = error_msg
            except Exception as e:
                error_msg = f"Unexpected error: {str(e)}"
                logger.error(f"Attempt {attempt + 1} failed: {error_msg}", exc_info=True)
                previous_error = error_msg

        # All retries failed
        logger.error(f"PyCheckerAgent.run failed after {self.max_retries} attempts")
        return {
            "success": False,
            "error": f"Failed after {self.max_retries} attempts",
            "testbench_json_path": None
        }
    
    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Call LLM to generate Python code
        
        Args:
            system_prompt: System prompt
            user_prompt: User prompt
            
        Returns:
            LLM response string
        """
        if self.llm_client is None:
            # Placeholder for testing
            logger.warning("No LLM client configured, returning placeholder code")
            return """```python
import json

def golden_dut(inputs):
    # Placeholder implementation
    return {"output": "0"}

if __name__ == "__main__":
    with open("stimulus.json", "r") as f:
        stimulus = json.load(f)
    
    results = []
    for test_case in stimulus:
        expected = golden_dut(test_case)
        results.append({"inputs": test_case, "expected_outputs": expected})
    
    with open("testbench.json", "w") as f:
        json.dump(results, f, indent=2)
```"""
        
        # Real LLM call
        try:
            response = self.llm_client.chat(
                system=system_prompt,
                user=user_prompt
            )
            return response
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return ""
    
    def _extract_code(self, response: str) -> str:
        """Extract Python code from LLM response
        
        Args:
            response: LLM response containing code
            
        Returns:
            Extracted Python code
        """
        import re
        
        # Try to find ```python ... ``` blocks
        pattern = r'```python\s*(.*?)\s*```'
        matches = re.findall(pattern, response, re.DOTALL)
        
        if matches:
            return matches[0].strip()
        
        # Try to find ``` ... ``` blocks
        pattern = r'```\s*(.*?)\s*```'
        matches = re.findall(pattern, response, re.DOTALL)
        
        if matches:
            return matches[0].strip()
        
        # If no code blocks found, return the whole response
        logger.warning("No code blocks found in response, using entire response")
        return response.strip()
