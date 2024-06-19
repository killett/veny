#!/usr/bin/env python3

import os
import sys
import subprocess
import time

def setup_virtualenv(packages, venv_name='myenv'):
    # Write the packages to requirements.txt
    with open('requirements.txt', 'w') as f:
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

    script_path = 'install_packages.sh'
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
    return 'VIRTUAL_ENV' in os.environ

def main():
    if len(sys.argv) < 2:
        print("Usage: mypy <script.py> [args]")
        sys.exit(1)

    script      = sys.argv[1]
    script_args = sys.argv[2:]

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
            packages = [
                'torrentool', 'unidecode', 'urwid', 'langdetect', 'nltk', 'PySide6', 'tqdm', 'fasttext', 'bs4', 'bencodepy', 'kivy', 'matplotlib', 'moviepy'
            ]
            setup_virtualenv(packages)
        else:
            print("'myenv' directory already exists.")

        # Activate the virtual environment
        activate_script = os.path.join('myenv', 'bin', 'activate')
        print(f"Activating virtual environment: {activate_script}")
        activate_cmd = f"bash -c 'source {activate_script} && {sys.executable} {script} {' '.join(script_args)}'"
        subprocess.run(activate_cmd, shell=True)
        if is_virtualenv():
            print("Virtual environment activated successfully.")
            subprocess.run([sys.executable, script] + script_args)
        else:
            print("!!!WARNING!!! Still couldn't open venv!")

if __name__ == "__main__":
    main()
