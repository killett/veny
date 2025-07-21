#!/usr/bin/env python3

# Written by Emmy Killett (she/her), ChatGPT 4o (it/its), ChatGPT o1-preview (it/its), ChatGPT o3-mini-high (it/its), ChatGPT o4-mini-high (it/its), and GitHub Copilot (it/its).
from __future__ import annotations # For Python 3.7+ compatibility with type annotations
import os, sys, subprocess
import logging
from typing import Dict, TextIO, Any, TypeAlias, Type
import re # Used to precompile regexes for performance

# This is the version of univ_defs.py
__version__ = '0.1.5'

# This is the version of python which should be used in scripts that import this module.
PY_VERSION = 3.11

valid_basins = ["California", "Sacramento", "San Joaquin", "Tulare-Buena Vista Lakes"]

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
        self.lightcolors = ['grey',  'pink',   'lightblue', 'lightgreen', 'lightpurple'] # Used for shaded areas in light mode or for lines in dark mode
        self.linestyles  = ['solid', 'dashed', 'dashdot',   'dotted']
        self.dark_mode   = 0 # 1 = dark mode, 0 = light mode
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

    def send_prompt(self, prompt: str,
                    system_message: str, model: str,
                    company: str, temperature: float,
                    max_tokens: int = 1000) -> str:
        """Call the chosen LLM's API and return the text response."""
        try:
            # ADD NEW COMPANY LLMs HERE.
            if company == "OpenAI":
                response_obj = self.clients[company].chat.completions.create(
                    model=model,
                    temperature=temperature,
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user",   "content": prompt},
                    ]
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
        except Exception as e:
            my_critical_error(f"An error occurred: {e}", choose_breakpoint=True)

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

def fallback_logging_config(level: str = 'INFO') -> None:
    """Configure the root logger with a basic configuration if no handlers are set."""
    if not logging.getLogger().handlers:
        logging.basicConfig(level=level,
                            format="%(asctime)s %(name)s %(levelname)s: %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")

def configure_logging(basename: str, log_level: str = 'INFO',
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
    if not logdir: # Default to the current working directory if no logdir is provided.
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
    console_handler_stdout.setLevel(logging.DEBUG) # Set to lowest level
    console_handler_stdout.addFilter(MaxLevelFilter(logging.WARNING)) # Highest

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

    root_logger.setLevel(get_log_level(log_level))
    root_logger.addHandler(debug_info_handler)
    root_logger.addHandler(warning_error_handler)
    root_logger.addHandler(console_handler_stdout)
    root_logger.addHandler(console_handler_stderr)
    root_logger.addHandler(memory_handler)
    if not rawlog: root_logger.info(f'Logging to {log_info} and {log_errors} with level {logging.getLevelName(get_log_level(log_level))}')

    return memory_handler

def get_log_level(log_level: str) -> int:
    """Return the logging level based on the input string."""
    value_map = {'INFO'     : logging.INFO,
                 'DEBUG'    : logging.DEBUG,
                 'WARNING'  : logging.WARNING,
                 'WARN'     : logging.WARNING,
                 'ERROR'    : logging.ERROR,
                 'CRITICAL' : logging.CRITICAL}
    return value_map.get(log_level, logging.INFO)

def print_all_errors(memory_handler: MemoryHandler,
                     rawlog: bool = False) -> None:
    """Print all the captured error messages."""
    if memory_handler.logs and not rawlog:
        print("\n****************************\n****************************\nError messages:")
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
    fallback_logging_config(level='INFO' if not suppress_info else 'ERROR')
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

    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return MyPopenResult(stdout="", stderr=str(e), returncode=-1)

def my_fopen(file_path: str, suppress_errors: bool = False,
             rawlog: bool = False, numlines: int | None = None) -> TextIO | bool | str:
    """Attempt to read the file with various encodings and return the file content if successful. Optionally, specify numlines to limit the number of lines read and return a string instead of a file object."""
    fallback_logging_config(level='INFO' if not suppress_errors else 'CRITICAL')

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
            return file_content  # Exit the function if reading is successful
        except UnicodeDecodeError:
            this_message = f"Unicode decode error with encoding {encoding} reading file {file_path}"
            if not suppress_errors: logging.warning(this_message)
            else:                   logging.info(this_message)
            continue
        except Exception as e:
            this_message = f"Error reading file {file_path} with encoding {encoding}: {str(e)}"
            if not rawlog:
                if not suppress_errors: logging.error(this_message)
                else:                   logging.info(this_message)
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
                        raise ValueError(f"Cannot literal_eval the value of {var_name}") from e
        # also handle annotated assignments: var_name: Type = <expr>
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == var_name and node.value:
                try:
                    return ast.literal_eval(node.value)
                except ValueError as e:
                    raise ValueError(f"Cannot literal_eval the value of {var_name}") from e

    raise AttributeError(f"Top-level variable {var_name!r} not found in {script_path}")

def normalize_to_dict(value: Any, var_name: str, script_path: str) -> Dict:
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
            logging.warning(f"Failed to JSON-decode variable {var_name!r} from {script_path}: {e}. Expected a dict or JSON string.")
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
    result = subprocess.run(['hostname'], capture_output=True, text=True, check=True)
    return result.stdout.strip()

def get_hostname_subprocess_scutil() -> str:
    """Retrieves the hostname using the 'scutil --get ComputerName' command on macOS via subprocess."""
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
        except Exception as e:
            # Optionally, you can log the exception or print it for debugging
            # print(f"Method {method_name} failed with error: {e}")
            pass  # Skip methods that fail

    computer_name = analyze_results(results)

    return computer_name

def analyze_results(results: Dict[str, str]) -> str:
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
        #print(f"Computer Name: {most_common[0][0]}")
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

    while True:
        # Find the process IDs of the given process name
        process_ids = []
        try:
            process_list = subprocess.check_output(["pgrep", "-f", pname]).decode("utf-8")
            process_ids = process_list.splitlines()
        except subprocess.CalledProcessError as e:
            raise ValueError(f"Failed to find process with name {pname}. Make sure the process name is correct and unique.") from e
        
        if process_ids:
            for pid in process_ids:
                print(f"Killing {pname} process with PID: {pid}")
                try:
                    os.kill(int(pid), signal.SIGTERM)  # Send SIGTERM to terminate the process
                    print(f"Sent SIGTERM to PID {pid}")
                except ProcessLookupError as e:
                    raise ValueError(f"Process with PID {pid} not found. It may have already exited.") from e
        else:
            print(f"No {pname} process found.")
            break
        
        # Check if the process is still running
        time.sleep(2)  # Wait for 2 seconds before checking again
        process_ids = subprocess.check_output(["pgrep", "-f", pname]).decode("utf-8").splitlines()
        
        if not process_ids:
            print(f"{pname} process successfully killed.")
            break  # Exit the loop when the process is no longer running
        else:
            print(f"{pname} is still running. Retrying...")

def ensure_even_dimensions(image_path: str) -> None:
    """Ensure the image at 'image_path' has dimensions divisible by 2 by resizing if necessary."""
    from PIL import Image
    fallback_logging_config()
    """Ensure the image has dimensions divisible by 2 by resizing if necessary."""
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
                raise ValueError(f"Could not resize image {image_path} to even dimensions.") from e
        else:
            logging.info(f"Image already has even dimensions: width = {width}, height = {height}")

def human_bytesize(num: int, suffix: str='B') -> str:
    """Convert a file size in bytes to a human-readable string with units like KB, MB, GB, etc."""
    for unit in ['','K','M','G','T','P','E','Z','Y']:
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
    **dict.fromkeys(['year', 'years', 'yr', 'yrs', 'calendar year', 'calendar years'],    31_556_952), # Average calender year = 365.2425 days (accounting for leap years)
    **dict.fromkeys(['solar year', 'solar years', 'tropical year', 'tropical years'],     31_556_925.216), # Average solar/tropical year = 365.24219 solar days = time for Earth to orbit the Sun once relative to the Sun/equinoxes
    **dict.fromkeys(['sidereal year', 'sidereal years'],                                  31_558_149.54), # Sidereal year = 365.25636 days = time for Earth to orbit the Sun once relative to the "fixed" stars
    **dict.fromkeys(['month', 'months', 'mo', 'mos', 'calendar month', 'calendar months'], 2_629_746.0), # Average calendar month = 30.436875 solar days
    **dict.fromkeys(['lunar month', 'lunar months', 'synodic month', 'synodic months'],    2_551_442.9), # Average lunar month (synodic month) = 29.53 solar days
    **dict.fromkeys(['week', 'weeks', 'wk', 'wks'],                                          604_800.0), # 7 solar days
    **dict.fromkeys(['day', 'days', 'd', 'solar day', 'solar days', 'ephemeris day', 'ephemeris days'], 86_400), # 24 hours = time for Earth to rotate once relative to the Sun
    **dict.fromkeys(['sidereal day', 'sidereal days'],                                                  86_164.0905), # 23 hours, 56 minutes, 4.1 seconds = time for Earth to rotate once relative to the "fixed" stars
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
    **dict.fromkeys(['planck time', 'planck times', 'planck', 'plancks', 'pt'], 5.391_247E-44), # Planck time
    **dict.fromkeys(['decade', 'decades'],                                  315_569_252.16), #   10 solar years
    **dict.fromkeys(['century', 'centuries'],                             3_155_692_521.60), #  100 solar years
    **dict.fromkeys(['millennium', 'millennia'],                         31_556_925_216.00), # 1000 solar years
    **dict.fromkeys(['megayear', 'megayears', 'mya', 'myr'],         31_556_925_216_000.00), # 1E06 solar years
    **dict.fromkeys(['gigayear', 'gigayears', 'gya', 'gyr'],     31_556_925_216_000_000.00), # 1E09 solar years
    **dict.fromkeys(['terayear', 'terayears', 'tya', 'tyr'], 31_556_925_216_000_000_000.00), # 1E12 solar years
    **dict.fromkeys(['fortnight',    'fortnights'],                           1_209_600.00), # 2 weeks = 604_800 * 2 seconds
    **dict.fromkeys(['decasecond',   'decaseconds',   'das'], 1E01),
    **dict.fromkeys(['hectosecond',  'hectoseconds',  'hs'],  1E02),
    **dict.fromkeys(['kilosecond',   'kiloseconds',   'ks'],  1E03),
    **dict.fromkeys(['megasecond',   'megaseconds'],          1E06), # no Ms because .lower() would convert it to ms
    **dict.fromkeys(['gigasecond',   'gigaseconds',   'gs'],  1E09),
    **dict.fromkeys(['terasecond',   'teraseconds',   'ts'],  1E12),
    **dict.fromkeys(['petasecond',   'petaseconds'],          1E15), # no Ps because .lower() would convert it to ps
    **dict.fromkeys(['exasecond',    'exaseconds',    'es'],  1E18),
    **dict.fromkeys(['zettasecond',  'zettaseconds'],         1E21), # no Zs because .lower() would convert it to zs
    **dict.fromkeys(['yottasecond',  'yottaseconds'],         1E24), # no Ys because .lower() would convert it to ys
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
_TZ_ABBREV_TO_ZONE: dict[str,str] = {
    "UTC" : "UTC",
    "GMT" : "Etc/GMT",
    "EST" : "America/New_York",
    "EDT" : "America/New_York",
    "CST" : "America/Chicago", # WARNING! "CST" can also mean China Standard Time (Asia/Shanghai, UTC+8), so use with caution!
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
        if up.startswith(('UTC','GMT')):
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
        except ImportError: # for Python < 3.9, fall back to backports.zoneinfo
            from backports.zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        # Try to interpret the string as a timezone abbreviation
        if up in _TZ_ABBREV_TO_ZONE:
            zone_name = _TZ_ABBREV_TO_ZONE[up]
            return ZoneInfo(zone_name)

        # Try to interpret the string as a ZoneInfo name
        try:
            return ZoneInfo(tz_arg)
        except ZoneInfoNotFoundError as e:
            raise ValueError(f"Unknown timezone {tz_arg!r}") from e

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
            raise ValueError("'use_astropy=True' requires the astropy package") from e
        t = Time(dec, format='jyear', scale='utc')
        return t.to_datetime().replace(tzinfo=dt.timezone.utc)

    import datetime as dt
    try:
        year = int(dec)
        rem = dec - year
        start_dt = dt.datetime(year,   1, 1, tzinfo=dt.timezone.utc)
        end_dt   = dt.datetime(year+1, 1, 1, tzinfo=dt.timezone.utc)
        year_secs = (end_dt - start_dt).total_seconds()
        return start_dt + dt.timedelta(seconds=rem * year_secs)
    except ValueError as e:
        raise ValueError(f"Failed to convert decimal year {dec} to datetime") from e

def _parse_iso(given_date: str) -> dt.datetime:
    """Parse an ISO8601 date string and return a datetime object. Raises ValueError if the date string is invalid."""
    from dateutil.parser import isoparse, ParserError

    try:
        return isoparse(given_date)
    except ParserError as e:
        raise ValueError(f"Invalid ISO8601 date '{given_date}'") from e

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
        if u in ('J2000','UNIX','NOW'):
            logging.debug(f"Given date is a special keyword: {u}, so it will be converted by shifting the clock")
            return True
        if format_str and format_str.upper() in ('JD','MJD'):
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

def _finalize_datetime(parsed_dt: dt.datetime, original_input: AnyDateTimeType, format_str: str | None,
                       tz_arg: str | dt.tzinfo | None, should_convert: bool | None = None) -> dt.datetime:
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
                   format_str: str | None = None, should_convert: bool | None = None) -> dt.datetime:
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
      - fallback to dateutil.parser.parse for free-form strings (“18 Oct 2002”, “March 5th, 2020”, etc.)
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
        else: # If format is provided, parse the date using the specified format.
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
                raise ValueError(f"Invalid time unit '{units}' in format string '{format_str}'.") from e
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
                raise ValueError(f"Invalid epoch '{epoch}' in format string '{format_str}'.") from e
            # Now we can calculate the datetime based on the given_date (and the multiplier from 'units') and the epoch
            parsed_dt = epoch + dt.timedelta(seconds=float(given_date) * multiplier)

    if parsed_dt is None and type(given_date) is dt.datetime: # Don't use isinstance() here, because it will also match subclasses like Pandas Timestamp
        parsed_dt = given_date
    elif isinstance(given_date, dt.date): # Handle date objects (without time) as midnight
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
            raise ValueError(f"Invalid date format '{given_date}' with specified format '{format_str}'.") from e
    
    # Try parsing the date string in various formats
    # Start with RFC 2822 format, then ISO8601, then free-form strings
    # Store any errors encountered in a list to provide feedback if all parsing attempts fail.
    errors = []

    if parsed_dt is None:
        import email.utils
        try:
            # parses “Tue, 25 Jun 2025 14:00:00 GMT”
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
            parsed_dt = parse_fuzzy(given_date, default=dt.datetime(1900,1,1))
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
    """Round a number away from zero (i.e. rounds up for x>0 and down for x<0) to the specified number of significant figures (defaults to 3). If the number is smaller than 10^(-max_digits), it will be returned as is. The max_digits parameter defaults to 15, but can be changed to a different value if needed."""
    import numpy as np
    if np.abs(x) < 10**(-max_digits): return x
    these_digits = sci_exp(x) - round_digits + 1
    thisfactor = 10**these_digits
    x = x/thisfactor
    if x > 0: x = np.ceil(x) 
    else:     x = np.floor(x)
    return x*(thisfactor*1.0)

def get_user_input(prompt: str) -> bool:
    """Prompt the user with the given message and return True if the user enters 'yes', False otherwise."""
    user_input = input(prompt)
    return user_input.casefold() == 'yes' or user_input.casefold() == 'y'

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
    Turn arbitrary text into an ASCII-only, filesystem‐safe filename.
    
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
    import re
    import unidecode

    # 1. Normalize to ASCII
    text = unidecode.unidecode(text)

    # 2. Replace common “word boundaries” with sep
    #    (dots, underscores, whitespace) but keep dashes
    #    e.g. "hello.world--foo_bar" → "hello world--foo bar"
    text = re.sub(r"[._\s]+", sep, text)
    
    # 3. Remove anything but a–z, 0–9, dashes, or our sep
    allowed = f"A-Za-z0-9\-{re.escape(sep)}"
    text = re.sub(fr"[^{allowed}]+", "", text)
    
    # 4. Collapse runs of sep (e.g. “__” → “_”)
    text = re.sub(fr"{re.escape(sep)}{{2,}}", sep, text)
    
    # 5. Strip leading/trailing seps
    text = text.strip(sep)
    
    # 6. Optionally truncate (try not to cut in middle of a word)
    if max_length is not None and len(text) > max_length:
        # cut at max_length, then drop a partial trailing token if any
        truncated = text[:max_length]
        # if the next char in original isn't sep and our chop landed mid-token, trim back to last sep
        if (len(text) > max_length and
            not truncated.endswith(sep) and
            sep in truncated):
            truncated = truncated.rsplit(sep, 1)[0]
        text = truncated
    
    return text

def compile_script(file_path: str) -> bool:
    """Attempt to compile the given file in 'exec' mode. If it compiles, return True. On syntax or I/O problems, log an error and return False."""
    import logging
    fallback_logging_config()
    try:
        source = my_fopen(file_path, suppress_errors=True)
        if not source:
            logging.error(f"Could not read file: {file_path}")
        compile(source, file_path, 'exec')
        return True
    except FileNotFoundError:
        logging.error(f"File not found: {file_path}")
    except PermissionError:
        logging.error(f"Permission denied: {file_path}")
    except UnicodeDecodeError as e:
        logging.error(f"Could not decode {file_path!r} as UTF-8: {e}")
    except SyntaxError as e:
        # protect against None offsets
        lineno = e.lineno or '?'
        offset = e.offset or 0
        line = (e.text or '').rstrip('\n')
        pointer = ' ' * (offset - 1) + '^' if offset else ''
        logging.error(f"Syntax error in {e.filename!r}, line {lineno}, column {offset}:\n"
                      f"    {line}\n"
                      f"    {pointer}\n"
                      f"    {e.msg!r}")
    except Exception as e:
        logging.error(f"Unexpected error checking syntax of {file_path!r}: {e}")
    return False

# --------------------------------------------------------------------------------
# Note: Python resolves base classes at the moment a class statement is executed.
# That means any names used as base classes (e.g., ast.NodeVisitor) must already
# be defined in the current scope when the class is created.
#
# If we defer importing `ast` until inside a function but still try to define
# the class at the module level, Python will raise:
#     NameError: name 'ast' is not defined
#
# Wrapping the class definition in a factory function lets us:
#   1) Import `ast` inside the function, so it’s guaranteed to be in scope
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
    from typing import List, Tuple
    class FormatChecker(ast.NodeVisitor):
        """
        Walks a module AST and collects formatting violations:
        - missing type hints on params / return
        - missing docstring or incorrect docstring quote style
        """
        def __init__(self, source: str) -> None:
            """Initialize the FormatChecker with the source code string."""
            self.source = source
            self.errors: List[Tuple[str, str, str, int]] = []
            self._seen_funcs: set[int] = set() # keep track of which FunctionDef/AsyncFunctionDef nodes we've already checked

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
            If `in_method` is True, it indicates that this is a method (e.g. inside a class).
            If `container` is provided, it indicates the context (e.g. class name)."""
            if id(node) in self._seen_funcs: # ←─ skip if we’ve already run this exact node
                return
            self._seen_funcs.add(id(node))
            who = (f'function "{node.name}"' if container is None else f'{container} → method "{node.name}"')
            self._check_docstring(node, who)

            missing: List[str] = []
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
                self.errors.append(("function", node.name, "missing type hints for " + ", ".join(missing), node.lineno))

        def _check_docstring(self, node: ast.AST, who: str) -> None:
            """Check a node for a docstring and its formatting.
            If the node has no docstring or the docstring is not formatted correctly, an error is added to self.errors.
            The `who` parameter is a string describing the context (e.g. function or class name)."""
            if not node.body or not isinstance(node.body[0], ast.Expr):
                self.errors.append((node.__class__.__name__.lower(), who, "no docstring", node.lineno))
                return

            expr = node.body[0]
            if not (isinstance(expr.value, ast.Constant) and isinstance(expr.value.value, str)):
                self.errors.append((node.__class__.__name__.lower(), who, "no docstring", node.lineno))
                return

            # recover the exact literal to verify triple-double-quote
            literal = ast.get_source_segment(self.source, expr.value) or ""
            first_line = literal.strip().splitlines()[0]
            if first_line.startswith("'''"):
                self.errors.append((node.__class__.__name__.lower(), who, 'docstring should use triple double quotes ("""…""")', node.lineno))
    return FormatChecker
FormatChecker = _make_format_checker()

def check_python_formatting(path: str) -> None:
    """Reads a .py file at `path` via ud.my_fopen, parses it with ud.my_ast_parse, and prints any formatting violations to stdout."""
    src = my_fopen(path)
    if src is False:
        logging.error(f"❌ Failed to open file: {path}")
        return

    if '`' in src:
        logging.info(f"File {path} contains the backtick character (`). This is not recommended in Python source code, as it may cause issues with syntax highlighting or string formatting. Consider replacing it with a single quote (').")

    try:
        tree = my_ast_parse(src, path)
    except SyntaxError as e:
        logging.error(f"❌ {e}")
        return

    checker = FormatChecker(src)
    checker.visit(tree)

    if not checker.errors:
        logging.info("🎉 All functions and classes conform to the formatting rules.")
    else:
        max_lineno = max(err[3] for err in checker.errors)
        the_digits = sci_exp(max_lineno) + 1
        for kind, name, msg, lineno in checker.errors:
            logging.error(f"{lineno:>{the_digits}} – {kind.capitalize()} {name}: {msg}")
    
    if compile_script(path):
        logging.info(f"✅ {path} compiled successfully.")

def open_dir_in_VLC(the_dir: str, sort_choice: str = "sort_by_name",
                    recursive: bool = False,
                    no_start:  bool = False) -> None:
    """Create a playlist of the files in the specified directory, then play that playlist in VLC. By default, don't search the directory recursively and sort the files by name. Optional arguments allow recursive loading or sorting by modification time. If no_start is True, don't start playback in VLC."""
    if the_dir is None:
        raise ValueError("The directory path cannot be None.")
    elif not isinstance(the_dir, str):
        raise TypeError(f"Expected 'the_dir' to be a string, got {type(the_dir).__name__!r}")
    elif not os.path.isdir(the_dir):
        raise ValueError(f"The specified path '{the_dir}' is not a valid directory.")
    #start_flag = "--start-paused" if no_start else False # The "--start-paused" flag forces you to press play in VLC EACH TIME YOU GO TO A NEW PLAYLIST ENTRY!
    start_flag = "--no-playlist-autostart" if no_start else False
    # List to store files with their modification times
    files_with_times = []
    recursive_string = "recursive" if recursive else "NOT_recursive"
    if recursive:
        # Recursively iterate over the files in the directory
        for root, dirs, files in os.walk(the_dir):
            for filename in files:
                file_path = os.path.join(root, filename)
                if os.path.isfile(file_path):
                    mod_time = os.path.getmtime(file_path)
                    files_with_times.append((mod_time, file_path))
    else:
        for item in os.listdir(the_dir):
            item_path = os.path.join(the_dir, item)
            if os.path.isfile(item_path):
                mod_time = os.path.getmtime(item_path)
                files_with_times.append((mod_time, item_path))
            elif os.path.isdir(item_path):
                mod_time = os.path.getmtime(item_path)
                files_with_times.append((mod_time, item_path))
            else:
                print(f"Skipping {item_path} as it is not a file or directory.")

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
    # Write the playlist to disk in the specified directory
    playlist_path = os.path.join(the_dir, f"playlist_{sort_choice}_{recursive_string}.m3u")
    with open(playlist_path, "w") as playlist_file:
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
                raise OSError(f"Failed to rename '{filepath}' to '{new_filepath}'") from e
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
        with open(filepath, 'w', encoding='utf-8') as file:
            file.write(new_html)
        print(f"Removed prefix '{prefix}' from the title in '{filepath}'.")
        return True
    else:
        return False

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
