import json
from typing import Dict

from llama_index.core.base.llms.types import ChatMessage, MessageRole
from utils.gen_config import get_llm
from utils.log_utils import get_logger
from utils.prompts import ORDER_PROMPT
from utils.token_counter import TokenCounter, TokenCounterCached

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are an expert in RTL design and Python programming. You can always write correct Python code to verify sequential RTL functionality. """


GENERATION_PROMPT = """
 You are tasked with analyzing and potentially revising Python code based on an RTL (Register Transfer Level) problem description and comparing it to an existing RTL code implementation. Your goal is to ensure the Python code correctly implements the functionality described in the problem description. If the python code is incorrect, please revise it. Please note that you only need to answer the class 'GoldenDUT' and the function 'init' and 'load', do not answer the head and tail part because they are already provided.

Here are the inputs you will be working with:

<problem_description>
{input_spec}
</problem_description>

<rtl_code>
{rtl_code}
</rtl_code>

<python_code>
{python_code}
</python_code>

Both the RTL and Python implementations are derived from spec.txt, but their output differs, stems from the different logic. Judge which is misaligned with the spec.txt(RTL or Python). One of them must be incorrect—please identify which implementation is incorrect and explain why.
Follow these steps:


1. Carefully read and understand the problem description. Compare the (possibly revised) Python implementation to the provided RTL code. Explain any differences you observe, focusing on:
   - How the Python code may have misinterpreted specifications or tables
   - Differences in bit ordering or logical implementation
   - Any other discrepancies between the two implementations

Remember, the RTL code provided may be correct or incorrect. Your primary task is to ensure the Python code correctly implements the functionality described in the problem description, using the RTL code as a reference for comparison.


2. Analyze the Python code to determine if it correctly implements the functionality described in the problem description. Pay special attention to:
   - Correct interpretation of any tables or specifications in the problem description
   - Proper handling of bit ordering (high bits vs low bits) as typically used in RTL
   - Logical equivalence to the expected behavior



3. Provide your final output in the following format:

<analysis>
[Your detailed analysis of the Python code, including whether it correctly implements the problem description, any modifications made, and explanations of differences between the Python and RTL implementations]
</analysis>



"""

EXAMPLE_OUTPUT_FORMAT = {
    "reasoning": "All reasoning to analyze, reasoning step by step",
    "Misaligned_part":"RTL or Python",
    "revised_python_code": "If modifications were necessary, include the revised Python code here. If no modifications were needed, give the original python code",
}

CLASSIFICATION_1_SHOT_EXAMPLES = """
Here are some examples:
Example 1:
<example> "input_spec": " 
Rule 110 is a one-dimensional cellular automaton with interesting properties (such as being Turing-complete). There is a one-dimensional array of cells (on or off). At each time step, the state of each cell changes. In Rule 110, the next state of each cell depends only on itself and its two neighbours, according to the following table:

[
    {
        "Left[i+1]": "1",
        "Center[i]": "1",
        "Right[i-1]": "1",
        "Center's next state": "0"
    },
    {
        "Left[i+1]": "1",
        "Center[i]": "1",
        "Right[i-1]": "0",
        "Center's next state": "1"
    },
    {
        "Left[i+1]": "1",
        "Center[i]": "0",
        "Right[i-1]": "1",
        "Center's next state": "1"
    },
    {
        "Left[i+1]": "1",
        "Center[i]": "0",
        "Right[i-1]": "0",
        "Center's next state": "0"
    },
    {
        "Left[i+1]": "0",
        "Center[i]": "1",
        "Right[i-1]": "1",
        "Center's next state": "1"
    },
    {
        "Left[i+1]": "0",
        "Center[i]": "1",
        "Right[i-1]": "0",
        "Center's next state": "1"
    },
    {
        "Left[i+1]": "0",
        "Center[i]": "0",
        "Right[i-1]": "1",
        "Center's next state": "1"
    },
    {
        "Left[i+1]": "0",
        "Center[i]": "0",
        "Right[i-1]": "0",
        "Center's next state": "0"
    }
]

In this circuit, create a 512-cell system (q[511:0]), and advance by one time step each clock cycle. The synchronous active high load input indicates the state of the system should be loaded with data[511:0]. Assume the boundaries (q[-1] and q[512], if they existed) are both zero (off).
",
"rtl_code": "
module top_module(
	input clk,
	input load,
	input [511:0] data,
	output reg [511:0] q);
	
	always @(posedge clk) begin
		if (load)
			q <= data;
		else begin
			q <= 
			~((q[$bits(q)-1:1] & q[$bits(q)-1:0] & {q[$bits(q)-2:0], 1'b0}) |
			(~q[$bits(q)-1:1] & ~q[$bits(q)-1:0] & ~{q[$bits(q)-2:0], 1'b0}) |  
			(q[$bits(q)-1:1] & ~q[$bits(q)-1:0] & ~{q[$bits(q)-2:0], 1'b0}) )
			;
		end
	end
endmodule

",
"python_code": "

import json
from typing import Dict, List, Union


class GoldenDUT:
    def __init__(self):
        '''
        Initialize the 512-bit register q to 0
        '''
        self.q = 0

    def _rule110(self, left, center, right):
        '''
        Implement Rule 110 logic for one cell
        '''
        pattern = (left << 2) | (center << 1) | right
        # Rule 110 lookup table
        return 1 if pattern in [3, 5, 6, 7] else 0

    def load(self, clk, stimulus_dict: Dict[str, str]):
        '''
        Process one clock cycle
        '''
        # Convert inputs from binary strings to integers
        load_val = int(stimulus_dict['load'], 2)
        data_val = int(stimulus_dict['data'], 2)

        if clk == 1:
            if load_val:
                # Load new data
                self.q = data_val
            else:
                # Apply Rule 110 to each cell
                new_q = 0
                for i in range(512):
                    # Get left neighbor (0 if i=511)
                    left = (self.q >> (i+1)) & 1 if i < 511 else 0
                    # Get current cell
                    center = (self.q >> i) & 1
                    # Get right neighbor (0 if i=0)
                    right = (self.q >> (i-1)) & 1 if i > 0 else 0
                    # Calculate next state
                    next_state = self._rule110(left, center, right)
                    # Set bit in new state
                    new_q |= (next_state << i)
                self.q = new_q

        # Convert output to 512-bit binary string
        return {'q': format(self.q, '0512b')}

",

"analysis": "The Python returns 1 for pattern 7 (111 - all cells on), but according to the specification, when all three cells are 1, the center's next state should be 0. returns 0 for pattern 1 and 2, but according to the specification, the center's next state should be 1. The Verilog implementation correctly identifies the patterns that should result in 0 (111, 000, 100) using a boolean expression that checks for these specific bit patterns, then inverts the result to get the final output.The python code is incorrect"
"revised_python_code": "


class GoldenDUT:
    def __init__(self):
        '''
        Initialize the 512-bit register q to 0
        '''
        self.q = 0

    def _rule110(self, left, center, right):
        '''
        Implement Rule 110 logic for one cell
        '''
        pattern = (left << 2) | (center << 1) | right
        # Rule 110 lookup table
        return 1 if pattern in [1,2,3, 5, 6] else 0

    def load(self, clk, stimulus_dict: Dict[str, str]):
        '''
        Process one clock cycle
        '''
        # Convert inputs from binary strings to integers
        load_val = int(stimulus_dict['load'], 2)
        data_val = int(stimulus_dict['data'], 2)

        if clk == 1:
            if load_val:
                # Load new data
                self.q = data_val
            else:
                # Apply Rule 110 to each cell
                new_q = 0
                for i in range(512):
                    # Get left neighbor (0 if i=511)
                    left = (self.q >> (i+1)) & 1 if i < 511 else 0
                    # Get current cell
                    center = (self.q >> i) & 1
                    # Get right neighbor (0 if i=0)
                    right = (self.q >> (i-1)) & 1 if i > 0 else 0
                    # Calculate next state
                    next_state = self._rule110(left, center, right)
                    # Set bit in new state
                    new_q |= (next_state << i)
                self.q = new_q

"
 </example>

Example 2:
<example> "input_spec": Consider the follow Moore machine with the diagram described below:

State Transition Table:
{
    'B': {
        'output': 1,
        'transitions': {
            '0': 'A',
            '1': 'B'
        }
    },
    'A': {
        'output': 0,
        'transitions': {
            '0': 'B',
            '1': 'A'
        }
    }
}

Write Verilog implementing this state machine. It should asynchronously
reset into state B if reset if high.

module TopModule (
  input clk,
  input in,
  input areset,
  output out
);

<rtl_code>
module top_module (
	input clk,
	input in,
	input areset,
	output out
);

    parameter A = 1'b0;
    parameter B = 1'b1;

    reg state, next_state;

    always @(posedge clk or posedge areset) begin
        if (areset)
            state <= B;
        else
            state <= next_state;
    end

    always @(*) begin
        case (state)
            A: next_state = in ? A : B;
            B: next_state = in ? B : A;
            default: next_state = B;
        endcase
    end

    assign out = state;

endmodule

</rtl_code>

<python_code>

import json
from typing import Dict, List, Union


class GoldenDUT:
    def __init__(self):
        '''
        Initialize internal state registers
        '''
        self.state = 0  # Initialize state to 0 (State A)
        self.out = 0    # Initialize output to 0

    def load(self, clk, stimulus_dict: Dict[str, str]):
        '''
        Update state machine based on inputs
        '''
        # Convert input binary strings to integers
        areset = int(stimulus_dict['areset'], 2)
        in_val = int(stimulus_dict['in'], 2)

        # Handle asynchronous reset
        if areset == 1:
            self.state = 1  # Reset to state B
            self.out = 1    # Output 1 in state B
        # Process on rising clock edge
        elif clk == 1:
            if self.state == 1:  # In state B
                if in_val == 0:
                    self.state = 0  # Transition to state A
                    self.out = 0    # Output 0 in state A
            else:  # In state A
                if in_val == 0:
                    self.state = 1  # Transition to state B
                    self.out = 1    # Output 1 in state B

        # Return output as binary string
        return {'out': format(self.out, 'b')}

</python_code>
<analysis>
The key difference lies in how they handle state transitions. The Verilog implementation correctly handles both cases (in=0 and in=1) using a ternary operator, while the Python implementation only handles the in=0 case and fails to implement transitions for in=1. This makes the Python version incomplete and incorrect according to the specification. The Verilog version properly implements the state machine where each state has defined transitions for both input values, while the Python version only implements partial transitions, making it behave differently from the specification.
</analysis>
<revised_python_code>
class GoldenDUT:
    def __init__(self):
        '''
        Initialize internal state registers
        '''
        self.state = 0  # Initialize state to 0 (State A)
        self.out = 0    # Initialize output to 0

    def load(self, clk, stimulus_dict: Dict[str, str]):
        '''
        Update state machine based on inputs
        '''
        # Convert input binary strings to integers
        areset = int(stimulus_dict['areset'], 2)
        in_val = int(stimulus_dict['in'], 2)

        # Handle asynchronous reset
        if areset == 1:
            self.state = 1  # Reset to state B
            self.out = 1    # Output 1 in state B
        # Process on rising clock edge
        elif clk == 1:
            if self.state == 0:  # In state A
                if in_val == 1:
                    self.state = 0  # Stay in state A
                else:
                    self.state = 1  # Go to state B
            else:  # In state B
                if in_val == 1:
                    self.state = 1  # Stay in state B
                else:
                    self.state = 0  # Go to state A
            
            # Update output based on current state (Moore machine)
            self.out = self.state

        # Return output as binary string
        return {'out': format(self.out, 'b')}
</revised_python_code>

"""

EXTRA_ORDER_PROMPT = r"""

"""
PythonHeader = """
import json
from typing import Dict, List, Union

"""
CHECKER_TAIL = """
def check_output(stimulus_list_scenario):

    
    tb_outputs = []


    for stimulus_list in stimulus_list_scenario["input variable"]:
        dut = GoldenDUT()


        clock_cycles = stimulus_list['clock cycles']
        clk = 1
        input_vars_list = {k: v for k, v in stimulus_list.items() if k != "clock cycles"}
        output_vars_list = {'clock cycles':clock_cycles}
        for k,v in input_vars_list.items():
            if len(v) < clock_cycles:
                v.extend([v[-1]] * (clock_cycles - len(v)))
                
        clk = 0

        falling_edge_input_vars = {k: '0'*len(v[0]) for k,v in input_vars_list.items()}
            

        

        for i in range(clock_cycles):
            
            input_vars = {k:v[i] for k,v in input_vars_list.items()}
            falling_edge_input_vars = {k: '0'*len(v[i]) for k,v in input_vars_list.items()}
            
            clk=1
            output_vars = dut.load(clk,input_vars)
            clk = 0
            

            output_vars_clk0 = dut.load(clk,falling_edge_input_vars)
            if i>=0:

                for k,v in output_vars.items():
                    if k not in output_vars_list:
                        output_vars_list[k] = []
                    output_vars_list[k].append(v)
            


        tb_outputs.append(output_vars_list)

    return tb_outputs

if __name__ == "__main__":
    stimulus_file_name = "stimulus.json"
    with open(stimulus_file_name, "r") as f:
        stimulus_data = json.load(f)


    if isinstance(stimulus_data, dict):
        stimulus_list_scenarios = stimulus_data.get("input variable", [])
    else:
        stimulus_list_scenarios = stimulus_data

    outputs=[]
    for stimulus_list_scenario in stimulus_list_scenarios:
        outputs.append( check_output(stimulus_list_scenario))
    with open(stimulus_file_name, "w") as f:
        json.dump(stimulus_list_scenarios, f, indent=4)

    print(json.dumps(outputs, indent=2))





"""
CMB_CHECKER_TAIL = """
def check_output(stimulus):

    dut = GoldenDUT()


        

    return dut.load(stimulus)

if __name__ == "__main__":

    with open("stimulus.json", "r") as f:
        stimulus_data = json.load(f)

    stimulus_list = []
    for stimulus in stimulus_data:
        stimulus_list.append(stimulus['input variable'])

    tb_outputs = []
    for stimulus in stimulus_list:
        scenario_outputs=[]
        for cycle in stimulus:

            outputs = check_output(cycle)
            scenario_outputs.append(outputs)
        tb_outputs.append(scenario_outputs)


    

    print(json.dumps(tb_outputs, indent=2))


"""



class JudgeForRTL:
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

    def run(self, input_spec: str,rtl_code: str,python_code: str, circuit_type: str) -> Dict:
        # self.token_counter.reset()
        if isinstance(self.token_counter, TokenCounterCached):  
            self.token_counter.set_enable_cache(True)
        print(f"Setting token counter tag to {self.__class__.__name__}")
        self.token_counter.set_cur_tag(self.__class__.__name__)
        msg = [
            ChatMessage(content=SYSTEM_PROMPT, role=MessageRole.SYSTEM),
            ChatMessage(
                content=GENERATION_PROMPT.format(
                    input_spec=input_spec, example_prompt=CLASSIFICATION_1_SHOT_EXAMPLES,rtl_code=rtl_code,python_code=python_code
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

            revised_python_code = output_json_obj["revised_python_code"]
            if circuit_type == "CMB":
                python_code = PythonHeader + revised_python_code + CMB_CHECKER_TAIL
            else:
                python_code = PythonHeader + revised_python_code + CHECKER_TAIL
            logger.info(f"Succeed to parse response, Revised Python Code: {revised_python_code}")
        except json.decoder.JSONDecodeError as e:
            print(f"Json parse error: {e}")
            logger.info(f"Json parse error: {e}")
            print(response)
            return None

        return python_code, output_json_obj["Misaligned_part"]


