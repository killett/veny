#!/usr/bin/env python3

# Written by Emmy Killett (she/her), ChatGPT 4o (it/its), ChatGPT o1-preview (it/its), ChatGPT o3-mini-high (it/its), ChatGPT o4-mini-high (it/its), and GitHub Copilot (it/its).
from __future__ import annotations  # For Python 3.7+ compatibility with type annotations
import os
from pathlib import Path  # Preferred over os.path for path manipulations.
import sys
import logging
from typing import TextIO, Any, TypeAlias, Type, Literal
import re  # Used to precompile regexes for performance

print("REPLACE ALL WRITE AND APPEND STATEMENTS WITH ud.my_atomic_write()!")

# This is the version of univ_defs.py
__version__ = '0.1.7'

# This is the version of python which should be used in scripts that import this module.
PY_VERSION = 3.11

DEFAULT_ENCODING = 'utf-8'  # This is the default encoding used for reading and writing text files.

valid_basins = ["California", "Sacramento", "San Joaquin", "Tulare-Buena Vista Lakes"]

# ANSI escape codes
ANSI_RED    = "\033[91m"
ANSI_GREEN  = "\033[92m"  # this is bold/bright green on Linux but orange on my Mac
ANSI_YELLOW = "\033[93m"
ANSI_CYAN   = "\033[94m"  # this is blue on Linux but cyan on my Mac
ANSI_RESET  = "\033[0m"

# All the formatting rules to ignore when running flake8 to check Python formatting.
IGNORED_CODES = [
    'W503',  # line break before binary operator (W503 and W504 are mutually exclusive, so ignore both)
    'W504',  # line break  after binary operator (W503 and W504 are mutually exclusive, so ignore both)
    'E128',  # continuation line under-indented for visual indent
    'E201',  # whitespace after '('
    'E202',  # whitespace before ')'
    'E203',  # whitespace before ':'
    'E211',  # whitespace before '('
    'E221',  # multiple spaces before operator
    'E222',  # multiple spaces after  operator
    'E226',  # missing whitespace around arithmetic operator        (the fix doesn't work on the right side even with --aggressive)
    'E227',  # missing whitespace around bitwise or shift operator  (the fix doesn't work on the right side even with --aggressive)
    'E241',  # multiple spaces after ','
    'E251',  # unexpected spaces around keyword / parameter equals
    'E262',  # inline comment should start with '# '
    'E271',  # multiple spaces  after keyword
    'E272',  # multiple spaces before keyword
    'E701',  # multiple statements on one line (colon)
]


def parent_unused_function() -> None:
    """This function is not used in the test.py script."""
    unused_function()


def unused_function() -> None:
    """This function is not used in the test.py script."""
    print("This function is not used in the test.py script.")
    import numpy as np


class PlotOptions:
    """Global figure options."""

    def __init__(self) -> None:
        """Initialize PlotOptions class with default values."""
        # Ideas for improving this parent class: https://chatgpt.com/share/6876a7e2-da84-8006-9c8f-100d243b73e4
        self.myfigsize   = (16, 9)
        self.fsize       = 24
        self.dpi_choice  = 300
        self.markers     = ['o',     's',      '^',         'v',          '<',           '>']
        self.colors      = ['black', 'red',    'blue',      'green',      'purple']      # Used for lines in light mode or for shaded areas in dark mode
        self.lightcolors = ['grey',  'pink',   'lightblue', 'lightgreen', 'lightpurple']  # Used for shaded areas in light mode or for lines in dark mode
        self.linestyles  = ['solid', 'dashed', 'dashdot',   'dotted']
        self.dark_mode   = 0  # 1 = dark mode, 0 = light mode
        if self.dark_mode:
            self.background_color = '#000000'
            self.text_color       = '#FFFFFF'
            self.colors      = [c.replace('black', 'darkgrey') for c in self.colors]
            self.lightcolors = [c.replace('grey', 'lightgrey') for c in self.lightcolors]
        else:
            self.background_color = '#FFFFFF'
            self.text_color       = '#000000'


class UnivClass:
    """Class that handles the import and operation of large language model APIs."""

    def __init__(self) -> None:
        """Initialize the class and import the necessary modules."""
        self.import_test()

    def import_test(self) -> None:
        """ Test the import of this module by printing a message and the version of Python being used."""
        import openai


class LLMs:
    """Class that handles the import and operation of large language model APIs."""

    def __init__(self) -> None:
        """Initialize the LLM class and import the necessary modules."""
        self.init_llms()

    def init_llms(self) -> None:
        """
        1. Import the LLM APIs into the self.llm_modules dictionary.
        2. Check if the necessary environment variables are set.
        3. Create clients for all successfully imported LLMs.
        """
        # 1. Import the LLM APIs into the self.llm_modules dictionary.
        # ADD NEW COMPANY LLMs HERE.
        self.llms = [
            {"name": "OpenAI", "module": "openai", "env_var": "OPENAI_API_KEY"},
            {"name": "Anthropic", "module": "anthropic", "env_var": "ANTHROPIC_API_KEY"},
        ]
        self.found_llms = {}
        self.llm_modules = {}
        for llm in self.llms:
            this_llm = llm["name"]
            this_key = llm["env_var"]
            try:
                # THIS DOESN'T WORK YET BECAUSE DYNAMIC IMPORTS BREAK mypy.py!
                # ALSO, THE importlib APPROACH IS MORE MODERN THAN THE __import__ APPROACH:
                # https://chatgpt.com/share/68158ef6-b5ec-8006-ab89-15340479e6d2
                # self.llm_modules[this_llm] = __import__(llm["module"])
                # ADD NEW COMPANY LLMs HERE.
                if  this_llm == "OpenAI":
                    import openai
                    self.llm_modules[this_llm] = openai
                elif this_llm == "Anthropic":
                    import anthropic
                    self.llm_modules[this_llm] = anthropic
                else:
                    my_critical_error(f"Unknown LLM: {this_llm}")
                print(f"{this_llm} package found", end="")
                # 2. Check if the necessary environment variables are set.
                if this_key in os.environ:
                    self.found_llms[this_llm] = True
                    print(f", and the {this_key} environment variable is set.")
                else:
                    self.found_llms[this_llm] = False
                    print(f", but the {this_key} environment variable is not set, so the {this_llm} package cannot be used.")
            except ImportError as e:
                self.found_llms[this_llm] = False
                print(f"{this_llm} package not found, so it cannot be used. Error: {e}")

        if not any(self.found_llms.values()):
            my_critical_error(f"Could not find any large language model APIs. Choices are: {', '.join(self.found_llms.keys())}\nExiting.")

        # 3. Create clients for all successfully imported LLMs.
        self.clients = {}
        for llm in self.found_llms:
            if self.found_llms[llm]:
                # ADD NEW COMPANY LLMs HERE.
                if   llm == "OpenAI":
                    self.clients[llm] = self.llm_modules[llm].OpenAI()
                elif llm == "Anthropic":
                    self.clients[llm] = self.llm_modules[llm].Anthropic()
                else:
                    print(f"Can't create client for unknown LLM: {llm}")
                    sys.exit()

    def send_prompt(self, prompt: str, system_message: str,
                    model: str, company: str, temperature: float,
                    max_tokens: int = 1000) -> str:
        """Call the chosen LLM's API and return the text response."""
        # ADD NEW COMPANY LLMs HERE.
        if company == "OpenAI":
            response_obj = self.clients[company].chat.completions.create(
                model=model,
                temperature=temperature,
                messages=[{"role": "system", "content": system_message},
                            {"role": "user",   "content": prompt}]
            )
            return response_obj.choices[0].message.content
        elif company == "Anthropic":
            response_obj = self.clients[company].messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_message,
                messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}]
            )
            return response_obj.content[0].text
        else:
            my_critical_error(f"Unknown company: {company}")


class MemoryHandler(logging.Handler):
    """A logging handler that stores logs in memory so the errors can be printed at the end."""

    def __init__(self, level: int = logging.ERROR) -> None:
        """Initialize the MemoryHandler with the specified logging level."""
        super().__init__(level)
        self.logs = []

    def emit(self, record: logging.LogRecord) -> None:
        """Capture the log record and store it in memory."""
        if record.levelno >= self.level:  # Only capture logs with the appropriate level
            self.logs.append(self.format(record))


class FlushingStreamHandler(logging.StreamHandler):
    """A logging handler that flushes the stream after emitting each log so the logs are immediately visible."""

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record and immediately flush the stream."""
        # Call the original emit method to handle the logging
        super().emit(record)
        # Immediately flush the stream after emitting the log
        self.flush()


class MaxLevelFilter(logging.Filter):
    """A logging filter that only allows logs up to a certain level to pass through, so that error messages aren't printed multiple times."""

    def __init__(self, max_level: int) -> None:
        """Initialize the MaxLevelFilter with the specified maximum logging level."""
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter out log records above the maximum level."""
        return record.levelno <= self.max_level


def fallback_logging_config(log_level: int | str = 'INFO', rawlog: bool = False) -> None:
    """
    Configure the root logger with a basic configuration if no handlers are set.
    Run this at the start of functions which might be run without first configuring logging.

    Parameters:
        level  : The logging level to set. Defaults to 'INFO'.
        rawlog : If True, use a simple log format without timestamps or levels.
    """
    if not logging.getLogger().handlers:
        if not rawlog:  # Use a full logging format with timestamps and levels.
            logging.basicConfig(level=log_level,
                                format="%(asctime)s %(name)s %(levelname)s: %(message)s",
                                datefmt="%Y-%m-%d %H:%M:%S")
        else:  # rawlog is True, so use a simple format without timestamps or levels.
            logging.basicConfig(level=log_level, format="%(message)s")


def configure_logging(basename: str, log_level: int | str = 'INFO',
                      rawlog: bool = False, logdir: str = '') -> MemoryHandler:
    """Configure logging to write to files and stdout/stderr, and return a MemoryHandler to capture ERROR logs for later (duplicate) printing."""
    import datetime as dt

    root_logger = logging.getLogger()

    # Check if logging is already configured by checking for any handlers
    if root_logger.hasHandlers():
        for handler in root_logger.handlers:
            if isinstance(handler, MemoryHandler):
                return handler

    # Proceed with configuring logging if no MemoryHandler was found
    if not logdir:  # Default to the current working directory if no logdir is provided.
        logdir = os.getcwd()
    os.makedirs(logdir, exist_ok=True)

    now = dt.datetime.now()
    log_base = f".{basename}-log-{now.strftime('%Y%m%d-%H%M%S')}"
    log_info = os.path.join(logdir, log_base + ".out")
    log_errors = os.path.join(logdir, log_base + ".err")

    root_logger.handlers = []  # Reset any existing handlers

    # File handlers for logging to files
    try:
        debug_info_handler = logging.FileHandler(log_info)
        debug_info_handler.setLevel(logging.DEBUG)
        warning_error_handler = logging.FileHandler(log_errors)
        warning_error_handler.setLevel(logging.WARNING)
    except (IOError, OSError) as e:
        print(f"Failed to create log files: {e}", flush=True)
        return None

    # Stream handler for stdout (WARNING and lower)
    console_handler_stdout = FlushingStreamHandler(stream=sys.stdout)
    console_handler_stdout.setLevel(logging.DEBUG)  # Set to lowest level
    console_handler_stdout.addFilter(MaxLevelFilter(logging.WARNING))  # Highest

    # Stream handler for stderr (ERROR and above)
    console_handler_stderr = FlushingStreamHandler(stream=sys.stderr)
    console_handler_stderr.setLevel(logging.ERROR)  # Only logs ERROR and higher to stderr

    memory_handler = MemoryHandler(level=logging.ERROR)  # Only capture ERROR level logs

    # Define the formatter based on the no_prefix parameter
    if rawlog:
        log_format = logging.Formatter('%(message)s')
    else:
        log_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    debug_info_handler.setFormatter(log_format)
    warning_error_handler.setFormatter(log_format)
    console_handler_stdout.setFormatter(log_format)
    console_handler_stderr.setFormatter(log_format)
    memory_handler.setFormatter(log_format)

    root_logger.setLevel(log_level)
    root_logger.addHandler(debug_info_handler)
    root_logger.addHandler(warning_error_handler)
    root_logger.addHandler(console_handler_stdout)
    root_logger.addHandler(console_handler_stderr)
    root_logger.addHandler(memory_handler)
    if not rawlog: root_logger.info(f'Logging to {log_info} and {log_errors} with level {logging.getLevelName(root_logger.level)}')

    return memory_handler


def print_all_errors(memory_handler: MemoryHandler,
                     rawlog: bool = False) -> None:
    """Print all the captured error messages."""
    if memory_handler.logs and not rawlog:
        print("\n******************************\n"
              "******************************\n"
              "All Error messages from above:")
        for log in memory_handler.logs:
            print(log)


def my_critical_error(message: str = "A critical error occurred.",
                      choose_breakpoint: bool = False,
                      exit_code: int = 1) -> None:
    """Log a critical error message and either exit the program or enter a breakpoint."""
    fallback_logging_config()
    # Determine if an exception is being handled:
    exc_type, exc_value, exc_traceback = sys.exc_info()
    if exc_type:
        # An exception is being handled; include exception info
        logging.critical(message, exc_info=True)
    else:
        # No exception is being handled; log only the message
        logging.critical(message)
    if choose_breakpoint:
        print("Entering breakpoint while inside the my_critical_error() function. You can step outside of this function and remain paused by pressing 'n' to access variables in the calling function or press 'c' to continue running the script.")
        breakpoint()
    else:
        sys.exit(exit_code)


class MyPopenResult:
    """A class to store the results of a customized subprocess.Popen call."""

    def __init__(self, stdout: str, stderr: str, returncode: int) -> None:
        """Initialize the MyPopenResult with stdout, stderr, and returncode."""
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.success = (returncode == 0)


def my_popen(command_list: list, suppress_info: bool = False,
             suppress_error: bool = False) -> MyPopenResult:
    """Execute a command using subprocess.Popen and capture the output line by line using threads."""
    import threading
    import subprocess
    fallback_logging_config(log_level='INFO' if not suppress_info else 'ERROR')
    command_list_str = [str(item) for item in command_list]
    the_statement = "Executing command: " + ' '.join(command_list_str)

    if not suppress_info:
        logging.info(the_statement)
    else:
        logging.debug(the_statement)

    try:
        process = subprocess.Popen(
            command_list_str,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1  # Line-buffered
        )

        stdout_lines = []
        stderr_lines = []

        def read_stdout() -> None:
            """Read stdout line by line and log it."""
            for line in process.stdout:
                stdout_lines.append(line)
                log_line = line.strip()
                if not suppress_info:
                    logging.info(log_line)
                else:
                    logging.debug(log_line)

        def read_stderr() -> None:
            """Read stderr line by line and log it."""
            for line in process.stderr:
                stderr_lines.append(line)
                log_line = line.strip()
                if not suppress_error:
                    logging.error(log_line)
                elif not suppress_info:
                    logging.info(log_line)
                else:
                    logging.debug(log_line)

        # Start threads
        stdout_thread = threading.Thread(target=read_stdout)
        stderr_thread = threading.Thread(target=read_stderr)
        stdout_thread.start()
        stderr_thread.start()

        # Wait for the process and threads to finish
        process.wait()
        stdout_thread.join()
        stderr_thread.join()

        stdout = ''.join(stdout_lines)
        stderr = ''.join(stderr_lines)

        return MyPopenResult(stdout=stdout, stderr=stderr, returncode=process.returncode)

    except Exception as e:  # I don't want any exception here to crash the script, so I catch it and return a MyPopenResult with an error message.
        if not suppress_error:
            logging.error(f"An error occurred while executing the command '{command_list_str}'", exc_info=True)
        else:
            logging.info( f"An error occurred while executing the command '{command_list_str}'", exc_info=True)
        return MyPopenResult(stdout="", stderr=str(e), returncode=-1)


def my_fopen(file_path: str, suppress_errors: bool = False,
             rawlog: bool = False, numlines: int | None = None) -> TextIO | bool | str:
    """Attempt to read the file with various encodings and return the file content if successful. Optionally, specify numlines to limit the number of lines read and return a string instead of a file object."""
    fallback_logging_config(log_level='INFO' if not suppress_errors else 'CRITICAL')

    if not os.path.isfile(file_path):
        this_message = f"File does not exist: {file_path}"
        if not rawlog:
            if not suppress_errors: logging.error(this_message)
            else:                   logging.info(this_message)
        return False
    if os.path.getsize(file_path) == 0:
        this_message = f"File is empty: {file_path}"
        if not rawlog:
            if not suppress_errors: logging.error(this_message)
            else:                   logging.info(this_message)
        return False
    # Does the file end with any of these (non-text) extensions?
    for ext in video_extensions:
        if file_path.endswith(ext):
            if not rawlog:
                if not suppress_errors: logging.error(f"Skipping video file {file_path}")
                else:                   logging.info( f"Skipping video file {file_path}")
            return False
    for ext in audio_extensions:
        if file_path.endswith(ext):
            if not rawlog:
                if not suppress_errors: logging.error(f"Skipping audio file {file_path}")
                else:                   logging.info( f"Skipping audio file {file_path}")
            return False
    for ext in image_extensions:
        if file_path.endswith(ext):
            if not rawlog:
                if not suppress_errors: logging.error(f"Skipping image file {file_path}")
                else:                   logging.info( f"Skipping image file {file_path}")
            return False
    for encoding in text_encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as file:
                if numlines is None:
                    file_content = file.read()
                else:
                    file_content = ''.join(file.readline() for _ in range(numlines))
            logging.debug(f"Successfully read {file_path} with encoding {encoding}")
            return file_content  # Exit the function if reading is successful
        except UnicodeDecodeError:
            this_message = f"Unicode decode error with encoding {encoding} reading file {file_path}"
            if not suppress_errors: logging.warning(this_message, exc_info=True)
            else:                   logging.info(   this_message, exc_info=True)
            continue
        except Exception: # Catch any other exceptions that might occur, but don't crash.
            this_message = f"Error reading file {file_path} with encoding {encoding}."
            if not rawlog:
                if not suppress_errors: logging.error(this_message, exc_info=True)
                else:                   logging.info( this_message, exc_info=True)
            return False
    return False


def my_ast_parse(file_content: str, file_path: str) -> ast.AST:
    """Attempt to parse the file with ast.parse and return the tree if successful."""
    import ast
    try:
        tree = ast.parse(file_content, filename=file_path)
        return tree
    except SyntaxError as e:
        raise SyntaxError(f"Syntax error in {file_path}: {e.msg} at line {e.lineno}, column {e.offset}") from e.filename


def load_ast_var(var_name: str, script_path: str, rawlog: bool = False) -> Any:
    """
    Load a top-level literal Python variable from a module without executing it.

    :param options: Command line options and various sundries.
    :param var_name: Name of the global variable to extract.
    :param script_path: Path to the .py file.
    :returns: The Python object assigned to var_name, if it's a literal; else raises.
    :raises FileNotFoundError: if script_path doesn't exist.
    :raises AttributeError: if var_name isn't found at top level.
    :raises ValueError: if the value isn't a literal expression.
    """
    import ast
    file_content = my_fopen(script_path, rawlog=rawlog)
    if not file_content:
        my_critical_error(f"Failed to open {script_path}", choose_breakpoint=True)
    tree = my_ast_parse(file_content, script_path)
    if tree is None:
        raise SyntaxError(f"Could not parse {script_path}")

    for node in tree.body:
        # handle plain assignments: var_name = <expr>
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == var_name:
                    try:
                        return ast.literal_eval(node.value)
                    except ValueError as e:
                        raise ValueError(f"Cannot literal_eval the value of {var_name}: {e}") from e
        # also handle annotated assignments: var_name: Type = <expr>
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == var_name and node.value:
                try:
                    return ast.literal_eval(node.value)
                except ValueError as e:
                    raise ValueError(f"Cannot literal_eval the value of {var_name}: {e}") from e

    raise AttributeError(f"Top-level variable {var_name!r} not found in {script_path}")


def normalize_to_dict(value: Any, var_name: str, script_path: str) -> dict:
    """Ensure that 'value' is a dict. If it's a JSON-style string, try to parse it. Otherwise, log a warning and return an empty dict."""
    import json
    fallback_logging_config()
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
            logging.warning(f"Variable {var_name!r} in {script_path} JSON-decoded to {type(parsed).__name__}, expected dict.")
        except json.JSONDecodeError as e:
            logging.warning(f"Failed to JSON-decode variable {var_name!r} from {script_path}. Expected a dict or JSON string.", exc_info=e)
    else:
        logging.warning(f"Variable {var_name!r} in {script_path} is of type {type(value).__name__}, expected dict or JSON string.")
    return {}


def get_hostname_socket() -> str:
    """Retrieves the hostname using socket.gethostname()."""
    import socket
    return socket.gethostname()


def get_hostname_platform() -> str:
    """Retrieves the hostname using platform.node()."""
    import platform
    return platform.node()


def get_hostname_os_uname() -> str:
    """Retrieves the hostname using os.uname().nodename."""
    return os.uname().nodename


def get_hostname_subprocess_hostname() -> str:
    """Retrieves the hostname using the 'hostname' system command via subprocess."""
    import subprocess
    result = subprocess.run(['hostname'], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def get_hostname_subprocess_scutil() -> str:
    """Retrieves the hostname using the 'scutil --get ComputerName' command on macOS via subprocess."""
    import subprocess
    result = subprocess.run(['scutil', '--get', 'ComputerName'], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def get_computer_name() -> str:
    """Attempts multiple methods to retrieve the computer's name and returns the most common one."""
    methods = {
        'socket_gethostname': get_hostname_socket,
        'platform_node': get_hostname_platform,
        'os_uname_nodename': get_hostname_os_uname,
        'subprocess_hostname': get_hostname_subprocess_hostname,
        'subprocess_scutil_computername': get_hostname_subprocess_scutil  # macOS specific
    }

    results = {}

    for method_name, method_func in methods.items():
        try:
            name = method_func()
            results[method_name] = name
        except Exception:  # Ignore all exceptions for individual methods
            # logging.exception(f"Method {method_name} failed.")
            pass  # Skip methods that fail

    computer_name = analyze_results(results)

    return computer_name


def analyze_results(results: dict[str, str]) -> str:
    """
    Analyzes the retrieved computer names.

    Args:
        results (dict): Dictionary with method names as keys and computer names as values.
    Returns:
        computer_name (str): The most common computer name.
    """
    from collections import Counter

    if not results:
        print("No methods succeeded in retrieving the computer name.")
        return "ERROR-NO-NAME"

    name_values = list(results.values())
    name_counts = Counter(name_values)
    most_common = name_counts.most_common()

    if len(name_counts) == 1:
        # All names are identical
        # print(f"Computer Name: {most_common[0][0]}")
        return most_common[0][0]
    else:
        # Names are not identical
        primary_name, primary_count = most_common[0]
        differing = {name: count for name, count in most_common if name != primary_name}

        print(f"Most Common Computer Name: {primary_name} (appeared {primary_count} times)")

        print("Other Names:")
        for name, count in differing.items():
            print(f" - {name} (appeared {count} times)")

        # Optionally, list which methods returned which names
        print("\nDetailed Method Outputs:")
        for method, name in results.items():
            print(f" - {method}: {name}")

        return primary_name


def kill_process(pname: str) -> None:
    """Kill a process by its name, then check if it is still running and retry if needed. Make sure the process name is unique to avoid killing unintended processes."""
    import time
    import signal
    import subprocess
    while True:
        # Find the process IDs of the given process name
        process_ids = []
        try:
            process_list = subprocess.check_output(["pgrep", "-f", pname]).decode(DEFAULT_ENCODING)
            process_ids = process_list.splitlines()
        except subprocess.CalledProcessError as e:
            raise ValueError(f"Failed to find process with name {pname}. Make sure the process name is correct and unique: {e}") from e

        if process_ids:
            for pid in process_ids:
                print(f"Killing {pname} process with PID: {pid}")
                try:
                    os.kill(int(pid), signal.SIGTERM)  # Send SIGTERM to terminate the process
                    print(f"Sent SIGTERM to PID {pid}")
                except ProcessLookupError as e:
                    raise ValueError(f"Process with PID {pid} not found. It may have already exited: {e}") from e
        else:
            print(f"No {pname} process found.")
            break

        # Check if the process is still running
        time.sleep(2)  # Wait for 2 seconds before checking again
        process_ids = subprocess.check_output(["pgrep", "-f", pname]).decode(DEFAULT_ENCODING).splitlines()

        if not process_ids:
            print(f"{pname} process successfully killed.")
            break  # Exit the loop when the process is no longer running
        else:
            print(f"{pname} is still running. Retrying...")


def ensure_even_dimensions(image_path: str) -> None:
    """Ensure the image at 'image_path' has dimensions divisible by 2, by resizing if necessary."""
    from PIL import Image
    fallback_logging_config()
    with Image.open(image_path) as img:
        width, height = img.size
        new_width = width if width % 2 == 0 else width - 1
        new_height = height if height % 2 == 0 else height - 1

        if new_width != width or new_height != height:
            try:
                img = img.resize((new_width, new_height), Image.LANCZOS)
                img.save(image_path)
                logging.info(f"Resized image to even dimensions: width = {new_width}, height = {new_height}")
            except OSError as e:
                raise ValueError(f"Could not resize image {image_path} to even dimensions: {e}") from e
        else:
            logging.info(f"Image already has even dimensions: width = {width}, height = {height}")


def human_bytesize(num: int, suffix: str = 'B') -> str:
    """Convert a file size in bytes to a human-readable string with units like KB, MB, GB, etc."""
    for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Y', suffix)


def human_timespan(timespan: float) -> str:
    """Input: A timespan specified by a floating point number of seconds.
    Returns: a string describing that timespan in years, weeks, days, hours, and seconds."""
    # Constants for time conversions
    SECONDS_PER_MINUTE =       60
    SECONDS_PER_HOUR   =     3600
    SECONDS_PER_DAY    =    86400
    SECONDS_PER_WEEK   =   604800
    SECONDS_PER_YEAR   = 31557600  # Average year accounting for leap years

    # Calculating years, weeks, days, hours
    years = int(timespan // SECONDS_PER_YEAR)
    remaining = timespan % SECONDS_PER_YEAR

    weeks = int(remaining // SECONDS_PER_WEEK)
    remaining = remaining % SECONDS_PER_WEEK

    days = int(remaining // SECONDS_PER_DAY)
    remaining = remaining % SECONDS_PER_DAY

    hours = int(remaining // SECONDS_PER_HOUR)
    remaining = remaining % SECONDS_PER_HOUR

    minutes = int(remaining // SECONDS_PER_MINUTE)
    remaining = remaining % SECONDS_PER_MINUTE

    # Creating a list of time components
    components = []
    if years > 0:
        components.append(f"{years} year" if years == 1 else f"{years} years")
    if weeks > 0:
        components.append(f"{weeks} week" if weeks == 1 else f"{weeks} weeks")
    if days > 0:
        components.append(f"{days} day" if days == 1 else f"{days} days")
    if hours > 0:
        components.append(f"{hours} hour" if hours == 1 else f"{hours} hours")
    if minutes > 0:
        components.append(f"{minutes} minute" if minutes == 1 else f"{minutes} minutes")
    else:
        components.append(f"{remaining:.3f} second" if round(remaining, 3) == 1.0 else f"{remaining:.3f} seconds")

    # Joining the components with commas, and "and" for the last component
    if len(components) > 1:
        time_str = ", ".join(components[:-1]) + " and " + components[-1]
    elif components:
        time_str = components[0]
    else:
        time_str = "0 seconds"

    return time_str


def format_date_range(date1: dt.datetime, date2: dt.datetime | None = None) -> str:
    """Process a pair of datetime.datetime dates and produce a formatted date range string where each date looks like 'Jan  7, 2025'. If date2 is not provided, it is set to date1."""
    import datetime as dt

    month_names = {
        1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr',
        5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug',
        9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'
    }

    # If date2 is not provided, set date2 to date1
    if date2 is None:
        date2 = date1

    # Make sure both dates are datetime.datetime objects
    if not isinstance(date1, dt.datetime) or not isinstance(date2, dt.datetime):
        raise ValueError(f"Both dates must be datetime.datetime objects, but date1 is {date1} with type {type(date1)} and date2 {date2} with type {type(date2)}.")

    # Ensure that the first date is earlier than the second.
    if date1 > date2: date1, date2 = date2, date1

    day1, day2     = date1.day, date2.day
    month1, month2 = month_names[date1.month], month_names[date2.month]
    year1, year2   = date1.year, date2.year

    if year1 == year2:
        if month1 == month2:
            if day1 == day2: return f"{month1} {day1:2d}, {year1}"
            else:            return f"{month1} {day1:2d} - {day2:2d}, {year1}"
        else:                return f"{month1} {day1:2d} - {month2} {day2:2d}, {year1}"
    else: return f"{month1} {day1:2d}, {year1} - {month2} {day2:2d}, {year2}"


# Mapping of unit aliases to their equivalent in seconds
_UNIT_SECONDS = {
    **dict.fromkeys(['year', 'years', 'yr', 'yrs', 'calendar year', 'calendar years'],    31_556_952),  # Average calender year = 365.2425 days (accounting for leap years)
    **dict.fromkeys(['solar year', 'solar years', 'tropical year', 'tropical years'],     31_556_925.216),  # Average solar/tropical year = 365.24219 solar days = time for Earth to orbit the Sun once relative to the Sun/equinoxes
    **dict.fromkeys(['sidereal year', 'sidereal years'],                                  31_558_149.54),  # Sidereal year = 365.25636 days = time for Earth to orbit the Sun once relative to the "fixed" stars
    **dict.fromkeys(['month', 'months', 'mo', 'mos', 'calendar month', 'calendar months'], 2_629_746.0),  # Average calendar month = 30.436875 solar days
    **dict.fromkeys(['lunar month', 'lunar months', 'synodic month', 'synodic months'],    2_551_442.9),  # Average lunar month (synodic month) = 29.53 solar days
    **dict.fromkeys(['week', 'weeks', 'wk', 'wks'],                                          604_800.0),  # 7 solar days
    **dict.fromkeys(['day', 'days', 'd', 'solar day', 'solar days', 'ephemeris day', 'ephemeris days'], 86_400),  # 24 hours = time for Earth to rotate once relative to the Sun
    **dict.fromkeys(['sidereal day', 'sidereal days'],                                                  86_164.0905),  # 23 hours, 56 minutes, 4.1 seconds = time for Earth to rotate once relative to the "fixed" stars
    **dict.fromkeys(['hour',   'hours',   'hr',  'hrs'],          3600),
    **dict.fromkeys(['minute', 'minutes', 'min', 'mins'],           60),
    **dict.fromkeys(['second', 'seconds', 'sec', 'secs', 's'],    1.00),
    **dict.fromkeys(['decisecond',  'deciseconds',  'ds'],       1E-01),
    **dict.fromkeys(['centisecond', 'centiseconds', 'cs'],       1E-02),
    **dict.fromkeys(['millisecond', 'milliseconds', 'ms'],       1E-03),
    **dict.fromkeys(['microsecond', 'microseconds', 'us', 'μs'], 1E-06),
    **dict.fromkeys(['nanosecond',  'nanoseconds',  'ns'],       1E-09),
    **dict.fromkeys(['picosecond',  'picoseconds',  'ps'],       1E-12),
    **dict.fromkeys(['femtosecond', 'femtoseconds', 'fs'],       1E-15),
    **dict.fromkeys(['attosecond',  'attoseconds',  'as'],       1E-18),
    **dict.fromkeys(['zeptosecond', 'zeptoseconds', 'zs'],       1E-21),
    **dict.fromkeys(['yoctosecond', 'yoctoseconds', 'ys'],       1E-24),
    **dict.fromkeys(['planck time', 'planck times', 'planck', 'plancks', 'pt'], 5.391_247E-44),  # Planck time
    **dict.fromkeys(['decade', 'decades'],                                  315_569_252.16),  #   10 solar years
    **dict.fromkeys(['century', 'centuries'],                             3_155_692_521.60),  #  100 solar years
    **dict.fromkeys(['millennium', 'millennia'],                         31_556_925_216.00),  # 1000 solar years
    **dict.fromkeys(['megayear', 'megayears', 'mya', 'myr'],         31_556_925_216_000.00),  # 1E06 solar years
    **dict.fromkeys(['gigayear', 'gigayears', 'gya', 'gyr'],     31_556_925_216_000_000.00),  # 1E09 solar years
    **dict.fromkeys(['terayear', 'terayears', 'tya', 'tyr'], 31_556_925_216_000_000_000.00),  # 1E12 solar years
    **dict.fromkeys(['fortnight',    'fortnights'],                           1_209_600.00),  # 2 weeks = 604_800 * 2 seconds
    **dict.fromkeys(['decasecond',   'decaseconds',   'das'], 1E01),
    **dict.fromkeys(['hectosecond',  'hectoseconds',  'hs'],  1E02),
    **dict.fromkeys(['kilosecond',   'kiloseconds',   'ks'],  1E03),
    **dict.fromkeys(['megasecond',   'megaseconds'],          1E06),  # no Ms because .lower() would convert it to ms
    **dict.fromkeys(['gigasecond',   'gigaseconds',   'gs'],  1E09),
    **dict.fromkeys(['terasecond',   'teraseconds',   'ts'],  1E12),
    **dict.fromkeys(['petasecond',   'petaseconds'],          1E15),  # no Ps because .lower() would convert it to ps
    **dict.fromkeys(['exasecond',    'exaseconds',    'es'],  1E18),
    **dict.fromkeys(['zettasecond',  'zettaseconds'],         1E21),  # no Zs because .lower() would convert it to zs
    **dict.fromkeys(['yottasecond',  'yottaseconds'],         1E24),  # no Ys because .lower() would convert it to ys
    **dict.fromkeys(['ronnasecond',  'ronnaseconds',  'rs'],  1E27),
    **dict.fromkeys(['quettasecond', 'quettaseconds', 'qs'],  1E30),
}


def seconds_in_unit(unit: str) -> float:
    """Return the number of seconds in a given time unit."""
    try:
        return _UNIT_SECONDS[unit.lower()]
    except KeyError:
        raise ValueError(f"Unknown time unit: {unit!r}")


# Common US & UTC/GMT abbreviations → IANA zone names
_TZ_ABBREV_TO_ZONE: dict[str, str] = {
    "UTC" : "UTC",
    "GMT" : "Etc/GMT",
    "EST" : "America/New_York",
    "EDT" : "America/New_York",
    "CST" : "America/Chicago",  # WARNING! "CST" can also mean China Standard Time (Asia/Shanghai, UTC+8), so use with caution!
    "CDT" : "America/Chicago",
    "MST" : "America/Denver",
    "MDT" : "America/Denver",
    "PST" : "America/Los_Angeles",
    "PDT" : "America/Los_Angeles",
    "HST" : "Pacific/Honolulu",
    "AKST": "America/Anchorage",
    "AKDT": "America/Anchorage",
    "AST" : "America/Puerto_Rico",  # Atlantic Standard Time
    "ADT" : "America/Puerto_Rico",  # Atlantic Daylight Time
    "NST" : "America/St_Johns",     # Newfoundland Standard Time
    "NDT" : "America/St_Johns",     # Newfoundland Daylight Time
    "BST" : "Europe/London",        # British Summer Time
    "CET" : "Europe/Berlin",        # Central European Time
    "CEST": "Europe/Berlin",        # Central European Summer Time
    "EET" : "Europe/Athens",        # Eastern European Time
    "EEST": "Europe/Athens",        # Eastern European Summer Time
    "IST" : "Asia/Kolkata",         # Indian Standard Time - WARNING! "IST" can also mean Irish Standard Time (Europe/Dublin, UTC+1), so use with caution!
    "JST" : "Asia/Tokyo",           # Japan Standard Time
    "KST" : "Asia/Seoul",           # Korea Standard Time
    "HKT" : "Asia/Hong_Kong",       # Hong Kong Time
    "SGT" : "Asia/Singapore",       # Singapore Time
    "AEST": "Australia/Sydney",     # Australian Eastern Standard Time
    "AEDT": "Australia/Sydney",     # Australian Eastern Daylight Time
    "ACST": "Australia/Adelaide",   # Australian Central Standard Time
    "ACDT": "Australia/Adelaide",   # Australian Central Daylight Time
    "AWST": "Australia/Perth",      # Australian Western Standard Time
    "AWDT": "Australia/Perth",      # Australian Western Daylight Time
    "NZT" : "Pacific/Auckland",     # New Zealand Time
    "NZST": "Pacific/Auckland",     # New Zealand Standard Time
    "NZDT": "Pacific/Auckland",     # New Zealand Daylight Time
    "WET" : "Europe/Lisbon",        # Western European Time
    "WEST": "Europe/Lisbon",        # Western European Summer Time
    # …add any others you need
}

# Pre‐compile once for all calls.
_TZ_OFFSET_RE = re.compile(r'''
    ^(?P<sign>[+-])
    (?:
        (?P<hours1>\d{1,2})[hH](?P<mins1>\d{1,2})(?:[mM])?  # +5h30m
      | (?P<hours1_only>\d{1,2})[hH]                        # +5h
      | (?P<hours2>\d{1,2}):(?P<mins2>\d{2})                # +5:30
      | (?P<hours3>\d{1,2})(?P<mins3>\d{2})                 # +0530
      | (?P<hours4>\d{1,2})                                 # +5
    )
    $
''', re.VERBOSE)


def parse_timezone(tz_arg: str | dt.tzinfo | None = None) -> dt.tzinfo | str:
    """
    Parse the given timezone string or tzinfo object into a datetime.tzinfo object.
    If tz_arg is None, return UTC timezone.
    If tz_arg is a string, it can be in one of the following formats:
      - A fixed‐offset like: "+HH:MM", "+HHMM", "+H", "+Hh", "+HhMMm" (or minus variants).
         Examples: "+05:30", "-0530", "+5h", "-5h30m".
      - A string that can be converted to a ZoneInfo object (e.g. 'America/New_York').
      - A timezone abbreviation that maps to a known IANA zone name (e.g. 'EST', 'CET').
      - "Z", "UTC", or "GMT" (case‐insensitive) to represent UTC.
      - A string "Naive" to represent a naive datetime (no timezone).
    If tz_arg is already a tzinfo object, return it as is.

    Raises:
      ValueError if the string cannot be converted to a valid timezone.
    """

    import datetime as dt

    # If tz_arg is None, return UTC timezone
    if tz_arg is None:
        return dt.timezone.utc

    # If tz_arg is already a tzinfo object, return it unchanged
    if isinstance(tz_arg, dt.tzinfo):
        return tz_arg

    # If tz_arg is a string, try to parse it
    if isinstance(tz_arg, str):
        s = tz_arg.strip()
        up = s.upper()

        # Handle "Naive" case
        if up == "NAIVE":
            return tz_arg

        # Bare UTC/GMT/Z
        if up in ('Z', 'UTC', 'GMT') and len(s) <= 3:
            return dt.timezone.utc

        # Strip leading "UTC" or "GMT" prefix
        if up.startswith(('UTC', 'GMT')):
            rest = s[3:].strip()
            if rest == '':
                return dt.timezone.utc
            s = rest  # now s begins with + or -

        # Try fixed-offset patterns
        m = _TZ_OFFSET_RE.fullmatch(s)
        if m:
            sign = 1 if m.group('sign') == '+' else -1

            if m.group('hours1') is not None:
                hours = int(m.group('hours1'))
                minutes = int(m.group('mins1'))
            elif m.group('hours1_only') is not None:
                hours = int(m.group('hours1_only'))
                minutes = 0
            elif m.group('hours2') is not None:
                hours = int(m.group('hours2'))
                minutes = int(m.group('mins2'))
            elif m.group('hours3') is not None:
                hours = int(m.group('hours3'))
                minutes = int(m.group('mins3'))
            else:
                hours = int(m.group('hours4'))
                minutes = 0

            offset = dt.timedelta(hours=hours, minutes=minutes) * sign
            return dt.timezone(offset)

        # Otherwise, fall back to ZoneInfo
        try:
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        except ImportError:  # for Python < 3.9, fall back to backports.zoneinfo
            from backports.zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        # Try to interpret the string as a timezone abbreviation
        if up in _TZ_ABBREV_TO_ZONE:
            zone_name = _TZ_ABBREV_TO_ZONE[up]
            return ZoneInfo(zone_name)

        # Try to interpret the string as a ZoneInfo name
        try:
            return ZoneInfo(tz_arg)
        except ZoneInfoNotFoundError as e:
            raise ValueError(f"Unknown timezone {tz_arg!r}: {e}") from e

    raise TypeError(f"Expected None, str, or tzinfo; got {type(tz_arg).__name__!r}")


def decimal_year_to_datetime(dec: float, use_astropy: bool = False) -> dt.datetime:
    """
    Convert a decimal year to a datetime object.
    If use_astropy is True, astropy.time is used for sub-second and leap-second–aware conversion.
    Usage: new_datetime_datetime_object = decimal_year_to_datetime(2002.291)
    """
    import datetime as dt
    if use_astropy:
        try:
            from astropy.time import Time
        except ImportError as e:
            raise ValueError(f"'use_astropy=True' requires the astropy package: {e}") from e
        t = Time(dec, format='jyear', scale='utc')
        return t.to_datetime().replace(tzinfo=dt.timezone.utc)

    try:
        year = int(dec)
        rem = dec - year
        start_dt = dt.datetime(year,     1, 1, tzinfo=dt.timezone.utc)
        end_dt   = dt.datetime(year + 1, 1, 1, tzinfo=dt.timezone.utc)
        year_secs = (end_dt - start_dt).total_seconds()
        return start_dt + dt.timedelta(seconds=rem * year_secs)
    except ValueError as e:
        raise ValueError(f"Failed to convert decimal year {dec} to datetime: {e}") from e


def _parse_iso(given_date: str) -> dt.datetime:
    """Parse an ISO8601 date string and return a datetime object. Raises ValueError if the date string is invalid."""
    from dateutil.parser import isoparse, ParserError

    try:
        return isoparse(given_date)
    except ParserError as e:
        raise ValueError(f"Invalid ISO8601 date '{given_date}': {e}") from e


def is_float(s: str) -> bool:
    """Check if a string can be parsed as a float."""
    try:
        float(s)
        return True
    except ValueError:
        return False


# Precompile Julian/MJD regex
# This regex is just used to check if a string looks like a JD or MJD:
_JD_MJD_SIMPLE  = re.compile(r"\s*(JD|MJD)?\s*[+-]?\d+(\.\d+)?\s*", re.IGNORECASE)
# This regex is used to capture the prefix (JD or MJD) and the value from a string that looks like a JD or MJD:
_JD_MJD_CAPTURE = re.compile(r"\s*(?P<prefix>JD|MJD)?\s*(?P<value>[+-]?\d+(?:\.\d+)?)\s*", re.IGNORECASE)
# This regex is used to check if a string has an explicit offset or Z at the end (indicating that the date should be converted by shifting the clock):
_OFFSET_IN_STR  = re.compile(r"(Z|[+-]\d{2}:\d{2}|[+-]\d{4})$")

# Enclose the type alias annotation in quotes because not all of these types have been imported yet.
AnyDateTimeType: TypeAlias = "str | float | int | np.datetime64 | pd.Timestamp | dt.datetime"


def _should_convert(given_date: AnyDateTimeType, format_str: str | None = None) -> bool:
    """Determine if the given date should be converted to a timezone (i.e. if the wall clock should be shifted) or if the timezone should just be attached without shifting the clock."""
    import datetime as dt

    # 1) Numbers, JD/MJD, decimal years, special keywords
    if isinstance(given_date, (int, float)) and not isinstance(given_date, bool):
        logging.debug(f"Given date is a number: {given_date}, so it will be converted by shifting the clock")
        return True
    if isinstance(given_date, str):
        u = given_date.strip().upper()
        if u in ('J2000', 'UNIX', 'NOW'):
            logging.debug(f"Given date is a special keyword: {u}, so it will be converted by shifting the clock")
            return True
        if format_str and format_str.upper() in ('JD', 'MJD'):
            logging.debug(f"Given date has a format_str: {format_str}, so it will be converted by shifting the clock")
            return True
        if _JD_MJD_SIMPLE.fullmatch(given_date):
            logging.debug(f"Given date is a JD/MJD: {given_date}, so it will be converted by shifting the clock")
            return True
        # explicit offset or Z
        if _OFFSET_IN_STR.search(given_date):
            logging.debug(f"Given date has an explicit offset or Z: {given_date}, so it will be converted by shifting the clock")
            return True
    # 2) Any datetime/timestamp already aware
    if isinstance(given_date, dt.datetime) and given_date.tzinfo is not None:
        logging.debug(f"Given date is an aware datetime: {given_date}, so it will be converted by shifting the clock")
        return True

    # Otherwise treat it as local‐time → attach only
    logging.debug(f"Given date is not a number, JD/MJD, or aware datetime: {given_date}, so the timezone will be attached without shifting the clock")
    return False


def _finalize_datetime(parsed_dt: dt.datetime, original_input: AnyDateTimeType,
                       format_str: str | None, tz_arg: str | dt.tzinfo | None,
                       should_convert: bool | None = None) -> dt.datetime:
    """Finalize the datetime object by either converting it to the target timezone or just attaching the timezone without shifting the clock. The boolean argument 'should_convert' can override the default behavior, which is determined by the function _should_convert()."""
    if isinstance(tz_arg, str) and tz_arg.strip().upper() == 'NAIVE':
        logging.debug(f"Naive timezone requested, returning datetime {parsed_dt} without any timezone info")
        return parsed_dt.replace(tzinfo=None)
    target_tz = parse_timezone(tz_arg)
    if should_convert is not False and (_should_convert(original_input, format_str) or should_convert is True):
        logging.debug(f"Converting datetime {parsed_dt} to timezone {target_tz} by shifting the clock")
        return parsed_dt.astimezone(target_tz)
    else:
        logging.debug(f"Attaching timezone {target_tz} to datetime {parsed_dt} without shifting the clock")
        return parsed_dt.replace(tzinfo=target_tz)


def parse_datetime(given_date: AnyDateTimeType, timezone: str | dt.tzinfo | None = None,
                   format_str: str | None = None,
                   should_convert: bool | None = None) -> dt.datetime:
    """
    Try parsing the given_date string or number into a datetime.datetime object in the specified timezone.

    If "format_str" is provided, it will be used to parse the date string. These format types are accepted:
     - "seconds" or "milliseconds" indicating the number of seconds or milliseconds since an epoch (Unix epoch by default).
     - "YYYY-MM-DD" or similar ISO8601 formats such as "YYYY-MM-DDTHH:MM:SS", "MM/DD/YYYY", etc.
     - A custom string following this pattern: "units (optional: since/after epoch)", where "units" can be anything that the function seconds_in_unit() accepts (e.g. "days", "weeks", "months", etc.). The optional epoch time can be a string, float, int, numpy.datetime64, pandas.Timestamp, or datetime.datetime object. Example: "days since 1990", "milliseconds after J2000", "sidereal days since 2000-01-01", etc. If the epoch is not specified, it defaults to the Unix epoch (1970-01-01T00:00:00Z)

    If a boolean "should_convert" is provided, it will override the default behavior of whether to convert the datetime to the specified timezone by shifting the clock or just attaching the timezone without shifting. If None, the function will determine this based on the type of given_date and format_str.

    If a given_date starts with "JD" or "MJD", it will be treated as a Julian Date or Modified Julian Date, respectively.

    Otherwise, if given_date is a float or int, treat it as a decimal year by default if format_str is not provided.

    Any call that doesn't provide a timezone argument will default to UTC.
    The timezone can be a datetime.tzinfo object or a string that can be converted to a ZoneInfo object (e.g. 'America/New_York').
    If the given_date is an "aware" datetime.datetime object which already has a timezone attached, it will be converted to the specified timezone (which may involve changing its date and time if the specified timezone is different).
    The timezone can also be a fixed‐offset like "+05:30" or "-04:00", or the string "Naive" to indicate that the datetime should be treated as a naive datetime (i.e. without any timezone information).

    Accepts:
      - 'NOW' (case-insensitive) → current datetime
      - strings in YYYY, YYYY-MM, YYYY-MM-DD, YYYY-MM-DDTHH:MM:SS, or other ISO8601 formats (e.g. '2002-10-18T07:00:00Z', '2002-10-18 07:00:00+00:00').
      - If YYYY is provided, it will default to January 1st of that year at midnight.
      - If YYYY-MM is provided, it will default to the first day of that month at midnight.
      - If YYYY-MM-DD is provided, it will default to midnight on that day.
      - fallback to dateutil.parser.parse for free-form strings ("18 Oct 2002", "March 5th, 2020", etc.)
      - floats (e.g. 2002.29178082191777) or integer (e.g. 2002) → decimal year
      - numpy.datetime64 objects (e.g. np.datetime64('2002-10-18T07:00:00'))
      - pandas.Timestamp objects (e.g. pd.Timestamp('2002-10-18 07:00:00'))
      - datetime.datetime objects (e.g. datetime.datetime(2002, 10, 18, 7, 0, 0))

    Returns:
      datetime.datetime object in the specified timezone.
      Note that datetime.datetime objects cannot represent dates before 1 January 1, 0001 or after 31 December 9999.
      So dates outside this range will raise a ValueError. Future versions of this code may support a wider range of dates (like 44 BC, 44 BCE, etc.) using libraries like 'astropy.time': https://chatgpt.com/share/685c5157-5cac-8006-b68c-4a0731927a50
      However, this will require the function to return an 'astropy.time.Time' object instead of a 'datetime.datetime' object.
    """
    import datetime as dt
    fallback_logging_config()  # Ensure logging is configured

    parsed_tz = parse_timezone(timezone)  # Ensure timezone is a valid tzinfo object or string

    parsed_dt = None

    # Handle special cases:
    if isinstance(given_date, str):
        if given_date.strip().upper() == 'J2000':
            # J2000 is January 1, 2000, 11:58:55.816 UTC
            parsed_dt = dt.datetime(2000, 1, 1, 11, 58, 55, 816_000, tzinfo=dt.timezone.utc)
        if given_date.strip().upper() == 'UNIX':
            # UNIX epoch is January 1, 1970, 00:00:00 UTC
            parsed_dt = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
        if given_date.strip().upper() == "NOW":
            parsed_dt = dt.datetime.now(tz=dt.timezone.utc)

    # Handle forced or explicit Julian Date (JD) or Modified Julian Date (MJD)
    m = None
    prefix = None
    if parsed_dt is None and isinstance(given_date, str):
        m = _JD_MJD_CAPTURE.fullmatch(given_date)
        if m:
            prefix = m.group('prefix')

    # Trigger JD/MJD branch only if format_str equals "JD" or "MJD", or prefix was provided
    if parsed_dt is None and (prefix is not None or (format_str and (format_str.upper() == 'JD' or format_str.upper() == 'MJD'))):

        try:
            import jdcal
        except ImportError:
            raise ImportError("The jdcal python library is required to parse Julian/MJD dates")

        # Determine raw value
        if isinstance(given_date, (int, float)):
            value = float(given_date)
        else:
            value = float(m.group('value'))

        # Determine if MJD conversion needed
        use_mjd = bool((format_str and format_str.upper() == 'MJD') or (prefix and prefix.upper() == 'MJD'))

        # Convert MJD to JD if necessary
        jd_val = value + (2_400_000.5 if use_mjd else 0.0)

        # Split into integer day and fraction
        int_part = int(jd_val)
        frac_part = jd_val - int_part
        year, month, day, day_frac = jdcal.jd2gcal(int_part, frac_part)

        # Convert day fraction to hours, minutes, seconds, microseconds
        day_int = int(day)
        frac_of_day = (day + day_frac) - day_int
        hours = int(frac_of_day * 24)
        mins = int((frac_of_day * 24 - hours) * 60)
        secs_frac = (frac_of_day * 24 - hours) * 60 - mins
        secs = int(secs_frac * 60)
        micros = int((secs_frac * 60 - secs) * 1e6)
        parsed_dt = dt.datetime(year, month, day_int, hours, mins, secs, micros, tzinfo=dt.timezone.utc)

    # Check if the given_date is a string that can be parsed as a float
    if parsed_dt is None and isinstance(given_date, str) and is_float(given_date):
        given_date = float(given_date)  # Convert string to float if it represents a number
    # Check if the given_date is a float or int but NOT a boolean
    if parsed_dt is None and isinstance(given_date, (int, float)) and not isinstance(given_date, bool):
        if format_str is None:
            # If the given_date is a decimal year, convert it to datetime in the specified timezone
            # Note: This will not shift the clock, just attach the tzinfo.
            parsed_dt = decimal_year_to_datetime(float(given_date))
        else:  # If format is provided, parse the date using the specified format.
            if not isinstance(format_str, str):
                raise TypeError(f"Expected 'format' to be a string, got {type(format_str).__name__!r}")
            # Make sure the format string is a valid example of "units (optionally: since/after epoch)"
            # Try to split by since or after, whichever works:
            format_parts = re.split(r'\s+(since|after)\s+', format_str, maxsplit=1)
            logging.debug(f"Parsing date with format string: '{format_str}' split into parts: {format_parts}")
            if len(format_parts) > 3:
                raise ValueError(f"Invalid format string: '{format_str}'. Expected at most three parts: 'units', 'since/after', and 'epoch'.")
            # The first part should be acceptable by seconds_in_unit():
            try:
                units = format_parts[0].strip()
                multiplier = seconds_in_unit(units)  # This will raise ValueError if the unit is unknown
            except ValueError as e:
                raise ValueError(f"Invalid time unit '{units}' in format string '{format_str}': {e}") from e
            # If the format_parts list has only one part, it means the epoch defaults to the Unix epoch (1970-01-01T00:00:00Z).
            if len(format_parts) == 1:
                # If the format_parts list has only one part, it means the format is just "units" (e.g. "days", "weeks", etc.)
                # In this case, we assume the epoch is the Unix epoch (1970-01-01T00:00:00Z).
                epoch_str = '1970-01-01T00:00:00Z'
            else:
                # If the format_parts list has three parts, the third part is the epoch.
                epoch_str = format_parts[2].strip()
            try:
                epoch = parse_datetime(epoch_str, timezone=parsed_tz)
            except ValueError as e:
                raise ValueError(f"Invalid epoch '{epoch}' in format string '{format_str}': {e}") from e
            # Now we can calculate the datetime based on the given_date (and the multiplier from 'units') and the epoch
            parsed_dt = epoch + dt.timedelta(seconds=float(given_date) * multiplier)

    if parsed_dt is None and type(given_date) is dt.datetime:  # Don't use isinstance() here, because it will also match subclasses like Pandas Timestamp
        parsed_dt = given_date
    elif isinstance(given_date, dt.date):  # Handle date objects (without time) as midnight
        parsed_dt = dt.datetime.combine(given_date, dt.time.min)

    if parsed_dt is None:
        try:
            import numpy as np
        except ImportError:
            np = None
        if np is not None and isinstance(given_date, np.datetime64):
            ts_ns = given_date.astype('datetime64[ns]').astype('int64')
            parsed_dt = dt.datetime.fromtimestamp(ts_ns/1e9, tz=parsed_tz)

    if parsed_dt is None:
        try:
            import pandas as pd
        except ImportError:
            pd = None
        if pd is not None and isinstance(given_date, pd.Timestamp):
            parsed_dt = given_date.to_pydatetime()

    error_message = f"The date '{given_date}' is type {type(given_date).__name__!r} in an unknown format. Please use NOW, YYYY, YYYY-MM, YYYY-MM-DD, YYYY-MM-DDTHH:MM:SS, other ISO8601 strings, or a decimal year like 2002.291. Datetimes in pandas.Timestamp, numpy.datetime64, or datetime.datetime formats are also accepted and will be converted to datetime.datetime objects in the specified timezone ({parsed_tz})."

    if parsed_dt is None and not isinstance(given_date, str):
        raise TypeError(error_message)

    if parsed_dt is None and format_str is not None:
        try:
            parsed_dt = dt.datetime.strptime(given_date, format_str)
        except ValueError as e:
            raise ValueError(f"Invalid date format '{given_date}' with specified format '{format_str}': {e}") from e

    # Try parsing the date string in various formats
    # Start with RFC 2822 format, then ISO8601, then free-form strings
    # Store any errors encountered in a list to provide feedback if all parsing attempts fail.
    errors = []

    if parsed_dt is None:
        import email.utils
        try:
            # parses "Tue, 25 Jun 2025 14:00:00 GMT"
            parsed_dt = email.utils.parsedate_to_datetime(given_date)
        except (TypeError, ValueError) as e:
            errors.append(f"Failed to parse '{given_date}' as an RFC 2822 date: {e}")

    if parsed_dt is None:
        try:
            parsed_dt = _parse_iso(given_date)
        except ValueError as e:
            errors.append(f"Failed to parse '{given_date}' as an ISO8601 date: {e}")

    if parsed_dt is None:
        try:
            from dateutil.parser import parse as parse_fuzzy
            parsed_dt = parse_fuzzy(given_date, default=dt.datetime(1900, 1, 1))
        except ValueError as e:
            errors.append(f"Failed to parse '{given_date}' as a free-form date string: {e}")

    if parsed_dt is None:
        if np is None:
            errors.append("The numpy package is not installed, so numpy.datetime64 objects cannot be parsed.")
        if pd is None:
            errors.append("The pandas package is not installed, so pandas.Timestamp objects cannot be parsed.")
    else:
        # Finalize the datetime object by converting it to the target timezone or just attaching the timezone without shifting the clock
        return _finalize_datetime(parsed_dt, given_date, format_str, parsed_tz, should_convert)

    raise ValueError(error_message + "\n".join(errors) + "\nPlease check the input format and try again.")


def sci_exp(float_input: float | int, max_digits: int = 15) -> int:
    """Return the scientific exponent of an integer or floating point number. An optional max_digits parameter can be specified to determine the maximum number of digits to consider for very small numbers; if the number is smaller than 10^(-max_digits), just say it has max_digits. By default, max_digits is 15."""
    import math
    if abs(float_input) < 10**(-max_digits): return -max_digits
    return int(math.floor(math.log10(abs(float_input))))


def round_out(x: float, round_digits: int = 3, max_digits: int = 15) -> float:
    """
    Round a number away from zero (i.e. rounds up for x>0 and down for x<0) to
    the specified number of significant figures (defaults to 3).
    If the number is smaller than 10^(-max_digits), it will be returned as is.
    The max_digits parameter defaults to 15, but can be changed to a different value if needed.

    Parameters:
        x            : The number to round.
        round_digits : The number of significant figures to round to (default is 3).
        max_digits   : The maximum number of digits to consider for very small numbers (default is 15).

    Returns:
        float : The rounded number, or the original number if it is smaller than 10^(-max_digits).
    """
    import numpy as np
    if np.abs(x) < 10**(-max_digits): return x
    these_digits = sci_exp(x) - round_digits + 1
    thisfactor = 10**these_digits
    x = x/thisfactor
    if x > 0: x = np.ceil(x)
    else:     x = np.floor(x)
    return x*(thisfactor*1.0)


def prompt_then_confirm(prompt: str) -> bool:
    """Prompt the user with the given message and return True if the user enters 'yes', False otherwise."""
    confirmation = input(prompt)
    return confirmation.casefold() == 'yes' or confirmation.casefold() == 'y'


def prompt_then_choose(prompt: str, choices: list[str], default: str = None) -> str:
    """
    Show a numbered list of choices and prompt the user to select one.

    Parameters:
        prompt : The message to display before the choices.
        choices : A list of choices to present to the user.
        default : The default choice to return if the user presses Enter without inputting a choice.

    Returns:
        str : The selected choice from the list (or the default if provided).
    """
    fallback_logging_config()

    logging.info(prompt)
    for i, choice in enumerate(choices, 1):
        logging.info(f"  {i}) {choice}")
    prompt = f"Select [1-{len(choices)}]"
    if default is not None:
        prompt += f" (default {default}): "
    else:
        prompt += ": "

    while True:
        ans = input(prompt).strip()
        if not ans and default:
            logging.info(f"No input provided, using default: {default}")
            return default
        if ans.isdigit() and 1 <= int(ans) <= len(choices):
            logging.info(f"User selected choice {ans}: {choices[int(ans)-1]}")
            return choices[int(ans)-1]
        logging.warning("Invalid choice, try again.")


def my_capitalize(string_to_capitalize: str) -> str:
    """Capitalize ONLY the first letter of a string and DON'T modify the rest of it."""
    if not string_to_capitalize:
        return ""
    return string_to_capitalize[0].upper() + string_to_capitalize[1:]


def my_title_case(the_title: str) -> str:
    """Capitalize the first letter of each word, but if a word already has ANY uppercase letters, leave it as is. This way, words like "WW2" or "iZombie" won't be modified."""
    words = the_title.split()
    capitalized_words = [word if any(letter.isupper() for letter in word)
                         else word.title() for word in words]
    return ' '.join(capitalized_words)


def filename_format(text: str, sep: str = "_", max_length: int = None) -> str:
    """
    Turn arbitrary text into an ASCII-only, filesystem‐safe base filename.
    WARNING: Do not include an extension in the text, because this function
    will remove the dot which separates the filename from the extension.

    Steps:
      1. Unicode → ASCII
      2. Treat dots, underscores & whitespace as word separators
      3. Remove any character that isn't A-z, a–z, 0–9, dashes, or the separator
      4. Collapse runs of separators into a single one
      5. Trim separators from ends
      6. Optionally truncate to max_length (preserving word boundaries)

    Args:
        text:        Original filename or title
        sep:         Single-character separator (default: "_")
        max_length:  If set, strongest‐effort truncate to this many chars

    Returns:
        A clean, filename-safe string.
    """
    fallback_logging_config()  # Ensure logging is configured
    # 1. Normalize to ASCII
    try:
        import unidecode
        text = unidecode.unidecode(text)
    except ImportError:
        logging.warning("unidecode package not found, falling back to ASCII encoding.")
        # Fallback: encode to ASCII, ignore errors
        text = text.encode('ascii', 'ignore').decode('ascii')

    # 2. Replace common "word boundaries" with sep
    #    (dots, underscores, whitespace) but keep dashes
    #    e.g. "hello.world--foo_bar" → "hello world--foo bar"
    text = re.sub(r"[._\s]+", sep, text)

    # 3. Remove anything but dashes, a–z, 0–9, or our sep
    allowed = f"-A-Za-z0-9{re.escape(sep)}"
    text = re.sub(fr"[^{allowed}]+", "", text)

    # 4. Collapse runs of sep (e.g. "__" → "_")
    text = re.sub(fr"{re.escape(sep)}{{2,}}", sep, text)

    # 5. Strip leading/trailing seps
    text = text.strip(sep)

    # 6. Optionally truncate (try not to cut in middle of a word)
    if max_length is not None and len(text) > max_length:
        # cut at max_length, then drop a partial trailing token if any
        truncated = text[:max_length]
        # if the next char in original isn't sep and our chop landed mid-token, trim back to last sep
        if (len(text) > max_length and not truncated.endswith(sep) and sep in truncated):
            truncated = truncated.rsplit(sep, 1)[0]
        text = truncated

    return text


def if_filepath_then_read(input_string_or_filepath: str,
                          force_string: bool = False) -> str:
    """
    If 'input_string_or_filepath' is a file path, read its contents and return as a string. If not, return the input_string as is.

    Parameters:
        input_string_or_filepath : The source can be a file path or a string.
        force_string : If True, treat 'input_string_or_filepath' as a string even if it looks like a file path.

    Returns:
        str : The contents of the file if input_string is a file path, or the input_string itself if it is not a file path.

    Raises:
        TypeError : If input_string is not a string or a file path.
    """
    fallback_logging_config()
    # Is "input_string" a file path, and is "force_string" False?
    # If so, read the file contents.
    if os.path.isfile(input_string_or_filepath) and not force_string:
        file_path = input_string_or_filepath
        try:
            contents = my_fopen(file_path, suppress_errors=True)
            if not contents:
                logging.error(f"Could not read file: {file_path}")
                return ""
            return contents
        except FileNotFoundError as e:
            logging.exception(f"File not found: {file_path}")
        except PermissionError as e:
            logging.exception(f"Permission denied: {file_path}")
        except UnicodeDecodeError as e:
            logging.exception(f"Could not decode {file_path!r}.")
    else:  # Otherwise, treat "input_string" as a string.
        if not isinstance(input_string_or_filepath, str):
            raise TypeError(f"Expected 'input_string_or_filepath' to be a string or file path, got {type(input_string_or_filepath).__name__!r}")
        return input_string_or_filepath  # Just return the input string as is.


def compile_code(source_or_filepath: str,
                 force_source: bool = False) -> bool:
    """
    Attempt to compile the given source code in 'exec' mode.
    If 'source_or_filepath' is a file path, read its contents first.

    Parameters:
        source_or_filepath : The source code string or file path to compile.
        force_source : If True, treat 'source_or_filepath' as a source code string even if it looks like a file path.

    Returns:
        bool : True if compilation succeeds, False if it fails with a SyntaxError or other exception
    """
    fallback_logging_config()
    # Read from file if source is a file path
    source = if_filepath_then_read(source_or_filepath, force_string=force_source)
    if source != source_or_filepath:
        file_path = source_or_filepath
    else:
        # If it's a string, we need to provide a dummy file path for the compiler.
        # This is just to satisfy the compiler, it won't be used.
        file_path = "<string>"
    try:
        compile(source, file_path, "exec")
    except SyntaxError as e:
        # protect against None offsets
        lineno = e.lineno or '?'
        offset = e.offset or 0
        line = (e.text or '').rstrip('\n')
        pointer = ' ' * (offset - 1) + '^' if offset else ''
        logging.error(f"Syntax error in {e.filename!r}, line {lineno}, column {offset}:\n"
                      f"    {line}\n"
                      f"    {pointer}\n"
                      f"    {e.msg!r}", exc_info=True)
        return False
    return True


# --------------------------------------------------------------------------------
# Note: Python resolves base classes at the moment a class statement is executed.
# That means any names used as base classes (e.g., ast.NodeVisitor) must already
# be defined in the current scope when the class is created.
#
# If we defer importing 'ast' until inside a function but still try to define
# the class at the module level, Python will raise:
#     NameError: name 'ast' is not defined
#
# Wrapping the class definition in a factory function lets us:
#   1) Import 'ast' inside the function, so it's guaranteed to be in scope
#      when we define the class.
#   2) Keep module‑level imports to a minimum (only __future__ and typing).
#   3) Return the fully‑constructed class and assign it to the module name.
#
# In short: by defining FormatChecker inside this helper, we avoid NameError
# and still get a clean, well‑typed class available at the module level.
# --------------------------------------------------------------------------------


def _make_format_checker() -> Type[FormatChecker]:
    """Factory function to create the FormatChecker class with the necessary imports."""
    import ast

    class FormatChecker(ast.NodeVisitor):
        """
        Walks a module AST and collects formatting violations:
        - missing type hints on params / return
        - missing docstring or incorrect docstring quote style
        """

        def __init__(self, source: str, doc_style: str = "None") -> None:
            """Initialize the FormatChecker with the source code string."""
            self.source = source
            self.doc_style = doc_style # "None", "NumPy", "Google", "reStructuredText"
            self.errors: list[tuple[str, str, str, int]] = []
            self._seen_funcs: set[int] = set()  # keep track of which FunctionDef/AsyncFunctionDef nodes we've already checked

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            """Visit a FunctionDef node and check for formatting violations."""
            self._check_function(node)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            """Visit an AsyncFunctionDef node and check for formatting violations."""
            self._check_function(node)
            self.generic_visit(node)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            """Visit a ClassDef node and check for formatting violations."""
            self._check_docstring(node, f'class "{node.name}"')
            init = self._find_init(node)
            if init:
                self._check_function(init, in_method=True, container=f'class "{node.name}"')
            self.generic_visit(node)

        def _find_init(self, node: ast.ClassDef) -> ast.FunctionDef | None:
            """Find the __init__ method in a class definition."""
            for elt in node.body:
                if isinstance(elt, (ast.FunctionDef, ast.AsyncFunctionDef)) and elt.name == "__init__":
                    return elt  # type: ignore
            return None

        def _check_function(self, node: ast.FunctionDef, *, in_method: bool = False, container: str | None = None) -> None:
            """Check a function or method node for formatting violations.
            If 'in_method' is True, it indicates that this is a method (e.g. inside a class).
            If 'container' is provided, it indicates the context (e.g. class name)."""
            if id(node) in self._seen_funcs:  # ←─ skip if we've already run this exact node
                return
            self._seen_funcs.add(id(node))
            who = (f'function "{node.name}"' if container is None else f'{container} → method "{node.name}"')
            self._check_docstring(node, who)

            missing: list[str] = []
            args = [a for a in node.args.args if a.arg != "self"]
            for a in args + node.args.kwonlyargs:
                if a.annotation is None:
                    missing.append(f'param "{a.arg}"')
            if node.args.vararg and node.args.vararg.annotation is None:
                missing.append(f'param "*{node.args.vararg.arg}"')
            if node.args.kwarg and node.args.kwarg.annotation is None:
                missing.append(f'param "**{node.args.kwarg.arg}"')
            if node.returns is None:
                missing.append("return")
            if missing:
                self.errors.append(("function", node.name,
                                    "missing type hints for " + ", ".join(missing),
                                    node.lineno))

        def _check_docstring(self, node: ast.AST, who: str) -> None:
            """
            Check a node for a docstring and its formatting.
            An error is added to self.errors if:
              - The node has no docstring
              - The docstring is not formatted correctly
              - There is more than one docstring
            The 'who' parameter is a string describing the context (e.g. function or class name).
            """
            if not node.body or not isinstance(node.body[0], ast.Expr):
                self.errors.append((node.__class__.__name__.lower(), who, "no docstring",
                                    node.lineno))
                return

            expr = node.body[0]
            if not (isinstance(expr.value, ast.Constant) and isinstance(expr.value.value, str)):
                self.errors.append((node.__class__.__name__.lower(), who, "no docstring",
                                    node.lineno))
                return

            # Recover the exact literal to verify triple-double-quote
            literal = ast.get_source_segment(self.source, expr.value) or ""
            first_line = literal.strip().splitlines()[0]
            if first_line.startswith("'''"):
                self.errors.append((node.__class__.__name__.lower(), who,
                                    'docstring should use triple double quotes ("""…""")',
                                    node.lineno))

            # Now scan for any extra standalone triple‐quoted strings
            for extra in node.body[1:]:
                # Only look at Exprs, i.e. un‐assigned string literals
                if  isinstance(extra, ast.Expr) \
                and isinstance(extra.value, ast.Constant) \
                and isinstance(extra.value.value, str):
                    literal = ast.get_source_segment(self.source, extra.value) or ""
                    first = literal.strip().splitlines()[0]
                    # If it starts with triple quotes, it’s an extra docstring
                    if first.startswith(('"""', "'''")):
                        self.errors.append((node.__class__.__name__.lower(),
                                            who, "extra docstring", extra.lineno))

            # Check the docstring style
            self._check_docstring_style(node, who)

        def _check_docstring_style(self, node: ast.AST, who: str) -> None:
            """Dispatch to the style‑specific docstring checker."""
            if not self.doc_style or self.doc_style.casefold() == "none":
                return
            checker = {
                "NumPy"              : self._check_numpy_docstring,
                # "Google"           : self._check_google_docstring,
                # "reStructuredText" : self._check_rst_docstring,
            }.get(self.doc_style)

            if checker is not None:
                checker(node, who)

        def _check_numpy_docstring(self, node: ast.AST, who: str) -> None:
            """
            Very basic NumPy‑style docstring validator:
            - must have a 'Parameters' and 'Returns' section header
            - every non‑self arg must be listed under Parameters
            """
            # Get the cleaned docstring
            doc = ast.get_docstring(node)
            if not doc:
                return  # already flagged as missing

            lines = doc.splitlines()
            # Locate the section headers
            try:
                params_idx = next(i for i, L in enumerate(lines) if L.strip() == "Parameters")
            except StopIteration:
                self.errors.append((node.__class__.__name__.lower(), who,
                                    "NumPy docstring missing 'Parameters' section",
                                    node.lineno))
                return

            try:
                returns_idx = next(i for i, L in enumerate(lines) if L.strip() == "Returns")
            except StopIteration:
                self.errors.append((node.__class__.__name__.lower(), who,
                                    "NumPy docstring missing 'Returns' section",
                                    node.lineno))

            # Collect documented params: lines immediately under 'Parameters'
            documented = set()
            for line in lines[params_idx+1:]:
                if not line.strip():
                    break
                m = re.match(r'^(\w+)\s*:\s*(.+)$', line)
                if m:
                    documented.add(m.group(1))

            # Get function args (excluding self)
            sig_args = []
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sig_args = [a.arg for a in node.args.args if a.arg != "self"]

            missing = [a for a in sig_args if a not in documented]
            if missing:
                self.errors.append((node.__class__.__name__.lower(), who,
                                    "NumPy docstring missing parameter(s): " + ", ".join(missing), node.lineno))

    return FormatChecker


FormatChecker = _make_format_checker()


def check_python_formatting(path: str, diff_choice: int = 1) -> bool:
    """
    Reads a .py file at 'path' via my_fopen, makes sure it compiles, parses it with my_ast_parse,
    prints any custom formatting violations to stdout,
    and asks the user to fix any backticks or curly quotes in the file. If the user quits, it returns False.

    Parameters:
        path:        The path to the Python file to check.
        diff_choice: How many context lines to show in the diff (0 = old-style diff, 1 = unified diff with 0 context lines, 2+ = unified diff with 'diff_choice - 1' context lines).
    """
    fallback_logging_config()
    src = my_fopen(path)
    if src is False:
        logging.error(f"❌ Failed to open file: {path}")
        return

    if compile_code(src):
        logging.info(f"✅ {path} compiled successfully.")

    BACKTICK  = "\u0060"      # U+0060 "GRAVE ACCENT" (the backtick)
    LSQUOTE   = "\u2018"      # U+2018 "LEFT  SINGLE QUOTATION MARK" (curly apostrophe)
    RSQUOTE   = "\u2019"      # U+2019 "RIGHT SINGLE QUOTATION MARK" (curly apostrophe)
    LDQUOTE   = "\u201C"      # U+201C "LEFT  DOUBLE QUOTATION MARK"
    RDQUOTE   = "\u201D"      # U+201D "RIGHT DOUBLE QUOTATION MARK"

    if BACKTICK in src:
        logging.warning(f"File {path} contains the backtick character ({BACKTICK!r}). Use straight quotation marks (') instead.")
        if not ask_and_replace(path, old=BACKTICK, new="'", label='backtick', diff_choice=diff_choice,
                               description=f"Replace backtick ({BACKTICK}) with straight apostrophe (')"):
            return False
    if LSQUOTE in src or RSQUOTE in src:
        logging.warning(f"File {path} contains curly single quotation marks ({LSQUOTE!r} or {RSQUOTE!r}). Use straight apostrophes (') instead.")
        if not ask_and_replace(path, old=LSQUOTE, new="'", label='left-curly-apostrophe', diff_choice=diff_choice,
                               description=f"Replace left curly apostrophe ({LSQUOTE}) with straight apostrophe (')"):
            return False
        if not ask_and_replace(path, old=RSQUOTE, new="'", label='right-curly-apostrophe', diff_choice=diff_choice,
                               description=f"Replace right curly apostrophe ({RSQUOTE}) with straight apostrophe (')"):
            return False
    if LDQUOTE in src or RDQUOTE in src:
        logging.warning(f'File {path} contains curly double quotation marks ({LDQUOTE!r} or {RDQUOTE!r}). Use straight quotation marks (") instead.')
        if not ask_and_replace(path, old=LDQUOTE, new='"', label='left-curly-quotation-mark', diff_choice=diff_choice,
                               description=f'Replace left curly double quotation mark ({LDQUOTE}) with straight double quotation mark (")'):
            return False
        if not ask_and_replace(path, old=RDQUOTE, new='"', label='right-curly-quotation-mark', diff_choice=diff_choice,
                               description=f'Replace right curly double quotation mark ({RDQUOTE}) with straight double quotation mark (")'):
            return False
    try:
        tree = my_ast_parse(src, path)
    except SyntaxError:
        logging.exception(f"❌ {path} contains a syntax error.")
        return False

    checker = FormatChecker(src)
    checker.visit(tree)

    if not checker.errors:
        logging.info("🎉 All functions and classes conform to the custom formatting rules.")
    else:
        max_lineno = max(err[3] for err in checker.errors)
        the_digits = sci_exp(max_lineno) + 1
        for kind, name, msg, lineno in checker.errors:
            logging.error(f"{lineno:>{the_digits}} – {kind.capitalize()} {name}: {msg}")

    return True


def run_flake8(path: str, ignore_codes: list[str] = [], max_line_length: int = 100) -> flake8.Report:
    """
    Run Flake8 on 'path', but:
      - only flag E501 if a line exceeds 'max_line_length',
      - ignore whatever codes are in 'ignore_codes'.

    :param path:       File or directory to lint.
    :param max_line_length:  The line‑length threshold for E501 (default 100).
    :return:           A Flake8 Report object with all violations.
    """
    import io
    from collections import defaultdict
    from flake8.api import legacy as flake8
    style_guide = flake8.get_style_guide(max_line_length=max_line_length, ignore=ignore_codes)
    report = style_guide.check_files([path])
    if report.total_errors == 0:
        logging.info(f"✅ No Flake8 violations found in {path}.")
        return report
    logging.error(f"Found {report.total_errors} total violations in {path}:")
    for stat in report.get_statistics(""):
        logging.error(f"  {stat}")

    # This section was SUPPOSED to print a grouped summary of violations by code with line numbers.
    # However, it CORRUPTS THE FILE IT IS EXAMINING! https://chatgpt.com/share/688ba75b-7860-8006-bc9f-1bce8cb01359
    # BEWARE: DO NOT USE THIS CODE!
    # # Create a StringIO and tell flake8 to write its output there
    # buf = io.StringIO()
    # style = flake8.get_style_guide(max_line_length=max_line_length, ignore=ignore_codes, output_file=buf)

    # # Run the checks
    # report = style.check_files([path])  # path is your filename or list of files
    # # now force every violation to be written into our StringIO
    # formatter = style._application.formatter
    # for violation in style._application.file_checker_manager.results:
    #     formatter.handle(violation)
    # formatter.stop()

    # # Rewind and parse each line of the report
    # buf.seek(0)
    # logging.info("\n" + buf.getvalue())
    # buf.seek(0)
    # by_code = defaultdict(list)
    # for line in buf:
    #     # Each line looks like: "univ_defs.py:1501:9: F841 local variable 'e' is assigned to but never used"
    #     parts = line.strip().split(":", 3)
    #     if len(parts) < 4:
    #         continue
    #     _, lineno_str, _, rest = parts
    #     code = rest.strip().split()[0]      # e.g. "F841"
    #     by_code[code].append(int(lineno_str))

    # # Print a grouped summary
    # breakpoint()
    # for code, lines in sorted(by_code.items()):
    #     lines = sorted(set(lines))
    #     print(f"{code}: line{'s' if len(lines)>1 else ''} {', '.join(map(str, lines))}")

    return report


def _gather_flake8_issues( path: str, ignore_codes: list[str] = [], max_line_length: int = 100) -> dict[str, str]:
    """
    Returns a dict mapping each Flake8 error code to its first-seen description
    in the file at 'path'.
    Tries the 'flake8' CLI (fast), but if it's not on PATH, falls back
    to an in-process Application/API solution.
    """
    try:
        return _gather_via_cli(path, max_line_length, ignore_codes)
    except FileNotFoundError:
        return _gather_via_app(path, max_line_length, ignore_codes)


def _gather_via_cli(path: str, max_line_length: int, ignore_codes: list[str]) -> dict[str, str]:
    """Use the flake8 CLI to gather codes and descriptions."""
    import subprocess
    fmt = "%(row)d:%(col)d: %(code)s %(text)s"
    args = [
        "flake8",
        f"--max-line-length={max_line_length}",
        f"--ignore={','.join(ignore_codes)}",
        f"--format={fmt}",
        path,
    ]
    proc = subprocess.run(args, capture_output=True, text=True)
    codes: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        # e.g. "12:5: E302 expected 2 blank lines, found 1"
        parts = line.split(": ", 1)
        if len(parts) != 2:
            continue
        _, rest = parts
        code, desc = rest.split(" ", 1)
        codes.setdefault(code, desc)
    return codes


def _gather_via_app(path: str, max_line_length: int, ignore_codes: list[str]) -> dict[str, str]:
    """Use the flake8 Application API to gather codes and descriptions."""
    from flake8.main.application import Application
    from flake8.formatting.base import BaseFormatter
    from flake8.violation import Violation

    class CodeDictFormatter(BaseFormatter):
        """Custom formatter that collects codes and their first descriptions."""
        def __init__(self, options: dict[str, str]) -> None:
            """Initialize the formatter with options."""
            super().__init__(options)
            self.codes: dict[str, str] = {}

        def format(self, error: Violation) -> str:
            """Format a single error, capturing its code and description."""
            # capture the first description we see for each code
            self.codes.setdefault(error.code, error.text)
            # suppress any actual stdout
            return ""

    class CodeDictApp(Application):
        """Custom Application subclass to use our CodeDictFormatter."""
        def make_formatter(self) -> BaseFormatter:
            """Create a custom formatter that collects codes and descriptions."""
            # force our custom formatter
            self.formatter = CodeDictFormatter(self.options)
            return self.formatter

    app = CodeDictApp()
    # supply exactly the same CLI settings in-process
    cli_args = [f"--max-line-length={max_line_length}", f"--ignore={','.join(ignore_codes)}", path]
    # this will parse, run checks, and invoke our formatter behind the scenes
    app.run(cli_args)
    # the formatter collected everything into .codes
    return app.formatter.codes


def get_autopep8_fixable_codes() -> set[str]:
    """
    Run 'autopep8 --list-fixes' (via subprocess) to discover exactly
    which Flake8 error‐codes autopep8 knows how to fix.
    Returns a set like {"E101","E111", …}.
    """
    import subprocess
    fallback_logging_config()
    try:
        proc = subprocess.run(["autopep8", "--list-fixes"], capture_output=True, text=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        logging.warning(f"autopep8 not found or failed.", exc_info=True)
        # autopep8 not on PATH or error—assume nothing fixable
        return set()

    fixable: set[str] = set()
    for line in proc.stdout.splitlines():
        # the output looks like:
        #   E101 - indentation not consistent
        #   E111 - indent does not match any outer indentation level
        # so take the code before the colon
        if " - " in line:
            code = line.split(" - ", 1)[0].strip()
            if code:
                fixable.add(code)
    return fixable


def _vis_trailing_ws(line: str) -> str:
    """
    Replace only the trailing spaces and tabs in 'line'
    with visible glyphs (· for space, → for tab).
    """
    core = line.rstrip(" \t")
    trail = line[len(core):]
    return core + trail.replace(" ", "·").replace("\t", "→")


def _vis_all_ws(s: str) -> str:
    """
    Show *all* spaces/tabs in s as visible glyphs:
      · for space, → for tab
    """
    return s.replace(" ", "·").replace("\t", "→")


def highlight_changes(orig: str, new: str, unchanged_color: str,
                      added_color: str, deleted_color: str) -> tuple[str, str]:
    """
    Compare 'orig' and 'new' strings and return a tuple
    (old_highlighted, new_highlighted), where:
    - old_highlighted has parts present only in 'orig' wrapped in deleted_color.
    - new_highlighted has parts present only in 'new' wrapped in added_color
      and unchanged parts in unchanged_color.
    """
    import difflib
    sm = difflib.SequenceMatcher(None, orig, new)
    new_out = []
    old_out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        old_segment = orig[i1:i2]
        new_segment =  new[j1:j2]
        if tag == 'equal':
            new_out.append(f"{unchanged_color}{new_segment}{ANSI_RESET}")
            old_out.append(old_segment)
        elif tag == 'replace':  # segments changed: mark old text as deleted, new text as added
            new_out.append(f"{added_color}{new_segment}{ANSI_RESET}")
            old_out.append(f"{deleted_color}{old_segment}{ANSI_RESET}")
        elif tag == 'delete':  # text removed: mark in old, nothing in new
            old_out.append(f"{deleted_color}{old_segment}{ANSI_RESET}")
        elif tag == 'insert':  # text added: mark in new, nothing in old
            # text added: if it's *only* whitespace, render it visibly
            if set(new_segment) <= {' ', '\t'}:
                visible = _vis_all_ws(new_segment)
            else:
                visible = new_segment
            new_out.append(f"{added_color}{visible}{ANSI_RESET}")
    return ''.join(old_out), ''.join(new_out)


def my_diff(orig_text: str, changed_text: str, orig_path: str,
            changed_path: str | None = None,
            diff_choice: int = 1, changed_color: str = ANSI_CYAN,
            deleted_color: str = ANSI_RED, added_color: str = ANSI_YELLOW) -> None:
    """
    Show a unified diff of orig_text → changed_text with 'context' lines
    around each hunk, log using 'label' and 'description', then prompt.
    If the user confirms, overwrite 'path' with changed_text and return True.
    If the user chooses to quit, log a message and return False.

    Parameters:
        orig_text:      Original text to compare against.
        changed_text:   Proposed changes to the original text.
        orig_path:      Path to the original file.
        changed_path:   Optional path to the changed file (if different).
        label:          A short label for the issue being fixed.
        diff_choice:    How many context lines to show in the diff (0 = old-style diff, 1 = unified diff with 0 context lines, 2+ = unified diff with 'diff_choice - 1' context lines).
        changed_color:  Color to use for unchanged characters in the changed lines in the diff (default ANSI_CYAN).
        deleted_color:  Color to use for the deleted characters in orig lines (default ANSI_YELLOW).
    """
    import difflib
    fallback_logging_config(rawlog=True)
    if not changed_path:
        changed_path = orig_path
    logging.debug(f"At the top of the function {sys._getframe(1).f_code.co_name}(), {diff_choice=}")
    orig_lines    =    orig_text.splitlines(keepends=True)
    changed_lines = changed_text.splitlines(keepends=True)
    the_digits = max(len(str(len(orig_lines))), len(str(len(changed_lines))))
    last_removed = None  # there is no last removed line initially
    # shared buffer for the current hunk's deletes/inserts
    hunk_entries: list[tuple[str, str, int, int]] = []
    # each entry is (tag, text, orig_lineno, new_lineno)
    # orig_lineno or new_lineno will be None for pure inserts/deletes.

    def process_hunk() -> None:
        """Pair up deletes and inserts in the current hunk and print them with highlights."""
        nonlocal hunk_entries
        if not hunk_entries:
            return
        deletes = [e for e in hunk_entries if e[0] == "-"]
        inserts = [e for e in hunk_entries if e[0] == "+"]
        pair_count = min(len(deletes), len(inserts))
        di = ii = 0
        for tag, text, dln, nln in hunk_entries:
            if tag == "-":
                if di < pair_count:
                    old_vis = _vis_trailing_ws(text)
                    new_vis = _vis_trailing_ws(inserts[di][1])
                    old_hl, new_hl = highlight_changes(
                        old_vis, new_vis,
                        unchanged_color=changed_color,
                        added_color=added_color,
                        deleted_color=deleted_color
                    )
                    logging.info(f"< {dln:>{the_digits}}: {old_hl}{ANSI_RESET}")
                    logging.info(f"{changed_color}> {inserts[di][3]:>{the_digits}}:{ANSI_RESET} {new_hl}{ANSI_RESET}")
                else:
                    logging.info(f"< {dln:>{the_digits}}: "
                                 f"{deleted_color}{_vis_trailing_ws(text)}{ANSI_RESET}")
                di += 1
            elif tag == "+":
                if ii >= pair_count:
                    logging.info(f"{changed_color}> {nln:>{the_digits}}:{ANSI_RESET} "
                                 f"{ANSI_RED}{_vis_trailing_ws(text)}{ANSI_RESET}")
                ii += 1
        hunk_entries.clear()

    def flush_removed(orig_lineno: int) -> None:
        """Flush the last removed line if it exists."""
        nonlocal last_removed
        if last_removed is not None:
            highlighted_old = f"{deleted_color}{last_removed}{ANSI_RESET}"
            logging.info(f"< {orig_lineno:>{the_digits}}: {highlighted_old}")
            last_removed = None

    if diff_choice == 0:  # old style diff (difflib.Differ)
        logging.debug(f"Using old-style diff for {orig_path} with {len(orig_lines)} original and {len(changed_lines)} fixed lines.")
        orig_lineno = 1
        new_lineno  = 1
        for line in difflib.Differ().compare(orig_lines, changed_lines):
            tag, body = line[:2], line[2:].rstrip("\n")
            if tag == "  ":    # context line
                # end of any previous mini‑hunk
                process_hunk()
                flush_removed(orig_lineno)
                # show context lines if you like, e.g.:
                # logging.info(f"  {orig_lineno:>{the_digits}}: {_vis_trailing_ws(body)}")
                orig_lineno += 1
                new_lineno  += 1
            elif tag == "- ":  # original line
                # buffer a delete
                hunk_entries.append(("-", body, orig_lineno, None))
                orig_lineno += 1
            elif tag == "+ ":  # fixed line
                # buffer an insert
                hunk_entries.append(("+", body, None, new_lineno))
                new_lineno += 1
            # skip '? ' lines entirely
        # flush any trailing buffered pairs/inserts
        process_hunk()
        flush_removed(orig_lineno)
    elif diff_choice >= 1:  # unified or context diff
        logging.debug(f"Using unified diff for {orig_path} with {len(orig_lines)} original and {len(changed_lines)} fixed lines.")
        ctx  = max(diff_choice - 1, 0)
        diff = difflib.unified_diff(
            orig_lines, changed_lines,
            fromfile=orig_path, tofile=changed_path,
            n=ctx, lineterm=""
        )
        header_re = re.compile(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")
        orig_lineno = new_lineno = None
        for line in diff:
            if line.startswith("@@"):  # hunk header?
                # flush any leftover from the prior hunk
                process_hunk()
                m = header_re.match(line)
                orig_lineno = int(m.group(1))
                new_lineno  = int(m.group(2))
                continue
            if line.startswith(("---", "+++")):  # skip file header lines
                continue
            tag, body = line[0], line[1:].rstrip("\n")
            if tag == " ":  # context line: flush and emit
                process_hunk()
                flush_removed(orig_lineno)
                logging.info(f"  {orig_lineno:>{the_digits}}: {_vis_trailing_ws(body)}")
                orig_lineno += 1
                new_lineno  += 1
            elif tag == "-":  # buffer a delete
                hunk_entries.append(("-", body, orig_lineno, None))
                orig_lineno += 1
            elif tag == "+":  # buffer an insert
                hunk_entries.append(("+", body, None, new_lineno))
                new_lineno += 1
        # final flush
        process_hunk()
        flush_removed(orig_lineno)
    else:
        logging.error(f"Unsupported diff_choice = {diff_choice}. Must be a non-negative integer.")


def diff_and_confirm(orig_text: str, changed_text: str, path: str, label: str, skip_compile: bool = False,
                     diff_choice: int = 1, changed_color: str = ANSI_CYAN,
                     deleted_color: str = ANSI_RED, added_color: str = ANSI_YELLOW,
                     the_fix: str = "", description: str = "") -> bool:
    """
    Show a unified diff of orig_text → changed_text with a number of context lines
    (determined by 'diff_choice') around each hunk, log using 'label' and 'description', then prompt.
    If the user confirms, overwrite 'path' with changed_text and return True.
    If the user chooses to quit, log a message and return False.

    Parameters:
        orig_text:     Original text to compare against.
        changed_text:  Proposed changes to the original text.
        path:          Path to the file being modified.
        label:         A short label for the issue being fixed.
        skip_compile:  If True, do not try to compile the changed text before writing.
        diff_choice:   How many context lines to show in the diff (0 = old-style diff, 1 = unified diff with 0 context lines, 2+ = unified diff with 'diff_choice - 1' context lines).
        changed_color: Color to use for unchanged characters in the changed lines in the diff (default ANSI_CYAN).
        deleted_color: Color to use for the deleted characters in orig lines (default ANSI_YELLOW).
        added_color:   Color to use for the added characters in changed lines (default ANSI_GREEN).
        the_fix:       A string describing the fix being applied (e.g. "autopep8", "manual edit").
        description:   A longer description of the issue being fixed.

    Returns False if the user chose to quit; True otherwise.
    """
    from pathlib import Path
    fallback_logging_config()
    logging.debug(f"At the top of the function {sys._getframe(1).f_code.co_name}(), {diff_choice=}")
    my_diff(orig_text, changed_text, path, diff_choice=diff_choice,
            changed_color=changed_color, deleted_color=deleted_color, added_color=added_color)
    logging.info(f"End of proposed {ANSI_RED}{label}{ANSI_RESET} changes to {path} using {the_fix}.")
    logging.info(f"{ANSI_RED}{label}{ANSI_RESET}: {ANSI_YELLOW}{description}{ANSI_RESET}")
    ans = input("Apply these changes? [y/N/q] ").strip().lower()
    if ans in ("y", "yes"):
        if not skip_compile and not compile_code(changed_text):
            logging.error(f"{ANSI_RED}Failed to compile the changed text. Aborting write.{ANSI_RESET}")
            return True  # don't write if it won't compile
        Path(path).write_text(changed_text, encoding=DEFAULT_ENCODING)
        logging.info(f"{ANSI_GREEN}Applied {the_fix} to {path}{ANSI_RESET}")
    elif ans in ("q", "quit", "exit"):
        logging.info(f"{ANSI_YELLOW}Exiting without further changes.{ANSI_RESET}")
        return False
    else:
        logging.info(f"{ANSI_YELLOW}Skipped writing changes.{ANSI_RESET}")
    return True


def ask_and_autopep8(path: str, code: str, description: str, diff_choice: int = 1,
                     changed_color: str = ANSI_CYAN, deleted_color: str = ANSI_RED,
                     added_color: str = ANSI_YELLOW) -> bool:
    """
    Prompt the user about fixing ALL occurrences of 'code' in 'path',
    and if yes, apply autopep8.fix_file with --select=code.
    The fix will be applied without saving, and the user will be shown a diff
    of the changes before saving to the file.

    Parameters:
        path:          The path to the file to modify.
        code:          The specific PEP 8 violation code to fix.
        description:   A description of the issue being fixed.
        diff_choice:   How many context lines to show in the diff (0 = old-style diff, 1 = unified diff with 0 context lines, 2+ = unified diff with 'diff_choice - 1' context lines).
        changed_color: Color to use for unchanged characters in the changed lines in the diff (default ANSI_CYAN).
        deleted_color: Color to use for the deleted characters in orig lines (default ANSI_YELLOW).
        added_color:   Color to use for the added characters in changed lines (default ANSI_GREEN).

    Returns true if the user wants to continue, False if they want to quit.
    """
    import autopep8
    fallback_logging_config()
    logging.debug(f"At the top of the function {sys._getframe(1).f_code.co_name}(), {diff_choice=}")
    # The number of blank lines expected in various contexts.
    blank_line_overrides = {
        'E301': 1,  # expected 1 blank line, found 0
        'E302': 2,  # expected 2 blank lines, found 1
        'E303': 5,  # too many blank lines (give a lot of context to see what is around the blank lines)
        'E305': 2,  # expected 2 blank lines after class/method
    }
    orig_text = my_fopen(path)
    changed_text = orig_text
    for level in (0, 1, 2):  # try with 0, 1, then 2 "-a" flags
        flags = ['-a'] * level
        the_fix = f"autopep8 {' '.join(flags)} --select={code}"
        args = [f"--select={code}", "--in-place"] + flags + [path]
        opts      = autopep8.parse_args(args)
        candidate = autopep8.fix_code(orig_text, options=opts)
        if candidate != orig_text:
            changed_text = candidate
            break
    if changed_text == orig_text:
        logging.info(f"No changes for {code} in {path} using {the_fix}.")
        return True
    if not isinstance(diff_choice, int) or diff_choice < 0:
        logging.error(f"Invalid diff_choice={diff_choice}. Must be a non-negative integer.")
        return False
    # If this is a blank‑line code, force unified with the number of context lines specified in blank_line_overrides.
    if code in blank_line_overrides:
        # +1 so that unified_diff(n=override‑1) gives you exactly override context
        effective = blank_line_overrides[code] + 1
    else:
        effective = diff_choice
    return diff_and_confirm(orig_text, changed_text, path, label=code, diff_choice=effective,
                            changed_color=changed_color, deleted_color=deleted_color, added_color=added_color,
                            the_fix=the_fix, description=description)


def ask_and_replace(path: str, old: str, new: str, label: str, diff_choice: int = 1, description: str = "",
                    changed_color: str = ANSI_CYAN, deleted_color: str = ANSI_RED, added_color: str = ANSI_YELLOW) -> bool:
    """Read 'path', do orig.replace(old, new), then show a diff and ask to confirm."""
    fallback_logging_config()
    orig_text = my_fopen(path)
    changed_text = orig_text.replace(old, new)
    if changed_text == orig_text:
        logging.info(f"No occurrences of {label} in {path}.")
        return True
    the_fix = f"replace '{old}' with '{new}'"
    return diff_and_confirm(orig_text, changed_text, path, label=label, diff_choice=diff_choice,
                            changed_color=changed_color, deleted_color=deleted_color, added_color=added_color,
                            the_fix=the_fix, description=description)


def interactive_flake8(path: str, diff_choice: int = 1, ignore_codes: list[str] = [], max_line_length: int = 100,
                       changed_color: str = ANSI_CYAN, deleted_color: str = ANSI_RED, added_color: str = ANSI_YELLOW) -> None:
    """
    1) Run the flake8 API for summary counts.
    2) Shell out to flake8 CLI once to harvest one description per code.
    3) For each code, ask the user; on "yes", call autopep8 to fix only that code.

    Parameters:
        path:            Path to the Python file to check.
        diff_choice:     How many context lines to show in the diff (0 = old-style diff, 1 = unified diff with 0 context lines, 2+ = unified diff with 'diff_choice - 1' context lines).
        ignore_codes:    List of Flake8 codes to ignore (default: empty list).
        max_line_length: Maximum line length for E501 (default: 100).
        changed_color:   Color for unchanged characters in changed lines (default: ANSI_CYAN).
        deleted_color:   Color for deleted characters in original lines (default: ANSI_RED).
        added_color:     Color for added characters in changed lines (default: ANSI_YELLOW).
    """
    fallback_logging_config()
    logging.debug(f"At the top of the function {sys._getframe(1).f_code.co_name}(), {diff_choice=}")
    if not run_flake8(path, ignore_codes=ignore_codes, max_line_length=max_line_length):
        logging.info("No flake8 errors—nothing to do.")
        return
    codes = _gather_flake8_issues(path, ignore_codes=ignore_codes, max_line_length=max_line_length)
    fixable_codes = get_autopep8_fixable_codes()
    logging.debug(f"Autopep8 can fix these codes: {fixable_codes}")
    for code, desc in codes.items():
        if code not in fixable_codes:
            logging.debug(f"Skipping {code}: no autopep8 fixer")
            continue
        logging.info(f"\n→ {ANSI_RED}{code}{ANSI_RESET}: {ANSI_YELLOW}{desc}{ANSI_RESET}")
        if not ask_and_autopep8(path, code, desc, diff_choice=diff_choice,
                                changed_color=changed_color, deleted_color=deleted_color, added_color=added_color):
            break
    logging.info(f"{ANSI_GREEN}Done. Re-running flake8 to confirm fixes...{ANSI_RESET}")
    run_flake8(path, ignore_codes=ignore_codes, max_line_length=max_line_length)


MYDIFF_SCRIPT = '''import argparse

import univ_defs as ud


def main() -> None:
    """Main entry point for the script."""
    ud.configure_logging("mydiff", log_level="INFO", rawlog=True)
    parser = argparse.ArgumentParser(description="Diff two files using ud.my_diff().")
    parser.add_argument("orig_path",     type=str, help="Path to original file.")
    parser.add_argument("changed_path",  type=str, help="Path to changed file.")
    parser.add_argument("--diff_choice", type=int, default=1,
                        help="0 = old-style diff, 1 = unified diff with 0 context lines, "
                             "2+ = unified diff with 'diff_choice - 1' context lines")
    parser.add_argument("--changed_color", type=str, default=ud.ANSI_CYAN,
                        help="Color for unchanged characters in changed lines (default: ANSI_CYAN)")
    parser.add_argument("--deleted_color", type=str, default=ud.ANSI_RED,
                        help="Color for deleted characters in original lines (default: ANSI_RED)")
    parser.add_argument("--added_color",   type=str, default=ud.ANSI_GREEN,
                        help="Color for added characters in changed lines (default: ANSI_GREEN)")
    args = parser.parse_args()

    orig_text    = ud.my_fopen(args.orig_path)
    changed_text = ud.my_fopen(args.changed_path)
    if orig_text is False or changed_text is False:
        return
    ud.my_diff(orig_text, changed_text, args.orig_path,
               changed_path=args.changed_path, diff_choice=args.diff_choice,
               changed_color=args.changed_color, deleted_color=args.deleted_color,
               added_color=args.added_color)


if __name__ == "__main__":
    main()
'''

MYAUDIT_SCRIPT = '''import argparse

import univ_defs as ud


def main() -> None:
    """Main entry point for the script."""
    ud.configure_logging("format_checker", log_level="INFO")
    parser = argparse.ArgumentParser(description="Check Python formatting in a file.")
    parser.add_argument("filepath", type=str, help="Path to the Python file to check")
    parser.add_argument("--diff_choice", type=int, default=1,
                        help="0 = old-style diff, 1 = unified diff with 0 context lines, "
                             "2+ = unified diff with 'diff_choice - 1' context lines")
    parser.add_argument("--changed_color", type=str, default=ud.ANSI_CYAN,
                        help="Color for unchanged characters in changed lines (default: ANSI_CYAN)")
    parser.add_argument("--deleted_color", type=str, default=ud.ANSI_RED,
                        help="Color for deleted characters in original lines (default: ANSI_RED)")
    parser.add_argument("--added_color", type=str, default=ud.ANSI_GREEN,
                        help="Color for added characters in changed lines (default: ANSI_GREEN)")
    args = parser.parse_args()

    if not ud.check_python_formatting(args.filepath, diff_choice=args.diff_choice):
        return

    ud.interactive_flake8(args.filepath, diff_choice=args.diff_choice, ignore_codes=ud.IGNORED_CODES, max_line_length=1000,
                          changed_color=args.changed_color, deleted_color=args.deleted_color, added_color=args.added_color)

if __name__ == "__main__":
    main()
'''


def verify_script(thepath: str, thescript: str) -> None:
    """
    Ensure that `thepath` exists and contains exactly `thescript`.
    - If `thepath` does not exist or is not a file, it will be created and populated.
    - If it exists but its contents differ, it will be overwritten.
    - Otherwise, nothing happens.
    """
    # Check if it exists and is a file
    if not os.path.isfile(thepath):
        if os.path.isdir(thepath):
            logging.error(f"Expected a file at {thepath}, but it is a directory.")
            return
        with open(thepath, 'w', encoding=DEFAULT_ENCODING) as f:
            logging.info(f"Creating {thepath} with the audit script.")
            f.write(thescript)
        return

    # It is a file: read and compare
    with open(thepath, 'r', encoding=DEFAULT_ENCODING) as f:
        existing = f.read()

    # Overwrite if different
    if existing != thescript:
        logging.info(f"Contents of {thepath} differ from the audit script in {__file__} as follows:")
        my_diff(existing, thescript, thepath, diff_choice=1)
        logging.info(f"Overwriting {thepath} with the audit script.")
        with open(thepath, 'w', encoding=DEFAULT_ENCODING) as f:
            f.write(thescript)
    # else: contents match exactly, nothing to do


def decode_utf8(raw_bytes: bytes, path: str = "input string") -> str | None:
    """
    If the file at `path` is valid UTF-8 without lone C1 controls,
    return the decoded string. Otherwise, return None.
    """
    fallback_logging_config()
    try:
        text = raw_bytes.decode('utf-8', errors='strict')
    except UnicodeDecodeError:
        logging.debug(f"{path} failed to decode as UTF‑8.")
        return None
    if any(0x0080 <= ord(ch) <= 0x009F for ch in text):
        logging.debug(f"{path} contains lone C1 controls, not valid UTF-8.")
        return None
    logging.debug(f"{path} decoded as valid UTF‑8.")
    return text


def decode_cp1252(raw_bytes: bytes, path: str = "input string") -> str | None:
    """
    Attempt to decode CP1252 bytes and return as a string.
    If it fails, return None.
    """
    fallback_logging_config()
    try:
        text = raw_bytes.decode('cp1252', errors='strict')
        logging.debug(f"{path} decoded as valid CP1252.")
        return text
    except UnicodeDecodeError:
        logging.debug(f"{path} failed to decode as CP1252.", exc_info=True)
        return None


def contains_mojibake(text: str) -> bool:
    """Use ftfy.badness.is_bad() to detect any likely mojibake in the text."""
    import ftfy
    fallback_logging_config()
    try:
        mojibake_present = ftfy.badness.is_bad(text)
    except Exception: # Catch any unexpected errors from ftfy without crashing
        logging.debug(f"Failed to check for mojibake.", exc_info=True)
        mojibake_present = False
    logging.debug(f"Mojibake present: {mojibake_present}")
    # I HAVEN'T TRIED THIS NEXT LINE, BUT IT MIGHT CAUSE FEWER FALSE POSITIVES:
    # return ftfy.badness(text) > 1
    return mojibake_present


def fix_text(current_text: str, path: str, raw_bytes: bytes) -> str | None:
    """
    Fix mojibake in a string using ftfy.fix_encoding().
    """
    import ftfy
    fallback_logging_config()
    logging.debug(f"Checking {path} for mojibake.")
    if not contains_mojibake(current_text):
        return None
    try:
        fixed = ftfy.fix_encoding(current_text)
    except Exception:  # Catch any unexpected errors from ftfy without crashing
        logging.error(f"Failed to fix mojibake in {path}.", exc_info=True)
        return None
    # If logging level is set to DEBUG, show my diff of original vs fixed:
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        try:
            # Mangle the original string to simulate browser encoding issues:
            mangled_original = raw_bytes.decode('cp1252', errors='replace')
            my_diff(mangled_original, fixed, path)
        except Exception:  # Catch any unexpected errors from decoding but don't crash.
            logging.debug(f"Could not simulate browser mangling in {path}.", exc_info=True)
    return fixed


def ensure_utf8_meta(html: str) -> str:
    """
    Ensure the HTML text has a <meta charset="utf-8"> tag.
    If one already exists—either as a charset attribute or
    as an http-equiv Content-Type declaration—normalize it to
    <meta charset="utf-8">. Otherwise, insert that tag right
    after the opening <head> tag.
    """
    # 1) Normalize any <meta ... charset=...> to <meta charset="utf-8">
    #    This covers both <meta charset="XYZ"> and
    #    <meta http-equiv="Content-Type" content="text/html; charset=XYZ">
    def _replace_charset_attr(match: re.Match) -> str:
        """
        Replace a <meta> tag with a charset attribute
        with a normalized <meta charset="utf-8"> tag.
        """
        # Always produce exactly: <meta charset="utf-8">
        return '<meta charset="utf-8">'
    
    # Pattern A: <meta ... charset=XYZ ...>
    pattern_a = r'<meta\b[^>]*\bcharset=["\']?[^"\'>\s]+["\']?[^>]*>'
    # Pattern B: <meta ... http-equiv=["\']Content-Type["\'] ... content="...; charset=XYZ"...>
    pattern_b = (r'<meta\b[^>]*\bhttp-equiv=["\']?Content-Type["\']?[^>]*'
                 r'\bcontent=["\'][^"\'>]*;\s*charset=[^"\'>]+["\'][^>]*>')

    if re.search(pattern_a, html, flags=re.IGNORECASE) or \
       re.search(pattern_b, html, flags=re.IGNORECASE):
        # First collapse any Pattern B occurrences
        html = re.sub(pattern_b, _replace_charset_attr, html, flags=re.IGNORECASE)
        # Then collapse any remaining Pattern A
        html = re.sub(pattern_a, _replace_charset_attr, html, flags=re.IGNORECASE)
        return html

    # 2) If no existing meta‐charset, insert one just after <head>
    return re.sub(r'(<head\b[^>]*>)',
                  r'\1\n    <meta charset="utf-8">',
                  html, count=1, flags=re.IGNORECASE)


def my_atomic_write(filepath: str | Path | os.PathLike, data: str | bytes | bytearray,
                    write_mode: Literal['w', 'a'], encoding: str = DEFAULT_ENCODING,
                    lock_timeout: float = None,  # seconds to wait for lock (None = forever)
                   ) -> None:
    """
    Atomically write `data` to `filepath` with an advisory lock.
    
    - If write_mode='a' and file exists, data is appended.
    - If write_mode='a' and file does *not* exist, file is created.
    - A `.lock` file beside `filepath` prevents concurrent writers.
    """
    from atomicwrites import atomic_write
    from filelock import FileLock, Timeout
    path = Path(filepath)
    # ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)
    # choose text or binary mode
    is_bytes = isinstance(data, (bytes, bytearray))
    mode     = write_mode + ('b' if is_bytes else '')
    text_enc = None if is_bytes else encoding
    lock_path = str(path) + '.lock'
    lock = FileLock(lock_path, timeout=lock_timeout)
    try:
        with lock:
            # atomicwrites will write to a temp file in the same dir then os.replace()
            # overwrite=(write_mode=='w') means "w" replaces, "a" appends
            with atomic_write(path, mode=mode, overwrite=(write_mode == 'w'),
                              encoding=text_enc, preserve_mode=True) as f:
                f.write(data)
    except Timeout:
        raise RuntimeError(f"Could not acquire lock on {lock_path!r} within {lock_timeout} seconds")


def fix_mojibake(filepath: str, make_backup: bool = True,
                 dry_run: bool = False) -> None:
    """
    Fix mojibake in a text file, recoding from CP1252 to UTF-8 if necessary.
    If the file is already valid UTF-8, it will only fix mojibake.
    """
    import datetime as dt
    fallback_logging_config()
    if not os.path.isfile(filepath):
        logging.error(f"{filepath} is not a file")
        return

    try:
        with open(filepath, 'rb') as f:
            raw_bytes = f.read()
    except Exception:  # Catch any unexpected errors from reading the file without crashing.
        logging.error(f"Failed to read {filepath}.", exc_info=True)
        return

    original_text =      decode_utf8(raw_bytes, filepath) \
                    or decode_cp1252(raw_bytes, filepath)
    if original_text is None:
        return

    # Start with the original text but keep it in memory unmodified.
    current_text = original_text

    # Either way, check for mojibake and fix it if necessary
    maybe_fixed = fix_text(current_text, filepath, raw_bytes)
    if maybe_fixed is not None:
        current_text = maybe_fixed
        logging.info(f"✔ Fixed mojibake: {filepath}")

    # If the text is from an HTML file, ensure it has a UTF-8 meta tag
    if filepath.lower().endswith(('.html','.htm')):
        current_text = ensure_utf8_meta(current_text)

    # If we have fixed the text, write it back
    if current_text != original_text:
        if dry_run:
            logging.info(f"Dry run: would write changes to {filepath}")
        else:
            if make_backup:
                current_datetime = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
                backup_path = f"{filepath}_{current_datetime}.bak"
                try:
                    os.rename(filepath, backup_path)
                    logging.info(f"Backup created: {backup_path}")
                except OSError:
                    logging.exception(f"Failed to create backup for {filepath}.")
                    return
            my_atomic_write(filepath, current_text, 'w', encoding='utf-8')
            logging.info(f"✔ Successfully fixed mojibake in {filepath}")


def treeview_new_files(directory: str, last_file_path: str, last_mtime: float,
                       prefix: str = '', is_last: bool = True, level: int = 0,
                       state: dict = None) -> bool:
    """Recursively scan the directory, print the contents of files newer than last_file_path (and store its modification date in last_mtime). Return True if any relevant files are found."""
    fallback_logging_config(rawlog=True)
    if state is None:
        state = {'excluded_dirs'   : {'__pycache__'},
                 'already_printed' : set(),
                 'my_filepath'     : os.path.abspath(__file__)}
    already_printed = state['already_printed']
    excluded_dirs   = state['excluded_dirs']
    my_filepath     = state['my_filepath']

    already_printed.add(directory)
    has_relevant_files = False  # Flag to indicate if current directory has relevant files

    try:
        entries = sorted(os.scandir(directory), key=lambda e: e.name.lower())
    except PermissionError:
        logging.error(f"{prefix}└── [Permission Denied]")
        return False

    # Filter out entries that should be skipped at the directory level
    entries = [
        entry for entry in entries
        if not (
            (entry.is_file() and (
                entry.path == last_file_path or
                entry.path == my_filepath    or
                os.path.basename(entry.path).startswith('.')
            )) or
            (entry.is_dir() and os.path.basename(entry.path) in excluded_dirs) or
            (entry.is_dir() and entry.path in already_printed)
        )
    ]

    # Collect relevant entries
    relevant_entries = []
    subdirectories = []

    for entry in entries:
        if entry.is_file():
            file_mtime = entry.stat().st_mtime
            if file_mtime > last_mtime:
                relevant_entries.append(entry)
                has_relevant_files = True
        elif entry.is_dir():
            sub_has_relevant = treeview_new_files(
                entry.path, last_file_path, last_mtime,
                prefix + ('    ' if is_last else '│   '), False, level + 1
            )
            if sub_has_relevant:
                subdirectories.append(entry)
                has_relevant_files = True

    if has_relevant_files:
        if level > 0:
            # Print the directory name only if it's not the root directory
            connector = '└── ' if is_last else '├── '
            logging.info(f"{prefix}{connector}{os.path.basename(directory)}/")

            # Update the prefix for child entries
            child_prefix = prefix + ('    ' if is_last else '│   ')
        else:
            # For root level, do not print the directory name
            child_prefix = prefix

        # Print relevant files
        for i, file_entry in enumerate(relevant_entries):
            # Determine if this is the last file to adjust connector
            is_file_last = (i == len(relevant_entries) - 1) and not subdirectories
            file_connector = '└── ' if is_file_last else '├── '
            logging.info(f"{child_prefix}{file_connector}{os.path.basename(file_entry.path)} contents:")
            try:
                with open(file_entry.path, 'r', encoding=DEFAULT_ENCODING) as f:
                    contents = f.read()
                    # Indent file contents for better readability
                    indented_contents = '\n'.join([f"{child_prefix}    {line}" for line in contents.splitlines()])
                    logging.info(indented_contents)
            except Exception:  # Catch any unexpected errors from reading the file without crashing.
                logging.exception(f"{child_prefix}    Error reading '{file_entry.path}'.", exc_info=True)
            logging.info("")  # Add an empty line for separation

        # Print subdirectories
        for i, subdir in enumerate(subdirectories):
            is_sub_last = (i == len(subdirectories) - 1)
            # Only scan the subdirectory if it isn't excluded
            if os.path.basename(subdir.path) not in excluded_dirs and subdir.path not in already_printed:
                treeview_new_files(subdir.path, last_file_path, last_mtime, child_prefix, is_sub_last, level + 1)

    return has_relevant_files


def open_terminal_and_run_command(the_command: str,
                                  close_after: bool = False) -> None:
    """Open a terminal window and run the_command while sourcing the .bashrc to access aliases. If close_after is True, the terminal will close after the command finishes."""
    import subprocess
    fallback_logging_config()
    logging.info(f"Opening terminal and running '{the_command}'...")
    # Adjust the terminal emulator if not using GNOME Terminal
    if close_after:
        terminal_command = ['gnome-terminal',
                            '--', 'bash', '-ic',
                            f'{the_command}; exit']
    else:
        terminal_command = ['gnome-terminal',
                            '--', 'bash', '-ic',
                            f'{the_command}; exec bash']
    
    subprocess.Popen(terminal_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def is_process_running(process_name: str) -> bool:
    """Check if a process with the given name is running."""
    import subprocess
    try:
        # Use pgrep to search for the process
        subprocess.run(['pgrep', '-x', process_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except subprocess.CalledProcessError:
        return False


def start_only_one_instance(process_name: str) -> None:
    """Start a process, but only if it's not already running."""
    import subprocess
    import time
    fallback_logging_config()
    if not is_process_running(process_name):
        logging.info(f"Starting {process_name}...")
        subprocess.Popen([process_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Wait briefly to ensure the command is processed
        time.sleep(1)
    else:
        logging.info(f"{process_name} is already running.")


def open_filemanager_with_dirs(directories: list) -> None:
    """
    Open the file manager with the specified directories.
    Note: Most file managers don't support multiple tabs via command line, so open separate windows.
    """
    import subprocess
    import time
    fallback_logging_config()
    logging.info("Opening file manager with specified directories...")
    for directory in directories:
        if os.path.isdir(directory):
            subprocess.Popen(['nemo', directory], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # Optional: Wait briefly between opening directories
            time.sleep(0.5)
        else:
            logging.warning(f"Directory does not exist: {directory}")


def open_playlist_in_VLC(playlist: str, no_start:  bool = False) -> None:
    """Open a playlist in VLC. If no_start is True, don't start playback in VLC."""
    import subprocess
    if playlist is None:
        raise ValueError("The directory path cannot be None.")
    elif not isinstance(playlist, str):
        raise TypeError(f"Expected 'playlist' to be a string, got {type(playlist).__name__!r}")
    elif not os.path.isfile(playlist):
        raise ValueError(f"The specified path '{playlist}' is not a valid file.")
    if no_start: command_list = ["vlc", "--no-playlist-autostart", playlist]
    else:        command_list = ["vlc",                            playlist]
    subprocess.Popen(command_list, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def open_dir_in_VLC(the_dir: str, sort_choice: str = "sort_by_name",
                    recursive: bool = False, no_start:  bool = False) -> None:
    """Create a playlist of the files in the specified directory, then play that playlist in VLC. By default, don't search the directory recursively and sort the files by name. Optional arguments allow recursive loading or sorting by modification time. If no_start is True, don't start playback in VLC."""
    import subprocess
    if the_dir is None:
        raise ValueError("The directory path cannot be None.")
    elif not isinstance(the_dir, str):
        raise TypeError(f"Expected 'the_dir' to be a string, got {type(the_dir).__name__!r}")
    elif not os.path.isdir(the_dir):
        raise ValueError(f"The specified path '{the_dir}' is not a valid directory.")
    # start_flag = "--start-paused" if no_start else False # The "--start-paused" flag forces you to press play in VLC EACH TIME YOU GO TO A NEW PLAYLIST ENTRY!
    start_flag = "--no-playlist-autostart" if no_start else False
    # List to store files with their modification times
    files_with_times = []
    if recursive:
        # Recursively iterate over the files in the directory
        for root, dirs, files in os.walk(the_dir):
            for filename in files:
                file_path = os.path.join(root, filename)
                if os.path.isfile(file_path) and not filename.endswith('.m3u'):
                    mod_time = os.path.getmtime(file_path)
                    files_with_times.append((mod_time, file_path))
    else:
        for item in os.listdir(the_dir):
            item_path = os.path.join(the_dir, item)
            if os.path.isfile(item_path) and not item.endswith('.m3u'):
                mod_time = os.path.getmtime(item_path)
                files_with_times.append((mod_time, item_path))
            elif os.path.isdir(item_path):
                mod_time = os.path.getmtime(item_path)
                files_with_times.append((mod_time, item_path))

    if sort_choice == "sort_by_name":
        # Sort files by name
        files_with_times.sort(key=lambda x: x[1])
    elif sort_choice == "sort_by_time":
        # Sort files by modification time (earliest first)
        files_with_times.sort(key=lambda x: x[0])
    # Create the .m3u playlist content
    playlist_content = "#EXTM3U\n"
    for _, file_path in files_with_times:
        base_name = os.path.basename(file_path)
        playlist_content += f"#EXTINF:-1,{base_name.replace(',', '').replace('-', '')}\n{file_path}\n"
    # Get the base directory name for the playlist filename
    base_dir = os.path.basename(os.path.normpath(the_dir))
    # Write the playlist to disk in the parent directory
    playlist_path = os.path.join(the_dir, f"{filename_format(base_dir)}_playlist.m3u")
    with open(playlist_path, 'w') as playlist_file:
        playlist_file.write(playlist_content)
    # Open the playlist in VLC
    if start_flag: command_list = ["vlc", start_flag, playlist_path]
    else:          command_list = ["vlc",             playlist_path]
    subprocess.Popen(command_list, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def remove_prefix_from_filename(filepath: str, prefix: str) -> bool:
    """If the given filepath's base filename starts with the given prefix, remove the prefix, move the file (but only if that doesn't cause errors) and return True. Otherwise, return False."""
    file = os.path.basename(filepath)
    if file.startswith(prefix):
        new_file = file.replace(prefix, "", 1)  # Replace only the first occurrence
        # If the first character is now in " _-", remove it:
        while new_file[0] in " _-":
            new_file = new_file[1:]
        new_filepath = os.path.join(os.path.dirname(filepath), new_file)
        if not os.path.exists(new_filepath):
            try:
                os.rename(filepath, new_filepath)
                print(f"Renamed '{filepath}' to '{new_filepath}'.")
                return True
            except OSError as e:
                raise OSError(f"Failed to rename '{filepath}' to '{new_filepath}': {e}") from e
        else:
            print(f"Cannot rename '{filepath}' to '{new_filepath}': New path already exists.")
            return False
    else:
        return False


def remove_prefix_from_html_title(filepath: str, prefix: str) -> bool:
    """If the given filepath is an HTML file and its title starts with the given prefix, remove the prefix from the title and save the file, then return True. Otherwise, return False."""
    if not filepath.endswith('.html') and not filepath.endswith('.htm'):
        print(f"File '{filepath}' is not an HTML or HTM file.")
        breakpoint()
        return False
    html = my_fopen(filepath)
    title_start = html.find('<title>') + len('<title>')
    title_end = html.find('</title>', title_start)
    if title_start == -1 or title_end == -1:
        print(f"Could not find the title in the HTML file '{filepath}'.")
        return False
    title = html[title_start:title_end]
    if title.startswith(prefix):
        new_title = title.replace(prefix, "", 1)  # Replace only the first occurrence
        new_html = html[:title_start] + new_title + html[title_end:]
        with open(filepath, 'w', encoding=DEFAULT_ENCODING) as file:
            file.write(new_html)
        print(f"Removed prefix '{prefix}' from the title in '{filepath}'.")
        return True
    else:
        return False


def combine_html_files(file_paths: list[str],
                       output_file_path: str) -> None:
    """
    Combine multiple HTML files into a single HTML file.
    The first file's <head> is preserved, and all <body> contents are concatenated.

    Parameters:
    - file_paths: List of (presorted) file paths to the HTML files to combine.
    - output_file_path: Path to save the combined HTML file.
    """
    from bs4 import BeautifulSoup
    fallback_logging_config()
    combined_body = ''
    head_content = ''
    first_file_processed = False
    for file_path in file_paths:
        file = my_fopen(file_path)
        try:
            soup = BeautifulSoup(file, 'html.parser')
            # Extract <head> from the first Chapter1.html
            if not first_file_processed:
                head_content = str(soup.head)
                first_file_processed = True            
            # Extract <body> content
            body_content = soup.body
            combined_body += str(body_content)
        except Exception:  # Catch any unexpected errors from BeautifulSoup without crashing.
            logging.exception(f"File {file_path} encountered an error.")
    # Create the new HTML structure
    combined_html = f"<!DOCTYPE html>\n<html>\n{head_content}\n<body>\n{combined_body}\n</body>\n</html>"
    # Save to the output file path
    try:
        with open(output_file_path, 'w', encoding=DEFAULT_ENCODING) as output_file:
            output_file.write(combined_html)
    except Exception:  # Catch any unexpected errors from writing the file without crashing.
        logging.exception(f"Error saving combined HTML to {output_file_path}.")
    logging.info(f"Saved combined HTML to '{output_file_path}'.")


def check_list_for_duplicates(the_list: list) -> bool:
    """Check a list for duplicate elements and return True if duplicates are found."""
    duplicates = [ext for ext in set(the_list) if the_list.count(ext) > 1]
    print("Duplicates:", duplicates)
    return len(duplicates) > 0


# A comprehensive list of encodings to try when reading files, with most likely encodings first.
text_encodings = [
    'utf-8',        'latin-1',      'ascii',          'iso-8859-1',      'big5',         'utf-8-sig',
    'utf-16',       'utf-16-be',    'utf-16-le',      'utf-32',          'utf-32-be',    'utf-32-le',
    'cp1252',       'cp1251',       'cp1250',         'cp1253',          'cp1254',       'cp1255',
    'cp1256',       'cp1257',       'cp1258',         'iso-8859-2',      'iso-8859-3',   'iso-8859-4',
    'iso-8859-5',   'iso-8859-6',   'iso-8859-7',     'iso-8859-8',      'iso-8859-9',   'iso-8859-10',
    'iso-8859-11',  'iso-8859-13',  'iso-8859-14',    'iso-8859-15',     'iso-8859-16',  'cp437',
    'cp850',        'cp852',        'cp855',          'cp857',           'cp858',        'cp860',
    'cp861',        'cp862',        'cp863',          'cp864',           'cp865',        'cp866',
    'cp869',        'cp037',        'cp424',          'cp500',           'cp720',        'cp737',
    'cp775',        'cp874',        'cp875',          'cp932',           'cp949',        'cp950',
    'cp1006',       'cp1026',       'cp1125',         'cp1140',          'big5hkscs',    'gb2312',
    'gbk',          'gb18030',      'euc-jp',         'euc-jis-2004',    'euc-jisx0213', 'euc-kr',
    'iso2022-jp',   'iso2022-jp-1', 'iso2022-jp-2',   'iso2022-jp-2004', 'iso2022-jp-3', 'iso2022-jp-ext',
    'iso2022-kr',   'johab',        'koi8-r',         'koi8-t',          'koi8-u',       'kz1048',
    'mac-cyrillic', 'mac-greek',    'mac-iceland',    'mac-latin2',      'mac-roman',    'mac-turkish',
    'ptcp154',      'shift-jis',    'shift-jis-2004', 'shift-jisx0213',  'hz',           'tis-620',
    'euc-tw',       'iso2022-tw'
]
# check_list_for_duplicates(text_encodings) # Run this after adding new extensions to ensure there are no duplicates.

# A comprehensive list of python extensions.
python_extensions = ['.py', '.pyw']

# A comprehensive list of text file extensions.
text_extensions = [
    '.txt',  '.html',     '.htm',      '.csv',        '.json', '.xml'
    '.adoc', '.asciidoc', '.bib',      '.cfg',        '.conf', '.ini',
    '.log',  '.md',       '.markdown', '.properties', '.rtf',  '.rst',
    '.sgm',  '.sgml',     '.tex',      '.toml',       '.tsv',  '.xhtml',
    '.yaml', '.yml',
]
# check_list_for_duplicates(text_extensions) # Run this after adding new extensions to ensure there are no duplicates.

# A comprehensive list of video file extensions.
video_extensions = [
    '.mp4',   '.mkv',   '.mov',   '.avi',  '.mpg',  '.mpeg',
    '.wmv',   '.m4v',   '.flv',   '.divx', '.vob',  '.iso',
    '.3gp',   '.webm',  '.mts',   '.m2ts', '.ts',   '.ogv',
    '.rm',    '.rmvb',  '.asf',   '.f4v',  '.mxf',  '.dv',
    '.swf',   '.m2v',   '.svi',   '.mpe',  '.ogm',  '.bik',
    '.xvid',  '.yuv',   '.qt',    '.gvi',  '.viv',  '.fli',
    '.mjpg',  '.mjpeg', '.amv',   '.drc',  '.flc',  '.wve',
    '.avchd', '.vp6',   '.ivf',   '.mps',  '.vro',  '.ssf',
    '.hevc',  '.h265',  '.264',   '.str',  '.evo',  '.3g2',
    '.h264',  '.av1',   '.ogx',   '.mlv',  '.ps',   '.tsx',
    '.mp2v',  '.dvs',   '.gxf',   '.m4p',  '.webp', '.vp8',
    '.trp',   '.f4p',   '.f4b',   '.f4m',  '.mk3d', '.3mm',
    '.3gpp',  '.mod',   '.tod',   '.cine', '.arf',  '.wrf',
    '.braw',  '.jmf',   '.r3d',   '.dpx',  '.mpv',  '.tsv',
    '.rmx',   '.smk',   '.mkd',   '.mj2',  '.scm',  '.ivr',
    '.xesc',  '.wtv',   '.dcr',   '.mpl',  '.pds',  '.ismv',
    '.vc1',   '.vcd',   '.mpcpl', '.bin',  '.sfd',  '.qtz',
    '.vdat',  '.vft',
]
# check_list_for_duplicates(video_extensions) # Run this after adding new extensions to ensure there are no duplicates.

# A comprehensive list of audio file extensions.
audio_extensions = [
    '.mp3',   '.wav',   '.flac',  '.aac',   '.ogg',   '.wma',
    '.m4a',   '.alac',  '.aiff',  '.opus',  '.amr',   '.pcm',
    '.au',    '.raw',   '.dts',   '.ac3',   '.mka',   '.mpc',
    '.vqf',   '.ape',   '.shn',   '.ra',    '.rm',    '.oga',
    '.spx',   '.caf',   '.snd',   '.mid',   '.midi',  '.kar',
    '.rmi',   '.m3u',   '.pls',   '.xspf',  '.asf',   '.wv',
    '.aa',    '.aax',   '.dsf',   '.dff',   '.sf2',   '.g721',
    '.voc',   '.swa',   '.bwf',   '.ivs',   '.smp',   '.htk',
    '.sds',   '.brstm', '.adx',   '.hca',   '.ast',   '.psf',
    '.psf2',  '.qsf',   '.ssf',   '.usf',   '.gsf',   '.flp',
    '.dsm',   '.dmf',   '.mod',   '.s3m',   '.it',    '.xm',
    '.mt2',   '.mo3',   '.umx',   '.tt',    '.tak',   '.trk',
    '.669',   '.abc',   '.ts',    '.ym',    '.hsq',   '.mpa',
]
# check_list_for_duplicates(audio_extensions) # Run this after adding new extensions to ensure there are no duplicates.

# A comprehensive list of subtitle file extensions.
subtitle_extensions = [
    '.srt',   '.sub',    '.idx',   '.ass',   '.ssa',   '.vtt',
    '.ttml',  '.dfxp',   '.smi',   '.smil',  '.usf',   '.psb',
    '.mks',   '.lrc',    '.stl',   '.pjs',   '.rt',    '.aqt',
    '.gsub',  '.jss',    '.dks',   '.mpl2',  '.tmp',   '.vsf',
    '.zeg',   '.webvtt', '.scc',   '.cap',   '.asc',   '.txt',
    '.sbv',   '.ebu',    '.sami',  '.xml',   '.itt',   '.qt.txt',
]
# check_list_for_duplicates(subtitle_extensions) # Run this after adding new extensions to ensure there are no duplicates.

# A comprehensive list of image file extensions.
image_extensions = [
    '.bmp',   '.dib',   '.gif',   '.jpeg',  '.jpg',   '.jpe',
    '.jfif',  '.pjpeg', '.pjp',   '.png',   '.pbm',   '.pgm',
    '.ppm',   '.pnm',   '.pam',   '.tif',   '.tiff',  '.sgi',
    '.rgb',   '.tga',   '.hdr',   '.exr',   '.webp',  '.apng',
    '.heic',  '.heif',  '.avif',  '.jp2',   '.j2k',   '.j2c',
    '.jxr',   '.svg',   '.svgz',  '.eps',   '.ai',    '.pdf',
    '.cdr',   '.emf',   '.wmf',   '.dxf',   '.dwg',   '.mng',
    '.raw',   '.arw',   '.cr2',   '.cr3',   '.dng',   '.erf',
    '.raf',   '.orf',   '.pef',   '.rw2',   '.rwl',   '.sr2',
    '.srw',   '.3fr',   '.kdc',   '.mrw',   '.mos',   '.nrw',
    '.pcx',   '.pcd',   '.pic',   '.pct',   '.xcf',   '.psd',
    '.psb',   '.kra',   '.fit',   '.fits',  '.fpx',   '.djvu',
    '.djv',   '.lbm',   '.iff',
]
# check_list_for_duplicates(image_extensions) # Run this after adding new extensions to ensure there are no duplicates.
