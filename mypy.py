#!/usr/bin/env python3

import os
import sys
import subprocess

from list_required_packages import list_packages

def setup_virtualenv(packages, script_dir, venv_name='myenv'):

    # Write the packages to requirements.txt
    print(f"Writing packages to {os.path.join(script_dir, 'requirements.txt')}")
    with open(os.path.join(script_dir, 'requirements.txt'), 'w') as f:
        for package in packages:
            f.write(f"{package}\n")

    # Create virtual environment
    print("Creating virtual environment...")
    subprocess.check_call([sys.executable, '-m', 'venv', venv_name])
    print("Virtual environment created.")

    # Create install_packages.sh script
    install_script = f"""#!/bin/bash
source {venv_name}/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
"""

    script_path = os.path.join(script_dir, 'install_packages.sh')
    with open(script_path, 'w') as f:
        f.write(install_script)
    
    # Make the script executable
    os.chmod(script_path, 0o755)
    print("Install packages script created and made executable.")

    # Execute the shell script
    try:
        subprocess.check_call(['/bin/bash', script_path])
        print("Packages installed.")
    except subprocess.CalledProcessError as e:
        print(f"Error during virtual environment setup: {e}")
        print(f"Command output: {e.output}")

def is_virtualenv():
    return sys.prefix != sys.base_prefix

def main():
    if len(sys.argv) < 2:
        print("Usage: mypy <script.py> [args]")
        sys.exit(1)

    script = sys.argv[1]
    script_args = sys.argv[2:]

    # Print the directory name where the script to be run is located
    script_dir = os.path.abspath(os.path.dirname(script))
    print(f"Directory where the script to run is located: {script_dir}")

    # List of local imports that I've created
    print("!!! GET RID OF THIS LIST AND CHANGE THIS TO A SYSTEM THAT LOOKS FOR THESE FILES WITH THE .py EXTENSION SOMEWHERE IN THE PATH!!!")
    local_imports = ['univ_defs', 'search_for_media_files', 'kill_switch', 'list_required_packages']

    installed_imports, uninstalled_imports = list_packages(script_dir, local_imports)

    print(f"  Installed Imports: {installed_imports}\n")
    print(f"Uninstalled Imports: {uninstalled_imports}")
    print(f"Script to run: {script}")
    print(f"Script arguments: {script_args}")

    if is_virtualenv():
        print("Already in a virtual environment.")
        # Already in a virtual environment, run the script
        subprocess.run([sys.executable, script] + script_args)
    else:
        print("Not in a virtual environment.")
        if not os.path.isdir('myenv'):
            print("Creating virtual environment 'myenv'...")
            setup_virtualenv(list(uninstalled_imports), script_dir)
        else:
            print("'myenv' directory already exists.")

        # Activate the virtual environment
        activate_script = os.path.join('myenv', 'bin', 'activate')
        venv_python = os.path.join('myenv', 'bin', 'python')
        print(f"Activating virtual environment: {activate_script}")

        # Additional debug statement before activation
        activate_cmd = f"bash -c 'source {activate_script} && echo \"Virtual environment activated.\" && {venv_python} {script} {' '.join(script_args)}'"
        print(f"Activation command: {activate_cmd}")
        subprocess.run(activate_cmd, shell=True)

if __name__ == "__main__":
    main()
