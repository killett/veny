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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_packages_in_venv(packages: List[str], options: Dict[str, str], script_dir: str) -> bool:
    """Create and run a script to test package imports in the virtual environment."""
    packages_str = ", ".join(f"'{pkg}'" for pkg in packages)  # Properly format the list of packages as strings
    test_script = f"""#!/bin/bash
source {options['venv_name']}/bin/activate
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
elif len(successes) != counter:
    print(f"Warning: Recorded {{len(successes)}} successes out of {{counter}} times through the loop.")
else:
    print(f"All {{len(successes)}} out of {{counter}} packages imported successfully.")
END
"""

    test_script_path = os.path.join(script_dir, f"test_imports.sh")
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

def install_packages(options: Dict[str, str]) -> None:
    """Create a script to install packages in a virtual environment."""
    install_script = f"""#!/bin/bash
source {options['venv_name']}/bin/activate
pip install --upgrade pip
pip download -r {requirements_file} -d {packages_dir}
pip install --no-index --find-links={packages_dir} -r {requirements_file}
"""

    install_script_path = os.path.join(packages_dir, f"install_packages.sh")
    logger.info(f"Writing installation script to {install_script_path}")
    with open(install_script_path, 'w') as f:
        f.write(install_script)
    os.chmod(install_script_path, 0o755)

    # Run the installation script
    subprocess.run([install_script_path], check=True)

    # Run the test script
    check_packages_in_venv(packages, options, packages_dir)

def pretty_packages_list(packages: List[str]) -> str:
    maxnum = 5
    if len(packages) > maxnum:
        first_five = '-'.join(packages[:maxnum])
        suffix = f'-and-{len(packages) - maxnum}-more'
    else:
        first_five = '-'.join(packages)
        suffix = ''
    
    return first_five + suffix

def setup_virtualenv(packages: List[str], script_dir: str, options: Dict[str, str]) -> None:
    """Setup a virtual environment and install packages."""
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    options['pretty_list'] = pretty_packages_list(packages)
    options['requirements_file'] = os.path.join(options['mypy_dir'], f"{options['venv_name']}-requirements-{timestamp}-versionless-{options['pretty_list']}.txt")
    options['packages_dir'] = os.path.join(options['mypy_dir'], f"{options['venv_name']}-packages-{timestamp}-{options['pretty_list']}")
    options['venv_dir'] = options['packages_dir'].replace('packages', 'venv')

    os.makedirs(options['packages_dir'], exist_ok=True)

    logger.info(f"Writing packages to {options['requirements_file']}")
    with open(options['requirements_file'], 'w') as f:
        for package in packages:
            f.write(f"{package}\n")

    logger.info("Creating virtual environment...")
    subprocess.check_call([sys.executable, '-m', 'venv', options['venv_dir']])
    logger.info("Virtual environment created.")

    install_packages(packages, requirements_file, packages_dir, options)

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

def main():
    args = parse_arguments()

    options = {}
    options['venv_name']        = 'myenv'
    options['mypy_dir']         = os.path.expanduser(os.path.join('~','mypy'))
    #options['packages_dir']     = os.path.join(options['mypy_dir'], 'offline-packages')
    #options['requirements_dir'] = os.path.join(options['mypy_dir'], 'requirements')
    for key, value in options.items():
        if key != 'venv_name' and not os.path.isdir(value):
            logger.error(f"{key} directory {value} does not exist yet, so it is being created.")
            os.makedirs(value)
        
    options['script'] = args.script
    options['script_args'] = args.script_args

    options['script_dir'] = os.path.abspath(os.path.dirname(options['script']))
    logger.info(f"Directory where the script to run is located: {options['script_dir']}")

    if args.full:
        logger.info("Building a virtual environment that can run every python script in this directory.")
        script_dir_or_file = options['script_dir']
    else:
        script_dir_or_file = options['script']

    installed_imports, uninstalled_imports, bad_imports = list_packages(script_dir_or_file)
    logger.info(f"Uninstalled imports: {uninstalled_imports}")
    if bad_imports:
        logger.error(f"Bad imports: {bad_imports}")


    if is_virtualenv():
        logger.info("Already in a virtual environment.")
        packages_available = check_packages_in_venv(uninstalled_imports, options, options['script_dir'])
        if packages_available:
            subprocess.run([sys.executable, options['script']] + options['script_args'])
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
                    match_dir = os.path.join(options['mypy_dir'], 'last_used')
                    pass
                except:
                    logger.error("The last used cache encountered a problem. Trying to load the latest matching venv now.")
                    args.latest    = True #If that didn't work, try to load the latest venv in the cache
                    args.last_used = False #And set this to False so the next if-statement will run
            if args.latest and not args.last_used and not args.smallest:
                # Load the latest venv in the cache which has all the packages needed now
                match_found = True
                match_dir = os.path.join(options['mypy_dir'], 'latest')
                pass
            elif args.smallest and not args.latest and not args.last_used:
                # Load the smallest venv in the cache which has all the packages needed now
                match_found = True
                match_dir = os.path.join(options['mypy_dir'], 'smallest')
                pass
            else: # This should never happen
                logger.error(f"Invalid combination of flags. {args.latest = }, {args.last_used = }, {args.smallest = }")
        if not match_found:
            logger.info(f"Creating new virtual environment '{options['venv_name']}'...")
            setup_virtualenv(list(uninstalled_imports), script_dir, options)
        else:
            logger.info(f"{options['venv_name']} directory already exists in {match_dir}.")

        activate_script = os.path.join(script_dir, options['venv_name'], 'bin', 'activate')
        venv_python = os.path.join(script_dir, options['venv_name'], 'bin', 'python')
        logger.info(f"Activating virtual environment: {activate_script}")

        activate_cmd = f"bash -c 'source {activate_script} && echo \"Virtual environment activated.\" && {venv_python} {script} {' '.join(script_args)}'"
        logger.info(f"{activate_cmd = }")
        # Guard:
        read_files, write_files = get_file_operations(script)
        download_urls, upload_urls = get_network_operations(script)
        if read_files:
            logger.info("Files read:", read_files)
        if write_files:
            logger.info("Files written:", write_files)
        if download_urls:
            logger.info("Download URLs:", download_urls)
        if upload_urls:
            logger.info("Upload URLs:", upload_urls)

        #breakpoint()
        subprocess.run(activate_cmd, shell=True)

if __name__ == "__main__":
    main()
