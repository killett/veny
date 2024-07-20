#!/usr/bin/env python3

# Emmy Killett

import os
import sys
import subprocess
from datetime import datetime
import argparse
import logging
import ast
import re
import json
import copy
from typing import Dict, List, Set, Tuple

class Options():
    '''Class that has all global options in one place.'''
    def __init__(self) -> None:
        self.venv_name: str = 'myenv' # Can NOT include dashes ('-')
        self.mypy_dir = os.path.expanduser(os.path.join('~','mypy'))
        self.packages_dir = os.path.join(self.mypy_dir, 'packages')

    def set_venv_dir(self, venv_dir: str) -> None:
        self.venv_dir = os.path.expanduser(venv_dir)
        self.activate_script   = 'source ' + os.path.join(self.venv_dir, 'bin', 'activate')
        self.venv_python       = os.path.join(self.venv_dir, 'bin', 'python')
        self.venv_pip          = os.path.join(self.venv_dir, 'bin', 'pip')
        self.requirements_file = os.path.join(self.venv_dir, "requirements.txt")

# Configure logging
#logging.basicConfig(level=logging.INFO)
#logger = logging.getLogger(__name__)
def logging_setup(basename: str) -> None:
    """
    Set up logging to write to a file and the console.
    Args:
        basename (str): The base name for the log files. The current date/time will be appended to this name.
    Returns:
        None
    """
    # Create a custom logger
    global logger
    logger = logging.getLogger("my_logger")
    logger.setLevel(logging.DEBUG)
    # Create a file handler
    global now
    now = datetime.now()
    log_base = "."+basename+"-log-"+now.strftime('%Y%m%d-%H%M%S')
    log_info = log_base+".out"
    log_errors = log_base+".err"
    # Create a file handler for debug and info messages
    debug_info_handler = logging.FileHandler(log_info)
    debug_info_handler.setLevel(logging.DEBUG)
    # Create a file handler for warning, error, and critical messages
    warning_error_handler = logging.FileHandler(log_errors)
    warning_error_handler.setLevel(logging.WARNING)
    # Create a stream handler (console)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    # Set a log format
    log_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    # Apply the format to all handlers
    debug_info_handler.setFormatter(log_format)
    warning_error_handler.setFormatter(log_format)
    console_handler.setFormatter(log_format)
    # Add the handlers to the logger
    logger.addHandler(debug_info_handler)
    logger.addHandler(warning_error_handler)
    logger.addHandler(console_handler)

print(__name__)
logging_setup(__name__)

# Attempt to import pipreqs
try:
    import pipreqs
    logger.info("pipreqs is available, so it will be used.")
    PIPREQS_AVAILABLE = True
except ImportError:
    #This used to be a logger.warning() but I changed it to logger.info() because it's not really a warning.
    logger.info("pipreqs is not available. Try installing it with 'pip install pipreqs'.")
    PIPREQS_AVAILABLE = False

def find_imports_in_script(file_path: str, all_imports: Set[str]) -> None:
    encodings = [
    'utf_8', 'latin_1', 'ascii', 'iso8859_1', 'big5', 'utf_8_sig', 'utf_16', 'utf_16_be', 'utf_16_le', 'utf_32', 'utf_32_be', 'utf_32_le',
    'cp1252', 'cp1251', 'cp1250', 'cp1253', 'cp1254', 'cp1255', 'cp1256', 'cp1257', 'cp1258',
    'iso8859_2', 'iso8859_3', 'iso8859_4', 'iso8859_5', 'iso8859_6', 'iso8859_7', 'iso8859_8', 'iso8859_9', 
    'iso8859_10', 'iso8859_11', 'iso8859_13', 'iso8859_14', 'iso8859_15', 'iso8859_16',
    'cp437', 'cp850', 'cp852', 'cp855', 'cp857', 'cp858', 'cp860', 'cp861', 'cp862', 'cp863', 'cp864', 'cp865', 'cp866', 'cp869',
    'cp037', 'cp424', 'cp500', 'cp720', 'cp737', 'cp775', 'cp874', 'cp875', 'cp932', 'cp949', 'cp950', 'cp1006', 'cp1026', 
    'cp1125', 'cp1140',
    'big5hkscs', 'gb2312', 'gbk', 'gb18030', 'euc_jp', 'euc_jis_2004', 'euc_jisx0213', 'euc_kr', 
    'iso2022_jp', 'iso2022_jp_1', 'iso2022_jp_2', 'iso2022_jp_2004', 'iso2022_jp_3', 'iso2022_jp_ext', 'iso2022_kr', 
    'johab', 'koi8_r', 'koi8_t', 'koi8_u', 'kz1048', 'mac_cyrillic', 'mac_greek', 'mac_iceland', 'mac_latin2', 'mac_roman', 
    'mac_turkish', 'ptcp154', 'shift_jis', 'shift_jis_2004', 'shift_jisx0213', 'hz', 'tis_620', 'euc_tw', 'iso2022_tw',]

    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as file:
                lines = file.readlines()
            break  # Exit the loop if reading is successful
        except UnicodeDecodeError:
            logger.error(f"Unicode decode error with encoding {encoding} reading file {file_path}")
            continue  # Try the next encoding
        except Exception as e:
            logger.error(f"Error reading file {file_path} with encoding {encoding}: {str(e)}")
            return

    for line in lines:
        line = line.strip()
        if '#' in line:
            line = line.split('#')[0].strip()  # Remove comments from the line
        
        if ';' in line:
            line = line.split(';')[0].strip()  # Remove other commands from the line

        if line.startswith('import '):
            # Handle multiple imports on the same line
            parts = re.split(r'import ', line, maxsplit=1)
            if len(parts) > 1:
                imports_list = parts[1].split(',')
            else:
                imports_list = []
        elif line.startswith('from '):
            # Handle 'from X import Y' type of lines
            parts = re.split(r'\s+', line, maxsplit=2)
            imports_list = [parts[1]]
        else:
            continue

        for imp in imports_list:
            imp = imp.split(' as ')[0].strip()  # Remove "as alias" part
            this_import = imp.split('.')[0].strip()
            if this_import and this_import not in all_imports:
                all_imports.add(this_import)

def get_all_imports(directory: str) -> Set[str]:

    all_imports = set()
    total_files = sum(len(files) for _, _, files in os.walk(directory) if 'myenv' not in _)
    processed_files = 0

    for root, _, files in os.walk(directory):
        if 'myenv' in root:
            continue
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                find_imports_in_script(file_path, all_imports)
                processed_files += 1
                logger.info(f"Processing files in {directory}: {processed_files}/{total_files}")

    logger.info(f"\nFinished processing files in {directory}.")
    return all_imports

def check_if_library_exists(library_name: str) -> bool:
    try:
        result = subprocess.run(
            [sys.executable, '-c', f'import {library_name}'],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Error checking library {library_name}: {e}")
    return False

def split_imports(all_imports: Set[str]) -> Tuple[Set[str], Set[str], Set[str]]:
    known_bad_imports = {'bs4', 'snakeClass', 'pathfinding_salvo_rework', 'seaborn', 'DQN', 'bayesOpt', 'tkinter', 'msvcrt', 'univ_defs', 'search_for_media_files', 'kill_switch', 'list_required_packages', 'crossover', 'non_existent_module'}
    bad_imports = known_bad_imports.intersection(all_imports)
    all_imports = all_imports - bad_imports
    installed_imports = set()
    uninstalled_imports = set()
    total_imports = len(all_imports)

    for i, imp in enumerate(all_imports, 1):
        if check_if_library_exists(imp):
            installed_imports.add(imp)
        else:
            uninstalled_imports.add(imp)
        logger.info(f"Checking imports: {i}/{total_imports}")

    return installed_imports, uninstalled_imports, bad_imports

def generate_requirements(directory: str) -> None:
    try:
        pipreqs.generate_requirements(directory)
    except Exception as e:
        logger.error(f"Error generating requirements file: {e}")

def list_packages(python_dir_or_file: str) -> Tuple[Set[str], Set[str]]:
    python_dir_or_file = os.path.expanduser(python_dir_or_file)

    if os.path.isfile(python_dir_or_file):
        logger.info("Processing a single Python script.")
        python_file = python_dir_or_file
        all_imports = set()
        find_imports_in_script(python_file, all_imports)
    elif os.path.isdir(python_dir_or_file):
        logger.info("Processing an entire folder of Python scripts.")
        python_dir = python_dir_or_file
        if PIPREQS_AVAILABLE:
            logger.info("Using pipreqs to generate requirements.")
            generate_requirements(python_dir_or_file)
            with open(os.path.join(python_dir, 'requirements.txt'), 'r') as f:
                all_imports = set(line.strip() for line in f)
        else:
            logger.info("Using custom script to find imports.")
            all_imports = get_all_imports(python_dir_or_file)
    else:
        logger.error(f"Error: The file or directory {python_dir_or_file} does not exist.")
        sys.exit(1)

    # Filter out invalid imports before splitting
    all_imports = {imp for imp in all_imports if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', imp)}
    
    installed_imports, uninstalled_imports, bad_imports = split_imports(all_imports)

    return installed_imports, uninstalled_imports, bad_imports

def install_packages(options: Options) -> None:
    """Install packages in a virtual environment."""
    download_script = f"""#!/bin/bash
source {options.venv_dir}/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Ensure setuptools and wheel are available locally
if ls {options.packages_dir}/setuptools-*.whl 1> /dev/null 2>&1; then
    echo "Local setuptools files found."
else
    echo "Downloading setuptools..."
    {options.venv_pip} download --only-binary=:all: setuptools -d {options.packages_dir}
fi

if ls {options.packages_dir}/wheel-*.whl 1> /dev/null 2>&1; then
    echo "Local wheel files found."
else
    echo "Downloading wheel..."
    {options.venv_pip} download --only-binary=:all: wheel -d {options.packages_dir}
fi

# Download required packages
echo "Downloading packages..."
{options.venv_pip} download -r {options.requirements_file} -d {options.packages_dir}
"""

    options.download_script_path = os.path.join(options.venv_dir, f"download_packages.sh")
    logger.info(f"Writing download script to {options.download_script_path}")
    with open(options.download_script_path, 'w') as f:
        f.write(download_script)
    os.chmod(options.download_script_path, 0o755)

    # Run the initial download script and capture the output
    process = subprocess.Popen(
        [options.download_script_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    captured_output = ""
    for line in iter(process.stdout.readline, ''):
        logger.info(line.strip())
        captured_output += line
    for line in iter(process.stderr.readline, ''):
        logger.error(line.strip())
        captured_output += line
    process.stdout.close()
    process.stderr.close()
    process.wait()

    # Now, attempt to install each package individually
    failed_packages = []
    for package in options.packages:
        if not install_package(package, options):
            failed_packages.append(package)
    
    if failed_packages:
        logger.error(f"Failed to install the following packages: {', '.join(failed_packages)}")
    else:
        logger.info("All packages installed successfully.")

    # Run the test script
    check_packages_in_venv(options)

def install_package(package_name: str, options: Options) -> bool:
    """Install a single package and return the success status."""
    try:
        result = subprocess.run(
            [options.venv_python, "-m", "pip", "install", package_name, "--no-index", "--find-links", options.packages_dir],
            capture_output=True,
            text=True
        )
        logger.info(result.stdout)
        if result.stderr:
            logger.error(result.stderr)
        if result.returncode != 0:
            # Try to install from PyPI if local installation fails
            logger.info(f"Package {package_name} not found locally. Attempting to install from PyPI.")
            result = subprocess.run(
                [options.venv_python, "-m", "pip", "install", package_name],
                capture_output=True,
                text=True
            )
            logger.info(result.stdout)
            if result.stderr:
                logger.error(result.stderr)
            return result.returncode == 0
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Error installing package {package_name}: {e}")
        return False

def check_packages_in_venv(options: Options) -> bool:
    """Create and run a script to test package imports in the virtual environment."""
    packages_str = ", ".join(f"'{pkg}'" for pkg in options.packages)  # Properly format the list of packages as strings
    test_script = f"""
source {options.venv_dir}/bin/activate
{options.venv_python} - << END
successes = []
failures = []
counter = 0
for package in [{packages_str}]:
    counter += 1
    try:
        __import__(package)
        successes.append(package)
    except ImportError:
        failures.append(package)
if failures:
    print("Failed packages: " + ", ".join(failures))
elif len(successes) != counter: #This should never happen.
    print(f"Warning: No failures, but only recorded {{len(successes)}} successes out of {{counter}} iterations through the loop.")
else:
    print(f"All {{len(successes)}} (out of {{counter}}) packages imported successfully.")
END
"""

    # Run the test script
    result = subprocess.run(test_script, shell=True, executable='/bin/bash', check=True, capture_output=True, text=True)
    logger.info(result.stdout)
    if result.stderr:
        logger.error(result.stderr)
    
    # This returns true if all packages imported successfully
    return "packages imported successfully" in result.stdout

def recover_pip_versions(output: str, options: Options) -> None:
    """Parse the output to recover the current and new pip versions."""
    if hasattr(output, 'read'):
        output = output.read()
    current_version_pattern = re.compile(r"Current pip version: (.+)")
    new_version_pattern = re.compile(r"New pip version: (.+)")

    current_version_match = current_version_pattern.search(output)
    new_version_match = new_version_pattern.search(output)

    if current_version_match:
        options.current_pip_version = current_version_match.group(1)
        logger.info(f"Recovered current pip version: {options.current_pip_version}")
    else:
        logger.warning("Failed to recover current pip version from output.")
    
    if new_version_match:
        options.new_pip_version = new_version_match.group(1)
        logger.info(f"Recovered new pip version: {options.new_pip_version}")
    else:
        logger.warning("Failed to recover new pip version from output.")

def pretty_packages_list(options: Options) -> str:
    maxnum = 5
    if len(options.packages) > maxnum:
        first_five = '-'.join(options.packages[:maxnum])
        suffix = f'-and-{len(options.packages) - maxnum}-more'
    else:
        first_five = '-'.join(options.packages)
        suffix = ''
    
    return first_five + suffix

def setup_virtualenv(options: Options) -> None:
    """Setup a virtual environment and install packages."""
    options.pretty_list = pretty_packages_list(options)
    options.set_venv_dir(os.path.join(options.mypy_dir, f"{options.venv_name}-versionless-{options.timestamp}-{options.pretty_list}"))
    os.makedirs(options.venv_dir, exist_ok=True)

    logger.info(f"Writing packages to {options.requirements_file}")
    with open(options.requirements_file, 'w') as f:
        for package in options.packages:
            f.write(f"{package}\n")

    logger.info("Creating virtual environment...")
    subprocess.check_call([sys.executable, '-m', 'venv', options.venv_dir])
    logger.info("Virtual environment created.")

    # Activate virtual environment and install wheel
    install_command = f"bash -c '{options.activate_script} && {options.venv_pip} install wheel'"
    subprocess.run(install_command, shell=True, check=True)
    logger.info("Wheel installed in the virtual environment.")

    install_packages(options)

def is_virtualenv() -> bool:
    """Check if currently running in a virtual environment."""
    return sys.prefix != sys.base_prefix

def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Run a python script with optional flags.")
    parser.add_argument('script', help="The python script to run.")
    parser.add_argument('script_args', nargs='*', help="Optional arguments for the python script.")
    parser.add_argument('-full', action='store_true', help="Build a virtual environment that can run every python script in this directory.")
    parser.add_argument('-blank-slate', action='store_true', help="Delete everything in ~/mypy/.")
    parser.add_argument('-no-cache', action='store_true', help="Don't use the cache.")
    parser.add_argument('-latest', action='store_true', help="Load the latest venv in the cache which has all the packages needed now.")
    parser.add_argument('-last-used', action='store_true', help="Load the last used venv in the cache, but if that fails try the latest venv which has all the packages needed now.")
    parser.add_argument('-smallest', action='store_true', help="Load the smallest venv in the cache (with the fewest packages) which has all the packages needed now.")
    return parser.parse_args()

def get_file_operations(script_path: str) -> Tuple[List[str], List[str]]:
    """Find files that are read or written."""
    with open(script_path, 'r') as file:
        tree = ast.parse(file.read())

    read_files = []
    write_files = []

    class FileOperationsVisitor(ast.NodeVisitor):
        def visit_Call(self, node):
            # Check if the function called is 'open'
            if isinstance(node.func, ast.Name) and node.func.id == 'open':
                # Get the filename
                if isinstance(node.args[0], ast.Str):
                    filename = node.args[0].s
                elif isinstance(node.args[0], ast.Constant):  # For Python 3.8+
                    filename = node.args[0].value
                else:
                    return

                # Determine if the file is being read or written
                if len(node.args) > 1:
                    if isinstance(node.args[1], ast.Str) or isinstance(node.args[1], ast.Constant):
                        mode = node.args[1].s if isinstance(node.args[1], ast.Str) else node.args[1].value
                    else:
                        return
                else:
                    mode = 'r'  # Default mode

                if 'r' in mode:
                    read_files.append(filename)
                elif 'w' in mode or 'a' in mode or 'x' in mode:
                    write_files.append(filename)

            self.generic_visit(node)

    visitor = FileOperationsVisitor()
    visitor.visit(tree)

    return read_files, write_files

def get_network_operations(script_path: str) -> Tuple[List[str], List[str]]:
    """Find URLs that are downloaded and uploaded"""
    with open(script_path, 'r') as file:
        tree = ast.parse(file.read())

    download_urls = []
    upload_urls = []

    # Regular expression to match URLs
    url_pattern = re.compile(
        r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+'
    )

    class NetworkOperationsVisitor(ast.NodeVisitor):
        def visit_Call(self, node):
            # Check if the function is a requests function
            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                if node.func.value.id == 'requests':
                    if node.func.attr in ['get', 'options', 'head', 'post', 'put', 'patch', 'delete']:
                        if len(node.args) > 0 and isinstance(node.args[0], ast.Str):
                            url = node.args[0].s
                            if node.func.attr == 'get':
                                download_urls.append(url)
                            else:
                                upload_urls.append(url)
                        elif len(node.args) > 0 and isinstance(node.args[0], ast.Constant):  # For Python 3.8+
                            url = node.args[0].value
                            if node.func.attr == 'get':
                                download_urls.append(url)
                            else:
                                upload_urls.append(url)

            # Check if the function is a urllib request function
            elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Attribute):
                if node.func.value.attr in ['urlopen', 'Request']:
                    if len(node.args) > 0 and isinstance(node.args[0], ast.Str):
                        url = node.args[0].s
                        download_urls.append(url)
                    elif len(node.args) > 0 and isinstance(node.args[0], ast.Constant):  # For Python 3.8+
                        url = node.args[0].value
                        download_urls.append(url)

            self.generic_visit(node)

    visitor = NetworkOperationsVisitor()
    visitor.visit(tree)

    return download_urls, upload_urls

def guard_examines(options: Options) -> None:
    """Examine the script to determine what files are read and written, and what URLs are downloaded and uploaded."""
    read_files, write_files = get_file_operations(options.python_script)
    download_urls, upload_urls = get_network_operations(options.python_script)
    if read_files:
        logger.info("Files read:", read_files)
    if write_files:
        logger.info("Files written:", write_files)
    if download_urls:
        logger.info("Download URLs:", download_urls)
    if upload_urls:
        logger.info("Upload URLs:", upload_urls)

def save_options_to_json(options: Options) -> None:
    """Save the options object to a JSON file."""
    options.json_filename = os.path.join(options.script_dir, f"{os.path.basename(options.python_script)}-mypy-last-used-on-{options.timestamp}.json")
    
    # Convert options to a dictionary and handle sets
    options_dict = options.__dict__

    # Identify non-serializable types.
    these_sets = []
    non_serializable = {}
    for key, value in options_dict.items():
        try:
            json.dumps(value)
        except TypeError:
            non_serializable[key] = type(value).__name__
            #logger.info(f"Key '{key}' is of type {type(value).__name__}, so it needs to be modified for JSON serialization.")

    if non_serializable:
        #logger.info("Non-serializable keys being modified for JSON serialization...", non_serializable)
        # Handle non-serializable objects as needed
        for key in non_serializable:
            if non_serializable[key] == 'set':
                options_dict[key] = list(options_dict[key])
                these_sets.append(key)
            elif non_serializable[key] == 'Namespace':
                options_dict[key] = vars(options_dict[key])
            # Add more handling for other types if necessary
    
    options_dict['sets'] = these_sets

    # Write the dictionary to a JSON file
    with open(options.json_filename, 'w') as json_file:
        json.dump(options_dict, json_file, indent=4)

def load_options_from_json(json_file: str) -> Options:
    """Load the options object from a JSON file."""
    with open(json_file, 'r') as file:
        options_dict = json.load(file)
    
    # Create a new Options object and set attributes from the dictionary
    options_FROM_JSON = Options()
    for key, value in options_dict.items():
        setattr(options_FROM_JSON, key, value)
    
    #If "sets" is in options_FROM_JSON, then convert the lists back to sets.
    if 'sets' in options_dict:
        for key in options_dict['sets']:
            setattr(options_FROM_JSON, key, set(getattr(options_FROM_JSON, key)))
    else:
        logger.warning(f"No 'sets' key found in {json_file}.")
    
    logger.info(f"options loaded from {json_file}")
    return options_FROM_JSON

def latest_venv(final_venv_folders: Dict[str, Dict[str, int]]) -> str:
    """Return the folder with the latest timestamp."""
    latest_folder = None
    latest_timestamp = None

    for folder, data in final_venv_folders.items():
        if latest_timestamp is None or data['timestamp'] > latest_timestamp:
            latest_timestamp = data['timestamp']
            latest_folder = folder

    return latest_folder

def smallest_venv(final_venv_folders: Dict[str, Dict[str, int]]) -> str:
    """Return the folder with the fewest packages."""
    smallest_folder = None
    smallest_num_packages = None

    for folder, data in final_venv_folders.items():
        if smallest_num_packages is None or data['num_packages'] < smallest_num_packages:
            smallest_num_packages = data['num_packages']
            smallest_folder = folder

    return smallest_folder

def check_venv_dir(options: Options, options_from_cache: Options) -> bool:
    """Check if the last used venv is still valid."""
    if hasattr(options_from_cache, 'venv_dir'):
        # Check if the last used venv is still valid using isdir:
        if os.path.isdir(options_from_cache.venv_dir):
            if options.uninstalled_imports.issubset(options_from_cache.uninstalled_imports):
                options_from_cache.uninstalled_imports = options.uninstalled_imports
                options_from_cache.packages = list(options.uninstalled_imports)
                print(f"{options_from_cache.packages = }")
                if check_packages_in_venv(options_from_cache):
                    return 1
                else:
                    logger.error(f"The cached venv directory {options_from_cache.venv_dir} failed check_packages_in_venv.")
            else:
                logger.error(f"The cached venv directory {options_from_cache.venv_dir} does not have all the currently required packages.")
        else:
            logger.error(f"The cached venv directory {options_from_cache.venv_dir} is no longer valid.")
    return 0
    
def find_match_dir_in_cache(options: Options) -> str:
    if not options.args.latest and not options.args.last_used and not options.args.smallest:
        options.args.last_used = True #If no flags are set, then the default is to load the last used venv in the cache
    if options.args.last_used and not options.args.latest and not options.args.smallest:
        try: # Try to load the last used venv in the cache
            json_files = [f for f in os.listdir(options.script_dir) if f.startswith(os.path.basename(options.python_script)) and f.endswith('.json')]
            if json_files:
                if len(json_files) > 1:
                    json_files.sort(key=lambda x: x.split('-')[4], reverse=True)
                options_last_used = load_options_from_json(os.path.join(options.script_dir, json_files[0]))
                if check_venv_dir(options, options_last_used):
                    return options_last_used.venv_dir
                else:
                    logger.error("The last used cache is invalid. Trying to load the latest matching venv now.")
        except:
            logger.error("The last used cache encountered a problem. Trying to load the latest matching venv now.")
        options.args.latest    = True #If that didn't work, try to load the latest venv in the cache
        options.args.last_used = False #And set this to False because it failed
    logger.info("Checking the cache for a virtual environment with all the required packages...")
    #Search for all venv_name folders in mypy:
    all_venv_folders = [f for f in os.listdir(options.mypy_dir) if os.path.isdir(os.path.join(options.mypy_dir, f)) and f.startswith(options.venv_name)]
    #Loop through the folders and eliminate folders that clearly don't have the right packages just based on their names:
    venv_folders = []
    for folder in all_venv_folders:
        #Extract the part of the folder name after the date/time:
        pretty_list = folder.split('-')[4:]
        #Create a known_packages set from the pretty_list:
        known_packages = set()
        number_unknown_packages = 0
        for item in pretty_list:
            if item == 'and':
                #Extract the number of unknown packages from the last part of the pretty_list:
                number_unknown_packages = int(pretty_list[-2].split('-')[0])
                break
            known_packages.add(item)
        missing_packages = options.uninstalled_imports - known_packages
        if len(missing_packages) <= number_unknown_packages:
            venv_folders.append(folder)
    #Loop through possibly valid venv folders and compare requirements in detail.
    final_venv_folders = {}
    for folder in venv_folders:
        this_requirements_file = os.path.join(options.mypy_dir, folder, 'requirements.txt')
        with open(this_requirements_file, 'r') as file:
            requirements = set(file.read().splitlines())
        if options.uninstalled_imports.issubset(requirements):
            this_timestamp = folder.split('-')[2]+'-'+folder.split('-')[3]
            final_venv_folders[folder] = {'timestamp': this_timestamp, 'num_packages': len(requirements)}
    if not final_venv_folders:
        logger.info("No matching venv folders found in the cache.")
    else:
        logger.info(f"Found {len(final_venv_folders)} matching venv folders in the cache.")
        if options.args.latest and not options.args.last_used and not options.args.smallest:
            # Return the latest venv in the cache which has all the packages needed now
            options_latest = copy.deepcopy(options)
            options_latest.set_venv_dir(os.path.join(options.mypy_dir, latest_venv(final_venv_folders)))
            options_latest.uninstalled_imports = options.uninstalled_imports
            options_latest.packages = list(options.uninstalled_imports)
            if check_venv_dir(options, options_latest):
                return options_latest.venv_dir
            else:
                logger.error("The latest venv in the cache is invalid. Giving up on the cache and starting from scratch.")
                return None
        elif options.args.smallest and not options.args.latest and not options.args.last_used:
            # Return the smallest venv in the cache which has all the packages needed now
            options_smallest = copy.deepcopy(options)
            options_smallest.set_venv_dir(os.path.join(options.mypy_dir, smallest_venv(final_venv_folders)))
            options_smallest.uninstalled_imports = options.uninstalled_imports
            options_smallest.packages = list(options.uninstalled_imports)
            if check_venv_dir(options, options_smallest):
                return options_smallest.venv_dir
            else:
                logger.error("The smallest venv in the cache is invalid. Giving up on the cache and starting from scratch.")
                return None
        else: # This should never happen
            logger.error(f"Invalid combination of flags. {options.args.latest = }, {options.args.last_used = }, {options.args.smallest = }")

def main():
    start_time = datetime.now()
    options = Options()
    options.args = parse_arguments()
    options.timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')

    if not os.path.isdir(options.mypy_dir):
        logger.warning(f"Directory {options.mypy_dir} does not exist yet, so it is being created.")
        os.makedirs(options.mypy_dir, exist_ok=True)
    if not os.path.isdir(options.packages_dir):
        logger.warning(f"Directory {options.packages_dir} does not exist yet, so it is being created.")
        os.makedirs(options.packages_dir, exist_ok=True)

    options.python_script = options.args.script
    options.script_args = options.args.script_args

    options.script_dir = os.path.abspath(os.path.dirname(options.python_script))
    logger.info(f"Directory where the script to run is located: {options.script_dir}")

    if options.args.full:
        logger.info("Building a virtual environment that can run every python script in this directory.")
        script_dir_or_file = options.script_dir
    else:
        script_dir_or_file = options.python_script

    installed_imports, uninstalled_imports, bad_imports = list_packages(script_dir_or_file)
    options.uninstalled_imports = uninstalled_imports
    options.packages = list(uninstalled_imports)
    logger.info(f"Uninstalled imports: {options.uninstalled_imports}")
    if bad_imports:
        logger.warning(f"Bad imports: {bad_imports}")

    if not uninstalled_imports:
        logger.info("All required packages are already installed.")
        guard_examines(options)
        subprocess.run([sys.executable, options.python_script] + options.script_args)
    elif is_virtualenv():
        logger.info("Already in a virtual environment.")
        if check_packages_in_venv(options):
            guard_examines(options)
            subprocess.run([sys.executable, options.python_script] + options.script_args)
        else:
            logger.error("The current virtual environment does not have all the required packages.")
            logger.info("Please deactivate the current virtual environment and run the script again.")
    else:
        logger.info("Not in a virtual environment.")
        if options.args.no_cache:
            match_dir = None
        else:
            match_dir = find_match_dir_in_cache(options)
        if not match_dir:
            logger.info(f"Creating new virtual environment '{options.venv_name}'...")
            setup_virtualenv(options)
            match_dir = options.venv_dir
        else:
            logger.info(f"Using directory: {match_dir}")

        options.set_venv_dir(match_dir)
        start_venv_time = datetime.now()
        elapsed_time = start_venv_time - start_time
        logger.info(f"Elapsed time: {elapsed_time}")
        logger.info(f"Activating virtual environment: {options.activate_script}")

        activate_cmd = f"bash -c '{options.activate_script} && echo \"Virtual environment activated.\" && {options.venv_python} {options.python_script} {' '.join(options.script_args)}'"
        guard_examines(options)
        subprocess.run(activate_cmd, shell=True)
        end_time = datetime.now()
        elapsed_time = end_time - start_venv_time
        logger.info(f"Elapsed time since activation of virtual environment: {elapsed_time}")
        save_options_to_json(options)

if __name__ == "__main__":
    main()
