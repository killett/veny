#!/usr/bin/env python3

# Written by Emmy Killett (she/her), ChatGPT 4o (it/its), ChatGPT o1-preview (it/its), ChatGPT o3-mini-high (it/its), ChatGPT o4-mini-high (it/its), and GitHub Copilot (it/its).
from __future__ import annotations # For Python 3.7+ compatibility with type annotations
import os
import sys
import subprocess
import datetime as dt
import argparse
import ast
import re
import json
import copy
import shutil
import venv
import pickle
from pathlib import Path, PosixPath
from typing import Dict, List, Set, Tuple, Iterable, Any
import logging
import tempfile
import stat

import univ_defs as ud

__version__ = '0.1.5'

class Options():
    """Class that has all global options in one place."""
    def __init__(self) -> None:
        """Initialize the Options class with default values."""
        self.log_mode = "INFO"
        #self.log_mode = "DEBUG" # Instead of uncommenting this line, just use the -debug command line argument.
        self.search_above_this_dir = True
        self.my_filepath: str = os.path.abspath(__file__) # This file's full path and filename
        self.my_name = os.path.splitext(os.path.basename(self.my_filepath))[0] # The base name of this script without the .py extension
        self.my_dir: str = os.path.expanduser(os.path.join('~',self.my_name))
        self.manual_instructions: str = f"""
This program acts as a wrapper around Python to automate the creation of virtual environments and the installation of any required packages. Instead of typing "python3 script.py", you can type "{self.my_name} script.py" to run script.py in a virtual environment which has all the required packages.

It's convenient to add an alias to the shell configuration file so that typing ALIAS anywhere runs this program. This can either be done by running this program with the "-alias ALIAS" command line argument (for example: "python3 {self.my_name}.py -alias {self.my_name}") or by following the manual instructions below. The following steps assume this program is saved as {self.my_name}.py in your home directory (~), but you can adjust the path and filename to match your setup.

If you're on a Mac you're probably using the zsh shell, so follow these steps to add the alias manually:
1. Open your zsh configuration file (~/.zshrc) in a text editor. For example:
   nano ~/.zshrc
2. Add the following line to the end of the file:
   alias {self.my_name}="python3 ~/{self.my_name}.py"
3. Save the file and exit the text editor.
4. Reload your zsh configuration by running the following command:
   source ~/.zshrc

If you're using the bash shell, follow these steps to add the alias manually:
1. Open your bash configuration file (~/.bashrc) in a text editor. For example:
   nano ~/.bashrc
2. Add the following line to the end of the file:
   alias {self.my_name}="python3 ~/{self.my_name}.py"
3. Save the file and exit the text editor.
4. Reload your bash configuration by running the following command:
   source ~/.bashrc
"""
        self.python_command: str = ''
        self.shell: str = ''
        self.computer_name: str = ud.get_computer_name()
        self.cwd: str = os.getcwd()
        self.venv_name: str = 'myenv' # Can NOT include dashes ('-')
        self.packages_dir: str = os.path.join(self.my_dir, 'packages')
        self.test_dir: str = os.path.join(self.my_dir, 'test')
        self.uninstalled_imports: Set[str] = set()
        self.installed_imports: Set[str] = set()
        self.bad_imports: Set[str] = set()
        self.custom_modules: Dict[str, str] = {}
        self.subfolders: List[str] = []
        self.samedir_files: List[str] = []
        self.pip_list: List[str] = []
        self.loaded_custom_modules: Set[str] = set()
        self.pretty_list: str = ''
        self.timestamp: str = dt.datetime.now().strftime('%Y%m%d-%H%M%S')
        self.python_script: str = ''
        self.script_name: str = '' # python_script without the .py extension
        self.script_dir: str = ''
        self.json_filename: str = ''
        self.script_dir_or_file_or_list: str | Iterable[str] = ''
        self.current_pip_version: str = ''
        self.new_pip_version: str = ''
        self.activate_script: str = ''
        self.venv_dir: str = ''
        self.venv_python: str = ''
        self.venv_pip: str = ''
        self.requirements_file: str = ''
        self.extra_requirements: str = ''
        self.extra_requirements_file: str = 'extra_requirements.txt'
        self.download_script_path: str = ''
        self.simultaneous_success: bool = False
        self.max_checks: int = 10 # Maximum number of times to check any repeated process.
        self.check_interval: int = 5 # Number of seconds to wait between checks.
        self.script_args: List[str] = []
        self.new_local_paths: Set[str] = set()
        self.all_imports: Set[str] = set()
        self.installed_imports: Set[str] = set()
        self.uninstalled_imports: Set[str] = set()
        self.total_imports: int = 0
        self.bad_imports: Set[str] = set()
        self.rawlog: bool = False
        self.pipreqs_available: bool = False
        self.read_files:    List[str] = [] # List of files read       by the Python script.
        self.write_files:   List[str] = [] # List of files written    by the Python script.
        self.download_urls: List[str] = [] # List of  URLs downloaded by the Python script.
        self.upload_urls:   List[str] = [] # List of  URLs uploaded   by the Python script.
        # Some packages also need other packages to be installed.
        self.also_needs: Dict[str, List[str]] = {
            'xarray': ['dask', 'netcdf4', 'h5netcdf'],
            # NOT PIP PACKAGES: 'pyautogui': ['scrot', 'python3-tk']
            # Add more packages and their dependencies here
        }
        # Keep a list of all python standard library modules.
        # Consider switching to stdlib_list package: https://pypi.org/project/stdlib-list/
        # https://chatgpt.com/share/687000fd-be84-8006-a7f4-06af4b1e0eda
        #This list is from the pipreqs repo in file "mapping", retrieved on 2024-08-15 from here: https://github.com/bndr/pipreqs
        self.standard_modules: List[str] = ['_abc', 'abc', 'aifc', 
            '_aix_support', 'antigravity', 'argparse', 'array', 
            '_ast', 'ast', 'asynchat', '_asyncio', 'asyncio', 
            'asyncio.base_events', 'asyncio.base_futures', 
            'asyncio.base_subprocess', 'asyncio.base_tasks', 
            'asyncio.constants', 'asyncio.coroutines', 
            'asyncio.events', 'asyncio.exceptions', 
            'asyncio.format_helpers', 'asyncio.futures', 
            'asyncio.locks', 'asyncio.log', 'asyncio.__main__', 
            'asyncio.proactor_events', 'asyncio.protocols', 
            'asyncio.queues', 'asyncio.runners', 
            'asyncio.selector_events', 'asyncio.sslproto', 
            'asyncio.staggered', 'asyncio.streams', 
            'asyncio.subprocess', 'asyncio.tasks', 'asyncio.threads', 
            'asyncio.transports', 'asyncio.trsock', 
            'asyncio.unix_events', 'asyncio.windows_events', 
            'asyncio.windows_utils', 'asyncore', 'atexit', 'audioop', 
            'base64', 'bdb', 'binascii', 'binhex', '_bisect', 
            'bisect', '_blake2', '_bootlocale', '_bootsubprocess', 
            'builtins', '_bz2', 'bz2', 'calendar', 'cgi', 'cgitb', 
            'chunk', 'cmath', 'cmd', 'code', '_codecs', 'codecs', 
            '_codecs_cn', '_codecs_hk', '_codecs_iso2022', 
            '_codecs_jp', '_codecs_kr', '_codecs_tw', 'codeop', 
            '_collections', 'collections', '_collections_abc', 
            'collections.abc', 'colorsys', '_compat_pickle', 
            'compileall', '_compression', 'concurrent', 
            'concurrent.futures', 'concurrent.futures._base', 
            'concurrent.futures.process', 'concurrent.futures.thread', 
            'configparser', 'contextlib', '_contextvars', 
            'contextvars', 'copy', 'copyreg', 'cProfile', '_crypt', 
            'crypt', '_csv', 'csv', '_ctypes', 'ctypes', 
            'ctypes._aix', 'ctypes._endian', 'ctypes.macholib', 
            'ctypes.macholib.dyld', 'ctypes.macholib.dylib', 
            'ctypes.macholib.framework', '_ctypes_test', 
            'ctypes.test', 'ctypes.test.__main__', 
            'ctypes.test.test_anon', 
            'ctypes.test.test_array_in_pointer', 
            'ctypes.test.test_arrays', 
            'ctypes.test.test_as_parameter', 
            'ctypes.test.test_bitfields', 'ctypes.test.test_buffers', 
            'ctypes.test.test_bytes', 'ctypes.test.test_byteswap', 
            'ctypes.test.test_callbacks', 'ctypes.test.test_cast', 
            'ctypes.test.test_cfuncs', 'ctypes.test.test_checkretval', 
            'ctypes.test.test_delattr', 'ctypes.test.test_errno', 
            'ctypes.test.test_find', 'ctypes.test.test_frombuffer', 
            'ctypes.test.test_funcptr', 'ctypes.test.test_functions', 
            'ctypes.test.test_incomplete', 'ctypes.test.test_init', 
            'ctypes.test.test_internals', 'ctypes.test.test_keeprefs', 
            'ctypes.test.test_libc', 'ctypes.test.test_loading', 
            'ctypes.test.test_macholib', 
            'ctypes.test.test_memfunctions', 
            'ctypes.test.test_numbers', 'ctypes.test.test_objects', 
            'ctypes.test.test_parameters', 'ctypes.test.test_pep3118', 
            'ctypes.test.test_pickling', 'ctypes.test.test_pointers', 
            'ctypes.test.test_prototypes', 
            'ctypes.test.test_python_api', 
            'ctypes.test.test_random_things', 
            'ctypes.test.test_refcounts', 'ctypes.test.test_repr', 
            'ctypes.test.test_returnfuncptrs', 
            'ctypes.test.test_simplesubclasses', 
            'ctypes.test.test_sizes', 'ctypes.test.test_slicing', 
            'ctypes.test.test_stringptr', 'ctypes.test.test_strings', 
            'ctypes.test.test_struct_fields', 
            'ctypes.test.test_structures', 
            'ctypes.test.test_unaligned_structures', 
            'ctypes.test.test_unicode', 'ctypes.test.test_values', 
            'ctypes.test.test_varsize_struct', 
            'ctypes.test.test_win32', 'ctypes.test.test_wintypes', 
            'ctypes.util', 'ctypes.wintypes', '_curses', 'curses', 
            'curses.ascii', 'curses.has_key', '_curses_panel', 
            'curses.panel', 'curses.textpad', 'dataclasses', 
            '_datetime', 'datetime', '_dbm', 'dbm', 'dbm.dumb', 
            'dbm.gnu', 'dbm.ndbm', '_decimal', 'decimal', 'difflib', 
            'dis', 'distutils', 'distutils.archive_util', 
            'distutils.bcppcompiler', 'distutils.ccompiler', 
            'distutils.cmd', 'distutils.command', 
            'distutils.command.bdist', 'distutils.command.bdist_dumb', 
            'distutils.command.bdist_msi', 
            'distutils.command.bdist_packager', 
            'distutils.command.bdist_rpm', 
            'distutils.command.bdist_wininst', 
            'distutils.command.build', 'distutils.command.build_clib', 
            'distutils.command.build_ext', 
            'distutils.command.build_py', 
            'distutils.command.build_scripts', 
            'distutils.command.check', 'distutils.command.clean', 
            'distutils.command.config', 'distutils.command.install', 
            'distutils.command.install_data', 
            'distutils.command.install_egg_info', 
            'distutils.command.install_headers', 
            'distutils.command.install_lib', 
            'distutils.command.install_scripts', 
            'distutils.command.register', 'distutils.command.sdist', 
            'distutils.command.upload', 'distutils.config', 
            'distutils.core', 'distutils.cygwinccompiler', 
            'distutils.debug', 'distutils.dep_util', 
            'distutils.dir_util', 'distutils.dist', 
            'distutils.errors', 'distutils.extension', 
            'distutils.fancy_getopt', 'distutils.filelist', 
            'distutils.file_util', 'distutils.log', 
            'distutils.msvc9compiler', 'distutils._msvccompiler', 
            'distutils.msvccompiler', 'distutils.spawn', 
            'distutils.sysconfig', 'distutils.tests', 
            'distutils.tests.support', 
            'distutils.tests.test_archive_util', 
            'distutils.tests.test_bdist', 
            'distutils.tests.test_bdist_dumb', 
            'distutils.tests.test_bdist_msi', 
            'distutils.tests.test_bdist_rpm', 
            'distutils.tests.test_bdist_wininst', 
            'distutils.tests.test_build', 
            'distutils.tests.test_build_clib', 
            'distutils.tests.test_build_ext', 
            'distutils.tests.test_build_py', 
            'distutils.tests.test_build_scripts', 
            'distutils.tests.test_check', 
            'distutils.tests.test_clean', 'distutils.tests.test_cmd', 
            'distutils.tests.test_config', 
            'distutils.tests.test_config_cmd', 
            'distutils.tests.test_core', 
            'distutils.tests.test_cygwinccompiler', 
            'distutils.tests.test_dep_util', 
            'distutils.tests.test_dir_util', 
            'distutils.tests.test_dist', 
            'distutils.tests.test_extension', 
            'distutils.tests.test_filelist', 
            'distutils.tests.test_file_util', 
            'distutils.tests.test_install', 
            'distutils.tests.test_install_data', 
            'distutils.tests.test_install_headers', 
            'distutils.tests.test_install_lib', 
            'distutils.tests.test_install_scripts', 
            'distutils.tests.test_log', 
            'distutils.tests.test_msvc9compiler', 
            'distutils.tests.test_msvccompiler', 
            'distutils.tests.test_register', 
            'distutils.tests.test_sdist', 
            'distutils.tests.test_spawn', 
            'distutils.tests.test_sysconfig', 
            'distutils.tests.test_text_file', 
            'distutils.tests.test_unixccompiler', 
            'distutils.tests.test_upload', 
            'distutils.tests.test_util', 
            'distutils.tests.test_version', 
            'distutils.tests.test_versionpredicate', 
            'distutils.text_file', 'distutils.unixccompiler', 
            'distutils.util', 'distutils.version', 
            'distutils.versionpredicate', 'doctest', '_dummy_thread', 
            'dummy_threading', '_elementtree', 'email', 
            'email.base64mime', 'email.charset', 
            'email.contentmanager', 'email._encoded_words', 
            'email.encoders', 'email.errors', 'email.feedparser', 
            'email.generator', 'email.header', 'email.headerregistry', 
            'email._header_value_parser', 'email.iterators', 
            'email.message', 'email.mime', 'email.mime.application', 
            'email.mime.audio', 'email.mime.base', 'email.mime.image', 
            'email.mime.message', 'email.mime.multipart', 
            'email.mime.nonmultipart', 'email.mime.text', 
            'email._parseaddr', 'email.parser', 'email.policy', 
            'email._policybase', 'email.quoprimime', 'email.utils', 
            'encodings', 'encodings.aliases', 'encodings.ascii', 
            'encodings.base64_codec', 'encodings.big5', 
            'encodings.big5hkscs', 'encodings.bz2_codec', 
            'encodings.charmap', 'encodings.cp037', 
            'encodings.cp1006', 'encodings.cp1026', 
            'encodings.cp1125', 'encodings.cp1140', 
            'encodings.cp1250', 'encodings.cp1251', 
            'encodings.cp1252', 'encodings.cp1253', 
            'encodings.cp1254', 'encodings.cp1255', 
            'encodings.cp1256', 'encodings.cp1257', 
            'encodings.cp1258', 'encodings.cp273', 'encodings.cp424', 
            'encodings.cp437', 'encodings.cp500', 'encodings.cp720', 
            'encodings.cp737', 'encodings.cp775', 'encodings.cp850', 
            'encodings.cp852', 'encodings.cp855', 'encodings.cp856', 
            'encodings.cp857', 'encodings.cp858', 'encodings.cp860', 
            'encodings.cp861', 'encodings.cp862', 'encodings.cp863', 
            'encodings.cp864', 'encodings.cp865', 'encodings.cp866', 
            'encodings.cp869', 'encodings.cp874', 'encodings.cp875', 
            'encodings.cp932', 'encodings.cp949', 'encodings.cp950', 
            'encodings.euc_jis_2004', 'encodings.euc_jisx0213', 
            'encodings.euc_jp', 'encodings.euc_kr', 
            'encodings.gb18030', 'encodings.gb2312', 'encodings.gbk', 
            'encodings.hex_codec', 'encodings.hp_roman8', 
            'encodings.hz', 'encodings.idna', 'encodings.iso2022_jp', 
            'encodings.iso2022_jp_1', 'encodings.iso2022_jp_2', 
            'encodings.iso2022_jp_2004', 'encodings.iso2022_jp_3', 
            'encodings.iso2022_jp_ext', 'encodings.iso2022_kr', 
            'encodings.iso8859_1', 'encodings.iso8859_10', 
            'encodings.iso8859_11', 'encodings.iso8859_13', 
            'encodings.iso8859_14', 'encodings.iso8859_15', 
            'encodings.iso8859_16', 'encodings.iso8859_2', 
            'encodings.iso8859_3', 'encodings.iso8859_4', 
            'encodings.iso8859_5', 'encodings.iso8859_6', 
            'encodings.iso8859_7', 'encodings.iso8859_8', 
            'encodings.iso8859_9', 'encodings.johab', 
            'encodings.koi8_r', 'encodings.koi8_t', 
            'encodings.koi8_u', 'encodings.kz1048', 
            'encodings.latin_1', 'encodings.mac_arabic', 
            'encodings.mac_centeuro', 'encodings.mac_croatian', 
            'encodings.mac_cyrillic', 'encodings.mac_farsi', 
            'encodings.mac_greek', 'encodings.mac_iceland', 
            'encodings.mac_latin2', 'encodings.mac_roman', 
            'encodings.mac_romanian', 'encodings.mac_turkish', 
            'encodings.mbcs', 'encodings.oem', 'encodings.palmos', 
            'encodings.ptcp154', 'encodings.punycode', 
            'encodings.quopri_codec', 'encodings.raw_unicode_escape', 
            'encodings.rot_13', 'encodings.shift_jis', 
            'encodings.shift_jis_2004', 'encodings.shift_jisx0213', 
            'encodings.tis_620', 'encodings.undefined', 
            'encodings.unicode_escape', 'encodings.utf_16', 
            'encodings.utf_16_be', 'encodings.utf_16_le', 
            'encodings.utf_32', 'encodings.utf_32_be', 
            'encodings.utf_32_le', 'encodings.utf_7', 
            'encodings.utf_8', 'encodings.utf_8_sig', 
            'encodings.uu_codec', 'encodings.zlib_codec', 'ensurepip', 
            'ensurepip._bundled', 'ensurepip.__main__', 
            'ensurepip._uninstall', 'enum', 'errno', 'faulthandler', 
            'fcntl', 'filecmp', 'fileinput', 'fnmatch', 'formatter', 
            'fractions', '_frozen_importlib', 
            '_frozen_importlib_external', 'ftplib', '_functools', 
            'functools', '__future__', 'gc', '_gdbm', 'genericpath', 
            'getopt', 'getpass', 'gettext', 'glob', 'graphlib', 'grp', 
            'gzip', '_hashlib', 'hashlib', '_heapq', 'heapq', 'hmac', 
            'html', 'html.entities', 'html.parser', 'http', 
            'http.client', 'http.cookiejar', 'http.cookies', 
            'http.server', 'idlelib', 'idlelib.autocomplete', 
            'idlelib.autocomplete_w', 'idlelib.autoexpand', 
            'idlelib.browser', 'idlelib.calltip', 'idlelib.calltip_w', 
            'idlelib.codecontext', 'idlelib.colorizer', 
            'idlelib.config', 'idlelib.configdialog', 
            'idlelib.config_key', 'idlelib.debugger', 
            'idlelib.debugger_r', 'idlelib.debugobj', 
            'idlelib.debugobj_r', 'idlelib.delegator', 
            'idlelib.dynoption', 'idlelib.editor', 'idlelib.filelist', 
            'idlelib.format', 'idlelib.grep', 'idlelib.help', 
            'idlelib.help_about', 'idlelib.history', 
            'idlelib.hyperparser', 'idlelib.idle', 
            'idlelib.idle_test', 'idlelib.idle_test.htest', 
            'idlelib.idle_test.mock_idle', 
            'idlelib.idle_test.mock_tk', 'idlelib.idle_test.template', 
            'idlelib.idle_test.test_autocomplete', 
            'idlelib.idle_test.test_autocomplete_w', 
            'idlelib.idle_test.test_autoexpand', 
            'idlelib.idle_test.test_browser', 
            'idlelib.idle_test.test_calltip', 
            'idlelib.idle_test.test_calltip_w', 
            'idlelib.idle_test.test_codecontext', 
            'idlelib.idle_test.test_colorizer', 
            'idlelib.idle_test.test_config', 
            'idlelib.idle_test.test_configdialog', 
            'idlelib.idle_test.test_config_key', 
            'idlelib.idle_test.test_debugger', 
            'idlelib.idle_test.test_debugger_r', 
            'idlelib.idle_test.test_debugobj', 
            'idlelib.idle_test.test_debugobj_r', 
            'idlelib.idle_test.test_delegator', 
            'idlelib.idle_test.test_editmenu', 
            'idlelib.idle_test.test_editor', 
            'idlelib.idle_test.test_filelist', 
            'idlelib.idle_test.test_format', 
            'idlelib.idle_test.test_grep', 
            'idlelib.idle_test.test_help', 
            'idlelib.idle_test.test_help_about', 
            'idlelib.idle_test.test_history', 
            'idlelib.idle_test.test_hyperparser', 
            'idlelib.idle_test.test_iomenu', 
            'idlelib.idle_test.test_macosx', 
            'idlelib.idle_test.test_mainmenu', 
            'idlelib.idle_test.test_multicall', 
            'idlelib.idle_test.test_outwin', 
            'idlelib.idle_test.test_parenmatch', 
            'idlelib.idle_test.test_pathbrowser', 
            'idlelib.idle_test.test_percolator', 
            'idlelib.idle_test.test_pyparse', 
            'idlelib.idle_test.test_pyshell', 
            'idlelib.idle_test.test_query', 
            'idlelib.idle_test.test_redirector', 
            'idlelib.idle_test.test_replace', 
            'idlelib.idle_test.test_rpc', 
            'idlelib.idle_test.test_run', 
            'idlelib.idle_test.test_runscript', 
            'idlelib.idle_test.test_scrolledlist', 
            'idlelib.idle_test.test_search', 
            'idlelib.idle_test.test_searchbase', 
            'idlelib.idle_test.test_searchengine', 
            'idlelib.idle_test.test_sidebar', 
            'idlelib.idle_test.test_squeezer', 
            'idlelib.idle_test.test_stackviewer', 
            'idlelib.idle_test.test_statusbar', 
            'idlelib.idle_test.test_text', 
            'idlelib.idle_test.test_textview', 
            'idlelib.idle_test.test_tooltip', 
            'idlelib.idle_test.test_tree', 
            'idlelib.idle_test.test_undo', 
            'idlelib.idle_test.test_warning', 
            'idlelib.idle_test.test_window', 
            'idlelib.idle_test.test_zoomheight', 'idlelib.iomenu', 
            'idlelib.macosx', 'idlelib.__main__', 'idlelib.mainmenu', 
            'idlelib.multicall', 'idlelib.outwin', 
            'idlelib.parenmatch', 'idlelib.pathbrowser', 
            'idlelib.percolator', 'idlelib.pyparse', 
            'idlelib.pyshell', 'idlelib.query', 'idlelib.redirector', 
            'idlelib.replace', 'idlelib.rpc', 'idlelib.run', 
            'idlelib.runscript', 'idlelib.scrolledlist', 
            'idlelib.search', 'idlelib.searchbase', 
            'idlelib.searchengine', 'idlelib.sidebar', 
            'idlelib.squeezer', 'idlelib.stackviewer', 
            'idlelib.statusbar', 'idlelib.textview', 
            'idlelib.tooltip', 'idlelib.tree', 'idlelib.undo', 
            'idlelib.window', 'idlelib.zoomheight', 'idlelib.zzdummy', 
            'imaplib', 'imghdr', '_imp', 'imp', 'importlib', 
            'importlib.abc', 'importlib._bootstrap', 
            'importlib._bootstrap_external', 'importlib._common', 
            'importlib.machinery', 'importlib.metadata', 
            'importlib.resources', 'importlib.util', 'inspect', '_io', 
            'io', 'ipaddress', 'itertools', '_json', 'json', 
            'json.decoder', 'json.encoder', 'json.scanner', 
            'json.tool', 'keyword', 'lib2to3', 'lib2to3.btm_matcher', 
            'lib2to3.btm_utils', 'lib2to3.fixer_base', 
            'lib2to3.fixer_util', 'lib2to3.fixes', 
            'lib2to3.fixes.fix_apply', 'lib2to3.fixes.fix_asserts', 
            'lib2to3.fixes.fix_basestring', 
            'lib2to3.fixes.fix_buffer', 'lib2to3.fixes.fix_dict', 
            'lib2to3.fixes.fix_except', 'lib2to3.fixes.fix_exec', 
            'lib2to3.fixes.fix_execfile', 
            'lib2to3.fixes.fix_exitfunc', 'lib2to3.fixes.fix_filter', 
            'lib2to3.fixes.fix_funcattrs', 'lib2to3.fixes.fix_future', 
            'lib2to3.fixes.fix_getcwdu', 'lib2to3.fixes.fix_has_key', 
            'lib2to3.fixes.fix_idioms', 'lib2to3.fixes.fix_import', 
            'lib2to3.fixes.fix_imports', 'lib2to3.fixes.fix_imports2', 
            'lib2to3.fixes.fix_input', 'lib2to3.fixes.fix_intern', 
            'lib2to3.fixes.fix_isinstance', 
            'lib2to3.fixes.fix_itertools', 
            'lib2to3.fixes.fix_itertools_imports', 
            'lib2to3.fixes.fix_long', 'lib2to3.fixes.fix_map', 
            'lib2to3.fixes.fix_metaclass', 
            'lib2to3.fixes.fix_methodattrs', 'lib2to3.fixes.fix_ne', 
            'lib2to3.fixes.fix_next', 'lib2to3.fixes.fix_nonzero', 
            'lib2to3.fixes.fix_numliterals', 
            'lib2to3.fixes.fix_operator', 'lib2to3.fixes.fix_paren', 
            'lib2to3.fixes.fix_print', 'lib2to3.fixes.fix_raise', 
            'lib2to3.fixes.fix_raw_input', 'lib2to3.fixes.fix_reduce', 
            'lib2to3.fixes.fix_reload', 'lib2to3.fixes.fix_renames', 
            'lib2to3.fixes.fix_repr', 'lib2to3.fixes.fix_set_literal', 
            'lib2to3.fixes.fix_standarderror', 
            'lib2to3.fixes.fix_sys_exc', 'lib2to3.fixes.fix_throw', 
            'lib2to3.fixes.fix_tuple_params', 
            'lib2to3.fixes.fix_types', 'lib2to3.fixes.fix_unicode', 
            'lib2to3.fixes.fix_urllib', 'lib2to3.fixes.fix_ws_comma', 
            'lib2to3.fixes.fix_xrange', 
            'lib2to3.fixes.fix_xreadlines', 'lib2to3.fixes.fix_zip', 
            'lib2to3.main', 'lib2to3.__main__', 'lib2to3.patcomp', 
            'lib2to3.pgen2', 'lib2to3.pgen2.conv', 
            'lib2to3.pgen2.driver', 'lib2to3.pgen2.grammar', 
            'lib2to3.pgen2.literals', 'lib2to3.pgen2.parse', 
            'lib2to3.pgen2.pgen', 'lib2to3.pgen2.token', 
            'lib2to3.pgen2.tokenize', 'lib2to3.pygram', 
            'lib2to3.pytree', 'lib2to3.refactor', 'lib2to3.tests', 
            'lib2to3.tests.data.bom', 'lib2to3.tests.data.crlf', 
            'lib2to3.tests.data.different_encoding', 
            'lib2to3.tests.data.false_encoding', 
            'lib2to3.tests.data.fixers.bad_order', 
            'lib2to3.tests.data.fixers.myfixes', 
            'lib2to3.tests.data.fixers.myfixes.fix_explicit', 
            'lib2to3.tests.data.fixers.myfixes.fix_first', 
            'lib2to3.tests.data.fixers.myfixes.fix_last', 
            'lib2to3.tests.data.fixers.myfixes.fix_parrot', 
            'lib2to3.tests.data.fixers.myfixes.fix_preorder', 
            'lib2to3.tests.data.fixers.no_fixer_cls', 
            'lib2to3.tests.data.fixers.parrot_example', 
            'lib2to3.tests.data.infinite_recursion', 
            'lib2to3.tests.data.py2_test_grammar', 
            'lib2to3.tests.data.py3_test_grammar', 
            'lib2to3.tests.__main__', 
            'lib2to3.tests.pytree_idempotency', 
            'lib2to3.tests.support', 'lib2to3.tests.test_all_fixers', 
            'lib2to3.tests.test_fixers', 'lib2to3.tests.test_main', 
            'lib2to3.tests.test_parser', 'lib2to3.tests.test_pytree', 
            'lib2to3.tests.test_refactor', 'lib2to3.tests.test_util', 
            'lib.libpython3', 'linecache', '_locale', 'locale', 
            'logging', 'logging.config', 'logging.handlers', 
            '_lsprof', '_lzma', 'lzma', 'mailbox', 'mailcap', 
            '__main__', '_markupbase', 'marshal', 'math', '_md5', 
            'mimetypes', 'mmap', 'modulefinder', 'msilib', 'msvcrt', 
            '_multibytecodec', '_multiprocessing', 'multiprocessing', 
            'multiprocessing.connection', 'multiprocessing.context', 
            'multiprocessing.dummy', 
            'multiprocessing.dummy.connection', 
            'multiprocessing.forkserver', 'multiprocessing.heap', 
            'multiprocessing.managers', 'multiprocessing.pool', 
            'multiprocessing.popen_fork', 
            'multiprocessing.popen_forkserver', 
            'multiprocessing.popen_spawn_posix', 
            'multiprocessing.popen_spawn_win32', 
            'multiprocessing.process', 'multiprocessing.queues', 
            'multiprocessing.reduction', 
            'multiprocessing.resource_sharer', 
            'multiprocessing.resource_tracker', 
            'multiprocessing.sharedctypes', 
            'multiprocessing.shared_memory', 'multiprocessing.spawn', 
            'multiprocessing.synchronize', 'multiprocessing.util', 
            'netrc', 'nis', 'nntplib', 'ntpath', 'nturl2path', 
            'numbers', '_opcode', 'opcode', '_operator', 'operator', 
            'optparse', 'os', 'os.path', 'ossaudiodev', 
            '_osx_support', 'parser', 'pathlib', 'pdb', 
            '__phello__.foo', '_pickle', 'pickle', 'pickletools', 
            'pipes', 'pkgutil', 'platform', 'plistlib', 'poplib', 
            'posix', 'posixpath', '_posixshmem', '_posixsubprocess', 
            'pprint', 'profile', 'pstats', 'pty', 'pwd', '_py_abc', 
            'pyclbr', 'py_compile', '_pydecimal', 'pydoc', 
            'pydoc_data', 'pydoc_data.topics', 'pyexpat', '_pyio', 
            '_queue', 'queue', 'quopri', '_random', 'random', 're', 
            'readline', 'reprlib', 'resource', 'rlcompleter', 'runpy', 
            'sched', 'secrets', 'select', 'selectors', '_sha1', 
            '_sha256', '_sha3', '_sha512', 'shelve', 'shlex', 
            'shutil', '_signal', 'signal', 'site', '_sitebuiltins', 
            'smtpd', 'smtplib', 'sndhdr', '_socket', 'socket', 
            'socketserver', 'spwd', '_sqlite3', 'sqlite3', 
            'sqlite3.dbapi2', 'sqlite3.dump', 'sqlite3.test', 
            'sqlite3.test.backup', 'sqlite3.test.dbapi', 
            'sqlite3.test.dump', 'sqlite3.test.factory', 
            'sqlite3.test.hooks', 'sqlite3.test.regression', 
            'sqlite3.test.transactions', 'sqlite3.test.types', 
            'sqlite3.test.userfunctions', '_sre', 'sre_compile', 
            'sre_constants', 'sre_parse', '_ssl', 'ssl', '_stat', 
            'stat', '_statistics', 'statistics', '_string', 'string', 
            'stringprep', '_strptime', '_struct', 'struct', 
            'subprocess', 'sunau', 'symbol', '_symtable', 'symtable', 
            'sys', 'sysconfig', 
            '_sysconfigdata_x86_64_conda_cos6_linux_gnu', 
            '_sysconfigdata_x86_64_conda_linux_gnu', 'syslog', 
            'tabnanny', 'tarfile', 'telnetlib', 'tempfile', 'termios', 
            'test', 'test.ann_module', 'test.ann_module2', 
            'test.ann_module3', 'test.audiotests', 'test.autotest', 
            'test.bad_coding', 'test.bad_coding2', 'test.bad_getattr', 
            'test.bad_getattr2', 'test.bad_getattr3', 
            'test.badsyntax_3131', 'test.badsyntax_future10', 
            'test.badsyntax_future3', 'test.badsyntax_future4', 
            'test.badsyntax_future5', 'test.badsyntax_future6', 
            'test.badsyntax_future7', 'test.badsyntax_future8', 
            'test.badsyntax_future9', 'test.badsyntax_pep3120', 
            'test.bisect_cmd', '_testbuffer', 'test.bytecode_helper', 
            '_testcapi', 'test.coding20731', 'test.curses_tests', 
            'test.dataclass_module_1', 'test.dataclass_module_1_str', 
            'test.dataclass_module_2', 'test.dataclass_module_2_str', 
            'test.datetimetester', 'test.dis_module', 
            'test.doctest_aliases', 'test.double_const', 
            'test.dtracedata.call_stack', 'test.dtracedata.gc', 
            'test.dtracedata.instance', 'test.dtracedata.line', 
            'test.eintrdata.eintr_tester', 'test.encoded_modules', 
            'test.encoded_modules.module_iso_8859_1', 
            'test.encoded_modules.module_koi8_r', 'test.final_a', 
            'test.final_b', 'test.fork_wait', 'test.future_test1', 
            'test.future_test2', 'test.gdb_sample', 
            'test.good_getattr', 'test.imp_dummy', 
            '_testimportmultiple', 'test.inspect_fodder', 
            'test.inspect_fodder2', '_testinternalcapi', 
            'test.libregrtest', 'test.libregrtest.cmdline', 
            'test.libregrtest.main', 'test.libregrtest.pgo', 
            'test.libregrtest.refleak', 'test.libregrtest.runtest', 
            'test.libregrtest.runtest_mp', 
            'test.libregrtest.save_env', 'test.libregrtest.setup', 
            'test.libregrtest.utils', 'test.libregrtest.win_utils', 
            'test.list_tests', 'test.lock_tests', 'test.__main__', 
            'test.make_ssl_certs', 'test.mapping_tests', 
            'test.memory_watchdog', 'test.mock_socket', 
            'test.mod_generics_cache', 'test.mp_fork_bomb', 
            'test.mp_preload', 'test.multibytecodec_support', 
            '_testmultiphase', 'test.outstanding_bugs', 
            'test.pickletester', 'test.profilee', 'test.pyclbr_input', 
            'test.pydocfodder', 'test.pydoc_mod', 'test.pythoninfo', 
            'test.regrtest', 'test.relimport', 'test.reperf', 
            'test.re_tests', 'test.sample_doctest', 
            'test.sample_doctest_no_docstrings', 
            'test.sample_doctest_no_doctests', 'test.seq_tests', 
            'test.signalinterproctester', 'test.sortperf', 
            'test.ssl_servers', 'test.ssltests', 'test.string_tests', 
            'test.subprocessdata.fd_status', 
            'test.subprocessdata.input_reader', 
            'test.subprocessdata.qcat', 'test.subprocessdata.qgrep', 
            'test.subprocessdata.sigchild_ignore', 'test.support', 
            'test.support.bytecode_helper', 
            'test.support.hashlib_helper', 
            'test.support.logging_helper', 
            'test.support.script_helper', 
            'test.support.socket_helper', 'test.support.testresult', 
            'test.test_abc', 'test.test_abstract_numbers', 
            'test.test_aifc', 'test.test___all__', 
            'test.test_argparse', 'test.test_array', 
            'test.test_asdl_parser', 'test.test_ast', 
            'test.test_asyncgen', 'test.test_asynchat', 
            'test.test_asyncio', 'test.test_asyncio.echo', 
            'test.test_asyncio.echo2', 'test.test_asyncio.echo3', 
            'test.test_asyncio.functional', 
            'test.test_asyncio.__main__', 
            'test.test_asyncio.test_base_events', 
            'test.test_asyncio.test_buffered_proto', 
            'test.test_asyncio.test_context', 
            'test.test_asyncio.test_events', 
            'test.test_asyncio.test_futures', 
            'test.test_asyncio.test_locks', 
            'test.test_asyncio.test_pep492', 
            'test.test_asyncio.test_proactor_events', 
            'test.test_asyncio.test_protocols', 
            'test.test_asyncio.test_queues', 
            'test.test_asyncio.test_runners', 
            'test.test_asyncio.test_selector_events', 
            'test.test_asyncio.test_sendfile', 
            'test.test_asyncio.test_server', 
            'test.test_asyncio.test_sock_lowlevel', 
            'test.test_asyncio.test_sslproto', 
            'test.test_asyncio.test_streams', 
            'test.test_asyncio.test_subprocess', 
            'test.test_asyncio.test_tasks', 
            'test.test_asyncio.test_transports', 
            'test.test_asyncio.test_unix_events', 
            'test.test_asyncio.test_windows_events', 
            'test.test_asyncio.test_windows_utils', 
            'test.test_asyncio.utils', 'test.test_asyncore', 
            'test.test_atexit', 'test.test_audioop', 
            'test.test_audit', 'test.test_augassign', 
            'test.test_base64', 'test.test_baseexception', 
            'test.test_bdb', 'test.test_bigaddrspace', 
            'test.test_bigmem', 'test.test_binascii', 
            'test.test_binhex', 'test.test_binop', 'test.test_bisect', 
            'test.test_bool', 'test.test_buffer', 'test.test_bufio', 
            'test.test_builtin', 'test.test_bytes', 'test.test_bz2', 
            'test.test_calendar', 'test.test_call', 'test.test_capi', 
            'test.test_cgi', 'test.test_cgitb', 
            'test.test_charmapcodec', 'test.test_class', 
            'test.test_clinic', 'test.test_c_locale_coercion', 
            'test.test_cmath', 'test.test_cmd', 'test.test_cmd_line', 
            'test.test_cmd_line_script', 'test.test_code', 
            'test.testcodec', 'test.test_codeccallbacks', 
            'test.test_codecencodings_cn', 
            'test.test_codecencodings_hk', 
            'test.test_codecencodings_iso2022', 
            'test.test_codecencodings_jp', 
            'test.test_codecencodings_kr', 
            'test.test_codecencodings_tw', 'test.test_codecmaps_cn', 
            'test.test_codecmaps_hk', 'test.test_codecmaps_jp', 
            'test.test_codecmaps_kr', 'test.test_codecmaps_tw', 
            'test.test_codecs', 'test.test_code_module', 
            'test.test_codeop', 'test.test_collections', 
            'test.test_colorsys', 'test.test_compare', 
            'test.test_compile', 'test.test_compileall', 
            'test.test_complex', 'test.test_concurrent_futures', 
            'test.test_configparser', 'test.test_contains', 
            'test.test_context', 'test.test_contextlib', 
            'test.test_contextlib_async', 'test.test_copy', 
            'test.test_copyreg', 'test.test_coroutines', 
            'test.test_cprofile', 'test.test_crashers', 
            'test.test_crypt', 'test.test_csv', 'test.test_ctypes', 
            'test.test_curses', 'test.test_dataclasses', 
            'test.test_datetime', 'test.test_dbm', 
            'test.test_dbm_dumb', 'test.test_dbm_gnu', 
            'test.test_dbm_ndbm', 'test.test_decimal', 
            'test.test_decorators', 'test.test_defaultdict', 
            'test.test_deque', 'test.test_descr', 
            'test.test_descrtut', 'test.test_devpoll', 
            'test.test_dict', 'test.test_dictcomps', 
            'test.test_dict_version', 'test.test_dictviews', 
            'test.test_difflib', 'test.test_dis', 
            'test.test_distutils', 'test.test_doctest', 
            'test.test_doctest2', 'test.test_docxmlrpc', 
            'test.test_dtrace', 'test.test_dummy_thread', 
            'test.test_dummy_threading', 'test.test_dynamic', 
            'test.test_dynamicclassattribute', 'test.test_eintr', 
            'test.test_email', 'test.test_email.__main__', 
            'test.test_email.test_asian_codecs', 
            'test.test_email.test_contentmanager', 
            'test.test_email.test_defect_handling', 
            'test.test_email.test_email', 
            'test.test_email.test__encoded_words', 
            'test.test_email.test_generator', 
            'test.test_email.test_headerregistry', 
            'test.test_email.test__header_value_parser', 
            'test.test_email.test_inversion', 
            'test.test_email.test_message', 
            'test.test_email.test_parser', 
            'test.test_email.test_pickleable', 
            'test.test_email.test_policy', 
            'test.test_email.test_utils', 
            'test.test_email.torture_test', 'test.test_embed', 
            'test.test_ensurepip', 'test.test_enum', 
            'test.test_enumerate', 'test.test_eof', 'test.test_epoll', 
            'test.test_errno', 'test.test_exception_hierarchy', 
            'test.test_exceptions', 'test.test_exception_variations', 
            'test.test_extcall', 'test.test_faulthandler', 
            'test.test_fcntl', 'test.test_file', 'test.test_filecmp', 
            'test.test_file_eintr', 'test.test_fileinput', 
            'test.test_fileio', 'test.test_finalization', 
            'test.test_float', 'test.test_flufl', 'test.test_fnmatch', 
            'test.test_fork1', 'test.test_format', 
            'test.test_fractions', 'test.test_frame', 
            'test.test_frozen', 'test.test_fstring', 
            'test.test_ftplib', 'test.test_funcattrs', 
            'test.test_functools', 'test.test___future__', 
            'test.test_future', 'test.test_future3', 
            'test.test_future4', 'test.test_future5', 'test.test_gc', 
            'test.test_gdb', 'test.test_generators', 
            'test.test_generator_stop', 'test.test_genericclass', 
            'test.test_genericpath', 'test.test_genexps', 
            'test.test_getargs2', 'test.test_getopt', 
            'test.test_getpass', 'test.test_gettext', 
            'test.test_glob', 'test.test_global', 'test.test_grammar', 
            'test.test_grp', 'test.test_gzip', 'test.test_hash', 
            'test.test_hashlib', 'test.test_heapq', 'test.test_hmac', 
            'test.test_html', 'test.test_htmlparser', 
            'test.test_http_cookiejar', 'test.test_http_cookies', 
            'test.test_httplib', 'test.test_httpservers', 
            'test.test_idle', 'test.test_imaplib', 'test.test_imghdr', 
            'test.test_imp', 'test.test_import', 
            'test.test_import.data.circular_imports.basic', 
            'test.test_import.data.circular_imports.basic2', 
            'test.test_import.data.circular_imports.binding', 
            'test.test_import.data.circular_imports.binding2', 
            'test.test_import.data.circular_imports.from_cycle1', 
            'test.test_import.data.circular_imports.from_cycle2', 
            'test.test_import.data.circular_imports.indirect', 
            'test.test_import.data.circular_imports.rebinding', 
            'test.test_import.data.circular_imports.rebinding2', 
            'test.test_import.data.circular_imports.source', 
            'test.test_import.data.circular_imports.subpackage', 
            'test.test_import.data.circular_imports.subpkg.subpackage2', 
            'test.test_import.data.circular_imports.subpkg.util', 
            'test.test_import.data.circular_imports.use', 
            'test.test_import.data.circular_imports.util', 
            'test.test_import.data.package', 
            'test.test_import.data.package2.submodule1', 
            'test.test_import.data.package2.submodule2', 
            'test.test_import.data.package.submodule', 
            'test.test_importlib', 'test.test_importlib.abc', 
            'test.test_importlib.builtin', 
            'test.test_importlib.builtin.__main__', 
            'test.test_importlib.builtin.test_finder', 
            'test.test_importlib.builtin.test_loader', 
            'test.test_importlib.data', 'test.test_importlib.data01', 
            'test.test_importlib.data01.subdirectory', 
            'test.test_importlib.data02', 
            'test.test_importlib.data02.one', 
            'test.test_importlib.data02.two', 
            'test.test_importlib.data03', 
            'test.test_importlib.data03.namespace.portion1', 
            'test.test_importlib.data03.namespace.portion2', 
            'test.test_importlib.extension', 
            'test.test_importlib.extension.__main__', 
            'test.test_importlib.extension.test_case_sensitivity', 
            'test.test_importlib.extension.test_finder', 
            'test.test_importlib.extension.test_loader', 
            'test.test_importlib.extension.test_path_hook', 
            'test.test_importlib.fixtures', 
            'test.test_importlib.frozen', 
            'test.test_importlib.frozen.__main__', 
            'test.test_importlib.frozen.test_finder', 
            'test.test_importlib.frozen.test_loader', 
            'test.test_importlib.import_', 
            'test.test_importlib.import_.__main__', 
            'test.test_importlib.import_.test_api', 
            'test.test_importlib.import_.test_caching', 
            'test.test_importlib.import_.test_fromlist', 
            'test.test_importlib.import_.test___loader__', 
            'test.test_importlib.import_.test_meta_path', 
            'test.test_importlib.import_.test___package__', 
            'test.test_importlib.import_.test_packages', 
            'test.test_importlib.import_.test_path', 
            'test.test_importlib.import_.test_relative_imports', 
            'test.test_importlib.__main__', 
            'test.test_importlib.namespace_pkgs.both_portions.foo.one', 
            'test.test_importlib.namespace_pkgs.both_portions.foo.two', 
            'test.test_importlib.namespace_pkgs.module_and_namespace_package.a_test', 
            'test.test_importlib.namespace_pkgs.not_a_namespace_pkg.foo', 
            'test.test_importlib.namespace_pkgs.not_a_namespace_pkg.foo.one', 
            'test.test_importlib.namespace_pkgs.portion1.foo.one', 
            'test.test_importlib.namespace_pkgs.portion2.foo.two', 
            'test.test_importlib.namespace_pkgs.project1.parent.child.one', 
            'test.test_importlib.namespace_pkgs.project2.parent.child.two', 
            'test.test_importlib.namespace_pkgs.project3.parent.child.three', 
            'test.test_importlib.source', 
            'test.test_importlib.source.__main__', 
            'test.test_importlib.source.test_case_sensitivity', 
            'test.test_importlib.source.test_file_loader', 
            'test.test_importlib.source.test_finder', 
            'test.test_importlib.source.test_path_hook', 
            'test.test_importlib.source.test_source_encoding', 
            'test.test_importlib.test_abc', 
            'test.test_importlib.test_api', 
            'test.test_importlib.test_lazy', 
            'test.test_importlib.test_locks', 
            'test.test_importlib.test_main', 
            'test.test_importlib.test_metadata_api', 
            'test.test_importlib.test_namespace_pkgs', 
            'test.test_importlib.test_open', 
            'test.test_importlib.test_path', 
            'test.test_importlib.test_read', 
            'test.test_importlib.test_resource', 
            'test.test_importlib.test_spec', 
            'test.test_importlib.test_util', 
            'test.test_importlib.test_windows', 
            'test.test_importlib.test_zip', 
            'test.test_importlib.util', 
            'test.test_importlib.zipdata01', 
            'test.test_importlib.zipdata02', 
            'test.test_import.__main__', 'test.test_index', 
            'test.test_inspect', 'test.test_int', 
            'test.test_int_literal', 'test.test_io', 
            'test.test_ioctl', 'test.test_ipaddress', 
            'test.test_isinstance', 'test.test_iter', 
            'test.test_iterlen', 'test.test_itertools', 
            'test.test_json', 'test.test_json.__main__', 
            'test.test_json.test_decode', 
            'test.test_json.test_default', 'test.test_json.test_dump', 
            'test.test_json.test_encode_basestring_ascii', 
            'test.test_json.test_enum', 'test.test_json.test_fail', 
            'test.test_json.test_float', 'test.test_json.test_indent', 
            'test.test_json.test_pass1', 'test.test_json.test_pass2', 
            'test.test_json.test_pass3', 
            'test.test_json.test_recursion', 
            'test.test_json.test_scanstring', 
            'test.test_json.test_separators', 
            'test.test_json.test_speedups', 
            'test.test_json.test_tool', 'test.test_json.test_unicode', 
            'test.test_keyword', 'test.test_keywordonlyarg', 
            'test.test_kqueue', 'test.test_largefile', 
            'test.test_lib2to3', 'test.test_linecache', 
            'test.test_list', 'test.test_listcomps', 
            'test.test_lltrace', 'test.test__locale', 
            'test.test_locale', 'test.test_logging', 'test.test_long', 
            'test.test_longexp', 'test.test_lzma', 
            'test.test_mailbox', 'test.test_mailcap', 
            'test.test_marshal', 'test.test_math', 
            'test.test_memoryio', 'test.test_memoryview', 
            'test.test_metaclass', 'test.test_mimetypes', 
            'test.test_minidom', 'test.test_mmap', 'test.test_module', 
            'test.test_modulefinder', 'test.test_msilib', 
            'test.test_multibytecodec', 'test._test_multiprocessing', 
            'test.test_multiprocessing_fork', 
            'test.test_multiprocessing_forkserver', 
            'test.test_multiprocessing_main_handling', 
            'test.test_multiprocessing_spawn', 
            'test.test_named_expressions', 'test.test_netrc', 
            'test.test_nis', 'test.test_nntplib', 
            'test.test_normalization', 'test.test_ntpath', 
            'test.test_numeric_tower', 'test.test__opcode', 
            'test.test_opcodes', 'test.test_openpty', 
            'test.test_operator', 'test.test_optparse', 
            'test.test_ordered_dict', 'test.test_os', 
            'test.test_ossaudiodev', 'test.test_osx_env', 
            'test.test__osx_support', 'test.test_parser', 
            'test.test_pathlib', 'test.test_pdb', 
            'test.test_peepholer', 'test.test_pickle', 
            'test.test_picklebuffer', 'test.test_pickletools', 
            'test.test_pipes', 'test.test_pkg', 'test.test_pkgimport', 
            'test.test_pkgutil', 'test.test_platform', 
            'test.test_plistlib', 'test.test_poll', 'test.test_popen', 
            'test.test_poplib', 'test.test_positional_only_arg', 
            'test.test_posix', 'test.test_posixpath', 'test.test_pow', 
            'test.test_pprint', 'test.test_print', 
            'test.test_profile', 'test.test_property', 
            'test.test_pstats', 'test.test_pty', 'test.test_pulldom', 
            'test.test_pwd', 'test.test_pyclbr', 
            'test.test_py_compile', 'test.test_pydoc', 
            'test.test_pyexpat', 'test.test_queue', 
            'test.test_quopri', 'test.test_raise', 'test.test_random', 
            'test.test_range', 'test.test_re', 'test.test_readline', 
            'test.test_regrtest', 'test.test_repl', 
            'test.test_reprlib', 'test.test_resource', 
            'test.test_richcmp', 'test.test_rlcompleter', 
            'test.test_robotparser', 'test.test_runpy', 
            'test.test_sax', 'test.test_sched', 'test.test_scope', 
            'test.test_script_helper', 'test.test_secrets', 
            'test.test_select', 'test.test_selectors', 
            'test.test_set', 'test.test_setcomps', 'test.test_shelve', 
            'test.test_shlex', 'test.test_shutil', 'test.test_signal', 
            'test.test_site', 'test.test_slice', 'test.test_smtpd', 
            'test.test_smtplib', 'test.test_smtpnet', 
            'test.test_sndhdr', 'test.test_socket', 
            'test.test_socketserver', 'test.test_sort', 
            'test.test_source_encoding', 'test.test_spwd', 
            'test.test_sqlite', 'test.test_ssl', 
            'test.test_startfile', 'test.test_stat', 
            'test.test_statistics', 'test.test_strftime', 
            'test.test_string', 'test.test_string_literals', 
            'test.test_stringprep', 'test.test_strptime', 
            'test.test_strtod', 'test.test_struct', 
            'test.test_structmembers', 'test.test_structseq', 
            'test.test_subclassinit', 'test.test_subprocess', 
            'test.test_sunau', 'test.test_sundry', 'test.test_super', 
            'test.test_support', 'test.test_symbol', 
            'test.test_symtable', 'test.test_syntax', 'test.test_sys', 
            'test.test_sysconfig', 'test.test_syslog', 
            'test.test_sys_setprofile', 'test.test_sys_settrace', 
            'test.test_tabnanny', 'test.test_tarfile', 
            'test.test_tcl', 'test.test_telnetlib', 
            'test.test_tempfile', 'test.test_textwrap', 
            'test.test_thread', 'test.test_threaded_import', 
            'test.test_threadedtempfile', 'test.test_threading', 
            'test.test_threading_local', 'test.test_threadsignals', 
            'test.test_time', 'test.test_timeit', 'test.test_timeout', 
            'test.test_tix', 'test.test_tk', 'test.test_tokenize', 
            'test.test_tools', 'test.test_tools.__main__', 
            'test.test_tools.test_fixcid', 
            'test.test_tools.test_gprof2html', 
            'test.test_tools.test_i18n', 'test.test_tools.test_lll', 
            'test.test_tools.test_md5sum', 
            'test.test_tools.test_pathfix', 
            'test.test_tools.test_pdeps', 
            'test.test_tools.test_pindent', 
            'test.test_tools.test_reindent', 
            'test.test_tools.test_sundry', 
            'test.test_tools.test_unparse', 'test.test_trace', 
            'test.test_traceback', 'test.test_tracemalloc', 
            'test.test_ttk_guionly', 'test.test_ttk_textonly', 
            'test.test_tuple', 'test.test_turtle', 
            'test.test_typechecks', 'test.test_type_comments', 
            'test.test_types', 'test.test_typing', 'test.test_ucn', 
            'test.test_unary', 'test.test_unicode', 
            'test.test_unicodedata', 'test.test_unicode_file', 
            'test.test_unicode_file_functions', 
            'test.test_unicode_identifiers', 'test.test_unittest', 
            'test.test_univnewlines', 'test.test_unpack', 
            'test.test_unpack_ex', 'test.test_urllib', 
            'test.test_urllib2', 'test.test_urllib2_localnet', 
            'test.test_urllib2net', 'test.test_urllibnet', 
            'test.test_urllib_response', 'test.test_urlparse', 
            'test.test_userdict', 'test.test_userlist', 
            'test.test_userstring', 'test.test_utf8_mode', 
            'test.test_utf8source', 'test.test_uu', 'test.test_uuid', 
            'test.test_venv', 'test.test_wait3', 'test.test_wait4', 
            'test.test_warnings', 
            'test.test_warnings.data.import_warning', 
            'test.test_warnings.data.stacklevel', 
            'test.test_warnings.__main__', 'test.test_wave', 
            'test.test_weakref', 'test.test_weakset', 
            'test.test_webbrowser', 'test.test_winconsoleio', 
            'test.test_winreg', 'test.test_winsound', 
            'test.test_with', 'test.test_wsgiref', 'test.test_xdrlib', 
            'test.test_xml_dom_minicompat', 'test.test_xml_etree', 
            'test.test_xml_etree_c', 'test.test_xmlrpc', 
            'test.test_xmlrpc_net', 'test.test__xxsubinterpreters', 
            'test.test_xxtestfuzz', 'test.test_yield_from', 
            'test.test_zipapp', 'test.test_zipfile', 
            'test.test_zipfile64', 'test.test_zipimport', 
            'test.test_zipimport_support', 'test.test_zlib', 
            'test.tf_inherit_check', 'test.threaded_import_hangers', 
            'test.time_hashlib', 'test.tracedmodules', 
            'test.tracedmodules.testmod', 'test.win_console_handler', 
            'test.xmltests', 
            'test.ziptestdata.testdata_module_inside_zip', 'textwrap', 
            'this', '_thread', 'threading', '_threading_local', 
            'time', 'timeit', '_tkinter', 'tkinter', 
            'tkinter.colorchooser', 'tkinter.commondialog', 
            'tkinter.constants', 'tkinter.dialog', 'tkinter.dnd', 
            'tkinter.filedialog', 'tkinter.font', 'tkinter.__main__', 
            'tkinter.messagebox', 'tkinter.scrolledtext', 
            'tkinter.simpledialog', 'tkinter.test', 
            'tkinter.test.runtktests', 'tkinter.test.support', 
            'tkinter.test.test_tkinter', 
            'tkinter.test.test_tkinter.test_font', 
            'tkinter.test.test_tkinter.test_geometry_managers', 
            'tkinter.test.test_tkinter.test_images', 
            'tkinter.test.test_tkinter.test_loadtk', 
            'tkinter.test.test_tkinter.test_misc', 
            'tkinter.test.test_tkinter.test_text', 
            'tkinter.test.test_tkinter.test_variables', 
            'tkinter.test.test_tkinter.test_widgets', 
            'tkinter.test.test_ttk', 
            'tkinter.test.test_ttk.test_extensions', 
            'tkinter.test.test_ttk.test_functions', 
            'tkinter.test.test_ttk.test_style', 
            'tkinter.test.test_ttk.test_widgets', 
            'tkinter.test.widget_tests', 'tkinter.tix', 'tkinter.ttk', 
            'token', 'tokenize', 'trace', 'traceback', '_tracemalloc', 
            'tracemalloc', 'tty', 'turtle', 'turtledemo', 
            'turtledemo.bytedesign', 'turtledemo.chaos', 
            'turtledemo.clock', 'turtledemo.colormixer', 
            'turtledemo.forest', 'turtledemo.fractalcurves', 
            'turtledemo.lindenmayer', 'turtledemo.__main__', 
            'turtledemo.minimal_hanoi', 'turtledemo.nim', 
            'turtledemo.paint', 'turtledemo.peace', 
            'turtledemo.penrose', 'turtledemo.planet_and_moon', 
            'turtledemo.rosette', 'turtledemo.round_dance', 
            'turtledemo.sorting_animate', 'turtledemo.tree', 
            'turtledemo.two_canvases', 'turtledemo.yinyang', 'types', 
            'typing', 'typing.io', 'typing.re', 'unicodedata', 
            'unittest', 'unittest.async_case', 'unittest.case', 
            'unittest.loader', 'unittest._log', 'unittest.__main__', 
            'unittest.main', 'unittest.mock', 'unittest.result', 
            'unittest.runner', 'unittest.signals', 'unittest.suite', 
            'unittest.test', 'unittest.test.dummy', 
            'unittest.test.__main__', 'unittest.test.support', 
            'unittest.test.test_assertions', 
            'unittest.test.test_async_case', 
            'unittest.test.test_break', 'unittest.test.test_case', 
            'unittest.test.test_discovery', 
            'unittest.test.test_functiontestcase', 
            'unittest.test.test_loader', 'unittest.test.testmock', 
            'unittest.test.testmock.__main__', 
            'unittest.test.testmock.support', 
            'unittest.test.testmock.testasync', 
            'unittest.test.testmock.testcallable', 
            'unittest.test.testmock.testhelpers', 
            'unittest.test.testmock.testmagicmethods', 
            'unittest.test.testmock.testmock', 
            'unittest.test.testmock.testpatch', 
            'unittest.test.testmock.testsealable', 
            'unittest.test.testmock.testsentinel', 
            'unittest.test.testmock.testwith', 
            'unittest.test.test_program', 'unittest.test.test_result', 
            'unittest.test.test_runner', 'unittest.test.test_setups', 
            'unittest.test.test_skipping', 'unittest.test.test_suite', 
            'unittest.test._test_warnings', 'unittest.util', 'urllib', 
            'urllib.error', 'urllib.parse', 'urllib.request', 
            'urllib.response', 'urllib.robotparser', 'uu', '_uuid', 
            'uuid', 'venv', 'venv.__main__', '_warnings', 'warnings', 
            'wave', '_weakref', 'weakref', '_weakrefset', 
            'webbrowser', 'winreg', 'winsound', 'wsgiref', 
            'wsgiref.handlers', 'wsgiref.headers', 
            'wsgiref.simple_server', 'wsgiref.util', 
            'wsgiref.validate', 'xdrlib', 'xml', 'xml.dom', 
            'xml.dom.domreg', 'xml.dom.expatbuilder', 
            'xml.dom.minicompat', 'xml.dom.minidom', 
            'xml.dom.NodeFilter', 'xml.dom.pulldom', 
            'xml.dom.xmlbuilder', 'xml.etree', 
            'xml.etree.cElementTree', 'xml.etree.ElementInclude', 
            'xml.etree.ElementPath', 'xml.etree.ElementTree', 
            'xml.parsers', 'xml.parsers.expat', 
            'xml.parsers.expat.errors', 'xml.parsers.expat.model', 
            'xmlrpc', 'xmlrpc.client', 'xmlrpc.server', 'xml.sax', 
            'xml.sax._exceptions', 'xml.sax.expatreader', 
            'xml.sax.handler', 'xml.sax.saxutils', 
            'xml.sax.xmlreader', 'xxlimited', '_xxsubinterpreters', 
            'xxsubtype', '_xxtestfuzz', 'zipapp', 'zipfile', 
            'zipimport', 'zlib', 'zoneinfo', 'zoneinfo._common', 
            'zoneinfo._tzpath', 'zoneinfo._zoneinfo']
        # Sometimes, a module is imported in python using a different name than is required in the "pip install" command. Keep track of these exceptions here.
        self.module_aliases: Dict[str, str] = {
            # I added these manually by asking ChatGPT what pip aliases are different than their import commands:
            # 'import name' : 'pip install name'
            'osgeo': 'gdal', #osgeo is the import name for gdal
            'ffmpeg': 'ffmpeg-python',
            'cv2': 'opencv-python',
            'jnp': 'jax.numpy',
#            'sm': 'statsmodels',
            'netCDF4': 'netcdf4',
            'skill_metrics': 'SkillMetrics',
            # This list is from the pipreqs repo in file "mapping", retrieved on 2024-08-15 from here: https://github.com/bndr/pipreqs
            'AFQ': 'pyAFQ',
            'AG_fft_tools': 'agpy',
            'ANSI': 'pexpect',
            'Adafruit': 'Adafruit_Libraries',
            'App': 'Zope2',
            'Asterisk': 'py_Asterisk',
            'BB_jekyll_hook': 'bitbucket_jekyll_hook',
            'Banzai': 'Banzai_NGS',
            'BeautifulSoupTests': 'BeautifulSoup',
            'BioSQL': 'biopython',
            'BuildbotStatusShields': 'BuildbotEightStatusShields',
            'ComputedAttribute': 'ExtensionClass',
            'constraint': 'python-constraint',
            'Crypto': 'pycryptodome',
            'Cryptodome': 'pycryptodomex',
            'FSM': 'pexpect',
            'FiftyOneDegrees': '51degrees_mobile_detector_v3_wrapper',
            'functional': 'pyfunctional',
            'GeoBaseMain': 'GeoBasesDev',
            'GeoBases': 'GeoBasesDev',
            'Globals': 'Zope2',
            'HelpSys': 'Zope2',
            'IPython': 'ipython',
            'Kittens': 'astro_kittens',
            'Levenshtein': 'python_Levenshtein',
            'Lifetime': 'Zope2',
            'MethodObject': 'ExtensionClass',
            'MySQLdb': 'MySQL-python',
            'OFS': 'Zope2',
            'OpenGL': 'PyOpenGL',
            'OpenSSL': 'pyOpenSSL',
            'PIL': 'Pillow',
            'Products': 'Zope2',
            'PyWCSTools': 'astLib',
            'Pyxides': 'astro_pyxis',
            'QtCore': 'PySide',
            'S3': 's3cmd',
            'SCons': 'pystick',
            'Shared': 'Zope2',
            'Signals': 'Zope2',
            'Stemmer': 'PyStemmer',
            'Testing': 'Zope2',
            'TopZooTools': 'topzootools',
            'TreeDisplay': 'DocumentTemplate',
            'WorkingWithDocumentConversion': 'aspose_pdf_java_for_python',
            'ZPublisher': 'Zope2',
            'ZServer': 'Zope2',
            'ZTUtils': 'Zope2',
            'aadb': 'auto_adjust_display_brightness',
            'abakaffe': 'abakaffe_cli',
            'abiosgaming': 'abiosgaming.py',
            'abiquo': 'abiquo_api',
            'abl': 'abl.cssprocessor',
            'abl': 'abl.robot',
            'abl': 'abl.util',
            'abl': 'abl.vpath',
            'abo': 'abo_generator',
            'abris_transform': 'abris',
            'abstract': 'abstract.jwrotator',
            'abu': 'abu.admin',
            'ac_flask': 'AC_Flask_HipChat',
            'acg': 'anikom15',
            'acme': 'acme.dchat',
            'acme': 'acme.hello',
            'acted': 'acted.projects',
            'action': 'ActionServer',
            'actionbar': 'actionbar.panel',
            'activehomed': 'afn',
            'activepapers': 'ActivePapers.Py',
            'address_book': 'address_book_lansry',
            'adi': 'adi.commons',
            'adi': 'adi.devgen',
            'adi': 'adi.fullscreen',
            'adi': 'adi.init',
            'adi': 'adi.playlist',
            'adi': 'adi.samplecontent',
            'adi': 'adi.slickstyle',
            'adi': 'adi.suite',
            'adi': 'adi.trash',
            'adict': 'aDict2',
            'aditam': 'aditam.agent',
            'aditam': 'aditam.core',
            'adiumsh': 'adium_sh',
            'adjector': 'AdjectorClient',
            'adjector': 'AdjectorTracPlugin',
            'adkit': 'Banner_Ad_Toolkit',
            'admin_tools': 'django_admin_tools',
            'adminishcategories': 'adminish_categories',
            'adminsortable': 'django_admin_sortable',
            'adspygoogle': 'adspygoogle.adwords',
            'advancedcaching': 'agtl',
            'adytum': 'Adytum_PyMonitor',
            'affinitic': 'affinitic.docpyflakes',
            'affinitic': 'affinitic.recipe.fakezope2eggs',
            'affinitic': 'affinitic.simplecookiecuttr',
            'affinitic': 'affinitic.verifyinterface',
            'affinitic': 'affinitic.zamqp',
            'afpy': 'afpy.xap',
            'agatesql': 'agate_sql',
            'ageliaco': 'ageliaco.recipe.csvconfig',
            'agent_http': 'agent.http',
            'agora': 'Agora_Client',
            'agora': 'Agora_Fountain',
            'agora': 'Agora_Fragment',
            'agora': 'Agora_Planner',
            'agora': 'Agora_Service_Provider',
            'agoraplex': 'agoraplex.themes.sphinx',
            'agsci': 'agsci.blognewsletter',
            'agx': 'agx.core',
            'agx': 'agx.dev',
            'agx': 'agx.generator.buildout',
            'agx': 'agx.generator.dexterity',
            'agx': 'agx.generator.generator',
            'agx': 'agx.generator.plone',
            'agx': 'agx.generator.pyegg',
            'agx': 'agx.generator.sql',
            'agx': 'agx.generator.uml',
            'agx': 'agx.generator.zca',
            'agx': 'agx.transform.uml2fs',
            'agx': 'agx.transform.xmi2uml',
            'aimes': 'aimes.bundle',
            'aimes': 'aimes.skeleton',
            'aio': 'aio.app',
            'aio': 'aio.config',
            'aio': 'aio.core',
            'aio': 'aio.signals',
            'aiohs2': 'aio_hs2',
            'aioroutes': 'aio_routes',
            'aios3': 'aio_s3',
            'airbrake': 'airbrake_flask',
            'airship': 'airship_icloud',
            'airship': 'airship_steamcloud',
            'airflow': 'apache-airflow',
            'akamai': 'edgegrid_python',
            'alation': 'alation_api',
            'alba_client': 'alba_client_python',
            'alburnum': 'alburnum_maas_client',
            'alchemist': 'alchemist.audit',
            'alchemist': 'alchemist.security',
            'alchemist': 'alchemist.traversal',
            'alchemist': 'alchemist.ui',
            'alchemyapi': 'alchemyapi_python',
            'alerta': 'alerta_server',
            'alexandria_upload': 'Alexandria_Upload_Utils',
            'alibaba': 'alibaba_python_sdk',
            'aliyun': 'aliyun_python_sdk',
            'aliyuncli': 'alicloudcli',
            'aliyunsdkacs': 'aliyun_python_sdk_acs',
            'aliyunsdkbatchcompute': 'aliyun_python_sdk_batchcompute',
            'aliyunsdkbsn': 'aliyun_python_sdk_bsn',
            'aliyunsdkbss': 'aliyun_python_sdk_bss',
            'aliyunsdkcdn': 'aliyun_python_sdk_cdn',
            'aliyunsdkcms': 'aliyun_python_sdk_cms',
            'aliyunsdkcore': 'aliyun_python_sdk_core',
            'aliyunsdkcrm': 'aliyun_python_sdk_crm',
            'aliyunsdkcs': 'aliyun_python_sdk_cs',
            'aliyunsdkdrds': 'aliyun_python_sdk_drds',
            'aliyunsdkecs': 'aliyun_python_sdk_ecs',
            'aliyunsdkess': 'aliyun_python_sdk_ess',
            'aliyunsdkft': 'aliyun_python_sdk_ft',
            'aliyunsdkmts': 'aliyun_python_sdk_mts',
            'aliyunsdkocs': 'aliyun_python_sdk_ocs',
            'aliyunsdkoms': 'aliyun_python_sdk_oms',
            'aliyunsdkossadmin': 'aliyun_python_sdk_ossadmin',
            'aliyunsdkr-kvstore': 'aliyun_python_sdk_r_kvstore',
            'aliyunsdkram': 'aliyun_python_sdk_ram',
            'aliyunsdkrds': 'aliyun_python_sdk_rds',
            'aliyunsdkrisk': 'aliyun_python_sdk_risk',
            'aliyunsdkros': 'aliyun_python_sdk_ros',
            'aliyunsdkslb': 'aliyun_python_sdk_slb',
            'aliyunsdksts': 'aliyun_python_sdk_sts',
            'aliyunsdkubsms': 'aliyun_python_sdk_ubsms',
            'aliyunsdkyundun': 'aliyun_python_sdk_yundun',
            'allattachments': 'AllAttachmentsMacro',
            'allocine': 'allocine_wrapper',
            'allowedsites': 'django_allowedsites',
            'alm': 'alm.solrindex',
            'aloft': 'aloft.py',
            'alpacalib': 'alpaca',
            'alphabetic': 'alphabetic_simple',
            'alphasms': 'alphasms_client',
            'altered': 'altered.states',
            'alterootheme': 'alterootheme.busycity',
            'alterootheme': 'alterootheme.intensesimplicity',
            'alterootheme': 'alterootheme.lazydays',
            'alurinium': 'alurinium_image_processing',
            'alxlib': 'alx',
            'amara3': 'amara3_iri',
            'amara3': 'amara3_xml',
            'amazon': 'AmazonAPIWrapper',
            'amazon': 'python_amazon_simple_product_api',
            'ambikesh1349-1': 'ambikesh1349_1',
            'ambilight': 'AmbilightParty',
            'amifs': 'amifs_core',
            'amiorganizer': 'ami_organizer',
            'amitu': 'amitu.lipy',
            'amitu': 'amitu_putils',
            'amitu': 'amitu_websocket_client',
            'amitu': 'amitu_zutils',
            'amltlearn': 'AMLT_learn',
            'amocrm': 'amocrm_api',
            'amqpdispatcher': 'amqp_dispatcher',
            'amqpstorm': 'AMQP_Storm',
            'analytics': 'analytics_python',
            'analyzedir': 'AnalyzeDirectory',
            'ancientsolutions': 'ancientsolutions_crypttools',
            'anderson_paginator': 'anderson.paginator',
            'android_clean_app': 'android_resource_remover',
            'anel_power_control': 'AnelPowerControl',
            'angus': 'angus_sdk_python',
            'annalist_root': 'Annalist',
            'annogesiclib': 'ANNOgesic',
            'ansible-role-apply': 'ansible_role_apply',
            'ansibledebugger': 'ansible_playbook_debugger',
            'ansibledocgen': 'ansible_docgen',
            'ansibleflow': 'ansible_flow',
            'ansibleinventorygrapher': 'ansible_inventory_grapher',
            'ansiblelint': 'ansible_lint',
            'ansiblerolesgraph': 'ansible_roles_graph',
            'ansibletools': 'ansible_tools',
            'anthill': 'anthill.exampletheme',
            'anthill': 'anthill.skinner',
            'anthill': 'anthill.tal.macrorenderer',
            'anthrax': 'AnthraxDojoFrontend',
            'anthrax': 'AnthraxHTMLInput',
            'anthrax': 'AnthraxImage',
            'antisphinx': 'antiweb',
            'antispoofing': 'antispoofing.evaluation',
            'antlr4': 'antlr4_python2_runtime',
            'antlr4': 'antlr4_python3_runtime',
            'antlr4': 'antlr4_python_alt',
            'anybox': 'anybox.buildbot.openerp',
            'anybox': 'anybox.nose.odoo',
            'anybox': 'anybox.paster.odoo',
            'anybox': 'anybox.paster.openerp',
            'anybox': 'anybox.recipe.sysdeps',
            'anybox': 'anybox.scripts.odoo',
            'apiclient': 'google_api_python_client',
            'apitools': 'google_apitools',
            'apm': 'arpm',
            'app_data': 'django_appdata',
            'appconf': 'django_appconf',
            'appd': 'AppDynamicsDownloader',
            'appd': 'AppDynamicsREST',
            'appdynamics_bindeps': 'appdynamics_bindeps_linux_x64',
            'appdynamics_bindeps': 'appdynamics_bindeps_linux_x86',
            'appdynamics_bindeps': 'appdynamics_bindeps_osx_x64',
            'appdynamics_proxysupport': 'appdynamics_proxysupport_linux_x64',
            'appdynamics_proxysupport': 'appdynamics_proxysupport_linux_x86',
            'appdynamics_proxysupport': 'appdynamics_proxysupport_osx_x64',
            'appium': 'Appium_Python_Client',
            'appliapps': 'applibase',
            'appserver': 'broadwick',
            'archetypes': 'archetypes.kss',
            'archetypes': 'archetypes.multilingual',
            'archetypes': 'archetypes.schemaextender',
            'arm': 'ansible_role_manager',
            'armor': 'armor_api',
            'armstrong': 'armstrong.apps.related_content',
            'armstrong': 'armstrong.apps.series',
            'armstrong': 'armstrong.cli',
            'armstrong': 'armstrong.core.arm_access',
            'armstrong': 'armstrong.core.arm_layout',
            'armstrong': 'armstrong.core.arm_sections',
            'armstrong': 'armstrong.core.arm_wells',
            'armstrong': 'armstrong.dev',
            'armstrong': 'armstrong.esi',
            'armstrong': 'armstrong.hatband',
            'armstrong': 'armstrong.templates.standard',
            'armstrong': 'armstrong.utils.backends',
            'armstrong': 'armstrong.utils.celery',
            'arstecnica': 'arstecnica.raccoon.autobahn',
            'arstecnica': 'arstecnica.sqlalchemy.async',
            'article-downloader': 'article_downloader',
            'artifactcli': 'artifact_cli',
            'arvados': 'arvados_python_client',
            'arvados_cwl': 'arvados_cwl_runner',
            'arvnodeman': 'arvados_node_manager',
            'asana_to_github': 'AsanaToGithub',
            'asciibinary': 'AsciiBinaryConverter',
            'asd': 'AdvancedSearchDiscovery',
            'askbot': 'askbot_tuan',
            'askbot': 'askbot_tuanpa',
            'asnhistory': 'asnhistory_redis',
            'aspen_jinja2_renderer': 'aspen_jinja2',
            'aspen_tornado_engine': 'aspen_tornado',
            'asprise_ocr_api': 'asprise_ocr_sdk_python_api',
            'aspy': 'aspy.refactor_imports',
            'aspy': 'aspy.yaml',
            'asterisk': 'asterisk_ami',
            'asts': 'add_asts',
            'asymmetricbase': 'asymmetricbase.enum',
            'asymmetricbase': 'asymmetricbase.fields',
            'asymmetricbase': 'asymmetricbase.logging',
            'asymmetricbase': 'asymmetricbase.utils',
            'asyncirc': 'asyncio_irc',
            'asyncmongoorm': 'asyncmongoorm_je',
            'asyncssh': 'asyncssh_unofficial',
            'athletelist': 'athletelistyy',
            'atm': 'automium',
            'atmosphere': 'atmosphere_python_client',
            'atom': 'gdata',
            'atomic': 'AtomicWrite',
            'atomisator': 'atomisator.db',
            'atomisator': 'atomisator.enhancers',
            'atomisator': 'atomisator.feed',
            'atomisator': 'atomisator.indexer',
            'atomisator': 'atomisator.outputs',
            'atomisator': 'atomisator.parser',
            'atomisator': 'atomisator.readers',
            'atreal': 'atreal.cmfeditions.unlocker',
            'atreal': 'atreal.filestorage.common',
            'atreal': 'atreal.layouts',
            'atreal': 'atreal.mailservices',
            'atreal': 'atreal.massloader',
            'atreal': 'atreal.monkeyplone',
            'atreal': 'atreal.override.albumview',
            'atreal': 'atreal.richfile.preview',
            'atreal': 'atreal.richfile.qualifier',
            'atreal': 'atreal.usersinout',
            'atsim': 'atsim.potentials',
            'attractsdk': 'attract_sdk',
            'audio': 'audio.bitstream',
            'audio': 'audio.coders',
            'audio': 'audio.filters',
            'audio': 'audio.fourier',
            'audio': 'audio.frames',
            'audio': 'audio.lp',
            'audio': 'audio.psychoacoustics',
            'audio': 'audio.quantizers',
            'audio': 'audio.shrink',
            'audio': 'audio.wave',
            'aufrefer': 'auf_refer',
            'auslfe': 'auslfe.formonline.content',
            'auspost': 'auspost_apis',
            'auth0': 'auth0_python',
            'auth_server_client': 'AuthServerClient',
            'authorize': 'AuthorizeSauce',
            'authzpolicy': 'AuthzPolicyPlugin',
            'autobahn': 'autobahn_rce',
            'avatar': 'geonode_avatar',
            'awebview': 'android_webview',
            'azure': 'azure_common',
            'azure': 'azure_mgmt_common',
            'azure': 'azure_mgmt_compute',
            'azure': 'azure_mgmt_network',
            'azure': 'azure_mgmt_nspkg',
            'azure': 'azure_mgmt_resource',
            'azure': 'azure_mgmt_storage',
            'azure': 'azure_nspkg',
            'azure': 'azure_servicebus',
            'azure': 'azure_servicemanagement_legacy',
            'azure': 'azure_storage',
            'b2gcommands': 'b2g_commands',
            'b2gperf': 'b2gperf_v1.3',
            'b2gperf': 'b2gperf_v1.4',
            'b2gperf': 'b2gperf_v2.0',
            'b2gperf': 'b2gperf_v2.1',
            'b2gperf': 'b2gperf_v2.2',
            'b2gpopulate': 'b2gpopulate_v1.3',
            'b2gpopulate': 'b2gpopulate_v1.4',
            'b2gpopulate': 'b2gpopulate_v2.0',
            'b2gpopulate': 'b2gpopulate_v2.1',
            'b2gpopulate': 'b2gpopulate_v2.2',
            'b3j0f': 'b3j0f.annotation',
            'b3j0f': 'b3j0f.aop',
            'b3j0f': 'b3j0f.conf',
            'b3j0f': 'b3j0f.sync',
            'b3j0f': 'b3j0f.utils',
            'babel': 'Babel',
            'babelglade': 'BabelGladeExtractor',
            'backplane': 'backplane2_pyclient',
            'backport_abcoll': 'backport_collections',
            'backports': 'backports.functools_lru_cache',
            'backports': 'backports.inspect',
            'backports': 'backports.pbkdf2',
            'backports': 'backports.shutil_get_terminal_size',
            'backports': 'backports.socketpair',
            'backports': 'backports.ssl',
            'backports': 'backports.ssl_match_hostname',
            'backports': 'backports.statistics',
            'badgekit': 'badgekit_api_client',
            'badlinks': 'BadLinksPlugin',
            'bael': 'bael.project',
            'baidu': 'baidupy',
            'balrog': 'buildtools',
            'baluhn': 'baluhn_redux',
            'bamboo': 'bamboo.pantrybell',
            'bamboo': 'bamboo.scaffold',
            'bamboo': 'bamboo.setuptools_version',
            'bamboo': 'bamboo_data',
            'bamboo': 'bamboo_server',
            'bambu': 'bambu_codemirror',
            'bambu': 'bambu_dataportability',
            'bambu': 'bambu_enqueue',
            'bambu': 'bambu_faq',
            'bambu': 'bambu_ffmpeg',
            'bambu': 'bambu_grids',
            'bambu': 'bambu_international',
            'bambu': 'bambu_jwplayer',
            'bambu': 'bambu_minidetect',
            'bambu': 'bambu_navigation',
            'bambu': 'bambu_notifications',
            'bambu': 'bambu_payments',
            'bambu': 'bambu_pusher',
            'bambu': 'bambu_saas',
            'bambu': 'bambu_sites',
            'banana': 'Bananas',
            'banana': 'banana.maya',
            'bang': 'bangtext',
            'barcode': 'barcode_generator',
            'bark': 'bark_ssg',
            'barking_owl': 'BarkingOwl',
            'bart': 'bart_py',
            'basalt': 'basalt_tasks',
            'base62': 'base_62',
            'basemap': 'basemap_Jim',
            'bash': 'bash_toolbelt',
            'bashutils': 'Python_Bash_Utils',
            'basic_http': 'BasicHttp',
            'basil': 'basil_daq',
            'batchapps': 'azure_batch_apps',
            'bcrypt': 'python_bcrypt',
            'beaker': 'Beaker',
            'beetsplug': 'beets',
            'begin': 'begins',
            'benchit': 'bench_it',
            'beproud': 'beproud.utils',
            'bfillings': 'burrito_fillings',
            'bigjob': 'BigJob',
            'billboard': 'billboard.py',
            'binstar_build_client': 'anaconda_build',
            'binstar_client': 'anaconda_client',
            'biocommons': 'biocommons.dev',
            'birdhousebuilder': 'birdhousebuilder.recipe.conda',
            'birdhousebuilder': 'birdhousebuilder.recipe.docker',
            'birdhousebuilder': 'birdhousebuilder.recipe.redis',
            'birdhousebuilder': 'birdhousebuilder.recipe.supervisor',
            'blender26-meshio': 'pymeshio',
            'bootstrap': 'BigJob',
            'borg': 'borg.localrole',
            'bow': 'bagofwords',
            'bpdb': 'bpython',
            'bqapi': 'bisque_api',
            'braces': 'django_braces',
            'briefscaster': 'briefs_caster',
            'brisa_media_server/plugins': 'brisa_media_server_plugins',
            'brkt_requests': 'brkt_sdk',
            'broadcastlogging': 'broadcast_logging',
            'brocadetool': 'brocade_tool',
            'bronto': 'bronto_python',
            'brownie': 'Brownie',
            'browsermobproxy': 'browsermob_proxy',
            'brubeckmysql': 'brubeck_mysql',
            'brubeckoauth': 'brubeck_oauth',
            'brubeckservice': 'brubeck_service',
            'brubeckuploader': 'brubeck_uploader',
            'bs4': 'beautifulsoup4',
            'bson': 'pymongo',
            'bst': 'bst.pygasus.core',
            'bst': 'bst.pygasus.datamanager',
            'bst': 'bst.pygasus.demo',
            'bst': 'bst.pygasus.i18n',
            'bst': 'bst.pygasus.resources',
            'bst': 'bst.pygasus.scaffolding',
            'bst': 'bst.pygasus.security',
            'bst': 'bst.pygasus.session',
            'bst': 'bst.pygasus.wsgi',
            'btable': 'btable_py',
            'btapi': 'bananatag_api',
            'btceapi': 'btce_api',
            'btcebot': 'btce_bot',
            'btsync': 'btsync.py',
            'buck': 'buck.pprint',
            'bud': 'bud.nospam',
            'budy': 'budy_api',
            'buffer': 'buffer_alpaca',
            'buggd': 'bug.gd',
            'bugle': 'bugle_sites',
            'bugspots': 'bug_spots',
            'bugzilla': 'python_bugzilla',
            'bugzscout': 'bugzscout_py',
            'buildTools': 'ajk_ios_buildTools',
            'buildnotifylib': 'BuildNotify',
            'buildout': 'buildout.bootstrap',
            'buildout': 'buildout.disablessl',
            'buildout': 'buildout.dumppickedversions',
            'buildout': 'buildout.dumppickedversions2',
            'buildout': 'buildout.dumprequirements',
            'buildout': 'buildout.eggnest',
            'buildout': 'buildout.eggscleaner',
            'buildout': 'buildout.eggsdirectories',
            'buildout': 'buildout.eggtractor',
            'buildout': 'buildout.extensionscripts',
            'buildout': 'buildout.locallib',
            'buildout': 'buildout.packagename',
            'buildout': 'buildout.recipe.isolation',
            'buildout': 'buildout.removeaddledeggs',
            'buildout': 'buildout.requirements',
            'buildout': 'buildout.sanitycheck',
            'buildout': 'buildout.sendpickedversions',
            'buildout': 'buildout.threatlevel',
            'buildout': 'buildout.umask',
            'buildout': 'buildout.variables',
            'buildslave': 'buildbot_slave',
            'builtins': 'pies2overrides',
            'bumper': 'bumper_lib',
            'bumple': 'bumple_downloader',
            'bundesliga': 'bundesliga_cli',
            'bundlemaker': 'bundlemanager',
            'burpui': 'burp_ui',
            'busyflow': 'busyflow.pivotal',
            'buttercms-django': 'buttercms_django',
            'buzz': 'buzz_python_client',
            'bvc': 'buildout_versions_checker',
            'bvggrabber': 'bvg_grabber',
            'byond': 'BYONDTools',
            'bzETL': 'Bugzilla_ETL',
            'bzlib': 'bugzillatools',
            'bzrlib': 'bzr',
            'bzrlib': 'bzr_automirror',
            'bzrlib': 'bzr_bash_completion',
            'bzrlib': 'bzr_colo',
            'bzrlib': 'bzr_killtrailing',
            'bzrlib': 'bzr_pqm',
            'c2c': 'c2c.cssmin',
            'c2c': 'c2c.recipe.closurecompile',
            'c2c': 'c2c.recipe.cssmin',
            'c2c': 'c2c.recipe.jarfile',
            'c2c': 'c2c.recipe.msgfmt',
            'c2c': 'c2c.recipe.pkgversions',
            'c2c': 'c2c.sqlalchemy.rest',
            'c2c': 'c2c.versions',
            'c2c_recipe_facts': 'c2c.recipe.facts',
            'cabalgata': 'cabalgata_silla_de_montar',
            'cabalgata': 'cabalgata_zookeeper',
            'cache_utils': 'django_cache_utils',
            'captcha': 'django_recaptcha',
            'cartridge': 'Cartridge',
            'cassandra': 'cassandra_driver',
            'cassandralauncher': 'CassandraLauncher',
            'cc42': '42qucc',
            'cerberus': 'Cerberus',
            'cfnlint': 'cfn-lint',
            'chameleon': 'Chameleon',
            'charmtools': 'charm_tools',
            'chef': 'PyChef',
            'chip8': 'c8d',
            'cjson': 'python_cjson',
            'classytags': 'django_classy_tags',
            'cloghandler': 'ConcurrentLogHandler',
            'clonevirtualenv': 'virtualenv_clone',
            'cloud-insight': 'al_cloudinsight',
            'cloud_admin': 'adminapi',
            'cloudservers': 'python_cloudservers',
            'clusterconsole': 'cerebrod',
            'clustersitter': 'cerebrod',
            'cms': 'django_cms',
            'colander': 'ba_colander',
            'colors': 'ansicolors',
            'compile': 'bf_lc3',
            'compose': 'docker_compose',
            'compressor': 'django_compressor',
            'concurrent': 'futures',
            'configargparse': 'ConfigArgParse',
            'configparser': 'pies2overrides',
            'contracts': 'PyContracts',
            'coordination': 'BigJob',
            'copyreg': 'pies2overrides',
            'corebio': 'weblogo',
            'couchapp': 'Couchapp',
            'couchdb': 'CouchDB',
            'couchdbcurl': 'couchdb_python_curl',
            'courseradownloader': 'coursera_dl',
            'cow': 'cow_framework',
            'creole': 'python_creole',
            'creoleparser': 'Creoleparser',
            'crispy_forms': 'django_crispy_forms',
            'cronlog': 'python_crontab',
            'crontab': 'python_crontab',
            'ctff': 'tff',
            'cups': 'pycups',
            'curator': 'elasticsearch_curator',
            'curl': 'pycurl',
            'daemon': 'python_daemon',
            'dare': 'DARE',
            'dateutil': 'python_dateutil',
            'dawg': 'DAWG',
            'deb822': 'python_debian',
            'debian': 'python_debian',
            'decouple': 'python-decouple',
            'demo': 'webunit',
            'demosongs': 'PySynth',
            'deployer': 'juju_deployer',
            'depot': 'filedepot',
            'devtools': 'tg.devtools',
            'dgis': '2gis',
            'dhtmlparser': 'pyDHTMLParser',
            'digitalocean': 'python_digitalocean',
            'discord': 'discord.py',
            'distribute_setup': 'ez_setup',
            'distutils2': 'Distutils2',
            'django': 'Django',
            'django_hstore': 'amitu_hstore',
            'djangobower': 'django_bower',
            'djcelery': 'django_celery',
            'djkombu': 'django_kombu',
            'djorm_pgarray': 'djorm_ext_pgarray',
            'dns': 'dnspython',
            'docgen': 'ansible_docgenerator',
            'docker': 'docker_py',
            'dogpile': 'dogpile.cache',
            'dogpile': 'dogpile.core',
            'dogshell': 'dogapi',
            'dot_parser': 'pydot',
            'dot_parser': 'pydot2',
            'dot_parser': 'pydot3k',
            'dotenv': 'python-dotenv',
            'dpkt': 'dpkt_fix',
            'dsml': 'python_ldap',
            'durationfield': 'django_durationfield',
            'dzclient': 'datazilla',
            'easybuild': 'easybuild_framework',
            'editor': 'python_editor',
            'elasticluster': 'azure_elasticluster',
            'elasticluster': 'azure_elasticluster_current',
            'elftools': 'pyelftools',
            'elixir': 'Elixir',
            'em': 'empy',
            'emlib': 'empy',
            'enchant': 'pyenchant',
            'encutils': 'cssutils',
            'engineio': 'python_engineio',
            'enum': 'enum34',
            'ephem': 'pyephem',
            'errorreporter': 'abl.errorreporter',
            'esplot': 'beaker_es_plot',
            'example': 'adrest',
            'examples': 'tweepy',
            'ez_setup': 'pycassa',
            'fabfile': 'Fabric',
            'fabric': 'Fabric',
            'faker': 'Faker',
            'fdpexpect': 'pexpect',
            'fedora': 'python_fedora',
            'fias': 'ailove_django_fias',
            'fiftyone_degrees': '51degrees_mobile_detector',
            'five': 'five.customerize',
            'five': 'five.globalrequest',
            'five': 'five.intid',
            'five': 'five.localsitemanager',
            'five': 'five.pt',
            'flasher': 'android_flasher',
            'flask': 'Flask',
            'flask_frozen': 'Frozen_Flask',
            'flask_redis': 'Flask_And_Redis',
            'flaskext': 'Flask_Bcrypt',
            'flvscreen': 'vnc2flv',
            'followit': 'django_followit',
            'forge': 'pyforge',
            'formencode': 'FormEncode',
            'formtools': 'django_formtools',
            'fourch': '4ch',
            'franz': 'allegrordf',
            'freetype': 'freetype_py',
            'frontmatter': 'python_frontmatter',
            'ftpcloudfs': 'ftp_cloudfs',
            'funtests': 'librabbitmq',
            'fuse': 'fusepy',
            'fuzzy': 'Fuzzy',
            'gabbi': 'tiddlyweb',
            'gen_3dwallet': '3d_wallet_generator',
            'gendimen': 'android_gendimen',
            'genshi': 'Genshi',
            'geohash': 'python_geohash',
            'geonode': 'GeoNode',
            'geoserver': 'gsconfig',
            'geraldo': 'Geraldo',
            'getenv': 'django_getenv',
            'geventwebsocket': 'gevent_websocket',
            'gflags': 'python_gflags',
            'git': 'GitPython',
            'github': 'PyGithub',
            'github3': 'github3.py',
            'gitpy': 'git_py',
            'globusonline': 'globusonline_transfer_api_client',
            'google': 'protobuf',
            'googleapiclient': 'google_api_python_client',
            'grace-dizmo': 'grace_dizmo',
            'grammar': 'anovelmous_grammar',
            'grapheneapi': 'graphenelib',
            'greplin': 'scales',
            'gridfs': 'pymongo',
            'grokcore': 'grokcore.component',
            'gslib': 'gsutil',
            'hamcrest': 'PyHamcrest',
            'harpy': 'HARPy',
            'hawk': 'PyHawk_with_a_single_extra_commit',
            'haystack': 'django_haystack',
            'hgext': 'mercurial',
            'hggit': 'hg_git',
            'hglib': 'python_hglib',
            'ho': 'pisa',
            'hola': 'amarokHola',
            'hoover': 'Hoover',
            'hostlist': 'python_hostlist',
            'html': 'pies2overrides',
            'htmloutput': 'nosehtmloutput',
            'http': 'pies2overrides',
            'hvad': 'django_hvad',
            'hydra': 'hydra-core',
            'i99fix': '199Fix',
            'igraph': 'python_igraph',
            'imdb': 'IMDbPY',
            'impala': 'impyla',
            'inmemorystorage': 'ambition_inmemorystorage',
            'ipaddress': 'backport_ipaddress',
            'jaraco': 'jaraco.timing',
            'jaraco': 'jaraco.util',
            'jinja2': 'Jinja2',
            'jiracli': 'jira_cli',
            'johnny': 'johnny_cache',
            'jpgrid': 'python_geohash',
            'jpiarea': 'python_geohash',
            'jpype': 'JPype1',
            'jpypex': 'JPype1',
            'jsonfield': 'django_jsonfield',
            'jstools': 'aino_jstools',
            'jupyterpip': 'jupyter_pip',
            'jwt': 'PyJWT',
            'kazoo': 'asana_kazoo',
            'kernprof': 'line_profiler',
            'keyczar': 'python_keyczar',
            'keyedcache': 'django_keyedcache',
            'keystoneclient': 'python_keystoneclient',
            'kickstarter': 'kickstart',
            'krbv': 'krbV',
            'kss': 'kss.core',
            'kuyruk': 'Kuyruk',
            'langconv': 'AdvancedLangConv',
            'lava': 'lava_utils_interface',
            'lazr': 'lazr.authentication',
            'lazr': 'lazr.restfulclient',
            'lazr': 'lazr.uri',
            'ldap': 'python_ldap',
            'ldaplib': 'adpasswd',
            'ldapurl': 'python_ldap',
            'ldif': 'python_ldap',
            'lib2or3': '2or3',
            'lib3to2': '3to2',
            'libaito': 'Aito',
            'libbe': 'bugs_everywhere',
            'libbucket': 'bucket',
            'libcloud': 'apache_libcloud',
            'libfuturize': 'future',
            'libgenerateDS': 'generateDS',
            'libmproxy': 'mitmproxy',
            'libpasteurize': 'future',
            'libsvm': '7lk_ocr_deploy',
            'lisa': 'lisa_server',
            'loadingandsaving': 'aspose_words_java_for_python',
            'locust': 'locustio',
            'logbook': 'Logbook',
            'logentries': 'buildbot_status_logentries',
            'logilab': 'logilab_mtconverter',
            'machineconsole': 'cerebrod',
            'machinesitter': 'cerebrod',
            'magic': 'python_magic',
            'mako': 'Mako',
            'manifestparser': 'ManifestDestiny',
            'marionette': 'marionette_client',
            'markdown': 'Markdown',
            'marks': 'pytest_marks',
            'markupsafe': 'MarkupSafe',
            'mavnative': 'pymavlink',
            'memcache': 'python_memcached',
            'metacomm': 'AllPairs',
            'metaphone': 'Metafone',
            'metlog': 'metlog_py',
            'mezzanine': 'Mezzanine',
            'migrate': 'sqlalchemy_migrate',
            'mimeparse': 'python_mimeparse',
            'minitage': 'minitage.paste',
            'minitage': 'minitage.recipe.common',
            'missingdrawables': 'android_missingdrawables',
            'mixfiles': 'PySynth',
            'mkfreq': 'PySynth',
            'mkrst_themes': '2lazy2rest',
            'mockredis': 'mockredispy',
            'modargs': 'python_modargs',
            'model_utils': 'django_model_utils',
            'models': 'asposebarcode',
            'models': 'asposestorage',
            'moksha': 'moksha.common',
            'moksha': 'moksha.hub',
            'moksha': 'moksha.wsgi',
            'moneyed': 'py_moneyed',
            'mongoalchemy': 'MongoAlchemy',
            'monthdelta': 'MonthDelta',
            'mopidy': 'Mopidy',
            'mopytools': 'MoPyTools',
            'mptt': 'django_mptt',
            'mpv': 'python-mpv',
            'mrbob': 'mr.bob',
            'msgpack': 'msgpack_python',
            'mutations': 'aino_mutations',
            'mws': 'amazon_mws',
            'mysql': 'mysql_connector_repackaged',
            'native_tags': 'django_native_tags',
            'ndg': 'ndg_httpsclient',
            'nereid': 'trytond_nereid',
            'nested': 'baojinhuan',
            'nester': 'Amauri',
            'nester': 'abofly',
            'nester': 'bssm_pythonSig',
            'novaclient': 'python_novaclient',
            'oauth2_provider': 'alauda_django_oauth',
            'oauth2client': 'oauth2client',
            'odf': 'odfpy',
            'ometa': 'Parsley',
            'openid': 'python_openid',
            'opensearchsdk': 'ali_opensearch',
            'oslo_i18n': 'oslo.i18n',
            'oslo_serialization': 'oslo.serialization',
            'oslo_utils': 'oslo.utils',
            'oss': 'alioss',
            'oss': 'aliyun_python_sdk_oss',
            'oss': 'aliyunoss',
            'output': 'cashew',
            'owslib': 'OWSLib',
            'packetdiag': 'nwdiag',
            'paho': 'paho_mqtt',
            'paintstore': 'django_paintstore',
            'parler': 'django_parler',
            'past': 'future',
            'paste': 'PasteScript',
            'path': 'forked_path',
            'path': 'path.py',
            'patricia': 'patricia-trie',
            'paver': 'Paver',
            'peak': 'ProxyTypes',
            'picasso': 'anderson.picasso',
            'picklefield': 'django-picklefield',
            'pilot': 'BigJob',
            'pivotal': 'pivotal_py',
            'play_wav': 'PySynth',
            'playhouse': 'peewee',
            'plivoxml': 'plivo',
            'plone': 'plone.alterego',
            'plone': 'plone.api',
            'plone': 'plone.app.blob',
            'plone': 'plone.app.collection',
            'plone': 'plone.app.content',
            'plone': 'plone.app.contentlisting',
            'plone': 'plone.app.contentmenu',
            'plone': 'plone.app.contentrules',
            'plone': 'plone.app.contenttypes',
            'plone': 'plone.app.controlpanel',
            'plone': 'plone.app.customerize',
            'plone': 'plone.app.dexterity',
            'plone': 'plone.app.discussion',
            'plone': 'plone.app.event',
            'plone': 'plone.app.folder',
            'plone': 'plone.app.i18n',
            'plone': 'plone.app.imaging',
            'plone': 'plone.app.intid',
            'plone': 'plone.app.layout',
            'plone': 'plone.app.linkintegrity',
            'plone': 'plone.app.locales',
            'plone': 'plone.app.lockingbehavior',
            'plone': 'plone.app.multilingual',
            'plone': 'plone.app.portlets',
            'plone': 'plone.app.querystring',
            'plone': 'plone.app.redirector',
            'plone': 'plone.app.registry',
            'plone': 'plone.app.relationfield',
            'plone': 'plone.app.textfield',
            'plone': 'plone.app.theming',
            'plone': 'plone.app.users',
            'plone': 'plone.app.uuid',
            'plone': 'plone.app.versioningbehavior',
            'plone': 'plone.app.viewletmanager',
            'plone': 'plone.app.vocabularies',
            'plone': 'plone.app.widgets',
            'plone': 'plone.app.workflow',
            'plone': 'plone.app.z3cform',
            'plone': 'plone.autoform',
            'plone': 'plone.batching',
            'plone': 'plone.behavior',
            'plone': 'plone.browserlayer',
            'plone': 'plone.caching',
            'plone': 'plone.contentrules',
            'plone': 'plone.dexterity',
            'plone': 'plone.event',
            'plone': 'plone.folder',
            'plone': 'plone.formwidget.namedfile',
            'plone': 'plone.formwidget.recurrence',
            'plone': 'plone.i18n',
            'plone': 'plone.indexer',
            'plone': 'plone.intelligenttext',
            'plone': 'plone.keyring',
            'plone': 'plone.locking',
            'plone': 'plone.memoize',
            'plone': 'plone.namedfile',
            'plone': 'plone.outputfilters',
            'plone': 'plone.portlet.collection',
            'plone': 'plone.portlet.static',
            'plone': 'plone.portlets',
            'plone': 'plone.protect',
            'plone': 'plone.recipe.zope2install',
            'plone': 'plone.registry',
            'plone': 'plone.resource',
            'plone': 'plone.resourceeditor',
            'plone': 'plone.rfc822',
            'plone': 'plone.scale',
            'plone': 'plone.schema',
            'plone': 'plone.schemaeditor',
            'plone': 'plone.session',
            'plone': 'plone.stringinterp',
            'plone': 'plone.subrequest',
            'plone': 'plone.supermodel',
            'plone': 'plone.synchronize',
            'plone': 'plone.theme',
            'plone': 'plone.transformchain',
            'plone': 'plone.uuid',
            'plone': 'plone.z3cform',
            'plonetheme': 'plonetheme.barceloneta',
            'png': 'pypng',
            'polymorphic': 'django_polymorphic',
            'postmark': 'python_postmark',
            'powerprompt': 'bash_powerprompt',
            'prefetch': 'django-prefetch',
            'printList': 'AndrewList',
            'progressbar': 'progressbar2',
            'progressbar': 'progressbar33',
            'provider': 'django_oauth2_provider',
            'puresasl': 'pure_sasl',
            'pwiz': 'peewee',
            'pxssh': 'pexpect',
            'py7zlib': 'pylzma',
            'pyAMI': 'pyAMI_core',
            'pyarsespyder': 'arsespyder',
            'pyasdf': 'asdf',
            'pyaspell': 'aspell_python_ctypes',
            'pybb': 'pybbm',
            'pybloomfilter': 'pybloomfiltermmap',
            'pyccuracy': 'Pyccuracy',
            'pyck': 'PyCK',
            'pycrfsuite': 'python_crfsuite',
            'pydispatch': 'PyDispatcher',
            'pygeolib': 'pygeocoder',
            'pygments': 'Pygments',
            'pygraph': 'python_graph_core',
            'pyjon': 'pyjon.utils',
            'pyjsonrpc': 'python_jsonrpc',
            'pykka': 'Pykka',
            'pylogo': 'PyLogo',
            'pylons': 'adhocracy_Pylons',
            'pymagic': 'libmagic',
            'pymycraawler': 'Amalwebcrawler',
            'pynma': 'AbakaffeNotifier',
            'pyphen': 'Pyphen',
            'pyrimaa': 'AEI',
            'pysideuic': 'PySide',
            'pysqlite2': 'adhocracy_pysqlite',
            'pysqlite2': 'pysqlite',
            'pysynth_b': 'PySynth',
            'pysynth_beeper': 'PySynth',
            'pysynth_c': 'PySynth',
            'pysynth_d': 'PySynth',
            'pysynth_e': 'PySynth',
            'pysynth_p': 'PySynth',
            'pysynth_s': 'PySynth',
            'pysynth_samp': 'PySynth',
            'pythongettext': 'python_gettext',
            'pythonjsonlogger': 'python_json_logger',
            'pyutilib': 'PyUtilib',
            'pyximport': 'Cython',
            'qs': 'qserve',
            'quadtree': 'python_geohash',
            'queue': 'future',
            'quickapi': 'django_quickapi',
            'quickunit': 'nose_quickunit',
            'rackdiag': 'nwdiag',
            'radical': 'radical.pilot',
            'radical': 'radical.utils',
            'reStructuredText': 'Zope2',
            'readability': 'readability_lxml',
            'readline': 'gnureadline',
            'recaptcha_works': 'django_recaptcha_works',
            'relstorage': 'RelStorage',
            'reportapi': 'django_reportapi',
            'reprlib': 'pies2overrides',
            #'requests': 'Requests', # This doesn't work on my Ubuntu machine.
            'requirements': 'requirements_parser',
            'rest_framework': 'djangorestframework',
            'restclient': 'py_restclient',
            'retrial': 'async_retrial',
            'reversion': 'django_reversion',
            'rhaptos2': 'rhaptos2.common',
            'robot': 'robotframework',
            'robots': 'django_robots',
            'rosdep2': 'rosdep',
            'rsbackends': 'RSFile',
            'ruamel': 'ruamel.base',
            's2repoze': 'pysaml2',
            'saga': 'saga_python',
            'saml2': 'pysaml2',
            'samtranslator': 'aws-sam-translator',
            'sass': 'libsass',
            'sassc': 'libsass',
            'sasstests': 'libsass',
            'sassutils': 'libsass',
            'sayhi': 'alex_sayhi',
            'scalrtools': 'scalr',
            'scikits': 'scikits.talkbox',
            'scratch': 'scratchpy',
            'screen': 'pexpect',
            'scss': 'pyScss',
            'sdict': 'dict.sorted',
            'sdk_updater': 'android_sdk_updater',
            'sekizai': 'django_sekizai',
            'sendfile': 'pysendfile',
            'serial': 'pyserial',
            'setuputils': 'astor',
            'shapefile': 'pyshp',
            'shapely': 'Shapely',
            'sika': 'ahonya_sika',
            'singleton': 'pysingleton',
            'sittercommon': 'cerebrod',
            'skbio': 'scikit_bio',
            'sklearn': 'scikit_learn',
            'slack': 'slackclient',
            'slugify': 'unicode_slugify',
            'slugify': 'python-slugify',
            'smarkets': 'smk_python_sdk',
            'snappy': 'ctypes_snappy',
            'socketio': 'python-socketio',
            'socketserver': 'pies2overrides',
            'sockjs': 'sockjs_tornado',
            'socks': 'SocksiPy_branch',
            'solr': 'solrpy',
            'solution': 'Solution',
            'sorl': 'sorl_thumbnail',
            'south': 'South',
            'sphinx': 'Sphinx',
            'sphinx_pypi_upload': 'ATD_document',
            'sphinxcontrib': 'sphinxcontrib_programoutput',
            'sqlalchemy': 'SQLAlchemy',
            'src': 'atlas',
            'src': 'auto_mix_prep',
            'stats_toolkit': 'bw_stats_toolkit',
            'statsd': 'dogstatsd_python',
            'stdnum': 'python_stdnum',
            'stoneagehtml': 'StoneageHTML',
            'storages': 'django_storages',
            'stubout': 'mox',
            'suds': 'suds_jurko',
            'swiftclient': 'python_swiftclient',
            'sx': 'pisa',
            'tabix': 'pytabix',
            'taggit': 'django_taggit',
            'tasksitter': 'cerebrod',
            'tastypie': 'django_tastypie',
            'teamcity': 'teamcity_messages',
            'telebot': 'pyTelegramBotAPI',
            'telegram': 'python-telegram-bot',
            'tempita': 'Tempita',
            'tenjin': 'Tenjin',
            'termstyle': 'python_termstyle',
            'test': 'pytabix',
            'thclient': 'treeherder_client',
            'threaded_multihost': 'django_threaded_multihost',
            'threecolor': '3color_Press',
            'tidylib': 'pytidylib',
            'tkinter': 'future',
            'tlw': '3lwg',
            'toredis': 'toredis_fork',
            'tornadoredis': 'tornado_redis',
            'tower_cli': 'ansible_tower_cli',
            'trac': 'Trac',
            'tracopt': 'Trac',
            'translation_helper': 'android_localization_helper',
            'treebeard': 'django_treebeard',
            'trytond': 'trytond_stock',
            'tsuru': 'tsuru_circus',
            'tvrage': 'python_tvrage',
            'tw2': 'tw2.core',
            'tw2': 'tw2.d3',
            'tw2': 'tw2.dynforms',
            'tw2': 'tw2.excanvas',
            'tw2': 'tw2.forms',
            'tw2': 'tw2.jit',
            'tw2': 'tw2.jqplugins.flot',
            'tw2': 'tw2.jqplugins.gritter',
            'tw2': 'tw2.jqplugins.ui',
            'tw2': 'tw2.jquery',
            'tw2': 'tw2.sqla',
            'twisted': 'Twisted',
            'twitter': 'python_twitter',
            'txclib': 'transifex_client',
            'u115': '115wangpan',
            #'unidecode': 'Unidecode', # This doesn't work on my Ubuntu machine.
            'universe': 'ansible_universe',
            'usb': 'pyusb',
            'useless': 'useless.pipes',
            'userpass': 'auth_userpass',
            'utilities': 'automakesetup.py',
            'utkik': 'aino_utkik',
            'uwsgidecorators': 'uWSGI',
            'valentine': 'ab',
            'validate': 'configobj',
            'version': 'chartio',
            'virtualenvapi': 'ar_virtualenv_api',
            'vyatta': 'brocade_plugins',
            'webdav': 'Zope2',
            'weblogolib': 'weblogo',
            'webob': 'WebOb',
            'websocket': 'websocket_client',
            'webtest': 'WebTest',
            'werkzeug': 'Werkzeug',
            'wheezy': 'wheezy.caching',
            'wheezy': 'wheezy.core',
            'wheezy': 'wheezy.http',
            'wikklytext': 'tiddlywebwiki',
            'winreg': 'future',
            'winrm': 'pywinrm',
            'workflow': 'Alfred_Workflow',
            'wsmeext': 'WSME',
            'wtforms': 'WTForms',
            'wtfpeewee': 'wtf_peewee',
            'xdg': 'pyxdg',
            'xdist': 'pytest_xdist',
            'xmldsig': 'pysaml2',
            'xmlenc': 'pysaml2',
            'xmlrpc': 'pies2overrides',
            'xmpp': 'xmpppy',
            'xstatic': 'XStatic_Font_Awesome',
            'xstatic': 'XStatic_jQuery',
            'xstatic': 'XStatic_jquery_ui',
            'yaml': 'PyYAML',
            'z3c': 'z3c.autoinclude',
            'z3c': 'z3c.caching',
            'z3c': 'z3c.form',
            'z3c': 'z3c.formwidget.query',
            'z3c': 'z3c.objpath',
            'z3c': 'z3c.pt',
            'z3c': 'z3c.relationfield',
            'z3c': 'z3c.traverser',
            'z3c': 'z3c.zcmlhook',
            'zmq': 'pyzmq',
            'zopyx': 'zopyx.textindexng3'}
        self.reversed_module_aliases = {v: k for k, v in self.module_aliases.items()}
        # Set of known bad imports that should be ignored.
        self.known_bad_imports: Set[str] = {'__builtin__', 'snakeClass', 'GPUampcor', 'pathfinding_salvo_rework', 'seaborn', 'DQN', 'bayesOpt', 'tkinter', 'msvcrt', 'BaseHTTPServer', 'urlparse', 'tkFileDialog', 'tkMessageBox', 'ConfigParser', 'Cookie', 'HTMLParser', 'Queue', 'SocketServer', 'StringIO', 'Tkinter', 'UserDict', 'cPickle', 'cStringIO', 'cookielib', 'htmlentitydefs', 'httplib', 'tkFont', 'tkMessageBox', 'urllib2', 'non_existent_module'} # 'BaseHTTPServer', 'urlparse', 'tkFileDialog', 'tkMessageBox', 'ConfigParser', 'Cookie', 'HTMLParser', 'Queue', 'SocketServer', 'StringIO', 'Tkinter', 'UserDict', 'cPickle', 'cStringIO', 'cookielib', 'htmlentitydefs', 'httplib', 'tkFont', 'tkMessageBox', 'urllib2' are Python 2 modules - we don't want to try to install them. A more general approach would involve importing stdlib_list and using that to filter out stdlib modules from Python 2 and Python 3: https://pypi.org/project/stdlib-list/
        # https://chatgpt.com/share/687000fd-be84-8006-a7f4-06af4b1e0eda
        # List of unusual imports that are not standard library modules or packages.
        self.unusual_imports: List[str] = ['a', 'an', 'dl', 'the', 'it', 'x', 'xx', 'above', 'another', '__builtin__', 'within']
        # List of directories to stay out of when searching for local custom imports because they're filled with standard library modules or other irrelevant files.
        self.stay_out_list: List[str] = ['myenv', 'anaconda3', '.conda',os.sep+'lib'+os.sep, '.vscode']

    def set_venv_dir(self, venv_dir: str) -> None:
        """Set the directory for the virtual environment."""
        self.venv_dir = os.path.expanduser(venv_dir)
        self.activate_script   = 'source ' + os.path.join(self.venv_dir, 'bin', 'activate')
        self.venv_python          = os.path.join(self.venv_dir, 'bin', 'python')
        self.venv_pip             = os.path.join(self.venv_dir, 'bin', 'pip')
        self.requirements_file    = os.path.join(self.venv_dir, "requirements.txt")
        self.download_script_path = os.path.join(self.venv_dir, "download_packages.sh")

def parse_arguments(options: Options) -> None:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description="Run a python script with optional flags.")    
    parser.add_argument('-version',     action='store_true', help='Print the version of this program.')
    parser.add_argument('-manual',      action='store_true', help='Print instructions for manually adding the alias to the shell configuration file.')
    parser.add_argument('-debug',       action='store_true', help='Run this program in debug mode, which prints additional debug messages.')
    parser.add_argument('-blank-slate', action='store_true', help=f"Delete ~/{options.my_name}/ and all {options.my_name} .out and .err and .json and .pkl files in the current directory.")
    parser.add_argument('-full',        action='store_true', help="Build a virtual environment (venv) that can run every python script in the specified directory (defaults to the current working directory).")
    parser.add_argument('-y',           action='store_true', help='Automatically say yes to any prompts.')
    parser.add_argument('-no-cache',    action='store_true', help="Don't search the cache. Instead, create a new virtual environment. Also, refresh the custom modules cache and the pip list.")
    parser.add_argument('-latest',      action='store_true', help="Load the latest venv in the cache which has all the packages needed now.")
    parser.add_argument('-oldest',      action='store_true', help="Load the oldest venv in the cache which has all the packages needed now.")
    parser.add_argument('-last-used',   action='store_true', help="Load the last used venv in the cache, but if that fails try the latest venv which has all the packages needed now.")
    parser.add_argument('-smallest',    action='store_true', help="Load the smallest venv in the cache (with the fewest packages) which has all the packages needed now.")
    parser.add_argument('-rc',          action='store_true', help='Refresh the custom modules cache and the pip list.')
    parser.add_argument('-reqs',        action='store_true', help='Read the extra_requirements.txt file in the current directory and install the packages listed there (with specific versions if present in the file) into the venv (along with the other packages needed to run the script as determined elsewhere in this program).')
    parser.add_argument('-alias',       type=str,            help='Add an alias to the shell configuration file so that typing ALIAS anywhere runs this program.')
    parser.add_argument('-rawlog',      action='store_true', help=f'Do not add timestamps or INFO level to log messages, and do not add extra INFO level log statements. Just produce the same output that would be seen when running the program without {options.my_name}.')
    parser.add_argument('-justprint',   action='store_true', help="Don't run the script, just print its package requirements.")
    parser.add_argument('script',      nargs='?',                help="The script to run.")
    parser.add_argument('script_args', nargs=argparse.REMAINDER, help="Optional arguments for the python script.")

    # If no arguments are provided, print a short guide
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)
    
    # Parse known args, and then manually add the script_args
    args = parser.parse_args()
    options.args = args

def detect_shell() -> str:
    """Detect the current shell."""
    shell = os.getenv("SHELL")
    if shell:
        return os.path.basename(shell)
    return None

def get_shell_rc_file(options: Options) -> str:
    """Get the shell configuration file for the current user."""
    home = os.path.expanduser("~")
    if options.shell == "bash":
        return os.path.join(home, ".bashrc")
    elif options.shell == "zsh":
        return os.path.join(home, ".zshrc")
    elif options.shell == "fish":
        return os.path.join(home, ".config", "fish", "config.fish")
    elif options.shell == "csh":
        return os.path.join(home, ".cshrc")
    elif options.shell == "tcsh":
        return os.path.join(home, ".tcshrc")
    return None

def get_alias_command(options: Options) -> str:
    """Get the alias command for the shell."""
    if options.shell in ["bash", "zsh"]:
        return f'alias {options.args.alias}="{options.python_command} {options.my_filepath}"'
    elif options.shell == "fish":
        return f'alias {options.args.alias} "{options.python_command} {options.my_filepath}"'
    elif options.shell in ["csh", "tcsh"]:
        return f"alias {options.args.alias} '{options.python_command} {options.my_filepath}'"
    return None

def alias_exists(rc_file: str, alias_pattern: str) -> bool:
    """Check if an alias exists in a file using a pattern."""
    try:
        with open(rc_file, "r") as file:
            lines = file.readlines()
        return any(re.search(alias_pattern, line) for line in lines)
    except FileNotFoundError:
        return False

def get_additional_alias_files(options: Options) -> List[str]:
    """Get additional alias files for the shell."""
    home = os.path.expanduser("~")
    if options.shell == "bash":
        return [os.path.join(home, ".bash_aliases")]
    elif options.shell == "zsh":
        return [os.path.join(home, ".zsh_aliases")]
    # Add other shells if they have alias files
    return []

def add_alias_to_rc(options: Options, rc_file: str, alias_command: str, additional_files: List[str] = []) -> None:
    """Add an alias to the shell configuration file."""
    try:
        all_files = [rc_file] + additional_files
        alias_pattern = rf"alias\s+{options.args.alias}\s*=.*"
        found_alias = False
        for file in all_files:
            if alias_exists(file, alias_pattern):
                found_alias = True
                logging.info(f"Alias {options.args.alias} already exists in {file}")
        if not found_alias:
            try:
                if ud.get_user_input(f"Type 'yes' or 'y' to write this alias command:\n{alias_command}\nTo this file:\n{rc_file}\n... or type anything else to quit: "):
                    with open(rc_file, "a") as file:
                        file.write(f"\n{alias_command}\n")
                    logging.info(f"Alias added to {rc_file}")
            except (IOError, OSError) as e:
                logging.error(f"Failed to write alias to {rc_file}: {e}\nException type: ", exc_info=True)
                logging.error(options.manual_instructions)
    except Exception as e:
        logging.error(f"An error occurred while adding the alias: {e}\nException type: ", exc_info=True)
        logging.error(options.manual_instructions)

def add_alias(options: Options) -> None:
    """Add an alias to the shell configuration file."""
    options.shell = detect_shell()
    if options.shell:
        rc_file = get_shell_rc_file(options)
        additional_files = get_additional_alias_files(options)
        if rc_file:
            alias_command = get_alias_command(options)
            if alias_command:
                add_alias_to_rc(options, rc_file, alias_command, additional_files)
            else:
                logging.info(f"Unsupported shell: {options.shell}")
        else:
            logging.info(f"Unsupported shell configuration file for shell: {options.shell}")
    else:
        logging.info("Could not detect shell")

def _safe_eval_node(node: ast.AST) -> Any:
    """
    Recursively evaluate a restricted subset of AST nodes:
    - Constants (strings, numbers, booleans, None)
    - Lists, tuples, dicts
    - os.path.abspath(<string>)
    """
    if isinstance(node, ast.Constant):
        # Python 3.8+: Constant covers str, int, float, bool, None
        return node.value

    if isinstance(node, ast.List):
        return [_safe_eval_node(elt) for elt in node.elts]

    if isinstance(node, ast.Tuple):
        return tuple(_safe_eval_node(elt) for elt in node.elts)

    if isinstance(node, ast.Dict):
        return {
            _safe_eval_node(k): _safe_eval_node(v)
            for k, v in zip(node.keys, node.values)
        }

    if isinstance(node, ast.Call):
        # Check for os.path.abspath
        func = node.func
        # attr.value.value.id == 'os' && attr.value.attr == 'path' && attr.attr == 'abspath'
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "abspath"
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "path"
            and isinstance(func.value.value, ast.Name)
            and func.value.value.id == "os"
        ):
            # exactly one argument?
            if len(node.args) == 1:
                arg_val = _safe_eval_node(node.args[0])
                if isinstance(arg_val, str):
                    return os.path.abspath(arg_val)
        # If it's not exactly os.path.abspath(str), fall through:
        raise ValueError(f"Unsupported call: {ast.unparse(node)}")

    # anything else is disallowed
    raise ValueError(f"Unsupported expression: {ast.dump(node)}")

def safe_eval(expr: str) -> Any | None:
    """
    Safely evaluate a Python expression string containing only:
      - literals (str, int, float, bool, None)
      - lists, tuples, dicts of the above
      - os.path.abspath(<literal string>)
    Returns the evaluated Python object, or None on unsupported syntax.
    """
    try:
        # Parse in 'eval' mode so we get an Expression node
        tree = ast.parse(expr, mode="eval")
        return _safe_eval_node(tree.body)  # tree.body is the root expr
    except (SyntaxError, ValueError) as e:
        logging.debug(f"safe_eval: Unsupported expression: {expr!r}: {e}")
        return None

class SysPathVisitor(ast.NodeVisitor):
    """Visitor class to extract sys.path modifications."""
    def __init__(self) -> None:
        """Initialize the sys.path visitor."""
        self.paths = set()

    def visit_Assign(self, node: ast.Assign) -> None:
        """Visit an assignment statement and check if it's modifying sys.path."""
        if isinstance(node.targets[0], ast.Attribute) and \
           isinstance(node.targets[0].value, ast.Name) and \
           node.targets[0].value.id == 'sys' and \
           node.targets[0].attr == 'path':
            paths = safe_eval(ast.unparse(node.value))
            if isinstance(paths, list):
                for path in paths:
                    self.paths.add(path)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Visit a function call and check if it's modifying sys.path."""
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

def process_import(options: Options, module_name: str, file_path: str) -> bool:
    """Process an import by checking if it's a local custom module or a standard import, and handle it accordingly."""
    if module_name in options.standard_modules:
        logging.debug(f"Skipping standard library import: {module_name}")
        return False

    logging.debug(f"Processing import: {module_name} from file {file_path}")

    base_dir = os.path.dirname(os.path.abspath(file_path))
    module_path = module_name.replace('.', os.sep)

    # Avoid loopback to the same file
    script_name = os.path.splitext(os.path.basename(file_path))[0]
    if module_name == script_name:
        logging.debug(f"Avoiding loopback to the same file: {module_name}")
        return False
    if module_name == 'pipreqs' and f'{options.my_name}.py' in file_path:
        logging.debug(f"Avoiding loopback to pipreqs in {options.my_name}.py")
        return False
    logging.debug(f"Constructed module path: {module_path}")

    # Check if the import is a .py file in the same directory
    potential_file_path = os.path.abspath(os.path.join(base_dir, module_path + '.py'))
    if os.path.isfile(potential_file_path) and potential_file_path not in options.samedir_files:
        options.custom_modules[module_name] = potential_file_path
        options.loaded_custom_modules.add(module_name)
        options.samedir_files.append(potential_file_path)
        logging.debug(f"Added same directory file: {potential_file_path}")
        return True
    
    # Check if the import is a package (directory with __init__.py)
    potential_dir_path = os.path.abspath(os.path.join(base_dir, module_path))
    logging.debug(f"Constructed potential directory path: {potential_dir_path}")
    if os.path.isdir(potential_dir_path) and os.path.isfile(os.path.join(potential_dir_path, '__init__.py')) and module_path not in options.subfolders:
        options.custom_modules[module_name] = potential_dir_path
        options.loaded_custom_modules.add(module_name)
        logging.debug(f"Resolved local package to: {potential_dir_path}")
        options.subfolders.append(module_path)
        logging.debug(f"Added subfolder: {module_path}")
        return True
    
    logging.debug(f"Could not resolve local import, treating as external: {module_name}")
    return False

class FunctionInfo:
    """Class to hold information about a function."""
    def __init__(self, function_name: str) -> None:
        """Initialize the function information."""
        self.function_name                 = function_name
        self.imports_in_function: Set[str] = set()
        self.function_calls:      Set[str] = set()

class ModuleInfo:
    """Class to hold information about a module."""
    def __init__(self, module_name: str) -> None:
        """Initialize the module information."""
        self.module_name                                = module_name
        self.top_level_imports: Set[str]                = set()
        self.functions:         Dict[str, FunctionInfo] = {}
        self.top_level_calls:   Set[str]                = set()
        self.aliases:           Dict[str, str]          = {}
        self.classes:           Set[str]                = set()

class ImportFunctionCollector(ast.NodeVisitor):
    """Visitor class to collect function and import information from a module."""
    def __init__(self, module_name: str, options: Options,
                 file_path: str) -> None:
        """Initialize the import function collector."""
        self.module_info = ModuleInfo(module_name)
        self.current_function = None
        self.current_class    = None
        self.aliases          = {}
        self.options          = options
        self.file_path        = file_path
        self.base_classes     = {}

    def visit_Import(self, node: ast.Import) -> None:
        """Visit an import statement and add the imported module to the module's list of imports."""
        for alias in node.names:
            name = alias.asname or alias.name
            full_name = alias.name
            top_level_package = full_name.split('.')[0]
            self.aliases[name] = full_name
            if self.current_function:
                self.module_info.functions[self.current_function].imports_in_function.add(top_level_package)
            else:
                self.module_info.top_level_imports.add(top_level_package)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Visit an import from statement and add the imported module to the module's list of imports."""
        module = node.module or ''
        # Extract the top-level package
        top_level_package = module.split('.')[0] if module else ''
        for alias in node.names:
            full_name = f"{module}.{alias.name}" if module else alias.name
            name = alias.asname or alias.name
            self.aliases[name] = full_name
            if self.current_function:
                self.module_info.functions[self.current_function].imports_in_function.add(top_level_package)
            else:
                self.module_info.top_level_imports.add(top_level_package)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit a function definition and add it to the module's list of functions."""
        func_name = node.name
        if self.current_class:
            func_name = f"{self.current_class}.{func_name}"
        self.module_info.functions[func_name] = FunctionInfo(func_name)
        logging.debug(f"Added function: {func_name} to module {self.module_info.module_name}")
        prev_function = self.current_function
        self.current_function = func_name
        self.generic_visit(node)
        self.current_function = prev_function

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit a class definition and set the current class."""
        self.module_info.classes.add(node.name)
        prev_class = self.current_class
        self.current_class = node.name

        # Record base classes before visiting the body
        base_class_names = []
        for base in node.bases:
            base_name = self.get_full_name(base)
            if base_name:
                parts = base_name.split('.')
                if parts and parts[0] in self.aliases:
                    alias_target = self.aliases[parts[0]]
                    base_name = alias_target + '.' + '.'.join(parts[1:])
                base_class_names.append(base_name)
        self.base_classes[node.name] = base_class_names
        logging.debug(f"Recorded base classes for {node.name}: {self.base_classes[node.name]}")
        # Now that base_classes is set, visit the class body
        self.generic_visit(node)
        self.current_class = prev_class

    def extract_module_name_from_import(self, node: ast.Call) -> str | None:
        """Extract the module name from a dynamic import using __import__."""
        if node.args:
            module_arg = node.args[0]
            if isinstance(module_arg, ast.Constant) and isinstance(module_arg.value, str):
                module_name = module_arg.value.split('.')[0]  # Get top-level package
                return module_name
            else:
                # Handle cases where module name cannot be resolved
                logging.error(f"Cannot resolve dynamic import with non-constant module name: {ast.unparse(node)}")
                return None
        else:
            logging.error(f"No arguments provided to __import__(): {ast.unparse(node)}")
            return None

    def visit_Call(self, node: ast.Call) -> None:
        """Visit a function call and add it to the function's list of calls."""
        func_name = self.get_full_name(node.func)
        original_func_name = func_name

        if func_name:
            parts = func_name.split('.')
            if parts[0] in self.module_info.classes:
                # It's a class from this module
                if func_name in self.module_info.classes:
                    # func_name is exactly the class name, treat as constructor
                    logging.debug(f"{func_name} is identified as a class. Converting to __init__ call.")
                    func_name = f"{self.module_info.module_name}.{func_name}.__init__"
                else:
                    # It's a method/attribute call on a class from this module
                    logging.debug(f"{func_name} is a method/attribute on a class from the same module. Qualifying with module name.")
                    func_name = f"{self.module_info.module_name}.{func_name}"
            else:
                logging.debug(f"{func_name} is not a class, leaving as-is.")

            # If func_name corresponds to a class in this module, treat it as calling __init__
            if func_name in self.module_info.classes:
                func_name = f"{func_name}.__init__"

            # Handle dynamic imports
            if func_name == '__import__':
                module_name = self.extract_module_name_from_import(node)
                if module_name:
                    if self.current_function:
                        self.module_info.functions[self.current_function].imports_in_function.add(module_name)
                    else:
                        self.module_info.top_level_imports.add(module_name)
                else:
                    logging.warning(f"Cannot resolve dynamic import: {ast.unparse(node)}")
            elif func_name.startswith('super.'):
                # Handle super calls
                _, method_name = func_name.split('.', 1)
                if self.current_class and self.current_class in self.base_classes:
                    base_classes = self.base_classes[self.current_class]
                    if base_classes:
                        base_class = base_classes[0]  # Assuming single inheritance
                        func_name = f"{base_class}.{method_name}"
                # Record super calls
                if self.current_function:
                    self.module_info.functions[self.current_function].function_calls.add(func_name)
                    logging.debug(f"Adding to {self.current_function}.function_calls: {func_name}")
                else:
                    self.module_info.top_level_calls.add(func_name)
                    logging.debug(f"Adding to top_level_calls: {func_name}")
            else:
                # Normal calls
                if self.current_function:
                    self.module_info.functions[self.current_function].function_calls.add(func_name)
                else:
                    self.module_info.top_level_calls.add(func_name)
        self.generic_visit(node)
        logging.debug(f"Call found: original func_name={original_func_name}, resolved func_name={func_name}")
        if self.current_function:
            logging.debug(f"Adding function call {func_name} to {self.current_function}")
        else:
            logging.debug(f"Adding top-level call: {func_name}")

    def get_full_name(self, node: ast.AST) -> str | None:
        """Get the full name of a node, including any aliases."""
        if isinstance(node, ast.Name): # Handle variable names
            if node.id in ('self', 'cls'): # Handle class methods
                if self.current_class:
                    return self.current_class
                else:
                    return node.id
            elif node.id == 'super': # Handle super() calls
                return 'super'
            else:
                return self.aliases.get(node.id, node.id)
        elif isinstance(node, ast.Attribute): # Handle attribute access
            value = self.get_full_name(node.value)
            return f"{value}.{node.attr}" if value else node.attr
        elif isinstance(node, ast.Call): # Handle super() calls
            func_name = self.get_full_name(node.func)
            return func_name
        return None

def split_function_name(called_func: str, default_module: str) -> Tuple[str, str]:
    """Split a fully qualified function name into module and function parts. If there's no dot, the default_module is used as the module."""
    parts = called_func.split('.')
    if len(parts) > 1:
        called_module = parts[0]
        called_name = '.'.join(parts[1:])
    else:
        called_module = default_module
        called_name = called_func
    return called_module, called_name

def build_call_graph(modules_info: Dict[str, ModuleInfo]) -> Dict[str, Set[str]]:
    """Build a call graph from the function calls in the modules."""
    call_graph = {}
    for module_name, module_info in modules_info.items():
        for func_name, func_info in module_info.functions.items():
            full_func_name = f"{module_name}.{func_name}"
            call_graph[full_func_name] = set()
            for called_func in func_info.function_calls:
                called_module, called_name = split_function_name(called_func, module_name)
                # Check if called_name is a class in the module
                if called_module in modules_info and called_name in modules_info[called_module].classes:
                    # Class instantiation, call __init__
                    called_full_name = f"{called_module}.{called_name}.__init__"
                else:
                    called_full_name = f"{called_module}.{called_name}"
                call_graph[full_func_name].add(called_full_name)
    logging.debug("Call graph constructed:")
    for func, calls in call_graph.items():
        logging.debug(f"{func} calls: {calls}")
    return call_graph

def collect_used_imports(start_module: str, start_func: str,
                         call_graph:   Dict[str, Set[str]],
                         modules_info: Dict[str, ModuleInfo],
                         visited: set[str] = None) -> Set[str]:
    """Collect all imports used in a function and its callees."""
    if visited is None:
        visited = set()
    full_func_name = f"{start_module}.{start_func}"
    if full_func_name in visited:
        logging.debug(f"Already visited {full_func_name}, skipping.")
        return set()
    logging.debug(f"Visiting function: {full_func_name}")
    visited.add(full_func_name)
    imports = set()
    module_info = modules_info.get(start_module)
    if module_info:
        func_info = module_info.functions.get(start_func)
        if func_info:
            if func_info.imports_in_function:
                logging.debug(f"Function {full_func_name} imports: {func_info.imports_in_function}")
            else:
                logging.debug(f"No direct imports found in {full_func_name}")
            imports.update(func_info.imports_in_function)
            for called_func in func_info.function_calls:
                called_module, called_name = split_function_name(called_func, start_module)
                logging.debug(f"From {full_func_name}, visiting called function {called_module}.{called_name}")
                imports.update(collect_used_imports(called_module, called_name, call_graph, modules_info, visited))
        else:
            logging.debug(f"No function info found for {full_func_name}")
    else:
        logging.debug(f"No module info found for {start_module}")
    return imports

def find_imports_in_script(options: Options, first_path: str) -> None:
    """Find all imports in the script and its dependencies."""
    # is_python_script() has already been called to verify that the first_path file LOOKS like a Python script.
    # However, it's still necessary to check if the file is a VALID Python script. If not, skip it.
    if not ud.compile_script(first_path):
        logging.error(f"Skipping invalid Python script: {first_path}")
        return
    processed_modules = set()
    modules_info = {}
    modules_to_process = [first_path]
    while modules_to_process:
        module_path = modules_to_process.pop()
        if os.path.isdir(module_path):
            pkg_dir = module_path
            init_py = os.path.join(pkg_dir, "__init__.py")
            if os.path.isfile(init_py):
                # 1) Parse the package __init__.py
                module_path = init_py
                # 2) Also enqueue all other .py modules in that same folder
                for fname in os.listdir(pkg_dir):
                    if is_python_script(fname) and fname != "__init__.py":
                        path = os.path.join(pkg_dir, fname)
                        if path not in modules_to_process and path not in processed_modules:
                            modules_to_process.append(path)
            else:
                logging.error(f"No __init__.py in package directory {pkg_dir}, skipping.")
                continue
        module_name = os.path.splitext(os.path.basename(module_path))[0]
        if module_name in processed_modules:
            continue
        processed_modules.add(module_name)
        file_content = ud.my_fopen(module_path, rawlog=options.rawlog)
        if not file_content:
            logging.error(f"Could not read file: {module_path}")
            continue
        try:
            tree = ud.my_ast_parse(file_content, module_path)
        except:
            breakpoint()
        collector = ImportFunctionCollector(module_name, options, module_path)
        collector.visit(tree)
        module_info = collector.module_info
        modules_info[module_name] = module_info
        # Process only top-level imports to find local modules
        for import_name in module_info.top_level_imports:
            if import_name in options.standard_modules:
                continue  # Skip standard modules
            resolved = process_import(options, import_name, module_path)
            if resolved:
                module_file_path = options.custom_modules.get(import_name)
                if module_file_path and module_file_path not in processed_modules:
                    modules_to_process.append(module_file_path)
            else:
                options.all_imports.add(import_name)
    logging.debug("Modules processed so far:")
    for m_name, m_info in modules_info.items():
        logging.debug(f"Module: {m_name}, Classes: {m_info.classes}, Functions: {list(m_info.functions.keys())}")
    # Now build the call graph
    call_graph = build_call_graph(modules_info)
    # Collect used imports starting from the first module
    used_imports = set()
    visited_funcs = set()
    def collect_imports_from_module(module_name: str) -> None:
        """Recursively collect used imports from a module."""
        module_info = modules_info[module_name]
        used_imports.update(module_info.top_level_imports)
        for func_name in module_info.top_level_calls:
            called_module, called_name = split_function_name(func_name, module_name)
            logging.debug(f"Collecting used imports for module '{called_module}' and func_name '{called_name}'")
            used_imports.update(
                collect_used_imports(
                    called_module, # Use the extracted module name
                    called_name,   # Use the extracted function name
                    call_graph,
                    modules_info,
                    visited_funcs
                )
            )
            logging.debug(f"Used imports collected from '{called_name}' in '{called_module}': {used_imports}")
        logging.debug(f"Used imports after collecting from module {module_name}: {used_imports}")
    collect_imports_from_module(os.path.splitext(os.path.basename(first_path))[0])
    options.all_imports.update(used_imports)
    # Now process used imports and recursively process new local modules
    new_modules_found = True
    while new_modules_found:
        new_modules_found = False
        for import_name in used_imports.copy():
            if import_name in options.standard_modules or import_name in options.all_imports:
                continue  # Skip standard modules and already processed imports
            if import_name in options.custom_modules:
                module_file_path = options.custom_modules[import_name]
                module_name = import_name
                if module_name not in processed_modules:
                    modules_to_process.append(module_file_path)
                    new_modules_found = True
                    processed_modules.add(module_name)
                    # Process the new module
                    file_content = ud.my_fopen(module_file_path, rawlog=options.rawlog)
                    if not file_content:
                        logging.error(f"Could not read file: {module_file_path}")
                        continue
                    tree = ud.my_ast_parse(file_content, module_file_path)
                    collector = ImportFunctionCollector(module_name, options, module_file_path)
                    collector.visit(tree)
                    module_info = collector.module_info
                    modules_info[module_name] = module_info
                    # Process top-level imports to find more local modules
                    for new_import in module_info.top_level_imports:
                        if new_import in options.standard_modules:
                            continue
                        resolved = process_import(options, new_import, module_file_path)
                        if resolved:
                            module_file_path = options.custom_modules.get(new_import)
                            if module_file_path and new_import not in processed_modules:
                                modules_to_process.append(module_file_path)
                    # Rebuild call graph and collect used imports again
                    call_graph = build_call_graph(modules_info)
                    used_imports.clear()
                    visited_funcs.clear()
                    collect_imports_from_module(os.path.splitext(os.path.basename(first_path))[0])
                    options.all_imports.update(used_imports)
            else:
                # If not a local module, add to options.all_imports
                options.all_imports.add(import_name)

def add_dependencies(options: Options) -> None:
    """Add dependencies for uninstalled imports."""
    # Create a copy to iterate over since we'll be modifying the set
    initial_packages = options.uninstalled_imports.copy()
    
    for package in initial_packages:
        if package in options.also_needs:
            dependencies = options.also_needs[package]
            if not options.rawlog:
                logging.info(f"Adding dependencies for {package}: {dependencies}")
            options.uninstalled_imports.update(dependencies)
    
    # Handle nested dependencies by repeating this process until no new dependencies are added.
    added = True
    while added:
        added = False
        current_packages = options.uninstalled_imports.copy()
        for package in current_packages:
            if package in options.also_needs:
                dependencies = options.also_needs[package]
                new_dependencies = set(dependencies) - options.uninstalled_imports
                if new_dependencies:
                    if not options.rawlog:
                        logging.info(f"Adding nested dependencies for {package}: {new_dependencies}")
                    options.uninstalled_imports.update(new_dependencies)
                    added = True

def split_imports(options: Options) -> None:
    """Split imports into installed, uninstalled, and bad imports."""
    options.bad_imports = options.known_bad_imports.intersection(options.all_imports)
    options.bad_imports.update({imp for imp in options.all_imports if imp.startswith('_')})
    if options.bad_imports:
        logging.debug(f"Identified bad imports: {options.bad_imports}")  # New logging
    options.all_imports = options.all_imports - options.bad_imports
    options.installed_imports = set()
    options.uninstalled_imports = set()
    if getattr(options.args, 'reqs', False):
        options.all_imports = options.all_imports.union(options.extra_requirements.keys())
    options.total_imports = len(options.all_imports)
    if not options.total_imports:
        if not options.rawlog: logging.info("No imports found.")
        return

    max_length = max(len(imp) for imp in options.all_imports) # Longest import name length, used for formatting
    max_digits = len(str(len(options.all_imports))) # Maximum number of digits in import count, also used for formatting

    with tempfile.TemporaryDirectory() as venv_dir:
        venv.create(venv_dir, with_pip=True)
        for i, imp in enumerate(options.all_imports, 1):
            package_name = options.module_aliases.get(imp, imp)
            logging.debug(f"Checking if import {imp} is installed or uninstalled")  # New logging
            if imp in options.custom_modules.keys():
                logging.debug(f"Custom module {imp} has path {options.custom_modules[imp]}")
                status_str = "YES - custom module"
            elif check_packages_in_venv(options, package=package_name,
                                        venv_dir=venv_dir):
                logging.debug(f"Module {imp} can be imported in venv")
                status_str = "YES -     installed"
                options.installed_imports.add(imp)
            else:
                logging.debug(f"Import {imp} is not installed and not a custom module")  # New logging
                status_str = "NO  - NOT installed"
                options.uninstalled_imports.add(package_name)
            if not options.rawlog: logging.info(f"Checking import {imp:{max_length}} : {i:>{max_digits}}/{options.total_imports} - {status_str}")
    if getattr(options.args, 'reqs', False):
        options.uninstalled_imports = options.uninstalled_imports.union(options.extra_requirements.keys())
    add_dependencies(options)
    return

def is_python_script(path: str) -> bool:
    """
    Return True if 'path' looks like a Python script:
      1. It ends in .py or .pyw
      2. Or it is executable AND its first line is a python shebang
    """
    # Common extensions
    if any(path.endswith(ext) for ext in ud.python_extensions):
        return True

    # No-extension scripts: check for executable bit + python shebang
    try:
        st = os.stat(path)
    except OSError:
        return False

    # Must be a regular file and executable by owner/group/other
    if not stat.S_ISREG(st.st_mode) or not (st.st_mode & (stat.S_IXUSR|stat.S_IXGRP|stat.S_IXOTH)):
        return False

    # Try to read the first line and look for a python shebang
    first_line = ud.my_fopen(path, suppress_errors=True, rawlog=False, numlines=1)
    if not first_line:
        return False
    return bool(re.match(r'#!.*\bpython[0-9.]*\b', first_line))

def list_packages(options: Options) -> None:
    """Examine command line arguments to determine if we're looking at a directory, a single python script, or a list of python scripts. List all installed and uninstalled packages that are imported in that directory or python script(s). Return these sets inside the options object."""
    if getattr(options.args, 'full', False):
        if not options.rawlog: logging.info("Building a virtual environment that can run every python script in this directory.")
        options.script_dir_or_file_or_list = options.script_dir
    else:
        # If there aren't any script arguments then we're looking at a single python script.
        # If the python script is autolambda.py then ignore any script arguments. Autolambda will take care of them separately so there's no need to install them in the venv.
        if not getattr(options.args, 'script_args', None) or "autolambda.py" in options.python_script:
            options.script_dir_or_file_or_list = options.python_script
        else:
            # List all the script arguments that are local python scripts.
            local_scripts = []
            for arg in options.script_args:
                full = arg if os.path.isabs(arg) else os.path.join(options.cwd, arg)
                # only include if it really looks like a Python script
                if is_python_script(full) and os.path.splitext(arg)[0] in options.custom_modules:
                    local_scripts.append(arg)
            # Local python scripts should be added to the list of scripts to examine for imports.
            if local_scripts:
                options.script_dir_or_file_or_list = [options.python_script] + local_scripts
            else:
                options.script_dir_or_file_or_list = options.python_script
    logging.debug(f"{options.script_dir_or_file_or_list = }")

    if type(options.script_dir_or_file_or_list) == str:
        options.script_dir_or_file_or_list = os.path.expanduser(options.script_dir_or_file_or_list)
        options.loaded_custom_modules = set()
        if os.path.isfile(options.script_dir_or_file_or_list):
            if is_python_script(options.script_dir_or_file_or_list):
                if not options.rawlog: logging.info(f"Processing a single Python script: {options.script_dir_or_file_or_list}.")
                python_file = options.script_dir_or_file_or_list
                options.all_imports = set()
                find_imports_in_script(options, python_file)
            else:
                ud.my_critical_error(f"'{options.script_dir_or_file_or_list}' is not a valid Python script.")
        elif os.path.isdir(options.script_dir_or_file_or_list):
            if not options.rawlog: logging.info(f"Processing an entire folder of Python scripts: {options.script_dir_or_file_or_list}.")
            python_dir = options.script_dir_or_file_or_list
            if options.pipreqs_available:
                if not options.rawlog: logging.info("Using pipreqs to generate requirements.")
                generate_requirements(options.script_dir_or_file_or_list)
                with open(os.path.join(python_dir, 'requirements.txt'), 'r') as f:
                    options.all_imports = set(line.strip() for line in f)
            else:
                if not options.rawlog: logging.info("Using custom script to find imports.")
                get_all_imports(options, options.script_dir_or_file_or_list)
        else:
            ud.my_critical_error(f"The file or directory {options.script_dir_or_file_or_list} does not exist.")
    else:
        if not options.rawlog: logging.info(f"Processing a list of Python scripts: {options.script_dir_or_file_or_list}")
        options.all_imports = set()
        # Filter out non‐Python files
        valid = []
        for sf in options.script_dir_or_file_or_list:
            full = sf if os.path.isabs(sf) else os.path.join(options.cwd, sf)
            if is_python_script(full):
                valid.append(sf)
            else:
                logging.info(f"Skipping non‐Python file in list: {full}")
        if not valid:
            ud.my_critical_error("No valid Python scripts found in the list of files.")
        options.script_dir_or_file_or_list = valid
        # Process only the ones left
        for python_file in options.script_dir_or_file_or_list:
            full = python_file if os.path.isabs(python_file) else os.path.join(options.cwd, python_file)
            find_imports_in_script(options, full)

    # Filter out invalid imports before splitting
    options.all_imports = {imp for imp in options.all_imports if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', imp)}
    
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
            file_path = os.path.join(root, file)
            if is_python_script(file_path):
                find_imports_in_script(options, file_path)
                processed_files += 1
                if not options.rawlog: logging.info(f"Processing {file_path} ({processed_files}/{total_files})")

    if not options.rawlog: logging.info(f"\nFinished processing files in {directory}.")

def generate_requirements(directory: str) -> None:
    """Generate a requirements file using pipreqs."""
    try:
        pipreqs.generate_requirements(directory)
    except (pipreqs.PipreqsError, pipreqs.PipreqsWarning) as e:
        raise ValueError(f"Error generating requirements file in {directory}") from e

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
        if not options.rawlog: logging.info(f"Writing download script to {options.download_script_path}")
        with open(options.download_script_path, 'w') as f:
            f.write(download_script)
        os.chmod(options.download_script_path, 0o755)
        # Run the initial download script and capture the output
        result = ud.my_popen([options.download_script_path])
        return result.returncode == 0
    except (IOError, OSError) as e:
        logging.error(f"Error writing or executing download script: {e}\nException type: ", exc_info=True)
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
        if not options.rawlog: logging.info("Installing all packages simultaneously...")
        # Run the command and capture the output line by line using ud.my_popen
        result = ud.my_popen(install_command)
        if result.returncode == 0:
            if not options.rawlog: logging.info("All packages installed successfully.")
            return True
        else:
            logging.error("Failed to install some packages.")
            return False
    except Exception as e:
        logging.error(f"Error during simultaneous installation: {e}\nException type: ", exc_info=True)
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
        if not options.rawlog: logging.info("All packages installed successfully.")

def install_package(package_name: str, options: Options) -> bool:
    """Install a single package and return the success status (True if successful, False otherwise)."""
    try:
        result = subprocess.run(
            [options.venv_python, "-m", "pip", "install", package_name, "--no-index", "--find-links", options.packages_dir],
            capture_output=True,
            text=True
        )
        if not options.rawlog: logging.info(result.stdout)
        if result.stderr:
            logging.error(result.stderr)
        if result.returncode != 0:
            # Use pip to download files for package_name to options.packages_dir
            download_command = [options.venv_python, "-m", "pip", "download", "--dest", options.packages_dir, package_name]
            download_result = subprocess.run(download_command, capture_output=True, text=True)
            if download_result.returncode != 0:
                ud.my_critical_error(f"Failed to download {package_name}. Error: {download_result.stderr}")
            # Use pip to install package_name from the file that was just downloaded to options.packages_dir
            install_command = [options.venv_python, "-m", "pip", "install", "--no-index",
                               "--find-links", options.packages_dir, package_name]
            install_result = subprocess.run(install_command, capture_output=True, text=True)
            if install_result.returncode != 0:
                logging.error(f"Failed to install {package_name}. Error: {install_result.stderr}")
            else:
                if not options.rawlog: logging.info(f"Successfully installed {package_name}")
            return result.returncode == 0
        return result.returncode == 0
    except Exception as e:
        logging.error(f"Error installing package {package_name}: {e}\nException type: ", exc_info=True)
        return False

def check_packages_in_venv(options: Options, package: str | None = None, venv_dir: str | None = None) -> bool:
    """Create and run a script to test package imports in the virtual environment. Add packages from the requirements.txt file if '-reqs' is specified as a runtime argument."""
    if not venv_dir:
        venv_dir = options.venv_dir
    venv_python = os.path.join(venv_dir, 'bin', 'python')
    if sys.platform == "win32":
        venv_python = os.path.join(venv_dir, 'Scripts', 'python.exe')
    if package:
        packages_str = f"'{options.reversed_module_aliases.get(package, package)}'"
    else:
        use_pip_list(options)
        packages_str = ", ".join(f"'{options.reversed_module_aliases.get(pkg, pkg)}'" for pkg in options.uninstalled_imports)
    test_script = f"""
source {venv_dir}/bin/activate
{venv_python} - << END
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
    try:
        # Since ud.my_popen expects a list of commands, we'll pass the shell command directly as a single argument list
        command_list = ['/bin/bash', '-c', test_script]
        # Run the command using the custom ud.my_popen function
        result = ud.my_popen(command_list, True) # True means to suppress output.
        return "packages imported successfully" in result.stdout
    except subprocess.CalledProcessError as e:
        logging.error(f"Error running test script: {e}\nException type: ", exc_info=True)
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
        if not options.rawlog: logging.info(f"Recovered current pip version: {options.current_pip_version}")
    else:
        logging.warning("Failed to recover current pip version from output.")
    
    if new_version_match:
        options.new_pip_version = new_version_match.group(1)
        if not options.rawlog: logging.info(f"Recovered new pip version: {options.new_pip_version}")
    else:
        logging.warning("Failed to recover new pip version from output.")

def pretty_packages_list(options: Options) -> str:
    """Create a pretty string of the first five package names and the number of remaining packages."""
    maxnum = 5
    packages_list = sorted(list(options.uninstalled_imports))
    if len(packages_list) > maxnum:
        first_five = '-'.join(packages_list[:maxnum])
        suffix = f'-and-{len(packages_list) - maxnum}-more'
    else:
        first_five = '-'.join(packages_list)
        suffix = ''
    
    return first_five + suffix

def use_pip_list(options: Options) -> None:
    """Use the pip list command to find all installed packages and use that pip list to modify the uninstalled and installed imports. Add packages from the options.extra_requirements dictionary if '-reqs' is specified as a runtime argument."""
    # Add packages from the options.extra_requirements dictionary if '-reqs' is specified as a runtime argument.
    if getattr(options.args, 'reqs', False):
        options.uninstalled_imports = options.uninstalled_imports.union(options.extra_requirements.keys())
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
            logging.debug(f"Output:\n{result.stdout}")
        except subprocess.CalledProcessError as e:
            logging.error(f"{e}\nException type: ", exc_info=True)

        # Use regular expressions to find all package names
        options.pip_list = re.findall(r'^[^\s]+', result.stdout, re.MULTILINE)
        options.pip_list = [pkg for pkg in options.pip_list if pkg != 'Package' and not all(c == '-' for c in pkg)]
        logging.debug(f"\n{options.pip_list = }")

        pip_list_filename = os.path.join(options.my_dir, f"pip_list_{options.timestamp}.txt")
        with open(pip_list_filename, 'w') as f:
            f.write('\n'.join(options.pip_list))
    
    new_uninstalled_imports = options.installed_imports - set(options.pip_list)
    options.uninstalled_imports = options.uninstalled_imports.union(new_uninstalled_imports)
    if options.uninstalled_imports:
        logging.debug(f"{new_uninstalled_imports = }")
    options.installed_imports = options.installed_imports - new_uninstalled_imports
    # Once again, add packages from the options.extra_requirements dictionary if '-reqs' is specified as a runtime argument. (Do this again, just in case they got removed from the uninstalled_imports set above.)
    if getattr(options.args, 'reqs', False):
        options.uninstalled_imports = options.uninstalled_imports.union(options.extra_requirements.keys())

def parse_extra_requirements(options: Options) -> Dict[str, str | None]:
    """Parse an extra requirements file and return a dictionary of package names (and version specifiers, if present)."""
    options.extra_requirements = {}
    file_content = ud.my_fopen(options.extra_requirements_file, suppress_errors=True, rawlog=options.rawlog)
    if not file_content:
        return
    # Regular expression to capture package name and version specifier
    pattern = re.compile(r'^\s*([A-Za-z0-9_\-\.]+)\s*(.*)$')
    try:
        for line in file_content.splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                match = pattern.match(line)
                if match:
                    package = match.group(1)
                    version_spec = match.group(2).strip() if match.group(2) else ''
                    options.extra_requirements[package] = version_spec
    except Exception as e:
        logging.error(f"Error parsing extra requirements file: {e}\nException type: ", exc_info=True)

def write_requirements_file_with_extras(options: Options) -> bool:
    """Write the requirements file with the extra requirements added and generate a 'pretty' requirements string."""
    logging.debug(f"Writing packages to {options.requirements_file}")
    options.pretty_requirements = ''
    # Define the symbol replacements
    replacements = [
        ('>=', '_ge'),
        ('<=', '_le'),
        ('==', '_eq'),
        ('~=', '_approx'),
        ('>', '_gt'),
        ('<', '_lt'),
        (',', '_and'),
    ]
    try:
        with open(options.requirements_file, 'w') as f:
            # Write the packages in alphabetical order so the requirements file is deterministic.
            for idx, package in enumerate(sorted(options.uninstalled_imports)):
                if package in options.extra_requirements:
                    version_spec = options.extra_requirements[package]
                    if version_spec:
                        f.write(f"{package}{version_spec}\n")
                        # Replace symbols in version_spec for the pretty_requirements string
                        pretty_version_spec = version_spec
                        for old, new in replacements:
                            pretty_version_spec = pretty_version_spec.replace(old, new)
                        pretty_package = f"{package}{pretty_version_spec}"
                    else:
                        f.write(f"{package}\n")
                        pretty_package = package
                else:
                    f.write(f"{package}\n")
                    pretty_package = package
                # Append to the pretty_requirements string with underscores
                if idx > 0:
                    options.pretty_requirements += '_'
                options.pretty_requirements += pretty_package
    except Exception as e:
        logging.error(f"Error writing packages to {options.requirements_file}: {e}\nException type: ", exc_info=True)
        return False
    return True

def setup_virtualenv(options: Options) -> bool:
    """Setup a virtual environment and install packages."""
    use_pip_list(options)
    options.pretty_list = pretty_packages_list(options)
    # Create a virtual environment directory that starts with 'failed' in case the process fails. Only remove the 'failed' part if this process completes successfully.
    options.set_venv_dir(os.path.join(options.my_dir, f"failed-{options.venv_name}-versionless-{options.timestamp}-{options.pretty_list}"))
    os.makedirs(options.venv_dir, exist_ok=True)

    if not write_requirements_file_with_extras(options):
        return False

    if not options.rawlog: logging.info("Creating virtual environment...")
    subprocess.check_call([sys.executable, '-m', 'venv', options.venv_dir])
    if not options.rawlog: logging.info("Virtual environment created.")

    # Activate virtual environment and install wheel
    install_command = f"bash -c '{options.activate_script} && {options.venv_pip} install wheel'"
    subprocess.run(install_command, shell=True, check=True)
    if not options.rawlog: logging.info("Wheel installed in the virtual environment.")

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

def get_file_operations(options: Options, script_path: str) -> None:
    """Find files that are read or written, store in options."""
    file_content = ud.my_fopen(script_path, rawlog=options.rawlog)
    if not file_content: # Do NOT run a file if we can't read it!
        ud.my_critical_error(f"Failed to open {script_path}", choose_breakpoint=True)
    tree = ud.my_ast_parse(file_content, script_path)
    if not tree:
        return

    class FileOperationsVisitor(ast.NodeVisitor):
        """Visitor class to find file operations in the AST (Abstract Syntax Tree)."""
        def visit_Call(self, node: ast.Call) -> None:
            """Visit function calls to find file operations."""
            # Check if the function called is 'open'
            if isinstance(node.func, ast.Name) and node.func.id == 'open':
                # Get the filename
                if isinstance(node.args[0], ast.Constant):  # For Python 3.8+
                    filename = node.args[0].value
                else:
                    return

                # Determine if the file is being read or written
                if len(node.args) > 1:
                    if isinstance(node.args[1], ast.Constant):
                        mode = node.args[1].s if isinstance(node.args[1], ast.Constant) else node.args[1].value
                    else:
                        return
                else:
                    mode = 'r'  # Default mode

                if 'r' in mode:
                    options.read_files.append(filename)
                elif 'w' in mode or 'a' in mode or 'x' in mode:
                    options.write_files.append(filename)

            self.generic_visit(node)

    visitor = FileOperationsVisitor()
    visitor.visit(tree)
    return

def get_network_operations(options: Options, script_path: str) -> None:
    """Find URLs that are downloaded and uploaded, store in options."""
    file_content = ud.my_fopen(script_path, rawlog=options.rawlog)
    if not file_content: # Do NOT run a file if we can't read it!
        ud.my_critical_error(f"Failed to open {script_path}", choose_breakpoint=True)
    tree = ud.my_ast_parse(file_content, script_path)
    if not tree:
        return

    class NetworkOperationsVisitor(ast.NodeVisitor):
        """Visitor class to find network operations in the AST (Abstract Syntax Tree)."""
        def visit_Call(self, node: ast.Call) -> None:
            """Visit function calls to find network operations."""

    class NetworkOperationsVisitor(ast.NodeVisitor):
        """Visitor class to find network operations in the AST (Abstract Syntax Tree)."""
        def visit_Call(self, node: ast.Call) -> None:
            """Visit function calls to find network operations."""
            # Check if the function is a requests function
            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                if node.func.value.id == 'requests':
                    if node.func.attr in ['get', 'options', 'head', 'post', 'put', 'patch', 'delete']:
                        if len(node.args) > 0 and isinstance(node.args[0], ast.Str):
                            url = node.args[0].s
                            if node.func.attr == 'get':
                                options.download_urls.append(url)
                            else:
                                options.upload_urls.append(url)
                        elif len(node.args) > 0 and isinstance(node.args[0], ast.Constant):  # For Python 3.8+
                            url = node.args[0].value
                            if node.func.attr == 'get':
                                options.download_urls.append(url)
                            else:
                                options.upload_urls.append(url)

            # Check if the function is a urllib request function
            elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Attribute):
                if node.func.value.attr in ['urlopen', 'Request']:
                    if len(node.args) > 0 and isinstance(node.args[0], ast.Str):
                        url = node.args[0].s
                        options.download_urls.append(url)
                    elif len(node.args) > 0 and isinstance(node.args[0], ast.Constant):  # For Python 3.8+
                        url = node.args[0].value
                        options.download_urls.append(url)

            self.generic_visit(node)

    visitor = NetworkOperationsVisitor()
    visitor.visit(tree)

    return

def guard_examines(options: Options) -> bool:
    """
    Examine options.python_script:
      1. Is it a valid python script? If not, return False and skip the rest of this function.
      2. If so, return True and list the files that it reads and writes, as well as the URLs it downloads and uploads.
    """
    options.read_files    = []
    options.write_files   = []
    options.download_urls = []
    options.upload_urls   = []

    def aggregate_operations(script_path: str) -> None:
        """Aggregate file and network operations from script_path."""
        get_file_operations(options, script_path)
        get_network_operations(options, script_path)

    # Examine the main script to make sure it's a valid Python script.
    if is_python_script(options.python_script) and ud.compile_script(options.python_script):
        try:
            aggregate_operations(options.python_script)
        except Exception as e:
            raise RuntimeError(f"Error examining {options.python_script} for file operations: {e}") from e
    else:
        logging.warning(f"Skipping file operations analysis for {options.python_script} because it doesn't look like a valid Python script.")
        return False

    # Examine each custom module
    for custom_load in options.loaded_custom_modules:
        module_path = options.custom_modules[custom_load]
        aggregate_operations(module_path)

    if not options.rawlog:
        if options.read_files:
            logging.info("Files read: " + ", ".join(options.read_files))
        if options.write_files:
            logging.info("Files written: " + ", ".join(options.write_files))
        if options.download_urls:
            logging.info("Download URLs: " + ", ".join(options.download_urls))
        if options.upload_urls:
            logging.info("Upload URLs: " + ", ".join(options.upload_urls))
    
    return True

def save_options_to_json(options: Options) -> None:
    """Save the options object to a JSON file."""
    options.json_filename = os.path.join(options.script_dir, f".{os.path.basename(options.python_script)}-{options.my_name}-last-used-on-{options.timestamp}.json")
    
    # Convert options to a dictionary and handle sets
    options_dict = options.__dict__

    # Convert PosixPath to string
    for key, value in options_dict.items():
        if isinstance(value, PosixPath):
            logging.debug(f"Converting PosixPath to string for key '{key}' and value '{value}'")
            options_dict[key] = str(value)

    # Ensure directory exists
    json_file_path = Path(options.json_filename)
    logging.debug(f"Ensuring directory exists: {json_file_path.parent}")
    json_file_path.parent.mkdir(parents=True, exist_ok=True)

    # Identify non-serializable types.
    these_sets = []
    non_serializable = {}
    for key, value in options_dict.items():
        try:
            json.dumps(value)
        except TypeError as e:
            non_serializable[key] = type(value).__name__
            logging.debug(f"Key '{key}' is of type {type(value).__name__}, so it needs to be modified for JSON serialization: {e}")

    if non_serializable:
        logging.debug("Non-serializable keys being modified for JSON serialization...", non_serializable)
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

def load_options_from_json(options: Options, json_file: str) -> Options:
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
    
    if not options.rawlog: logging.info(f"options loaded from {json_file}")
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
                if not options.rawlog: logging.info(f"The cached venv directory {options_from_cache.venv_dir} does not have all the currently required packages.")
        else:
            if not options.rawlog: logging.info(f"The cached venv directory {options_from_cache.venv_dir} is no longer valid.")
    return 0

def find_match_dir_in_cache(options: Options) -> str:
    """Find a matching virtual environment directory in the cache."""
    if not getattr(options.args, 'latest', False) and \
       not getattr(options.args, 'oldest', False) and \
       not getattr(options.args, 'last_used', False) and \
       not getattr(options.args, 'smallest', False):
        options.args.last_used = True #If no flags are set, then the default is to load the last used venv in the cache
    if     getattr(options.args, 'last_used', False) and \
       not getattr(options.args, 'latest', False) and \
       not getattr(options.args, 'smallest', False):
        try: # Try to load the last used venv in the cache
            json_files = [f for f in os.listdir(options.script_dir) if f.startswith("."+os.path.basename(options.python_script)) and f.endswith('.json')]
            if json_files:
                if len(json_files) > 1:
                    json_files.sort(key=lambda x: dt.datetime.strptime(x.split('-')[-2] + x.split('-')[-1].replace('.json', ''), "%Y%m%d%H%M%S"), reverse=True)
                options_last_used = load_options_from_json(options, os.path.join(options.script_dir, json_files[0]))
                if check_venv_dir(options, options_last_used):
                    return options_last_used.venv_dir
                else:
                    if not options.rawlog: logging.info("Trying to load the latest matching venv now.")
        except Exception as e:
            if not options.rawlog:
                logging.error(f"Error loading last used venv from cache: {e}\nException type: ", exc_info=True)
                logging.warning("The last used cache encountered a problem. Trying to load the latest matching venv now.")
        options.args.latest    = True #If that didn't work, try to load the latest venv in the cache
        options.args.last_used = False #And set this to False because it failed
    if not options.rawlog: logging.info("Checking the cache for a virtual environment with all the required packages...")
    #Search for all venv_name folders in my_dir:
    all_venv_folders = [f for f in os.listdir(options.my_dir) if os.path.isdir(os.path.join(options.my_dir, f)) and f.startswith(options.venv_name)]
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
        this_requirements_file = os.path.join(options.my_dir, folder, 'requirements.txt')
        with open(this_requirements_file, 'r') as file:
            requirements = set(file.read().splitlines())
        if options.uninstalled_imports.issubset(requirements):
            this_timestamp = folder.split('-')[2]+'-'+folder.split('-')[3]
            final_venv_folders[folder] = {'timestamp': this_timestamp, 'num_packages': len(requirements)}
    if not final_venv_folders:
        if not options.rawlog: logging.info("No matching venv folders found in the cache.")
    else:
        if not options.rawlog: logging.info(f"Found {len(final_venv_folders)} matching venv folders in the cache.")
        if     getattr(options.args, 'latest', False) and \
           not getattr(options.args, 'oldest', False) and \
           not getattr(options.args, 'last_used', False) and \
           not getattr(options.args, 'smallest', False):
            # Return the latest venv in the cache which has all the packages needed now
            options_latest = copy.deepcopy(options)
            options_latest.set_venv_dir(os.path.join(options.my_dir, latest_venv(final_venv_folders)))
            options_latest.uninstalled_imports = options.uninstalled_imports
            if check_venv_dir(options, options_latest):
                return options_latest.venv_dir
            else:
                if not options.rawlog: logging.error("The latest venv in the cache is invalid. Giving up on the cache and starting from scratch.")
                return None
        elif    getattr(options.args, 'oldest', False) and \
            not getattr(options.args, 'latest', False) and \
            not getattr(options.args, 'last_used', False) and \
            not getattr(options.args, 'smallest', False):
            # Return the oldest venv in the cache which has all the packages needed now
            options_oldest = copy.deepcopy(options)
            options_oldest.set_venv_dir(os.path.join(options.my_dir, oldest_venv(final_venv_folders)))
            options_oldest.uninstalled_imports = options.uninstalled_imports
            if check_venv_dir(options, options_oldest):
                return options_oldest.venv_dir
            else:
                if not options.rawlog: logging.error("The oldest venv in the cache is invalid. Giving up on the cache and starting from scratch.")
                return None
        elif    getattr(options.args, 'smallest', False) and \
            not getattr(options.args, 'latest', False) and \
            not getattr(options.args, 'oldest', False) and \
            not getattr(options.args, 'last_used', False):
            # Return the smallest venv in the cache which has all the packages needed now
            options_smallest = copy.deepcopy(options)
            options_smallest.set_venv_dir(os.path.join(options.my_dir, smallest_venv(final_venv_folders)))
            options_smallest.uninstalled_imports = options.uninstalled_imports
            if check_venv_dir(options, options_smallest):
                return options_smallest.venv_dir
            else:
                if not options.rawlog: logging.error("The smallest venv in the cache is invalid. Giving up on the cache and starting from scratch.")
                return None
        else: # This should never happen
            logging.error(f"Invalid combination of flags. {getattr(options.args, 'latest', False) = }, {getattr(options.args, 'oldest', False) = }, {getattr(options.args, 'last_used', False) = }, {getattr(options.args, 'smallest', False) = }")

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

def only_search_here_filename_boolean(filename: str, thestring: str) -> bool:
    """Check if the given filename contains thestring, which is used to determine if the search is limited to the current directory."""
    return thestring in filename

def search_anywhere_filename_boolean(filename: str, thestring: str) -> bool:
    """Check if the given filename does NOT contain thestring. By default, those files are assumed to have been created by searching above the current directory."""
    return thestring not in filename

def only_search_here_path_boolean(options: Options, path: str) -> bool:
    """Check if the given path is in the current directory."""
    return os.path.abspath(path).startswith(os.path.abspath('.'))

def search_anywhere_path_boolean(options: Options, path: str) -> bool:
    """Return True regardless."""
    return True

def dict_of_custom_modules(options: Options) -> Dict[str, str]:
    """Create a dictionary of all local custom modules in the non-standard sys.path directories and their associated filepaths."""
    #If -rc and -no-cache were not specified, look for a pickle file with the custom modules dictionary the last time this script was run.

    # I.f.f. options.search_above_this_dir is True, then search above the current directory for custom modules.
    # Either way, only load custom module pickle files that searched in the same places as requested.
    search_above_text_to_match = 'only_search_here_' # For legacy reasons, custom module pickle files are assumed to have searched above the current directory unless this text is present in the filename.
    if options.search_above_this_dir:
        search_above_text_to_write = '_' # This will be added to the filename of the custom modules pickle file.
        search_constraint_filename_boolean = search_anywhere_filename_boolean
        search_constraint_path_boolean     = search_anywhere_path_boolean
    else:
        search_above_text_to_write = search_above_text_to_match # This will be added to the filename of the custom modules pickle file.
        search_constraint_filename_boolean = only_search_here_filename_boolean
        search_constraint_path_boolean     = only_search_here_path_boolean

    if not getattr(options.args, 'rc', False) and not getattr(options.args, 'no_cache', False):
        for file in os.listdir('.'):
            if file.startswith(f'.{options.my_name}_custom_modules_') and file.endswith('.pkl') and options.computer_name in file and search_constraint_filename_boolean(file, search_above_text_to_match):
                if not options.rawlog: logging.info(f"Loading custom modules from {file}")
                with open(file, 'rb') as f:
                    custom_modules = pickle.load(f)
                return custom_modules

    custom_modules = {}
    logging.debug(f"In dict_of_custom_modules: {options.new_local_paths = }")
    for path in sys.path:
        if not is_standard_path(options, path) and os.path.isdir(path) and search_constraint_path_boolean(options, path):
            for root, dirs, files in os.walk(path):
                for file in files:
                    if file.endswith('.py') and file != '__init__.py':
                        module_name = os.path.splitext(file)[0]
                        if module_name not in custom_modules.keys():
                            full_path = os.path.join(root, file)
                            if not is_standard_path(options, full_path):
                                custom_modules[module_name] = full_path
                for dir in dirs:
                    if not is_standard_path(options, os.path.join(root, dir)):
                        package_path = os.path.join(root, dir)
                        if os.path.isfile(os.path.join(package_path, '__init__.py')):
                            if dir not in custom_modules and not is_standard_path(options, package_path):
                                custom_modules[dir] = package_path + os.sep
                            # Remove any individual module entries within the package directory
                            for file in os.listdir(package_path):
                                module_name = os.path.splitext(file)[0]
                                if module_name in custom_modules and package_path == os.path.dirname(custom_modules[module_name]):
                                    del custom_modules[module_name]
    #Now save to a pickle file:
    current_time = dt.datetime.now().strftime('%Y%m%d-%H%M%S')
    custom_filename = f'.{options.my_name}_custom_modules_{options.computer_name}{search_above_text_to_write}{current_time}.pkl'
    with open(custom_filename, 'wb') as f:
        if not options.rawlog: logging.info(f"Saving custom modules to {custom_filename}")
        pickle.dump(custom_modules, f)
    return custom_modules

def check_python_version(command: str) -> bool:
    """Check if the given Python command is available and has a version of PY_VERSION or higher."""
    try:
        preferred_major = int(ud.PY_VERSION)
        preferred_minor = int((ud.PY_VERSION - preferred_major) * 100)
        result = subprocess.run([command, '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            version = result.stdout.strip().split()[1]
            major, minor = map(int, version.split('.')[:2])
            if major == preferred_major and minor >= preferred_minor:
                return True
        return False
    except Exception as e:
        logging.error(f"Error checking {command}: {e}\nException type: ", exc_info=True)
        return False

def find_preferred_python_version() -> str | None:
    """Find the command for the preferred version of python (stored in univ_defs.py as PY_VERSION)."""
    try:
        # Check if the preferred python command (only specifying integer part of the preferred version) exists and returns a valid path
        preferred_major = int(ud.PY_VERSION)
        preferred_python_path = subprocess.run(['which', f'python{preferred_major}'], capture_output=True, text=True).stdout.strip()
        if preferred_python_path and check_python_version(f'python{preferred_major}'):
            return os.path.basename(preferred_python_path)

        # Check if the preferred python command (with complete version specified) exists and returns a valid path
        preferred_python_path = subprocess.run(['which', f'python{ud.PY_VERSION}'], capture_output=True, text=True).stdout.strip()
        if preferred_python_path and check_python_version(f'python{ud.PY_VERSION}'):
            return os.path.basename(preferred_python_path)
        
        return None
    except Exception as e:
        logging.error(f"Error finding python{ud.PY_VERSION}: {e}\nException type: ", exc_info=True)
        return None

def main() -> None:
    """Main function."""
    start_time = dt.datetime.now()
    options = Options()
    parse_arguments(options)
    options.python_script = getattr(options.args, 'script', None)
    options.script_args = getattr(options.args, 'script_args', [])
    options.rawlog = getattr(options.args, 'rawlog', False)

    if getattr(options.args, 'version', False):
        print(__version__)
        sys.exit(0)
    if getattr(options.args, 'manual', False):
        # Print instructions for manually adding the alias to the shell configuration file
        print(options.manual_instructions)
        sys.exit(0)

    if getattr(options.args, 'debug', False):
        options.log_mode = 'DEBUG'

    memory_handler = ud.configure_logging(options.my_name,
                                          log_level=options.log_mode,
                                          rawlog=options.rawlog)

    options.python_command = find_preferred_python_version()
    if options.python_command:
        logging.debug(f"Python {ud.PY_VERSION} is available at: {options.python_command}")
    else:
        logging.debug(f"Python {ud.PY_VERSION} is not available.")

    try:
        import pipreqs
        logging.debug("pipreqs is available, so it will be used.")
        options.pipreqs_available = True
    except ImportError:
        logging.debug("pipreqs is not available. Try installing it with 'pip install pipreqs'.")
        options.pipreqs_available = False

    if getattr(options.args, 'alias', False):
        # Add the alias to the shell configuration file
        add_alias(options)
        sys.exit(0)
    elif getattr(options.args, 'script', False):
        pass
    elif getattr(options.args, 'blank_slate', False):
        if not getattr(options.args, 'y', False):
            response = input(f"Are you sure you want to delete everything in ~/{options.my_name}/ and all {options.my_name} .json files in the current directory? (y/n) ")
            if response.casefold() != 'y':
                logging.info("Exiting without deleting anything.")
                sys.exit(0)
        logging.info(f"Deleting everything in ~/{options.my_name}/ and all {options.my_name} .out and .err and .json and .pkl files in the current directory.")
        shutil.rmtree(options.my_dir, ignore_errors=True)
        for file in os.listdir(options.cwd):
            logging.debug(f"Checking {file}")
            if os.path.isfile(file):
               if (file.startswith(f'.{options.my_name}-') and file.endswith('.out')) or \
                  (file.startswith(f'.{options.my_name}-') and file.endswith('.err')) or \
                  (file.startswith(f'.{options.my_name}_custom_modules_') and file.endswith('.pkl')) or \
                  (file.startswith('.') and f'-{options.my_name}-' in file and file.endswith('.json')):
                    try:
                        logging.info(f"Deleting {file}")
                        os.remove(os.path.join(options.cwd, file))
                    except:
                        logging.error(f"Error deleting {file}")
        sys.exit(0)
    elif getattr(options.args, 'full', False) and not getattr(options.args, 'script', False):
        options.args.script   = options.cwd
        options.python_script = options.cwd
    else:
        logging.info("You must specify either a script to run or one of these arguments: alias, manual, blank-slate (be careful using blank-slate because it deletes all cached virtual environments, among other things!).")

    options.script_dir = os.path.abspath(os.path.dirname(options.python_script))
    logging.debug(f"Directory where the script to run is located: {options.script_dir}")

    if getattr(options.args, 'reqs', False):
        parse_extra_requirements(options)
        if not options.rawlog: logging.info(f"Loaded extra requirements from ./{options.extra_requirements_file}: {options.extra_requirements}")

    if not os.path.isdir(options.my_dir):
        if not options.rawlog: logging.info(f"Directory {options.my_dir} does not exist yet, so it is being created.")
        os.makedirs(options.my_dir, exist_ok=True)
    if not os.path.isdir(options.packages_dir):
        if not options.rawlog: logging.info(f"Directory {options.packages_dir} does not exist yet, so it is being created.")
        os.makedirs(options.packages_dir, exist_ok=True)

    time1 = dt.datetime.now()
    options.custom_modules = dict_of_custom_modules(options)
    time2 = dt.datetime.now()
    elapsed_time = time2 - time1
    if not options.rawlog: logging.info(f"dict_of_custom_modules() took {elapsed_time}")
    
    #Look for files in options.my_dir that start with pip_list and load the most recent one.
    options.pip_list = []
    pip_list_files = sorted([f for f in os.listdir(options.my_dir) if f.startswith('pip_list')],reverse=True)
    logging.debug(f"{pip_list_files = }")
    #If -rc was not specified, look for a text file with the pip list the last time this script was run.
    if not getattr(options.args, 'rc', False) and pip_list_files:
        try:
            with open(os.path.join(options.my_dir, pip_list_files[0]), 'r') as file:
                for line in file:
                    options.pip_list.append(line.strip())
        except:
            logging.error(f"Error reading {pip_list_files[0]}")

    start_list_packages_time = dt.datetime.now()
    elapsed_time = start_list_packages_time - start_time
    if not options.rawlog: logging.info(f"Elapsed time: {elapsed_time}")

    list_packages(options)

    if not options.rawlog:
        logging.info(f"Uninstalled imports: {options.uninstalled_imports}")
        if options.bad_imports:
            logging.warning(f"Bad imports: {options.bad_imports}")
        if options.samedir_files:
            logging.info(f"Imported files in the same directory as the script: {options.samedir_files}")
        if options.subfolders:
            logging.info(f"Imported subfolders: {options.subfolders}")

    if getattr(options.args, 'justprint', False):
        ud.print_all_errors(memory_handler, options.rawlog)
        sys.exit(0)

    if not options.uninstalled_imports:
        if not options.rawlog: logging.info("All required packages are already installed.")
        if guard_examines(options):
            start_raw_time = dt.datetime.now()
            subprocess.run([sys.executable, options.python_script] + options.script_args)
            elapsed_raw_time = dt.datetime.now() - start_raw_time
            if not options.rawlog: logging.info(f"Runtime: {elapsed_raw_time}")
    elif is_virtualenv():
        if not options.rawlog: logging.info("Already in a virtual environment.")
        if check_packages_in_venv(options):
            if guard_examines(options):
                start_raw_time = dt.datetime.now()
                subprocess.run([sys.executable, options.python_script] + options.script_args)
                elapsed_raw_time = dt.datetime.now() - start_raw_time
                if not options.rawlog: logging.info(f"Runtime: {elapsed_raw_time}")
        else:
            logging.error("The current virtual environment does not have all the required packages.")
            if not options.rawlog: logging.info("Please deactivate the current virtual environment and run the script again.")
    else:
        if getattr(options.args, 'no_cache', False):
            match_dir = None
        else:
            match_dir = find_match_dir_in_cache(options)
        if not match_dir:
            if not options.rawlog: logging.info(f"Creating new virtual environment '{options.venv_name}'...")
            if setup_virtualenv(options):
                match_dir = options.venv_dir
            else:
                ud.my_critical_error("Failed to create a virtual environment.", choose_breakpoint=True)
                match_dir = None
        else:
            if not options.rawlog: logging.info(f"Using directory: {match_dir}")

        if match_dir:
            options.set_venv_dir(match_dir)
            start_venv_time = dt.datetime.now()
            elapsed_time = start_venv_time - start_time
            if not options.rawlog: logging.info(f"Elapsed time: {elapsed_time}")
            if guard_examines(options):
                if not options.rawlog:
                    logging.info(f"Activating virtual environment: {options.activate_script}")
                    echo_statement = " && echo \"Virtual environment activated.\""
                else:
                    echo_statement = ""
                activate_cmd = f"bash -c '{options.activate_script}{echo_statement} && {options.venv_python} {options.python_script} {' '.join(options.script_args)}'"
                #I want to capture the output of the subprocess.run() so that I can print it at the end.
                result = subprocess.run(activate_cmd, shell=True)
                end_time = dt.datetime.now()
                elapsed_time = end_time - start_venv_time
                if not options.rawlog: logging.info(f"Elapsed time since activating virtual environment: {elapsed_time}")
                if result.returncode != 0 and not options.rawlog:
                    logging.error(f"Error running script: {result.stderr}")
            if os.path.basename(options.venv_dir).startswith('failed-') and options.simultaneous_success:
                #If the program has made it to this point, it has run successfully, so the venv directory can be renamed. It HASN'T failed. However, if it couldn't install simultaneously, then it's still a failed venv.
                os.rename(options.venv_dir, options.venv_dir.replace('failed-', ''))
                options.set_venv_dir(options.venv_dir.replace('failed-', ''))
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

    ud.print_all_errors(memory_handler, options.rawlog)
    logging.shutdown()

if __name__ == "__main__":
    main()
