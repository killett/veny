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
    subprocess.check_call([sys.executable, '-m', 'venv', venv_name])

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

    # Execute the shell script
    try:
        subprocess.check_call(['/bin/bash', script_path])
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

    if is_virtualenv():
        # Already in a virtual environment, run the script
        subprocess.run([sys.executable, script] + script_args)
    else:
        if not os.path.isdir('myenv'):
            packages = [
                'torrentool', 'unidecode', 'urwid', 'langdetect', 'nltk', 'PySide6', 'tqdm', 'fasttext', 'bs4', 'bencodepy', 'kivy', 'matplotlib', 'moviepy'
            ]
            setup_virtualenv(packages)
        # Activate the virtual environment
        activate_script = os.path.join('myenv', 'bin', 'activate')
        with open(activate_script, 'w') as f:
            f.write("")
        time.sleep(10)
        if is_virtualenv():
            subprocess.run([sys.executable, script] + script_args)
        else:
            print("!!!WARNING!!! Still couldn't open venv!")
    
if __name__ == "__main__":
    main()
