#!/usr/bin/env python3

import os
import sys
import subprocess
from datetime import datetime
import argparse
import logging
from list_required_packages_03 import list_packages

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def install_packages(packages, requirements_file, packages_dir, venv_name):
    """Create a script to install packages in a virtual environment."""
    install_script = f"""#!/bin/bash
source {venv_name}/bin/activate
pip install --upgrade pip
pip download -r {requirements_file} -d {packages_dir}
pip install --no-index --find-links={packages_dir} -r {requirements_file}
"""

    install_script_path = os.path.join(packages_dir, f"install_packages.sh")
    with open(install_script_path, 'w') as f:
        f.write(install_script)
    os.chmod(install_script_path, 0o755)

    # Run the installation script
    subprocess.run([install_script_path], check=True)

def setup_virtualenv(packages, script_dir, venv_name):
    """Setup a virtual environment and install packages."""
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    requirements_file = os.path.join(script_dir, f"requirements-{timestamp}.txt")
    packages_dir = os.path.join(script_dir, f"{venv_name}-packages")

    os.makedirs(packages_dir, exist_ok=True)

    logger.info(f"Writing packages to {requirements_file}")
    with open(requirements_file, 'w') as f:
        for package in packages:
            f.write(f"{package}\n")

    logger.info("Creating virtual environment...")
    subprocess.check_call([sys.executable, '-m', 'venv', venv_name])
    logger.info("Virtual environment created.")

    install_packages(packages, requirements_file, packages_dir, venv_name)

def is_virtualenv():
    """Check if currently running in a virtual environment."""
    return sys.prefix != sys.base_prefix

def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Run a Python script with optional flags.")
    parser.add_argument('script', help="The Python script to run.")
    parser.add_argument('script_args', nargs=argparse.REMAINDER, help="Arguments for the Python script.")
    parser.add_argument('-full', action='store_true', help="Build a virtual environment that can run every python script in this directory.")
    parser.add_argument('-wipe', action='store_true', help="Delete all directories matching a certain pattern.")
    return parser.parse_args()

def main():
    args = parse_arguments()

    venv_name = 'myenv'
    script = args.script
    script_args = args.script_args

    script_dir = os.path.abspath(os.path.dirname(script))
    logger.info(f"Directory where the script to run is located: {script_dir}")

    if args.full:
        logger.info("Building a virtual environment that can run every python script in this directory.")
        script_dir_or_file = script_dir
    else:
        script_dir_or_file = script

    bad_imports = ['bs4', 'snakeClass', 'seaborn', 'tkinter', 'msvcrt', 'univ_defs', 'search_for_media_files', 'kill_switch', 'list_required_packages']

    installed_imports, uninstalled_imports = list_packages(script_dir_or_file, bad_imports)
    logger.info(f"Uninstalled Imports: {uninstalled_imports}")

    if is_virtualenv():
        logger.info("Already in a virtual environment.")
        subprocess.run([sys.executable, script] + script_args)
    else:
        logger.info("Not in a virtual environment.")
        if not os.path.isdir(os.path.join(script_dir, venv_name)):
            logger.info(f"Creating virtual environment '{venv_name}'...")
            setup_virtualenv(list(uninstalled_imports), script_dir, venv_name)
        else:
            logger.info(f"{venv_name} directory already exists in {script_dir}.")

        activate_script = os.path.join(script_dir, venv_name, 'bin', 'activate')
        venv_python = os.path.join(script_dir, venv_name, 'bin', 'python')
        logger.info(f"Activating virtual environment: {activate_script}")

        activate_cmd = f"bash -c 'source {activate_script} && echo \"Virtual environment activated.\" && {venv_python} {script} {' '.join(script_args)}'"
        subprocess.run(activate_cmd, shell=True)

if __name__ == "__main__":
    main()
