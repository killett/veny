#!/usr/bin/env python3

import os
import sys
import subprocess
from datetime import datetime
import argparse
import logging
from typing import Dict, List
from list_required_packages_03 import list_packages
import ast
import re
import json
import requests

class Options():
    '''Class that has all global options in one place.'''
    def __init__(self) -> None:
        self.venv_name: str = 'myenv'
        self.mypy_dir = os.path.expanduser(os.path.join('~','mypy'))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

def get_latest_pip_version() -> str:
    """Get the latest version of pip available on PyPI."""
    response = requests.get('https://pypi.org/pypi/pip/json')
    response.raise_for_status()
    data = response.json()
    return data['info']['version']

def get_local_pip_version(packages_dir: str) -> str:
    """Get the latest version of pip available in the local files."""
    pip_files = [f for f in os.listdir(packages_dir) if f.startswith('pip-') and f.endswith('.whl')]
    if not pip_files:
        return None
    
    # Extract version from filename
    versions = [re.search(r'pip-(.*?)-py3-none-any.whl', f).group(1) for f in pip_files if re.search(r'pip-(.*?)-py3-none-any.whl', f)]
    return max(versions, key=lambda v: [int(part) for part in v.split('.')]) if versions else None

def install_packages(OPTIONS: Options) -> None:
    """Create a script to install packages in a virtual environment."""
    install_script = f"""#!/bin/bash
source {OPTIONS.venv_dir}/bin/activate

# Check the current version of pip
current_pip_version=$(pip --version)
echo "Current pip version: $current_pip_version"
"""

    # Get the latest pip version available on PyPI
    latest_pip_version = get_latest_pip_version()
    logger.info(f"Latest pip version available on PyPI: {latest_pip_version}")

    # Get the current pip version from the environment
    current_pip_version_output = subprocess.check_output(["pip", "--version"], text=True).strip()
    logger.info(f"Current pip version output: {current_pip_version_output}")

    current_pip_version_match = re.search(r'pip (\d+\.\d+(\.\d+)?)', current_pip_version_output)
    if current_pip_version_match:
        current_pip_version = current_pip_version_match.group(1)
        logger.info(f"Currently installed pip version: {current_pip_version}")
    else:
        logger.error("Failed to parse the current pip version.")
        current_pip_version = "0.0.0"  # Fallback to ensure the script continues

    # Get the latest pip version from the local packages
    local_pip_version = get_local_pip_version(OPTIONS.packages_dir)
    logger.info(f"Latest pip version in local files: {local_pip_version}")

    if current_pip_version >= latest_pip_version:
        logger.info("Current pip version is up-to-date. No need to download or install.")
    else:
        if local_pip_version == latest_pip_version:
            logger.info("Local pip version is up-to-date. Installing from local files.")
        else:
            logger.info("Downloading the latest pip version...")
            download_script = f"""
            pip download --only-binary=:all: pip -d {OPTIONS.packages_dir}
            """
            install_script += download_script

        install_script += f"""
        echo "Reinstalling the latest pip version from local files..."
        pip install --force-reinstall --no-index --find-links={OPTIONS.packages_dir} pip

        # Check the new version of pip
        new_pip_version=$(pip --version)
        echo "New pip version: $new_pip_version"
        """

    install_script += f"""
    # Download required packages
    echo "Downloading packages..."
    pip download -r {OPTIONS.requirements_file} -d {OPTIONS.packages_dir}

    # Install packages from the downloaded files
    echo "Installing packages..."
    pip install --no-index --find-links={OPTIONS.packages_dir} -r {OPTIONS.requirements_file}
    """

    install_script_path = os.path.join(OPTIONS.packages_dir, f"install_packages.sh")
    logger.info(f"Writing installation script to {install_script_path}")
    with open(install_script_path, 'w') as f:
        f.write(install_script)
    os.chmod(install_script_path, 0o755)

    # Run the installation script and capture the output
    result = subprocess.run([install_script_path], check=True, capture_output=True, text=True)
    
    logger.info(result.stdout)
    if result.stderr:
        logger.error(result.stderr)

    # Recover pip versions from the output
    recover_pip_versions(result.stdout, OPTIONS)

    # Run the test script
    check_packages_in_venv(OPTIONS)

def recover_pip_versions(output: str, OPTIONS: Options) -> None:
    """Parse the output to recover the current and new pip versions."""
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
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    OPTIONS.pretty_list = pretty_packages_list(OPTIONS)
    OPTIONS.requirements_file = os.path.join(OPTIONS.mypy_dir, f"{OPTIONS.venv_name}-requirements-{timestamp}-versionless-{OPTIONS.pretty_list}.txt")
    OPTIONS.packages_dir = os.path.join(OPTIONS.mypy_dir, f"{OPTIONS.venv_name}-packages-{timestamp}-{OPTIONS.pretty_list}")
    OPTIONS.venv_dir = OPTIONS.packages_dir.replace('packages', 'venv')

    os.makedirs(OPTIONS.packages_dir, exist_ok=True)

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
    logger.error("Need to add script_args to the guard_examines function to let the guard know what the command line arguments are.")
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

def save_options_to_json(OPTIONS: Options) -> None:
    """Save the OPTIONS object to a JSON file."""
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    OPTIONS.json_filename = os.path.join(OPTIONS.script_dir, f"{os.path.basename(OPTIONS.python_script)}-mypy-{timestamp}.json")
    
    # Convert OPTIONS to a dictionary
    options_dict = OPTIONS.__dict__
    
    # Write the dictionary to a JSON file
    with open(OPTIONS.json_filename, 'w') as json_file:
        json.dump(options_dict, json_file, indent=4)
    
    logger.info(f"OPTIONS saved to {OPTIONS.json_filename}")

def load_options_from_json(json_file: str) -> Options:
    """Load the OPTIONS object from a JSON file."""
    with open(json_file, 'r') as file:
        options_dict = json.load(file)
    
    # Create a new Options object and set attributes from the dictionary
    options = Options()
    for key, value in options_dict.items():
        setattr(options, key, value)
    
    logger.info(f"OPTIONS loaded from {json_file}")
    return options

def main():
    args = parse_arguments()

    OPTIONS = Options()
    if not os.path.isdir(OPTIONS.mypy_dir):
        logger.error(f"Directory {OPTIONS.mypy_dir} does not exist yet, so it is being created.")
        os.makedirs(OPTIONS.mypy_dir, exist_ok=True)
        
    OPTIONS.python_script = args.script
    OPTIONS.script_args = args.script_args

    OPTIONS.script_dir = os.path.abspath(os.path.dirname(OPTIONS.python_script))
    logger.info(f"Directory where the script to run is located: {OPTIONS.script_dir}")

    if args.full:
        logger.info("Building a virtual environment that can run every python script in this directory.")
        script_dir_or_file = OPTIONS.script_dir
    else:
        script_dir_or_file = OPTIONS.python_script

    installed_imports, uninstalled_imports, bad_imports = list_packages(script_dir_or_file)
    OPTIONS.uninstalled_imports = uninstalled_imports
    OPTIONS.packages = list(uninstalled_imports)
    logger.info(f"Uninstalled imports: {OPTIONS.uninstalled_imports}")
    if bad_imports:
        logger.error(f"Bad imports: {bad_imports}")

    if is_virtualenv():
        logger.info("Already in a virtual environment.")
        packages_available = check_packages_in_venv(uninstalled_imports, OPTIONS)
        if packages_available:
            logger.error("Need to add script_args to the guard_examines function to let the guard know what the command line arguments are.")
            guard_examines(OPTIONS)
            subprocess.run([sys.executable, OPTIONS.python_script] + OPTIONS.script_args)
        else:
            logger.error("The current virtual environment does not have all the required packages.")
            logger.info("Please deactivate the current virtual environment and run the script again.")
    else:
        logger.info("Not in a virtual environment.")
        match_found = False
        match_dir = ""
        if not args.no_cache:
            logger.info("Checking the cache for a virtual environment with all the required packages...")
            if not args.latest and not args.last_used and not args.smallest:
                args.last_used = True #If no flags are set, then the default is to load the last used venv in the cache
            if args.last_used and not args.latest and not args.smallest:
                # Load the last used venv in the cache
                try:
                    # Load the last used venv in the cache
                    match_found = True
                    match_dir = os.path.join(OPTIONS.mypy_dir, 'last_used')
                    pass
                except:
                    logger.error("The last used cache encountered a problem. Trying to load the latest matching venv now.")
                    args.latest    = True #If that didn't work, try to load the latest venv in the cache
                    args.last_used = False #And set this to False so the next if-statement will run
            if args.latest and not args.last_used and not args.smallest:
                # Load the latest venv in the cache which has all the packages needed now
                match_found = True
                match_dir = os.path.join(OPTIONS.mypy_dir, 'latest')
                pass
            elif args.smallest and not args.latest and not args.last_used:
                # Load the smallest venv in the cache which has all the packages needed now
                match_found = True
                match_dir = os.path.join(OPTIONS.mypy_dir, 'smallest')
                pass
            else: # This should never happen
                logger.error(f"Invalid combination of flags. {args.latest = }, {args.last_used = }, {args.smallest = }")
        if not match_found:
            logger.info(f"Creating new virtual environment '{OPTIONS.venv_name}'...")
            setup_virtualenv(OPTIONS)
        else:
            logger.info(f"{OPTIONS.venv_name} directory already exists in {match_dir}.")

        activate_script = os.path.join(OPTIONS.script_dir, OPTIONS.venv_name, 'bin', 'activate')
        venv_python = os.path.join(OPTIONS.script_dir, OPTIONS.venv_name, 'bin', 'python')
        logger.info(f"Activating virtual environment: {activate_script}")

        activate_cmd = f"bash -c 'source {activate_script} && echo \"Virtual environment activated.\" && {venv_python} {OPTIONS.python_script} {' '.join(OPTIONS.script_args)}'"
        logger.info(f"{activate_cmd = }")
        logger.error("Need to add script_args to the guard_examines function to let the guard know what the command line arguments are.")
        guard_examines(OPTIONS)
        subprocess.run(activate_cmd, shell=True)

if __name__ == "__main__":
    main()
