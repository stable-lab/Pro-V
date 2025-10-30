import json
from typing import Dict

from llama_index.core.base.llms.types import ChatMessage, MessageRole
from utils.gen_config import get_llm
from utils.log_utils import get_logger
from utils.prompts import ORDER_PROMPT
from utils.token_counter import TokenCounter, TokenCounterCached

logger = get_logger(__name__)

SYSTEM_PROMPT = r"""
You are an expert in RTL design. You can always write SystemVerilog code with no syntax errors and always reach correct functionality.
"""

GENERATION_PROMPT = r"""
Analyze the provided SystemVerilog specification to classify it as Combinational (CMB) or Sequential (SEQ) logic.

Key Decision Criteria:
1. SEQ Indicators (ANY of these qualifies as sequential):
   - Clock-edge triggered blocks (posedge/negedge in sensitivity list)
   - Explicit registers (always_ff, flip-flop templates)
   - State variables retained between cycles
   - Usage of non-blocking assignments (<=) in clocked blocks

2. CMB Indicators (ALL must apply):
   - No edge-sensitive constructs
   - Outputs purely function of current inputs
   - Uses always_comb/always @* or continuous assignments
   - Any "state" variables are combinatorial precursors (immediately resolved)

Critical Differentiation Guidelines:
- Combinational state machines using case/if for next_state without registration → CMB
- Latches (level-sensitive) → Classify as SEQ per industry convention
- Asynchronous reset alone doesn't make logic sequential
- Edge detection in testbenches doesn't affect module classification

{example_prompt}
<input_spec>
{input_spec}
</input_spec>
"""

EXAMPLE_OUTPUT_FORMAT = {
    "reasoning": "All reasoning to analyze the circuit type",
    "classification": "CMB or SEQ (do not use any other words)",
}

CLASSIFICATION_1_SHOT_EXAMPLES = r"""
Here are some examples:
Example 1:
<example> "input_spec": " // Module: simple_counter // Interface: // input logic clk, rst_n // output logic [3:0] count // // Specification: // 1. On every rising edge of clk, if rst_n is low, count resets to 0. // 2. Otherwise, count increments by 1. ", "reasoning": r" The design explicitly uses a clock (clk) and a reset signal (rst_n) to control state transitions. Since the counter updates its value on a clock edge, it clearly implements sequential logic. ", "classification": "SEQ" </example>

Example 2:
<example> "input_spec": " // Module: adder // Interface: // input logic [7:0] a, b // output logic [7:0] sum // // Specification: // 1. The module computes the sum of inputs a and b combinationally. // 2. There is no clock or state element involved. ", "reasoning": r" The absence of any clock or state-related signals and the direct assignment of the output based on inputs indicate that the module is purely combinational. ", "classification": "CMB" </example>

Boundary Case Examples:

Example 3:
<example>
input_spec: "// Combinational state machine
always_comb begin
    case(current_state)
        S0: next_state = (cond) ? S1 : S0;
        S1: next_state = S2;
        default: next_state = S0;
    endcase
end"
output: {
    "classification": "CMB"
}
</example>

Example 4:
<example>
input_spec: "// Latch implementation
always_latch begin
    if (enable) q <= d;"
output: {
    "classification": "SEQ"
}
</example>
"""

EXTRA_ORDER_PROMPT = r"""
VERY IMPORTANT: Please only include "classification" in your response.
Do not include any other information in your response, like 'json', 'example', 'Let me analyze','input_spec' or '<output_format>'.
Key instruction: Direct output, no extra comments.
As a reminder, please directly provide the content without adding any extra comments or explanations.
"""


class CircuitTypeClassifier:
    def __init__(
        self,
        model: str,
        max_token: int,
        provider: str,
        cfg_path: str,
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
        # self.token_counter.token_cnts['circuit_type_classifier'] = []
        # self.history = []
        # self.max_trials = 15

    def run(self, input_spec: str) -> Dict:
        # self.token_counter.reset()
        if isinstance(self.token_counter, TokenCounterCached):
            self.token_counter.set_enable_cache(True)
        print(f"Setting token counter tag to {self.__class__.__name__}")
        self.token_counter.set_cur_tag(self.__class__.__name__)
        msg = [
            ChatMessage(content=SYSTEM_PROMPT, role=MessageRole.SYSTEM),
            ChatMessage(
                content=GENERATION_PROMPT.format(
                    input_spec=input_spec, example_prompt=CLASSIFICATION_1_SHOT_EXAMPLES
                ),
                role=MessageRole.USER,
            ),
            ChatMessage(
                content=ORDER_PROMPT.format(
                    output_format="".join(json.dumps(EXAMPLE_OUTPUT_FORMAT, indent=4))
                ),
                role=MessageRole.USER,
            ),
        ]
        print(f"Generating response ")
        response, token_cnt = self.token_counter.count_chat(msg)
        print(f"Response: {response.message.content}")

        logger.info(f"Token count: {token_cnt}")
        logger.info(f"{response.message.content}")
        self.token_counter.log_token_stats()

        # response = self.generate(msg)
        logger.info(f"Get response from {self.model}: {response.message.content}")
        try:
            # output_json_obj: Dict = json.loads(response.message.content, strict=False)

            # use this for Deepseek r1 and claude-3-5-sonnet
            # if self.model == "claude-3-5-sonnet-20241022":
            #     output_json_obj: Dict = json.loads("".join(response.choices[0].message.content.split("\n")[1:]), strict=False)
            # else:
            #     output_json_obj: Dict = json.loads(response.choices[0].message.content, strict=False)
            output_json_obj: Dict = json.loads(response.message.content, strict=False)

            classification = output_json_obj["classification"]
            logger.info(f"Succeed to parse response, Classification: {classification}")
        except json.decoder.JSONDecodeError as e:
            print(f"Json parse error: {e}")
            logger.info(f"Json parse error: {e}")
            print(response)
            return None

        return output_json_obj


