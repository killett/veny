#!/usr/bin/env python3

import os
import sys
import subprocess
from datetime import datetime
import argparse
import logging
import ast
import re
import json
from typing import Dict, List, Set, Tuple

class Options():
    '''Class that has all global options in one place.'''
    def __init__(self) -> None:
        self.venv_name: str = 'myenv' # Can NOT include dashes ('-')
        self.mypy_dir = os.path.expanduser(os.path.join('~','mypy'))
        self.packages_dir = os.path.join(self.mypy_dir, 'packages')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Attempt to import pipreqs
try:
    import pipreqs
    logger.info("NOTE: pipreqs is available.")
    PIPREQS_AVAILABLE = True
except ImportError:
    logger.warning("NOTE: pipreqs is not available. Try installing it with 'pip install pipreqs'.")
    PIPREQS_AVAILABLE = False

def find_imports_in_script(file_path: str, all_imports: Set[str]) -> None:
    with open(file_path, 'r') as file:
        lines = file.readlines()
        for line in lines:
            line = line.strip()
            if '#' in line:
                line = line.split('#')[0].strip()  # Remove comments from the line

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
    known_bad_imports = {'bs4', 'snakeClass', 'pathfinding_salvo_rework', 'seaborn', 'tkinter', 'msvcrt', 'univ_defs', 'search_for_media_files', 'kill_switch', 'list_required_packages', 'crossover'}
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

    # Expand '~' to the full path
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

    installed_imports, uninstalled_imports, bad_imports = split_imports(all_imports)

    return installed_imports, uninstalled_imports, bad_imports

def check_packages_in_venv(OPTIONS: Options) -> bool:
    """Create and run a script to test package imports in the virtual environment."""
    packages_str = ", ".join(f"'{pkg}'" for pkg in OPTIONS.packages)  # Properly format the list of packages as strings
    test_script = f"""#!/bin/bash
source {OPTIONS.venv_name}/bin/activate
python - << END
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

    test_script_path = os.path.join(OPTIONS.script_dir, f"test_imports.sh")
    logger.info(f"Writing test script to {test_script_path}")
    with open(test_script_path, 'w') as f:
        f.write(test_script)
    os.chmod(test_script_path, 0o755)

    # Run the test script
    result = subprocess.run([test_script_path], check=True, capture_output=True, text=True)
    logger.info(result.stdout)
    if result.stderr:
        logger.error(result.stderr)
    
    # This returns true if all packages imported successfully
    return "packages imported successfully" in result.stdout 

def install_packages(OPTIONS: Options) -> None:
    """Create a script to install packages in a virtual environment."""
    install_script = f"""#!/bin/bash
source {OPTIONS.venv_dir}/bin/activate

# Check the current version of pip
current_pip_version=$(pip --version | grep -oP '\\d+\\.\\d+(\\.\\d+)?' | head -1)
echo "Current pip version: $current_pip_version"

# Get the latest pip version available on PyPI
latest_pip_version=$(curl -s https://pypi.org/pypi/pip/json | python3 -c "import sys, json; print(json.load(sys.stdin)['info']['version'])")
echo "Latest pip version available on PyPI: $latest_pip_version"

# Get the latest pip version from the local packages
echo "Checking for local pip files in {OPTIONS.packages_dir}..."
if ls {OPTIONS.packages_dir}/pip-*.whl 1> /dev/null 2>&1; then
    echo "Local pip files found."
    ls {OPTIONS.packages_dir}/pip-*.whl
    local_pip_version=$(ls {OPTIONS.packages_dir}/pip-*.whl | grep -oP 'pip-\\K[0-9]+\\.[0-9]+(\\.[0-9]+)?(?=-py3-none-any\\.whl)' | sort -V | tail -1)
    echo "Extracted local pip version: $local_pip_version"
else
    echo "No local pip files found."
    local_pip_version=""
fi
echo "Latest pip version in local files: $local_pip_version"

# Compare versions and decide whether to download and install
if [ "$current_pip_version" = "$latest_pip_version" ]; then
    echo "Current pip version is up-to-date. No need to download or install."
else
    if [ "$local_pip_version" = "$latest_pip_version" ]; then
        echo "Local pip version is up-to-date. Installing from local files."
    else
        echo "Downloading the latest pip version..."
        pip download --only-binary=:all: pip -d {OPTIONS.packages_dir}
    fi

    echo "Reinstalling the latest pip version from local files..."
    pip install --force-reinstall --no-index --find-links={OPTIONS.packages_dir} pip

    # Check the new version of pip
    new_pip_version=$(pip --version | grep -oP '\\d+\\.\\d+(\\.\\d+)?' | head -1)
    echo "New pip version: $new_pip_version"
fi

# Download required packages
echo "Downloading packages..."
pip download -r {OPTIONS.requirements_file} -d {OPTIONS.packages_dir}

# Install packages from the downloaded files
echo "Installing packages..."
pip install --no-index --find-links={OPTIONS.packages_dir} -r {OPTIONS.requirements_file}
"""

    OPTIONS.install_script_path = os.path.join(OPTIONS.venv_dir, f"install_packages.sh")
    logger.info(f"Writing installation script to {OPTIONS.install_script_path}")
    with open(OPTIONS.install_script_path, 'w') as f:
        f.write(install_script)
    os.chmod(OPTIONS.install_script_path, 0o755)

    # Run the installation script and capture the output
    process = subprocess.Popen(
        [OPTIONS.install_script_path], 
        stdout=subprocess.PIPE, 
        stderr=subprocess.PIPE, 
        text=True
    )

    # Initialize an empty string to capture the output
    captured_output = ""

    # Log stdout and stderr as they are produced
    for line in iter(process.stdout.readline, ''):
        logger.info(line.strip())
        captured_output += line

    for line in iter(process.stderr.readline, ''):
        logger.error(line.strip())
        captured_output += line

    # Wait for the process to complete
    process.stdout.close()
    process.stderr.close()
    process.wait()

    # Recover pip versions from the captured output
    recover_pip_versions(captured_output, OPTIONS)

    # Run the test script
    check_packages_in_venv(OPTIONS)

def recover_pip_versions(output: str, OPTIONS: Options) -> None:
    """Parse the output to recover the current and new pip versions."""
    if hasattr(output, 'read'):
        output = output.read()
    current_version_pattern = re.compile(r"Current pip version: (.+)")
    new_version_pattern = re.compile(r"New pip version: (.+)")

    current_version_match = current_version_pattern.search(output)
    new_version_match = new_version_pattern.search(output)

    if current_version_match:
        OPTIONS.current_pip_version = current_version_match.group(1)
        logger.info(f"Recovered current pip version: {OPTIONS.current_pip_version}")
    else:
        logger.warning("Failed to recover current pip version from output.")
    
    if new_version_match:
        OPTIONS.new_pip_version = new_version_match.group(1)
        logger.info(f"Recovered new pip version: {OPTIONS.new_pip_version}")
    else:
        logger.warning("Failed to recover new pip version from output.")

def pretty_packages_list(OPTIONS: Options) -> str:
    maxnum = 5
    if len(OPTIONS.packages) > maxnum:
        first_five = '-'.join(OPTIONS.packages[:maxnum])
        suffix = f'-and-{len(OPTIONS.packages) - maxnum}-more'
    else:
        first_five = '-'.join(OPTIONS.packages)
        suffix = ''
    
    return first_five + suffix

def setup_virtualenv(OPTIONS: Options) -> None:
    """Setup a virtual environment and install packages."""
    OPTIONS.pretty_list = pretty_packages_list(OPTIONS)
    OPTIONS.venv_dir = os.path.join(OPTIONS.mypy_dir, f"{OPTIONS.venv_name}-versionless-{OPTIONS.timestamp}-{OPTIONS.pretty_list}")
    OPTIONS.requirements_file = os.path.join(OPTIONS.venv_dir, "requirements.txt")

    os.makedirs(OPTIONS.venv_dir, exist_ok=True)

    logger.info(f"Writing packages to {OPTIONS.requirements_file}")
    with open(OPTIONS.requirements_file, 'w') as f:
        for package in OPTIONS.packages:
            f.write(f"{package}\n")

    logger.info("Creating virtual environment...")
    subprocess.check_call([sys.executable, '-m', 'venv', OPTIONS.venv_dir])
    logger.info("Virtual environment created.")

    install_packages(OPTIONS)

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

def get_file_operations(script_path):
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

def get_network_operations(script_path):
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

def guard_examines(OPTIONS: Options) -> None:
    """Examine the script to determine what files are read and written, and what URLs are downloaded and uploaded."""
    read_files, write_files = get_file_operations(OPTIONS.python_script)
    download_urls, upload_urls = get_network_operations(OPTIONS.python_script)
    if read_files:
        logger.info("Files read:", read_files)
    if write_files:
        logger.info("Files written:", write_files)
    if download_urls:
        logger.info("Download URLs:", download_urls)
    if upload_urls:
        logger.info("Upload URLs:", upload_urls)

def save_options_to_json(OPTIONS) -> None:
    """Save the OPTIONS object to a JSON file."""
    OPTIONS.json_filename = os.path.join(OPTIONS.script_dir, f"{os.path.basename(OPTIONS.python_script)}-mypy-last-used-on-{OPTIONS.timestamp}.json")
    
    # Convert OPTIONS to a dictionary and handle sets
    options_dict = OPTIONS.__dict__

    # Identify non-serializable types.
    these_sets = []
    non_serializable = {}
    for key, value in options_dict.items():
        try:
            json.dumps(value)
        except TypeError:
            non_serializable[key] = type(value).__name__
            logger.info(f"Key '{key}' is of type {type(value).__name__}, so it needs to be modified for JSON serialization.")

    if non_serializable:
        logger.info("Non-serializable keys being modified for JSON serialization...", non_serializable)
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
    with open(OPTIONS.json_filename, 'w') as json_file:
        json.dump(options_dict, json_file, indent=4)

def load_options_from_json(json_file: str) -> Options:
    """Load the OPTIONS object from a JSON file."""
    with open(json_file, 'r') as file:
        options_dict = json.load(file)
    
    # Create a new Options object and set attributes from the dictionary
    OPTIONS_FROM_JSON = Options()
    for key, value in options_dict.items():
        setattr(OPTIONS_FROM_JSON, key, value)
    
    #If "sets" is in OPTIONS_FROM_JSON, then convert the lists back to sets.
    if 'sets' in options_dict:
        for key in options_dict['sets']:
            setattr(OPTIONS_FROM_JSON, key, set(getattr(OPTIONS_FROM_JSON, key)))
    else:
        logger.warning(f"No 'sets' key found in {json_file}.")
    
    logger.info(f"OPTIONS loaded from {json_file}")
    return OPTIONS_FROM_JSON

def latest_venv(final_venv_folders):
    latest_folder = None
    latest_timestamp = None

    for folder, data in final_venv_folders.items():
        if latest_timestamp is None or data['timestamp'] > latest_timestamp:
            latest_timestamp = data['timestamp']
            latest_folder = folder

    return latest_folder

def smallest_venv(final_venv_folders):
    smallest_folder = None
    smallest_num_packages = None

    for folder, data in final_venv_folders.items():
        if smallest_num_packages is None or data['num_packages'] < smallest_num_packages:
            smallest_num_packages = data['num_packages']
            smallest_folder = folder

    return smallest_folder

def find_match_dir_in_cache(OPTIONS: Options) -> str:
    if not OPTIONS.args.latest and not OPTIONS.args.last_used and not OPTIONS.args.smallest:
        OPTIONS.args.last_used = True #If no flags are set, then the default is to load the last used venv in the cache
    if OPTIONS.args.last_used and not OPTIONS.args.latest and not OPTIONS.args.smallest:
        try: # Try to load the last used venv in the cache
            json_files = [f for f in os.listdir(OPTIONS.script_dir) if f.startswith(os.path.basename(OPTIONS.python_script)) and f.endswith('.json')]
            if json_files:
                if len(json_files) > 1:
                    json_files.sort(key=lambda x: x.split('-')[4], reverse=True)
                OPTIONS_LAST_USED = load_options_from_json(os.path.join(OPTIONS.script_dir, json_files[0]))
                if hasattr(OPTIONS_LAST_USED, 'venv_dir'):
                    # Check if the last used venv is still valid using isdir:
                    if os.path.isdir(OPTIONS_LAST_USED.venv_dir):
                        return OPTIONS_LAST_USED.venv_dir
                    else:
                        logger.error(f"The last used venv directory {OPTIONS_LAST_USED.venv_dir} is no longer valid.")
        except:
            logger.error("The last used cache encountered a problem. Trying to load the latest matching venv now.")
        OPTIONS.args.latest    = True #If that didn't work, try to load the latest venv in the cache
        OPTIONS.args.last_used = False #And set this to False because it failed
    logger.info("Checking the cache for a virtual environment with all the required packages...")
    #Search for all venv_name folders in mypy:
    all_venv_folders = [f for f in os.listdir(OPTIONS.mypy_dir) if os.path.isdir(os.path.join(OPTIONS.mypy_dir, f)) and f.startswith(OPTIONS.venv_name)]
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
        missing_packages = OPTIONS.uninstalled_imports - known_packages
        if len(missing_packages) <= number_unknown_packages:
            venv_folders.append(folder)
    #Loop through possibly valid venv folders and compare requirements in detail.
    final_venv_folders = {}
    for folder in venv_folders:
        this_requirements_file = os.path.join(OPTIONS.mypy_dir, folder, 'requirements.txt')
        with open(this_requirements_file, 'r') as file:
            requirements = set(file.read().splitlines())
        if OPTIONS.uninstalled_imports.issubset(requirements):
            this_timestamp = folder.split('-')[2]+'-'+folder.split('-')[3]
            final_venv_folders[folder] = {'timestamp': this_timestamp, 'num_packages': len(requirements)}
    if not final_venv_folders:
        logger.info("No matching venv folders found in the cache.")
    else:
        logger.info(f"Found {len(final_venv_folders)} matching venv folders in the cache.")
        if OPTIONS.args.latest and not OPTIONS.args.last_used and not OPTIONS.args.smallest:
            # Return the latest venv in the cache which has all the packages needed now
            return os.path.join(OPTIONS.mypy_dir, latest_venv(final_venv_folders))
        elif OPTIONS.args.smallest and not OPTIONS.args.latest and not OPTIONS.args.last_used:
            # Return the smallest venv in the cache which has all the packages needed now
            return os.path.join(OPTIONS.mypy_dir, smallest_venv(final_venv_folders))
        else: # This should never happen
            logger.error(f"Invalid combination of flags. {OPTIONS.args.latest = }, {OPTIONS.args.last_used = }, {OPTIONS.args.smallest = }")

def main():

    OPTIONS = Options()
    OPTIONS.args = parse_arguments()
    OPTIONS.timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')

    if not os.path.isdir(OPTIONS.mypy_dir):
        logger.warning(f"Directory {OPTIONS.mypy_dir} does not exist yet, so it is being created.")
        os.makedirs(OPTIONS.mypy_dir, exist_ok=True)
    if not os.path.isdir(OPTIONS.packages_dir):
        logger.warning(f"Directory {OPTIONS.packages_dir} does not exist yet, so it is being created.")
        os.makedirs(OPTIONS.packages_dir, exist_ok=True)

    OPTIONS.python_script = OPTIONS.args.script
    OPTIONS.script_args = OPTIONS.args.script_args

    OPTIONS.script_dir = os.path.abspath(os.path.dirname(OPTIONS.python_script))
    logger.info(f"Directory where the script to run is located: {OPTIONS.script_dir}")

    if OPTIONS.args.full:
        logger.info("Building a virtual environment that can run every python script in this directory.")
        script_dir_or_file = OPTIONS.script_dir
    else:
        script_dir_or_file = OPTIONS.python_script

    installed_imports, uninstalled_imports, bad_imports = list_packages(script_dir_or_file)
    OPTIONS.uninstalled_imports = uninstalled_imports
    OPTIONS.packages = list(uninstalled_imports)
    logger.info(f"Uninstalled imports: {OPTIONS.uninstalled_imports}")
    if bad_imports:
        logger.warning(f"Bad imports: {bad_imports}")

    if not uninstalled_imports:
        logger.info("All required packages are already installed.")
        guard_examines(OPTIONS)
        subprocess.run([sys.executable, OPTIONS.python_script] + OPTIONS.script_args)
    elif is_virtualenv():
        logger.info("Already in a virtual environment.")
        packages_available = check_packages_in_venv(uninstalled_imports, OPTIONS)
        if packages_available: #This should never happen because if it runs that means uninstalled_imports is empty, so the previous code block would have run. Paranoia!
            guard_examines(OPTIONS)
            subprocess.run([sys.executable, OPTIONS.python_script] + OPTIONS.script_args)
        else:
            logger.error("The current virtual environment does not have all the required packages.")
            logger.info("Please deactivate the current virtual environment and run the script again.")
    else:
        logger.info("Not in a virtual environment.")
        if OPTIONS.args.no_cache:
            match_dir = None
        else:
            match_dir = find_match_dir_in_cache(OPTIONS)
        if not match_dir:
            logger.info(f"Creating new virtual environment '{OPTIONS.venv_name}'...")
            setup_virtualenv(OPTIONS)
            match_dir = OPTIONS.venv_dir
        else:
            logger.info(f"Using {OPTIONS.venv_name} directory: {match_dir}")

        OPTIONS.venv_dir = match_dir
        activate_script = os.path.join(match_dir, 'bin', 'activate')
        venv_python = os.path.join(OPTIONS.script_dir, OPTIONS.venv_name, 'bin', 'python')
        logger.info(f"Activating virtual environment: {activate_script}")

        activate_cmd = f"bash -c 'source {activate_script} && echo \"Virtual environment activated.\" && {venv_python} {OPTIONS.python_script} {' '.join(OPTIONS.script_args)}'"
        guard_examines(OPTIONS)
        subprocess.run(activate_cmd, shell=True)
        save_options_to_json(OPTIONS)

if __name__ == "__main__":
    main()
