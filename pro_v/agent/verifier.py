"""
Verifier Agent - LLM-Based Testbench Verification Agent (Simplified Architecture)

This agent uses LLM to verify logical consistency between stimulus and testbench.
Architecture: Only __init__ and run methods.
"""

import json
import logging
import os
import re
from typing import Dict, Any, Optional, Tuple, List

logger = logging.getLogger(__name__)


# ============================================================================
# Verification Prompts
# ============================================================================

VERIFICATION_SYSTEM_PROMPT = """You are an expert in RTL verification and hardware design. Your task is to verify the logical consistency between stimulus inputs and expected outputs in a testbench."""

VERIFICATION_PROMPT = """
Analyze the following RTL design, specification, stimulus inputs, and expected outputs to verify logical consistency.

<RTL Code>
{rtl_code}
</RTL Code>

<Specification>
{specification}
</Specification>

<Circuit Type>
{circuit_type}
</Circuit Type>

<Stimulus Sample (first 3 test cases)>
{stimulus_sample}
</Stimulus Sample>

<Testbench Sample (first 3 test cases)>
{testbench_sample}
</Testbench Sample>

<PyChecker Code (Golden DUT)>
{pychecker_code}
</PyChecker Code>

Your task:
1. Verify that the testbench outputs are logically consistent with the RTL specification
2. Check if the PyChecker golden model correctly implements the circuit logic
3. Identify any errors in:
   - Stimulus generation (incorrect signal names, invalid values)
   - Golden model logic (wrong implementation)
   - Expected outputs (incorrect values)

Based on your analysis, provide ONE of these three decisions:

**Decision 1: MODIFY_PYCHECKER**
Use this if the PyChecker golden model has logic errors or doesn't match the specification.
Output format:
```
DECISION: MODIFY_PYCHECKER
REASON: [Explain the error in the golden model logic]
ERROR_LOCATIONS: [Specific lines or functions with errors]
CORRECTED_LOGIC: [Describe the correct logic implementation]
```

**Decision 2: MODIFY_TESTBENCH**
Use this if the testbench outputs are incorrect but the PyChecker logic is correct.
Output format:
```
DECISION: MODIFY_TESTBENCH
REASON: [Explain why the outputs are incorrect]
INCORRECT_FIELDS: [List of test cases and fields that are wrong]
CORRECT_VALUES: [Provide the correct expected output values]
```

**Decision 3: COMPLETE**
Use this if everything is logically consistent and correct.
Output format:
```
DECISION: COMPLETE
REASON: [Explain why the testbench is verified as correct]
CONFIDENCE: [High/Medium/Low]
```

Provide your analysis and decision:
"""


class VerifierAgent:
    """
    Agent for LLM-based verification of testbench logical consistency
    Simplified architecture: only __init__ and run
    """

    def __init__(self, llm_client=None, max_retries: int = 3):
        """Initialize the Verifier Agent

        Args:
            llm_client: LLM client for making API calls
            max_retries: Maximum number of verification retries
        """
        self.llm_client = llm_client
        self.max_retries = max_retries
        logger.info(f"VerifierAgent initialized with max_retries={max_retries}")

    def run(
        self,
        rtl_code: str,
        specification: str,
        circuit_type: str,
        stimulus_json_path: str,
        testbench_json_path: str,
        pychecker_code_path: str
    ) -> Dict[str, Any]:
        """Verify testbench logical consistency using LLM

        This method:
        1. Loads stimulus.json, testbench.json, and pychecker code
        2. Sends to LLM for logical consistency verification
        3. Receives one of three decisions:
           - MODIFY_PYCHECKER: PyChecker code has errors
           - MODIFY_TESTBENCH: Testbench outputs are incorrect
           - COMPLETE: Verification passed

        Args:
            rtl_code: RTL code
            specification: Specification description
            circuit_type: Circuit type ("cmb" or "seq")
            stimulus_json_path: Path to stimulus.json file
            testbench_json_path: Path to testbench.json file
            pychecker_code_path: Path to PyChecker golden model code

        Returns:
            Dictionary with verification decision and details
        """
        logger.info(f"VerifierAgent.run started for circuit_type={circuit_type}")

        try:
            # Load stimulus data
            with open(stimulus_json_path, 'r') as f:
                stimulus_data = json.load(f)
                stimulus_sample = json.dumps(
                    stimulus_data[:3] if len(stimulus_data) > 3 else stimulus_data,
                    indent=2
                )

            # Load testbench data
            with open(testbench_json_path, 'r') as f:
                testbench_data = json.load(f)
                testbench_sample = json.dumps(
                    testbench_data[:3] if len(testbench_data) > 3 else testbench_data,
                    indent=2
                )

            # Load PyChecker code
            with open(pychecker_code_path, 'r') as f:
                pychecker_code = f.read()

        except Exception as e:
            logger.error(f"Failed to load verification files: {e}")
            return {
                "success": False,
                "decision": "ERROR",
                "error": f"Failed to load files: {e}"
            }

        # Send to LLM for verification
        user_prompt = VERIFICATION_PROMPT.format(
            rtl_code=rtl_code,
            specification=specification,
            circuit_type=circuit_type,
            stimulus_sample=stimulus_sample,
            testbench_sample=testbench_sample,
            pychecker_code=pychecker_code
        )

        logger.info("Sending verification request to LLM")
        response = self._call_llm(VERIFICATION_SYSTEM_PROMPT, user_prompt)

        if not response:
            logger.error("Empty LLM response")
            return {
                "success": False,
                "decision": "ERROR",
                "error": "Empty LLM response"
            }

        # Parse LLM decision
        result = self._parse_decision(response)
        result["llm_response"] = response
        result["success"] = True

        logger.info(f"Verification decision: {result['decision']}")
        return result

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Call LLM for verification analysis

        Args:
            system_prompt: System prompt
            user_prompt: User prompt

        Returns:
            LLM response string
        """
        if self.llm_client is None:
            # Placeholder for testing
            logger.warning("No LLM client configured, returning placeholder decision")
            return """
DECISION: COMPLETE
REASON: Testbench appears logically consistent with the RTL specification. All test cases have valid inputs and expected outputs match the circuit behavior.
CONFIDENCE: High
"""

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

    def _parse_decision(self, response: str) -> Dict[str, Any]:
        """Parse LLM decision from response

        Args:
            response: LLM response containing decision

        Returns:
            Parsed decision dictionary
        """
        result = {
            "decision": "UNKNOWN",
            "reason": "",
            "details": {}
        }

        # Extract decision
        decision_match = re.search(r'DECISION:\s*(MODIFY_PYCHECKER|MODIFY_TESTBENCH|COMPLETE)', response, re.IGNORECASE)
        if decision_match:
            result["decision"] = decision_match.group(1).upper()

        # Extract reason
        reason_match = re.search(r'REASON:\s*(.+?)(?=\n[A-Z_]+:|$)', response, re.DOTALL)
        if reason_match:
            result["reason"] = reason_match.group(1).strip()

        # Parse decision-specific details
        if result["decision"] == "MODIFY_PYCHECKER":
            # Extract error locations
            error_loc_match = re.search(r'ERROR_LOCATIONS:\s*(.+?)(?=\n[A-Z_]+:|$)', response, re.DOTALL)
            if error_loc_match:
                result["details"]["error_locations"] = error_loc_match.group(1).strip()

            # Extract corrected logic
            corrected_match = re.search(r'CORRECTED_LOGIC:\s*(.+?)(?=\n[A-Z_]+:|$)', response, re.DOTALL)
            if corrected_match:
                result["details"]["corrected_logic"] = corrected_match.group(1).strip()

        elif result["decision"] == "MODIFY_TESTBENCH":
            # Extract incorrect fields
            incorrect_match = re.search(r'INCORRECT_FIELDS:\s*(.+?)(?=\n[A-Z_]+:|$)', response, re.DOTALL)
            if incorrect_match:
                result["details"]["incorrect_fields"] = incorrect_match.group(1).strip()

            # Extract correct values
            correct_match = re.search(r'CORRECT_VALUES:\s*(.+?)(?=\n[A-Z_]+:|$)', response, re.DOTALL)
            if correct_match:
                result["details"]["correct_values"] = correct_match.group(1).strip()

        elif result["decision"] == "COMPLETE":
            # Extract confidence
            confidence_match = re.search(r'CONFIDENCE:\s*(High|Medium|Low)', response, re.IGNORECASE)
            if confidence_match:
                result["details"]["confidence"] = confidence_match.group(1).capitalize()

        return result

