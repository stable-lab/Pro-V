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
You are an expert in Python code design.
"""
INIT_EDITION_PROMPT = """

Your task is to review a natural-language problem description, some python code list(index begin from 0) designed to solve the problem , their result is different, please review the python code and the result, and choose the best python code. Important: even  the best python code is still likely to fail to meet the exact requirements of the problem description, you should also judge if the best python code is matched with the specification.

You must think step by step to determine whether the python code and the observed input/output behavior matches the expected logic described in the problem description.


<problem_description>
{spec}
</problem_description>



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
    "best_python_code": "int, 0/1/2/3/4/5,the best python code index ",
    "if_matches": "yes or no, if the best python code is perfectly matched with the specification",
    "reason_for_best_python_code_mismatch":"the reason for the best python code mismatch with the specification, if if_matches is yes, this field is empty",
    
}

ACTION_OUTPUT_PROMPT = r"""
Output after running given action:
<action_output>
{action_output}
</action_output>
"""

example = """
"""


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
                spec=spec,  python_code_list=python_code_list,example=example,module_header=module_header
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
                if_matches=True if output_json_obj['if_matches']=='yes' else False
                
                return best_python_code_index,if_matches,output_json_obj['reason_for_best_python_code_mismatch']
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