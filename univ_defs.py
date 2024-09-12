import os, subprocess
from datetime import datetime
import logging

class MemoryHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.logs = []

    def emit(self, record):
        self.logs.append(self.format(record))

def configure_logging(basename: str, log_level: str = 'INFO', testing: bool = False) -> MemoryHandler:
    """Configure logging to write to a file and the console."""
    #logs_directory = '/tmp/logs'
    #os.makedirs(logs_directory, exist_ok=True)
    logs_directory = '.'
    
    now = datetime.now()
    log_base = f".{basename}-log-{now.strftime('%Y%m%d-%H%M%S')}"
    log_info = log_base + ".out"
    log_errors = log_base + ".err"
    
    logging.root.handlers = []  # Clear any existing handlers
    
    # Create handlers
    debug_info_handler = logging.FileHandler(log_info)
    debug_info_handler.setLevel(logging.DEBUG)
    
    warning_error_handler = logging.FileHandler(log_errors)
    warning_error_handler.setLevel(logging.WARNING)
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(get_log_level(log_level))
    
    memory_handler = MemoryHandler()
    memory_handler.setLevel(logging.WARNING)
    
    # Formatter
    log_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    debug_info_handler.setFormatter(log_format)
    warning_error_handler.setFormatter(log_format)
    console_handler.setFormatter(log_format)
    memory_handler.setFormatter(log_format)
    
    # Add handlers to the root logger
    logging.basicConfig(
        level=get_log_level(log_level),
        handlers=[debug_info_handler, warning_error_handler, console_handler, memory_handler]
    )
    
    if testing:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.info(f'Logging to console with level {logging.getLevelName(get_log_level(log_level))}')
    else:
        logging.info(f'Logging to {log_info} and {log_errors} with level {logging.getLevelName(get_log_level(log_level))}')
    
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

def get_user_input(prompt: str) -> bool:
    """Prompt the user with the given message and return True if the user enters 'yes', False otherwise."""
    user_input = input(prompt)
    return user_input.casefold() == 'yes' or user_input.casefold() == 'y'

def my_capitalize(string_to_capitalize: str) -> str:
    """Capitalize ONLY the first letter of a string and DON'T modify the rest of it."""
    return string_to_capitalize[0].upper() + string_to_capitalize[1:]

class MyPopenResult:
    def __init__(self, stdout, stderr, returncode):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.success = (returncode == 0)

def my_popen(command_list: list, suppress_info: bool = False) -> MyPopenResult:
    """Execute a command using subprocess.Popen and capture the output line by line."""
    print(f"{suppress_info = }")
    command_list_str = [str(item) for item in command_list]
    the_statement = "Executing command: " + ' '.join(command_list_str)
    
    if not suppress_info: logging.info( the_statement)
    else:                 logging.debug(the_statement)

    try:
        process = subprocess.Popen(command_list_str,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   text=True)
        stdout = ""
        stderr = ""
        # Capture stdout and stderr line by line
        while True:
            line_out = process.stdout.readline()
            line_err = process.stderr.readline()
            if line_out:
                log_line = line_out.strip()
                if not suppress_info: logging.info( log_line)
                else:                 logging.debug(log_line)
                stdout += line_out
            if line_err:
                log_line = line_err.strip()
                logging.error(log_line)
                stderr += line_err
            if not line_out and not line_err and process.poll() is not None:
                break
        return MyPopenResult(stdout=stdout, stderr=stderr, returncode=process.returncode)    
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return MyPopenResult(stdout="", stderr=str(e), returncode=-1)

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

def open_dir_in_VLC(the_dir: str, sort_choice: str,
                    recursive: bool = False) -> None:
    """Recursively open the files in the directory in VLC, sorted by name or modification time."""
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
    # Write the playlist to ./playlist.m3u
    playlist_path = "./playlist.m3u"
    with open(playlist_path, "w") as playlist_file:
        playlist_file.write(playlist_content)
    # Open the playlist in VLC
    subprocess.Popen(["vlc", playlist_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
