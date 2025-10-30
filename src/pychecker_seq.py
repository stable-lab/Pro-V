import json
from typing import Dict

from llama_index.core.base.llms.types import ChatMessage, ChatResponse, MessageRole
from utils.gen_config import get_llm
from utils.log_utils import get_logger
from utils.prompts import ORDER_PROMPT
from utils.token_counter import TokenCounter, TokenCounterCached
from pydantic import BaseModel

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are an expert in RTL design and Python programming. You can always write correct Python code to verify sequential RTL functionality."""
GENERATION_PROMPT = """
You are tasked with implementing a Python class named "GoldenDUT" that realizes the functionality described in a hardware language problem. Your implementation should accurately reflect the behavior specified in the RTL (Register-Transfer Level) description provided. Here is the RTL specification:
<description>
{description}
</description>

<module_header>
{module_header}
</module_header>

Your task is to implement the GoldenDUT class with two methods: __init__ and load. Follow these instructions carefully:

1. Implementing the __init__ method:
   - Initialize all internal state registers.
   - Each internal register/state variable must align with the module header in the RTL specification.
   - Explicitly initialize these states according to the RTL specification.
   - Use the exact method signature provided:
     ```python
     def __init__(self):
         '''
         Initialize all internal state registers to **zero**. It is very important and you must do this. No matter what the initial value is in the RTL specification.
         Each internal register/state variable must align with the module header.
         Explicitly initialize these states according to the RTL specification.
         '''
     ```

2. Implementing the load method:
   - Use the exact method signature provided:
     ```python
     def load(self, clk, stimulus_dict: Dict[str, List[str]]):
         '''
         clk: the clock signal, 1 for high, 0 for low
          Parse each input variable: You must generate a Python dictionary that decodes a binary string into the corresponding RTL signal assignments by associating each bit with its correct index based on the signal's declared range.
like:
1. in= stimulus_dict\["in"\]in_dict = {{f"\[{{msb - i}}\]": int(b) for i, b in enumerate(in)}}. In RTL descriptions, a signal is typically defined with a range notation like \[m:n\]:

The first number (m) is the leftmost position in the bit vector
The second number (n) is the rightmost position
String to Bit Position Mapping
Examine each input combination and its corresponding output position:
For descending order [m] where m > n (typical RTL):

If a signal is defined as x[4:0], then the binary value '11100' corresponds to:

x[4]=1 (leftmost digit in string)
x[3]=1
x[2]=1
x[1]=0
x[0]=0 (rightmost digit in string)
for module top_module (
    input  logic [msb:lsb] x,
    input  logic       w,
    output logic       Y0
);
 x= stimulus_dict\["x"\]\n x_dict = {{f"\[{{msb - i}}\]": int(b) for i, b in enumerate(x)}}. 

    Please note all the input variables names strictly align with the RTL module head.
    Returns a dictionary of the outputs strictly aligned with the RTL module outputs name and updated states for verification.
    You must return string includes only 1 and 0, do not return any other value like 'X', 'x' and 'd'
    
         stimulus_dict: a dictionary formatted not include clock cycles as follows:
         {{"input_variable_name1": (a binary sequence string)input_variable_value1,
         "input_variable_name2": (a binary sequence string)input_variable_value2,
         "input_variable_name3": (a binary sequence string)input_variable_value3}}
         Parse each input variable and use it to perform RTL state updates.
         Please note input variable is in string format and you need to convert it to the corresponding type.
         Returns a dictionary of the outputs aligned with the RTL module outputs and updated states for verification. The format of the output dictionary is as follows:
         {{"output_variable_name1": (a binary sequence string)output_variable_value1,
         "output_variable_name2": (a binary sequence string)output_variable_value2,
         "output_variable_name3": (a binary sequence string)output_variable_value3}}
         '''
     ```
   - Implement the signal loading and state update logic based on the RTL specification.
   - Parse each input variable from the stimulus_dict and convert it to the appropriate type.
   - Perform RTL state updates according to the specification.
   - Return a dictionary of outputs aligned with the RTL module outputs and updated states.
   # Python Implementations for Logic Operations

| Logic Operation | Verilog/HDL | Python Implementation |
|-----------------|-------------|------------------------|
| NOT | `z = ~a` | `z = (~a) & 1` |
| AND | `z = a & b` | `z = a & b` |
| OR | `z = a \| b` | `z = a \| b` |
| XOR | `z = a ^ b` | `z = a ^ b` |
| NAND | `z = ~(a & b)` | `z = (~(a & b)) & 1` |
| NOR | `z = ~(a \| b)` | `z = (~(a \| b)) & 1` |
| XNOR | `z = ~(a ^ b)` | `z = (~(a ^ b)) & 1` |
| Reduction NOR | `z = ~\|s` | `z = (~(s[0] \| s[1] \| s[2])) & 1` |
| Reduction NAND | `z = ~&s` | `z = (~(s[0] & s[1] & s[2])) & 1` |
| Reduction OR | `z = \|s` | `z = s[0] \| s[1] \| s[2]` |
| Reduction AND | `z = &s` | `z = s[0] & s[1] & s[2]` |
| Reduction XOR | `z = ^s` | `z = s[0] ^ s[1] ^ s[2]` |
| Reduction XNOR | `z = ~^s` | `z = (~(s[0] ^ s[1] ^ s[2])) & 1` |
| Bit shifting left | `z = a << 2` | `z = (a << 2) & 0xFF` |
| Bit shifting right | `z = a >> 2` | `z = a >> 2` |

Please provide your complete implementation of the GoldenDUT class, including both the __init__ and load methods, adhering to the RTL specification and the guidelines provided above. 

### 3. Helper methods (optional)

You may implement additional helper methods if needed to organize your code clearly.

## Important RTL-to-Python Simulation Considerations:

To accurately replicate RTL behavior in Python, explicitly handle the following:

<instructions>
{instructions}
</instructions>
---

Additional information for your implementation:



---
{code_context}
Python implementation examples (GoldenDUT):

{examples_prompt}
"""




instructions = """
1. [Important]
# Python Implementations for Logic Operations

| Logic Operation | Verilog/HDL | Python Implementation |
|-----------------|-------------|------------------------|
| NOT | `z = ~a` | `z = (~a) & 1` |
| AND | `z = a & b` | `z = a & b` |
| OR | `z = a \| b` | `z = a \| b` |
| XOR | `z = a ^ b` | `z = a ^ b` |
| NAND | `z = ~(a & b)` | `z = (~(a & b)) & 1` |
| NOR | `z = ~(a \| b)` | `z = (~(a \| b)) & 1` |
| XNOR | `z = ~(a ^ b)` | `z = (~(a ^ b)) & 1` |
| Reduction NOR | `z = ~\|s` | `z = (~(s[0] \| s[1] \| s[2])) & 1` |
| Reduction NAND | `z = ~&s` | `z = (~(s[0] & s[1] & s[2])) & 1` |
| Reduction OR | `z = \|s` | `z = s[0] \| s[1] \| s[2]` |
| Reduction AND | `z = &s` | `z = s[0] & s[1] & s[2]` |
| Reduction XOR | `z = ^s` | `z = s[0] ^ s[1] ^ s[2]` |
| Reduction XNOR | `z = ~^s` | `z = (~(s[0] ^ s[1] ^ s[2])) & 1` |
| Bit shifting left | `z = a << 2` | `z = (a << 2) & 0xFF` |
| Bit shifting right | `z = a >> 2` | `z = a >> 2` |
2. ## Summary

- Use masking and formatting for fixed-width bit simulation.
- Perform logic by converting binary strings to integers.
- Emulate registers with Python classes and state updates.
- Handle two’s complement for signed numbers.
- Structure simulation loops like RTL clock cycles.

"""


EXAMPLE_OUTPUT_FORMAT = {
    "reasoning": "All reasoning steps and advices to generate the python code of the GoldenDUT class",
    "python_code": "The python code of the GoldenDUT class",
}

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
                
        

        for i in range(clock_cycles):
            input_vars = {k:v[i] for k,v in input_vars_list.items()}

            output_vars = dut.load(clk,input_vars)
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


code_context = """
Please provide code that should be inserted between the two string variables <header>{PythonHeader}</header> and <tail>{CHECKER_TAIL}</tail>.
The code you generate will go after <header> and before <tail>.
Do not include the content of <header> or <tail>; just generate the code that goes in between.

"""


ONE_SHOT_EXAMPLES = r"""
Here are some examples of the GoldenDUT python code generation:

Example 0:
<example>
    <input_spec>


 There is a one-dimensional array of cells (on or off). At each time step, the state of each cell changes. In Rule 110, the next state of each cell depends only on itself and its two neighbours, according to the following table:
// Left | Center | Right | Center's next state
// 1 | 1 | 1 | 0
// 1 | 1 | 0 | 0
// 1 | 0 | 1 | 1
// 1 | 0 | 0 | 1
// 0 | 1 | 1 | 1
// 0 | 1 | 0 | 1
// 0 | 0 | 1 | 1
// 0 | 0 | 0 | 0 
// In this circuit, create a 512-cell system (q[511:0]), and advance by one time step each clock cycle. The synchronous active high load input indicates the state of the system should be loaded with data[511:0]. Assume the boundaries (q[-1] and q[512]) are both zero (off).
    </input_spec>
   <python_code>
  
class GoldenDUT:
    def __init__(self):
        '''
        Initialize 512-bit register for cell states
        '''
        self.q = 0  # 512-bit register initialized to 0

    def load(self, clk, stimulus_dict: Dict[str, str]):
        '''
        Process one clock cycle matching the Verilog implementation
        '''
        # Convert input signals from binary strings to integers
        load_en = int(stimulus_dict['load'], 2)
        data = int(stimulus_dict['data'], 2)

        if clk == 1:  # On rising edge
            if load_en:
                self.q = data  # Load new data
            else:
                # Get the shifted versions of q
                q_current = self.q
                q_left = (q_current >> 1) & ((1 << 512) - 1)  # q[$bits(q)-1:1]
                q_right = ((q_current << 1) & ((1 << 512) - 1))  # {q[$bits(q)-2:0], 1'b0}

                            # Implement the boolean logic from Verilog truth table for cellular automaton update
                # The input states are from three neighbors: left, center, and right
                # The truth table shows when the center bit should be 1 in the next state

                # term1: Left=1, Center=1, Right=1 → Next=0 → must exclude this case
                term1 = q_left & q_current & q_right  # This is a pattern we want to turn OFF (will be filtered later)

                 # term3: Left=1, Center=1, Right=0 → Next=0 → must exclude this case
                # This is another invalid pattern for the next-state to be 1
                term2 = (q_left & q_current & ~q_right) & ((1 << 512) - 1)


                # term2: Left=0, Center=0, Right=0 → Next=0 → must exclude this case
                # (~q_left & ~q_current & ~q_right) captures this pattern
                term3 = (~q_left & ~q_current & ~q_right) & ((1 << 512) - 1)

               
                # Combine all patterns that should NOT result in a 1 output
                # Then invert (~) to get the valid positions for next-state=1
                # Mask with (1 << 512) - 1 to limit the bit-width to 512
                self.q = ~(term1 | term2 | term3) & ((1 << 512) - 1)

        # Return output as 512-bit binary string
        return {'q': format(self.q, '0512b')}

    </python_code>
Example 1:

<example>
    <input_spec>

This is a sequential circuit. It samples the value of input a on the rising edge of clk, and assigns that value directly to output q. The output holds its value between clock edges.

// time clk a q
// 0ns 0 x x
// 5ns 1 1 x
// 10ns 0 1 x
// 15ns 1 1 1
// 20ns 0 1 1
// 25ns 1 0 0
// 30ns 0 0 0
// 35ns 1 1 1
// 40ns 0 1 1
// 45ns 1 1 1
// 50ns 0 1 1
// 55ns 1 0 0
// 60ns 0 0 0
// 65ns 1 1 1
// 70ns 0 1 1
// 75ns 1 0 0
// 80ns 0 0 0
// 85ns 1 1 1
// 90ns 0 1 1




    </input_spec>
    <module_header>
   module top_module (
	input clk,
	input a, 
	output reg q
);
    </module_header>
    <reasoning>
    You can oberservation that on the upper edge of the clock, the output q is always the same as the input a.
    </reasoning>
    <python_code>
    class GoldenDUT:
    def __init__(self):
        '''
        Initialize internal state registers
        '''
        self.q = 0  # Initialize output q to 0

    def load(self, clk, stimulus_dict: Dict[str, str]):
        '''
        Update state on rising edge of clock based on input a
        '''
        # Convert input binary string to integer
        a_val = int(stimulus_dict['a'], 2)

        # On rising edge of clock
        if clk == 1:
            self.q = a_val  # Directly sample a

        # Convert output to binary string
        return {'q': format(self.q, 'b')}

    </python_code>
</example>

Example 2:

<example>
    <input_spec>
Design a Moore state machine that checks the parity of a serial bit stream input x.

The machine processes one bit per clock cycle, and outputs z as follows:

If the number of 1s seen so far (including the current input) is even, output z = 1.

Otherwise, output z = 0.

The machine has an asynchronous active-high reset signal areset:

When areset is high, the machine resets to the initial state (which assumes zero 1s have been received so far → even parity → z = 1).

    </input_spec>
    <module_header>
 module top_module (
    input clk,
    input areset,
    input x,
    output z
);
    </module_header>
    <python_code>
   class GoldenDUT:
    def __init__(self):
        '''
        Initialize state variables:
        - state: FSM state (0=EVEN, 1=ODD)
        - z: output bit
        '''
        self.state = 0  # Initial state is EVEN (0)
        self.z = 0      # Initial output is 0

    def load(self, clk: int, stimulus_dict: dict):
        '''
        Process one clock cycle of the parity checker state machine
        '''
        # Convert input signals from binary strings to integers
        areset = int(stimulus_dict['areset'], 2)
        x = int(stimulus_dict['x'], 2)
        
        # Handle asynchronous reset
        if areset == 1:
            self.state = 0  # EVEN state
            self.z = 1      # z=1 when state=EVEN
        # Process on rising clock edge
        elif clk == 1:
            if self.state == 0:  # EVEN state
                if x == 1:
                    self.state = 1  # Move to ODD state
            else:  # ODD state
                if x == 1:
                    self.state = 0  # Move to EVEN state
            
            # Output logic (Moore: output depends only on the state)
            self.z = 1 if self.state == 0 else 0  # z=1 when state=EVEN

        # Return output as binary string
        return {'z': format(self.z, 'b')}
    </python_code>
</example>

"""


class PyOutputFormat(BaseModel):
    reasoning: str
    python_code: str


class PyChecker_SEQ:
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

    def reset(self):
        self.history = []

    def parse_output(self, response: ChatResponse) -> PyOutputFormat:
        try:
            output_json_obj: Dict = json.loads(response.message.content, strict=False)
            ret = PyOutputFormat(
                reasoning=output_json_obj["reasoning"],
                python_code=output_json_obj["python_code"],
            )
        except json.decoder.JSONDecodeError as e:
            ret = PyOutputFormat(
                reasoning=f"Json Decode Error: {str(e)}", python_code=""
            )
        return ret

    def run(
        self,
        problem_description: str,
        header: str,
        python_path: str,
        circuit_type: str = "SEQ",
    ) -> str:
        """Generate Python checker code for the given problem

        Args:
            problem_description: Problem description text
            checker_spec: Checker specification text
            python_rules: Optional Python rules/guidelines

        Returns:
            Tuple[bool, str]: (success, generated code)
        """
        Code_Context = code_context.format(
            PythonHeader=PythonHeader,
            CHECKER_TAIL=CHECKER_TAIL,
        )
        prompt = GENERATION_PROMPT.format(
            description=problem_description,
            module_header=header,
            instructions=instructions,
            examples_prompt=ONE_SHOT_EXAMPLES,
            code_context=Code_Context,
        )

        messages = [
            ChatMessage(content=SYSTEM_PROMPT, role=MessageRole.SYSTEM),
            ChatMessage(content=prompt, role=MessageRole.USER),
            ChatMessage(
                content=ORDER_PROMPT.format(
                    output_format="".join(json.dumps(EXAMPLE_OUTPUT_FORMAT, indent=4))
                ),
                role=MessageRole.USER,
            ),
        ]

        response, token_cnt = self.token_counter.count_chat(messages)
        py_output = (
            PythonHeader + "\n" + self.parse_output(response).python_code + CHECKER_TAIL
        )
        gen_python_code = self.parse_output(response).python_code
        logger.info(f"Token count: {token_cnt}")
        logger.info(f"Response: {response.message.content}")

        with open(python_path, "w") as f:
            f.write(py_output)

        return True, gen_python_code
