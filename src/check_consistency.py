import json
from pathlib import Path
from typing import Dict, List, Tuple
import argparse
import os
from datetime import datetime

import json
from typing import Dict

from llama_index.core.base.llms.types import ChatMessage, MessageRole
from utils.gen_config import get_llm
from utils.log_utils import get_logger
from utils.prompts import ORDER_PROMPT
from utils.token_counter import TokenCounter, TokenCounterCached
from utils.gen_config import Config
from utils.log_utils import get_logger, set_log_dir, switch_log_to_file
logger = get_logger(__name__)

SYSTEM_PROMPT = """
You are an expert in Python code design. Select the best python code from the following list, remeber the code which have truth table is better than the code which have not truth table.
"""
INIT_EDITION_PROMPT = """

Your task is to review a natural-language problem description, some python code list(index begin from 0) designed to solve the problem , their result is different, please review the python code and the result, and choose the best python code. Important: even  the best python code is still very likely to fail to meet the exact requirements of the problem description, you should also judge if the best python code is matched with the specification. Pay special attention to verifying that the output result conforms to the RTL bit-assignment behavior. If the output depends on bit positions, remember that for a variable declared as x[3:0], x[3] is the most significant (leftmost) bit and x[0] is the least significant (rightmost) bit. For example, if the problem description requires output the first bit of the result, you should output the rightmost bit of the result. To solve the FSM problem, it is necessary to analyze if the number of states is correct, which is very important: if three digits are near to be read, there will be a total of four states (0 digits, 1 digit, 2 digits, 3 digits already received); analyze which state is entered when a 0 is read, and which state is entered when a 1 is read.

You must think step by step to determine whether the python code and the observed input/output behavior matches the expected logic described in the problem description.


<problem_description>
{spec}
</problem_description>
Select the best python code from the following list, remeber the code which have truth table is better than the code which have not truth table. Also check if the output align with the FSM specification. And remeber to do not return any other value like 'X', 'x' and 'd' as output!!! return a dictionary of outputs strictly aligned with the RTL module outputs name and updated states for verification, do not return any other value like 'X', 'x' and 'd' as output! Even if the specification have random value, do not return random value as output since we can not parse them!!!!


<python_code_list>
{python_code_list}
</python_code_list>



[Task]:
1. **Interpret the problem description** and understand the intended combinational logic. 
To complete this task, follow these steps:

1. Analyze the problem description:
   - Identify the key logical operations and expected behavior
   - Determine the expected input/output relationships
   - Note any specific logical constraints or requirements

2. Analyze the I/O data:
   - Parse the JSON data to understand input combinations and their outputs
   - Verify that each input combination has a unique corresponding output
   - Check for any unexpected state-dependent behavior

3. Compare the expected behavior with the observed behavior:
   - Verify that each input combination produces the correct output according to the specification
   - Check that the logical operations are implemented correctly
   - Ensure all specified functionality is demonstrated in the test cases

4. Secondly, analyze the relationship between inputs and outputs: Pay special attention to bit-width and bit-ordering. Examine each input combination and its corresponding output. 
[Very Important]

In RTL descriptions, a signal is typically defined with a range notation like [m:n]:

The first number (m) is the leftmost position in the bit vector
The second number (n) is the rightmost position
String to Bit Position Mapping
Examine each input combination and its corresponding output position:
For descending order [m] where m > n (typical RTL):

If a signal is defined as x[4:0], then the binary value '11100' corresponds to:

x4=1 (leftmost digit in string)
x3=1
x2=1
x1=0
x0=0 (rightmost digit in string)


If a signal is defined as x[3:1], then the binary value '100' corresponds to:

x3=1 (leftmost digit in string)
x2=0
x1=0 (rightmost digit in string)

For codes y[3:1], Y2 is the middle bit.

[Hint]

0. Perform bitwise consistency checks for all 01 sequences: Confirm input/output bit lengths match. Verify no duplicate minterms in truth tables. Cross-check Karnaugh map groupings against standard adjacency rules. When detecting non-standard ordering in inputs, check the order of outputs. 

1. Karnaugh Maps:
example:
// ab
// cd 00 01 11 10
// 00 | 1 | 0 | 1 | 1 |
// 01 | 0 | 1 | 0 | 1 |
// 11 | 1 | 1 | 0 | 0 |
// 10 | 1 | 0 | 0 | 0 |
To interpret the table:
The columns (left to right) represent the values of ab = 00, 01, 11, 10
The rows (top to bottom) represent the values of cd = 00, 01, 11, 10
Each cell contains the function output f(a, b, c, d) for the corresponding combination of a, b, c, and d.
Make sure that the key 'abcd' is constructed with: a and b from the column label (left to right: 00, 01, 11, 10), c and d from the row label (top to bottom: 00, 01, 11, 10), So the top-third cell corresponds to a=1, b=1, c=0, d=0 → '0011'
eg. For a = 1, b = 1, c = 1, d = 0, look at row cd = 10 and column ab = 11; the value is 0, so f(1, 1, 1, 0) = 0.
For a = 1, b = 0, c = 1, d = 0, look at row cd = 10 and column ab = 10; the value is 0, so f(1, 0, 1, 0) = 0. 

3. For finite state machine, the next state is determined by the current state and the input. You need to generate the truth table which includes all the possible combinations of the current state and the input. For example,    
 _TRUTH_TABLE = {{
            '0000': '1',  # S0 + w=0 → S1 → y0 = 1
            '0001': '0',  # S0 + w=1 → S2 → y0 = 0
            '0010': '1',  # S1 + w=0 → S3 → y0 = 1
            '0011': '0',  # S1 + w=1 → S4 → y0 = 0
            '0100': '0',  # S2 + w=0 → S4 → y0 = 0
            '0101': '1',  # S2 + w=1 → S5 → y0 = 1
            '0110': '1',  # S3 + w=0 → S5 → y0 = 1
            '0111': '0',  # S3 + w=1 → S0 → y0 = 0
            
            
        }}


When encountering Karnaugh maps in specifications:
-  Please construct a `_TRUTH_TABLE` dictionary representing the circuit logic, where:
   - Each key is a binary string representing the input combination, ordered using **Gray code** for Karnaugh map alignment.
   Make sure that the key 'abcd' is constructed with: a and b from the column label (left to right: 00, 01, 11, 10), c and d from the row label (top to bottom: 00, 01, 11, 10), So the top-third cell corresponds to a=1, b=1, c=0, d=0 → '0011'.

   - Each value is either 0 or 1, corresponding to the output for that input.
   - Don't-care (`d`) entries should be resolved in a way that simplifies logic (you may assign them to 0).
   - For any unspecified or ambiguous input (e.g., variables named `x` or unused in K-map), default the value to 0.
- Follow these rules strictly:
   - All input variables must be used in the Gray code order to construct the lookup key.
   - If a variable does not appear in the Karnaugh map (e.g., labeled `x` or not mentioned), treat it as `0` during simulation.
   - Only logic lookup is allowed, no procedural conditionals like `if/else` are permitted.

<reasoning>
1. RTL Specification Summary:
   [Briefly summarize the key logical operations and expected behavior]

2. I/O Data Analysis:
   [Describe the observed input/output relationships]

3. Comparison and Mismatches:
   [List and describe any mismatches between the specification and observed behavior]
</reasoning>

3. **Review the testbench** and compare the observed input/output combinations against the expected behavior from the RTL specification.
4. Determine whether the observed behavior **matches** or **does not match** what the specification dictates.
   - If it does not match, **identify** and **describe** the mismatch or possible cause of the discrepancy.
5. Compile the results into the final structure, producing a scenario-by-scenario breakdown:
   - For each scenario (e.g., "Scenario1", "Scenario2", etc.):
     - Provide a short textual explanation of the reasoning (why you believe it matches or not).
     - Indicate "yes" or "no" for `if matches`.
     - If "no", fill in `unmatched action` with a brief explanation of the mismatch or an action you would take to resolve it.

<example>
{example}
</example>
"""





ONE_SHOT_EXAMPLES = r"""
</example>
Example 1:

<example>
    <input_spec>
       
This module collects 6-bit data inputs into 18-bit packets. It implements a state machine with 4 states to collect 3 bytes sequentially. When a data packet with the MSB (bit 5) set is received in the FIRST state, it transitions to collect a complete packet. Once a complete packet is assembled, the valid signal is asserted. The module shifts in each new data input while maintaining previously collected data.
    </input_spec>
 

    <python_code>

class GoldenDUT:
    def __init__(self):
        '''
        Initialize all internal state registers to zero.
        '''
        # State constants
        self.BYTE1 = 0
        self.BYTE2 = 1
        self.BYTE3 = 2
        self.DONE = 3
        
        # State registers
        self.state = 0
        self.out_bytes_r = 0
        
    def load(self, clk, stimulus_dict):
        '''
        Process inputs on clock edge and return outputs
        '''
        # Parse inputs from stimulus dictionary
        in_val = int(stimulus_dict.get('in', '0'), 2)
        reset = int(stimulus_dict.get('reset', '0'), 2)
        
        # Output dictionary
        outputs = {}
        
        # Process on positive clock edge
        if clk == 1:
            # Update out_bytes_r register - shift in new byte
            self.out_bytes_r = ((self.out_bytes_r & 0xFFFF) << 8) | in_val
            
            # State transition logic
            if reset == 1:
                self.state = self.BYTE1
            else:
                # Determine next state
                in3 = (in_val >> 3) & 1
                
                if self.state == self.BYTE1:
                    self.state = self.BYTE2 if in3 else self.BYTE1
                elif self.state == self.BYTE2:
                    self.state = self.BYTE3
                elif self.state == self.BYTE3:
                    self.state = self.DONE
                elif self.state == self.DONE:
                    self.state = self.BYTE2 if in3 else self.BYTE1
        
        # Determine outputs
        done = 1 if self.state == self.DONE else 0
        
        # Only provide valid out_bytes when done
        if done:
            out_bytes = self.out_bytes_r
            outputs['out_bytes'] = format(out_bytes, '024b')
        else:
            # For simulation purposes, return all zeros when not done
            outputs['out_bytes'] = '0' * 24
        
        outputs['done'] = format(done, '01b')
        
        return outputs
    </python_code>

    Example 2:

<example>
    <input_spec>
      This robot controller FSM manages a robot with five states:

FWD: Moving forward
BWD: Moving backward
CHARGE: Charging battery
GRAB_FWD: Grabbing while facing forward
GRAB_BWD: Grabbing while facing backward

The robot transitions between states based on inputs like obstacle detection, battery status, and target detection. It prioritizes battery charging when low, then target grabbing, and finally obstacle avoidance. The outputs indicate the robot's current action (moving forward/backward, charging, or grabbing).
    </input_spec>

    
    
    <python_code>
class GoldenDUT:
    def __init__(self):
        '''
        Initialize all internal state registers to zero.
        Each internal register/state variable must align with the module header.
        Explicitly initialize these states according to the RTL specification.
        '''
        # State parameters
        self.WL = 0
        self.WR = 1
        self.FALLL = 2
        self.FALLR = 3
        self.DIGL = 4
        self.DIGR = 5
        
        # State register
        self.state = 0
        
    def load(self, clk, stimulus_dict):
        '''
        Process inputs according to the FSM logic and return outputs
        '''
        # Parse inputs as binary
        areset = int(stimulus_dict.get('areset', '0'), 2)
        bump_left = int(stimulus_dict.get('bump_left', '0'), 2)
        bump_right = int(stimulus_dict.get('bump_right', '0'), 2)
        ground = int(stimulus_dict.get('ground', '0'), 2)
        dig = int(stimulus_dict.get('dig', '0'), 2)
        
        # Determine next state based on current state and inputs
        if self.state == self.WL:
            if not ground:
                next_state = self.FALLL
            elif dig:
                next_state = self.DIGL
            elif bump_left:
                next_state = self.WR
            else:
                next_state = self.WL
        elif self.state == self.WR:
            if not ground:
                next_state = self.FALLR
            elif dig:
                next_state = self.DIGR
            elif bump_right:
                next_state = self.WL
            else:
                next_state = self.WR
        elif self.state == self.FALLL:
            next_state = self.WL if ground else self.FALLL
        elif self.state == self.FALLR:
            next_state = self.WR if ground else self.FALLR
        elif self.state == self.DIGL:
            next_state = self.DIGL if ground else self.FALLL
        elif self.state == self.DIGR:
            next_state = self.DIGR if ground else self.FALLR
        else:
            next_state = self.WL  # Default case
        
        # Update state on positive clock edge or asynchronous reset
        if clk == 1:
            if areset:
                self.state = self.WL
            else:
                self.state = next_state
        
        # Calculate outputs
        walk_left = 1 if self.state == self.WL else 0
        walk_right = 1 if self.state == self.WR else 0
        aaah = 1 if (self.state == self.FALLL or self.state == self.FALLR) else 0
        digging = 1 if (self.state == self.DIGL or self.state == self.DIGR) else 0
        
        # Return outputs as binary strings
        return {
            'walk_left': format(walk_left, 'b'),
            'walk_right': format(walk_right, 'b'),
            'aaah': format(aaah, 'b'),
            'digging': format(digging, 'b')
        }
    </python_code>

</example>
<example>
    <input_spec>
    Please implements a Mealy machine (where output depends on both state and input) with the following state transition table:
    state_transitions = [
    {
        'current_state': 'S0',
        'input': '00',
        'next_state': 'S0',
        'output': '0'
    },
    {
        'current_state': 'S0',
        'input': '01',
        'next_state': 'S1',
        'output': '0'
    },
    {
        'current_state': 'S0',
        'input': '10',
        'next_state': 'S2',
        'output': '0'
    },
    {
        'current_state': 'S0',
        'input': '11',
        'next_state': 'S3',
        'output': '0'
    },
    {
        'current_state': 'S1',
        'input': '00',
        'next_state': 'S1',
        'output': '0'
    },
    {
        'current_state': 'S1',
        'input': '01',
        'next_state': 'S0',
        'output': '1'
    },
    {
        'current_state': 'S1',
        'input': '10',
        'next_state': 'S3',
        'output': '0'
    },
    {
        'current_state': 'S1',
        'input': '11',
        'next_state': 'S2',
        'output': '0'
    },
    {
        'current_state': 'S2',
        'input': '00',
        'next_state': 'S2',
        'output': '0'
    },
    {
        'current_state': 'S2',
        'input': '01',
        'next_state': 'S3',
        'output': '0'
    },
    {
        'current_state': 'S2',
        'input': '10',
        'next_state': 'S0',
        'output': '1'
    },
    {
        'current_state': 'S2',
        'input': '11',
        'next_state': 'S1',
        'output': '0'
    },
    {
        'current_state': 'S3',
        'input': '00',
        'next_state': 'S3',
        'output': '0'
    },
    {
        'current_state': 'S3',
        'input': '01',
        'next_state': 'S2',
        'output': '0'
    },
    {
        'current_state': 'S3',
        'input': '10',
        'next_state': 'S1',
        'output': '0'
    },
    {
        'current_state': 'S3',
        'input': '11',
        'next_state': 'S0',
        'output': '1'
    }
]
    </input_spec>
    <python_code>

class GoldenDUT:
    def __init__(self):
        '''
        Initialize all internal state registers to zero.
        Each internal register/state variable must align with the module header.
        Explicitly initialize these states according to the RTL specification.
        '''
        # Initialize state to S0 (reset state)
        self.current_state = 'S0'

    def load(self, clk, stimulus_dict: Dict[str, List[str]]):
        '''
        clk: the clock signal, 1 for high, 0 for low.
        Parse inputs from stimulus_dict and convert to binary representation.
        Returns a dictionary of outputs and updated states.
        '''
        # Truth table for state transitions and outputs (Mealy machine)
        _TRUTH_TABLE = {
            'S0_00': {'next_state': 'S0', 'output': '0'},
            'S0_01': {'next_state': 'S1', 'output': '0'},
            'S0_10': {'next_state': 'S2', 'output': '0'},
            'S0_11': {'next_state': 'S3', 'output': '0'},
            'S1_00': {'next_state': 'S1', 'output': '0'},
            'S1_01': {'next_state': 'S0', 'output': '1'},
            'S1_10': {'next_state': 'S3', 'output': '0'},
            'S1_11': {'next_state': 'S2', 'output': '0'},
            'S2_00': {'next_state': 'S2', 'output': '0'},
            'S2_01': {'next_state': 'S3', 'output': '0'},
            'S2_10': {'next_state': 'S0', 'output': '1'},
            'S2_11': {'next_state': 'S1', 'output': '0'},
            'S3_00': {'next_state': 'S3', 'output': '0'},
            'S3_01': {'next_state': 'S2', 'output': '0'},
            'S3_10': {'next_state': 'S1', 'output': '0'},
            'S3_11': {'next_state': 'S0', 'output': '1'}
        }

        # Parse inputs
        areset = int(stimulus_dict['areset'], 2)
        # Combine two input bits into a single key
        in_a = int(stimulus_dict['in_a'], 2)
        in_b = int(stimulus_dict['in_b'], 2)
        in_val = f"{in_a}{in_b}"

        # Handle asynchronous reset
        if areset:
            self.current_state = 'S0'
            return {'out': '0'}

        # Only update state and output on rising clock edge
        if clk:
            # Lookup next state and output based on current state and input
            key = f"{self.current_state}_{in_val}"
            next_state_info = _TRUTH_TABLE[key]
            self.current_state = next_state_info['next_state']
            out_val = next_state_info['output']
            return {'out': out_val}
        
        # On non-rising edge, just return the current output based on current state and input
        key = f"{self.current_state}_{in_val}"
        out_val = _TRUTH_TABLE[key]['output']
        return {'out': out_val}
    </python_code>
</example>

"""



WITH_SIGNAL_PROMPT = """
You are an AI assistant tasked with analyzing the alignment between a Python code implementation and a problem description. There is high probability that the python code is not perfectly matched with the problem description. Your goal is to determine if the implementation correctly matches the expected behavior of the problem description. You will also be given a signal generated by the python code, please analyze the python code and the signal to determine if they correctly implement the behavior described in the problem description.

First, carefully read and understand the following problem description:

<problem_description>
{spec}
</problem_description>

Now, examine the Python code implementation:

<python_code>
{python_code}
</python_code>
To solve the FSM problem, it is necessary to analyze if the number of states is correct, which is very important: if three digits are near to be read, there will be a total of four states (0 digits, 1 digit, 2 digits, 3 digits already received); analyze which state is entered when a 0 is read, and which state is entered when a 1 is read


Next, review the signals generated by this Python code:

<generated_signals>
{signal}
</generated_signals>

Analyze the Python code and the generated signals sample to determine if they correctly implement the behavior described in the problem description. Notably, you only need to modify the python code, do not give any suggestions for the signal. You only need to check the functionality of the code, and the output. Consider the following aspects in your analysis:
1. Does the Python code accurately represent the logic described in the problem description?
2. Do the generated signals match the expected output based on the problem description?
3. Are there any discrepancies between the expected behavior and the actual implementation?
To solve the FSM problem, it is necessary to analyze what states there are, which is very important: if three digits are read, there will be a total of four states (0 digits, 1 digit, 2 digits, 3 digits already received); analyze which state is entered when a 0 is read, and which state is entered when a 1 is read.


Provide a detailed explanation of your analysis, including specific references to parts of the problem description, Python code. 

Here are some examples:

<example>
{example}


</example>
"""


EXAMPLE_OUTPUT_FORMAT_WITH_SIGNAL = {
    "reasoning": "All reasoning steps, think step by step",
    "if_matches": "yes or no, if the python code is perfectly matched with the problem specification",
    "reason_for_mismatch":"the reason for the python code and the signal mismatch with the specification, if if_matches is yes, this field is empty",
    "suggestion":"the python code which is mismatched with the specification, the suggestion for the python code to fix the mismatch, if if_matches is yes, this field is empty"
}

EXTRA_ORDER_PROMPT = """
VERY IMPORTANT: Please only include "reasoning" and "result" in your response.
Do not include any other information in your response, like 'json', 'example', 'Let me analyze','input_spec' or '<output_format>'.
Key instruction: Direct output, no extra comments.
As a reminder, please directly provide the content without adding any extra comments or explanations.
"""

EXAMPLE_OUTPUT_FORMAT = {
    "reasoning": "All reasoning steps, think step by step which scenario is most significant to the functionality of the design",
    "reasoning_for_candidate_python_0":"the reasoning for if the first candidate python code aligns with the specification",
    "reasoning_for_candidate_python_1":"the reasoning for if the second candidate python code aligns with the specification",
    "reasoning_for_candidate_python_2":"the reasoning for if the third candidate python code aligns with the specification",
    "reasoning_for_candidate_python_3":"the reasoning for if the fourth candidate python code aligns with the specification",
    "reasoning_for_candidate_python_4":"the reasoning for if the fifth candidate python code aligns with the specification",
    "best_python_code": "int, 0/1/2/3/4/5,the best python code index ",
    
    
}

ACTION_OUTPUT_PROMPT = r"""
Output after running given action:
<action_output>
{action_output}
</action_output>
"""




class ConsistencyChecker_with_signal:
    def __init__(
        self,
        model: str,
        max_token: int,
        provider: str,
        cfg_path: str,
        top_p: float,
        temperature: float,
        exp_dir: str,
        task_numbers: int,
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
        self.exp_dir = exp_dir



    def get_order_prompt_messages(self) -> List[ChatMessage]:
        """Generate order prompt messages."""
        return [
            ChatMessage(
                    content=ORDER_PROMPT.format(
                        output_format="".join(
                            json.dumps(EXAMPLE_OUTPUT_FORMAT_WITH_SIGNAL, indent=4)
                        )
                    ),
                    role=MessageRole.USER,
                ),
        ]


    def load_input_files(self) -> Tuple[str, str, str]:
        """Load the spec, scenario description and testbench files."""
        with open(f"{self.exp_dir}/spec.txt", "r") as f:
            spec = f.read()

      
        with open(f"{self.exp_dir}/module_header.txt", "r") as f:
            module_header = f.read()
        
        return spec, module_header

    def run(self,python_code:str,signal: str) -> bool:
        """
        Main function to check consistency and fix implementation if needed.
        Returns True if all scenarios match after potential fixes.
        """
        """Single chat interaction to check consistency."""
        #spec, scenario, testbench = self.load_input_files()
        
        if isinstance(self.token_counter, TokenCounterCached):
            self.token_counter.set_enable_cache(True)
        self.token_counter.set_cur_tag(self.__class__.__name__)
        system_prompt = ChatMessage(content=SYSTEM_PROMPT, role=MessageRole.SYSTEM)

        spec,module_header = self.load_input_files()

        init_prompt = ChatMessage(
            content=WITH_SIGNAL_PROMPT.format(
                spec=spec,  python_code=python_code,signal=signal,module_header=module_header,example=ONE_SHOT_EXAMPLES
            ),
            role=MessageRole.USER,
        )

        # Generate response
        messages = [system_prompt, init_prompt] + self.get_order_prompt_messages()
        logger.info(f"Consistency checker input message: {messages}")
        resp, token_cnt = self.token_counter.count_chat(messages)
        logger.info(f"Token count: {token_cnt}")
        logger.info(f"Response: {resp.message.content}")
        
        #response_content = resp.message.content
        try:
                # output_json_obj: Dict = json.loads(response.message.content, strict=False)

                # use this for Deepseek r1 and claude-3-5-sonnet
                # if self.model == "claude-3-5-sonnet-20241022":
                #     output_json_obj: Dict = json.loads("".join(response.choices[0].message.content.split("\n")[1:]), strict=False)
                # else:
                #     output_json_obj: Dict = json.loads(response.choices[0].message.content, strict=False)
                output_json_obj: Dict = json.loads(resp.message.content, strict=False)
                with open(f"{self.exp_dir}/judge_1.txt", "w") as f:
                    f.write(resp.message.content)
                print(f"output_json_obj: {output_json_obj}")
                
                if_matches=True if output_json_obj['if_matches']=='yes' else False
                reason=output_json_obj['reason_for_mismatch']
                suggestion=output_json_obj['suggestion']
                
                return if_matches,reason,suggestion
        except json.decoder.JSONDecodeError as e:
            logger.error(f"Json parse error: {e}")
            logger.error(f"Response: {resp.message.content}")
            return None,None,None


            # Run consistency check again with new implementation
            # Note: You might want to implement a mechanism to use the new file
            # return check_and_fix_implementation(exp_dir, token_counter)

        return if_matches,reason




class ConsistencyChecker:
    def __init__(
        self,
        model: str,
        max_token: int,
        provider: str,
        cfg_path: str,
        top_p: float,
        temperature: float,
        exp_dir: str,
        task_numbers: int,
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
        self.exp_dir = exp_dir



    def get_order_prompt_messages(self) -> List[ChatMessage]:
        """Generate order prompt messages."""
        return [
            ChatMessage(
                    content=ORDER_PROMPT.format(
                        output_format="".join(
                            json.dumps(EXAMPLE_OUTPUT_FORMAT, indent=4)
                        )
                    ),
                    role=MessageRole.USER,
                ),
        ]


    def load_input_files(self) -> Tuple[str, str, str]:
        """Load the spec, scenario description and testbench files."""
        with open(f"{self.exp_dir}/spec.txt", "r") as f:
            spec = f.read()

      
        with open(f"{self.exp_dir}/module_header.txt", "r") as f:
            module_header = f.read()
        
        return spec, module_header

    def run(self,python_code_list:List[str]) -> bool:
        """
        Main function to check consistency and fix implementation if needed.
        Returns True if all scenarios match after potential fixes.
        """
        """Single chat interaction to check consistency."""
        #spec, scenario, testbench = self.load_input_files()
        
        if isinstance(self.token_counter, TokenCounterCached):
            self.token_counter.set_enable_cache(True)
        self.token_counter.set_cur_tag(self.__class__.__name__)
        system_prompt = ChatMessage(content=SYSTEM_PROMPT, role=MessageRole.SYSTEM)

        spec,module_header = self.load_input_files()

        init_prompt = ChatMessage(
            content=INIT_EDITION_PROMPT.format(
                spec=spec,  python_code_list=python_code_list,example=ONE_SHOT_EXAMPLES,module_header=module_header
            ),
            role=MessageRole.USER,
        )

        # Generate response
        messages = [system_prompt, init_prompt] + self.get_order_prompt_messages()
        logger.info(f"Consistency checker input message: {messages}")
        resp, token_cnt = self.token_counter.count_chat(messages)
        logger.info(f"Token count: {token_cnt}")
        logger.info(f"Response: {resp.message.content}")
        
        #response_content = resp.message.content
        try:
                # output_json_obj: Dict = json.loads(response.message.content, strict=False)

                # use this for Deepseek r1 and claude-3-5-sonnet
                # if self.model == "claude-3-5-sonnet-20241022":
                #     output_json_obj: Dict = json.loads("".join(response.choices[0].message.content.split("\n")[1:]), strict=False)
                # else:
                #     output_json_obj: Dict = json.loads(response.choices[0].message.content, strict=False)
                output_json_obj: Dict = json.loads(resp.message.content, strict=False)
                with open(f"{self.exp_dir}/judge_1.txt", "w") as f:
                    f.write(resp.message.content)
                print(f"output_json_obj: {output_json_obj}")
                best_python_code_index=int(output_json_obj['best_python_code'])
                
                return best_python_code_index,output_json_obj
        except json.decoder.JSONDecodeError as e:
            logger.error(f"Json parse error: {e}")
            logger.error(f"Response: {resp.message.content}")
            return None,None


            # Run consistency check again with new implementation
            # Note: You might want to implement a mechanism to use the new file
            # return check_and_fix_implementation(exp_dir, token_counter)

        return best_python_code_index,if_matches



args_dict = {
    # "model": "deepseek-reasoner",
    # "model": "gpt-4o-2024-08-06",
    # "model": "gpt-4o-mini-2024-07-18",
    # "model": "gemini-2.0-flash",
    # "model": "claude-3-5-sonnet-v2@20241022",
    # "model_fixer": "models/gemini-2.0-flash",
    "model": "claude-3-5-sonnet-20241022",
    # "model_fixer": "gpt-4o-2024-08-06",
    # "provider": "anthropic",
    #"provider": "openai",
    "provider": "anthropic",
    # "provider_fixer": "anthropic",
    # "provider_fixer": "openai",
    "temperature": 0,
    "top_p": 1,
    "temperature_sample": 0.3,
    "top_p_sample": 0.95,
    "max_token": 8096,
    # "model": "claude-3-7-sonnet@20250219",
    #"model": "claude-3-5-sonnet-v2@20241022",
    #"provider": "vertexanthropic",
    #"provider": "vertex",
    #"model": "gemini-1.5-flash",
    "provider_fixer": "vertex",
    # "task_numbers": [50],
    "task_numbers": [121,125,130,140,143],
    # "filter_instance": "Prob051|Prob052|Prob053|Prob054|Prob055|Prob101|Prob102|Prob103|Prob104|Prob105",
    # "filter_instance": "Prob092",
    # "filter_instance": "",
    "folder_path": "../verilog-eval/HDLBits/HDLBits_data_backup0304.jsonl",
    "run_identifier": "mismatch_report_for_correctness",
    "key_cfg_path": "../key.cfg",
    "use_golden_ref": True,
    "max_trials": 5,
    "exp_dir": "output_tb_gen_tb_20250406"
}



def main():
    # Example usage
    
    args = argparse.Namespace(**args_dict)
    Config(args.key_cfg_path)
    switch_log_to_file()
    timestamp = datetime.now().strftime("%Y%m%d")
    output_dir = f"{args.run_identifier}_{timestamp}"
    log_dir = f"log_{args.run_identifier}_{timestamp}"
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)
    results=[]
    incorrect_cases=[46, 55, 56, 59, 63, 78, 86, 94, 98, 99, 107,118, 120, 142, 147, 148,  149, 150, 152, 153]
    not_identify_mistake=[]
    wrong_identify_correct_cases=[]
    summary_txt= ""
    for task_number in args.task_numbers:

        set_log_dir(log_dir)
        
        consistency_checker = ConsistencyChecker(args.model, args.max_token, args.provider, args.key_cfg_path, args.top_p, args.temperature, args.exp_dir, task_number)
        unmatch_case = consistency_checker.run()
        if unmatch_case>0:
            
            summary_txt+= f"There are {unmatch_case} unmatch cases for task {task_number}\n"
        else:
           
            summary_txt+= f"All cases match the specification for task {task_number}\n"
        results.append(unmatch_case)
    
        if unmatch_case>0 and task_number not in incorrect_cases:
            wrong_identify_correct_cases.append(task_number)
        if unmatch_case==0 and task_number in incorrect_cases:
            not_identify_mistake.append(task_number)
    
    with open(f"{args.run_identifier}_summary.txt", "w") as f:
        f.write(summary_txt+str(results)+'\n'+str(not_identify_mistake)+'\n'+str(wrong_identify_correct_cases))
    


    

if __name__ == "__main__":
    main()