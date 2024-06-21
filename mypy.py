#!/usr/bin/env python3

import os
import sys
import subprocess
from datetime import datetime
import argparse

from list_required_packages import list_packages

def setup_virtualenv(packages, script_dir, venv_name):
    # Create a timestamp string in the format YYYYMMDD-HHMMSS
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')

    # File names with timestamp
    requirements_filename = f"requirements-{timestamp}.txt"
    install_script_filename = f"install_packages-{timestamp}.sh"
    #packages_dir = f"{venv_name}-packages-{timestamp}"
    packages_dir = f"{venv_name}-packages"

    #Make packages_dir
    os.makedirs(packages_dir, exist_ok=True)

    # Write the packages to a timestamped requirements text file
    print(f"Writing packages to {os.path.join(script_dir, requirements_filename)}")
    with open(os.path.join(script_dir, requirements_filename), 'w') as f:
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
pip download -r {requirements_filename} -d {packages_dir}
pip install --no-index --find-links={packages_dir} -r {requirements_filename}
"""

    script_path = os.path.join(script_dir, install_script_filename)
    with open(script_path, 'w') as f:
        f.write(install_script)
    
    # Make the script executable
    os.chmod(script_path, 0o755)

    #Run script:
    subprocess.run([script_path])
    

def is_virtualenv():
    return sys.prefix != sys.base_prefix

def main():
    venv_name = 'myenv'
    
    parser = argparse.ArgumentParser(description="Run a Python script with optional flags.")
    parser.add_argument('script', help="The Python script to run.")
    parser.add_argument('script_args', nargs=argparse.REMAINDER, help="Arguments for the Python script.")
    parser.add_argument('-full', action='store_true', help="Build a virtual environment that can run every python script in this directory.")
    parser.add_argument('-wipe', action='store_true', help="Delete all directories matching a certain pattern.")

    args = parser.parse_args()

    full_build = 0
    if args.full:
        print("Building a virtual environment that can run every python script in this directory.")
        full_build = 1

    if args.wipe:
        #delete_directories(venv_name)
        print("Directories wiped.")
    
    venv_name = 'myenv'
    if len(sys.argv) < 2:
        print("Usage: mypy <script.py> [args]")
        sys.exit(1)

    script = sys.argv[1]
    script_args = sys.argv[2:]

    # Print the directory name where the script to be run is located
    script_dir = os.path.abspath(os.path.dirname(script))
    print(f"Directory where the script to run is located: {script_dir}")

    if full_build:
        script_dir_or_file = script_dir
    else:
        script_dir_or_file = script

    # List of bad imports that are either broken or they're local imports that I've created
    print("!!! GET RID OF THIS LIST AND CHANGE THIS TO A SYSTEM THAT LOOKS FOR THESE FILES WITH THE .py EXTENSION SOMEWHERE IN THE PATH!!! HOWEVER, tkinter and msvcrt ARE DIFFERENT. msvcrt is FOR WINDOWS. *TRY* TO DOWNLOAD ALL THE FILES, BUT IF IT'S NOT AVAILABLE THEN JUST PRINT A MESSAGE IN THE EXCEPT CONSTRUCT AND MOVE ON. THEN *TRY* TO MAKE A TEMP VENV WITH JUST THAT PACKAGE. ALSO, I NEED TO MAKE SURE TO CHECK THE LOCAL FILES THAT ARE IMPORTED, BECAUSE THEIR DEPENDENCIES NEED TO BE IMPORTED EVEN IN SINGLE-FILE MODE! \n\n\n\n\n NEW APPROACH: LOAD ALL (?) PACKAGES IN ~/mypy/offline-packages/ PUT REQUIREMENTS FILES IN ~/mypy/requirements-files/ and call them requirements-202406202320-general-tqdm-bs4-openai-#4-#5-plus-8-more.txt and also specific versions of those files, and also files that start with 'broken-'. Then the program sees the imports it needs and searches the requirements files for the latest, smallest, or the previously used (although upon encountering ModuleNotFoundError: No module named 'tqdm' each of those approaches will mark that venv as 'broken-' and then maybe they could try venv's that still have all the packages but aren't #1 on that particular list).")
    print("\n\nALSO, NEED TO LOOK INTO A SOLUTION FOR NOT MISSING FILES LIKE MYPY OR RSYNC_SAFELY. THEY HAVE NO EXTENSIONS AND ARE NOT BINARY AND START WITH A PARTICULAR LINE: '#!/usr/bin/env python3' \n\n\n NO:     if is_virtualenv(): print('Already in a virtual environment.') <-- THIS MIGHT NOT BE THE *RIGHT* VENV, SO I NEED TO TEST THAT BY LOOKING AT ITS NAME, AND IF I CAN'T RECOGNIZE IT THEN DO WHAT? IF I DO RECOGNIZE IT MAYBE I CAN LOOK IN REQUIREMENTS FILE ARCHIVES. \n\n\n\n UNIT TESTS!!! SEND CHATGPT THREE DIFFERENT TYPES OF SYSTEM MESSAGES: (1) PROGRAMMER (2) QUALITY CONTROL (3) GUARD . GUARD LOOKS AT THE INITIAL PROGRAM AND FIGURES OUT WHICH FILES IT READS/WRITES AND WHICH INTERNET OR LAN ADDRESSES IT ACCESSES IN READ OR WRITE MODE, ETC. THEN IT PRINTS IT TO THE SCREEN WHEN THE PROGRAM IS FIRST RUN, AND ASKS FOR CONFIRMATION. IF 'Y', IT NEVER ASKS AGAIN UNLESS THAT SAME LIST GETS BIGGER AS THE CODE IS REWRITTEN. check if the output has gotten stuck in a loop (exactly the same) and let them off with a warning the first time. The second time, either quit or in more advanced versions, go back to a previous point in the code and try adding a flair statement to follow a different route through the conversation. PROGRAMMER IS TOLD THEIR OUTPUT SHOULD ONLY BE CODE, AND TO ASSUME THAT WE WILL INSTALL ANY PACKAGES THAT ARE NECESSARY (OR IS THIS LAST PART JUST GONNA MAKE IT TRY TO DO THAT JUST FOR KICKS?) SO MAYBE I ALSO NEED TO TELL PROGRAMMER: You are a skilled developer who is fluent in python. You write code that is robust, resilient to errors, and well-organized so it is easy to modify. The first line of all your programs will be INSERT and the last line in all your programs will be INSERT . Your function call arguments and return values will be typed where possible. QUALITY CONTROL constant system message: You are the lead software engineer responsible for quality control. You are very good at judging whether new output achieves the stated project objective: REMINDER OF INITIAL PROMPT FROM ME . Addition to the top of every 'user' message: Please examine this output and determine if it has achieved the stated project objective:  REMINDER OF INITIAL PROMPT FROM ME . If so, just say 'Yes' with nothing else in your output. If you think this output has NOT achieved the stated objective, Imagine that you are talking to the person who wrote the code and ran it to produce that output. what would you say to the person who wrote that code in order to help them understand the problem and (possibly) offer a potential solution or point out places where a print statement added to the code would give us useful information about the intermediate states of variables. ALSO, ADD A PART WHERE THE DIFF FROM THE OLD VS NEW CODE IS MADE AND SHOWN TO (THE SAME? A DIFFERENT) LLM. TRY SEVERAL LLMS IN BOTH ROLES. FLAIR STATEMENTS: Let's reason together. Let's put our heads together and think about this. Let's sit down and think about this carefully. I'll tip you $100/$1000 if you solve this problem. There's a $78 million dollar prize for the first person to solve this problem. Let's see if we can figure it out and split that prize 50/50!")

    print("I'm looking for any projects on the web where people are using LLMs (chatgpt or others) to try to automate the debugging process. For instance, right now when I encounter an error I explain the project objective, copy the python code and error message. Then I copy the resulting program and save it to disk, then run it to see if it has worked. Are there people who are working on projects where the resulting program is saved and run automatically using the API? And then the output could be sent back to the LLM to see if it satisfies the initial user's project objective. There would have to be guardrails in place to prevent the LLM's program from writing to disk or accessing the internet, but it should be sufficient to put the LLM's program into a locked-down virtualbox or docker environment. Are there projects working on something like this?")
    bad_imports = ['bs4', 'snakeClass', 'seaborn', 'tkinter', 'msvcrt', 'univ_defs', 'search_for_media_files', 'kill_switch', 'list_required_packages']

    installed_imports, uninstalled_imports = list_packages(script_dir_or_file, bad_imports)

    print(f"Uninstalled Imports: {uninstalled_imports}")

    if is_virtualenv():
        print("Already in a virtual environment.")
        # Already in a virtual environment, run the script
        subprocess.run([sys.executable, script] + script_args)
    else:
        print("Not in a virtual environment.")
        if not os.path.isdir(os.path.join(script_dir,venv_name)):
            print(f"Creating virtual environment '{venv_name}'...")
            setup_virtualenv(list(uninstalled_imports), script_dir, venv_name)
        else:
            print(f"{venv_name} directory already exists in {script_dir}.")

        # Activate the virtual environment
        activate_script = os.path.join(venv_name, 'bin', 'activate')
        venv_python = os.path.join(venv_name, 'bin', 'python')
        print(f"Activating virtual environment: {activate_script}")

        # Additional debug statement before activation
        activate_cmd = f"bash -c 'source {activate_script} && echo \"Virtual environment activated.\" && {venv_python} {script} {' '.join(script_args)}'"
        subprocess.run(activate_cmd, shell=True)

if __name__ == "__main__":
    main()
