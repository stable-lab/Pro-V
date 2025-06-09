"""
Description :   some utils for project
Author      :   Ruidi Qiu (ruidi.qiu@tum.de)
Time        :   2022/11/08 13:00:00
LastEdited  :   2024/9/3 17:33:26
"""

import collections
import os
import threading
import time
from datetime import datetime, timedelta
from functools import wraps
from itertools import repeat
import re

import anthropic
from llama_index.llms.anthropic import Anthropic
# import tiktoken


def str_list(list, precision=4) -> str:
    """
    convert a list of string/number to a string;

    to show the list in the way what we see it in the code

    if string, add '' around it; if number, do nothing

    Example:
    ::

        str_list(['a', 2, '3']) -> "['a', 2, '3']"
    """
    if len(list) == 0:
        return "[]"
    str_list = "["
    for i in list:
        if isinstance(i, str):
            str_list += "'%s', " % (i)
        elif isinstance(i, int):  # number
            str_list += "%d, " % (i)
        else:  # number
            str_list += "%.*f, " % (precision, i)
    str_list = str_list[:-2] + "]"
    return str_list


def print_time(en=True):
    """
    print the running time of a function

    For example:
    ::

        @print_time()
        def forward(self, input):
            return self.top_level(input)
    """

    def decorator_nopara(func):
        def wrapper(*args, **kwargs):
            if en:
                old_time = time.time()
                result = func(*args, **kwargs)
                func_name = str(func).split(" ")[1]
                run_time = time.time() - old_time
                print("{} use time: {}s".format(func_name, run_time))
            else:
                result = func(*args, **kwargs)
            return result

        return wrapper

    return decorator_nopara


def raise_error(func):
    """
    decorator

    raise error after a function
    """

    def wrapper(*args, **kwargs):
        func(*args, **kwargs)
        raise Exception('this error is raised by debug decorator "raise_error"')

    return wrapper


##########################################################
class Timer:
    """
    print the running time of a code block

    Args:

        - code_name (str): the name of the code block; default: None

        - print_en (bool): whether to print the running time; default: True

    Example 1 (print time on the console):
    ::

        with Timer('test') as t:
            loss.backward() # some code
        # this will print 'test: time cost = 0.1s' on the console

    Example 2 (get time of a code block):
    ::

        with Timer(print_en=False) as t:
            loss.backward() # some code
        time_cost = t.interval # time_cost = 0.1
    """

    def __init__(self, code_name=None, print_en=True):
        self.code_name = code_name
        self.print_en = print_en

    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, *args):
        self.end = time.time()
        self.interval_time = self.end - self.start
        print_line = "time cost = %.4fs" % (self.interval_time)
        if self.code_name is not None:
            print_line = self.code_name + ": " + print_line
        if self.print_en:
            print(print_line)
        self.print_line = print_line

    @property
    def interval(self):
        return self.interval_time

    @property
    def name(self):
        return self.code_name

    @property
    def info(self):
        return self.print_line

    @property
    def message(self):
        return self.print_line


def get_time(compact=False):
    """
    get the string of current time, format: '%H:%M:%S %Y-%m-%d'
    """
    if compact:
        return get_time_compact()
    else:
        return time.strftime("%H:%M:%S %Y-%m-%d", time.localtime(time.time()))


def get_time_compact():
    now = datetime.now()
    time_str = now.strftime("%Y%m%d_%H%M%S")
    return time_str


class run_in_dir:
    """
    change the current directory to a new directory, and then change it back after the code block

    Args:
        dir (str): the new directory (relative path to the current directory)
    """

    def __init__(self, dir):
        self.new_dir_relative = dir

    def __enter__(self):
        self.old_dir = os.getcwd()
        self.new_dir = os.path.join(self.old_dir, self.new_dir_relative)
        os.chdir(self.new_dir)

    def __exit__(self, *args):
        os.chdir(self.old_dir)


def _ntuple(n, name="parse"):
    def parse(x):
        if isinstance(x, collections.abc.Iterable):
            return tuple(x)
        return tuple(repeat(x, n))

    parse.__name__ = name
    return parse


_single = _ntuple(1, "_single")
_pair = _ntuple(2, "_pair")
_triple = _ntuple(3, "_triple")
_quadruple = _ntuple(4, "_quadruple")


def clean_wave_vcd(clean_dir, cnt_en=False):
    """
    remove all the "wave.vcd" files in the directory
    """
    cnt = 0
    for root, _dirs, files in os.walk(clean_dir):
        for file in files:
            # must be strictly equal to "wave.vcd"
            if file == "wave.vcd":
                os.remove(os.path.join(root, file))
                if cnt_en:
                    cnt += 1
                    if cnt % 100 == 0:
                        print("%d files cleaned" % (cnt))


def get_week_range(start_day: str | int = "Monday", today=None) -> str:
    """
    - function:
        - return the week range of the current week, the start day can be any day of the week
        - for example, if today is 20240807, which is wednesday, if the start_day is "Monday", the output will be "0805~0811"; if the start day is "Tuesday", the output will be "0806~0812"; if the start day is "Thursday", the output will be "0801~0807"
    - input:
        - start_day: the start day of the week, can be a string or an integer
            - string: the name of the day, for example, "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
            - integer: the index of the day, 0 is Monday, 1 is Tuesday, 2 is Wednesday, 3 is Thursday, 4 is Friday, 5 is Saturday, 6 is Sunday, invalid index will be mod 7
        - today: the date of the day, if None, the current date will be used;
            - formart: "%Y%m%d", e.g. "20240807"
    """
    weekday_map = {
        "Monday": 0,
        "Tuesday": 1,
        "Wednesday": 2,
        "Thursday": 3,
        "Friday": 4,
        "Saturday": 5,
        "Sunday": 6,
    }
    start_day = weekday_map[start_day] if isinstance(start_day, str) else start_day % 7
    # Get the current date
    # today = datetime.today()
    if today is None:
        today = datetime.today()
    else:
        today = datetime.strptime(today, "%Y%m%d")

    # Calculate the current day of the week (0 is Monday, 6 is Sunday)
    current_weekday = today.weekday()

    # Calculate the number of days to subtract to get to the start day
    days_to_subtract = (current_weekday - start_day) % 7

    # Subtract the days to get to the start day
    start = today - timedelta(days=days_to_subtract)

    # the output format is like "0805~0811"
    end = start + timedelta(days=6)
    return start.strftime("%m%d") + "~" + end.strftime("%m%d")


def run_with_timeout(timeout):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Define a thread target function to run the target code
            def target(result):
                try:
                    result.append(func(*args, **kwargs))
                except Exception as e:
                    result.append(e)

            # List used to store the function result
            result = []
            # Create a thread
            thread = threading.Thread(target=target, args=(result,))
            # Start the thread
            thread.start()
            # Wait for the thread to complete, with a specified timeout
            thread.join(timeout)

            # If the thread is still alive, it timed out
            if thread.is_alive():
                raise TimeoutError(f"Function call timed out after {timeout} seconds")

            # If the thread finished, check if there was an exception
            if isinstance(result[0], Exception):
                raise result[0]

            # Return the function result
            return result[0]

        return wrapper

    return decorator


def walk_files(path):
    """Walk through files in a directory path."""
    for root, _dirs, files in os.walk(path):
        for file in files:
            file_path = os.path.join(root, file)
            yield file_path


def add_lineno(file_content: str) -> str:
    lines = file_content.split("\n")
    ret = ""
    for i, line in enumerate(lines):
        ret += f"{i+1}: {line}\n"
    return ret


def reformat_json_string(output: str) -> str:
    # in gemini, the output has markdown surrounding the json string
    # like ```json ... ```
    # we need to remove the markdown
    # remove by using regex between ```json and ```
    pattern = r"```json(.*?)```"
    match = re.search(pattern, output, re.DOTALL)
    if match:
        return match.group(1).strip()

    pattern = r"```xml(.*?)```"
    match = re.search(pattern, output, re.DOTALL)
    if match:
        return match.group(1).strip()

    return output.strip()


class VertexAnthropicWithCredentials(Anthropic):
    def __init__(self, credentials, **kwargs):
        """
        In addition to all parameters accepted by Anthropic, this class accepts a
        new parameter `credentials` that will be passed to the underlying clients.
        """
        # Pop parameters that determine client type so we can reuse them in our branch.
        region = kwargs.get("region")
        project_id = kwargs.get("project_id")
        aws_region = kwargs.get("aws_region")

        # Call the parent initializer; this sets up a default _client and _aclient.
        super().__init__(**kwargs)

        # If using AnthropicVertex (i.e., region and project_id are provided and aws_region is None),
        # override the _client and _aclient with the additional credentials parameter.
        if region and project_id and not aws_region:
            self._client = anthropic.AnthropicVertex(
                region=region,
                project_id=project_id,
                credentials=credentials,  # extra argument
                timeout=self.timeout,
                max_retries=self.max_retries,
                default_headers=kwargs.get("default_headers")
            )
            self._aclient = anthropic.AsyncAnthropicVertex(
                region=region,
                project_id=project_id,
                credentials=credentials,  # extra argument
                timeout=self.timeout,
                max_retries=self.max_retries,
                default_headers=kwargs.get("default_headers")
            )
        # Optionally, you could add similar overrides for the aws_region branch if needed.
