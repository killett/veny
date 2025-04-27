#!/usr/bin/env python3

# Written by Emmy Killett (she/her), ChatGPT 4o (it/its), ChatGPT o1-preview (it/its), ChatGPT o3-mini-high (it/its), and GitHub Copilot (it/its).
import os, sys, subprocess
import logging
from typing import Dict, Optional, TextIO

# This is the version of univ_defs.py
__version__ = '0.1.3'

# This is the version of python which should be used in scripts that import this module.
PY_VERSION = 3.11

def parent_unused_function():
    unused_function()

def unused_function():
    """This function is not used in the test.py script."""
    print("This function is not used in the test.py script.")
    import numpy as np

class univ_class:
    """Class that handles the import and operation of large language model APIs."""
    def __init__(self):
        self.import_test()

    def import_test(self) -> None:
        import openai

def parse_date(date_str: str) -> 'dt.datetime':
    """Try parsing the given date string in multiple formats. Once a format works, return the datetime object. If none of the formats work, raise a ValueError. If the date string is 'NOW', return the current datetime."""
    import datetime as dt
    if date_str.upper() == "NOW":
        return dt.datetime.now()
    for fmt in ("%Y", "%Y-%m", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return dt.datetime.strptime(date_str, fmt)
        except ValueError:
            pass
    raise ValueError(f"The date '{date_str}' is in an unknown format. Please use NOW, YYYY, YYYY-MM, YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS.")

def sci_exp(float_input: float) -> int:
    """Return the scientific exponent of a float."""
    import math
    max_digits = 15 #If the number is smaller than 10^(-max_digits), just say it has max_digits.
    if abs(float_input) < 10**(-max_digits): return -max_digits
    return int(math.floor(math.log10(abs(float_input))))

class LLMs:
    """Class that handles the import and operation of large language model APIs."""
    def __init__(self):
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
            except ImportError:
                self.found_llms[this_llm] = False
                print(f"{this_llm} package not found.")

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

# #"round out" away from zero while keeping round_digits significant figures.
# #Rounds up for x>0, down for x<0.
# def round_out(x, round_digits):
#   import numpy as np
#   if np.abs(x) < 10**(-max_digits): return x
#   these_digits = sci_exp(x) - round_digits + 1
#   thisfactor = 10**these_digits
#   x = x/thisfactor
#   if x > 0: x = np.ceil(x) 
#   else:     x = np.floor(x)
#   return x*(thisfactor*1.0)

# #Convert decimal years to datetimes.
# #From here: https://archive.vn/KyBU7  https://stackoverflow.com/questions/20911015/decimal-years-to-datetime-in-python 
# #and here: https://archive.vn/dCEqU  https://numpy.org/doc/stable/reference/arrays.datetime.html
# #Usage: dec2date(2002.29178082191777)
# def dec2date(dec):
#   import datetime as dt
#   year = int(dec)
#   rem = dec - year
#   base = dt.datetime(year, 1, 1)
#   result = base + dt.timedelta(seconds=(base.replace(year=base.year + 1) - base).total_seconds() * rem)
#   #result = np.datetime64(result)
#   return result

class MemoryHandler(logging.Handler):
    """A logging handler that stores logs in memory so the errors can be printed at the end."""
    def __init__(self, level=logging.ERROR):
        super().__init__(level)
        self.logs = []
    def emit(self, record):
        if record.levelno >= self.level:  # Only capture logs with the appropriate level
            self.logs.append(self.format(record))

class FlushingStreamHandler(logging.StreamHandler):
    """A logging handler that flushes the stream after emitting each log so the logs are immediately visible."""
    def emit(self, record):
        # Call the original emit method to handle the logging
        super().emit(record)
        # Immediately flush the stream after emitting the log
        self.flush()

class MaxLevelFilter(logging.Filter):
    """A logging filter that only allows logs up to a certain level to pass through, so that error messages aren't printed multiple times."""
    def __init__(self, max_level):
        self.max_level = max_level
    def filter(self, record):
        return record.levelno <= self.max_level
    
def configure_logging(basename: str, log_level: str = 'INFO',
                      rawlog: bool = False, logdir: str = '') -> MemoryHandler:
    """Configure logging to write to files and stdout/stderr, and return a MemoryHandler to capture ERROR logs for later (duplicate) printing."""
    import datetime as dt
    
    root_logger = logging.getLogger()

    # Check if logging is already configured by checking for any handlers
    if root_logger.hasHandlers():
        print("Logging is already configured.", flush=True)
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

def print_errors_at_end(memory_handler: MemoryHandler,
                        rawlog: bool) -> None:
    """Print any captured error messages at the end of the script."""
    if memory_handler.logs and not rawlog:
        print("\n****************************\nCaptured error messages:")
        for log in memory_handler.logs:
            print(log)

def my_critical_error(message: str = "A critical error occurred.",
                      choose_breakpoint: bool = False,
                      exit_code: int = 1) -> None:
    """Log a critical error message and either exit the program or enter a breakpoint."""
    import traceback
    # Determine if an exception is being handled:
    exc_type, exc_value, exc_traceback = sys.exc_info()
    #Check to see if logger is set up. If not, just print the critical error message.
    if logging.getLogger().hasHandlers():
        if exc_type:
            # An exception is being handled; include exception info
            logging.critical(message, exc_info=True)
        else:
            # No exception is being handled; log only the message
            logging.critical(message)
    else:
        if exc_type:
            # An exception is being handled; include exception info
            print(f"{message}\n", file=sys.stderr)
            traceback.print_exception(exc_type, exc_value, exc_traceback, file=sys.stderr)
        else:
            # No exception is being handled; log only the message
            print(message)
    if choose_breakpoint:
        print("Entering breakpoint while inside the my_critical_error() function. You can step outside of this function and remain paused by pressing 'n' to access variables in the calling function or press 'c' to continue running the script.")
        breakpoint()
    else:
        sys.exit(exit_code)

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

class MyPopenResult:
    """A class to store the results of a customized subprocess.Popen call."""
    def __init__(self, stdout: str, stderr: str, returncode: int):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.success = (returncode == 0)

def my_popen(command_list: list, suppress_info: bool = False,
             suppress_error: bool = False) -> MyPopenResult:
    """Execute a command using subprocess.Popen and capture the output line by line using threads."""
    import threading

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

        def read_stdout():
            for line in process.stdout:
                stdout_lines.append(line)
                log_line = line.strip()
                if not suppress_info:
                    logging.info(log_line)
                else:
                    logging.debug(log_line)

        def read_stderr():
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
             rawlog: bool = False) -> Optional[TextIO]:
    """Attempt to read the file with various encodings and return the file content if successful."""
    # List of encodings to try when reading files, with most likely encodings first.
    encodings = [
        'utf-8', 'latin-1', 'ascii', 'iso-8859-1', 'big5', 'utf-8-sig', 'utf-16', 
        'utf-16-be', 'utf-16-le', 'utf-32', 'utf-32-be', 'utf-32-le', 'cp1252', 'cp1251', 
        'cp1250', 'cp1253', 'cp1254', 'cp1255', 'cp1256', 'cp1257', 'cp1258', 'iso-8859-2', 
        'iso-8859-3', 'iso-8859-4', 'iso-8859-5', 'iso-8859-6', 'iso-8859-7', 'iso-8859-8', 
        'iso-8859-9', 'iso-8859-10', 'iso-8859-11', 'iso-8859-13', 'iso-8859-14', 'iso-8859-15', 
        'iso-8859-16', 'cp437', 'cp850', 'cp852', 'cp855', 'cp857', 'cp858', 'cp860', 'cp861', 
        'cp862', 'cp863', 'cp864', 'cp865', 'cp866', 'cp869', 'cp037', 'cp424', 'cp500', 
        'cp720', 'cp737', 'cp775', 'cp874', 'cp875', 'cp932', 'cp949', 'cp950', 'cp1006', 
        'cp1026', 'cp1125', 'cp1140', 'big5hkscs', 'gb2312', 'gbk', 'gb18030', 'euc-jp', 
        'euc-jis-2004', 'euc-jisx0213', 'euc-kr', 'iso2022-jp', 'iso2022-jp-1', 'iso2022-jp-2', 
        'iso2022-jp-2004', 'iso2022-jp-3', 'iso2022-jp-ext', 'iso2022-kr', 'johab', 'koi8-r', 
        'koi8-t', 'koi8-u', 'kz1048', 'mac-cyrillic', 'mac-greek', 'mac-iceland', 'mac-latin2', 
        'mac-roman', 'mac-turkish', 'ptcp154', 'shift-jis', 'shift-jis-2004', 'shift-jisx0213', 
        'hz', 'tis-620', 'euc-tw', 'iso2022-tw'
    ]
    #encodings = ['utf_8', 'latin_1', 'ascii', 'iso8859_1', 'big5', 'utf_8_sig', 'utf_16', 'utf_16_be', 'utf_16_le', 'utf_32', 'utf_32_be', 'utf_32_le', 'cp1252', 'cp1251', 'cp1250', 'cp1253', 'cp1254', 'cp1255', 'cp1256', 'cp1257', 'cp1258', 'iso8859_2', 'iso8859_3', 'iso8859_4', 'iso8859_5', 'iso8859_6', 'iso8859_7', 'iso8859_8', 'iso8859_9', 'iso8859_10', 'iso8859_11', 'iso8859_13', 'iso8859_14', 'iso8859_15', 'iso8859_16', 'cp437', 'cp850', 'cp852', 'cp855', 'cp857', 'cp858', 'cp860', 'cp861', 'cp862', 'cp863', 'cp864', 'cp865', 'cp866', 'cp869','cp037', 'cp424', 'cp500', 'cp720', 'cp737', 'cp775', 'cp874', 'cp875', 'cp932', 'cp949', 'cp950', 'cp1006', 'cp1026', 'cp1125', 'cp1140','big5hkscs', 'gb2312', 'gbk', 'gb18030', 'euc_jp', 'euc_jis_2004', 'euc_jisx0213', 'euc_kr', 'iso2022_jp', 'iso2022_jp_1', 'iso2022_jp_2', 'iso2022_jp_2004', 'iso2022_jp_3', 'iso2022_jp_ext', 'iso2022_kr', 'johab', 'koi8_r', 'koi8_t', 'koi8_u', 'kz1048', 'mac_cyrillic', 'mac_greek', 'mac_iceland', 'mac_latin2', 'mac_roman', 'mac_turkish', 'ptcp154', 'shift_jis', 'shift_jis_2004', 'shift_jisx0213', 'hz', 'tis_620', 'euc_tw', 'iso2022_tw']
    if not os.path.isfile(file_path):
        this_message = f"File does not exist: {file_path}"
        if not rawlog:
            if not suppress_errors: logging.error(this_message)
            else:                   logging.info(this_message)
        return False
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as file:
                file_content = file.read()
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

def my_ast_parse(file_content: str, file_path: str) -> 'Optional[ast.AST]':
    """Attempt to parse the file with ast.parse and return the tree if successful."""
    import ast
    try:
        tree = ast.parse(file_content, filename=file_path)
    except SyntaxError as e:
        logging.error(f"Syntax error parsing file {file_path}: {str(e)}")
        return
    except Exception as e:
        logging.error(f"Error parsing file {file_path}: {str(e)}")
        return
    return tree

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
    SECONDS_PER_YEAR   = 31556952

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
        except subprocess.CalledProcessError:
            print(f"No {pname} process found.")
        
        if process_ids:
            for pid in process_ids:
                print(f"Killing {pname} process with PID: {pid}")
                try:
                    os.kill(int(pid), signal.SIGTERM)  # Send SIGTERM to terminate the process
                    print(f"Sent SIGTERM to PID {pid}")
                except ProcessLookupError:
                    print(f"Process {pid} already terminated.")
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

def open_dir_in_VLC(the_dir: str, sort_choice: str = "sort_by_name",
                    recursive: bool = False,
                    no_start: bool = False) -> None:
    """Create a playlist of the files in the specified directory, then play that playlist in VLC. By default, don't search the directory recursively and sort the files by name. Optional arguments allow recursive loading or sorting by modification time. If no_start is True, don't start playback in VLC."""
    start_flag = "--start-paused" if no_start else ""
    #start_flag = "--no-playlist-autostart" if no_start else ""
    # List to store files with their modification times
    files_with_times = []
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
    # Write the playlist to disk
    playlist_path = os.path.join(os.getcwd(), "playlist.m3u")
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
                print(f"Error renaming '{filepath}' to '{new_filepath}': {e}")
                sys.exit(1)
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
    '.vdat',  '.vft',   '.md5',   '.par2', # The extensions.md5 and .par2 are included because hash/parity files are useful here.
]
# check_list_for_duplicates(video_extensions)

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
# check_list_for_duplicates(audio_extensions)

# A comprehensive list of subtitle file extensions.
subtitle_extensions = [
    '.srt',   '.sub',    '.idx',   '.ass',   '.ssa',   '.vtt',
    '.ttml',  '.dfxp',   '.smi',   '.smil',  '.usf',   '.psb',
    '.mks',   '.lrc',    '.stl',   '.pjs',   '.rt',    '.aqt',
    '.gsub',  '.jss',    '.dks',   '.mpl2',  '.tmp',   '.vsf',
    '.zeg',   '.webvtt', '.scc',   '.cap',   '.asc',   '.txt',
    '.sbv',   '.ebu',    '.sami',  '.xml',   '.itt',   '.qt.txt',
]
# check_list_for_duplicates(subtitle_extensions)
