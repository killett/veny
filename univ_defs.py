#NEW aws help docstring:
# disables searching through script args for python scripts and then scanning them for imports. 
import os, sys, subprocess
from datetime import datetime
import logging
import threading
import socket
import platform
from collections import Counter
from typing import Dict

# This is the version of univ_defs.py
__version__ = '0.1.1'

# This is the version of python which should be used in scripts that import this module.
PY_VERSION = 3.11

# sigfigs    =  1 #significant figures to keep during rounding.
# max_digits = 15 #If the number is less than 10^(-max_digits), just say it has max_digits.

# #Given 'float_input', what is its exponent in scientific notation?
# def sci_exp(float_input):
#   if np.abs(float_input) < 10**(-max_digits): return -max_digits
#   return int(np.floor(np.log10(np.abs(float_input))))

# #"round out" away from zero while keeping round_digits significant figures.
# #Rounds up for x>0, down for x<0.
# def round_out(x, round_digits):
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
#   year = int(dec)
#   rem = dec - year
#   base = datetime.datetime(year, 1, 1)
#   result = base + datetime.timedelta(seconds=(base.replace(year=base.year + 1) - base).total_seconds() * rem)
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
                      rawlog: bool = False) -> MemoryHandler:
    """Configure logging to write to files and stdout/stderr, and return a MemoryHandler to capture ERROR logs for later (duplicate) printing."""
    
    root_logger = logging.getLogger()

    # Check if logging is already configured by checking for any handlers
    if root_logger.hasHandlers():
        print("Logging is already configured.", flush=True)
        for handler in root_logger.handlers:
            if isinstance(handler, MemoryHandler):
                return handler

    # Proceed with configuring logging if no MemoryHandler was found
    #logs_directory = '/tmp/logs'
    logs_directory = os.getcwd()
    os.makedirs(logs_directory, exist_ok=True)

    now = datetime.now()
    log_base = f".{basename}-log-{now.strftime('%Y%m%d-%H%M%S')}"
    log_info = os.path.join(logs_directory, log_base + ".out")
    log_errors = os.path.join(logs_directory, log_base + ".err")

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

    # Stream handler for stdout (INFO and lower)
    console_handler_stdout = FlushingStreamHandler(stream=sys.stdout)
    console_handler_stdout.setLevel(logging.DEBUG)  # Set to lowest level
    console_handler_stdout.addFilter(MaxLevelFilter(logging.INFO))  # Add filter for INFO and lower

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

def my_critical_error(message: str, choose_breakpoint: bool = False,
                      exit_code: int = 1) -> None:
    """Log a critical error message and either exit the program or enter a breakpoint."""
    #Check to see if logger is set up. If not, just print the critical error message.
    if logging.getLogger().hasHandlers():
        logging.critical(message)
    else:
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
    return string_to_capitalize[0].upper() + string_to_capitalize[1:]

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

def get_hostname_socket():
    """Retrieves the hostname using socket.gethostname()."""
    return socket.gethostname()

def get_hostname_platform():
    """Retrieves the hostname using platform.node()."""
    return platform.node()

def get_hostname_os_uname():
    """Retrieves the hostname using os.uname().nodename."""
    return os.uname().nodename

def get_hostname_subprocess_hostname():
    """Retrieves the hostname using the 'hostname' system command via subprocess."""
    result = subprocess.run(['hostname'], capture_output=True, text=True, check=True)
    return result.stdout.strip()

def get_hostname_subprocess_scutil():
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

def prettyprint_timespan(timespan: float) -> None:
    """Pretty-prints a timespan in years, weeks, days, hours, and seconds."""

    # Constants for time conversions
    SECONDS_PER_MINUTE = 60
    SECONDS_PER_HOUR = 3600
    SECONDS_PER_DAY = 86400
    SECONDS_PER_WEEK = 604800
    SECONDS_PER_YEAR = 31556952

    # Calculating years, weeks, days, hours
    years = int(timespan // SECONDS_PER_YEAR)
    remaining = timespan % SECONDS_PER_YEAR

    weeks = int(remaining // SECONDS_PER_WEEK)
    remaining = remaining % SECONDS_PER_WEEK

    days = int(remaining // SECONDS_PER_DAY)
    remaining = remaining % SECONDS_PER_DAY

    hours = remaining / SECONDS_PER_HOUR
    remaining = remaining % SECONDS_PER_HOUR

    # Creating a list of time components
    components = []
    if years > 0:
        components.append(f"{years} years")
    if weeks > 0:
        components.append(f"{weeks} weeks")
    if days > 0:
        components.append(f"{days} days")
    if hours > 0:
        components.append(f"{hours:.1f} hours")
    else:
        components.append(f"{remaining:.3f} seconds")
    
    # Joining the components with commas, and "and" for the last component
    if len(components) > 1:
        time_str = ", ".join(components[:-1]) + " and " + components[-1]
    elif components:
        time_str = components[0]
    else:
        time_str = "0 seconds"

    print(f"The script took {time_str} to run.")

def open_dir_in_VLC(the_dir: str, sort_choice: str = "sort_by_name",
                    recursive: bool = False,
                    no_start: bool = False) -> None:
    """Create a playlist of the files in the specified directory, then play that playlist in VLC. By default, don't search the directory recursively and sort the files by name. Optional arguments allow recursive loading or sorting by modification time. If no_start is True, don't start playback in VLC."""
    #start_flag = "--start-paused" if no_start else ""
    start_flag = "--no-playlist-autostart" if no_start else ""
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
