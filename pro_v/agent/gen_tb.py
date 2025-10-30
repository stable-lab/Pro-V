"""
GenTB Agent - Testbench Generation Agent (Simplified Architecture)

This agent generates Python stimulus code for RTL designs.
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

CMB_SYSTEM_PROMPT = """You are an expert in RTL design and Python programming."""

CMB_GENERATION_PROMPT = """
Generate a Python function named "stimulus_gen" that produces test vectors for a combinational circuit.

<RTL Code>
{rtl_code}
</RTL Code>

<Specification>
{specification}
</Specification>

Requirements:
1. Return a list of dictionaries
2. Each dictionary has input signal names as keys, binary strings as values
3. Use Python programming (random, numpy) to generate test vectors dynamically
4. Include corner cases, edge cases, and random test cases (at least 10-20)

Output your code in this format:
```python
import json
import random
import numpy as np

def stimulus_gen():
    test_vectors = []
    # Your implementation here
    return test_vectors

if __name__ == "__main__":
    result = stimulus_gen()
    with open("stimulus.json", "w") as f:
        json.dump(result, f, indent=2)
```
"""


# ============================================================================
# SEQ (Sequential) Circuit Prompts
# ============================================================================

SEQ_SYSTEM_PROMPT = """You are an expert in RTL design and Python programming."""

SEQ_GENERATION_PROMPT = """
Generate a Python function named "stimulus_gen" that produces test scenarios for a sequential circuit.

<RTL Code>
{rtl_code}
</RTL Code>

<Specification>
{specification}
</Specification>

Requirements:
1. Return a list of test scenarios (dictionaries)
2. Each scenario has "clock_cycles" (int) and input signal sequences (lists)
3. Use the EXACT signal names from the RTL module header
4. Use Python programming to generate scenarios dynamically
5. Include reset, normal operation, edge cases, and random scenarios (at least 10-20)

Output your code in this format:
```python
import json
import random
import numpy as np

def stimulus_gen():
    scenarios = []
    # Your implementation here
    return scenarios

if __name__ == "__main__":
    result = stimulus_gen()
    with open("stimulus.json", "w") as f:
        json.dump(result, f, indent=2)
```
"""


# ============================================================================
# GenTBAgent Class
# ============================================================================

class GenTBAgent:
    """Agent for generating stimulus files"""
    
    def __init__(self, llm_client=None, max_retries: int = 3):
        """Initialize the GenTB Agent
        
        Args:
            llm_client: LLM client for generating code
            max_retries: Maximum number of retry attempts
        """
        self.llm_client = llm_client
        self.max_retries = max_retries
        logger.info(f"GenTBAgent initialized with max_retries={max_retries}")
        
    def run(self, rtl_code: str, specification: str, circuit_type: str, output_dir: str) -> Dict[str, Any]:
        """Generate stimulus.json file

        Args:
            rtl_code: RTL source code
            specification: Circuit specification
            circuit_type: "cmb" or "seq"
            output_dir: Directory to save outputs

        Returns:
            Dictionary with success status and file paths
        """
        logger.info(f"GenTBAgent.run started for circuit_type={circuit_type}")

        # Track previous attempts for error feedback
        previous_code = None
        previous_error = None

        for attempt in range(self.max_retries):
            try:
                # Select prompts based on circuit type
                if circuit_type.lower() == "seq":
                    system_prompt = SEQ_SYSTEM_PROMPT
                    user_prompt = SEQ_GENERATION_PROMPT.format(
                        rtl_code=rtl_code,
                        specification=specification
                    )
                else:
                    system_prompt = CMB_SYSTEM_PROMPT
                    user_prompt = CMB_GENERATION_PROMPT.format(
                        rtl_code=rtl_code,
                        specification=specification
                    )

                # For retry attempts, append previous code and error information
                if attempt > 0 and previous_code and previous_error:
                    user_prompt += f"\n\n---\n\n**RETRY ATTEMPT {attempt + 1}**\n\n"
                    user_prompt += "The previous code generated has errors. Please fix the issues.\n\n"
                    user_prompt += f"<previous_code>\n```python\n{previous_code}\n```\n</previous_code>\n\n"
                    user_prompt += f"<error_message>\n{previous_error}\n</error_message>\n\n"
                    user_prompt += "Please analyze the error and provide corrected code."

                # Call LLM to generate code
                logger.info(f"Attempt {attempt + 1}/{self.max_retries}: Sending LLM request")
                response = self._call_llm(system_prompt, user_prompt)

                if not response:
                    logger.warning(f"Attempt {attempt + 1} failed: Empty LLM response")
                    previous_error = "Empty LLM response"
                    continue

                # Extract Python code
                python_code = self._extract_code(response)

                if not python_code:
                    logger.warning(f"Attempt {attempt + 1} failed: No Python code extracted")
                    previous_error = "No Python code extracted from LLM response"
                    continue

                # Store current code for potential retry
                previous_code = python_code

                # Save Python code
                os.makedirs(output_dir, exist_ok=True)
                stimulus_py_path = os.path.join(output_dir, "stimulus_gen.py")

                with open(stimulus_py_path, 'w') as f:
                    f.write(python_code)

                # Execute Python code
                logger.info(f"Executing Python code: {stimulus_py_path}")
                result = subprocess.run(
                    ["python", "stimulus_gen.py"],
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

                # Verify stimulus.json was created
                stimulus_json_path = os.path.join(output_dir, "stimulus.json")

                if not os.path.exists(stimulus_json_path):
                    logger.warning(f"Attempt {attempt + 1} failed: stimulus.json not created")
                    previous_error = "stimulus.json was not created after execution"
                    continue

                # Validate JSON format
                with open(stimulus_json_path, 'r') as f:
                    stimulus_data = json.load(f)

                logger.info(f"GenTBAgent.run succeeded on attempt {attempt + 1}")
                return {
                    "success": True,
                    "stimulus_json_path": stimulus_json_path,
                    "stimulus_py_path": stimulus_py_path,
                    "num_test_cases": len(stimulus_data),
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
        logger.error(f"GenTBAgent.run failed after {self.max_retries} attempts")
        return {
            "success": False,
            "error": f"Failed after {self.max_retries} attempts",
            "stimulus_json_path": None
        }
    
    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Call LLM to generate Python code
        
        Args:
            system_prompt: System message for LLM
            user_prompt: User message for LLM
            
        Returns:
            LLM response string
        """
        if self.llm_client is None:
            logger.warning("No LLM client configured, returning placeholder code")
            return """```python
import json
import random

def stimulus_gen():
    test_vectors = []
    for i in range(10):
        test_vectors.append({"input": format(i, '04b')})
    return test_vectors

if __name__ == "__main__":
    result = stimulus_gen()
    with open("stimulus.json", "w") as f:
        json.dump(result, f, indent=2)
```"""
        
        try:
            response = self.llm_client.chat(system=system_prompt, user=user_prompt)
            return response
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return ""
    
    def _extract_code(self, response: str) -> str:
        """Extract Python code from LLM response
        
        Args:
            response: LLM response text
            
        Returns:
            Extracted Python code
        """
        import re
        
        # Try to find code in ```python``` blocks
        pattern = r'```python\s*(.*?)\s*```'
        matches = re.findall(pattern, response, re.DOTALL)
        
        if matches:
            return matches[0].strip()
        
        # Try to find code in ``` blocks
        pattern = r'```\s*(.*?)\s*```'
        matches = re.findall(pattern, response, re.DOTALL)
        
        if matches:
            return matches[0].strip()
        
        # Use entire response if no code blocks found
        logger.warning("No code blocks found in response, using entire response")
        return response.strip()
