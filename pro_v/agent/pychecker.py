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

try:
    import ray
    RAY_AVAILABLE = True
except ImportError:
    RAY_AVAILABLE = False
    ray = None

logger = logging.getLogger(__name__)


# ============================================================================
# CMB (Combinational) Circuit Prompts
# ============================================================================

CMB_SYSTEM_PROMPT = """You are an expert in RTL design and Python programming. You can always write correct Python code to verify RTL functionality."""

CMB_GENERATION_PROMPT =  r"""
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
import re
import random
import subprocess
import os
from typing import Dict, List, Union, Any

def extract_module_ports_with_yosys(verilog_file="module_code.v"):
    \"\"\"
    Use yosys to extract module port information (inputs/outputs with widths).
    Returns a dict with 'inputs' and 'outputs', each containing {port_name: width}.
    \"\"\"
    try:
        # Create a temporary yosys script
        yosys_script = f\"\"\"
read_verilog {verilog_file}
hierarchy -check
proc
opt_clean
write_json ports.json
\"\"\"
        with open("extract_ports.ys", "w") as f:
            f.write(yosys_script)

        # Run yosys
        result = subprocess.run(
            ["yosys", "-s", "extract_ports.ys"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            print(f"Yosys extraction failed: {result.stderr}")
            return None

        # Parse the JSON output
        with open("ports.json", "r") as f:
            yosys_data = json.load(f)

        # Extract port information from the first module
        module_name = list(yosys_data["modules"].keys())[0]
        module_data = yosys_data["modules"][module_name]

        ports = {"inputs": {}, "outputs": {}}

        for port_name, port_info in module_data["ports"].items():
            direction = port_info["direction"]
            bits = port_info["bits"]
            width = len(bits)

            port_name_lower = port_name.lower()
            # Skip ONLY clock signals - reset signals should be included!
            if any(keyword in port_name_lower for keyword in ["clk", "clock"]):
                continue

            if direction == "input":
                ports["inputs"][port_name] = width
            elif direction == "output":
                ports["outputs"][port_name] = width

        return ports
    except Exception as e:
        print(f"Error extracting ports with yosys: {e}")
        return None

def generate_random_stimulus(ports_info, num_vectors=10):
    \"\"\"
    Generate random stimulus based on port information.
    Returns a list of test vectors (for combinational) or scenarios (for sequential).
    \"\"\"
    test_vectors = []

    for _ in range(num_vectors):
        vector = {}
        for port_name, width in ports_info["inputs"].items():
            # Generate random binary string of specified width
            random_value = random.randint(0, (1 << width) - 1)
            vector[port_name] = format(random_value, f'0{width}b')
        test_vectors.append(vector)

    return test_vectors

def verify_and_fix_stimulus(stimulus_data, verilog_file="module_code.v"):
    \"\"\"
    Verify stimulus.json matches module ports. If not, generate new stimulus.
    Returns the verified/corrected stimulus data.
    \"\"\"
    # Extract port information using yosys
    ports_info = extract_module_ports_with_yosys(verilog_file)

    if ports_info is None:
        print("Warning: Could not extract port information with yosys, using original stimulus")
        return stimulus_data

    # Get expected input port names (excluding clock/reset)
    expected_inputs = set(ports_info["inputs"].keys())

    if len(stimulus_data) == 0:
        print("Warning: stimulus.json is empty, generating random stimulus")
        return generate_random_stimulus(ports_info)

    # Check if stimulus keys match expected inputs
    actual_inputs = set(stimulus_data[0].keys()) - {"clock_cycles"}  # For sequential circuits

    if expected_inputs != actual_inputs:
        print(f"Mismatch detected!")
        print(f"Expected inputs from module: {sorted(expected_inputs)}")
        print(f"Actual inputs from stimulus.json: {sorted(actual_inputs)}")
        print(f"Generating new random stimulus based on module ports...")

        return generate_random_stimulus(ports_info, num_vectors=len(stimulus_data))
    else:
        print(f"Stimulus verification passed. All ports match: {sorted(expected_inputs)}")
        return stimulus_data
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

    # Load stimulus.json
    with open("stimulus.json", "r") as f:
        test_vectors = json.load(f)

    # Verify and fix stimulus if needed (using yosys)
    print("\\n=== Verifying stimulus against module ports ===")
    test_vectors = verify_and_fix_stimulus(test_vectors, verilog_file="module_code.v")
    print("==============================================\\n")

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

    # Load stimulus.json
    with open("stimulus.json", "r") as f:
        test_scenarios = json.load(f)

    # Verify and fix stimulus if needed (using yosys)
    print("\\n=== Verifying stimulus against module ports ===")
    test_scenarios = verify_and_fix_stimulus_seq(test_scenarios, verilog_file="module_code.v")
    print("==============================================\\n")

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


# ============================================================================
# SEQ (Sequential) Circuit Configuration
# ============================================================================

SEQ_SYSTEM_PROMPT = """You are an expert in RTL design and Python programming. You can always write correct Python code to verify RTL functionality."""

SEQ_GENERATION_PROMPT = r"""

You are implementing a Python class "GoldenDUT" for sequential logic.

<description>
{description}
</description>

<module_header>
{module_header}
</module_header>

## CRITICAL REQUIREMENTS

**1. EXACT Signal Names from module_header**:
   - Use ONLY the signal names that appear in module_header (exclude 'clk')
   - ✓ CORRECT: If module has "reset", use inputs["reset"]
   - ✓ CORRECT: If module has "areset", use inputs["areset"]
   - ✓ CORRECT: If module has "resetn", use inputs["resetn"]
   - ❌ WRONG: If module has "reset", do NOT use inputs["rst"] or inputs["areset"]
   - Do NOT access signals that don't exist in module_header

**2. Input/Output Signal Handling**:
   - inputs parameter contains INPUT signals (excluding 'clk')
   - Return dict should contain ONLY OUTPUT signals
   - Do NOT include input signals in return dict

**3. Bit Widths and Format**:
   - `[m:n]` → width = m-n+1, no range → 1 bit
   - Output ONLY '0' and '1' binary strings - NEVER 'X', 'Z', 'd'
   - Always mask outputs: `result & ((1 << width) - 1)`
   - Multi-bit format: `format(result, f'0{{{{width}}}}b')`

**4. State Updates**:
   - Update state ONLY when `clk == 1` (rising edge)
   - Initialize all state variables to 0 in __init__

## Implementation Template

```python
class GoldenDUT:
    def __init__(self):
        # Initialize state variables to 0
        pass

    def load(self, clk: int, inputs: Dict[str, str]) -> Dict[str, str]:
        # Parse inputs using EXACT signal names from module_header
        # Example: reset = int(inputs["reset"], 2)  # Use actual name!

        # Update state on clk == 1 (rising edge)

        # Return outputs as binary strings
        # Example: return {{"out": format(result, f'0{{width}}b')}}
        pass
```

**REMEMBER**:
- Use EXACT signal names from module_header
- Output ONLY binary strings with '0' and '1'
- Access inputs dict with correct key names
"""

SEQ_PythonHeader = """
import json
import re
import random
import subprocess
import os
from typing import Dict, List, Union

def extract_module_ports_with_yosys(verilog_file="module_code.v"):
    \"\"\"
    Use yosys to extract module port information (inputs/outputs with widths).
    Returns a dict with 'inputs' and 'outputs', each containing {port_name: width}.
    \"\"\"
    try:
        # Create a temporary yosys script
        yosys_script = f\"\"\"
read_verilog {verilog_file}
hierarchy -check
proc
opt_clean
write_json ports.json
\"\"\"
        with open("extract_ports.ys", "w") as f:
            f.write(yosys_script)

        # Run yosys
        result = subprocess.run(
            ["yosys", "-s", "extract_ports.ys"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            print(f"Yosys extraction failed: {result.stderr}")
            return None

        # Parse the JSON output
        with open("ports.json", "r") as f:
            yosys_data = json.load(f)

        # Extract port information from the first module
        module_name = list(yosys_data["modules"].keys())[0]
        module_data = yosys_data["modules"][module_name]

        ports = {"inputs": {}, "outputs": {}}

        for port_name, port_info in module_data["ports"].items():
            direction = port_info["direction"]
            bits = port_info["bits"]
            width = len(bits)

            port_name_lower = port_name.lower()
            # Skip ONLY clock signals - reset signals should be included!
            if any(keyword in port_name_lower for keyword in ["clk", "clock"]):
                continue

            if direction == "input":
                ports["inputs"][port_name] = width
            elif direction == "output":
                ports["outputs"][port_name] = width

        return ports
    except Exception as e:
        print(f"Error extracting ports with yosys: {e}")
        return None

def generate_random_stimulus_seq(ports_info, num_scenarios=5, cycles_per_scenario=10):
    \"\"\"
    Generate random stimulus scenarios for sequential circuits.
    Returns a list of scenarios with clock_cycles and input sequences.
    \"\"\"
    scenarios = []

    for _ in range(num_scenarios):
        scenario = {"clock_cycles": cycles_per_scenario}

        for port_name, width in ports_info["inputs"].items():
            # Generate random sequence for this input
            sequence = []
            for _ in range(cycles_per_scenario):
                random_value = random.randint(0, (1 << width) - 1)
                sequence.append(format(random_value, f'0{width}b'))
            scenario[port_name] = sequence

        scenarios.append(scenario)

    return scenarios

def verify_and_fix_stimulus_seq(stimulus_data, verilog_file="module_code.v"):
    \"\"\"
    Verify stimulus.json matches module ports for sequential circuits.
    If not, generate new stimulus.
    Returns the verified/corrected stimulus data.
    \"\"\"
    # Flatten nested lists (handle cases where stimulus_gen returns nested structures)
    if isinstance(stimulus_data, list):
        flattened_data = []
        for item in stimulus_data:
            if isinstance(item, list):
                # If item is a list, extend (flatten) it into the main list
                flattened_data.extend(item)
            else:
                # If item is not a list, append it directly
                flattened_data.append(item)
        stimulus_data = flattened_data

    # Extract port information using yosys
    ports_info = extract_module_ports_with_yosys(verilog_file)

    if ports_info is None:
        print("Warning: Could not extract port information with yosys, using original stimulus")
        return stimulus_data

    # Get expected input port names (excluding clock/reset)
    expected_inputs = set(ports_info["inputs"].keys())

    if len(stimulus_data) == 0:
        print("Warning: stimulus.json is empty, generating random stimulus")
        return generate_random_stimulus_seq(ports_info)

    # Infer clock_cycles for scenarios missing it
    for idx, scenario in enumerate(stimulus_data):
        if not isinstance(scenario, dict):
            continue
        if "clock_cycles" not in scenario:
            # Check if all values are single strings (single cycle) or lists (multi-cycle)
            has_lists = any(isinstance(v, list) for k, v in scenario.items() if k != "clock_cycles")
            if has_lists:
                # If any value is a list, infer clock_cycles from the longest list
                max_len = max((len(v) if isinstance(v, list) else 1) for v in scenario.values())
                scenario["clock_cycles"] = max_len
                print(f"Warning: Scenario {idx} missing 'clock_cycles', inferred as {max_len} from signal lengths")
            else:
                # All values are single strings, so it's a single cycle test
                scenario["clock_cycles"] = 1
                print(f"Warning: Scenario {idx} missing 'clock_cycles', inferred as 1 (single cycle)")

    # Check if stimulus keys match expected inputs
    # Skip scenarios that are not dicts
    valid_scenarios = [s for s in stimulus_data if isinstance(s, dict)]
    if not valid_scenarios:
        print("Warning: No valid scenarios after flattening, generating random stimulus")
        return generate_random_stimulus_seq(ports_info)

    actual_inputs = set(valid_scenarios[0].keys()) - {"clock_cycles"}

    # Check if we have at least some overlap with expected inputs
    # Don't require exact match - allow extra signals (will be filtered) or missing signals
    overlap = actual_inputs & expected_inputs

    if not overlap and expected_inputs:
        # Only regenerate if there's ZERO overlap with expected inputs
        print(f"Critical mismatch detected!")
        print(f"Expected inputs from module: {sorted(expected_inputs)}")
        print(f"Actual inputs from stimulus.json: {sorted(actual_inputs)}")
        print(f"No overlap found - Generating new random stimulus based on module ports...")

        # Determine average cycles from original stimulus
        avg_cycles = sum(s.get("clock_cycles", 10) for s in stimulus_data) // len(stimulus_data)
        return generate_random_stimulus_seq(ports_info, num_scenarios=len(stimulus_data), cycles_per_scenario=avg_cycles)
    elif expected_inputs != actual_inputs:
        # Partial mismatch - filter out extra signals, keep the ones that match
        print(f"Partial mismatch detected:")
        print(f"Expected inputs from module: {sorted(expected_inputs)}")
        print(f"Actual inputs from stimulus.json: {sorted(actual_inputs)}")

        extra_signals = actual_inputs - expected_inputs
        missing_signals = expected_inputs - actual_inputs

        if extra_signals:
            print(f"Extra signals (will be filtered): {sorted(extra_signals)}")
        if missing_signals:
            print(f"Missing signals (will NOT be auto-added): {sorted(missing_signals)}")

        # Filter stimulus to only keep valid signals
        filtered_data = []
        for scenario in stimulus_data:
            if not isinstance(scenario, dict):
                continue
            filtered_scenario = {"clock_cycles": scenario.get("clock_cycles", 1)}
            for sig in expected_inputs:
                if sig in scenario:
                    filtered_scenario[sig] = scenario[sig]
            filtered_data.append(filtered_scenario)

        print(f"Filtered stimulus to keep only valid signals: {sorted(expected_inputs & actual_inputs)}")
        return filtered_data
    else:
        print(f"Stimulus verification passed. All ports match: {sorted(expected_inputs)}")
        return stimulus_data

"""
# =============================================================================


PythonHeader = """
import json
from typing import Dict, List, Union

"""

class PyCheckerAgent:
    """
    Agent for generating testbench files with expected outputs
    Simplified architecture: only __init__ and run
    """
    
    def __init__(self, llm_client=None, max_retries: int = 3, worker=None):
        """Initialize the PyChecker Agent
        
        Args:
            llm_client: LLM client for making API calls
            max_retries: Maximum number of retries on failure
            worker: Ray worker actor for executing Python code (optional)
        """
        self.llm_client = llm_client
        self.max_retries = max_retries
        self.worker = worker
        logger.info(f"PyCheckerAgent initialized with max_retries={max_retries}, worker={'provided' if worker else 'None'}")
        
    def run(
        self,
        description: str,
        header: str,
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
                
                if circuit_type.lower() == "seq":
                    system_prompt = SEQ_SYSTEM_PROMPT
                    user_prompt = SEQ_GENERATION_PROMPT.format(
                        description=description,
                        module_header=header
                    )
                else:  # cmb
                    system_prompt = CMB_SYSTEM_PROMPT
                    user_prompt = CMB_GENERATION_PROMPT.format(
                        description=description,
                        module_header=header
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

                # Validate Python syntax before saving
                logger.info(f"Validating Python syntax for attempt {attempt + 1}")
                syntax_error = self._validate_python_syntax(complete_code)
                if syntax_error:
                    error_msg = f"Python syntax error:\n{syntax_error}"
                    logger.warning(f"Attempt {attempt + 1} failed: {error_msg}")
                    previous_error = error_msg
                    continue

                # Step 5: Save Python code to file
                golden_dut_path = os.path.join(output_dir, "golden_dut.py")

                with open(golden_dut_path, 'w') as f:
                    f.write(complete_code)

                # Step 6: Execute Python code to generate testbench.json
                logger.info(f"Executing Python code: {golden_dut_path}")
                
                if self.worker is not None:
                    # Use Ray worker for execution
                    try:
                        if RAY_AVAILABLE:
                            # Increased timeouts to handle complex golden DUT execution
                            # Worker timeout: 120s for execution
                            # Ray.get timeout: 300s (5 min) to allow for Ray overhead and queueing
                            obj_ref = self.worker.run_python_file.remote(
                                python_file_path="golden_dut.py",
                                working_directory=output_dir,
                                timeout=120.0
                            )
                            success, error_msg = ray.get(obj_ref, timeout=300.0)
                            
                            if not success:
                                logger.warning(f"Attempt {attempt + 1} failed: {error_msg}")
                                previous_error = error_msg
                                continue
                        else:
                            raise RuntimeError("Ray is not available but worker was provided")
                    except Exception as e:
                        error_msg = f"Worker execution error: {str(e)}"
                        logger.warning(f"Attempt {attempt + 1} failed: {error_msg}")
                        previous_error = error_msg
                        continue
                else:
                    # Fallback to subprocess if no worker provided
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
        
        # Strip out reasoning tags like <think> ... </think> that some LLMs emit
        cleaned_response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
        cleaned_response = re.sub(r'</?think>', '', cleaned_response)
        
        # Try to find ```python ... ``` blocks
        pattern = r'```python\s*(.*?)\s*```'
        matches = re.findall(pattern, cleaned_response, re.DOTALL)
        
        if matches:
            return matches[0].strip()
        
        # Try to find ``` ... ``` blocks
        pattern = r'```\s*(.*?)\s*```'
        matches = re.findall(pattern, cleaned_response, re.DOTALL)
        
        if matches:
            return matches[0].strip()
        
        # If no fenced code, try to capture from the first class/def definition
        class_idx = cleaned_response.find("class ")
        if class_idx != -1:
            return cleaned_response[class_idx:].strip()
        def_idx = cleaned_response.find("def ")
        if def_idx != -1:
            return cleaned_response[def_idx:].strip()
        
        # If no code blocks found, return the whole response
        logger.warning("No code blocks found in response, using entire response")
        return cleaned_response.strip()
    
    def _validate_python_syntax(self, code: str) -> Optional[str]:
        """Validate Python code syntax
        
        Args:
            code: Python code string
            
        Returns:
            Error message if syntax is invalid, None if valid
        """
        import ast
        
        try:
            ast.parse(code)
            return None
        except SyntaxError as e:
            return f"SyntaxError: {e.msg} at line {e.lineno}, column {e.offset}\n{e.text}"
        except Exception as e:
            return f"Parse error: {str(e)}"
