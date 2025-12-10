"""
GenRTL Agent - RTL Generation Agent

This agent generates Verilog RTL code based on specifications.
Uses simulation feedback to iteratively refine the RTL.
"""

import json
import logging
import os
import re
from typing import Dict, Any, Optional

try:
    import ray
    RAY_AVAILABLE = True
except ImportError:
    RAY_AVAILABLE = False
    ray = None

logger = logging.getLogger(__name__)

RTL_SYSTEM_PROMPT = """You are an expert in RTL (Register Transfer Level) design and Verilog programming. You can write correct, efficient, and synthesizable Verilog code."""

RTL_GENERATION_PROMPT = """
Your task is to implement a Verilog module based on the given specification.

<description>
{description}
</description>

<module_header>
{module_header}
</module_header>

## Requirements

1. **Module Declaration**: Use the EXACT module header provided above
2. **Signal Names**: Use the exact signal names from the module header
3. **Functionality**: Implement the behavior described in the specification
4. **Synthesizable Code**: Write clean, synthesizable Verilog code
5. **No Testbench**: Only provide the module implementation, not a testbench

## Important Guidelines

- For **combinational circuits**: Use `assign` statements or `always @(*)` blocks
- For **sequential circuits**: Use `always @(posedge clk)` blocks for registers
- Handle reset signals properly (synchronous or asynchronous as specified)
- Avoid race conditions and latches
- Use proper bit widths for all signals
- Comment complex logic for clarity

## Output Format

You MUST return your code in this exact format:
```verilog
module top_module (
    // ports from header
);
    // your implementation here
endmodule
```

**IMPORTANT**:
- Do NOT include any testbench code
- Do NOT include timescale directives
- Only provide the module implementation
- Ensure the code is syntactically correct Verilog
"""

RTL_REFINEMENT_PROMPT = """
The previous RTL implementation has errors. Please fix the issues based on the simulation feedback.

<description>
{description}
</description>

<module_header>
{module_header}
</module_header>

<previous_rtl>
```verilog
{previous_rtl}
```
</previous_rtl>

<simulation_errors>
{simulation_errors}
</simulation_errors>

<golden_reference>
{golden_reference}
</golden_reference>

## Analysis Required

1. **Understand the errors**: Analyze the simulation output to identify what went wrong
2. **Compare with golden reference**: The golden_dut.py shows the expected behavior
3. **Identify the bug**: Determine where your RTL differs from the specification
4. **Fix the implementation**: Correct the RTL to match the expected behavior

## Output Format

Provide the corrected Verilog code in this format:
```verilog
module top_module (
    // ports from header
);
    // your corrected implementation here
endmodule
```

**IMPORTANT**: Only provide the corrected module code, nothing else.
"""


class GenRTLAgent:
    """Agent for generating Verilog RTL code"""

    def __init__(self, llm_client=None, max_retries: int = 3):
        """Initialize the GenRTL Agent

        Args:
            llm_client: LLM client for generating code
            max_retries: Maximum number of retry attempts (total turns including first generation)
        """
        self.llm_client = llm_client
        self.max_retries = max_retries
        logger.info(f"GenRTLAgent initialized with max_retries={max_retries}")

    def _generate_rtl_prompt(self, description: str, header: str,
                            previous_rtl: Optional[str] = None,
                            simulation_errors: Optional[str] = None,
                            golden_reference: Optional[str] = None) -> str:
        """Generate prompt for RTL generation or refinement"""

        if previous_rtl is None:
            # First generation
            prompt = RTL_SYSTEM_PROMPT + "\n\n" + RTL_GENERATION_PROMPT.format(
                description=description,
                module_header=header
            )
        else:
            # Refinement with error feedback
            prompt = RTL_SYSTEM_PROMPT + "\n\n" + RTL_REFINEMENT_PROMPT.format(
                description=description,
                module_header=header,
                previous_rtl=previous_rtl,
                simulation_errors=simulation_errors or "No specific error information available",
                golden_reference=golden_reference or "No golden reference available"
            )

        return prompt

    def run(self, description: str, header: str, output_dir: str,
            previous_rtl: Optional[str] = None,
            simulation_errors: Optional[str] = None,
            golden_dut_path: Optional[str] = None) -> Dict[str, Any]:
        """Generate or refine RTL code

        Args:
            description: Problem description
            header: Module header specification
            output_dir: Directory to save outputs
            previous_rtl: Previous RTL code (for refinement)
            simulation_errors: Error messages from simulation (for refinement)
            golden_dut_path: Path to golden_dut.py for reference (for refinement)

        Returns:
            Dictionary with success status and file paths
        """
        is_refinement = previous_rtl is not None
        mode = "refinement" if is_refinement else "generation"
        logger.info(f"GenRTLAgent.run started in {mode} mode")

        # Load golden reference if provided
        golden_reference = None
        if golden_dut_path and os.path.exists(golden_dut_path):
            try:
                with open(golden_dut_path, 'r') as f:
                    golden_reference = f.read()
            except Exception as e:
                logger.warning(f"Failed to load golden reference: {e}")

        try:
            # Generate prompt
            system_prompt = ""
            user_prompt = self._generate_rtl_prompt(
                description=description,
                header=header,
                previous_rtl=previous_rtl,
                simulation_errors=simulation_errors,
                golden_reference=golden_reference
            )

            # Call LLM to generate code
            logger.info(f"Sending LLM request for RTL {mode}")
            response = self._call_llm(system_prompt, user_prompt)

            if not response:
                logger.warning(f"Empty LLM response")
                return {
                    "success": False,
                    "error": "Empty LLM response"
                }

            # Extract Verilog code
            verilog_code = self._extract_verilog_code(response)

            if not verilog_code:
                logger.warning(f"No Verilog code extracted")
                return {
                    "success": False,
                    "error": "No Verilog code extracted from LLM response"
                }

            # Basic syntax validation
            if not self._validate_verilog_syntax(verilog_code):
                logger.warning(f"Basic Verilog syntax validation failed")
                return {
                    "success": False,
                    "error": "Basic Verilog syntax validation failed"
                }

            # Save Verilog code
            os.makedirs(output_dir, exist_ok=True)
            rtl_path = os.path.join(output_dir, "top_module.v")

            with open(rtl_path, 'w') as f:
                f.write(verilog_code)

            logger.info(f"GenRTLAgent.run succeeded in {mode} mode")
            return {
                "success": True,
                "rtl_path": rtl_path,
                "code_length": len(verilog_code)
            }

        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                "success": False,
                "error": error_msg
            }

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Call LLM to generate Verilog code

        Args:
            system_prompt: System message for LLM
            user_prompt: User message for LLM

        Returns:
            LLM response string
        """
        if self.llm_client is None:
            logger.warning("No LLM client configured, returning placeholder code")
            return """```verilog
module top_module (
    input wire clk,
    input wire [7:0] data_in,
    output reg [7:0] data_out
);
    always @(posedge clk) begin
        data_out <= data_in;
    end
endmodule
```"""

        try:
            response = self.llm_client.chat(system=system_prompt, user=user_prompt)
            return response
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return ""

    def _extract_verilog_code(self, response: str) -> str:
        """Extract Verilog code from LLM response

        Args:
            response: LLM response text

        Returns:
            Extracted Verilog code
        """
        # Try to find code in ```verilog``` blocks
        pattern = r'```verilog\s*(.*?)\s*```'
        matches = re.findall(pattern, response, re.DOTALL)

        if matches:
            return matches[0].strip()

        # Try to find code in ``` blocks
        pattern = r'```\s*(.*?)\s*```'
        matches = re.findall(pattern, response, re.DOTALL)

        if matches:
            # Check if it looks like Verilog (contains 'module')
            for match in matches:
                if 'module' in match:
                    return match.strip()

        # Try to find module...endmodule block
        pattern = r'(module\s+\w+.*?endmodule)'
        matches = re.findall(pattern, response, re.DOTALL)

        if matches:
            return matches[0].strip()

        # Use entire response if no code blocks found
        logger.warning("No code blocks found in response, using entire response")
        return response.strip()

    def _validate_verilog_syntax(self, code: str) -> bool:
        """Basic Verilog syntax validation

        Args:
            code: Verilog code string

        Returns:
            True if basic syntax looks valid, False otherwise
        """
        # Check for module declaration
        if not re.search(r'module\s+\w+', code):
            logger.error("No module declaration found")
            return False

        # Check for endmodule
        if 'endmodule' not in code:
            logger.error("No endmodule found")
            return False

        # Count module/endmodule pairs (should be balanced)
        module_count = len(re.findall(r'\bmodule\b', code))
        endmodule_count = len(re.findall(r'\bendmodule\b', code))

        if module_count != endmodule_count:
            logger.error(f"Unbalanced module/endmodule: {module_count} modules, {endmodule_count} endmodules")
            return False

        # Basic checks passed
        return True
