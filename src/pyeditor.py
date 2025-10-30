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
You are tasked with refining a Python class named "GoldenDUT" that realizes the functionality described in a hardware language problem. The exsiting python code has some misalignment with the RTL specification, you need to fix the misalignment and return the correct python code, the information you have is:
<problem_description>
{description}
</problem_description>

<module_header>
{module_header}
</module_header>

<existing_python_code>
{existing_python_code}
</existing_python_code>

"""

code_context = """
Please provide code that should be inserted between the two string variables <header>{PythonHeader}</header> and <tail>{CHECKER_TAIL}</tail>.
The code you generate will go after <header> and before <tail>.
Do not include the content of <header> or <tail>; just generate the code that goes in between.

"""


instructions = """


"""
code_context = """


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


"""

ONE_SHOT_EXAMPLES = """

"""


class PyOutputFormat(BaseModel):
    reasoning: str
    python_code: str


class PyEditor:
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
