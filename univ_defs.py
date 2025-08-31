#!/usr/bin/env python3

# Written by Emmy Killett (she/her), ChatGPT 4o (it/its), ChatGPT o1-preview (it/its), ChatGPT o3-mini-high (it/its), ChatGPT o4-mini-high (it/its), ChatGPT 5 (it/its), and GitHub Copilot (it/its).
from __future__ import annotations  # For Python 3.7+ compatibility with type annotations
import os
from pathlib import Path  # Preferred over os.path for path manipulations.
import sys
import logging
from typing import TextIO, Any, TypeAlias, Type, Literal
from collections.abc import Iterator
import re  # Used to precompile regexes for performance

# This is the version of univ_defs.py
__version__: str = '0.1.7'

# This is the version of python which should be used in scripts that import this module.
PY_VERSION: float = 3.11

DEFAULT_ENCODING: str = 'utf-8'  # This is the default encoding used for reading and writing text files.

# ANSI escape codes
ANSI_RED:    str = "\033[91m"
ANSI_GREEN:  str = "\033[92m"  # this is bold/bright green on Linux but orange on my Mac
ANSI_YELLOW: str = "\033[93m"
ANSI_CYAN:   str = "\033[94m"  # this is blue on Linux but cyan on my Mac
ANSI_RESET:  str = "\033[0m"

# All the formatting rules to ignore when running flake8 to check Python formatting.
IGNORED_CODES: list[str] = [
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


class Options:
    """Class that has all global options in one place."""

    def __init__(self) -> None:
        """Initialize the options with default values."""
        self.log_mode: int = logging.INFO
        self.home:    Path = Path.home()  # User's home directory


class PlotOptions:
    """Global figure options."""

    def __init__(self) -> None:
        """Initialize PlotOptions class with default values."""
        # Ideas for improving this parent class: https://chatgpt.com/share/6876a7e2-da84-8006-9c8f-100d243b73e4
        self.myfigsize: tuple[int, int] = (16, 9)
        self.fsize:                 int = 24
        self.dpi_choice:            int = 300
        # self.colors      are used for shaded areas in light mode or for lines in dark mode
        # self.lightcolors are used for lines in light mode or for shaded areas in dark mode
        self.markers:         list[str] = ['o',     's',      '^',         'v',          '<',     '>']
        self.colors:          list[str] = ['black', 'red',    'blue',      'green',      'purple']
        self.lightcolors:     list[str] = ['grey',  'pink',   'lightblue', 'lightgreen', 'lightpurple']
        self.linestyles:      list[str] = ['solid', 'dashed', 'dashdot',   'dotted']
        self.dark_mode:             int = 0  # 1 = dark mode, 0 = light mode
        if self.dark_mode:  # Define colors as hexadecimal mainly because VS Code has a nifty color picker for hex colors.
            self.background_color:  str = '#000000'  # black background for dark mode
            self.text_color:        str = '#FFFFFF'  # white text for dark mode
            self.colors:      list[str] = [c.replace('black', 'darkgrey') for c in self.colors]
            self.lightcolors: list[str] = [c.replace('grey', 'lightgrey') for c in self.lightcolors]
        else:
            self.background_color:  str = '#FFFFFF'  # white background for light mode
            self.text_color:        str = '#000000'  # black text for light mode


class UnivClass:
    """Class that handles the import and operation of large language model APIs."""

    def __init__(self) -> None:
        """Initialize the class and import the necessary modules."""
        self.import_test()

    def import_test(self) -> None:
        """ Test the import of this module by printing a message and the version of Python being used."""
        import openai


def return_method_name(levels_up: int = 1) -> str:
    """
    Return the caller's qualified method/function name.

    - For instance methods: ClassName.method
    - For classmethods:     ClassName.method
    - For staticmethods:    ClassName.method on Python >= 3.11 (via co_qualname),
                            otherwise just 'method' (class is not recoverable without heuristics)
    - For functions:        function

    Args:
        levels_up: How many frames up to inspect (1 = caller). If greater than
                   the stack depth, the highest available frame is used.
    
    Returns:
        The current method name as a string, formatted as 'ClassName.method' or 'function'.
    
    Raises:
        None: This function does not raise exceptions, but it may log warnings
              if sys._getframe or inspect fails.
    """
    fallback_logging_config()
    try:
        levels = int(levels_up)
    except Exception:
        levels = 1
    if levels < 1:
        levels = 1
    name = "<unknown>"
    fr   = None
    # Try sys._getframe first
    try:
        fr = sys._getframe(levels)  # Get the frame at the specified level
    except Exception as e1:
        logging.warning("return_method_name(): sys._getframe(%s) failed. Falling back to inspect...", levels, exc_info=e1)
        try:
            import inspect
            frame = inspect.currentframe()
            try:
                fr = frame
                climbed = 0
                for _ in range(levels):
                    if fr is None or fr.f_back is None:
                        break
                    fr = fr.f_back
                    climbed += 1
                if climbed < levels:
                    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("return_method_name(): truncated at top of stack (requested levels_up=%s but only climbed=%s)", levels, climbed)
            finally:
                if frame is not None:
                    try:
                        frame.clear()
                    except Exception:
                        pass
                    del frame
        except Exception as e2:
            logging.warning("return_method_name(): inspect fallback failed", exc_info=e2)
            fr = None
    if fr is not None:
        # Python 3.11+: co_qualname gives 'Class.method' (or 'outer.<locals>.inner')
        qual = getattr(fr.f_code, "co_qualname", None)
        if isinstance(qual, str) and qual:
            # Remove all occurrences of '.<locals>.' from the qualified name.
            name = qual.replace(".<locals>.", ".")
        else:
            func     = fr.f_code.co_name
            self_obj = fr.f_locals.get("self")
            cls_obj  = fr.f_locals.get("cls")
            if self_obj is not None:
                name = f"{type(self_obj).__qualname__}.{func}"
            elif isinstance(cls_obj, type):
                name = f"{cls_obj.__qualname__}.{func}"
            else:
                argc = getattr(fr.f_code, "co_posonlyargcount", 0) + fr.f_code.co_argcount
                if argc:
                    for a in fr.f_code.co_varnames[:argc]:
                        obj = fr.f_locals.get(a)
                        if obj is not None:
                            t = obj if isinstance(obj, type) else type(obj)
                            attr = getattr(t, func, None)
                            if attr is not None:
                                name = f"{getattr(t, '__qualname__', t.__name__)}.{func}"
                                break
                    else:
                        name = func
                else:
                    name = func
    else:
        logging.warning("return_method_name(): no frame available.")
    if fr is not None:
        if name == "<module>":
            mod = fr.f_globals.get("__name__")
            if isinstance(mod, str) and mod:
                name = mod
    fr = None  # Clear the frame reference to free memory.
    return name


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
        from types import ModuleType
        # 1. Import the LLM APIs into the self.llm_modules dictionary.
        # ADD NEW COMPANY LLMs HERE.
        self.llms: list[dict[str, str]] = [
            {"name": "OpenAI",    "module": "openai",    "env_var": "OPENAI_API_KEY"},
            {"name": "Anthropic", "module": "anthropic", "env_var": "ANTHROPIC_API_KEY"},
        ]
        self.found_llms:  dict[str,       bool] = {}
        self.llm_modules: dict[str, ModuleType] = {}
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
        self.clients: dict[str, Any] = {}
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


def fallback_logging_config(log_level: int | str = logging.INFO, rawlog: bool = False) -> None:
    """
    Configure the root logger with a basic configuration if no handlers are set.
    Run this at the start of functions which might be run without first configuring logging.

    Args:
        level  : The logging level to set. Defaults to logging.INFO.
        rawlog : If True, use a simple log format without timestamps or levels.
    """
    root = logging.getLogger()
    for h in root.handlers:
        print(h, h.level, getattr(h.formatter, "_fmt", None))

    if not logging.getLogger().handlers:
        if not rawlog:  # Use a full logging format with timestamps and levels.
            logging.basicConfig(level=log_level,
                                format="%(asctime)s - %(levelname)s - %(message)s",
                                datefmt="%Y-%m-%d %H:%M:%S")
        else:  # rawlog is True, so use a simple format without timestamps or levels.
            logging.basicConfig(level=log_level, format="%(message)s")


def configure_logging(basename: str, log_level: int | str = logging.INFO,
                      rawlog: bool = False, logdir: str | os.PathLike[str] = '') -> MemoryHandler:
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
        logdir = Path.cwd() / "logs"
    else:
        logdir = Path(logdir).expanduser().resolve()
    logdir.mkdir(parents=True, exist_ok=True)

    now = dt.datetime.now()
    log_base = f".{basename}-log-{now.strftime('%Y%m%d-%H%M%S')}"
    log_info = logdir / (log_base + ".out")
    log_errors = logdir / (log_base + ".err")

    root_logger.handlers = []  # Reset any existing handlers

    # File handlers for logging to files
    try:
        debug_info_handler    = logging.FileHandler(log_info)
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

    debug_info_handler.setFormatter(    log_format)
    warning_error_handler.setFormatter( log_format)
    console_handler_stdout.setFormatter(log_format)
    console_handler_stderr.setFormatter(log_format)
    memory_handler.setFormatter(        log_format)

    root_logger.setLevel(log_level)
    root_logger.addHandler(debug_info_handler)
    root_logger.addHandler(warning_error_handler)
    root_logger.addHandler(console_handler_stdout)
    root_logger.addHandler(console_handler_stderr)
    root_logger.addHandler(memory_handler)
    if not rawlog: root_logger.info("Logging to '%s' and '%s' with level %s", log_info, log_errors, logging.getLevelName(root_logger.level))

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
    import shlex
    fallback_logging_config(log_level=logging.INFO if not suppress_info else logging.ERROR)
    command_list_str = [str(item) for item in command_list]
    the_statement = "Executing command: " + ' '.join(shlex.quote(os.fspath(arg)) for arg in command_list_str)
    if not suppress_info:
        logging.info(the_statement)
    else:
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug(the_statement)

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
                    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug(log_line)

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
                    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug(log_line)

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
            logging.error("An error occurred while executing the command '%s'", command_list_str, exc_info=True)
        else:
            logging.info("An error occurred while executing the command '%s'", command_list_str, exc_info=True)
        return MyPopenResult(stdout="", stderr=str(e), returncode=-1)


def my_fopen(file_path: str | os.PathLike[str], suppress_errors: bool = False,
             rawlog: bool = False, numlines: int | None = None) -> TextIO | bool | str:
    """
    Attempt to read a text file with various encodings and return the file content if successful. Optionally, specify numlines to limit the number of lines read and return a string instead of a TextIO object.

    Args:
        file_path:       Path to the file to read.
        suppress_errors: If True, suppress error messages and return False instead of logging errors.
        rawlog:          If True, use a simple log format without timestamps or levels.
        numlines:        If specified, read only this many lines from the file and return them as a string.

    Returns:
        The content of the file as a string if numlines is specified, otherwise a TextIO object. Returns False if the file does not exist, is empty, or is a non-text file (video, audio, or image).

    Raises:
        FileNotFoundError:  If the file does not exist.
        UnicodeDecodeError: If the file cannot be read with any of the specified encodings.
    """
    fallback_logging_config(log_level=logging.INFO if not suppress_errors else logging.CRITICAL,
                            rawlog=rawlog)
    file_path = Path(file_path).expanduser().resolve()
    if not file_path.exists():
        this_message = f"File does not exist: {file_path}"
        if not rawlog:
            if not suppress_errors: logging.error(this_message)
            else:                   logging.info(this_message)
        return False
    if not file_path.is_file():
        this_message = f"Path is a directory, not a file: {file_path}"
        if not rawlog:
            if not suppress_errors: logging.error(this_message)
            else:                   logging.info(this_message)
        return False
    if file_path.stat().st_size == 0:
        this_message = f"File is empty: {file_path}"
        if not rawlog:
            if not suppress_errors: logging.error(this_message)
            else:                   logging.info(this_message)
        return False
    # Does the file end with any of these (non-text) extensions?
    # Join all suffixes because some listed extensions look like ".tar.gz"
    if "".join(file_path.suffixes).casefold() in video_extensions:
        if not rawlog:
            if not suppress_errors: logging.error("Skipping video file %s", file_path)
            else:                   logging.info( "Skipping video file %s", file_path)
        return False
    if "".join(file_path.suffixes).casefold() in audio_extensions:
        if not rawlog:
            if not suppress_errors: logging.error("Skipping audio file %s", file_path)
            else:                   logging.info( "Skipping audio file %s", file_path)
        return False
    if "".join(file_path.suffixes).casefold() in image_extensions:
        if not rawlog:
            if not suppress_errors: logging.error("Skipping image file %s", file_path)
            else:                   logging.info( "Skipping image file %s", file_path)
        return False
    if "".join(file_path.suffixes).casefold() in archive_extensions:
        if not rawlog:
            if not suppress_errors: logging.error("Skipping archive file %s", file_path)
            else:                   logging.info( "Skipping archive file %s", file_path)
        return False
    for encoding in text_encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as file:
                if numlines is None:
                    file_content = file.read()
                else:
                    file_content = ''.join(file.readline() for _ in range(numlines))
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Successfully read %s with encoding %s", file_path, encoding)
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


def load_ast_var(var_name: str, script_path: str | os.PathLike[str],
                 rawlog: bool = False) -> Any | None:
    """
    Load a top-level literal Python variable from a module without executing it.

    Args:
        var_name:    The name of the global variable to extract from the script.
        script_path: The path to the Python script file from which to extract the variable.
        rawlog:      If True, use a simple log format without timestamps or levels.

    Returns:
        The value of the variable if found, or None.

    Raises:
        FileNotFoundError: If the script file does not exist.
        AttributeError:    If the variable is not found at the top level of the script.
        ValueError:        If the value of the variable cannot be evaluated as a literal expression.
    """
    fallback_logging_config(rawlog=rawlog)
    import ast
    file_content = my_fopen(script_path, rawlog=rawlog)
    if not file_content:
        my_critical_error(f"Failed to open {script_path}", choose_breakpoint=True)
    tree = ast.parse(file_content, script_path)
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

    logging.info("Top-level variable %r not found in %s", var_name, script_path)
    return None


def _sanitize_text_signature(sig: str | None) -> str:
    """
    Clean up a __text_signature__ string for display.
    
    Args:
        sig: The __text_signature__ string to clean up.
    
    Returns:
        A cleaned-up version of the signature string.
    
    Raises:
        None.
    """
    if not sig:
        return "(...)"
    s = sig
    # Replace CPython-internal placeholders
    s = s.replace("$self", "self").replace("$module", "")
    # Tidy up commas/spaces that might be left after removing $module
    s = re.sub(r"\(\s*,", "(", s)
    s = re.sub(r",\s*,", ", ", s)
    s = s.replace("(,", "(").replace(", )", ")")
    return s


def _builtin_stub(obj: object) -> str:
    """
    Return a stub definition for a built-in or C-extension function.
    
    Args:
        obj: The built-in function or method object.
    
    Returns:
        A string representing a stub definition of the function.
    
    Raises:
        None.
    """
    import inspect
    from textwrap import indent
    def_name = getattr(obj, "__name__", getattr(obj, "__qualname__", "<builtin>"))
    context = None
    if hasattr(obj, "__objclass__"):
        context = f"{obj.__objclass__.__name__}.{def_name}"   # e.g., "list.append"
    else:
        mod = getattr(obj, "__module__", None)
        if mod and mod != "builtins":
            context = f"{mod}.{def_name}"                     # e.g., "math.prod"
    header = f"# {context}\n" if context else ""

    try:
        sig = str(inspect.signature(obj))
    except Exception:
        sig = _sanitize_text_signature(getattr(obj, "__text_signature__", None))

    doc = inspect.getdoc(obj) or "Built-in function; Python source unavailable."
    doc = doc.replace('"""', '\\"""')  # keep our triple quotes intact
    doc = indent(doc, '    ')
    return f"{header}def {def_name}{sig}:\n    \"\"\"\n{doc}\n    \"\"\"\n    ...\n"


def show_function_source(target: object | str, *, unwrap: bool = True,
                         file: TextIO | None = None) -> str:
    """
    Print the full source text of a Python function (including comments,
    docstrings, decorators, and type hints).

    Args:
        target: A function *name* (string) or a function object.
                If a string is given, it's resolved in the caller's scope, then
                in builtins, then as a dotted path via pydoc.locate (e.g. 'pkg.mod.func').
        unwrap: If True, attempt to unwrap decorated functions to show
                the original implementation. Defaults to True.
        file:   A file-like object to write to (defaults to sys.stdout).

    Returns:
        str: The source text that was printed.

    Raises:
        NameError: If a string cannot be resolved to an object.
        OSError:   If source is unavailable (e.g., built-in/C extension or optimized away).
        TypeError: If the resolved object isn't suitable for source extraction.
    """
    import builtins
    import functools
    import inspect
    import pydoc
    # Resolve the object if `target` is a string
    if isinstance(target, str):
        name = target
        frame = inspect.currentframe().f_back  # caller's frame
        try:
            obj = frame.f_locals.get(name)
            if obj is None:
                obj = frame.f_globals.get(name)
            if obj is None:
                obj = getattr(builtins, name, None)
            if obj is None and "." in name:
                head, *tail = name.split(".")
                base = frame.f_locals.get(head)
                if base is None:
                    base = frame.f_globals.get(head)
                if base is None:
                    base = getattr(builtins, head, None)
                if base is not None:
                    try:
                        for part in tail:
                            base = getattr(base, part)
                        obj = base
                    except Exception:
                        pass
            if obj is None:
                # Try dotted-path resolution (e.g., "pkg.module.func")
                obj = pydoc.locate(name)
        finally:
            # Avoid reference cycles
            del frame

        if obj is None:
            raise NameError(f"Could not resolve '{name}' to a function object.")
    else:
        obj = target

    # Optionally unwrap decorated functions
    if unwrap:
        try:
            obj = inspect.unwrap(obj)
        except Exception:
            pass  # not fatal if we can't unwrap

    if isinstance(obj, functools.partial):
        obj = obj.func

    if not (inspect.isroutine(obj) or inspect.ismethoddescriptor(obj)):
        call = getattr(obj, "__call__", None)
        if call and (inspect.isfunction(call) or inspect.ismethod(call)):
            obj = call

    # Built-ins / C-extensions don’t have retrievable Python source
    if inspect.isbuiltin(obj) or inspect.ismethoddescriptor(obj):
        src = _builtin_stub(obj)
    else:
        src = inspect.getsource(obj)

    out = file or sys.stdout
    # Preserve the exact text (including trailing newline if missing)
    print(src, file=out, end="" if src.endswith("\n") else "\n")
    return src


def normalize_to_dict(value: Any, var_name: str, script_path: str | os.PathLike[str]) -> dict:
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
            logging.warning("Variable %r in %r JSON-decoded to %s, expected dict.", var_name, script_path, type(parsed).__name__)
        except json.JSONDecodeError as e:
            logging.warning("Failed to JSON-decode variable %r from %s. Expected a dict or JSON string.", var_name, script_path, exc_info=e)
    else:
        logging.warning("Variable %r in %s is of type %s, expected dict or JSON string.", var_name, script_path, type(value).__name__)
    return {}


def get_hostname_socket(rawlog: bool = False) -> str | None:
    """Retrieves the hostname using socket.gethostname()."""
    try:
        import socket
        return socket.gethostname()
    except Exception as e:
        if not rawlog: logging.warning("Failed to retrieve hostname using %s: %s", return_method_name(), e)
        return None


def get_hostname_platform(rawlog: bool = False) -> str | None:
    """Retrieves the hostname using platform.node()."""
    try:
        import platform
        return platform.node()
    except Exception as e:
        if not rawlog: logging.warning("Failed to retrieve hostname using %s: %s", return_method_name(), e)
        return None


def get_hostname_os_uname(rawlog: bool = False) -> str | None:
    """Retrieves the hostname using os.uname().nodename."""
    try:
        return os.uname().nodename
    except Exception as e:
        if not rawlog: logging.warning("Failed to retrieve hostname using %s: %s", return_method_name(), e)
        return None


def get_hostname_subprocess_hostname(rawlog: bool = False) -> str | None:
    """Retrieves the hostname using the 'hostname' system command via subprocess."""
    try:
        import subprocess
        result = subprocess.run(['hostname'], capture_output=True, text=True)
        return result.stdout.strip()
    except Exception as e:
        if not rawlog: logging.warning("Failed to retrieve hostname using %s: %s", return_method_name(), e)
        return None


def get_hostname_subprocess_scutil(rawlog: bool = False) -> str | None:
    """Retrieves the hostname using the 'scutil --get ComputerName' command on macOS via subprocess."""
    if sys.platform == 'darwin':
        try:
            import subprocess
            result = subprocess.run(['scutil', '--get', 'ComputerName'],
                                    capture_output=True, text=True)
            return result.stdout.strip()
        except Exception as e:
            if not rawlog: logging.warning("Failed to retrieve hostname using %s: %s", return_method_name(), e)
    return None


def get_computer_name(rawlog: bool = False) -> str:
    """
    Attempts multiple methods to retrieve the computer's name and returns the most common one.

    Args:
        rawlog: If True, print statements are disabled.
    
    Returns:
        A string representing the most common computer name obtained from the methods.
        If no names were retrieved, returns "ERROR-NO-NAME".
    
    Raises:
        None: This function does not raise exceptions, but it may log warnings if no names are retrieved.
    """
    fallback_logging_config(rawlog=rawlog)
    methods = {
        'socket_gethostname':  get_hostname_socket,
        'platform_node':       get_hostname_platform,
        'os_uname_nodename':   get_hostname_os_uname,
        'subprocess_hostname': get_hostname_subprocess_hostname,
    }

    if sys.platform == 'darwin':  # This next method is macOS-specific
        methods['subprocess_scutil_computername'] = get_hostname_subprocess_scutil

    results = {}

    for method_name, method_func in methods.items():
        try:
            name = method_func(rawlog=rawlog)
            if name:
              results[method_name] = name
        except Exception:  # Ignore all exceptions for individual methods
            if not rawlog: logging.exception("Method %s failed.", method_name)
            pass  # Skip methods that fail

    computer_name = analyze_computer_name_results(results, rawlog=rawlog)

    return computer_name


def analyze_computer_name_results(results: dict[str, str], rawlog: bool = False) -> str:
    """
    Analyzes the retrieved computer names.

    Args:
        results: Dictionary with method names as keys and computer names as values.
        rawlog:  If True, print statements are disabled.

    Returns:
        A string representing the most common computer name obtained from the methods.
        If no names were retrieved, returns "ERROR-NO-NAME".
    
    Raises:
        None: This function does not raise exceptions, but it may log errors or warnings if
              no names (or differing names) are retrieved.
    """
    from collections import Counter
    fallback_logging_config(rawlog=rawlog)

    if not results:
        if not rawlog: logging.error("No methods succeeded in retrieving the computer name.")
        return "ERROR-NO-NAME"

    name_values = list(results.values())
    name_counts = Counter(name_values)
    most_common = name_counts.most_common()

    if len(name_counts) == 1:
        # All names are identical
        if not rawlog: logging.info("Computer name: %s", most_common[0][0])
        return most_common[0][0]
    else:
        # Names are not identical
        primary_name, primary_count = most_common[0]
        differing = {name: count for name, count in most_common if name != primary_name}

        if not rawlog:
            the_string = f"Multiple computer names detected:\n"
            the_string += f" - Most common name: {primary_name} (appeared {primary_count} times)\n"
            the_string += f" - Other names: {', '.join(f'{name} ({count} times)' for name, count in differing.items())}\n"
            detailed_results_str = '\n'.join(f'     - {method}: {name}' for method, name in results.items())
            the_string += f" - Detailed method outputs:\n{detailed_results_str}"
            logging.warning(the_string)

        return primary_name


def detect_shell(options: Options) -> None:
    """
    Detect the current interactive shell, falling back to parent process name if needed.

    Args:
        options: Options object to store the detected shell information.

    Returns:
        None, but updates options.shell with the detected shell name.
    
    Raises:
        None, but logs an error if the shell cannot be detected via
        subprocess.CalledProcessError or FileNotFoundError.
    """
    import subprocess
    shell_path = os.getenv("SHELL")
    if not shell_path: # If shell_path is None or empty (""), try to get the parent process name
        try:
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("SHELL environment variable not set, trying to detect shell from parent process.")
            ppid   = os.getppid()
            result = subprocess.run(["ps", "-p", str(ppid), "-o", "comm="],
                                    capture_output=True, text=True, check=True)
            shell_path = result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logging.error(f"Error detecting shell via ps: {e}")
    if shell_path:
        options.shell = Path(shell_path).resolve().name.lstrip("-")
    else:
        logging.error("Could not detect shell from SHELL environment variable or parent process.")
        options.shell = None


def find_shell_rc_file(options: Options) -> None:
    """
    Find the shell configuration file for the current user, store in options.rc_file.
    For bash/zsh, also consider login‐shell files if the usual rc isn’t present.

    Args:
        options: Options object containing the shell type and rc_file attribute.

    Returns:
        None, but updates options.rc_file with the path to the shell configuration file.
    
    Raises:
        None, but logs an error if the shell is unsupported or if no rc file is found
        for the specified shell.
    """
    candidates = []

    xdg = Path(os.environ.get("XDG_CONFIG_HOME", options.home / ".config"))
    if options.shell == "bash":
        candidates = [".bashrc", ".bash_profile", ".bash_login", ".profile"]
    elif options.shell == "zsh":
        candidates = [".zshrc", ".zprofile"]
    elif options.shell == "fish":
        candidates = [os.fspath(xdg / "fish" / "config.fish")]  # just to be consistent with the other strings.
    elif options.shell == "csh":
        candidates = [".cshrc"]
    elif options.shell == "tcsh":
        candidates = [".tcshrc"]
    else:
        logging.error(f"Unsupported shell: {options.shell}")
        options.rc_file = None
        return

    # pick the first one that actually exists
    for fname in candidates:
        path = options.home / fname
        if path.is_file():
            options.rc_file = path
            break
    else:
        options.rc_file = None
        logging.error("No existing rc file found for %s shell in %s. Tried: %s.",
                      options.shell, options.home, ', '.join(candidates))


def find_additional_alias_files(options: Options) -> None:
    """Find additional alias files for the shell."""
    # Define common potential additional alias files based on the shell type.
    if options.shell == "bash":
        options.additional_alias_files.append(options.home / ".bash_aliases")
    elif options.shell == "zsh":
        options.additional_alias_files.append(options.home / ".zsh_aliases")
    elif options.shell == "fish":
        options.additional_alias_files.append(options.home / ".config" / "fish" / "conf.d" / "aliases.fish")
    elif options.shell == "csh":
        options.additional_alias_files.append(options.home / ".csh_aliases")
    elif options.shell == "tcsh":
        options.additional_alias_files.append(options.home / ".tcsh_aliases")
    else:
        logging.error(f"Unsupported shell for additional alias files: {options.shell}")
    valid_files = []
    for this_file in options.additional_alias_files:
        if this_file.is_file():
            valid_files.append(this_file)
        else:
            logging.error(f"Additional alias file {this_file} does not exist for shell {options.shell}.")
    options.additional_alias_files = valid_files


def ensure_path_is_a_file(path: str | os.PathLike[str]) -> Path:
    """
    Ensure that the given path is an existing file and return it as a Path object.
    
    Args:
        path: The path to check.

    Returns:
        A Path object representing the file.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    p = Path(path).resolve(strict=True)
    if not p.is_file():
        raise IsADirectoryError(f"Expected a file, got directory: {p}")
    if p.stat().st_size == 0:
        logging.warning("File is empty: %s", p)
    return p


def download_file(url: str, dest: str | os.PathLike[str], retries: int = 5,
                  chunk_size: int = 1 << 20, timeout: int = 30,
                  headers: dict[str, str] | None = None) -> None:
    """
    Download a file to 'dest' with retry + exponential backoff.
    Writes to a temporary .part file and renames atomically on success.
    Verifies Content-Length if provided.
    Logs progress by bytes (rough).
    Also checks free disk space (if size is known) before downloading.

    Args:
        url:        The source URL to download from.
        dest:       Destination file path.
        retries:    Number of attempts (default 5 is a good balance for transient errors).
        chunk_size: Bytes per read chunk (default 1MiB).
        timeout:    Per-attempt socket timeout (seconds).
        headers:    Optional dict of HTTP headers to include in the request.

    Returns:
        None. Writes the file to 'dest'.

    Raises:
        SystemExit on failure after retries or if insufficient free space is detected.
    """
    import time
    from urllib.request import Request, urlopen
    from urllib.error import URLError, HTTPError
    import socket

    fallback_logging_config()
    dest = Path(dest).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = dest.with_suffix(dest.suffix + ".part")

    base_headers = {"Accept-Encoding" : "identity",
                    "User-Agent"      : "python-download/1.0",}
    eff_headers  = {**base_headers, **(headers or {})}

    succeeded = False  # Track if download succeeded

    # Remove any stale partial to avoid skewing free-space checks.
    try:
        if temp.exists():
            temp.unlink()
    except OSError:
        # If we can't remove it, we'll truncate on open later; free-space check may be conservative.
        pass

    # Pre-flight: attempt to learn expected size and check free space.
    expected: int | None = None
    try:
        req_head = Request(url, headers=eff_headers, method="HEAD")
        with urlopen(req_head, timeout=timeout) as r:
            cl = r.headers.get("Content-Length")
            if cl:
                try:
                    expected = int(cl.strip())
                except ValueError:
                    expected = None
    except Exception as e:
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("HEAD probe failed (%s); proceeding without pre-known size.", e)

    if expected is not None:
        # Skip re-download if size matches on disk already.
        if dest.exists():
            try:
                if dest.stat().st_size == expected:
                    logging.info("File already present with expected size; skipping: %s", dest)
                    return
            except OSError:
                pass
        free_bytes = query_free_space(dest)
        if free_bytes < expected:
            raise SystemExit(f"Not enough disk space: need {human_bytesize(expected)}, have {human_bytesize(free_bytes)}")

    backoff = 1.0
    last_err: Exception | None = None

    for attempt in range(1, max(1, retries) + 1):
        try:
            logging.info("Downloading %s → %s (attempt %d/%d)", url, dest, attempt, retries)
            req = Request(url, headers=eff_headers)
            with urlopen(req, timeout=timeout) as resp:
                total = resp.headers.get("Content-Length")
                total_i = None
                if total:
                    try:
                        total_i = int(total.strip())
                    except ValueError:
                        pass
                # Re-check space at the moment of download if size is known.
                if total_i is not None:
                    free_bytes = query_free_space(dest)
                    if free_bytes < total_i:
                        raise SystemExit(
                            f"Not enough disk space: need {human_bytesize(total_i)}, have {human_bytesize(free_bytes)}"
                        )

                with temp.open("wb") as f:
                    downloaded = 0
                    last_bucket = -1
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_i:
                            # Lightweight textual progress (kept minimal for logging)
                            pct = int(downloaded * 100 / total_i)
                            bucket = pct // 10
                            # Log just once every ~10% but not at 0%
                            if pct and pct % 10 == 0 and bucket != last_bucket:
                                logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("… %d%% (%s out of %s)", pct, human_bytesize(downloaded), human_bytesize(total_i))
                                last_bucket = bucket
                    f.flush()
                    os.fsync(f.fileno())

            # Verify size if Content-Length available
            if total_i is not None:
                actual = temp.stat().st_size
                if actual != total_i:
                    raise IOError(f"Incomplete download: expected {total_i} bytes, got {actual} bytes")
            temp.replace(dest)
            logging.info("Saved %s (%s)", dest, human_bytesize(dest.stat().st_size))
            succeeded = True
            return
        except (HTTPError, URLError, socket.timeout, TimeoutError, IOError) as e:
            last_err = e
            logging.warning("Download failed (%s).", e)
            if attempt >= retries:
                break
            sleep_s = backoff
            backoff = min(backoff * 2, 30.0)  # cap backoff
            logging.info("Retrying in %.1f seconds…", sleep_s)
            time.sleep(sleep_s)
        except Exception as e:
            # Unexpected errors: don't loop indefinitely
            last_err = e
            logging.exception("Unexpected error during download.")
            break
        finally:
            try:
                if not succeeded and temp.exists():
                    temp.unlink()
            except OSError:
                pass

    raise SystemExit(f"Failed to download {url} after {retries} attempts. Last error: {last_err}")


def query_free_space(path: str | os.PathLike[str]) -> int:
    """
    Return the free space (in bytes) available to the current user on the
    filesystem that contains `path`. Works for files or directories, and
    for paths that don't yet exist (it climbs to the nearest existing parent).

    Args:
        path: A file or directory path.
    
    Returns:
        Free space in bytes available to the current user on the filesystem.
    
    Raises:
        FileNotFoundError: If no existing parent directory is found.
        OSError:           If the filesystem information cannot be retrieved.
    """
    p = Path(path)

    # Use the path itself if it's an existing directory; otherwise use its parent.
    base = p if (p.exists() and p.is_dir()) else p.parent

    # Climb up until we find an existing directory.
    while not base.exists():
        if base == base.parent:
            raise FileNotFoundError(f"No existing parent found for {path!r}")
        base = base.parent

    # POSIX: prefer statvfs to get user-available bytes (excludes reserved blocks).
    if hasattr(os, "statvfs"):
        st = os.statvfs(base)
        return st.f_bavail * st.f_frsize

    # Windows / others: fallback to shutil.disk_usage
    import shutil
    return shutil.disk_usage(str(base)).free


def ensure_even_dimensions(image_path: str | os.PathLike[str]) -> None:
    """Ensure the image at 'image_path' has dimensions divisible by 2, by resizing if necessary."""
    from PIL import Image
    fallback_logging_config()
    image_path = ensure_path_is_a_file(image_path)
    with Image.open(image_path) as img:
        width, height = img.size
        new_width  = width  if width  % 2 == 0 else width  - 1
        new_height = height if height % 2 == 0 else height - 1

        if new_width != width or new_height != height:
            try:
                img = img.resize((new_width, new_height), Image.LANCZOS)
                img.save(image_path)
                logging.info("Resized image to even dimensions: width = %d, height = %d", new_width, new_height)
            except OSError as e:
                raise ValueError(f"Could not resize image {image_path} to even dimensions: {e}") from e
        else:
            logging.info("Image already has even dimensions: width = %d, height = %d", width, height)


def human_bytesize(num: float | int, *, suffix: str = "B", si: bool = False, precision: int = 1,
                   space: bool = True, trim_trailing_zeros: bool = False, long_units: bool = False) -> str:
    """
    Formats a byte count into a human-readable string.

    Args:
        num:                 Size in bytes. Negative values are preserved with a leading minus.
        suffix:              Unit suffix appended after the prefix (defaults to "B"). If long_units is True and
                             suffix is "B", "bytes" is appended in the output. Otherwise, the suffix is appended to the long name.
        si:                  If True, use powers of 1000 with SI prefixes (k, M, G, … up to R, Q).
                             If False, use powers of 1024 with IEC prefixes (Ki, Mi, Gi, … up to Ri, Qi).
        precision:           Digits to show after the decimal point.
        space:               If True, inserts a space between the number and the unit (ignored when long_units is True).
        trim_trailing_zeros: If True, removes trailing zeros and any dangling decimal point.
        long_units:          If True, spell out unit names ("bytes", "kibibytes", … "quebibytes"/"quettabytes").

    Returns:
        A concise string such as "1.5KiB", "1.5 kB", or "1.5 megabytes" depending on options.
        Handles negative values with a leading minus sign and units up to "quebibytes" (2^100 = 1024^10 bytes) for IEC,
        or "quettabytes" (10^30 bytes) for SI.

    Raises:
        None.
    """
    step = 1000.0 if si else 1024.0
    symbols = (["", "k", "M", "G", "T", "P", "E", "Z", "Y", "R", "Q"]
               if si else ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi", "Yi", "Ri", "Qi"])
    long_prefixes = (["", "kilo", "mega", "giga", "tera", "peta",
                      "exa", "zetta", "yotta", "ronna", "quetta"]
                     if si else ["", "kibi", "mebi", "gibi", "tebi",
                                 "pebi", "exbi", "zebi", "yobi", "robi", "quebi"])

    sign = "-" if num < 0 else ""
    n = abs(float(num))
    i = 0
    while n >= step and i < len(symbols) - 1:
        n /= step
        i += 1

    s = f"{n:.{precision}f}"
    if trim_trailing_zeros:
        s = s.rstrip("0").rstrip(".")

    if long_units:
        long_name = long_prefixes[i]
        if suffix == "B":
            long_name += "bytes"
        else:
            long_name += suffix
        return f"{sign}{s} {long_name}"
    else:
        sep = " " if space else ""
        return f"{sign}{s}{sep}{symbols[i]}{suffix}"


def my_plural(n: int, word: str) -> str:
    """
    Return a pluralized version of `word` preceded by `n`.

    Behavior:
    - If the open-source `inflect` library is available, use it for pluralization.
    - Otherwise, fall back to a casefold()-based irregulars table, some uncountables,
      and a small set of morphological rules.

    Examples (fallback behavior):
        1 millennium -> "1 millennium"
        2 millennium -> "2 millennia"
        2 millenium  -> "2 millennia"   # (handles the common misspelling too)

    Args:
        n:    The quantity of the item.
        word: The singular form of the item.

    Raises:
        None.
    """
    if n == 1:
        return f"{n} {word}"

    # 1) Try the open-source 'inflect' library if present
    try:
        import inflect  # MIT-licensed, widely used for pluralization
        engine = getattr(my_plural, "_inflect_engine", None)
        if engine is None:
            engine = inflect.engine()
            setattr(my_plural, "_inflect_engine", engine)

        # plural_noun returns False when it can't/shouldn't pluralize
        plural = engine.plural_noun(word)
        if not plural:
            plural = engine.plural(word)
        if plural:
            return f"{n} {plural}"
    except Exception:
        # Fall through to custom logic if inflect isn't available or errors
        pass

    # 2) Fallback: irregular/uncountable lists (case-insensitive via casefold)
    irregulars = {
        # Common irregulars
        "child"      : "children",
        "person"     : "people",
        "man"        : "men",
        "woman"      : "women",
        "mouse"      : "mice",
        "goose"      : "geese",
        "tooth"      : "teeth",
        "foot"       : "feet",
        "ox"         : "oxen",

        # Classical/latin/greek
        "cactus"     : "cacti",
        "focus"      : "foci",
        "fungus"     : "fungi",
        "nucleus"    : "nuclei",
        "syllabus"   : "syllabi",
        "analysis"   : "analyses",
        "diagnosis"  : "diagnoses",
        "thesis"     : "theses",
        "crisis"     : "crises",
        "phenomenon" : "phenomena",
        "criterion"  : "criteria",
        "datum"      : "data",
        "index"      : "indices",
        "appendix"   : "appendices",
        "matrix"     : "matrices",
        "vertex"     : "vertices",
        "radius"     : "radii",
        "alumnus"    : "alumni",
        "alumna"     : "alumnae",
        "bacterium"  : "bacteria",
        "medium"     : "media",
        "millennium" : "millennia",
        "millenium"  : "millennia",  # handle common misspelling

        # Mixed/accepted forms — pick one
        "octopus"    : "octopuses",
        "platypus"   : "platypuses",
        "virus"      : "viruses",
    }

    uncountables = {
        "sheep", "fish", "deer", "series", "species", "aircraft", "moose",
        "bison", "salmon", "trout", "swine", "rice", "information", "equipment",
        "money", "news", "offspring", "fruit"
    }

    def _preserve_simple_case(src: str, target: str) -> str:
        """Match ALLCAPS or Titlecase of `src` onto `target`."""
        if src.isupper():
            return target.upper()
        if src.istitle():
            # Capitalize first letter only; keeps internal case of target
            return target[:1].upper() + target[1:]
        return target

    def _basic_rules(w: str) -> str:
        """Very small set of English pluralization rules."""
        lw = w.casefold()
        # Endings that usually take 'es'
        if lw.endswith(("s", "ss", "sh", "ch", "x", "z")):
            return w + "es"

        # consonant + 'y' -> 'ies'
        vowels = set("aeiou")
        if len(w) >= 2 and w[-1] in "yY" and w[-2].casefold() not in vowels:
            return w[:-1] + "ies"

        # Words ending with 'f' / 'fe' -> 'ves' (with some common exceptions)
        f_exceptions = {"roof", "chief", "chef", "belief", "cliff", "proof", "reef", "gulf", "brief"}
        if lw.endswith("fe") and lw[:-2] not in f_exceptions:
            return w[:-2] + "ves"
        if lw.endswith("f") and lw[:-1] not in f_exceptions:
            return w[:-1] + "ves"

        # Words ending with 'o' sometimes take 'es' (common subset)
        o_es = {"potato", "tomato", "hero", "echo", "torpedo", "veto"}
        if lw.endswith("o") and lw in o_es:
            return w + "es"

        # Default: just 's'
        return w + "s"

    key = word.casefold()

    if key in uncountables:
        plural_word = word  # unchanged
    elif key in irregulars:
        plural_word = _preserve_simple_case(word, irregulars[key])
    else:
        plural_word = _basic_rules(word)

    return f"{n} {plural_word}"


def human_timespan(timespan: int | float) -> str:
    """
    Format a time span in seconds into a human-readable string.
    Negative values are treated as absolute.

    Args:
        timespan: A float or int representing the time span in seconds.
    
    Returns:
        A human-readable string describing the time span, such as
        "1 year, 2 weeks, 3 days, 4 hours, 5 minutes and 6.789 seconds".
        If the timespan is zero, returns "0 seconds".
    
    Raises:
        None.
    """
    # Work in integer milliseconds to avoid float modulo issues
    total_ms = int(round(abs(float(timespan)) * 1000))
    if total_ms == 0:
        return "0 seconds"

    MS_PER_MINUTE =         60_000
    MS_PER_HOUR   =      3_600_000
    MS_PER_DAY    =     86_400_000
    MS_PER_WEEK   =    604_800_000
    MS_PER_YEAR   = 31_557_600_000  # 365.25 days

    components: list[str] = []

    years, rem   = divmod(total_ms, MS_PER_YEAR)
    weeks, rem   = divmod(rem,      MS_PER_WEEK)
    days,  rem   = divmod(rem,      MS_PER_DAY)
    hours, rem   = divmod(rem,      MS_PER_HOUR)
    minutes, rem = divmod(rem,      MS_PER_MINUTE)
    seconds = rem / 1000.0  # in [0, 60)

    if years:   components.append(my_plural(years,     "year"))
    if weeks:   components.append(my_plural(weeks,     "week"))
    if days:    components.append(my_plural(days,       "day"))
    if hours:   components.append(my_plural(hours,     "hour"))
    if minutes: components.append(my_plural(minutes, "minute"))
    if seconds:
        s = f"{seconds:.3f}".rstrip("0").rstrip(".")
        components.append(f"{s} second" + ("" if seconds == 1.0 else "s"))

    if len(components) == 1:
        return components[0]
    return ", ".join(components[:-1]) + " and " + components[-1]


def format_date_range(date1: dt.datetime, date2: dt.datetime | None = None) -> str:
    """
    Process a pair of datetime.datetime dates and produce a formatted date range string
    where each date looks like 'Jan  7, 2025'. If date2 is not provided, it is set to date1.

    Args:
        date1: The first date as a datetime.datetime object.
        date2: The second date as a datetime.datetime object. If None, defaults to date1.

    Returns:
        A formatted string representing the date range, such as 'Jan  7, 2025' or 'Jan  7 - Feb  3, 2025'.
        If both dates are the same, it returns just one date like 'Jan  7, 2025'.

    Raises:
        ValueError: If either date1 or date2 is not a datetime.datetime object.
    """
    import datetime as dt

    month_names = {
        1: 'Jan',  2: 'Feb',  3: 'Mar',  4: 'Apr',
        5: 'May',  6: 'Jun',  7: 'Jul',  8: 'Aug',
        9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'
    }

    # If date2 is not provided, set date2 to date1
    if date2 is None:
        date2 = date1

    # Make sure both dates are datetime.datetime objects
    if not isinstance(date1, dt.datetime) or not isinstance(date2, dt.datetime):
        raise ValueError(f"Both dates must be datetime.datetime objects, but date1 is {date1} with type {type(date1)} and date2 {date2} with type {type(date2)}.")

    # Ensure that the first date is earlier than the second.
    if date1 > date2:
        date1, date2 = date2, date1

    day1, day2     = date1.day, date2.day
    month1, month2 = month_names[date1.month], month_names[date2.month]
    year1, year2   = date1.year, date2.year

    if year1 == year2:
        if month1 == month2:
            if day1 == day2: return f"{month1} {day1:2d}, {year1}"
            else:            return f"{month1} {day1:2d} - {day2:2d}, {year1}"
        else:                return f"{month1} {day1:2d} - {month2} {day2:2d}, {year1}"
    else: return f"{month1} {day1:2d}, {year1} - {month2} {day2:2d}, {year2}"


_TIMESTAMP_PATTERN_RE: re.Pattern = re.compile(r"(\d{8}-\d{6}).pkl$")


def extract_timestamp(the_string: str) -> str | None:
    """Extract timestamp string (in format YYYYMMDD-HHMMSS) from the_string, or None if not found."""
    if (m := _TIMESTAMP_PATTERN_RE.search(the_string)):
        try:
            return m.group(1)
        except ValueError:
            return None
    return None


# Mapping of unit aliases (all in lowercase) to their equivalent in seconds
_UNIT_SECONDS = {
    **dict.fromkeys(['year', 'years', 'yr', 'yrs', 'calendar year', 'calendar years'],    31_556_952),  # Average calender year = 365.2425 days (accounting for leap years)
    **dict.fromkeys(['solar year', 'solar years', 'tropical year', 'tropical years'],     31_556_925.216),  # Average solar/tropical year = 365.24219 solar days = time for Earth to orbit the Sun once relative to the Sun/equinoxes
    **dict.fromkeys(['sidereal year', 'sidereal years'],                                  31_558_149.54),  # Sidereal year = 365.25636 days = time for Earth to orbit the Sun once relative to the "fixed" stars
    **dict.fromkeys(['month', 'months', 'mo', 'mos', 'calendar month', 'calendar months'], 2_629_746.0),  # Average calendar month = 30.436875 solar days
    **dict.fromkeys(['lunar month', 'lunar months', 'synodic month', 'synodic months'],    2_551_442.9),  # Average lunar month (synodic month) = 29.53 solar days
    **dict.fromkeys(['week', 'weeks', 'wk', 'wks'],                                          604_800.0),  # 7 solar days
    **dict.fromkeys(['day', 'days', 'd', 'solar day', 'solar days', 'ephemeris day', 'ephemeris days'], 86_400),  # 24 hours = time for Earth to rotate once relative to the Sun
    **dict.fromkeys(['sidereal day', 'sidereal days'],                                                  86_164.0905),  # 23 hours, 56 minutes, 4.1 seconds = time for Earth to rotate once relative to the "fixed" stars
    **dict.fromkeys(['hour',         'hours',   'hr',  'hrs'],          3600),
    **dict.fromkeys(['minute',       'minutes', 'min', 'mins'],           60),
    **dict.fromkeys(['second',       'seconds', 'sec', 'secs', 's'],    1.00),
    **dict.fromkeys(['decisecond',   'deciseconds',  'ds'],            1E-01),
    **dict.fromkeys(['centisecond',  'centiseconds', 'cs'],            1E-02),
    **dict.fromkeys(['millisecond',  'milliseconds', 'ms'],            1E-03),
    **dict.fromkeys(['microsecond',  'microseconds', 'us', 'μs'],      1E-06),
    **dict.fromkeys(['nanosecond',   'nanoseconds',  'ns'],            1E-09),
    **dict.fromkeys(['picosecond',   'picoseconds',  'ps'],            1E-12),
    **dict.fromkeys(['femtosecond',  'femtoseconds', 'fs'],            1E-15),
    **dict.fromkeys(['attosecond',   'attoseconds',  'as'],            1E-18),
    **dict.fromkeys(['zeptosecond',  'zeptoseconds', 'zs'],            1E-21),
    **dict.fromkeys(['yoctosecond',  'yoctoseconds', 'ys'],            1E-24),
    **dict.fromkeys(['planck time',  'planck times', 'planck', 'plancks', 'pt'], 5.391_247E-44),  # Planck time
    **dict.fromkeys(['decade',       'decades'],                                315_569_252.16),  #   10 solar years
    **dict.fromkeys(['century',      'centuries'],                            3_155_692_521.60),  #  100 solar years
    **dict.fromkeys(['millennium',   'millennia'],                           31_556_925_216.00),  # 1000 solar years
    **dict.fromkeys(['megayear',     'megayears', 'mya', 'myr'],         31_556_925_216_000.00),  # 1E06 solar years
    **dict.fromkeys(['gigayear',     'gigayears', 'gya', 'gyr'],     31_556_925_216_000_000.00),  # 1E09 solar years
    **dict.fromkeys(['terayear',     'terayears', 'tya', 'tyr'], 31_556_925_216_000_000_000.00),  # 1E12 solar years
    **dict.fromkeys(['fortnight',    'fortnights'],                               1_209_600.00),  # 2 weeks = 604_800 * 2 seconds
    **dict.fromkeys(['decasecond',   'decaseconds',   'das'], 1E01),
    **dict.fromkeys(['hectosecond',  'hectoseconds',  'hs'],  1E02),
    **dict.fromkeys(['kilosecond',   'kiloseconds',   'ks'],  1E03),
    **dict.fromkeys(['megasecond',   'megaseconds'],          1E06),  # no Ms because .casefold() would convert it to ms
    **dict.fromkeys(['gigasecond',   'gigaseconds',   'gs'],  1E09),
    **dict.fromkeys(['terasecond',   'teraseconds',   'ts'],  1E12),
    **dict.fromkeys(['petasecond',   'petaseconds'],          1E15),  # no Ps because .casefold() would convert it to ps
    **dict.fromkeys(['exasecond',    'exaseconds',    'es'],  1E18),
    **dict.fromkeys(['zettasecond',  'zettaseconds'],         1E21),  # no Zs because .casefold() would convert it to zs
    **dict.fromkeys(['yottasecond',  'yottaseconds'],         1E24),  # no Ys because .casefold() would convert it to ys
    **dict.fromkeys(['ronnasecond',  'ronnaseconds',  'rs'],  1E27),
    **dict.fromkeys(['quettasecond', 'quettaseconds', 'qs'],  1E30),
}


def seconds_in_unit(unit: str) -> float:
    """Return the number of seconds in a given time unit."""
    try:
        return _UNIT_SECONDS[unit.casefold()]
    except KeyError:
        raise ValueError(f"Unknown time unit: {unit!r}")


# Common US & UTC/GMT abbreviations → IANA zone names
_TZ_ABBREV_TO_ZONE: dict[str, str] = {
    "UTC"  : "UTC",
    "GMT"  : "Etc/GMT",
    "EST"  : "America/New_York",
    "EDT"  : "America/New_York",
    "CST"  : "America/Chicago",  # WARNING! "CST" can also mean China Standard Time (Asia/Shanghai, UTC+8), so use with caution!
    "CDT"  : "America/Chicago",
    "MST"  : "America/Denver",
    "MDT"  : "America/Denver",
    "PST"  : "America/Los_Angeles",
    "PDT"  : "America/Los_Angeles",
    "HST"  : "Pacific/Honolulu",
    "AKST" : "America/Anchorage",
    "AKDT" : "America/Anchorage",
    "AST"  : "America/Puerto_Rico",  # Atlantic Standard Time
    "ADT"  : "America/Puerto_Rico",  # Atlantic Daylight Time
    "NST"  : "America/St_Johns",     # Newfoundland Standard Time
    "NDT"  : "America/St_Johns",     # Newfoundland Daylight Time
    "BST"  : "Europe/London",        # British Summer Time
    "CET"  : "Europe/Berlin",        # Central European Time
    "CEST" : "Europe/Berlin",        # Central European Summer Time
    "EET"  : "Europe/Athens",        # Eastern European Time
    "EEST" : "Europe/Athens",        # Eastern European Summer Time
    "IST"  : "Asia/Kolkata",         # Indian Standard Time - WARNING! "IST" can also mean Irish Standard Time (Europe/Dublin, UTC+1), so use with caution!
    "JST"  : "Asia/Tokyo",           # Japan Standard Time
    "KST"  : "Asia/Seoul",           # Korea Standard Time
    "HKT"  : "Asia/Hong_Kong",       # Hong Kong Time
    "SGT"  : "Asia/Singapore",       # Singapore Time
    "AEST" : "Australia/Sydney",     # Australian Eastern Standard Time
    "AEDT" : "Australia/Sydney",     # Australian Eastern Daylight Time
    "ACST" : "Australia/Adelaide",   # Australian Central Standard Time
    "ACDT" : "Australia/Adelaide",   # Australian Central Daylight Time
    "AWST" : "Australia/Perth",      # Australian Western Standard Time
    "AWDT" : "Australia/Perth",      # Australian Western Daylight Time
    "NZT"  : "Pacific/Auckland",     # New Zealand Time
    "NZST" : "Pacific/Auckland",     # New Zealand Standard Time
    "NZDT" : "Pacific/Auckland",     # New Zealand Daylight Time
    "WET"  : "Europe/Lisbon",        # Western European Time
    "WEST" : "Europe/Lisbon",        # Western European Summer Time
    # …add any others you need
}

# Pre‐compile once for all calls.
_TZ_OFFSET_RE: re.Pattern = re.compile(r'''
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

    Args:
        tz_arg : A timezone string, a datetime.tzinfo object, or None.
    
    Returns:
        A datetime.tzinfo object representing the parsed timezone, or a string "Naive"
        if the input was "Naive".

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
_JD_MJD_SIMPLE_RE: re.Pattern  = re.compile(r"\s*(JD|MJD)?\s*[+-]?\d+(\.\d+)?\s*", re.IGNORECASE)
# This regex is used to capture the prefix (JD or MJD) and the value from a string that looks like a JD or MJD:
_JD_MJD_CAPTURE_RE: re.Pattern = re.compile(r"\s*(?P<prefix>JD|MJD)?\s*(?P<value>[+-]?\d+(?:\.\d+)?)\s*", re.IGNORECASE)
# This regex is used to check if a string has an explicit offset or Z at the end (indicating that the date should be converted by shifting the clock):
_OFFSET_IN_STR_RE: re.Pattern  = re.compile(r"(Z|[+-]\d{2}:\d{2}|[+-]\d{4})$")

# Enclose the type alias annotation in quotes because not all of these types have been imported yet.
AnyDateTimeType: TypeAlias = "str | float | int | np.datetime64 | pd.Timestamp | dt.datetime"


def _should_convert(given_date: AnyDateTimeType, format_str: str | None = None) -> bool:
    """Determine if the given date should be converted to a timezone (i.e. if the wall clock should be shifted) or if the timezone should just be attached without shifting the clock."""
    import datetime as dt

    # 1) Numbers, JD/MJD, decimal years, special keywords
    if isinstance(given_date, (int, float)) and not isinstance(given_date, bool):
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Given date is a number: %s, so it will be converted by shifting the clock", given_date)
        return True
    if isinstance(given_date, str):
        u = given_date.strip().upper()
        if u in ('J2000', 'UNIX', 'NOW'):
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Given date is a special keyword: %s, so it will be converted by shifting the clock", u)
            return True
        if format_str and format_str.upper() in ('JD', 'MJD'):
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Given date has a format_str: %s, so it will be converted by shifting the clock", format_str)
            return True
        if _JD_MJD_SIMPLE_RE.fullmatch(given_date):
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Given date is a JD/MJD: %s, so it will be converted by shifting the clock", given_date)
            return True
        # explicit offset or Z
        if _OFFSET_IN_STR_RE.search(given_date):
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Given date has an explicit offset or Z: %s, so it will be converted by shifting the clock", given_date)
            return True
    # 2) Any datetime/timestamp already aware
    if isinstance(given_date, dt.datetime) and given_date.tzinfo is not None:
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Given date is an aware datetime: %s, so it will be converted by shifting the clock", given_date)
        return True

    # Otherwise treat it as local‐time → attach only
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Given date is not a number, JD/MJD, or aware datetime: %s, so the timezone will be attached without shifting the clock", given_date)
    return False


def _finalize_datetime(parsed_dt: dt.datetime, original_input: AnyDateTimeType,
                       format_str: str | None, tz_arg: str | dt.tzinfo | None,
                       should_convert: bool | None = None) -> dt.datetime:
    """
    Finalize the datetime object by either converting it to the target timezone or just attaching the timezone without shifting the clock. The boolean argument 'should_convert' can override the default behavior, which is determined by the function _should_convert().

    Args:
        parsed_dt:      The datetime object that has been parsed from the original input.
        original_input: The original input that was used to parse the datetime.
        format_str:     The format string used to parse the datetime, if any.
        tz_arg:         The timezone argument, which can be a string or a datetime.tzinfo object.
        should_convert: A boolean indicating whether to convert the datetime to the specified timezone by shifting the clock (True) or just attaching the timezone without shifting (False). If None, the function will determine this based on the type of original_input and format_str.

    Returns:
        A datetime.datetime object in the specified timezone.
        If tz_arg is "Naive", the datetime will be returned without any timezone info.
        If should_convert is True, the datetime will be converted to the specified timezone by shifting the clock.
        If should_convert is False, the timezone will be attached to the datetime without shifting the clock.
        If should_convert is None, the function will determine whether to convert or not based on the type of original_input and format_str.

    Raises:
        ValueError: If the tz_arg is not a valid timezone string or tzinfo object.
        TypeError:  If the parsed_dt is not a datetime.datetime object.
    """
    if isinstance(tz_arg, str) and tz_arg.strip().upper() == 'NAIVE':
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Naive timezone requested, returning datetime %s without any timezone info", parsed_dt)
        return parsed_dt.replace(tzinfo=None)
    target_tz = parse_timezone(tz_arg)
    if should_convert is not False and (_should_convert(original_input, format_str) or should_convert is True):
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Converting datetime %s to timezone %s by shifting the clock", parsed_dt, target_tz)
        return parsed_dt.astimezone(target_tz)
    else:
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Attaching timezone %s to datetime %s without shifting the clock", target_tz, parsed_dt)
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
        'NOW' (case-insensitive) → current datetime
        strings in YYYY, YYYY-MM, YYYY-MM-DD, YYYY-MM-DDTHH:MM:SS, or other ISO8601 formats (e.g. '2002-10-18T07:00:00Z', '2002-10-18 07:00:00+00:00').
        If YYYY is provided, it will default to January 1st of that year at midnight.
        If YYYY-MM is provided, it will default to the first day of that month at midnight.
        If YYYY-MM-DD is provided, it will default to midnight on that day.
        fallback to dateutil.parser.parse for free-form strings ("18 Oct 2002", "March 5th, 2020", etc.)
        floats (e.g. 2002.29178082191777) or integer (e.g. 2002) → decimal year
        numpy.datetime64 objects (e.g. np.datetime64('2002-10-18T07:00:00'))
        pandas.Timestamp objects (e.g. pd.Timestamp('2002-10-18 07:00:00'))
        datetime.datetime objects (e.g. datetime.datetime(2002, 10, 18, 7, 0, 0))

    Args:
        given_date:     The date to parse, which can be a string, float, int, numpy.datetime64,
                        pandas.Timestamp, or datetime.datetime object.
        timezone:       A string or datetime.tzinfo object representing the timezone to convert
                        the datetime to. If None, defaults to UTC.
        format_str:     A string indicating the format of the date. If None, the function will
                        try to infer the format from the given_date.
        should_convert: A boolean indicating whether to convert the datetime to the specified
                        timezone by shifting the clock (True) or just attaching the timezone
                        without shifting (False). If None, the function will determine this
                        based on the type of given_date and format_str.
    
    Returns:
        datetime.datetime object in the specified timezone.
        Note that datetime.datetime objects cannot represent dates before 1 January 1, 0001 or after 31 December 9999.
        So dates outside this range will raise a ValueError. Future versions of this code may support a wider range of dates (like 44 BC, 44 BCE, etc.) using libraries like 'astropy.time': https://chatgpt.com/share/685c5157-5cac-8006-b68c-4a0731927a50
        However, this will require the function to return an 'astropy.time.Time' object instead of a 'datetime.datetime' object.

    Raises:
        ValueError:  If the given_date cannot be parsed into a datetime object, or if the timezone is invalid.
        TypeError:   If the given_date is not a string, float, int, numpy.datetime64, pandas.Timestamp, or datetime.datetime object.
        ImportError: If the 'jdcal' library is not installed and the given_date is a Julian Date or Modified Julian Date.
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
        m = _JD_MJD_CAPTURE_RE.fullmatch(given_date)
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
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Parsing date with format string: '%s' split into parts: %s", format_str, format_parts)
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

    raise ValueError(error_message + "\n".join(map(str, errors)) + "\nPlease check the input format and try again.")


def _coerce_log_mode(value: Any) -> int:
    """Accept old string values like 'INFO' (or '20') and return an int."""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        s = value.strip()
        # Handle numeric strings like "20"
        try:
            return int(s)
        except ValueError:
            pass
        # Handle level names like "INFO", "debug", etc. (case-insensitive)
        value_map = {'INFO'    : logging.INFO,
                    'DEBUG'    : logging.DEBUG,
                    'WARNING'  : logging.WARNING,
                    'WARN'     : logging.WARNING,
                    'ERROR'    : logging.ERROR,
                    'CRITICAL' : logging.CRITICAL}
        lvl = value_map.get(s.upper())
        # lvl = logging.getLevelName(s.upper())  # deprecated
        if isinstance(lvl, int):
            return lvl
    logging.warning("Unrecognized log_mode %r; defaulting to INFO", value)
    return logging.INFO


def _json_default(o: object) -> dict[str, str | list[Any] | dict[str, Any]]:
    """Custom JSON serializer for non-serializable objects."""
    if isinstance(o, Path):
        return {"__type__": "path", "value": str(o)}
    if isinstance(o, set):
        return {"__type__": "set", "value": list(o)}
    import argparse
    if isinstance(o, argparse.Namespace):
        return {"__type__": "namespace", "value": vars(o)}
    # Let json raise for anything else you haven't handled
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


def _json_object_hook(d: dict[str, Any]) -> object:
    """Custom JSON deserializer for non-serializable objects. Converts JSON objects back to their original types."""
    t = d.get("__type__")
    if t == "path":
        return Path(d["value"])  # Don't resolve() here; leave it to the caller
    if t == "set":
        return set(d["value"])
    if t == "namespace":
        import argparse
        return argparse.Namespace(**d["value"])
    return d


def save_options_to_json(options: Options) -> None:
    """
    Save the options object to a JSON file.
    
    Args:
        options: Options object containing:
            - script_dir:    Directory where the JSON file will be saved.
            - python_script: Name of the Python script (used in the JSON filename).
            - my_name:       Name of the current script (used in the JSON filename).
            - timestamp:     Current timestamp (used in the JSON filename).

    Returns:
        None - writes the options to a JSON file.
    
    Raises:
        IOError:    If there is an error writing to the file.
        ValueError: If the options object is invalid.
    """
    import json
    options.options_json_filepath = options.script_dir / f".{options.python_script.name}-{options.my_name}-last-used-on-{options.timestamp}.json"

    # Convert options to a dictionary and handle sets
    options_dict = options.__dict__.copy()

    # Ensure directory exists
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Ensuring directory exists: %s", options.options_json_filepath.parent)
    options.options_json_filepath.parent.mkdir(parents=True, exist_ok=True)

    # Write the dictionary to a JSON file (ensure_ascii=False to preserve non-ASCII characters)
    with open(options.options_json_filepath, 'w', encoding=DEFAULT_ENCODING) as json_file:
        json.dump(options_dict, json_file, indent=4, ensure_ascii=False, default=_json_default)
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Options saved to JSON file: %s", options.options_json_filepath)


def load_options_from_json(options: Options, json_file: str | os.PathLike[str]) -> Options | None:
    """
    Load the options object from a JSON file.
    
    Args:
        options:    An existing Options object (used for logging purposes).
        json_file:  Path to the JSON file to load.
    
    Returns:
        Options object loaded from the JSON file, or None if the file does not exist or cannot be read.
    
    Raises:
        IOError:    If there is an error reading the file.
        ValueError: If the JSON file is invalid or cannot be parsed.
    """
    import json
    import copy
    json_file = ensure_path_is_a_file(json_file)
    with open(json_file, 'r', encoding=DEFAULT_ENCODING) as file:
        options_dict = json.load(file, object_hook=_json_object_hook)

    # Backwards compatibility: coerce old string log levels to ints
    if "log_mode" in options_dict:
        options_dict["log_mode"] = _coerce_log_mode(options_dict["log_mode"])

    # Create a new Options object and set attributes from the dictionary
    options_FROM_JSON = copy.deepcopy(Options())  # Just in case.
    for key, value in options_dict.items():
        setattr(options_FROM_JSON, key, value)
    if not options.rawlog: logging.info("options loaded from %s", json_file)
    return options_FROM_JSON


def sci_exp(x: float | int, max_digits: int = 15) -> int:
    """Return floor(log10(|x|)), clamped to -max_digits for very small |x|.
    For x == 0, returns -max_digits.
    """
    import math
    if not isinstance(x, (int, float)) or isinstance(x, bool):
        raise TypeError("x must be an int or float (not bool)")
    if not math.isfinite(x):
        raise ValueError("x must be finite")
    if x == 0:
        return -max_digits
    exp = int(math.floor(math.log10(abs(x))))
    return max(exp, -max_digits)


def round_out(x: float, round_digits: int = 3, max_digits: int = 15) -> float:
    """
    Round a number away from zero (i.e. rounds up for x>0 and down for x<0) to
    the specified number of significant figures (defaults to 3).
    If the number is smaller than 10^(-max_digits), it will be returned as is.
    The max_digits parameter defaults to 15, but can be changed to a different value if needed.

    Args:
        x:             The number to round.
        round_digits:  The number of significant figures to round to (default is 3).
        max_digits:    The maximum number of digits to consider for very small numbers (default is 15).

    Returns:
        float: The rounded number, or the original number if it is smaller than 10^(-max_digits).
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

    Args:
        prompt:  The message to display before the choices.
        choices: A list of choices to present to the user.
        default: The default choice to return if the user presses Enter without inputting a choice.

    Returns:
        str : The selected choice from the list (or the default if provided).
    
    Raises:
        None: If the user input is invalid, it will keep prompting until a valid choice is made.
    """
    fallback_logging_config()

    logging.info(prompt)
    for i, choice in enumerate(choices, 1):
        logging.info("  %d) %s", i, choice)
    prompt = f"Select [1-{len(choices)}]"
    if default is not None:
        prompt += f" (default {default}): "
    else:
        prompt += ": "

    while True:
        ans = input(prompt).strip()
        if not ans and default:
            logging.info("No input provided, using default: %s", default)
            return default
        if ans.isdigit() and 1 <= int(ans) <= len(choices):
            logging.info("User selected choice %d: %s", int(ans), choices[int(ans)-1])
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
    might remove the dot which separates the filename from the extension.
    It attempts to recognize and remove extensions listed in all_known_extensions
    but this list is not exhaustive.

    Steps:
      1. Unicode → ASCII
      2. Recognize & remove common extensions (e.g. .txt, .fits, .tar.gz)
      3. Treat dots, underscores & whitespace as word separators
      4. Remove any character that isn't A-z, a–z, 0–9, dashes, or the separator
      5. Collapse runs of separators into a single one
      6. Trim separators from ends
      7. Optionally truncate to max_length (preserving word boundaries)
      8. If an extension was removed, append it back as the last step.

    Args:
        text:       Original filename or title
        sep:        Single-character separator (default: "_")
        max_length: If set, strongest‐effort truncate to this many chars

    Returns:
        A clean, filename-safe string.
    
    Raises:
        None: If the input text is None, it will return an empty string.
    """
    fallback_logging_config()  # Ensure logging is configured
    if not text:
        return ""
    # Normalize to ASCII
    try:
        import unidecode
        text = unidecode.unidecode(text)
    except ImportError:
        logging.warning("unidecode package not found, falling back to ASCII encoding.")
        # Fallback: encode to ASCII, ignore errors
        text = text.encode('ascii', 'ignore').decode('ascii')

    # List of common extensions to recognize and (temporarily) remove
    removed_ext = ""
    for ext in all_known_extensions:
        if text.casefold().endswith(ext):
            text = text[:-len(ext)]
            removed_ext = ext
            break

    # Replace common "word boundaries" with sep
    #    (dots, underscores, whitespace) but keep dashes
    #    e.g. "hello.world--foo_bar" → "hello world--foo bar"
    text = re.sub(r"[._\s]+", sep, text)

    # Remove anything but dashes, a–z, 0–9, or our sep
    allowed = f"-A-Za-z0-9{re.escape(sep)}"
    text = re.sub(fr"[^{allowed}]+", "", text)

    # Collapse runs of sep (e.g. "__" → "_")
    text = re.sub(fr"{re.escape(sep)}{{2,}}", sep, text)

    # Strip leading/trailing seps
    text = text.strip(sep)

    # Optionally truncate (try not to cut in middle of a word)
    if max_length is not None and len(text) > max_length:
        # cut at max_length, then drop a partial trailing token if any
        truncated = text[:max_length]
        # if the next char in original isn't sep and our chop landed mid-token, trim back to last sep
        if (len(text) > max_length and not truncated.endswith(sep) and sep in truncated):
            truncated = truncated.rsplit(sep, 1)[0]
        text = truncated

    # If an extension was removed, append it back
    text += removed_ext

    return text


def if_filepath_then_read(input_string_or_filepath: str | os.PathLike[str],
                          force_string: bool = False) -> str:
    """
    If 'input_string_or_filepath' is a file path, read its contents and return as a string. If not, return the input_string as is.

    Args:
        input_string_or_filepath: The source can be a file path or a string.
        force_string:             If True, treat 'input_string_or_filepath' as a string even if it looks like a file path.

    Returns:
        str : The contents of the file if input_string_or_filepath is a file path,
              or the input_string_or_filepath itself if it is not a file path.

    Raises:
        TypeError : If input_string is not a string or a file path, or if force_string is True but input_string_or_filepath is os.PathLike.
    """
    fallback_logging_config()
    # Is "input_string" a file path, and is "force_string" False?
    # If so, read the file contents.
    if force_string and isinstance(input_string_or_filepath, os.PathLike):
        raise TypeError(f"'input_string_or_filepath' was given as a file path ({input_string_or_filepath!r}) but 'force_string' is True, so it cannot be treated as a file path.")
    if not force_string and Path(input_string_or_filepath).is_file():
        file_path = Path(input_string_or_filepath)
        try:
            contents = my_fopen(file_path, suppress_errors=True)
            if not contents:
                logging.error("Could not read file: %s", file_path)
                return ""
            return contents
        except FileNotFoundError as e:
            logging.exception("File not found: %s", file_path)
        except PermissionError as e:
            logging.exception("Permission denied: %s", file_path)
        except UnicodeDecodeError as e:
            logging.exception("Could not decode %r.", file_path)
    else:  # Otherwise, treat "input_string" as a string.
        if not isinstance(input_string_or_filepath, str):
            raise TypeError(f"Expected 'input_string_or_filepath' to be a string or file path, got {type(input_string_or_filepath).__name__!r}")
        return input_string_or_filepath  # Just return the input string as is.


def compile_code(source_or_filepath: str | os.PathLike[str],
                 force_source: bool = False) -> bool:
    """
    Attempt to compile the given source code in 'exec' mode.
    If 'source_or_filepath' is a file path, read its contents first.

    Args:
        source_or_filepath: The source code string or file path to compile.
        force_source:       If True, treat 'source_or_filepath' as a source code string even if it looks like a file path.

    Returns:
        bool: True if compilation succeeds, False if it fails with a SyntaxError or other exception

    Raises:
        SyntaxError: If the source code has a syntax error, it will be logged and False is returned.
        TypeError:   If 'source_or_filepath' is not a string or a file path.
    """
    fallback_logging_config()
    # Read from file if source is a file path
    source = if_filepath_then_read(source_or_filepath, force_string=force_source)
    if source != source_or_filepath:
        file_path = Path(source_or_filepath).expanduser().resolve()
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


def _make_format_checker() -> Type[Any]:
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
                self.errors.append((node.__class__.__name__.casefold(), who, "no docstring",
                                    node.lineno))
                return

            expr = node.body[0]
            if not (isinstance(expr.value, ast.Constant) and isinstance(expr.value.value, str)):
                self.errors.append((node.__class__.__name__.casefold(), who, "no docstring",
                                    node.lineno))
                return

            # Recover the exact literal to verify triple-double-quote
            literal = ast.get_source_segment(self.source, expr.value) or ""
            first_line = literal.strip().splitlines()[0]
            if first_line.startswith("'''"):
                self.errors.append((node.__class__.__name__.casefold(), who,
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
                        self.errors.append((node.__class__.__name__.casefold(),
                                            who, "extra docstring", extra.lineno))

            # Check the docstring style
            self._check_docstring_style(node, who)

        def _check_docstring_style(self, node: ast.AST, who: str) -> None:
            """Dispatch to the style‑specific docstring checker."""
            if not self.doc_style or self.doc_style.casefold() == "none":
                return
            checker = {
                "Google"           : self._check_google_docstring,
                # "NumPy"              : self._check_numpy_docstring,
                # "reStructuredText" : self._check_rst_docstring,
            }.get(self.doc_style)

            if checker is not None:
                checker(node, who)

        def _check_google_docstring(self, node: ast.AST, who: str) -> None:
            """
            Very basic Google‑style docstring validator:
            - must have a 'Args:' and 'Returns:' section header
            - every non‑self arg must be listed under Parameters
            """
            doctype = "Google"
            # Get the cleaned docstring
            doc = ast.get_docstring(node)
            if not doc:
                return  # already flagged as missing

            lines = doc.splitlines()
            # Locate the section headers
            try:
                params_idx = next(i for i, L in enumerate(lines) if L.strip() == "Args:")
            except StopIteration:
                self.errors.append((node.__class__.__name__.casefold(), who,
                                    f"{doctype} docstring missing 'Args' section",
                                    node.lineno))
                return

            try:
                returns_idx = next(i for i, L in enumerate(lines) if L.strip() == "Returns:")
            except StopIteration:
                self.errors.append((node.__class__.__name__.casefold(), who,
                                    f"{doctype} docstring missing 'Returns' section",
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
                self.errors.append((node.__class__.__name__.casefold(), who,
                                    f"{doctype} docstring missing parameter(s): " + ", ".join(missing), node.lineno))


        def _check_numpy_docstring(self, node: ast.AST, who: str) -> None:
            """
            Very basic NumPy‑style docstring validator:
            - must have a 'Parameters' and 'Returns' section header
            - every non‑self arg must be listed under Parameters
            """
            doctype = "NumPy"
            # Get the cleaned docstring
            doc = ast.get_docstring(node)
            if not doc:
                return  # already flagged as missing

            lines = doc.splitlines()
            # Locate the section headers
            try:
                params_idx = next(i for i, L in enumerate(lines) if L.strip() == "Parameters")
            except StopIteration:
                self.errors.append((node.__class__.__name__.casefold(), who,
                                    f"{doctype} docstring missing 'Parameters' section",
                                    node.lineno))
                return

            try:
                returns_idx = next(i for i, L in enumerate(lines) if L.strip() == "Returns")
            except StopIteration:
                self.errors.append((node.__class__.__name__.casefold(), who,
                                    f"{doctype} docstring missing 'Returns' section",
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
                self.errors.append((node.__class__.__name__.casefold(), who,
                                    f"{doctype} docstring missing parameter(s): " + ", ".join(missing), node.lineno))

    return FormatChecker


FormatChecker = _make_format_checker()


def check_python_formatting(path: str | os.PathLike[str], diff_choice: int = 1) -> bool:
    """
    Reads a .py file at 'path' via my_fopen, makes sure it compiles, parses it with AST,
    prints any custom formatting violations to stdout,
    and asks the user to fix any backticks or curly quotes in the file. If the user quits, it returns False.

    Args:
        path:        The path to the Python file to check.
        diff_choice: How many context lines to show in the diff (0 = old-style diff, 1 = unified diff with 0 context lines, 2+ = unified diff with 'diff_choice - 1' context lines).
    
    Returns:
        bool: False if the user chose to quit during any replacement prompts, True otherwise.
    
    Raises:
        FileNotFoundError: If the specified file does not exist.
    """
    import ast
    fallback_logging_config()
    path = ensure_path_is_a_file(path)
    src = my_fopen(path)
    if src is False:
        logging.error("❌ Failed to open file: %s", path)
        return

    if compile_code(src):
        logging.info("✅ %s compiled successfully.", path)

    # Check for some characters that I personally dislike in Python source code:
    BACKTICK            = "\u0060"  # U+0060 "GRAVE ACCENT" (the backtick)
    LSQUOTE             = "\u2018"  # U+2018 "LEFT  SINGLE QUOTATION MARK" (curly apostrophe)
    RSQUOTE             = "\u2019"  # U+2019 "RIGHT SINGLE QUOTATION MARK" (curly apostrophe)
    LDQUOTE             = "\u201C"  # U+201C "LEFT  DOUBLE QUOTATION MARK"
    RDQUOTE             = "\u201D"  # U+201D "RIGHT DOUBLE QUOTATION MARK"
    HORIZONTAL_ELLIPSIS = "\u2026"  # U+2026 "HORIZONTAL ELLIPSIS" (three closely spaced periods)

    if BACKTICK in src:
        logging.warning("File %s contains the backtick character (%r). Use straight quotation marks (') instead.", path, BACKTICK)
        if not ask_and_replace(old_str=BACKTICK, new_str="'", path=path, label='backtick',
                               diff_choice=diff_choice,
                               description=f"Replace backtick ({BACKTICK}) with straight apostrophe (')"):
            return False
    if LSQUOTE in src or RSQUOTE in src:
        logging.warning("File %s contains curly single quotation marks (%r or %r). Use straight apostrophes (') instead.", path, LSQUOTE, RSQUOTE)
        if not ask_and_replace(old_str=LSQUOTE, new_str="'", path=path, label='left-curly-apostrophe',
                               diff_choice=diff_choice,
                               description=f"Replace left curly apostrophe ({LSQUOTE}) with straight apostrophe (')"):
            return False
        if not ask_and_replace(old_str=RSQUOTE, new_str="'", path=path, label='right-curly-apostrophe',
                               diff_choice=diff_choice,
                               description=f"Replace right curly apostrophe ({RSQUOTE}) with straight apostrophe (')"):
            return False
    if LDQUOTE in src or RDQUOTE in src:
        logging.warning('File %s contains curly double quotation marks (%r or %r). Use straight quotation marks (") instead.', path, LDQUOTE, RDQUOTE)
        if not ask_and_replace(old_str=LDQUOTE, new_str='"', path=path,
                               label='left-curly-quotation-mark',
                               diff_choice=diff_choice,
                               description=f'Replace left curly double quotation mark ({LDQUOTE}) with straight double quotation mark (")'):
            return False
        if not ask_and_replace(old_str=RDQUOTE, new_str='"', path=path, label='right-curly-quotation-mark',
                               diff_choice=diff_choice,
                               description=f'Replace right curly double quotation mark ({RDQUOTE}) with straight double quotation mark (")'):
            return False
    if HORIZONTAL_ELLIPSIS in src:
        logging.warning("File %s contains the horizontal ellipsis character (%r). Use three periods (...) instead.", path, HORIZONTAL_ELLIPSIS)
        if not ask_and_replace(old_str=HORIZONTAL_ELLIPSIS, new_str='...', path=path,
                               label='horizontal-ellipsis', diff_choice=diff_choice,
                               description=f"Replace horizontal ellipsis ({HORIZONTAL_ELLIPSIS}) with three periods (...)"):
            return False

    try:
        tree = ast.parse(src, path)
    except SyntaxError:
        logging.exception("❌ %s contains a syntax error.", path)
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


def run_flake8(path: str | os.PathLike[str], ignore_codes: list[str] = [],
               max_line_length: int = 100) -> flake8.Report:
    """
    Run Flake8 on 'path', but:
      - only flag E501 if a line exceeds 'max_line_length',
      - ignore whatever codes are in 'ignore_codes'.

    Args:
        path:            The path to the Python file to check.
        ignore_codes:    A list of Flake8 error/warning codes to ignore.
        max_line_length: The (custom) maximum allowed line length for E501 checks.
    
    Returns:
        flake8.Report : The Flake8 report object containing the results.
    
    Raises:
        FileNotFoundError: If the specified file does not exist.
    """
    import io
    from collections import defaultdict
    from flake8.api import legacy as flake8
    fallback_logging_config()
    path = ensure_path_is_a_file(path)
    style_guide = flake8.get_style_guide(max_line_length=max_line_length, ignore=ignore_codes)
    report = style_guide.check_files([path])
    if report.total_errors == 0:
        logging.info("✅ No Flake8 violations found in %s.", path)
        return report
    logging.error("Found %d total violations in %s:", report.total_errors, path)
    for stat in report.get_statistics(""):
        logging.error("  %s", stat)

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


def _gather_flake8_issues(path: str | os.PathLike[str], ignore_codes: list[str] = [],
                          max_line_length: int = 100) -> dict[str, str]:
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


def _gather_via_cli(path: str | os.PathLike[str], max_line_length: int,
                    ignore_codes: list[str]) -> dict[str, str]:
    """Use the flake8 CLI to gather codes and descriptions."""
    import subprocess
    path = ensure_path_is_a_file(path)
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


def _gather_via_app(path: str | os.PathLike[str], max_line_length: int,
                    ignore_codes: list[str]) -> dict[str, str]:
    """Use the flake8 Application API to gather codes and descriptions."""
    from flake8.main.application import Application
    from flake8.formatting.base import BaseFormatter
    from flake8.violation import Violation
    path = ensure_path_is_a_file(path)

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
        logging.warning("autopep8 not found or failed.", exc_info=True)
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
    
    Args:
        orig:            The original string.
        new:             The modified string.
        unchanged_color: The color to use for unchanged parts.
        added_color:     The color to use for added parts.
        deleted_color:   The color to use for deleted parts.
    
    Returns:
        A tuple of (old_highlighted, new_highlighted) strings.

    Raises:
        None.
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


def my_diff(orig_text: str, changed_text: str, orig_path: str | os.PathLike[str],
            changed_path: str | os.PathLike[str] | None = None,
            diff_choice: int = 1, changed_color: str = ANSI_CYAN,
            deleted_color: str = ANSI_RED, added_color: str = ANSI_YELLOW) -> None:
    """
    Show a diff between 'orig_text' and 'changed_text' in the console,
    highlighting character-level changes within changed lines.

    Args:
        orig_text:      Original text to compare against.
        changed_text:   Proposed changes to the original text.
        orig_path:      Path to the original file.
        changed_path:   Optional path to the changed file (if different).
        diff_choice:    How many context lines to show in the diff (0 = old-style diff, 1 = unified diff with 0 context lines, 2+ = unified diff with 'diff_choice - 1' context lines).
        changed_color:  Color to use for unchanged characters in the changed lines in the diff (default ANSI_CYAN).
        deleted_color:  Color to use for the deleted characters in orig lines (default ANSI_YELLOW).
        added_color:    Color to use for the added characters in changed lines (default ANSI_RED).
    
    Returns:
        None: Prints the diff to the console.
    
    Raises:
        None.
    """
    import difflib
    fallback_logging_config(rawlog=True)
    orig_path = Path(orig_path).expanduser().resolve()
    if not changed_path:
        changed_path = orig_path
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("At the top of the function %s(), diff_choice=%s", return_method_name(), diff_choice)
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
                        unchanged_color=changed_color,  # this is confusing but correct. "The unchanged parts in the changed line"
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
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Using old-style diff for %s with %d original and %d fixed lines.", orig_path, len(orig_lines), len(changed_lines))
        orig_lineno = 1
        new_lineno  = 1
        for line in difflib.Differ().compare(orig_lines, changed_lines):
            tag, body = line[:2], line[2:].rstrip("\n")
            if tag == "  ":    # context line
                # end of any previous mini‑hunk
                process_hunk()
                flush_removed(orig_lineno)
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
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Using unified diff for %s with %d original and %d fixed lines.", orig_path, len(orig_lines), len(changed_lines))
        ctx  = max(diff_choice - 1, 0)
        diff = difflib.unified_diff(
            orig_lines, changed_lines,
            fromfile=os.fspath(orig_path), tofile=os.fspath(changed_path),
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
        logging.error("Unsupported diff_choice = %d. Must be a non-negative integer.", diff_choice)


def is_python_script(path: str | os.PathLike[str]) -> bool:
    """
    Return True if 'path' looks like a Python script:
      1. It's a file which ends in .py or .pyw
      2. Or it is executable AND its first line is a python shebang
    
    Args:
        path: The file path to check.

    Returns:
        bool: True if the path is a Python script, False otherwise.

    Raises:
        IsADirectoryError: If the path is a directory.
        FileNotFoundError: If the file is not found.
        PermissionError:   If the file is not accessible due to permission issues.
    """
    import stat
    path = Path(path)
    if not path.is_file():
        return False

    # Common extensions
    if path.suffix.casefold() in python_extensions:
        return True

    # No-extension scripts: check for executable bit + python shebang
    try:
        st = path.stat()
    except OSError:
        return False

    # Must be a regular file and executable by owner/group/other
    if not stat.S_ISREG(st.st_mode) or not (st.st_mode & (stat.S_IXUSR|stat.S_IXGRP|stat.S_IXOTH)):
        return False

    # Try to read the first line and look for a python shebang
    first_line = my_fopen(path, suppress_errors=True, rawlog=False, numlines=1)
    if not first_line:
        return False
    return bool(re.match(r'#!.*\bpython[0-9.]*\b', first_line))


def diff_and_confirm(orig_text: str, changed_text: str, path: str | os.PathLike[str], label: str = "",
                     skip_compile: bool = False, diff_choice: int = 1,
                     changed_color: str = ANSI_CYAN, deleted_color: str = ANSI_RED,
                     added_color: str = ANSI_YELLOW, the_fix: str = "", description: str = "") -> bool:
    """
    Show a unified diff of orig_text → changed_text with a number of context lines
    (determined by 'diff_choice') around each hunk, log using 'label' and 'description', then prompt.
    If the user confirms, overwrite 'path' with changed_text and return True.
    If the user chooses to quit, log a message and return False.

    Args:
        orig_text:     Original text to compare against.
        changed_text:  Proposed changes to the original text.
        path:          Path to the file being modified.
        label:         A short label for the issue being fixed (default "").
        skip_compile:  If True, do not try to compile the changed text before writing (default False).
        diff_choice:   How many context lines to show in the diff (0 = old-style diff, 1 = unified diff with 0 context lines, 2+ = unified diff with 'diff_choice - 1' context lines) (default 1).
        changed_color: Color to use for unchanged characters in the changed lines in the diff (default ANSI_CYAN).
        deleted_color: Color to use for the deleted characters in orig lines (default ANSI_YELLOW).
        added_color:   Color to use for the added characters in changed lines (default ANSI_GREEN).
        the_fix:       A string describing the fix being applied (e.g. "autopep8", "manual edit") (default "").
        description:   A longer description of the issue being fixed (default "").

    Returns:
        bool: False if the user chose to quit; True otherwise.
    
    Raises:
        FileNotFoundError: If the specified file does not exist.
        ValueError: If the specified path is not a file. The function which raises this exception is my_fopen().
    """
    fallback_logging_config()
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("At the top of the function %s(), diff_choice=%s", return_method_name(), diff_choice)
    path = ensure_path_is_a_file(path)
    my_diff(orig_text, changed_text, path, diff_choice=diff_choice,
            changed_color=changed_color, deleted_color=deleted_color, added_color=added_color)
    label_str = f"{ANSI_RED}{label}{ANSI_RESET}" if label     else ""
    fix_str   = f" using {the_fix}"              if the_fix   else ""
    subject   = f"{label_str} "                  if label_str else ""
    logging.info("End of proposed %schanges to %s%s.", subject, path, fix_str)
    if description:
        prefix = f"{label_str}: "                if label_str else ""
        logging.info(f"{prefix}{ANSI_YELLOW}{description}{ANSI_RESET}")
    ans = input("Apply these changes? [y/N/q] ").strip().casefold()
    if ans in ("y", "yes"):
        # If the user hasn't chosen to skip compilation and this is a Python script,
        # try to compile the changed text before writing it. If compilation fails, abort the write.
        if not skip_compile and is_python_script(path) and not compile_code(changed_text):
            logging.error(f"{ANSI_RED}Failed to compile the changed python script. Aborting write.{ANSI_RESET}")
            return False  # Don't write if it won't compile, and don't continue.
        path.write_text(changed_text, encoding=DEFAULT_ENCODING)
        if the_fix:
            logging.info(f"{ANSI_GREEN}Applied {the_fix} to {path}{ANSI_RESET}")
        else:
            logging.info(f"{ANSI_GREEN}Applied changes to {path}{ANSI_RESET}")
    elif ans in ("q", "quit", "exit"):
        logging.info(f"{ANSI_YELLOW}Exiting without further changes.{ANSI_RESET}")
        return False
    else:
        logging.info(f"{ANSI_YELLOW}Skipped writing changes.{ANSI_RESET}")
    return True


def ask_and_autopep8(path: str | os.PathLike[str], code: str,
                     description: str = "", diff_choice: int = 1,
                     changed_color: str = ANSI_CYAN, deleted_color: str = ANSI_RED,
                     added_color: str = ANSI_YELLOW) -> bool:
    """
    Prompt the user about fixing ALL occurrences of 'code' in 'path',
    and if yes, apply autopep8.fix_file with --select=code.
    The fix will be applied without saving, and the user will be shown a diff
    of the changes before saving to the file.

    Args:
        path:          The path to the file to modify.
        code:          The specific PEP 8 violation code to fix.
        description:   A description of the issue being fixed (default "").
        diff_choice:   How many context lines to show in the diff (0 = old-style diff, 1 = unified diff with 0 context lines, 2+ = unified diff with 'diff_choice - 1' context lines) (default 1).
        changed_color: Color to use for unchanged characters in the changed lines in the diff (default ANSI_CYAN).
        deleted_color: Color to use for the deleted characters in orig lines (default ANSI_YELLOW).
        added_color:   Color to use for the added characters in changed lines (default ANSI_GREEN).

    Returns:
        bool: True if the user wants to continue, False if they want to quit.
    
    Raises:
        FileNotFoundError: If the specified file does not exist.
        ValueError: If the specified path is not a file. The function which raises this exception is autopep8.fix_file().
    """
    import autopep8
    fallback_logging_config()
    path = ensure_path_is_a_file(path)
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("At the top of the function %s(), diff_choice=%s", return_method_name(), diff_choice)
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
        logging.info("No changes for %s in %s using %s.", code, path, the_fix)
        return True
    if not isinstance(diff_choice, int) or diff_choice < 0:
        logging.error("Invalid diff_choice=%d. Must be a non-negative integer.", diff_choice)
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


def ask_and_replace(old_str: str, new_str: str, path: str | os.PathLike[str],  label: str = "",
                    diff_choice: int = 1, description: str = "",
                    changed_color: str = ANSI_CYAN, deleted_color: str = ANSI_RED,
                    added_color: str = ANSI_YELLOW, skip_compile: bool = False) -> bool:
    """
    Read 'path', do orig.replace(old, new), then show a diff and ask to confirm.

    Args:
        old_str:       Old string to search for.
        new_str:       New string to replace the old string.
        path:          Path to the file being modified.
        label:         A short label for the issue being fixed (default "").
        skip_compile:  If True, do not try to compile the changed text before writing (default False).
        diff_choice:   How many context lines to show in the diff (0 = old-style diff, 1 = unified diff with 0 context lines, 2+ = unified diff with 'diff_choice - 1' context lines) (default 1).
        changed_color: Color to use for unchanged characters in the changed lines in the diff (default ANSI_CYAN).
        deleted_color: Color to use for the deleted characters in orig lines (default ANSI_YELLOW).
        added_color:   Color to use for the added characters in changed lines (default ANSI_GREEN).
        the_fix:       A string describing the fix being applied (e.g. "autopep8", "manual edit") (default "").
        description:   A longer description of the issue being fixed (default "").

    Returns:
        False if the user chose to quit; True otherwise.

    Raises:
        IsADirectoryError: If the path is a directory.
        FileNotFoundError: If the file is not found.
        PermissionError: If the file is not accessible due to permission issues.
    """
    fallback_logging_config()
    path = ensure_path_is_a_file(path)
    orig_text = my_fopen(path)
    changed_text = orig_text.replace(old_str, new_str)
    if changed_text == orig_text:
        if label:
            logging.info("No occurrences of %s in %s.", label, path)
        else:
            logging.info("No occurrences of '%s' in %s.", old_str, path)
        return True
    the_fix = f"replace '{old_str}' with '{new_str}'"
    return diff_and_confirm(orig_text, changed_text, path, label=label, diff_choice=diff_choice,
                            changed_color=changed_color, deleted_color=deleted_color, added_color=added_color,
                            skip_compile=skip_compile, the_fix=the_fix, description=description)


def _validate_glob_pattern(pattern: str) -> None:
    """Basic validation for glob pattern (non-empty string)."""
    if not isinstance(pattern, str) or not pattern.strip():
        raise ValueError("glob_pattern must be a non-empty string.")


def _resolve_dir(dir_arg: str | None) -> Path:
    """Resolve the directory from the command line argument."""
    if dir_arg:
        p = Path(dir_arg).expanduser().resolve()
    else:
        p = Path.cwd()
    if not p.exists():
        raise FileNotFoundError(f"Directory does not exist: {p}")
    if not p.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {p}")
    return p


def _collect_files(root: Path, pattern: str, recursive: bool) -> list[Path]:
    """Collect files matching the glob pattern from root."""
    from collections.abc import Iterable
    search_iter: Iterable[Path]
    if recursive:
        search_iter = root.rglob(pattern)
    else:
        search_iter = root.glob(pattern)

    files = [p for p in search_iter if p.is_file()]
    return files


def multireplace(options: Options) -> None:
    """
    Perform a multi-file replace operation.

    Args:
        options: The parsed command-line options. Contains:
            - old_str: The text to be replaced in the files.
            - new_str: The text to replace the old_str.
            - glob_pattern: Glob pattern of files to edit.
            - dir: Directory to search in.
            - recursive: Whether to search recursively in subdirectories.

    Returns:
        None. Modifies files in place if the user confirms the changes.

    Raises:
        ValueError:         If the glob pattern is invalid.
        FileNotFoundError:  If the specified directory does not exist.
        NotADirectoryError: If the specified path is not a directory.
    """
    fallback_logging_config()
    try:
        _validate_glob_pattern(options.args.glob_pattern)
    except Exception as e:
        logging.error(f"Invalid glob pattern: {e}")
        sys.exit(2)

    try:
        dir = _resolve_dir(options.args.dir)
    except Exception as e:
        logging.error(str(e))
        sys.exit(2)

    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Directory: %s", dir)
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Glob pattern: %s", options.args.glob_pattern)
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Recursive: %s", options.args.recursive)

    files = _collect_files(dir, options.args.glob_pattern, options.args.recursive)

    if not files:
        logging.warning("No files matched the given pattern.")
        return

    logging.info("Found %d file(s) to process:", len(files))
    num_files  = len(files)
    max_digits = len(str(num_files))
    for i, f in enumerate(files, start=1):
        logging.info(f"{i:>{max_digits}}/{num_files}: {f}")

    logging.info("==========================================")
    for f in files:
        logging.info("Processing: %s", f)
        try:
            if not ask_and_replace(old_str=options.args.old_str, new_str=options.args.new_str, path=str(f)):
                break
        except KeyboardInterrupt:
            logging.warning("Interrupted by user.")
            sys.exit(130)
        except Exception as e:
            logging.error(f"Error processing {f}: {e}")

    logging.info("Done.")


def interactive_flake8(path: str | os.PathLike[str], diff_choice: int = 1,
                       ignore_codes: list[str] = [], max_line_length: int = 100,
                       changed_color: str = ANSI_CYAN, deleted_color: str = ANSI_RED,
                       added_color: str = ANSI_YELLOW) -> None:
    """
    1) Run the flake8 API for summary counts.
    2) Shell out to flake8 CLI once to harvest one description per code.
    3) For each code, ask the user; on "yes", call autopep8 to fix only that code.

    Args:
        path:            Path to the Python file to check.
        diff_choice:     How many context lines to show in the diff (0 = old-style diff,
                         1  = unified diff with 0 context lines,
                         2+ = unified diff with 'diff_choice - 1' context lines).
        ignore_codes:    List of Flake8 codes to ignore (default: empty list).
        max_line_length: Maximum line length for E501 (default: 100).
        changed_color:   Color for unchanged characters in changed lines (default: ANSI_CYAN).
        deleted_color:   Color for deleted characters in original lines (default: ANSI_RED).
        added_color:     Color for added characters in changed lines (default: ANSI_YELLOW).
    """
    fallback_logging_config()
    path = ensure_path_is_a_file(path)
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("At the top of the function %s(), diff_choice=%s", return_method_name(), diff_choice)
    if not run_flake8(path, ignore_codes=ignore_codes, max_line_length=max_line_length):
        logging.info("No flake8 errors—nothing to do.")
        return
    codes = _gather_flake8_issues(path, ignore_codes=ignore_codes, max_line_length=max_line_length)
    fixable_codes = get_autopep8_fixable_codes()
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Autopep8 can fix these codes: %s", fixable_codes)
    for code, desc in codes.items():
        if code not in fixable_codes:
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Skipping %s: no autopep8 fixer", code)
            continue
        logging.info("\n→ %s: %s", ANSI_RED + code + ANSI_RESET, ANSI_YELLOW + desc + ANSI_RESET)
        if not ask_and_autopep8(path, code, desc, diff_choice=diff_choice,
                                changed_color=changed_color, deleted_color=deleted_color, added_color=added_color):
            break
    logging.info("%sDone. Re-running flake8 to confirm fixes...%s", ANSI_GREEN, ANSI_RESET)
    run_flake8(path, ignore_codes=ignore_codes, max_line_length=max_line_length)


# - Use {str(univ_defs_dir)!r} so Windows backslashes are safely escaped in the string literal.
# - Double the braces around `univ_defs_dir` in the f-string to keep them literal in the written file.
UNIV_DEFS_SYS_PATH_SCRIPT: str = f'''# Auto-generated helper: ensure the univ_defs directory is on sys.path
import sys
from pathlib import Path

univ_defs_dir = Path({str(Path(__file__).parent.resolve())!r}).resolve()
if not univ_defs_dir.is_dir():
    raise FileNotFoundError(f"Expected univ_defs_dir to be a directory: {{univ_defs_dir}}")
if str(univ_defs_dir) not in sys.path:
    sys.path.append(str(univ_defs_dir))
'''

MYDIFF_SCRIPT: str = r'''from __future__ import annotations
import sys
import argparse
import logging
from pathlib import Path
import univ_defs_sys_path_script  # Appends sys.path with the location of univ_defs.py
import univ_defs as ud

__version__: str = "0.1.0"


class Options:
    """Class that has all global options in one place."""

    def __init__(self) -> None:
        """Initialize the Options class with default values."""
        self.my_name:  str = Path(sys.argv[0]).stem  # The invoked name of this script without the .py extension
        self.log_mode: int = logging.INFO  # Use the -debug command line argument to change to DEBUG.
        self.args: argparse.Namespace | None = None
        self.default_dir: Path = Path.cwd()  # Default to current working directory


def parse_arguments(options: Options) -> None:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Diff two files using ud.my_diff().")
    parser.add_argument("orig_path", type=str, help="Path to original file.")
    parser.add_argument("changed_path", type=str, help="Path to changed file.")
    parser.add_argument("--diff_choice", type=int, default=1,
                        help="0 = old-style diff, 1 = unified diff with 0 context lines, "
                             "2+ = unified diff with 'diff_choice - 1' context lines")
    parser.add_argument("--changed_color", type=str, default=ud.ANSI_CYAN,
                        help="Color for unchanged characters in changed lines (default: ANSI_CYAN)")
    parser.add_argument("--deleted_color", type=str, default=ud.ANSI_RED,
                        help="Color for deleted characters in original lines (default: ANSI_RED)")
    parser.add_argument("--added_color", type=str, default=ud.ANSI_GREEN,
                        help="Color for added characters in changed lines (default: ANSI_GREEN)")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-debug", "--debug", action="store_true",
                        help="Enable DEBUG logging.")
    options.args = parser.parse_args()
    if options.args.debug:
        options.log_mode = logging.DEBUG


def main() -> None:
    """Main function."""
    options = Options()
    parse_arguments(options)
    memory_handler = ud.configure_logging(options.my_name, log_level=options.log_mode,
                                          rawlog=True)
    orig_text    = ud.my_fopen(options.args.orig_path)
    changed_text = ud.my_fopen(options.args.changed_path)
    if orig_text is False:
        logging.error(f"Failed to read original file: {options.args.orig_path}")
        return
    if changed_text is False:
        logging.error(f"Failed to read changed file: {options.args.changed_path}")
        return
    if orig_text == changed_text:
        return  # Standard diff would show no changes
    ud.my_diff(orig_text, changed_text, options.args.orig_path,
               changed_path=options.args.changed_path, diff_choice=options.args.diff_choice,
               changed_color=options.args.changed_color, deleted_color=options.args.deleted_color,
               added_color=options.args.added_color)
    ud.print_all_errors(memory_handler)
    logging.shutdown()


if __name__ == "__main__":
    main()
'''

MYAUDIT_SCRIPT: str = r'''from __future__ import annotations
import sys
import argparse
import logging
from pathlib import Path

import univ_defs_sys_path_script  # Appends sys.path with the location of univ_defs.py
import univ_defs as ud

__version__: str = "0.1.0"


class Options:
    """Class that has all global options in one place."""

    def __init__(self) -> None:
        """Initialize the Options class with default values."""
        self.my_name:  str = Path(sys.argv[0]).stem  # The invoked name of this script without the .py extension
        self.log_mode: int = logging.INFO  # Use the -debug command line argument to change to DEBUG.
        self.args: argparse.Namespace | None = None
        self.default_dir: Path = Path.cwd()  # Default to current working directory


def parse_arguments(options: Options) -> None:
    """Parse command-line arguments."""
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
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-debug", "--debug", action="store_true",
                        help="Enable DEBUG logging.")
    options.args = parser.parse_args()
    if options.args.debug:
        options.log_mode = logging.DEBUG


def main() -> None:
    """Main function."""
    options = Options()
    parse_arguments(options)
    memory_handler = ud.configure_logging(options.my_name, log_level=options.log_mode,
                                          rawlog=True)
    if not ud.check_python_formatting(options.args.filepath, diff_choice=options.args.diff_choice):
        return
    ud.interactive_flake8(options.args.filepath, diff_choice=options.args.diff_choice,
                          ignore_codes=ud.IGNORED_CODES, max_line_length=1000,
                          changed_color=options.args.changed_color, deleted_color=options.args.deleted_color,
                          added_color=options.args.added_color)
    ud.print_all_errors(memory_handler)
    logging.shutdown()


if __name__ == "__main__":
    main()
'''

MULTIREPLACE_SCRIPT: str = r'''from __future__ import annotations
import sys
import argparse
import logging
from pathlib import Path

import univ_defs_sys_path_script  # Appends sys.path with the location of univ_defs.py
import univ_defs as ud

__version__: str = "0.1.0"


class Options:
    """Class that has all global options in one place."""

    def __init__(self) -> None:
        """Initialize the Options class with default values."""
        self.my_name:  str = Path(sys.argv[0]).stem  # The invoked name of this script without the .py extension
        self.log_mode: int = logging.INFO  # Use the -debug command line argument to change to DEBUG.
        self.args: argparse.Namespace | None = None
        self.default_glob_pattern: str = "*"
        self.default_dir: Path = Path.cwd()  # Default to current working directory


def parse_arguments(options: Options) -> None:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Find files by glob and call ud.ask_and_replace() on each until it returns False.")
    parser.add_argument("old_str",
                        help="The text to be replaced in the files.")
    parser.add_argument("new_str",
                        help="The text to replace the old_str.")
    parser.add_argument("glob_pattern", nargs="?", default=options.default_glob_pattern,
                        help=f'Glob pattern of files to edit (default: "{options.default_glob_pattern}"). Example: "*.py"')
    parser.add_argument("-dir", "-d", default=options.default_dir,
                        help=f"Directory to search in (defaults to current working directory: {options.default_dir}).")
    parser.add_argument("-recursive", "-r", action="store_true",
                        help="Search recursively in subdirectories.")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-debug", "--debug", action="store_true",
                        help="Enable DEBUG logging.")
    options.args = parser.parse_args()
    if options.args.debug:
        options.log_mode = logging.DEBUG


def main() -> None:
    """Main function."""
    options = Options()
    parse_arguments(options)
    memory_handler = ud.configure_logging(options.my_name, log_level=options.log_mode,
                                          rawlog=True)
    ud.multireplace(options)
    ud.print_all_errors(memory_handler)
    logging.shutdown()


if __name__ == "__main__":
    main()
'''

TREEVIEW_SCRIPT: str = r'''#!/usr/bin/env python3
from __future__ import annotations

import sys
import argparse
import logging
from pathlib import Path

import univ_defs_sys_path_script  # Appends sys.path with the location of univ_defs.py
import univ_defs as ud

__version__: str = "0.1.0"


class Options:
    """Class that has all global options in one place."""

    def __init__(self) -> None:
        """Initialize the Options class with default values."""
        self.my_name:  str = Path(sys.argv[0]).stem  # The invoked name of this script without the .py extension
        self.log_mode: int = logging.INFO  # Use the -debug command line argument to change to DEBUG.
        self.args: argparse.Namespace | None = None
        self.default_dir: Path = Path.cwd()  # Default to current working directory


def parse_arguments(options: Options) -> None:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Print a tree view of the specified directory.")
    parser.add_argument("dir", default=options.default_dir, nargs="?",
                        help=f"Directory to search in (defaults to current working directory: {options.default_dir}).")
    parser.add_argument("-no_colors", action="store_true",
                        help="Do not use colors in the output.")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-debug", "--debug", action="store_true",
                        help="Enable DEBUG logging.")
    options.args = parser.parse_args()
    if options.args.debug:
        options.log_mode = logging.DEBUG


def main() -> None:
    """Main function."""
    options = Options()
    parse_arguments(options)
    memory_handler = ud.configure_logging(options.my_name, log_level=options.log_mode,
                                          rawlog=True)
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Directory: %s", options.args.dir)
    ud.treeview_new_files(options.args.dir, use_colors=not options.args.no_colors)
    ud.print_all_errors(memory_handler)
    logging.shutdown()


if __name__ == "__main__":
    main()
'''

PRINTALL_SCRIPT: str = r'''from __future__ import annotations

import os
import sys
import argparse
import io
import logging
import re
from pathlib import Path
from typing import Iterable

import tokenize  # stdlib

__version__: str = "0.1.0"


class Options():
    """Class that has all global options in one place."""

    def __init__(self) -> None:
        """Initialize the Options class with default values."""
        self.my_name:  str = Path(sys.argv[0]).stem  # The invoked name of this script without the extension
        self.default_exclude_dirs: list[str] = [".git", "__pycache__", ".venv", "venv", "build", "dist"]
        self.log_mode: int = logging.INFO  # Use -debug to change to logging.DEBUG.
        self.args: argparse.Namespace | None = None


def parse_arguments(options: Options) -> None:
    """
    Parse command-line arguments.
    """
    p = argparse.ArgumentParser(description="Search Python files and print full logical statements that match a pattern.")
    p.add_argument("paths", nargs="+", type=Path,  # parse as Path at the boundary
                   help="Files and/or directories to search.")
    p.add_argument("-p", "--pattern", required=True, help="Search pattern (string or regex).")
    p.add_argument("-E", "--regex", action="store_true",
                   help="Treat the pattern as a regular expression.")
    p.add_argument("-i", "--ignore-case", action="store_true", help="Case-insensitive match.")
    p.add_argument("-n", "--line-numbers", action="store_true",
                   help="Show line numbers in output blocks.")
    p.add_argument("-r", "--recursive", action="store_true", help="Recurse into directories.")
    p.add_argument("--no-glob", action="store_true",
                   help="Do not automatically filter for *.py inside directories.")
    p.add_argument("--exclude-dir", action="append",
                   default=options.default_exclude_dirs,
                   help=f"Directory name to exclude (can be given multiple times). Default: {options.default_exclude_dirs}")
    p.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("-debug", "--debug", action="store_true", help="Enable debug logging.")
    options.args = p.parse_args()
    if options.args.debug:
        options.log_mode = logging.DEBUG


def _is_excluded(path: Path, excluded: set[str]) -> bool:
    """Return True if any ancestor directory name is in the excluded set."""
    # Only compare directory names (Path.name); do not do string-prefix checks.
    return any(parent.name in excluded for parent in path.parents)


def iter_files(paths: Iterable[str | os.PathLike[str]],
               recursive: bool,
               exclude_dirs: list[str],
               only_py: bool) -> Iterable[Path]:
    """
    Yield files from given paths, respecting recursion and directory excludes.

    Parameters that represent paths accept str | os.PathLike[str] at the boundary.
    Returned paths are pathlib.Path instances.
    """
    excluded = set(exclude_dirs)
    pattern = "*.py" if only_py else "*"

    for raw in paths:
        base = Path(raw)

        if base.is_dir():
            if recursive:
                # Prefer Path.rglob for recursion (portable across 3.9+).
                for f in base.rglob(pattern):
                    if f.is_file() and not _is_excluded(f, excluded):
                        yield f
            else:
                for f in base.glob(pattern):
                    if f.is_file() and not _is_excluded(f, excluded):
                        yield f
        else:
            # Single file (or non-existent); yield if it meets filters.
            if base.is_file() and (not only_py or base.suffix == ".py") and not _is_excluded(base, excluded):
                yield base


def _statement_spans(src: str) -> list[tuple[int, int]]:
    """Return list of (start_line, end_line) for each logical statement in the source."""
    reader = io.StringIO(src).readline
    spans: list[tuple[int, int]] = []
    depth = 0
    start_line: int | None = None

    for tok in tokenize.generate_tokens(reader):
        tok_type, tok_str, start, end, _ = tok

        # establish start at first meaningful token of a statement
        if start_line is None and tok_type not in (tokenize.NL, tokenize.COMMENT,
                                                   tokenize.INDENT, tokenize.DEDENT,
                                                   tokenize.ENDMARKER):
            start_line = start[0]

        if tok_type == tokenize.OP:
            if tok_str in "([{":
                depth += 1
            elif tok_str in ")]}":
                depth -= 1
            elif tok_str == ";" and depth == 0 and start_line is not None:
                spans.append((start_line, start[0]))
                start_line = None
                continue

        if tok_type == tokenize.NEWLINE and depth == 0:
            if start_line is not None:
                spans.append((start_line, end[0]))
            start_line = None

        if tok_type == tokenize.ENDMARKER:
            break

    return spans


def _mask_strings_and_comments(src: str) -> str:
    """Return source with STRING and COMMENT contents replaced by spaces (preserving positions)."""
    lines = src.splitlines(keepends=True)
    matrix = [list(line) for line in lines]
    reader = io.StringIO(src).readline
    for tok in tokenize.generate_tokens(reader):
        tok_type, _tok_str, start, end, _ = tok
        if tok_type in (tokenize.STRING, tokenize.COMMENT):
            (sr, sc), (er, ec) = start, end
            # mask all full lines covered by the token
            for r in range(sr - 1, er - 1):
                cstart = sc if r == sr - 1 else 0
                for c in range(cstart, len(matrix[r])):
                    if matrix[r][c] != "\n":
                        matrix[r][c] = " "
            # final line (partial)
            r = er - 1
            if 0 <= r < len(matrix):
                cstart = 0 if sr != er else sc
                for c in range(cstart, ec):
                    if matrix[r][c] != "\n":
                        matrix[r][c] = " "
    return "".join("".join(row) for row in matrix)


def _merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping or adjacent spans."""
    if not spans:
        return []
    spans = sorted(spans)
    merged: list[list[int]] = [[spans[0][0], spans[0][1]]]
    for s, e in spans[1:]:
        last = merged[-1]
        if s <= last[1] + 1:
            last[1] = max(last[1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def _extract_blocks(src: str, spans: list[tuple[int, int]], show_line_numbers: bool) -> list[str]:
    """Return pretty-printed blocks for each span."""
    lines = src.splitlines()
    if show_line_numbers:
        max_line = max((e for _, e in spans), default=0)
        width = len(str(max_line))
    blocks: list[str] = []
    for s, e in spans:
        segment = lines[s - 1:e]
        if show_line_numbers:
            segment = [f"{i:>{width}} | {line}" for i, line in zip(range(s, e + 1), segment)]
        blocks.append("\n".join(segment))
    return blocks


def search_file(path: str | os.PathLike[str],
                pattern: str, *,
                regex: bool,
                ignore_case: bool,
                show_line_numbers: bool) -> list[str]:
    """Return matching blocks for a single file."""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = p.read_text(encoding="latin-1")
    except Exception as ex:
        logging.warning("Skipping %s (%s)", os.fspath(p), ex)  # convert at presentation boundary
        return []

    masked = _mask_strings_and_comments(text)
    flags = re.IGNORECASE if ignore_case else 0
    pat = re.compile(pattern if regex else re.escape(pattern), flags)

    # lines that contain a match (in code, not in strings/comments)
    hit_lines: set[int] = set()
    for m in pat.finditer(masked):
        before = masked[:m.start()]
        line = before.count("\n") + 1
        hit_lines.add(line)

    if not hit_lines:
        return []

    # map lines to statement spans
    spans = _statement_spans(text)
    line_to_span: dict[int, tuple[int, int]] = {}
    for s, e in spans:
        for ln in range(s, e + 1):
            line_to_span[ln] = (s, e)

    chosen: list[tuple[int, int]] = []
    for ln in sorted(hit_lines):
        sp = line_to_span.get(ln)
        if sp:
            chosen.append(sp)

    chosen = _merge_spans(chosen)
    return _extract_blocks(text, chosen, show_line_numbers)


def main() -> None:
    """
    Main function.
    """
    options = Options()
    parse_arguments(options)
    logging.basicConfig(level=options.log_mode,
                        format="%(asctime)s - %(levelname)s - %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S")

    any_hits = False

    for file in iter_files(options.args.paths, options.args.recursive,
                           options.args.exclude_dir, only_py=not options.args.no_glob):
        results = search_file(file, options.args.pattern, regex=options.args.regex,
                              ignore_case=options.args.ignore_case,
                              show_line_numbers=options.args.line_numbers)
        if results:
            any_hits = True
            print(f"# {os.fspath(file)}")
            for block in results:
                print(block)
                print()  # extra newline between blocks

    if not any_hits:
        logging.info("No matches found.")

    logging.shutdown()


if __name__ == "__main__":
    main()
'''

SETUP_CARTOPY_SCRIPT: str = r'''import os
import matplotlib.pyplot as plt
import cartopy
cartopy.config['data_dir'] = os.getenv('CARTOPY_DATA_DIR', cartopy.config.get('data_dir'))

fig, ax = plt.subplots(subplot_kw={'projection': cartopy.crs.PlateCarree()})
ax.coastlines('110m')    # Explicitly specify resolution to ensure pre-loading
ax.add_feature(cartopy.feature.OCEAN)  # Example color; adjust as needed
ax.add_feature(cartopy.feature.LAND)   # Example color; adjust as needed

# Force feature download
plt.savefig('cartopy_test_map.png')
os.remove('cartopy_test_map.png')
'''


def verify_script(options: Options, thepath: str | os.PathLike[str], thescript: str) -> None:
    """
    Ensure that `thepath` exists and contains exactly `thescript`.
    - If `thepath` does not exist or is not a file, it will be created and populated.
    - If it exists but its contents differ, it will be overwritten.
    - Otherwise, nothing happens.
    """
    # Check if it exists and is a file
    thepath = Path(thepath).expanduser().resolve()
    if not thepath.is_file():
        if thepath.is_dir():
            if not options.rawlog:
                logging.error(f"Expected a file at {thepath}, but it is a directory.")
            return
        thepath.write_text(thescript, encoding=DEFAULT_ENCODING)
        if not options.rawlog:
            logging.info("Creating %s with the audit script.", thepath)
        return

    # It is a file: read and compare
    existing = thepath.read_text(encoding=DEFAULT_ENCODING)
    # Overwrite if different
    if existing != thescript:
        if not options.rawlog:
            logging.info("Contents of %s differ from the audit script in %s as follows:", thepath, __file__)
            my_diff(existing, thescript, thepath, diff_choice=1)
            logging.info("Overwriting %s with the audit script.", thepath)
        thepath.write_text(thescript, encoding=DEFAULT_ENCODING)


def decode_utf8(raw_bytes: bytes, path: str = "input string") -> str | None:
    """
    If the file at `path` is valid UTF-8 without lone C1 controls,
    return the decoded string. Otherwise, return None.
    """
    fallback_logging_config()
    try:
        text = raw_bytes.decode('utf-8', errors='strict')
    except UnicodeDecodeError:
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("%s failed to decode as UTF‑8.", path)
        return None
    if any(0x0080 <= ord(ch) <= 0x009F for ch in text):
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("%s contains lone C1 controls, not valid UTF-8.", path)
        return None
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("%s decoded as valid UTF‑8.", path)
    return text


def decode_cp1252(raw_bytes: bytes, path: str = "input string") -> str | None:
    """
    Attempt to decode CP1252 bytes and return as a string.
    If it fails, return None.
    """
    fallback_logging_config()
    try:
        text = raw_bytes.decode('cp1252', errors='strict')
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("%s decoded as valid CP1252.", path)
        return text
    except UnicodeDecodeError:
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("%s failed to decode as CP1252.", path, exc_info=True)
        return None


def contains_mojibake(text: str) -> bool:
    """Use ftfy.badness.is_bad() to detect any likely mojibake in the text."""
    import ftfy
    fallback_logging_config()
    try:
        mojibake_present = ftfy.badness.is_bad(text)
    except Exception: # Catch any unexpected errors from ftfy without crashing
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Failed to check for mojibake.", exc_info=True)
        mojibake_present = False
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Mojibake present: %s", mojibake_present)
    # I HAVEN'T TRIED THIS NEXT LINE, BUT IT MIGHT CAUSE FEWER FALSE POSITIVES:
    # return ftfy.badness(text) > 1
    return mojibake_present


def fix_text(current_text: str, path: str | os.PathLike[str], raw_bytes: bytes) -> str | None:
    """
    Fix mojibake in a string using ftfy.fix_encoding().
    """
    import ftfy
    fallback_logging_config()
    path = ensure_path_is_a_file(path)
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Checking %s for mojibake.", path)
    if not contains_mojibake(current_text):
        return None
    try:
        fixed = ftfy.fix_encoding(current_text)
    except Exception:  # Catch any unexpected errors from ftfy without crashing
        logging.error("Failed to fix mojibake in %s.", path, exc_info=True)
        return None
    # If logging level is set to DEBUG, show my diff of original vs fixed:
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        try:
            # Mangle the original string to simulate browser encoding issues:
            mangled_original = raw_bytes.decode('cp1252', errors='replace')
            my_diff(mangled_original, fixed, path)
        except Exception:  # Catch any unexpected errors from decoding but don't crash.
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Could not simulate browser mangling in %s.", path, exc_info=True)
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


def my_atomic_write(filepath: str | Path | os.PathLike[str], data: str | bytes | bytearray,
                    write_mode: Literal['w', 'a'], encoding: str = DEFAULT_ENCODING,
                    lock_timeout: float = None,  # seconds to wait for lock (None = forever)
                   ) -> None:
    """
    Atomically write `data` to `filepath` with an advisory lock.

    - If write_mode='a' and file exists, data is appended.
    - If write_mode='a' and file does *not* exist, file is created.
    - A `.lock` file beside `filepath` prevents concurrent writers.

    Args:
        filepath:     Path to the file to write.
        data:         Data to write (str or bytes).
        write_mode:   'w' for overwrite, 'a' for append.
        encoding:     Encoding to use for text data (default: DEFAULT_ENCODING).
        lock_timeout: Maximum time to wait for the lock (default: None, meaning wait indefinitely).

    Returns:
        None: The file is written atomically.

    Raises:
        RuntimeError: If the lock cannot be acquired within the specified timeout.
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


def fix_mojibake(filepath: str | os.PathLike[str], make_backup: bool = True,
                 dry_run: bool = False) -> None:
    """
    Fix mojibake in a text file, recoding from CP1252 to UTF-8 if necessary.
    If the file is already valid UTF-8, it will only fix mojibake.
    """
    import datetime as dt
    fallback_logging_config()
    filepath = Path(filepath)
    if not filepath.is_file():
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
        logging.info("✔ Fixed mojibake: %s", filepath)

    # If the text is from an HTML file, ensure it has a UTF-8 meta tag
    if filepath.suffix.casefold() in ('.html','.htm'):
        current_text = ensure_utf8_meta(current_text)

    # If we have fixed the text, write it back
    if current_text != original_text:
        if dry_run:
            logging.info("Dry run: would write changes to %s", filepath)
        else:
            if make_backup:
                current_datetime = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
                backup_path = f"{filepath}_{current_datetime}.bak"
                try:
                    filepath.rename(backup_path)
                    logging.info("Backup created: %s", backup_path)
                except OSError:
                    logging.exception("Failed to create backup for %s.", filepath)
                    return
            my_atomic_write(filepath, current_text, 'w', encoding='utf-8')
            logging.info("✔ Successfully fixed mojibake in %s", filepath)


def treeview_new_files(directory:      str | os.PathLike[str],
                       last_file_path: str | os.PathLike[str] | None = None,
                       last_mtime: float | None = None, maxlines: int = 0,
                       use_colors: bool = True, print_root: bool = True,
                       prefix: str = '', is_last: bool = True, level: int = 0,
                       state: dict = None, probe_only: bool = False) -> bool:
    """
    Recursively scan the directory, print the contents of files newer than last_file_path (if provided- if so store its modification date in last_mtime). Return True if any relevant files are found.

    Args:
        directory:      The directory to scan.
        last_file_path: The optional path to a chosen file. Only files newer than this will be printed.
        last_mtime:     The modification time of the last_file_path. If None, all files will be
                        considered.
        maxlines:       The maximum number of lines to read from each file. 0 means don't read at all,
                        -1 means read all lines, otherwise read up to maxlines (default 0).
        use_colors:     Whether to use ANSI color codes in the output (default True).
        print_root:     If True, print the root directory name (default True).
        prefix:         The prefix to use for logging output (default '').
        is_last:        Whether this is the last item in the current level (default True).
        level:          The current recursion level (default 0).
        state:          A dictionary to maintain state across recursive calls (default None).
        probe_only:     If True, do not print file contents, just check for existence of relevant
                        files (default False).

    Returns:
        bool: True if any relevant files are found or the directory itself is newer than last_mtime,
              False otherwise.

    Raises:
        None: Catches exceptions, logs an error and returns False if the directory is not a valid
              directory or does not exist.
    """
    import datetime as dt
    fallback_logging_config(rawlog=True)

    directory = Path(directory).resolve()
    if not directory.exists():
        logging.error(f"{prefix}└── [Directory does not exist: {directory}]")
        return False
    if not directory.is_dir():
        logging.error(f"{prefix}└── [Not a directory: {directory}]")
        return False

    if last_file_path is None:
        last_mtime = 0
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("%sNo last file path provided, considering all files.", prefix)
    else:
        last_file_path = Path(last_file_path).expanduser().resolve()
        if not last_file_path.exists():
            logging.error("%s└── [Last file path does not exist: %s]", prefix, last_file_path)
            return False
        last_mtime = last_file_path.stat().st_mtime
        last_mtime_readable = dt.datetime.fromtimestamp(last_mtime).strftime('%Y-%m-%d %H:%M:%S')
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("%sLast file path: %s (mtime: %s)", prefix, last_file_path, last_mtime_readable)

    if use_colors:
        reset_color = ANSI_RESET
        dir_color   = ANSI_CYAN
    else:
        reset_color = ''
        dir_color   = ''    

    # Get the modification time of the directory itself
    dir_mtime = directory.stat().st_mtime
    current_is_new = dir_mtime > (last_mtime or 0)

    if state is None:
        state = {'excluded_dirs'   : {'__pycache__'},
                 'already_printed' : set(),
                 'my_filepath'     : Path(__file__).expanduser().resolve()}
    already_printed = state['already_printed']
    excluded_dirs   = state['excluded_dirs']
    my_filepath     = state['my_filepath']

    if not probe_only:
        already_printed.add(directory)
    
    has_relevant_files = False  # Flag to indicate if current directory has relevant files

    try:
        entries = sorted(directory.iterdir(), key=lambda e: e.name.casefold())
    except PermissionError:
        logging.error(f"{prefix}└── [Permission Denied]")
        return False

    # Filter out entries that should be skipped at the directory level
    entries = [
        entry for entry in entries
        if not (
            (entry.is_file() and (
                entry == last_file_path or
                entry == my_filepath    or
                entry.name.startswith('.')
            )) or
            (entry.is_dir() and entry.name in excluded_dirs) or
            (entry.is_dir() and entry.expanduser().resolve() in already_printed)
        )
    ]

    # Sort entries: directories first, then files, case-insensitive
    entries = sorted(entries, key=lambda e: (not e.is_dir(), e.name.casefold()))

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
                entry,
                last_file_path=last_file_path,
                last_mtime=last_mtime,
                maxlines=maxlines,
                use_colors=use_colors,      # use_colors doesn't matter in probe mode
                prefix=prefix,              # prefix doesn’t matter in probe mode
                is_last=False,              # ignored in probe mode
                level=level + 1,
                state=state,
                probe_only=True             # probe mode: do not print contents
            )
            # Consider the subdirectory’s own mtime
            sub_is_new = entry.stat().st_mtime > last_mtime
            if sub_has_relevant or sub_is_new:
                subdirectories.append(entry)
            if sub_has_relevant:
                has_relevant_files = True

    # Sort subdirectories and relevant entries by name, case-insensitive
    subdirectories.sort(  key=lambda p: p.name.casefold())
    relevant_entries.sort(key=lambda p: p.name.casefold())

    should_show = has_relevant_files or current_is_new
    if probe_only:
        return should_show

    if should_show:
        if level > 0:
            # Print the directory name with a connector only if it's not the root directory
            connector = '└── ' if is_last else '├── '
            logging.info(f"{prefix}{connector}{dir_color}{directory.name}/{reset_color}")

            # Update the prefix for child entries
            child_prefix = prefix + ('    ' if is_last else '│   ')
        else:
            # For root level, do not print the directory name unless print_root is True
            child_prefix = prefix
            if print_root:
                # Print the root directory name with a connector
                logging.info(f"{dir_color}{directory.name}/{reset_color}")


        # Print subdirectories first
        printable_subdirs = [
            d for d in subdirectories
            if d.name not in excluded_dirs and d.expanduser().resolve() not in already_printed
        ]
        for i, subdir in enumerate(printable_subdirs):
            is_sub_last = (i == len(printable_subdirs) - 1) and (len(relevant_entries) == 0)
            # Only scan the subdirectory if it isn't excluded
            if subdir.name not in excluded_dirs and subdir.expanduser().resolve() not in already_printed:
                treeview_new_files(subdir, last_file_path=last_file_path, last_mtime=last_mtime,
                                   maxlines=maxlines, use_colors=use_colors, prefix=child_prefix,
                                   is_last=is_sub_last, level=level + 1)

        # Print relevant files next
        for i, file_entry in enumerate(relevant_entries):
            # Determine if this is the last file to adjust connector
            is_file_last = (i == len(relevant_entries) - 1)
            file_connector = '└── ' if is_file_last else '├── '
            contents_str = f"{file_entry.name} contents:" if maxlines != 0 else f"{file_entry.name}"
            logging.info(f"{child_prefix}{file_connector}{contents_str}")
            try:
                if maxlines != 0:  # Only open if not disabled
                    with open(file_entry, 'r', encoding=DEFAULT_ENCODING) as f:
                        if maxlines > 0:
                            # Read only up to maxlines
                            lines = []
                            for i, line in enumerate(f):
                                if i >= maxlines:
                                    break
                                lines.append(line.rstrip("\n"))
                        else:  # maxlines == -1 → read all
                            lines = [line.rstrip("\n") for line in f]
                    # Indent file contents for better readability
                    indented_contents = '\n'.join(f"{child_prefix}    {line}" for line in lines)
                    logging.info(indented_contents)
            except Exception:  # Catch any unexpected errors from reading the file without crashing.
                logging.exception(f"{child_prefix}    Error reading '{file_entry}'.")
            if maxlines != 0:  # Add an empty line for separation, but only if printing contents
                logging.info("")

    return should_show


def check_if_command_exists(command: str) -> bool:
    """
    Check if a command exists on the system.
    
    Args:
        command: The command to check.
    
    Returns:
        bool: True if the command exists, False otherwise.
    """
    import subprocess
    return subprocess.run(['which', command], capture_output=True).returncode == 0


def open_terminal_and_run_command(the_command: str, close_after: bool = False,
                                  maximize_window: bool = False) -> None:
    """Open a GNOME terminal, source ~/.bashrc (via bash -i), run the_command,
    and optionally close or keep the window open. Optionally, maximize it."""
    import subprocess
    fallback_logging_config()
    logging.info("Opening terminal and running '%s'...", the_command)
    terminal_args = ['gnome-terminal']
    if maximize_window:
        # either of these works; here we use both for clarity
        terminal_args += ['--window', '--maximize']
    # Now tell bash to run the command, then exit or hand off to an interactive shell
    if close_after:
        bash_cmd = f'{the_command}; exit'
    else:
        bash_cmd = f'{the_command}; exec bash'
    terminal_args += ['--', 'bash', '-ic', bash_cmd]
    subprocess.Popen(terminal_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


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


def is_process_running(process_name: str) -> bool:
    """Check if a process with the given name is running."""
    import subprocess
    fallback_logging_config()
    try:
        the_command = ['pgrep', '-f', process_name]
        results = subprocess.run(the_command, capture_output=True, text=True)
        if results.returncode != 0:
            return False
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Error occurred: {e}")
        return False


def start_only_one_instance(process_name: str) -> None:
    """Start a process, but only if it's not already running."""
    import subprocess
    import time
    fallback_logging_config()
    if not is_process_running(process_name):
        logging.info("Starting %s...", process_name)
        subprocess.Popen([process_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Wait briefly to ensure the command is processed
        time.sleep(1)
    else:
        logging.info("%s is already running.", process_name)


def open_filemanager_with_dirs(directories: list[str | os.PathLike[str]]) -> None:
    """
    Open the file manager with the specified directories.
    Note: Most file managers don't support multiple tabs via command line, so open separate windows.
    """
    import subprocess
    import time
    fallback_logging_config()
    if not sys.platform.startswith('linux'):
        logging.error(f"The function {return_method_name()} is only implemented for Linux systems.")
        return
    logging.info("Opening file manager with specified directories...")
    for directory in directories:
        directory = Path(directory)
        if not directory.is_absolute():
            logging.error(f"Directory {directory} is not an absolute path. Skipping.")
            continue
        if not directory.is_dir():
            logging.error(f"Directory {directory} is not a valid directory. Skipping.")
            continue
        if not directory.exists():
            logging.error(f"Directory {directory} does not exist. Skipping.")
            continue
        subprocess.Popen(['nemo', directory], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Optional: Wait briefly between opening directories
        time.sleep(0.5)


def detect_country(force_wtfismyip: bool = False) -> str | None:
    """
    Detect the country of the IP address using ipinfo.io service.
    If the request fails, it falls back to wtfismyip.com service.

    Args:
        force_wtfismyip: If True, always use wtfismyip.com
    
    Returns:
        The country name as a string, or None if detection fails.
    
    Raises:
        ValueError: If the IPINFO_API_TOKEN environment variable is not set.
    """
    import subprocess
    import requests
    import json
    thecountryname = None
    if not force_wtfismyip:
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("force_wtfismyip=%s.", force_wtfismyip)
        try:
            if 'IPINFO_API_TOKEN' in os.environ:
                ipinfo_access_token = os.environ['IPINFO_API_TOKEN']
            else:
                raise ValueError("IPINFO_API_TOKEN environment variable is not set. If you don't have one, you can sign up for a free account here: https://ipinfo.io/signup")

            logging.info("Attempting to detect country using IPinfo...")
            # Uncomment the following lines if you want to use the ipinfo library instead of curl
            # import ipinfo
            # handler = ipinfo.getHandler(ipinfo_access_token,
            #                             request_options={'timeout': ipinfo_timeout_seconds})
            # details = handler.getDetails()
            # logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("IPinfo DETAILS:\n%s", details)
            # thecountryname = details.country
            the_command = ["curl", f"https://api.ipinfo.io/lite/8.8.8.8?token={ipinfo_access_token}"]
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Running command: %s", ' '.join(the_command))
            result = subprocess.run(the_command, capture_output=True,
                                    text=True, timeout=5)
            if result.returncode != 0:
                logging.error("curl command failed with return code %d", result.returncode)
                raise Exception("Curl command failed")
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("curl output: %s", result.stdout)
            dct = json.loads(result.stdout)
            thecountryname = dct.get('country', '')
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Detected country from curl: %s", thecountryname)
        except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
            logging.warning("IPinfo exception: %s\nFalling back to wtfismyip.com.", e)

    if not thecountryname:
        try:
            resp = requests.get("https://wtfismyip.com/json", timeout=5)
            resp.raise_for_status()
            dct = resp.json()
            thecountryname = dct.get("YourFuckingCountry", "")
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Detailed results: %s", dct)
        except requests.exceptions.RequestException as e:
            logging.error("Country detection failed (network error): %s", e)
            return None
        except (ValueError, KeyError) as e:
            logging.error("Country detection failed (bad response): %s", e)
            return None

    return thecountryname.strip() if thecountryname else None


def set_system_volume(percent: int, tolerance: int = 1,
                      change_mute: Literal['mute', 'unmute'] | None = None,
                      force_pactl: bool = False) -> None:
    """
    Set the system volume to a specific level.
    On Linux, this function will:
    Try to set the PulseAudio default sink volume to `percent`% via pulsectl,
    verify it, and if that fails, fall back to pactl.

    Args:
        percent:     Desired volume level (0–100).
        tolerance:   Allowed percent difference when verifying (default: 1%).
        change_mute: If set to "mute", the function will mute the audio instead of
                     setting a specific volume. If set to "unmute", it will unmute
                     the audio. If None, it will not change the mute state.
        force_pactl: If True, always use pactl even if pulsectl is available (default: False).

    Returns:
        None

    Raises:
        RuntimeError: If the volume could not be set or verified.
    """
    import subprocess
    import logging
    fallback_logging_config()
    if not sys.platform.startswith('linux'):
        raise RuntimeError("This set_system_volume() function is only intended to run on Linux systems.")
    fraction = percent / 100.0
    mute_arg = None
    if change_mute is not None:
        if change_mute.casefold() == "mute":
            mute_arg = 1
        elif change_mute.casefold() == "unmute":
            mute_arg = 0
        else:
            raise ValueError("change_mute must be 'mute', 'unmute', or None")
    # First, try using pulsectl to set the volume.
    if not force_pactl:
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("force_pactl=%s.", force_pactl)
        try:
            from pulsectl import Pulse, PulseError
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("[pulsectl] Attempting to set the volume to %d%% using pulsectl...", percent)
            with Pulse('volume-setter') as pulse:
                default_name = pulse.server_info().default_sink_name
                sink = pulse.get_sink_by_name(default_name)
                pulse.sink_suspend(sink.index, False)  # <— wake it up if it’s suspended
                pulse.volume_set_all_chans(sink, fraction)
                # Optionally set mute
                if mute_arg is not None:
                    pulse.sink_mute(sink.index, mute_arg)
                    sink_after = pulse.get_sink_by_name(default_name)
                    # Verify mute state
                    if   mute_arg == 1 and not sink_after.mute:
                        raise RuntimeError("[pulsectl] Volume is not muted even though the user requested it to be muted.")
                    elif mute_arg == 0 and     sink_after.mute:
                        raise RuntimeError("[pulsectl] Volume is still muted even though the user requested it to be unmuted.")
                else:
                    # Fetch volume again to verify
                    sink_after = pulse.get_sink_by_name(default_name)
                vols = sink_after.volume.values  # list of channel floats 0.0–1.0
                avg = sum(vols) / len(vols)
                actual = int(round(avg * 100))
                if abs(actual - percent) > tolerance:
                    raise RuntimeError(f"[pulsectl] Expected {percent}%, but got {actual}%")
                if mute_arg is not None and sink_after.mute != mute_arg:
                    state = "muted" if sink_after.mute else "unmuted"
                    raise RuntimeError(f"Mute verify failed: got {state}")
                logging.info("[pulsectl] Volume set to %d%%, %s", actual, state)
                return  # Successfully set volume and verified
        except (ImportError, ModuleNotFoundError):
            logging.warning("[pulsectl] Not installed; falling back to pactl…")
        except PulseError as e:
            logging.error("[pulsectl] PulseError: %s; falling back to pactl…", e)
        except RuntimeError as e:
            logging.error("%s; falling back to pactl…", e)
        except Exception as e:
            logging.error("[pulsectl] Unexpected error: %s; falling back to pactl…", e)

    # Fallback to pactl if pulsectl is not available or fails
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("[pactl] Attempting to set the volume to %d%% using pactl...", percent)
    the_command = ["pactl", "suspend-sink", "@DEFAULT_SINK@", "0"]
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("[pactl] Running command: %s", ' '.join(the_command))
    result = subprocess.run(the_command, check=True, capture_output=True, text=True)
    if result.stderr:
        raise RuntimeError(f"[pactl] Error waking up sink from suspension: {result.stderr.strip()}")
    the_command = ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"]
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("[pactl] Running command: %s", ' '.join(the_command))
    result = subprocess.run(the_command, check=True, capture_output=True, text=True)
    if result.stderr:
        raise RuntimeError(f"[pactl] Error setting volume: {result.stderr.strip()}")
    # Set mute if requested
    if mute_arg is not None:
        cmd = ["pactl", "set-sink-mute", "@DEFAULT_SINK@", str(mute_arg)]
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("[pactl] %s", ' '.join(cmd))
        mute_result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if mute_result.stderr:
            raise RuntimeError(f"[pactl] Error setting mute: {mute_result.stderr.strip()}")
        # Verify mute state
        mute_check_cmd = ["pactl", "get-sink-mute", "@DEFAULT_SINK@"]
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("[pactl] Running command: %s", ' '.join(mute_check_cmd))
        mute_result = subprocess.run(mute_check_cmd, check=True, capture_output=True, text=True)
        if mute_result.stderr:
            raise RuntimeError(f"[pactl] Error getting mute state: {mute_result.stderr.strip()}")
        mute_output = mute_result.stdout.strip()
        if   mute_arg == 1 and "yes" not in mute_output:
            raise RuntimeError("[pactl] Volume is not muted even though the user requested it to be muted.")
        elif mute_arg == 0 and "no"  not in mute_output:
            raise RuntimeError("[pactl] Volume is still muted even though the user requested it to be unmuted.")
        logging.info("[pactl] Audio %s", 'muted' if mute_arg else 'unmuted')
    # Verify volume setting with pactl
    the_command = ["pactl", "get-sink-volume", "@DEFAULT_SINK@"]
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("[pactl] Running command: %s", ' '.join(the_command))
    result = subprocess.run(the_command, check=True, capture_output=True, text=True)
    if result.stderr:
        raise RuntimeError(f"[pactl] Error getting volume: {result.stderr.strip()}")
    output = result.stdout.strip()
    # Example output: "Volume: front-left: 32768 / 100% / 32768 / 100%"
    parts = output.split('/')
    if len(parts) < 2:
        raise RuntimeError(f"[pactl] Unexpected pactl output: {output}")
    actual = int(parts[1].strip().replace('%', ''))
    if abs(actual - percent) > tolerance:
        raise RuntimeError(f"[pactl] Expected {percent}%, but got {actual}%")
    logging.info("[pactl] Volume set to %d%%", percent)


def open_playlist_in_VLC(playlist: str | os.PathLike[str], no_start:  bool = False) -> None:
    """Open a playlist in VLC. If no_start is True, don't start playback in VLC."""
    import subprocess
    playlist = ensure_path_is_a_file(playlist)
    if no_start: command_list = ["vlc", "--no-playlist-autostart", os.fspath(playlist)]
    else:        command_list = ["vlc",                            os.fspath(playlist)]
    subprocess.Popen(command_list, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def open_dir_in_VLC(the_dir: str | os.PathLike[str], sort_choice: str = "sort_by_name",
                    recursive: bool = False, no_start:  bool = False) -> None:
    """Create a playlist of the files in the specified directory, then play that playlist in VLC. By default, don't search the directory recursively and sort the files by name. Optional arguments allow recursive loading or sorting by modification time. If no_start is True, don't start playback in VLC."""
    import subprocess
    if the_dir is None:
        raise ValueError("The directory path cannot be None.")
    the_dir = Path(the_dir).expanduser().resolve(strict=True)
    if not the_dir.is_dir():
        raise ValueError(f"The specified path '{the_dir}' is not a valid directory.")
    # start_flag = "--start-paused" if no_start else False # The "--start-paused" flag forces you to press play in VLC EACH TIME YOU GO TO A NEW PLAYLIST ENTRY!
    start_flag = "--no-playlist-autostart" if no_start else False
    # List to store files with their modification times
    files_with_times: list[tuple[float, Path]] = []
    dirs_with_times:  list[tuple[float, Path]] = []  # Only used if not recursive
    entries: Iterator[Path] = the_dir.rglob("*") if recursive else the_dir.iterdir()
    for p in entries:
        if p.is_file():
            # Exclude .m3u or .m3u8 playlist files
            if p.suffix.casefold() in (".m3u", ".m3u8"):
                continue
            files_with_times.append((p.stat().st_mtime, p))
        elif not recursive and p.is_dir():
            dirs_with_times.append((p.stat().st_mtime, p))
    if sort_choice == "sort_by_name":
        # Sort files by name, case-insensitively
        files_with_times.sort(   key=lambda x: x[1].name.casefold())
        if len(dirs_with_times) > 0:
            dirs_with_times.sort(key=lambda x: x[1].name.casefold())
    elif sort_choice == "sort_by_time":
        # Sort files by modification time (earliest first)
        files_with_times.sort(   key=lambda x: x[0])
        if len(dirs_with_times) > 0:
            dirs_with_times.sort(key=lambda x: x[0])
    # If present, put directories at the top of the list
    files_with_times = dirs_with_times + files_with_times
    # Create the .m3u playlist content with as_posix() to ensure forward slashes even on Windows
    playlist_content = "#EXTM3U\n"
    for _, file_path in files_with_times:
        playlist_content += f"#EXTINF:-1,{file_path.name.replace(',', '').replace('-', '')}" \
                            f"\n{file_path.as_posix()}\n"
    # Write the playlist to disk in the directory
    playlist_path = the_dir / f"{filename_format(the_dir.name)}_playlist.m3u"
    playlist_path.write_text(playlist_content, encoding=DEFAULT_ENCODING)
    # Open the playlist in VLC
    if start_flag: command_list = ["vlc", start_flag, playlist_path]
    else:          command_list = ["vlc",             playlist_path]
    subprocess.Popen(command_list, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def remove_prefix_from_filename(filepath: str | os.PathLike[str], prefix: str) -> bool:
    """
    If the given filepath's base filename starts with the given prefix:
      1. Remove the prefix (and any " _-" immediately following it).
      2. Move the file (but only if that doesn't cause errors).
    
    Args:
        filepath: The path to the file whose name may need to be changed.
        prefix:   The prefix to remove from the filename.

    Returns:
        True:  If the file was successfully renamed, or if it didn't need renaming.
        False: If the file was not renamed because it didn't start with the prefix,
               or if the new filename already exists.

    Raises:
        OSError: If the rename operation fails due to an OS error (e.g., permission denied).
    """
    fallback_logging_config()
    filepath = Path(filepath).expanduser().resolve()
    if not filepath.exists():
        logging.warning("File or directory '%s' does not exist.", filepath)
        return False
    file = filepath.name
    if file.startswith(prefix):
        new_file = file.replace(prefix, "", 1)  # Replace only the first occurrence
        # If the first character is now in " _-", remove it:
        while new_file[0] in " _-":
            new_file = new_file[1:]
        new_filepath = filepath.parent / new_file
        if not new_filepath.exists():
            try:
                filepath.rename(new_filepath)
                logging.info("Renamed '%s' to '%s'.", filepath, new_filepath)
                return True
            except OSError as e:
                raise OSError(f"Failed to rename '{filepath}' to '{new_filepath}': {e}") from e
        else:
            logging.warning("Cannot rename '%s' to '%s': New path already exists.", filepath, new_filepath)
            return False
    else:
        return False


def remove_prefix_from_html_title(filepath: str | os.PathLike[str], prefix: str) -> bool:
    """If the given filepath is an HTML file and its title starts with the given prefix, remove the prefix from the title and save the file, then return True. Otherwise, return False."""
    fallback_logging_config()
    filepath = Path(filepath)
    if not filepath.is_file():
        logging.warning("File '%s' does not exist or is not a file.", filepath)
        return False
    if filepath.suffix.casefold() not in ('.html', '.htm'):
        logging.warning("File '%s' is not an HTML or HTM file.", filepath)
        return False
    html = my_fopen(filepath)
    title_start = html.find('<title>') + len('<title>')
    title_end   = html.find('</title>', title_start)
    if title_start == -1 or title_end == -1:
        logging.warning("Could not find the title in the HTML file '%s'.", filepath)
        return False
    title = html[title_start:title_end]
    if title.startswith(prefix):
        new_title = title.replace(prefix, "", 1)  # Replace only the first occurrence
        new_html = html[:title_start] + new_title + html[title_end:]
        filepath.write_text(new_html, encoding=DEFAULT_ENCODING)
        logging.info("Removed prefix '%s' from the title in '%s'.", prefix, filepath)
        return True
    else:
        return False


def combine_html_files(file_paths: list[str | os.PathLike[str]],
                       output_file_path: str | os.PathLike[str]) -> None:
    """
    Combine multiple HTML files into a single HTML file.
    The first file's <head> is preserved, and all <body> contents are concatenated.

    Args:
        file_paths:       List of (presorted) file paths to the HTML files to combine.
        output_file_path: Path to save the combined HTML file.

    Returns:
        None: the combined HTML is saved to the specified output file path.

    Raises:
        Exception:         If there is an error reading any of the HTML files or writing the output file.
        FileNotFoundError: If any of the input files do not exist.
        ValueError:        If the output file path is not valid.
        ImportError:       If BeautifulSoup is not installed.
        RuntimeError:      If the output file cannot be written.
        OSError:           If there is an error during file operations.
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
        output_file_path = Path(output_file_path).expanduser().resolve()
        output_file_path.parent.mkdir(parents=True, exist_ok=True)
        output_file_path.write_text(combined_html, encoding=DEFAULT_ENCODING)
    except Exception:  # Catch any unexpected errors from writing the file without crashing.
        logging.exception("Error saving combined HTML to %s.", output_file_path)
    logging.info("Saved combined HTML to '%s'.", output_file_path)


def check_list_for_duplicates(the_list: list) -> bool:
    """Check a list for duplicate elements and return True if duplicates are found."""
    duplicates = [ext for ext in set(the_list) if the_list.count(ext) > 1]
    print("Duplicates:", duplicates)
    return len(duplicates) > 0


# A comprehensive list of encodings to try when reading files, with most likely encodings first.
text_encodings: list[str] = [
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
text_encodings = [e.casefold() for e in text_encodings]  # Just in... case.
# check_list_for_duplicates(text_encodings) # Run this after adding new extensions to ensure there are no duplicates.

# A comprehensive list of python extensions.
python_extensions: list[str] = ['.py', '.pyw']
python_extensions = [e.casefold() for e in python_extensions]  # Just in... case.

# A comprehensive list of text file extensions.
text_extensions: list[str] = [
    '.txt',  '.html',     '.htm',      '.csv',        '.json', '.xml'
    '.adoc', '.asciidoc', '.bib',      '.cfg',        '.conf', '.ini',
    '.log',  '.md',       '.markdown', '.properties', '.rtf',  '.rst',
    '.sgm',  '.sgml',     '.tex',      '.toml',       '.tsv',  '.xhtml',
    '.yaml', '.yml',
]
text_extensions = [e.casefold() for e in text_extensions]  # Just in... case.
# check_list_for_duplicates(text_extensions) # Run this after adding new extensions to ensure there are no duplicates.

# A comprehensive list of video file extensions.
video_extensions: list[str] = [
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
video_extensions = [e.casefold() for e in video_extensions]  # Just in... case.
# check_list_for_duplicates(video_extensions) # Run this after adding new extensions to ensure there are no duplicates.

# A comprehensive list of audio file extensions.
audio_extensions: list[str] = [
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
audio_extensions = [e.casefold() for e in audio_extensions]  # Just in... case.
# check_list_for_duplicates(audio_extensions) # Run this after adding new extensions to ensure there are no duplicates.

# A comprehensive list of subtitle file extensions.
subtitle_extensions: list[str] = [
    '.srt',   '.sub',    '.idx',   '.ass',   '.ssa',   '.vtt',
    '.ttml',  '.dfxp',   '.smi',   '.smil',  '.usf',   '.psb',
    '.mks',   '.lrc',    '.stl',   '.pjs',   '.rt',    '.aqt',
    '.gsub',  '.jss',    '.dks',   '.mpl2',  '.tmp',   '.vsf',
    '.zeg',   '.webvtt', '.scc',   '.cap',   '.asc',   '.qt.txt',  # match .qt.txt before .txt
    '.sbv',   '.ebu',    '.sami',  '.xml',   '.itt',   '.txt',
]
subtitle_extensions = [e.casefold() for e in subtitle_extensions]  # Just in... case.
# check_list_for_duplicates(subtitle_extensions) # Run this after adding new extensions to ensure there are no duplicates.

# A comprehensive list of image file extensions.
image_extensions: list[str] = [
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
image_extensions = [e.casefold() for e in image_extensions]  # Just in... case.
# check_list_for_duplicates(image_extensions) # Run this after adding new extensions to ensure there are no duplicates.

# A comprehensive list of archive file extensions.
archive_extensions: list[str] = [
    '.zip',     '.rar',    '.7z',    '.tar.gz', '.tar.bz2', '.tar.xz',  # match .tar.(gz,bz2,xz) before (.gz,.bz2,.xz)
    '.tar.zst', '.tar',    '.gz',    '.tgz',    '.bz2',     '.xz',
    '.tbz2',    '.tz2',    '.lzma',  '.lz',     '.xpi',     '.crx',
    '.zst',     '.cab',    '.arj',   '.ace',    '.uue',     '.zoo',
    '.jar',     '.war',    '.ear',   '.iso',    '.img',     '.dmg',
    '.lzh',     '.lha',    '.cpio',  '.deb',    '.rpm',     '.apk',
    '.pak',     '.arc',    '.a',     '.mar',    '.b1',      '.wim',
    '.shar',    '.run',    '.shk',   '.sit',    '.sitx',    '.zpaq',
    '.br', 
]
archive_extensions = [e.casefold() for e in archive_extensions]  # Just in... case.
# check_list_for_duplicates(archive_extensions) # Run this after adding new extensions to ensure there are no duplicates.

# Put subtitle_ext before text_ext so .qt.txt matches before .txt
all_known_extensions: list[str] = python_extensions + subtitle_extensions + \
                                  text_extensions   + video_extensions    + \
                                  audio_extensions  + image_extensions    + \
                                  archive_extensions  
# check_list_for_duplicates(all_extensions) # Run this after adding new extensions to ensure there are no duplicates. But in this case there WILL be because subtitle_extensions and text_extensions overlap.
