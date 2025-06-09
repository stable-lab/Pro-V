import json
from typing import Dict

from llama_index.core.base.llms.types import ChatMessage, MessageRole
from utils.gen_config import get_llm
from utils.log_utils import get_logger
from utils.prompts import ORDER_PROMPT
from utils.token_counter import TokenCounter, TokenCounterCached

logger = get_logger(__name__)

SYSTEM_PROMPT = """"""


GENERATION_PROMPT = """
You are tasked with extracting table-like expressions from specification text and converting them into structured dictionaries. This process will facilitate easier information access, organization, and further manipulation of the data.

Here is the specification text you will be working with:

<specification_text>
{input_spec}
</specification_text>

Follow these steps to complete the task:

1. Identify table-like structures in the specification text. These structures typically have a clear layout with rows and columns, often separated by lines, pipes (|), or consistent spacing. If the specification text does not contain any table-like structures, please return the original specification text.
2. For each identified table-like structure, create a list for each table.
3. Return the revised specification text with table dictionary list.
4. For Moore machine, like A (0) --0--> B, you must return in the format of {{"from": "A (0)", "input": "0", "to": "B"}}.
Here is the example:    
<example>
{example_prompt}




</example>

"""

EXAMPLE_OUTPUT_FORMAT = {
    "reasoning": "All reasoning to analyze the table-like structure",
    "revised_spec": "Revised originalspecification text with table dictionary list, if there is no table-like structure, please return the original specification text",
}

CLASSIFICATION_1_SHOT_EXAMPLES = """
Here are some examples:
Example 1:
<example> "input_spec": " 
Rule 110 is a one-dimensional cellular automaton with interesting properties (such as being Turing-complete). There is a one-dimensional array of cells (on or off). At each time step, the state of each cell changes. In Rule 110, the next state of each cell depends only on itself and its two neighbours, according to the following table:
// Left | Center | Right | Center's next state
// 1 | 1 | 1 | 0
// 1 | 1 | 0 | 1
// 1 | 0 | 1 | 1
// 1 | 0 | 0 | 0
// 0 | 1 | 1 | 1
// 0 | 1 | 0 | 1
// 0 | 0 | 1 | 1
// 0 | 0 | 0 | 0 
", "revised_spec": "table = [
    {"Left": 1, "Center": 1, "Right": 1, "Next": 0},
    {"Left": 1, "Center": 1, "Right": 0, "Next": 1},
    {"Left": 1, "Center": 0, "Right": 1, "Next": 1},
    {"Left": 1, "Center": 0, "Right": 0, "Next": 0},
    {"Left": 0, "Center": 1, "Right": 1, "Next": 1},
    {"Left": 0, "Center": 1, "Right": 0, "Next": 1},
    {"Left": 0, "Center": 0, "Right": 1, "Next": 1},
    {"Left": 0, "Center": 0, "Right": 0, "Next": 0},
]" </example>

Example 2:
<example> "input_spec": "Consider the state machine shown below:


// A (0) --0--> B
// A (0) --1--> A
// B (0) --0--> C
// B (0) --1--> D
// C (0) --0--> E
// C (0) --1--> D
// D (0) --0--> F
// D (0) --1--> A
// E (1) --0--> E
// E (1) --1--> D
// F (1) --0--> C
// F (1) --1--> D

// Assume that you want to Implement the FSM using three flip-flops and state codes y[3:1] = 000, 001, ..., 101 for states A, B, ..., F, respectively. Implement just the next-state logic for y[2] in Verilog. The output Y2 is y[2]. ", "revised_spec": "Consider the state machine shown below:
state_transitions = [
    {"from": "A (0)", "input": "0", "to": "B"},
    {"from": "A (0)", "input": "1", "to": "A"},
    {"from": "B (0)", "input": "0", "to": "C"},
    {"from": "B (0)", "input": "1", "to": "D"},
    {"from": "C (0)", "input": "0", "to": "E"},
    {"from": "C (0)", "input": "1", "to": "D"},
    {"from": "D (0)", "input": "0", "to": "F"},
    {"from": "D (0)", "input": "1", "to": "A"},
    {"from": "E (1)", "input": "0", "to": "E"},
    {"from": "E (1)", "input": "1", "to": "D"},
    {"from": "F (1)", "input": "0", "to": "C"},
    {"from": "F (1)", "input": "1", "to": "D"},
]
// Assume that you want to Implement the FSM using three flip-flops and state codes y[3:1] = 000, 001, ..., 101 for states A, B, ..., F, respectively. Implement just the next-state logic for y[2] in Verilog. The output Y2 is y[2]. 
" </example>

Boundary Case Examples:

Example 3:
<example>
input_spec: "For the following Karnaugh map, give the circuit implementation using one 4-to-1 multiplexer and as many 2-to-1 multiplexers as required, but using as few as possible. You are not allowed to use any other logic gate and you must use _a_ and _b_ as the multiplexer selector inputs, as shown on the 4-to-1 multiplexer below.

//       ab
// cd   00 01 11 10
//  00 | 0 | 0 | 0 | 1 |
//  01 | 1 | 0 | 0 | 0 |
//  11 | 1 | 0 | 1 | 1 |
//  10 | 1 | 0 | 0 | 1 |

// Consider a block diagram with inputs 'c' and 'd' going into a module called "top_module". This "top_module" has four outputs, mux_in[3:0], that connect to a four input mux. The mux takes as input {a,b} and ab = 00 is connected to mux_in[0], ab=01 is connected to mux_in[1], and so in. You are implementing in Verilog just the portion labelled "top_module", such that the entire circuit (including the 4-to-1 mux) implements the K-map."
revised_spec: "For the following Karnaugh map, give the circuit implementation using one 4-to-1 multiplexer and as many 2-to-1 multiplexers as required, but using as few as possible. You are not allowed to use any other logic gate and you must use _a_ and _b_ as the multiplexer selector inputs, as shown on the 4-to-1 multiplexer below.

kmap_entries = [
    {'ab': '00', 'cd': '00', 'value': '0'},
    {'ab': '01', 'cd': '00', 'value': '0'},
    {'ab': '11', 'cd': '00', 'value': '0'},
    {'ab': '10', 'cd': '00', 'value': '1'},
    
    {'ab': '00', 'cd': '01', 'value': '1'},
    {'ab': '01', 'cd': '01', 'value': '0'},
    {'ab': '11', 'cd': '01', 'value': '0'},
    {'ab': '10', 'cd': '01', 'value': '0'},
    
    {'ab': '00', 'cd': '11', 'value': '1'},
    {'ab': '01', 'cd': '11', 'value': '0'},
    {'ab': '11', 'cd': '11', 'value': '1'},
    {'ab': '10', 'cd': '11', 'value': '1'},
    
    {'ab': '00', 'cd': '10', 'value': '1'},
    {'ab': '01', 'cd': '10', 'value': '0'},
    {'ab': '11', 'cd': '10', 'value': '0'},
    {'ab': '10', 'cd': '10', 'value': '1'},
]

// Consider a block diagram with inputs 'c' and 'd' going into a module called "top_module". This "top_module" has four outputs, mux_in[3:0], that connect to a four input mux. The mux takes as input {a,b} and ab = 00 is connected to mux_in[0], ab=01 is connected to mux_in[1], and so in. You are implementing in Verilog just the portion labelled "top_module", such that the entire circuit (including the 4-to-1 mux) implements the K-map.
"
</example>

"""

EXTRA_ORDER_PROMPT = r"""

"""


class TBExtractor:
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
            if output_json_obj["revised_spec"]:
                revised_spec = output_json_obj["revised_spec"]
                logger.info(f"Succeed to parse response, Revised Spec: {revised_spec}")
            else:
                logger.info(f"Failed to parse response, Original Spec: {input_spec}")
                return None
        except json.decoder.JSONDecodeError as e:
            print(f"Json parse error: {e}")
            logger.info(f"Json parse error: {e}")
            print(response)
            return None

        return output_json_obj


