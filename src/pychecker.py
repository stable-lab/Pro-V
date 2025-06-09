import json
from typing import Dict

from llama_index.core.base.llms.types import ChatMessage, ChatResponse, MessageRole
from utils.gen_config import get_llm
from utils.log_utils import get_logger
from utils.prompts import ORDER_PROMPT
from utils.token_counter import TokenCounter, TokenCounterCached
from pydantic import BaseModel

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are an expert in RTL design and Python programming. You can always write correct Python code to verify RTL functionality."""
GENERATION_PROMPT =r"""
You are tasked with implementing a Python class named "GoldenDUT" that realizes the functionality described in a hardware language problem. Your implementation should accurately reflect the behavior specified in the RTL (Register-Transfer Level) description provided. Here is the RTL specification:
<description>
{description}
</description>

<module_header>
{module_header}
</module_header>

You will receive input stimuli formatted explicitly as JSON:

{{
  "scenario": "scenario_name(not include any Punctuation)",
  "input variable": [
    {{"variable_name1": "(a binary sequence string)variable_value1",
    "variable_name2": "(a binary sequence string)variable_value2",
    "variable_name3": "(a binary sequence string)variable_value3"}},
    {{"variable_name1": "(a binary sequence string)variable_value1",
    "variable_name2": "(a binary sequence string)variable_value2",
    "variable_name3": "(a binary sequence string)variable_value3"}}
  ]
}}

And the python code should return the outputs aligned with the RTL module outputs as JSON:

{{
  "scenario": "scenario_name",
  "output variable": [
       {{"variable_name1": "(a binary sequence string, only includes '1' and '0')variable_value1",
    "variable_name2": "(a binary sequence string, only includes '1' and '0')variable_value2",
    "variable_name3": "(a binary sequence string, only includes '1' and '0')variable_value3"}},
    {{"variable_name1": "(a binary sequence string, only includes '1' and '0')variable_value1",
    "variable_name2": "(a binary sequence string, only includes '1' and '0')variable_value2",
    "variable_name3": "(a binary sequence string, only includes '1' and '0')variable_value3"}}
  ]
}}

Each scenario contains multiple input variables. Your primary goal is to implement a Python class whose outputs precisely match the functionality and logic described by the provided RTL specification (`spec`) and module header.

## Implementation Requirements:

### 1. Initialization (__init__ method)

Implement the following method exactly:

def __init__(self):
    '''
    Initialize all internal state registers to zero.
    Each internal register/state variable must align with the module header.
    Explicitly initialize these states according to the RTL specification.
    '''
    pass  # Initialize your state variables here

### 2. Signal Loading and State Updates (load method)

Implement the method exactly as shown:

def load(self, stimulus_dict: Dict[str, any]):
    '''
    stimulus_dict: a dictionary formatted as shown above.
    Parse each input variable: You must generate a Python dictionary that decodes a binary string into the corresponding RTL signal assignments by associating each bit with its correct index based on the signal's declared range.

    '''
    pass  # Implement your signal update logic here
[Importance]
### 1. Data structure transfer
In RTL descriptions, a signal is typically defined with a range notation like [m:n]: If a signal is defined as x[3:1], then the binary value '100' corresponds to:

X3=1,x[3]=1 (leftmost digit in string)
X2=0,x[2]=0
X1=0,x[1]=0 (rightmost digit in string)
You will receive a dictionary of input variables which all all  binary string.
          Parse each input variable: You must parse each input variable and convert it from a string into its binary representation. All register/state variable must align with the **module header**. eg: S = stimulus_dict['S'], S=int(S,2). Important: For subsequent unified reading and calculation, it must be binary rather than other numeral systems (or bases). It must be converted to binary; converting it to any other base—like S=int(S,16) is not allowed!!!
    0. [Important] For read and output variable, you should know that for hardware language, the rightmost bit is [0], the leftmost bit is [n-1].So if you need to read r2, please use r2=r>>2&1 or output x[3], please use x_3=x>>3&1 instead of x[3].
2. the first 1 bit means the rightmost bit which value is 1, the second 1 bit means the second rightmost bit which value is 1, and so on.
If the problem description related to the position of the bit, you must generate a Python dictionary that decodes a binary string into the corresponding RTL signal assignments by associating each bit with its correct index based on the signal's declared range.
like:
1. in_dict = {{f"in\[{{msb - i}}\]": int(b) for i, b in enumerate(in)}}


### 4. Error Handling and Edge Cases:
   - Implement appropriate error handling for invalid inputs or unexpected conditions.
   - Consider edge cases that might arise from the RTL specification and handle them accordingly.

### 5. Final Implementation:
   - Ensure your implementation accurately reflects the behavior described in the RTL specification.
   - Use clear and concise Python code.
   - Add comments to explain complex logic or important implementation details.

Please provide your complete implementation of the GoldenDUT class, including both the __init__ and load methods, adhering to the RTL specification and the guidelines provided above. Write your implementation inside <implementation> tags.

## Important RTL-to-Python Simulation Considerations:

To accurately replicate RTL behavior in Python, explicitly handle the following:

<instructions>
{instructions}
</instructions>

Additional information for your implementation:

{code_context}
Python implementation examples (GoldenDUT):

{examples_prompt}
"""

code_context = """
Please provide code that should be inserted between the two string variables <header>{PythonHeader}</header> and <tail>{CHECKER_TAIL}</tail>.
The code you generate will go after <header> and before <tail>.
Do not include the content of <header> or <tail>; just generate the code that goes in between.

"""


instructions = """

## Summary

- Use masking and formatting for fixed-width bit simulation.
- Perform logic by converting binary strings to integers.
- Emulate registers with Python classes and state updates.
- Handle two's complement for signed numbers.
- Structure simulation loops 

[Hint]

0. Perform bitwise consistency checks for all 01 sequences: Confirm input/output bit lengths match. Verify no duplicate minterms in truth tables. Cross-check Karnaugh map groupings against standard adjacency rules. When detecting non-standard ordering in inputs, check the order of outputs. 


1. For finite state machine, the next state is determined by the current state and the input. You need to generate the truth table which includes all the possible combinations of the current state and the input. For example,    
 _TRUTH_TABLE = {
            '0000': '1',  # S0 + w=0 → S1 → y0 = 1
            '0001': '0',  # S0 + w=1 → S2 → y0 = 0
            '0010': '1',  # S1 + w=0 → S3 → y0 = 1
            '0011': '0',  # S1 + w=1 → S4 → y0 = 0
            '0100': '0',  # S2 + w=0 → S4 → y0 = 0
            '0101': '1',  # S2 + w=1 → S5 → y0 = 1
            '0110': '1',  # S3 + w=0 → S5 → y0 = 1
            '0111': '0',  # S3 + w=1 → S0 → y0 = 0
            
            
        }


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

3. Diagrams and Charts
When processing diagrams in specifications:
- Extract timing relationships from waveform diagrams
- Convert flowcharts to sequential test patterns
- For block diagrams, test each component interface separately
- Ensure signal transitions match the timing shown in diagrams
4. State Machines
For state machine specifications:
- Generate test sequences that traverse all states
- Test all valid state transitions at least once
- Include invalid transitions to verify error handling
- Test reset conditions and initialization sequences
- Verify state persistence and proper state memory
- Test corner cases where multiple transitions are possible

"""
code_context = """
Please provide code that should be inserted between the two string variables <header>{PythonHeader}</header> and <tail>{CHECKER_TAIL}</tail>.
The code you generate will go after <header> and before <tail>.
Do not include the content of <header> or <tail>; just generate the code that goes in between.

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
def check_output(stimulus,dut):

    


        

    return dut.load(stimulus)

if __name__ == "__main__":

    with open("stimulus.json", "r") as f:
        stimulus_data = json.load(f)

    stimulus_list = []
    for stimulus in stimulus_data:
        stimulus_list.append(stimulus['input variable'])

    tb_outputs = []
    for stimulus in stimulus_list:
        dut = GoldenDUT()
        scenario_outputs=[]
        for cycle in stimulus:

            outputs = check_output(cycle,dut)
            scenario_outputs.append(outputs)
        tb_outputs.append(scenario_outputs)


    

    print(json.dumps(tb_outputs, indent=2))


"""

ONE_SHOT_EXAMPLES = """
Here are some examples of the GoldenDUT python code generation:
Example 1:

<example>
    <input_spec>
        Consider the four‑variable Boolean function **g(y[4:1])** whose truth table is given in Karnaugh‑map form below. The two least–significant bits **y\[1] y\[2]** label the columns in Gray‑code order **00 01 11 10**, and the two most‑significant bits **y\[3] y\[4]** label the rows in the same Gray order **00 01 11 10**. The symbol **d** marks *don't‑care* positions that may be implemented as either 0 or 1, whichever yields the simplest hardware.
//        y[1]y[2]
// y[3]y[4]   00   01   11   10
//   00 | 1 |  d |  0 |  d |
//   01 | d |  1 |  1 |  0 |
//   11 | 0 |  1 |  d |  d |
//   10 | 0 |  d |  1 |  1 |

// Consider a block diagram with inputs 'r' and 's' going into a module called "top_module". This "top_module" has four outputs, mux_in[3:0], that connect to a four input mux. The mux takes as input {p,q} and pq = 00 is connected to mux_in[0], pq=01 is connected to mux_in[1], and so on. You are implementing in Verilog just the portion labelled "top_module", such that the entire circuit (including the 4-to-1 mux) implements the K-map.
    </input_spec>
  <module_header>
    module top_module (
    input  logic [4:1] y,
    output logic       g
);
  </module_header>

    <python_code>

class GoldenDUT:

    #Golden reference model for the combinational function g(y[4:1]).
    #It contains *no* internal state and therefore needs no clock.
    def __init__(self) -> None:
  
        #No internal registers are required because the circuit is purely combinational.

        pass

    def load(self, stimulus_dict: Dict[str, Any]) -> List[Dict[str, str]]:


        # Lookup table: index is the 4‑bit input value (0–15), value is '0', '1', or 'x'.
        # Notice the order of "11" is before "10" in the Karnaugh map.
        _TRUTH_TABLE: List={
            '0000': '1',  # y[3]y[4]=00, y[1]y[2]=00
            '0001': '0',  # y[3]y[4]=00, y[1]y[2]=01
            '0011': '0',  # y[3]y[4]=00, y[1]y[2]=11
            '0010': '0',  # y[3]y[4]=00, y[1]y[2]=10
            '0100': '0',  # y[3]y[4]=00, y[1]y[2]=01
            '0101': '1',  # y[3]y[4]=00, y[1]y[2]=01
            '0110': '0',  # y[3]y[4]=00, y[1]y[2]=10
            '0111': '1',  # y[3]y[4]=00, y[1]y[2]=11
            '1100': '0',  # y[3]y[4]=00, y[1]y[2]=11
            '1101': '1',  # y[3]y[4]=00, y[1]y[2]=11
            '1110': '0',  # y[3]y[4]=00, y[1]y[2]=10
            '1111': '0',  # y[3]y[4]=00, y[1]y[2]=11
            '1000': '1',  # y[3]y[4]=00, y[1]y[2]=00
            '1001': '1',  # y[3]y[4]=00, y[1]y[2]=01
            '1011': '0',  # y[3]y[4]=00, y[1]y[2]=11
            '1010': '1'   # y[3]y[4]=00, y[1]y[2]=10
        }
        #Convert each binary input string in stimulus_dict['input variable'] into an integer,
        look up the corresponding output, and return a list of per‑cycle output dictionaries.

        outputs: List[Dict[str, str]] = []

       
       
        y_dict = {{f"y\[{{4 - i}}\]": int(b) for i, b in enumerate(stimulus_dict["y"])}}        # y 's msb is 4, lsb is 1
        y_array = y_dict["3"]+y_dict["4"]+y_dict["1"]+y_dict["2"] #reverse the order of the bits in the binary string
        g_val = self._TRUTH_TABLE[y_array]
       

        return {"g": g_val}
    </python_code>

    Example 2:

<example>
    <input_spec>
       Consider the following finite state machine:
       // S0 (000) --0--> S1
// S0 (000) --1--> S2
// S1 (001) --0--> S3
// S1 (001) --1--> S4
// S2 (010) --0--> S4
// S2 (010) --1--> S5
// S3 (011) --0--> S5
// S3 (011) --1--> S0
Your task is to implement the next-state logic for bit y[0].
    </input_spec>
    <module_header>
    module top_module (
    input  logic [2:0] y,
    input  logic       w,
    output logic       Y0
);
  </module_header>
    
    
    <python_code>
class GoldenDUT:
    def __init__(self):
        # No internal state needed – purely combinational logic
        pass

    def load(self, stimulus_dict: Dict[str, any]):
        # Truth table for computing Y0 (the least significant bit of next state)
        # Key = current state (y2y1y0) + input w
        # Value = y0 of next state
        _TRUTH_TABLE = {
            '0000': '1',  # S0 + w=0 → S1 → y0 = 1
            '0001': '0',  # S0 + w=1 → S2 → y0 = 0
            '0010': '1',  # S1 + w=0 → S3 → y0 = 1
            '0011': '0',  # S1 + w=1 → S4 → y0 = 0
            '0100': '0',  # S2 + w=0 → S4 → y0 = 0
            '0101': '1',  # S2 + w=1 → S5 → y0 = 1
            '0110': '1',  # S3 + w=0 → S5 → y0 = 1
            '0111': '0',  # S3 + w=1 → S0 → y0 = 0

        }

       
        
        y_bits = stimulus_dict['y']  # e.g., '010'
        w_bit = stimulus_dict['w']   # e.g., '1'

        key = y_bits + w_bit
        Y0 = _TRUTH_TABLE[key]

        

        return {'Y0': Y0}
    </python_code>

</example>
Example 3:

<example>
    <input_spec>
        You are given a 64-bit input vector in[63:0]. You need to compute the following three outputs:

out_rising: For each bit position i, out_rising[i] = 1 if in[i] == 1 and in[i+1] == 0, indicating a falling edge from left to right (i.e., a 1 followed by a 0). Since in[63] has no in[64], we ignore out_rising[63].

out_falling: For each bit position i, out_falling[i] = 1 if in[i] == 0 and in[i+1] == 1, indicating a rising edge from left to right. Also ignore out_falling[63].

out_same: For each bit position i, out_same[i] = 1 if in[i] == in[i+1]. For i=63, compare in[63] with in[0] (wrap-around).
    </input_spec>

    <python_code>
    class GoldenDUT:
    def __init__(self):
        pass

    def load(self, stimulus_dict: Dict[str, any]):
        

       
            bin_str = stimulus['in']
            assert len(bin_str) == 64, "Input must be 64 bits."

            # Step 1: Create in_dict from binary string
            in_dict = {f"in[{63 - i}]": int(b) for i, b in enumerate(bin_str)}

            # Step 2: Compute out_rising (from i=0 to i=62)
            out_rising = []
            for i in range(63):
                if in_dict[f"in[{i}]"] == 1 and in_dict[f"in[{i+1}]"] == 0:
                    out_rising.append("1")
                else:
                    out_rising.append("0")

            # Step 3: Compute out_falling (from i=0 to i=62)
            out_falling = []
            for i in range(63):
                if in_dict[f"in[{i}]"] == 0 and in_dict[f"in[{i+1}]"] == 1:
                    out_falling.append("1")
                else:
                    out_falling.append("0")

            # Step 4: Compute out_same (i from 0 to 63, wrap around)
            out_same = []
            for i in range(64):
                neighbor_idx = (i + 1) % 64
                same = in_dict[f"in[{i}]"] == in_dict[f"in[{neighbor_idx}]"]
                out_same.append("1" if same else "0")

          

        return {
                "out_rising": ''.join(out_rising),
                "out_falling": ''.join(out_falling),
                "out_same": ''.join(out_same),
            }
    </python_code>
</example>

"""


class PyOutputFormat(BaseModel):
    reasoning: str
    python_code: str


class PyChecker:
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
        prompt = GENERATION_PROMPT.format(
            description=problem_description,
            module_header=header,
            instructions=instructions,
            examples_prompt=ONE_SHOT_EXAMPLES,
            code_context=code_context,
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

        logger.info(f"Token count: {token_cnt}")
        logger.info(f"Response: {response.message.content}")

        with open(python_path, "w") as f:
            f.write(py_output)

        return True, self.parse_output(response).python_code
