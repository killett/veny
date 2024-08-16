#!/usr/bin/env python3

# Written by Emmy Killett, ChatGPT 4o, and GitHub Copilot.

import os
import sys
import subprocess
from datetime import datetime
import argparse
import ast
import re
import json
import copy
import shutil
import venv
import pickle
from pathlib import Path, PosixPath
from typing import Dict, List, Set, Tuple, Union, Iterable
import logging
import tempfile
import ast

from univ_defs import *

class Options():
    """Class that has all global options in one place."""
    def __init__(self) -> None:
        self.manual_instructions: str = """
This program acts as a wrapper around Python to automate the creation of virtual environments and the installation of any required packages. Instead of typing "python3 script.py", you can type "mypy script.py" to run script.py in a virtual environment which has all the required packages.

It's convenient to add an alias to the shell configuration file so that typing ALIAS anywhere runs this program. This can either be done by running this program with the "-alias ALIAS" command line argument (for example: "python3 mypy.py -alias mypy") or by following the manual instructions below. The following steps assume this program is saved as mypy.py in your home directory (~), but you can adjust the path and filename to match your setup.

If you're on a Mac you're probably using the zsh shell, so follow these steps to add the alias manually:
1. Open your zsh configuration file (~/.zshrc) in a text editor. For example:
   nano ~/.zshrc
2. Add the following line to the end of the file:
   alias mypy="python3 ~/mypy.py"
3. Save the file and exit the text editor.
4. Reload your zsh configuration by running the following command:
   source ~/.zshrc

If you're using the bash shell, follow these steps to add the alias manually:
1. Open your bash configuration file (~/.bashrc) in a text editor. For example:
   nano ~/.bashrc
2. Add the following line to the end of the file:
   alias mypy="python3 ~/mypy.py"
3. Save the file and exit the text editor.
4. Reload your bash configuration by running the following command:
   source ~/.bashrc
"""
        self.mypy_path: str = os.path.abspath(__file__) # This file's full path and filename
        self.current_dir: str = os.getcwd()
        self.venv_name: str = 'myenv' # Can NOT include dashes ('-')
        self.mypy_dir: str = os.path.expanduser(os.path.join('~','mypy'))
        self.packages_dir: str = os.path.join(self.mypy_dir, 'packages')
        self.test_dir: str = os.path.join(self.mypy_dir, 'test')
        self.uninstalled_imports: Set[str] = set()
        self.installed_imports: Set[str] = set()
        self.bad_imports: Set[str] = set()
        self.custom_modules: Dict[str, str] = {}
        self.subfolders: List[str] = []
        self.pip_list: List[str] = []
        self.loaded_custom_modules: Set[str] = set()
        self.pretty_list: str = ''
        self.timestamp: str = datetime.now().strftime('%Y%m%d-%H%M%S')
        self.python_script: str = ''
        self.script_name: str = '' # python_script without the .py extension
        self.script_dir: str = ''
        self.json_filename: str = ''
        self.script_dir_or_file_or_list: Union[str, Iterable[str]] = ''
        self.current_pip_version: str = ''
        self.new_pip_version: str = ''
        self.activate_script: str = ''
        self.venv_dir: str = ''
        self.venv_python: str = ''
        self.venv_pip: str = ''
        self.requirements_file: str = ''
        self.download_script_path: str = ''
        self.simultaneous_success: bool = False
        self.max_checks: int = 5 # Maximum number of times to check any repeated process.
        self.script_args: List[str] = []
        self.new_local_paths: Set[str] = set()
        self.processed_files: Set[str] = set()
        self.all_imports: Set[str] = set()
        self.installed_imports: Set[str] = set()
        self.uninstalled_imports: Set[str] = set()
        self.total_imports: int = 0
        self.bad_imports: Set[str] = set()
        # Sometimes, a module is imported in python using a different name than is required in the "pip install" command. Keep track of these exceptions here.
        self.module_aliases: Dict[str, str] = {
            'ffmpeg': 'ffmpeg-python',
            'cv2': 'opencv-python',
            'PIL': 'Pillow',
            'bs4': 'beautifulsoup4',
            'sklearn': 'scikit-learn',
            'yaml': 'PyYAML',
            'jnp': 'jax.numpy',
            'sm': 'statsmodels',
        }
        # Set of known bad imports that should be ignored.
        self.known_bad_imports: Set[str] = {'__builtin__', 'bs4', 'snakeClass', 'pathfinding_salvo_rework', 'seaborn', 'DQN', 'bayesOpt', 'tkinter', 'msvcrt', 'non_existent_module'}
        # List of unusual imports that are not standard library modules or packages.
        self.unusual_imports: List[str] = ['a', 'an', 'dl', 'the', 'it', 'x', 'xx', 'above', 'another', '__builtin__', 'within']
        # List of directories to stay out of when searching for local custom imports because they're filled with standard library modules or other irrelevant files.
        self.stay_out_list: List[str] = ['myenv', 'anaconda3', '.conda']
        # List of encodings to try when reading files, in order from most to least likely.
        self.encodings: List[str] = ['utf_8', 'latin_1', 'ascii', 'iso8859_1', 'big5', 'utf_8_sig', 'utf_16', 'utf_16_be', 'utf_16_le', 'utf_32', 'utf_32_be', 'utf_32_le', 'cp1252', 'cp1251', 'cp1250', 'cp1253', 'cp1254', 'cp1255', 'cp1256', 'cp1257', 'cp1258', 'iso8859_2', 'iso8859_3', 'iso8859_4', 'iso8859_5', 'iso8859_6', 'iso8859_7', 'iso8859_8', 'iso8859_9', 'iso8859_10', 'iso8859_11', 'iso8859_13', 'iso8859_14', 'iso8859_15', 'iso8859_16', 'cp437', 'cp850', 'cp852', 'cp855', 'cp857', 'cp858', 'cp860', 'cp861', 'cp862', 'cp863', 'cp864', 'cp865', 'cp866', 'cp869','cp037', 'cp424', 'cp500', 'cp720', 'cp737', 'cp775', 'cp874', 'cp875', 'cp932', 'cp949', 'cp950', 'cp1006', 'cp1026', 'cp1125', 'cp1140','big5hkscs', 'gb2312', 'gbk', 'gb18030', 'euc_jp', 'euc_jis_2004', 'euc_jisx0213', 'euc_kr', 'iso2022_jp', 'iso2022_jp_1', 'iso2022_jp_2', 'iso2022_jp_2004', 'iso2022_jp_3', 'iso2022_jp_ext', 'iso2022_kr', 'johab', 'koi8_r', 'koi8_t', 'koi8_u', 'kz1048', 'mac_cyrillic', 'mac_greek', 'mac_iceland', 'mac_latin2', 'mac_roman', 'mac_turkish', 'ptcp154', 'shift_jis', 'shift_jis_2004', 'shift_jisx0213', 'hz', 'tis_620', 'euc_tw', 'iso2022_tw']

    def set_venv_dir(self, venv_dir: str) -> None:
        self.venv_dir = os.path.expanduser(venv_dir)
        self.activate_script   = 'source ' + os.path.join(self.venv_dir, 'bin', 'activate')
        self.venv_python          = os.path.join(self.venv_dir, 'bin', 'python')
        self.venv_pip             = os.path.join(self.venv_dir, 'bin', 'pip')
        self.requirements_file    = os.path.join(self.venv_dir, "requirements.txt")
        self.download_script_path = os.path.join(self.venv_dir, "download_packages.sh")

def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Run a python script with optional flags.")
    
    # Create a mutually exclusive group
    group = parser.add_mutually_exclusive_group(required=True)
    
    # Add the script argument to the mutually exclusive group
    group.add_argument('script', nargs='?', help="The python script to run.")
    parser.add_argument('script_args', nargs='*', help="Optional arguments for the python script.")
    
    # Add the alias argument to the mutually exclusive group
    group.add_argument('-alias', type=str, help='Add an alias to the shell configuration file so that typing ALIAS anywhere runs this program.')

    # Add the manual argument to the mutually exclusive group
    group.add_argument('-manual', action='store_true', help='Print instructions for manually adding the alias to the shell configuration file.')

    # Add the blank-slate argument to the mutually exclusive group
    group.add_argument('-blank-slate', action='store_true', help="Delete ~/mypy/ and all mypy .out and .err and .json and .pkl files in the current directory.")
    
    # Add additional arguments to the parser (not part of the mutually exclusive group)
    parser.add_argument('-full', action='store_true', help="Build a virtual environment (venv) that can run every python script in this directory.")
    parser.add_argument('-y', action='store_true', help='Automatically say yes to any prompts.')
    parser.add_argument('-no-cache', action='store_true', help="Don't search the cache. Instead, create a new virtual environment. Also, refresh the custom modules cache and the pip list.")
    parser.add_argument('-latest', action='store_true', help="Load the latest venv in the cache which has all the packages needed now.")
    parser.add_argument('-oldest', action='store_true', help="Load the oldest venv in the cache which has all the packages needed now.")
    parser.add_argument('-last-used', action='store_true', help="Load the last used venv in the cache, but if that fails try the latest venv which has all the packages needed now.")
    parser.add_argument('-smallest', action='store_true', help="Load the smallest venv in the cache (with the fewest packages) which has all the packages needed now.")
    parser.add_argument('-rc', action='store_true', help='Refresh the custom modules cache and the pip list.')
    
    return parser.parse_args()

def detect_shell() -> str:
    """Detect the current shell."""
    shell = os.getenv("SHELL")
    if shell:
        return os.path.basename(shell)
    return None

def get_shell_rc_file(shell: str) -> str:
    """Get the shell configuration file for the current user."""
    home = os.path.expanduser("~")
    if shell == "bash":
        return os.path.join(home, ".bashrc")
    elif shell == "zsh":
        return os.path.join(home, ".zshrc")
    elif shell == "fish":
        return os.path.join(home, ".config", "fish", "config.fish")
    elif shell == "csh":
        return os.path.join(home, ".cshrc")
    elif shell == "tcsh":
        return os.path.join(home, ".tcshrc")
    return None

def get_alias_command(shell: str, alias_name: str, script_path: str) -> str:
    """Get the alias command for the shell."""
    if shell in ["bash", "zsh"]:
        return f'alias {alias_name}="python3 {script_path}"'
    elif shell == "fish":
        return f'alias {alias_name} "python3 {script_path}"'
    elif shell in ["csh", "tcsh"]:
        return f"alias {alias_name} 'python3 {script_path}'"
    return None

def alias_exists(rc_file: str, alias_pattern: str) -> bool:
    """Check if an alias exists in a file using a pattern."""
    try:
        with open(rc_file, "r") as file:
            lines = file.readlines()
        return any(re.search(alias_pattern, line) for line in lines)
    except FileNotFoundError:
        return False

def alias_exists_in_files(files: List[str], alias_pattern: str) -> bool:
    """Check if an alias exists in any of the files using a pattern."""
    for file in files:
        if alias_exists(file, alias_pattern):
            return True
    return False

def get_additional_alias_files(shell: str) -> List[str]:
    """Get additional alias files for the shell."""
    home = os.path.expanduser("~")
    if shell == "bash":
        return [os.path.join(home, ".bash_aliases")]
    elif shell == "zsh":
        return [os.path.join(home, ".zsh_aliases")]
    # Add other shells if they have alias files
    return []

def add_alias_to_rc(options: Options, rc_file: str, alias_command: str, alias_name: str, additional_files: List[str] = []) -> None:
    """Add an alias to the shell configuration file."""
    try:
        all_files = [rc_file] + additional_files
        alias_pattern = rf"alias\s+{alias_name}\s*=.*"
        if alias_exists_in_files(all_files, alias_pattern):
            print(f"Alias already exists in one of the configuration files: {all_files}")
        else:
            try:
                with open(rc_file, "a") as file:
                    file.write(f"\n{alias_command}\n")
                print(f"Alias added to {rc_file}")
            except Exception as e:
                logging.error(f"Failed to write alias to {rc_file}: {e}")
                logging.error(options.manual_instructions)
    except Exception as e:
        logging.error(f"An error occurred while adding the alias: {e}")
        logging.error(options.manual_instructions)

def add_alias(options: Options) -> None:
    """Add an alias to the shell configuration file."""
    shell = detect_shell()
    if shell:
        rc_file = get_shell_rc_file(shell)
        additional_files = get_additional_alias_files(shell)
        if rc_file:
            alias_command = get_alias_command(shell, options.args.alias, options.mypy_path)
            if alias_command:
                add_alias_to_rc(options, rc_file, alias_command, options.args.alias, additional_files)
            else:
                print(f"Unsupported shell: {shell}")
        else:
            print(f"Unsupported shell configuration file for shell: {shell}")
    else:
        print("Could not detect shell")

def safe_eval(expr: str) -> Union[None, str]:
    """Safely evaluate a Python expression using ast.literal_eval or custom parsing."""
    try:
        return ast.literal_eval(expr)
    except Exception:
        if expr.startswith('os.path.abspath'):
            inner_expr = expr[len('os.path.abspath('):-1]
            path = safe_eval(inner_expr)
            if path:
                return os.path.abspath(path)
        # Add more handling as needed
    return None

class SysPathVisitor(ast.NodeVisitor):
    """Visitor class to extract sys.path modifications."""
    def __init__(self):
        self.paths = set()

    def visit_Assign(self, node):
        if isinstance(node.targets[0], ast.Attribute) and \
           isinstance(node.targets[0].value, ast.Name) and \
           node.targets[0].value.id == 'sys' and \
           node.targets[0].attr == 'path':
            paths = safe_eval(ast.unparse(node.value))
            if isinstance(paths, list):
                for path in paths:
                    self.paths.add(path)
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute) and \
           isinstance(node.func.value, ast.Attribute) and \
           isinstance(node.func.value.value, ast.Name) and \
           node.func.value.value.id == 'sys' and \
           node.func.value.attr == 'path' and \
           node.func.attr in {'append', 'insert'}:
            if node.args:
                path = safe_eval(ast.unparse(node.args[-1]))
                if path:
                    self.paths.add(path)
        self.generic_visit(node)

def process_import(module_name: str, options: 'Options', file_path: str) -> None:
    """Process an import by checking if it's a local custom module or a standard import, and handle it accordingly."""
    logging.info(f"Processing import: {module_name} from file {file_path}")
    
    if module_name in options.all_imports:
        logging.info(f"Skipping already processed import: {module_name}")
        return

    base_dir = os.path.dirname(file_path)
    module_path = module_name.replace('.', os.sep) + ".py"

    # First, try to resolve the import relative to the base directory of the current file
    potential_file_path = os.path.join(base_dir, module_path)
    logging.info(f"Constructed potential file path: {potential_file_path}")

    if os.path.isfile(potential_file_path):
        resolved_path = os.path.abspath(potential_file_path)
        logging.info(f"Resolved local import to: {resolved_path}")
        options.custom_modules[module_name.split('.')[0]] = resolved_path
        options.loaded_custom_modules.add(module_name.split('.')[0])
        find_imports_in_script(options, resolved_path)
        return  # Exit after finding the file to avoid unnecessary checks

    # Second, check if the module is part of a package in the current directory
    package_name = base_dir.split(os.sep)[-1]  # Current directory name
    if module_path.split(os.sep)[0] == package_name and os.path.isfile(os.path.join(base_dir, '__init__.py')):
        # Modify module_path to adjust for package resolution
        adjusted_module_path = module_path.replace(package_name + os.sep, '', 1)
        resolved_path = os.path.abspath(os.path.join(base_dir, adjusted_module_path))
        print(f"Constructed adjusted file path: {resolved_path}")
        
        if os.path.isfile(resolved_path):
            logging.info(f"Resolved local import within package to: {resolved_path}")
            options.custom_modules[module_name.split('.')[0]] = resolved_path
            options.loaded_custom_modules.add(module_name.split('.')[0])
            find_imports_in_script(options, resolved_path)
            return  # Exit after finding the file to avoid unnecessary checks

    # If not found locally, fall back to checking options.custom_modules
    if module_name in options.custom_modules:
        resolved_path = options.custom_modules[module_name]
        if resolved_path == file_path:
            logging.info(f"Avoiding loopback to the same file: {resolved_path}")
            return
        logging.info(f"Using existing resolved path from custom_modules: {resolved_path}")
        options.loaded_custom_modules.add(module_name.split('.')[0])
        if not any(substring in resolved_path for substring in options.stay_out_list):
            find_imports_in_script(options, resolved_path)
    else:
        options.all_imports.add(module_name)

def my_fopen(options: Options, file_path: str):
    """Attempt to read the file with various encodings and return the file content if successful."""
    for encoding in options.encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as file:
                file_content = file.read()
            return file_content  # Exit the function if reading is successful
        except UnicodeDecodeError:
            logging.warning(f"Unicode decode error with encoding {encoding} reading file {file_path}")
            continue
        except Exception as e:
            logging.error(f"Error reading file {file_path} with encoding {encoding}: {str(e)}")
            return
    return False

def find_imports_in_script(options: 'Options', file_path: str) -> None:
    """Find all imports in a Python script and add them to a set. Recursively check local imports in any custom modules that are imported."""
    if file_path in options.processed_files:
        return
    options.processed_files.add(file_path)

    if os.path.islink(file_path):
        logging.info(f"Skipping symbolic link {file_path}")
        return

    file_content = my_fopen(options, file_path)

    try:
        tree = ast.parse(file_content, filename=file_path)
    except SyntaxError as e:
        logging.error(f"Syntax error parsing file {file_path}: {str(e)}")
        return

    # Track sys.path modifications
    sys_path_visitor = SysPathVisitor()
    sys_path_visitor.visit(tree)
    options.new_local_paths.update(sys_path_visitor.paths)
    for path in sys_path_visitor.paths:
        logging.info(f"Adding new local path: {path}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            line = ast.unparse(node)
            logging.info(f"Processing import statement: {line}")
            for alias in node.names:
                module_name = alias.name.split('.')[0]
                process_import(module_name, options, file_path)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                module_name = node.module.split('.')[0]
                process_import(module_name, options, file_path)
            elif node.level > 0:
                # Handle relative imports
                base_dir = os.path.dirname(file_path)
                rel_path = os.path.join(base_dir, *(['..'] * (node.level - 1)), node.module or '')
                resolved_path = os.path.abspath(rel_path)
                if os.path.isdir(resolved_path):
                    resolved_path = os.path.join(resolved_path, '__init__.py')
                else:
                    resolved_path += '.py'
                if os.path.isfile(resolved_path):
                    find_imports_in_script(options, resolved_path)

def check_if_library_exists_in_venv(library_name: str, venv_dir: str) -> bool:
    """Check if a library exists in the virtual environment."""
    try:
        venv_python = os.path.join(venv_dir, 'bin', 'python')
        if sys.platform == "win32":
            venv_python = os.path.join(venv_dir, 'Scripts', 'python.exe')
        
        result = subprocess.run(
            [venv_python, '-c', f'import {library_name}'],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except Exception as e:
        logging.error(f"Error checking library {library_name} in virtual environment: {e}")
        return False

def split_imports(options: Options) -> None:
    """Split imports into installed, uninstalled, and bad imports."""
    logging.info(f"Before filtering: all_imports={options.all_imports}")  # New logging
    options.bad_imports = options.known_bad_imports.intersection(options.all_imports)
    logging.info(f"Identified bad imports: {options.bad_imports}")  # New logging
    options.bad_imports.update({imp for imp in options.all_imports if imp.startswith('_')})
    options.all_imports = options.all_imports - options.bad_imports
    options.installed_imports = set()
    options.uninstalled_imports = set()
    options.total_imports = len(options.all_imports)
    if not options.total_imports:
        logging.info("No imports found.")
        return

    max_length = max(len(imp) for imp in options.all_imports)

    with tempfile.TemporaryDirectory() as venv_dir:
        venv.create(venv_dir, with_pip=True)
        for i, imp in enumerate(options.all_imports, 1):
            if imp in options.module_aliases:
                package_name = options.module_aliases[imp]
            else:
                package_name = imp
            logging.info(f"Checking if import {imp} is installed or uninstalled")  # New logging
            if imp in options.custom_modules.keys():
                logging.info(f"Custom module {imp} has path {options.custom_modules[imp]}")
            elif check_if_library_exists_in_venv(package_name, venv_dir):
                logging.info(f"Module {imp} can be imported in venv")
                options.installed_imports.add(imp)
            else:
                logging.info(f"Import {imp} is not installed and not a custom module")  # New logging
                options.uninstalled_imports.add(package_name)
            logging.info(f"Checking import {imp:{max_length}} : {i}/{options.total_imports}")
    return

def list_packages(options: Options) -> None:
    """List all installed and uninstalled packages that are imported in a directory or file. Return these sets inside the options object."""
    if type(options.script_dir_or_file_or_list) == str:
        options.script_dir_or_file_or_list = os.path.expanduser(options.script_dir_or_file_or_list)
        options.loaded_custom_modules = set()
        if os.path.isfile(options.script_dir_or_file_or_list):
            logging.info("Processing a single Python script.")
            python_file = options.script_dir_or_file_or_list
            options.all_imports = set()
            find_imports_in_script(options, python_file)
        elif os.path.isdir(options.script_dir_or_file_or_list):
            logging.info("Processing an entire folder of Python scripts.")
            python_dir = options.script_dir_or_file_or_list
            if PIPREQS_AVAILABLE:
                logging.info("Using pipreqs to generate requirements.")
                generate_requirements(options.script_dir_or_file_or_list)
                with open(os.path.join(python_dir, 'requirements.txt'), 'r') as f:
                    options.all_imports = set(line.strip() for line in f)
            else:
                logging.info("Using custom script to find imports.")
                options.all_imports = get_all_imports(options, options.script_dir_or_file_or_list)
        else:
            logging.error(f"Error: The file or directory {options.script_dir_or_file_or_list} does not exist.")
            sys.exit(1)
    else:
        logging.info("Processing a list of Python scripts.")
        options.all_imports = set()
        for python_file in options.script_dir_or_file_or_list:
            python_filepath = os.path.join(options.script_dir, python_file)
            find_imports_in_script(options, python_filepath)

    # Filter out invalid imports before splitting
    options.all_imports = {imp for imp in options.all_imports if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', imp)}
    
    logging.info(f"Finished finding imports: all_imports={options.all_imports}, total_imports={len(options.all_imports)}")  # New logging
    split_imports(options)

def get_all_imports(options: Options, directory: str) -> None:
    """Get all imports from all Python scripts in a directory."""
    options.all_imports = set()
    total_files = sum(len(files) for _, _, files in os.walk(directory) if 'myenv' not in _)
    processed_files = 0

    for root, _, files in os.walk(directory):
        if any(substring in root for substring in options.stay_out_list):
            continue
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                find_imports_in_script(options, file_path)
                processed_files += 1
                logging.info(f"Processing files in {directory}: {processed_files}/{total_files}")

    logging.info(f"\nFinished processing files in {directory}.")

def find_subfolders(options: Options) -> None:
    """Find the subfolders of the current directory that contain custom modules."""
    current_dir = os.path.normpath(options.current_dir)
    print(f"{current_dir=}")
    one_level_deep_subfolders = set()

    for module_name, module_path in options.custom_modules.items():
        module_dir = os.path.normpath(os.path.dirname(module_path))
        print(f"{module_dir=}")

        if module_dir.startswith(current_dir):
            # Calculate relative path from current_dir
            relative_path = os.path.relpath(module_dir, current_dir)
            # Extract the first part (one level deeper)
            first_dir = relative_path.split(os.sep)[0]
            one_level_deep_subfolders.add(first_dir)

    options.subfolders.extend(list(one_level_deep_subfolders))

def generate_requirements(directory: str) -> None:
    """Generate a requirements file using pipreqs."""
    try:
        pipreqs.generate_requirements(directory)
    except Exception as e:
        logging.error(f"Error generating requirements file: {e}")

class MyPopenResult:
    def __init__(self, stdout, stderr, returncode):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.success = (returncode == 0)

def my_popen(command_list: list) -> MyPopenResult:
    """Execute a command using subprocess.Popen and capture the output line by line."""
    # Convert any bytes elements in the command list to strings for logging
    command_list_str = [item.decode('utf-8') if isinstance(item, bytes) else item for item in command_list]
    logging.info("Executing command: " + ' '.join(command_list_str))

    try:
        process = subprocess.Popen(command_list,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   text=True)
        stdout = ""
        stderr = ""
        # Capture stdout line by line
        for line in iter(process.stdout.readline, ''):
            logging.info(line.strip())
            stdout += line
        # Capture stderr line by line
        for line in iter(process.stderr.readline, ''):
            logging.error(line.strip())
            stderr += line
        process.stdout.close()
        process.stderr.close()
        process.wait()
        return MyPopenResult(stdout=stdout, stderr=stderr, returncode=process.returncode)
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return MyPopenResult(stdout="", stderr=str(e), returncode=-1)

def download_packages(options: Options) -> bool:
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
    {options.venv_pip} download -r {options.requirements_file} -d {options.packages_dir}"""

    try:
        logging.info(f"Writing download script to {options.download_script_path}")
        with open(options.download_script_path, 'w') as f:
            f.write(download_script)
        os.chmod(options.download_script_path, 0o755)
        # Run the initial download script and capture the output
        result = my_popen([options.download_script_path])
        return result.returncode == 0
    except Exception as e:
        logging.error(f"Error downloading packages: {e}")
        return False

def install_packages_simultaneously(options: Options) -> bool:
    """Install all packages simultaneously in the virtual environment."""
    try:
        # Construct the install command
        install_command = [
            options.venv_python, "-m", "pip", "install",
            "--no-index", "--find-links", options.packages_dir,
            "-r", options.requirements_file
        ]
        logging.info("Installing all packages simultaneously...")
        # Run the command and capture the output line by line using my_popen
        result = my_popen(install_command)
        if result.returncode == 0:
            logging.info("All packages installed successfully.")
            return True
        else:
            logging.error("Failed to install some packages.")
            return False
    except Exception as e:
        logging.error(f"Error during simultaneous installation: {e}")
        return False

def install_packages_individually(options: Options) -> bool:
    """Install packages individually in the virtual environment."""
    failed_packages = []
    for package in options.uninstalled_imports:
        if not install_package(package, options):
            failed_packages.append(package)
    
    if failed_packages:
        logging.error(f"Failed to install the following packages: {', '.join(failed_packages)}")
    else:
        logging.info("All packages installed successfully.")

def install_package(package_name: str, options: Options) -> bool:
    """Install a single package and return the success status."""
    try:
        result = subprocess.run(
            [options.venv_python, "-m", "pip", "install", package_name, "--no-index", "--find-links", options.packages_dir],
            capture_output=True,
            text=True
        )
        logging.info(result.stdout)
        if result.stderr:
            logging.error(result.stderr)
        if result.returncode != 0:
            # Step 1: Use pip to download files for package_name to options.packages_dir
            download_command = [
                options.venv_python, "-m", "pip", "download", 
                "--dest", options.packages_dir, package_name
            ]
            download_result = subprocess.run(download_command, capture_output=True, text=True)
            if download_result.returncode != 0:
                logging.error(f"Failed to download {package_name}. Error: {download_result.stderr}")
                exit(1)
            # Step 2: Use pip to install package_name from the file that was just downloaded to options.packages_dir
            install_command = [
                options.venv_python, "-m", "pip", "install", 
                "--no-index", "--find-links", options.packages_dir, package_name
            ]
            install_result = subprocess.run(install_command, capture_output=True, text=True)
            if install_result.returncode != 0:
                logging.error(f"Failed to install {package_name}. Error: {install_result.stderr}")
            else:
                logging.info(f"Successfully installed {package_name}")
            return result.returncode == 0
        return result.returncode == 0
    except Exception as e:
        logging.error(f"Error installing package {package_name}: {e}")
        return False

def check_packages_in_venv(options: Options) -> bool:
    """Create and run a script to test package imports in the virtual environment."""
    use_pip_list(options)
    packages_str = ", ".join(f"'{pkg}'" for pkg in options.uninstalled_imports)  # Properly format the set as strings
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
    try:
        result = subprocess.run(test_script, shell=True, executable='/bin/bash', check=True, capture_output=True, text=True)
        logging.info(result.stdout)
        if result.stderr:
            logging.error(result.stderr)
        
        # This returns true if all packages imported successfully
        return "packages imported successfully" in result.stdout
    except subprocess.CalledProcessError as e:
        logging.error(f"Error running test script: {e}")
        return False

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
        logging.info(f"Recovered current pip version: {options.current_pip_version}")
    else:
        logging.warning("Failed to recover current pip version from output.")
    
    if new_version_match:
        options.new_pip_version = new_version_match.group(1)
        logging.info(f"Recovered new pip version: {options.new_pip_version}")
    else:
        logging.warning("Failed to recover new pip version from output.")

def pretty_packages_list(options: Options) -> str:
    """Create a pretty string of the first five package names and the number of remaining packages."""
    maxnum = 5
    packages_list = list(options.uninstalled_imports)
    if len(packages_list) > maxnum:
        first_five = '-'.join(packages_list[:maxnum])
        suffix = f'-and-{len(packages_list) - maxnum}-more'
    else:
        first_five = '-'.join(packages_list)
        suffix = ''
    
    return first_five + suffix

def use_pip_list(options: Options) -> None:
    """Use the pip list command to find all installed packages and use that pip list to modify the uninstalled and installed imports."""
    if len(options.pip_list) == 0:
        # Create virtual environment
        venv.create(options.test_dir, with_pip=True)
        python_executable = os.path.join(options.test_dir, 'bin', 'python')

        # Run custom list command using the Python executable from the virtual environment
        list_command_script = """
import importlib.metadata
import pkgutil
import sys

def list_installed_packages():
    installed_packages = [dist.metadata['Name'] for dist in importlib.metadata.distributions()]
    return installed_packages

def list_available_modules():
    available_modules = [module.name for module in pkgutil.iter_modules()]
    return available_modules

def list_builtin_modules():
    builtin_modules = sys.builtin_module_names
    return builtin_modules

installed_packages = list_installed_packages()
available_modules = list_available_modules()
builtin_modules = list_builtin_modules()

print("\\n".join(installed_packages + available_modules + list(builtin_modules)))
"""

        list_command = [python_executable, "-c", list_command_script]

        try:
            result = subprocess.run(list_command, check=True, capture_output=True, text=True)
            #logging.info(f"Output:\n{result.stdout}")
        except subprocess.CalledProcessError as e:
            logging.error(f"{e}")

        # Use regular expressions to find all package names
        options.pip_list = re.findall(r'^[^\s]+', result.stdout, re.MULTILINE)
        options.pip_list = [pkg for pkg in options.pip_list if pkg != 'Package' and not all(c == '-' for c in pkg)]
        #logging.info(f"\n{options.pip_list = }")

        pip_list_filename = os.path.join(options.mypy_dir, f"pip_list_{options.timestamp}.txt")
        with open(pip_list_filename, 'w') as f:
            f.write('\n'.join(options.pip_list))
    
    new_uninstalled_imports = options.installed_imports - set(options.pip_list)
    logging.info(f"{new_uninstalled_imports = }")
    options.uninstalled_imports = options.uninstalled_imports.union(new_uninstalled_imports)
    options.installed_imports = options.installed_imports - new_uninstalled_imports

def setup_virtualenv(options: Options) -> bool:
    """Setup a virtual environment and install packages."""
    use_pip_list(options)
    options.pretty_list = pretty_packages_list(options)
    # Create a virtual environment directory that starts with 'failed' in case the process fails. Only remove the 'failed' part if this process completes successfully.
    options.set_venv_dir(os.path.join(options.mypy_dir, f"failed-{options.venv_name}-versionless-{options.timestamp}-{options.pretty_list}"))
    os.makedirs(options.venv_dir, exist_ok=True)

    logging.info(f"Writing packages to {options.requirements_file}")
    with open(options.requirements_file, 'w') as f:
        for package in options.uninstalled_imports:
            f.write(f"{package}\n")

    logging.info("Creating virtual environment...")
    subprocess.check_call([sys.executable, '-m', 'venv', options.venv_dir])
    logging.info("Virtual environment created.")

    # Activate virtual environment and install wheel
    install_command = f"bash -c '{options.activate_script} && {options.venv_pip} install wheel'"
    subprocess.run(install_command, shell=True, check=True)
    logging.info("Wheel installed in the virtual environment.")

    download_packages(options)
    if install_packages_simultaneously(options):
        options.simultaneous_success = True
    else:
        options.simultaneous_success = False #This is redundant, but it's here for clarity. The 'failed' part of the venv_dir will not be removed if this is False.
        logging.error("Failed to install packages simultaneously. Trying to install packages individually to see which fail, but this venv folder will still have 'failed-' in its name...")
        if not install_packages_individually(options):
            logging.error("Failed to install packages individually.")

    # Check that all packages can be imported in the venv.
    return check_packages_in_venv(options)

def is_virtualenv() -> bool:
    """Check if currently running in a virtual environment."""
    return sys.prefix != sys.base_prefix

def get_file_operations(options: Options, script_path: str) -> Tuple[List[str], List[str]]:
    """Find files that are read or written."""
    file_content = my_fopen(options, script_path)
    try:
        tree = ast.parse(file_content, filename=script_path)
    except SyntaxError as e:
        logging.error(f"Syntax error parsing file {script_path}: {str(e)}")
        return

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

def get_network_operations(options: Options, script_path: str) -> Tuple[List[str], List[str]]:
    """Find URLs that are downloaded and uploaded"""
    file_content = my_fopen(options, script_path)
    try:
        tree = ast.parse(file_content, filename=script_path)
    except SyntaxError as e:
        logging.error(f"Syntax error parsing file {script_path}: {str(e)}")
        return

    download_urls = []
    upload_urls   = []

    # Regular expression to match URLs
    url_pattern = re.compile(r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+')

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
    read_files = []
    write_files = []
    download_urls = []
    upload_urls = []

    def aggregate_operations(script_path: str):
        """Aggregate file and network operations from script_path."""
        nonlocal read_files, write_files, download_urls, upload_urls
        r_files, w_files = get_file_operations(options, script_path)
        d_urls, u_urls = get_network_operations(options, script_path)
        read_files.extend(r_files)
        write_files.extend(w_files)
        download_urls.extend(d_urls)
        upload_urls.extend(u_urls)

    # Examine the main script
    aggregate_operations(options.python_script)

    # Examine each custom module
    for custom_load in options.loaded_custom_modules:
        module_path = options.custom_modules[custom_load]
        aggregate_operations(module_path)

    if read_files:
        logging.info("Files read: " + ", ".join(read_files))
    if write_files:
        logging.info("Files written: " + ", ".join(write_files))
    if download_urls:
        logging.info("Download URLs: " + ", ".join(download_urls))
    if upload_urls:
        logging.info("Upload URLs: " + ", ".join(upload_urls))
    
def save_options_to_json(options: Options) -> None:
    """Save the options object to a JSON file."""
    options.json_filename = os.path.join(options.script_dir, f".{os.path.basename(options.python_script)}-mypy-last-used-on-{options.timestamp}.json")
    
    # Convert options to a dictionary and handle sets
    options_dict = options.__dict__

    # Convert PosixPath to string
    for key, value in options_dict.items():
        if isinstance(value, PosixPath):
            logging.info(f"Converting PosixPath to string for key '{key}' and value '{value}'")
            options_dict[key] = str(value)

    # Ensure directory exists
    json_file_path = Path(options.json_filename)
    #logging.info(f"Ensuring directory exists: {json_file_path.parent}")
    json_file_path.parent.mkdir(parents=True, exist_ok=True)

    # Identify non-serializable types.
    these_sets = []
    non_serializable = {}
    for key, value in options_dict.items():
        try:
            json.dumps(value)
        except TypeError:
            non_serializable[key] = type(value).__name__
            #logging.info(f"Key '{key}' is of type {type(value).__name__}, so it needs to be modified for JSON serialization.")

    if non_serializable:
        #logging.info("Non-serializable keys being modified for JSON serialization...", non_serializable)
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
        logging.warning(f"No 'sets' key found in {json_file}.")
    
    logging.info(f"options loaded from {json_file}")
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

def oldest_venv(final_venv_folders: Dict[str, Dict[str, int]]) -> str:
    """Return the folder with the oldest timestamp."""
    oldest_folder = None
    oldest_timestamp = None

    for folder, data in final_venv_folders.items():
        if oldest_timestamp is None or data['timestamp'] > oldest_timestamp:
            oldest_timestamp = data['timestamp']
            oldest_folder = folder

    return oldest_folder

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
        if os.path.isdir(options_from_cache.venv_dir):
            if options.uninstalled_imports.issubset(options_from_cache.uninstalled_imports):
                options_from_cache.uninstalled_imports = options.uninstalled_imports
                options_from_cache.installed_imports = options.installed_imports
                if check_packages_in_venv(options_from_cache):
                    return 1
                else:
                    logging.error(f"The cached venv directory {options_from_cache.venv_dir} failed check_packages_in_venv.")
            else:
                logging.info(f"The cached venv directory {options_from_cache.venv_dir} does not have all the currently required packages.")
        else:
            logging.error(f"The cached venv directory {options_from_cache.venv_dir} is no longer valid.")
    return 0

def find_match_dir_in_cache(options: Options) -> str:
    """Find a matching virtual environment directory in the cache."""
    if not options.args.latest and not options.args.oldest and not options.args.last_used and not options.args.smallest:
        options.args.last_used = True #If no flags are set, then the default is to load the last used venv in the cache
    if options.args.last_used and not options.args.latest and not options.args.smallest:
        try: # Try to load the last used venv in the cache
            json_files = [f for f in os.listdir(options.script_dir) if f.startswith("."+os.path.basename(options.python_script)) and f.endswith('.json')]
            if json_files:
                if len(json_files) > 1:
                    json_files.sort(key=lambda x: x.split('-')[4], reverse=True)
                options_last_used = load_options_from_json(os.path.join(options.script_dir, json_files[0]))
                if check_venv_dir(options, options_last_used):
                    return options_last_used.venv_dir
                else:
                    logging.info("Trying to load the latest matching venv now.")
        except:
            logging.error("The last used cache encountered a problem. Trying to load the latest matching venv now.")
        options.args.latest    = True #If that didn't work, try to load the latest venv in the cache
        options.args.last_used = False #And set this to False because it failed
    logging.info("Checking the cache for a virtual environment with all the required packages...")
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
        logging.info("No matching venv folders found in the cache.")
    else:
        logging.info(f"Found {len(final_venv_folders)} matching venv folders in the cache.")
        if options.args.latest and not options.args.oldest and not options.args.last_used and not options.args.smallest:
            # Return the latest venv in the cache which has all the packages needed now
            options_latest = copy.deepcopy(options)
            options_latest.set_venv_dir(os.path.join(options.mypy_dir, latest_venv(final_venv_folders)))
            options_latest.uninstalled_imports = options.uninstalled_imports
            if check_venv_dir(options, options_latest):
                return options_latest.venv_dir
            else:
                logging.error("The latest venv in the cache is invalid. Giving up on the cache and starting from scratch.")
                return None
        elif options.args.oldest and not options.args.latest and not options.args.last_used and not options.args.smallest:
            # Return the oldest venv in the cache which has all the packages needed now
            options_oldest = copy.deepcopy(options)
            options_oldest.set_venv_dir(os.path.join(options.mypy_dir, oldest_venv(final_venv_folders)))
            options_oldest.uninstalled_imports = options.uninstalled_imports
            if check_venv_dir(options, options_oldest):
                return options_oldest.venv_dir
            else:
                logging.error("The oldest venv in the cache is invalid. Giving up on the cache and starting from scratch.")
                return None
        elif options.args.smallest and not options.args.latest and not options.args.oldest and not options.args.last_used:
            # Return the smallest venv in the cache which has all the packages needed now
            options_smallest = copy.deepcopy(options)
            options_smallest.set_venv_dir(os.path.join(options.mypy_dir, smallest_venv(final_venv_folders)))
            options_smallest.uninstalled_imports = options.uninstalled_imports
            if check_venv_dir(options, options_smallest):
                return options_smallest.venv_dir
            else:
                logging.error("The smallest venv in the cache is invalid. Giving up on the cache and starting from scratch.")
                return None
        else: # This should never happen
            logging.error(f"Invalid combination of flags. {options.args.latest = }, {options.args.oldest = }, {options.args.last_used = }, {options.args.smallest = }")

def is_standard_path(options: Options, path: str) -> bool:
    """Check if the given path is a standard system path or part of a virtual environment."""
    standard_paths = [os.path.join(os.sep, 'usr', 'lib'), os.path.join(os.sep, 'usr', 'local', 'lib')]
    # Check if path starts with standard system paths
    if any(path.startswith(standard) for standard in standard_paths):
        return True
    # Check if path contains anything in the stay_out list:
    if any(substring in path for substring in options.stay_out_list):
        return True
    # Check if path contains virtual environment indicators
    if 'site-packages' in path and (os.path.join('lib','python') in path or os.path.join('lib64','python') in path):
        return True
    return False

def dict_of_custom_modules(options: Options) -> Dict[str, str]:
    """Create a dictionary of all local custom modules in the non-standard sys.path directories and their associated filepaths."""
    #If -rc and -no-cache were not specified, look for a pickle file with the custom modules dictionary the last time this script was run.
    if not options.args.rc and not options.args.no_cache:
        for file in os.listdir('.'):
            if file.startswith('.mypy_custom_modules_') and file.endswith('.pkl'):
                logging.info(f"Loading custom modules from {file}")
                with open(file, 'rb') as f:
                    custom_modules = pickle.load(f)
                return custom_modules

    custom_modules = {}
    logging.info(f"IN dict_of_custom_modules: {options.new_local_paths = }")
    for path in sys.path:
        if not is_standard_path(options, path) and os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                for file in files:
                    if file.endswith('.py') and file != '__init__.py':
                        module_name = os.path.splitext(file)[0]
                        if module_name not in custom_modules:
                            full_path = os.path.join(root, file)
                            custom_modules[module_name] = full_path
                for dir in dirs:
                    if not is_standard_path(options, os.path.join(root, dir)):
                        package_path = os.path.join(root, dir)
                        if os.path.isfile(os.path.join(package_path, '__init__.py')):
                            if dir not in custom_modules:
                                custom_modules[dir] = package_path + os.sep
                            # Remove any individual module entries within the package directory
                            for file in os.listdir(package_path):
                                module_name = os.path.splitext(file)[0]
                                if module_name in custom_modules:
                                    del custom_modules[module_name]
    #Now save to a pickle file:
    current_time = datetime.now().strftime('%Y%m%d-%H%M%S')
    custom_filename = f'.mypy_custom_modules_{current_time}.pkl'
    with open(custom_filename, 'wb') as f:
        logging.info(f"Saving custom modules to {custom_filename}")
        pickle.dump(custom_modules, f)
    return custom_modules

def main() -> None:
    memory_handler = configure_logging("mypy", log_level="INFO")

    start_time = datetime.now()

    try:
        import pipreqs
        logging.info("pipreqs is available, so it will be used.")
        PIPREQS_AVAILABLE = True
    except ImportError:
        logging.info("pipreqs is not available. Try installing it with 'pip install pipreqs'.")
        PIPREQS_AVAILABLE = False

    options = Options()
    options.args = parse_arguments()

    options.python_script = options.args.script
    options.script_args = options.args.script_args

    if options.args.alias:
        # Add the alias to the shell configuration file
        add_alias(options)
        sys.exit(0)
    elif options.args.script:
        # Run the specified script with the provided arguments
        script_path = os.path.abspath(options.args.script)
    elif options.args.manual:
        # Print instructions for manually adding the alias to the shell configuration file
        print(options.manual_instructions)
        sys.exit(0)
    elif options.args.blank_slate:
        if not options.args.y:
            response = input("Are you sure you want to delete everything in ~/mypy/ and all mypy .json files in the current directory? (y/n) ")
            if response.casefold() != 'y':
                logging.info("Exiting without deleting anything.")
                sys.exit(0)
        logging.info("Deleting everything in ~/mypy/ and all mypy .out and .err and .json and .pkl files in the current directory.")
        shutil.rmtree(options.mypy_dir, ignore_errors=True)
        for file in os.listdir(options.current_dir):
            try:
                if (file.startswith('.mypy-') and file.endswith('.out')) or \
                (file.startswith('.mypy-') and file.endswith('.err')) or \
                (file.startswith('.mypy_custom_modules_') and file.endswith('.pkl')) or \
                (file.startswith('.'+os.path.basename(options.python_script)) and file.endswith('.json')):
                    logging.info(f"Deleting {file}")
                    os.remove(os.path.join(options.script_dir, file))
            except:
                logging.error(f"Error deleting {file}")
        sys.exit(0)
    else:
        print("You must specify either a script to run or these options: alias, manual, blank-slate (be careful using blank-slate because it deletes all the virtual environments you've made, among other things!) .")

    options.script_dir = os.path.abspath(os.path.dirname(options.python_script))
    #logging.info(f"Directory where the script to run is located: {options.script_dir}")

    if not os.path.isdir(options.mypy_dir):
        logging.info(f"Directory {options.mypy_dir} does not exist yet, so it is being created.")
        os.makedirs(options.mypy_dir, exist_ok=True)
    if not os.path.isdir(options.packages_dir):
        logging.info(f"Directory {options.packages_dir} does not exist yet, so it is being created.")
        os.makedirs(options.packages_dir, exist_ok=True)

    time1 = datetime.now()
    options.custom_modules = dict_of_custom_modules(options)
    time2 = datetime.now()
    elapsed_time = time2 - time1
    logging.info(f"dict_of_custom_modules() took {elapsed_time}")
    
    #Look for files in options.mypy_dir that start with pip_list and load the most recent one.
    options.pip_list = []
    pip_list_files = sorted([f for f in os.listdir(options.mypy_dir) if f.startswith('pip_list')],reverse=True)
    #logging.info(f"{pip_list_files = }")
    #If -rc was not specified, look for a text file with the pip list the last time this script was run.
    if not options.args.rc and pip_list_files:
        try:
            with open(os.path.join(options.mypy_dir, pip_list_files[0]), 'r') as file:
                for line in file:
                    options.pip_list.append(line.strip())
        except:
            logging.error(f"Error reading {pip_list_files[0]}")

    if options.args.full:
        logging.info("Building a virtual environment that can run every python script in this directory.")
        options.script_dir_or_file_or_list = options.script_dir
    else:
        if not options.args.script_args:
            options.script_dir_or_file_or_list = options.python_script
        else:
            #Loop through all the script arguments and see if any of them are local python scripts.
            options.script_dir_or_file_or_list = [options.python_script]
            for arg in options.script_args:
                if arg.endswith('.py'):
                   if arg.replace('.py','') in options.custom_modules:
                       options.script_dir_or_file_or_list.append(arg)
            if len(options.script_dir_or_file_or_list) == 1:
                options.script_dir_or_file_or_list = options.python_script
    logging.info(f"{options.script_dir_or_file_or_list = }")

    start_list_packages_time = datetime.now()
    elapsed_time = start_list_packages_time - start_time
    logging.info(f"Elapsed time: {elapsed_time}")

    list_packages(options)
    logging.info(f"Uninstalled imports: {options.uninstalled_imports}")
    if options.bad_imports:
        logging.warning(f"Bad imports: {options.bad_imports}")

    if not options.uninstalled_imports:
        logging.info("All required packages are already installed.")
        guard_examines(options)
        start_raw_time = datetime.now()
        subprocess.run([sys.executable, options.python_script] + options.script_args)
        elapsed_raw_time = datetime.now() - start_raw_time
        logging.info(f"Runtime: {elapsed_raw_time}")
    elif is_virtualenv():
        logging.info("Already in a virtual environment.")
        if check_packages_in_venv(options):
            guard_examines(options)
            start_raw_time = datetime.now()
            subprocess.run([sys.executable, options.python_script] + options.script_args)
            elapsed_raw_time = datetime.now() - start_raw_time
            logging.info(f"Runtime: {elapsed_raw_time}")
        else:
            logging.error("The current virtual environment does not have all the required packages.")
            logging.info("Please deactivate the current virtual environment and run the script again.")
    else:
        logging.info("Not in a virtual environment.")
        if options.args.no_cache:
            match_dir = None
        else:
            match_dir = find_match_dir_in_cache(options)
        if not match_dir:
            logging.info(f"Creating new virtual environment '{options.venv_name}'...")
            if setup_virtualenv(options):
                match_dir = options.venv_dir
            else:
                logging.error("Failed to create a virtual environment.")
                match_dir = None
        else:
            logging.info(f"Using directory: {match_dir}")

        if match_dir:
            options.set_venv_dir(match_dir)
            start_venv_time = datetime.now()
            elapsed_time = start_venv_time - start_time
            logging.info(f"Elapsed time: {elapsed_time}")
            logging.info(f"Activating virtual environment: {options.activate_script}")

            activate_cmd = f"bash -c '{options.activate_script} && echo \"Virtual environment activated.\" && {options.venv_python} {options.python_script} {' '.join(options.script_args)}'"
            guard_examines(options)
            #I want to capture the output of the subprocess.run() so that I can print it at the end.
            result = subprocess.run(activate_cmd, shell=True)
            end_time = datetime.now()
            elapsed_time = end_time - start_venv_time
            logging.info(f"Elapsed time since activating virtual environment: {elapsed_time}")
            if result.returncode != 0:
                logging.error(f"Error running script: {result.stderr}")
            elif os.path.basename(options.venv_dir).startswith('failed-') and options.simultaneous_success:
                #If the program has made it to this point, it has run successfully, so the venv directory can be renamed. It HASN'T failed. However, if it couldn't install simultaneously, then it's still a failed venv.
                os.rename(options.venv_dir, options.venv_dir.replace('failed-', ''))
                options.set_venv_dir(       options.venv_dir.replace('failed-', ''))
                #Now edit the pyvenv.cfg file inside it:
                cfg_file_path = os.path.join(options.venv_dir, 'pyvenv.cfg')
                # Read the content of the file
                with open(cfg_file_path, 'r') as file:
                    lines = file.readlines()
                # Modify the command line
                modified_lines = []
                for line in lines:
                    if line.startswith("command = "):
                        line = line.replace(os.sep+"failed-", os.sep)
                    modified_lines.append(line)
                # Write the modified content back to the file
                with open(cfg_file_path, 'w') as file:
                    file.writelines(modified_lines)
                # Read the content of the file
                with open(options.download_script_path, 'r') as file:
                    lines = file.readlines()
                # Modify the command line
                modified_lines = []
                for line in lines:
                    line = line.replace(os.sep+"failed-", os.sep)
                    modified_lines.append(line)
                # Write the modified content back to the file
                with open(options.download_script_path , 'w') as file:
                    file.writelines(modified_lines)

            save_options_to_json(options)

    # Print all captured error messages at the end
    if memory_handler.logs: print("\n****************************\nCaptured error messages:")
    for log in memory_handler.logs:
        logging.info(log)

if __name__ == "__main__":
    main()
