import json
from typing import Dict

from llama_index.core.base.llms.types import ChatMessage, ChatResponse, MessageRole
from utils.gen_config import get_llm
from utils.log_utils import get_logger
from utils.prompts import ORDER_PROMPT
from utils.token_counter import TokenCounter, TokenCounterCached
from pydantic import BaseModel

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are an expert in RTL design and Python programming. You are working on solve a python problem. If the problem is related to finite state machine or FSM, you must generate the truth table for the state transitions and then use the truth table to generate the python code."""
GENERATION_PROMPT = """
You are tasked with implementing a Python class named "GoldenDUT" that realizes the functionality described in a hardware language problem. Your implementation should accurately reflect the behavior specified in the RTL (Register-Transfer Level) description provided. The functional interface variable and return value's case sensitivity and names must exactly match the definitions in the module header!!  Here is the problem specification:
<description>
{description}
</description>
 If the problem is related to finite state machine or FSM, you must generate the truth table for the state transitions and then use the truth table to generate the python code.
<module_header>
{module_header}
</module_header>

Your task is to implement the GoldenDUT class with two methods: __init__ and load. Follow these instructions carefully:

1. Implementing the __init__ method:
   - Initialize all internal state registers.
   - Each internal register/state variable must align with the module header in the problem specification.
    - Use the exact method signature provided:
     ```python
     def __init__(self):
         '''
         Initialize all internal state registers to **zero**. It is very important and you must do this. No matter what the initial value is in the problem specification.
         Each internal register/state variable must align with the **module header**.
         '''
     ```

2. Implementing the load method:
   - Use the exact method signature provided:
     ```python
     def load(self, clk, stimulus_dict: Dict[str, List[str]]):
         '''
         clk: the clock signal, 1 for high, 0 for low. return different output for low and high clk based on the current state and input.
         You will receive a dictionary of input variables which all all  binary string.
          Parse each input variable: You must parse each input variable and convert it from a string into its binary representation. All register/state variable must align with the **module header**. eg: S = stimulus_dict['S'], S=int(S,2). Important: For subsequent unified reading and calculation, it must be binary rather than other numeral systems (or bases). It must be converted to binary; converting it to any other base—like S=int(S,16) is not allowed!!!
    0. [Important] For read and output variable, you should know that for hardware language, the rightmost bit is [0], the leftmost bit is [n-1].So if you need to read r2, please use r2=r>>2&1 or output x[3], please use x_3=x>>3&1 instead of x[3].
       1. [Important] For any  problem related to the finite state machine problem, like {{'from': 'A', 'input': 'r1=0,r2=0,r3=0', 'to': 'A'}}, you must analyze the state transition table and write python code with the _TRUTH_TABLE dictionary 
        eg.  _TRUTH_TABLE = {{
    BYTE1: {{ True:  BYTE2,
             False: BYTE1 }},
    BYTE2: {{ True:  BYTE3,
             False: BYTE3 }},   
    BYTE3: {{ True:  DONE,
            False: DONE }},
    DONE:  {{ True:  BYTE2,
             False: BYTE1 }},
}} to solve the problem, the key is the current state and the input, the value is the next state and the output. Then read the table and return the output based on the current state and input. To solve the FSM problem, it is necessary to analyze what states there are, which is very important: if three digits are read, there will be a total of four states (0 digits, 1 digit, 2 digits, 3 digits already received); analyze which state is entered when a 0 is read, and which state is entered when a 1 is read. 
    2. [Important] For the output, you must return string includes only 1 and 0. To note that if the output could be random or not be clarified in the problem specification,  you must return  string of 'x' as output, the length of the output must be the same as the width in the module header.!!! 
    3. [Important] For load, you must convert the string to binary representation, other based like hex is not allowed. For read and output variable, you should know that for hardware language, the rightmost bit is [0], the leftmost bit is [n-1].So if you need to read r2, please use r2=r>>2&1 or output x[3], please use x_3=x>>3&1 instead of x[3]. For output, please use the format(x, 'b') to convert the integer to a 2-bit binary string. So the overall structure is: use int(n, 2) to parse the string as a binary number, perform your operations, and then use: print(format(n, '(width)b')) to output the binary representation with the specified bit-width.
    4. [Important] if the code have truth table, you must return the output directly based on the truth table. 


    [Important]return a dictionary of outputs strictly aligned with the RTL module outputs name and updated states for verification, The case sensitivity and names must exactly match the definitions in the module header!! To note that if the output could be random or not be clarified in the problem specification,  you must return  string of 'x' as output, the length of the output must be the same as the width in the module header.!!! if the code have truth table, you must return the output directly based on the truth table.
 
          '''

   - Implement the signal loading and state update logic based on the RTL specification.
   - Parse each input variable from the stimulus_dict and convert it to the appropriate type.
   - Perform RTL state updates according to the specification.
   - Return a dictionary of outputs aligned with the RTL module outputs and updated states.



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




instructions = r"""
0. "The output bit should be set the cycle after \[condition\]" means the output bit will be set immediately(same cycle) after the condition is met.
1. **Important**

### 1. Data structure transfer
In RTL descriptions, a signal is typically defined with a range notation like \[m:n\]: If a signal is defined as x\[3:1\], then the binary value '100' corresponds to:

x\[3\]=1 (leftmost digit in string)
x\[2\]=0
x\[1\]=0 (rightmost digit in string)
2. the first 1 bit means the rightmost bit which value is 1, the second 1 bit means the second rightmost bit which value is 1, and so on.
- Add comments to explain complex logic or important implementation details.

Please provide your complete implementation of the GoldenDUT class, including both the __init__ and load methods, adhering to the RTL specification and the guidelines provided above. Write your implementation inside <implementation> tags.
- Use masking and formatting for fixed-width bit simulation.
- Perform logic by converting binary strings to integers.
- Emulate registers with Python classes and state updates.
- Handle two's complement for signed numbers.
- Structure simulation loops like RTL clock cycles.

"""


EXAMPLE_OUTPUT_FORMAT = {
    "reasoning": "All reasoning steps and advices to generate the python code of the GoldenDUT class",
    "the_truth_table": "The truth table for the state transitions",
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


code_context = """
Please provide code that should be inserted between the two string variables <header>{PythonHeader}</header> and <tail>{CHECKER_TAIL}</tail>.
The code you generate will go after <header> and before <tail>.
Do not include the content of <header> or <tail>; just generate the code that goes in between.

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
        #First, we need to define the truth table for the state transitions
        _TRUTH_TABLE = {
    BYTE1: { True:  BYTE2,
             False: BYTE1 },
    BYTE2: { True:  BYTE3,
             False: BYTE3 },   
    BYTE3: { True:  DONE,
             False: DONE },
    DONE:  { True:  BYTE2,
             False: BYTE1 },
}
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
                
                self.state = _TRUTH_TABLE[self.state][in3]
        
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
    Design a Finite State Machine (FSM) that controls traffic lights at a T-junction with a main road and a side road. The system should implement the following behavior:

The default state (A) is GREEN for the main road and RED for the side road
When a vehicle is detected on the side road (sensor = 1), the FSM transitions to a YELLOW state (B) for the main road
After the YELLOW state, the FSM transitions to a state (C) where the side road gets GREEN and the main road gets RED
The side road stays GREEN as long as the sensor detects vehicles (sensor = 1)
Once no vehicles are detected on the side road (sensor = 0), the FSM transitions back to the default state through a YELLOW state (D) for the side road

The FSM has a synchronous reset signal that resets to state A.
The state transitions can be described as follows:
state_transitions = [
    {'from': 'A', 'input': 'sensor=0', 'to': 'A'},
    {'from': 'A', 'input': 'sensor=1', 'to': 'B'},
    {'from': 'B', 'input': 'timer=0', 'to': 'B'},
    {'from': 'B', 'input': 'timer=1', 'to': 'C'},
    {'from': 'C', 'input': 'sensor=1', 'to': 'C'},
    {'from': 'C', 'input': 'sensor=0', 'to': 'D'},
    {'from': 'D', 'input': 'timer=0', 'to': 'D'},
    {'from': 'D', 'input': 'timer=1', 'to': 'A'}
]
    </input_spec>
    <python_code>
    from typing import Dict, List

class GoldenDUT:
    def __init__(self):
        '''
        Initialize all internal state registers to zero.
        Each internal register/state variable must align with the module header.
        Explicitly initialize these states according to the RTL specification.
        '''
        # Initialize the state register (using 2 bits for 4 states)
        self.state = 0  # State A = 0, B = 1, C = 2, D = 3
        
        # Define simple truth table for state transitions and outputs
        
    
    def load(self, clk, stimulus_dict: Dict[str, List[str]]):
        '''
        clk: the clock signal, 1 for high, 0 for low
        stimulus_dict: Dictionary containing input signals as lists of strings
        Returns a dictionary of the outputs aligned with the RTL module outputs
        '''
        # Parse inputs
        reset = int(stimulus_dict['reset'], 2)
        sensor = int(stimulus_dict['sensor'], 2)
        timer = int(stimulus_dict['timer'], 2)
        self._TRUTH_TABLE = {
            # State A: Main=GREEN, Side=RED
            0: {
                0: {'next_state': 0, 'main_light': '10', 'side_light': '00'},  # sensor=0
                1: {'next_state': 1, 'main_light': '10', 'side_light': '00'}   # sensor=1
            },
            # State B: Main=YELLOW, Side=RED
            1: {
                0: {'next_state': 1, 'main_light': '01', 'side_light': '00'},  # timer=0
                1: {'next_state': 2, 'main_light': '01', 'side_light': '00'}   # timer=1
            },
            # State C: Main=RED, Side=GREEN
            2: {
                0: {'next_state': 3, 'main_light': '00', 'side_light': '10'},  # sensor=0
                1: {'next_state': 2, 'main_light': '00', 'side_light': '10'}   # sensor=1
            },
            # State D: Main=RED, Side=YELLOW
            3: {
                0: {'next_state': 3, 'main_light': '00', 'side_light': '01'},  # timer=0
                1: {'next_state': 0, 'main_light': '00', 'side_light': '01'}   # timer=1
            }
        }
        
        # State transition logic (on rising edge of clock)
        if clk == 1:
            if reset == 1:  # Synchronous reset
                self.state = 0  # Reset to state A
            else:
                # Get the appropriate input for current state
                input_value = 0
                if self.state == 0 or self.state == 2:  # States A and C use sensor
                    input_value = sensor
                elif self.state == 1 or self.state == 3:  # States B and D use timer
                    input_value = timer
                
                # Update state based on truth table
                self.state = self._TRUTH_TABLE[self.state][input_value]['next_state']
        
        # Determine current outputs based on state (use any input, output is the same)
        outputs = self._TRUTH_TABLE[self.state][0]
        
        return {
            'main_light': outputs['main_light'],
            'side_light': outputs['side_light']
        }
    </python_code>
</example>



    Example 3:

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
        _TRUTH_TABLE = {{
            self.WL: {
                "ground_False": self.FALLL,
                "dig_True": self.DIGL,
                "bump_left_True": self.WR,
                "default": self.WL
            },
            self.WR: {
                "ground_False": self.FALLR,
                "dig_True": self.DIGR,
                "bump_right_True": self.WL,
                "default": self.WR
            },
            self.FALLL: {
                "ground_True": self.WL,
                "default": self.FALLL
            },
            self.FALLR: {
                "ground_True": self.WR,
                "default": self.FALLR
            },
            self.DIGL: {
                "ground_True": self.DIGL,
                "default": self.FALLL
            },
            self.DIGR: {
                "ground_True": self.DIGR,
                "default": self.FALLR
            }
        }
        if bump_left == 1:
            input_value = "bump_left_True"
        elif bump_right == 1:
            input_value = "bump_right_True"
        elif ground == 1:
            input_value = "ground_True"
        elif dig == 1:
            input_value = "dig_True"
            
        
        # Update state on positive clock edge or asynchronous reset
        if clk == 1:
            if areset:
                self.state = self.WL
            else:
                self.state = _TRUTH_TABLE[self.state][input_value]
        
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
Example 4:
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
            # return the out according to the Truth table
            return {'out': _TRUTH_TABLE[key]['output']}
        
        # On non-rising edge, just return the  output based on current state and input
        key = f"{self.current_state}_{in_val}"
        # return the out according to the Truth table
    
        return {'out': _TRUTH_TABLE[key]['output']}
    </python_code>
</example>

"""



ONE_SHOT_EXAMPLES_old = r"""
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
        print(f"===py_output===\n{py_output}")

        with open(python_path, "w") as f:
            f.write(py_output)
        print("saved to ",python_path)

        return True, gen_python_code
