#!/usr/bin/env python3

# Written by Emmy Killett (she/her), ChatGPT 4o (it/its), ChatGPT o1-preview (it/its), ChatGPT o3-mini-high (it/its), ChatGPT o4-mini-high (it/its), ChatGPT 5 Thinking (it/its), and GitHub Copilot (it/its).
from __future__ import annotations  # For Python 3.7+ compatibility with type annotations
import os
import sys
import subprocess
import datetime as dt
import argparse
import ast
import re
import copy
import shutil
import venv
import pickle
from pathlib     import Path  # Preferred over os.path for path manipulations.
from typing      import Any, Final
import logging
import tempfile
import shlex  # For safely quoting shell commands
from functools   import lru_cache  # For caching results of expensive function calls
from collections import defaultdict

import univ_defs as ud

__version__: str = "0.2.2"


class Options(ud.Options):
    """Class that has all global options in one place."""

    def __init__(self) -> None:
        """Initialize the Options class with default values."""
        super().__init__()                  # Call the parent class's __init__ method from univ_defs.py
        self.log_mode:                      int = logging.INFO  # Use --debug to change to logging.DEBUG.
        self.search_above_this_dir:        bool = True
        self.my_filepath:                  Path = ud.ensure_path(sys.argv[0])  # Full (invoked) path to this script
        self.my_name:                       str = self.my_filepath.stem  # The base name of this script without the .py extension
        self.home:                         Path = Path.home()  # User's home directory
        # The "my_dir" is NOT the directory where this script is located.
        # Instead, it's the directory where this script will store its virtual environments and packages.
        self.my_dir:                       Path = self.home / self.my_name
        self.python_command:                str = ""
        self.cwd:                          Path = Path.cwd().expanduser().resolve(strict=True)
        self.venv_name:                     str = "myenv"  # Can NOT include dashes ("-")
        self.packages_dir:                 Path = self.my_dir / "packages"
        self.test_dir:                     Path = self.my_dir / "test"
        self.uninstalled_imports:      set[str] = set()
        self.installed_imports:        set[str] = set()
        self.bad_imports:              set[str] = set()
        self.all_imports:              set[str] = set()
        self.total_imports:                 int = 0
        self.custom_modules:    dict[str, Path] = {}  # Maps custom module names to their file Paths
        self.subfolders:              list[str] = []
        self.samedir_files:          list[Path] = []
        self.pip_list:                list[str] = []
        self.loaded_custom_modules:    set[str] = set()
        self.pretty_list:                   str = ""  # A pretty-printed string listing "all" imports
        self.timestamp:                     str = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.sys_path_hints:          set[Path] = set()  # Filled by SysPathVisitor
        self.python_script:         Path | None = None
        self.script_name:                   str = ""  # python_script without the .py extension
        self.script_dir:            Path | None = None
        self.script_args:             list[str] = []
        self.options_json_filepath: Path | None = None
        # Before 2025-08-10 at 22:49:00, paths were stored as strings. After that date, they were stored as pathlib.Path objects. Any .pkl files created before that date have their paths converted to pathlib.Path objects when loaded. Any .json files created before that date are ignored when loading last-used options.
        self.pathlibcutoff:                        str = "20250810-224900"
        self.current_pip_version:                  str = ""
        self.new_pip_version:                      str = ""
        self.venv_dir:                     Path | None = None
        self.venv_python:                  Path | None = None
        self.venv_pip:                     Path | None = None
        self.requirements_file:            Path | None = None
        self.extra_requirements: dict[str, str | None] = {}
        self.extra_requirements_file:              str = "extra_requirements.txt"
        self.pretty_requirements:                  str = ""
        self.download_script_path:         Path | None = None
        self.simultaneous_success:                bool = False
        self.max_checks:                           int = 10  # Maximum number of times to check any repeated process.
        self.check_interval:                       int =  5  # Number of seconds to wait between checks.
        self.rawlog:                              bool = False
        self.pipreqs_available:                   bool = False
        self.univ_defs_path:                      Path = ud.ensure_path(ud.__file__).resolve(strict=True)
        self.univ_defs_sys_path_script:           Path = self.my_dir / "univ_defs_sys_path_script.py"
        self.mydiff_path:                         Path = self.my_dir / "mydiff.py"
        self.myaudit_path:                        Path = self.my_dir / "myaudit.py"
        self.multireplace_path:                   Path = self.my_dir / "multireplace.py"
        self.treeview_path:                       Path = self.my_dir / "treeview.py"
        self.printall_path:                       Path = self.my_dir / "printall.py"
        self.read_files:                    list[Path] = []  # List of files read       by the Python script.
        self.write_files:                   list[Path] = []  # List of files written    by the Python script.
        self.download_urls:                 list[Path] = []  # List of  URLs downloaded by the Python script.
        self.upload_urls:                   list[Path] = []  # List of  URLs uploaded   by the Python script.
        self.current_method_name:                  str = ""  # Name of the current method being executed.
        self.args:           argparse.Namespace | None = None
        self.manual_instructions:                  str = f"""
This program acts as a wrapper around Python to automate the creation of virtual environments and the installation of any required packages. Instead of typing "python3 script.py", you can type "{self.my_name} script.py" to run script.py in a virtual environment which has all the required packages.

It's convenient to add an alias to the shell configuration file so that typing ALIAS anywhere runs this program. This can either be done by running this program with the "--alias ALIAS" command line argument (for example: "python3 {self.my_name}.py --alias {self.my_name}") or by following the manual instructions below. The following steps assume this program is saved as {self.my_name}.py in your home directory (~), but you can adjust the path and filename to match your setup.

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
        self.also_needs: dict[str, list[str]] = {  # Some packages also need other packages to be installed.
            "xarray"  : ["dask", "netcdf4", "h5netcdf"],
            "litellm" : ["tenacity"],
            # NOT PIP PACKAGES: "pyautogui": ["scrot", "python3-tk"]
            # Add more packages and their dependencies here
        }
        # Keep a list of all python standard library modules.
        # Consider switching to stdlib_list package: https://pypi.org/project/stdlib-list/
        # https://chatgpt.com/share/687000fd-be84-8006-a7f4-06af4b1e0eda
        # This list is from the pipreqs repo in file "stdlib", retrieved on 2024-08-15 from here: https://github.com/bndr/pipreqs
        # File "stdlib" is here: https://github.com/bndr/pipreqs/blob/master/pipreqs/stdlib
        self.standard_modules: Final[frozenset[str]] = frozenset({"_abc", "abc", "aifc",
            "_aix_support", "antigravity", "argparse", "array",
            "_ast", "ast", "asynchat", "_asyncio", "asyncio",
            "asyncio.base_events", "asyncio.base_futures",
            "asyncio.base_subprocess", "asyncio.base_tasks",
            "asyncio.constants", "asyncio.coroutines",
            "asyncio.events", "asyncio.exceptions",
            "asyncio.format_helpers", "asyncio.futures",
            "asyncio.locks", "asyncio.log", "asyncio.__main__",
            "asyncio.proactor_events", "asyncio.protocols",
            "asyncio.queues", "asyncio.runners",
            "asyncio.selector_events", "asyncio.sslproto",
            "asyncio.staggered", "asyncio.streams",
            "asyncio.subprocess", "asyncio.tasks", "asyncio.threads",
            "asyncio.transports", "asyncio.trsock",
            "asyncio.unix_events", "asyncio.windows_events",
            "asyncio.windows_utils", "asyncore", "atexit", "audioop",
            "base64", "bdb", "binascii", "binhex", "_bisect",
            "bisect", "_blake2", "_bootlocale", "_bootsubprocess",
            "builtins", "_bz2", "bz2", "calendar", "cgi", "cgitb",
            "chunk", "cmath", "cmd", "code", "_codecs", "codecs",
            "_codecs_cn", "_codecs_hk", "_codecs_iso2022",
            "_codecs_jp", "_codecs_kr", "_codecs_tw", "codeop",
            "_collections", "collections", "_collections_abc",
            "collections.abc", "colorsys", "_compat_pickle",
            "compileall", "_compression", "concurrent",
            "concurrent.futures", "concurrent.futures._base",
            "concurrent.futures.process", "concurrent.futures.thread",
            "configparser", "contextlib", "_contextvars",
            "contextvars", "copy", "copyreg", "cProfile", "_crypt",
            "crypt", "_csv", "csv", "_ctypes", "ctypes",
            "ctypes._aix", "ctypes._endian", "ctypes.macholib",
            "ctypes.macholib.dyld", "ctypes.macholib.dylib",
            "ctypes.macholib.framework", "_ctypes_test",
            "ctypes.test", "ctypes.test.__main__",
            "ctypes.test.test_anon",
            "ctypes.test.test_array_in_pointer",
            "ctypes.test.test_arrays",
            "ctypes.test.test_as_parameter",
            "ctypes.test.test_bitfields", "ctypes.test.test_buffers",
            "ctypes.test.test_bytes", "ctypes.test.test_byteswap",
            "ctypes.test.test_callbacks", "ctypes.test.test_cast",
            "ctypes.test.test_cfuncs", "ctypes.test.test_checkretval",
            "ctypes.test.test_delattr", "ctypes.test.test_errno",
            "ctypes.test.test_find", "ctypes.test.test_frombuffer",
            "ctypes.test.test_funcptr", "ctypes.test.test_functions",
            "ctypes.test.test_incomplete", "ctypes.test.test_init",
            "ctypes.test.test_internals", "ctypes.test.test_keeprefs",
            "ctypes.test.test_libc", "ctypes.test.test_loading",
            "ctypes.test.test_macholib",
            "ctypes.test.test_memfunctions",
            "ctypes.test.test_numbers", "ctypes.test.test_objects",
            "ctypes.test.test_parameters", "ctypes.test.test_pep3118",
            "ctypes.test.test_pickling", "ctypes.test.test_pointers",
            "ctypes.test.test_prototypes",
            "ctypes.test.test_python_api",
            "ctypes.test.test_random_things",
            "ctypes.test.test_refcounts", "ctypes.test.test_repr",
            "ctypes.test.test_returnfuncptrs",
            "ctypes.test.test_simplesubclasses",
            "ctypes.test.test_sizes", "ctypes.test.test_slicing",
            "ctypes.test.test_stringptr", "ctypes.test.test_strings",
            "ctypes.test.test_struct_fields",
            "ctypes.test.test_structures",
            "ctypes.test.test_unaligned_structures",
            "ctypes.test.test_unicode", "ctypes.test.test_values",
            "ctypes.test.test_varsize_struct",
            "ctypes.test.test_win32", "ctypes.test.test_wintypes",
            "ctypes.util", "ctypes.wintypes", "_curses", "curses",
            "curses.ascii", "curses.has_key", "_curses_panel",
            "curses.panel", "curses.textpad", "dataclasses",
            "_datetime", "datetime", "_dbm", "dbm", "dbm.dumb",
            "dbm.gnu", "dbm.ndbm", "_decimal", "decimal", "difflib",
            "dis", "distutils", "distutils.archive_util",
            "distutils.bcppcompiler", "distutils.ccompiler",
            "distutils.cmd", "distutils.command",
            "distutils.command.bdist", "distutils.command.bdist_dumb",
            "distutils.command.bdist_msi",
            "distutils.command.bdist_packager",
            "distutils.command.bdist_rpm",
            "distutils.command.bdist_wininst",
            "distutils.command.build", "distutils.command.build_clib",
            "distutils.command.build_ext",
            "distutils.command.build_py",
            "distutils.command.build_scripts",
            "distutils.command.check", "distutils.command.clean",
            "distutils.command.config", "distutils.command.install",
            "distutils.command.install_data",
            "distutils.command.install_egg_info",
            "distutils.command.install_headers",
            "distutils.command.install_lib",
            "distutils.command.install_scripts",
            "distutils.command.register", "distutils.command.sdist",
            "distutils.command.upload", "distutils.config",
            "distutils.core", "distutils.cygwinccompiler",
            "distutils.debug", "distutils.dep_util",
            "distutils.dir_util", "distutils.dist",
            "distutils.errors", "distutils.extension",
            "distutils.fancy_getopt", "distutils.filelist",
            "distutils.file_util", "distutils.log",
            "distutils.msvc9compiler", "distutils._msvccompiler",
            "distutils.msvccompiler", "distutils.spawn",
            "distutils.sysconfig", "distutils.tests",
            "distutils.tests.support",
            "distutils.tests.test_archive_util",
            "distutils.tests.test_bdist",
            "distutils.tests.test_bdist_dumb",
            "distutils.tests.test_bdist_msi",
            "distutils.tests.test_bdist_rpm",
            "distutils.tests.test_bdist_wininst",
            "distutils.tests.test_build",
            "distutils.tests.test_build_clib",
            "distutils.tests.test_build_ext",
            "distutils.tests.test_build_py",
            "distutils.tests.test_build_scripts",
            "distutils.tests.test_check",
            "distutils.tests.test_clean", "distutils.tests.test_cmd",
            "distutils.tests.test_config",
            "distutils.tests.test_config_cmd",
            "distutils.tests.test_core",
            "distutils.tests.test_cygwinccompiler",
            "distutils.tests.test_dep_util",
            "distutils.tests.test_dir_util",
            "distutils.tests.test_dist",
            "distutils.tests.test_extension",
            "distutils.tests.test_filelist",
            "distutils.tests.test_file_util",
            "distutils.tests.test_install",
            "distutils.tests.test_install_data",
            "distutils.tests.test_install_headers",
            "distutils.tests.test_install_lib",
            "distutils.tests.test_install_scripts",
            "distutils.tests.test_log",
            "distutils.tests.test_msvc9compiler",
            "distutils.tests.test_msvccompiler",
            "distutils.tests.test_register",
            "distutils.tests.test_sdist",
            "distutils.tests.test_spawn",
            "distutils.tests.test_sysconfig",
            "distutils.tests.test_text_file",
            "distutils.tests.test_unixccompiler",
            "distutils.tests.test_upload",
            "distutils.tests.test_util",
            "distutils.tests.test_version",
            "distutils.tests.test_versionpredicate",
            "distutils.text_file", "distutils.unixccompiler",
            "distutils.util", "distutils.version",
            "distutils.versionpredicate", "doctest", "_dummy_thread",
            "dummy_threading", "_elementtree", "email",
            "email.base64mime", "email.charset",
            "email.contentmanager", "email._encoded_words",
            "email.encoders", "email.errors", "email.feedparser",
            "email.generator", "email.header", "email.headerregistry",
            "email._header_value_parser", "email.iterators",
            "email.message", "email.mime", "email.mime.application",
            "email.mime.audio", "email.mime.base", "email.mime.image",
            "email.mime.message", "email.mime.multipart",
            "email.mime.nonmultipart", "email.mime.text",
            "email._parseaddr", "email.parser", "email.policy",
            "email._policybase", "email.quoprimime", "email.utils",
            "encodings", "encodings.aliases", "encodings.ascii",
            "encodings.base64_codec", "encodings.big5",
            "encodings.big5hkscs", "encodings.bz2_codec",
            "encodings.charmap", "encodings.cp037",
            "encodings.cp1006", "encodings.cp1026",
            "encodings.cp1125", "encodings.cp1140",
            "encodings.cp1250", "encodings.cp1251",
            "encodings.cp1252", "encodings.cp1253",
            "encodings.cp1254", "encodings.cp1255",
            "encodings.cp1256", "encodings.cp1257",
            "encodings.cp1258", "encodings.cp273", "encodings.cp424",
            "encodings.cp437", "encodings.cp500", "encodings.cp720",
            "encodings.cp737", "encodings.cp775", "encodings.cp850",
            "encodings.cp852", "encodings.cp855", "encodings.cp856",
            "encodings.cp857", "encodings.cp858", "encodings.cp860",
            "encodings.cp861", "encodings.cp862", "encodings.cp863",
            "encodings.cp864", "encodings.cp865", "encodings.cp866",
            "encodings.cp869", "encodings.cp874", "encodings.cp875",
            "encodings.cp932", "encodings.cp949", "encodings.cp950",
            "encodings.euc_jis_2004", "encodings.euc_jisx0213",
            "encodings.euc_jp", "encodings.euc_kr",
            "encodings.gb18030", "encodings.gb2312", "encodings.gbk",
            "encodings.hex_codec", "encodings.hp_roman8",
            "encodings.hz", "encodings.idna", "encodings.iso2022_jp",
            "encodings.iso2022_jp_1", "encodings.iso2022_jp_2",
            "encodings.iso2022_jp_2004", "encodings.iso2022_jp_3",
            "encodings.iso2022_jp_ext", "encodings.iso2022_kr",
            "encodings.iso8859_1", "encodings.iso8859_10",
            "encodings.iso8859_11", "encodings.iso8859_13",
            "encodings.iso8859_14", "encodings.iso8859_15",
            "encodings.iso8859_16", "encodings.iso8859_2",
            "encodings.iso8859_3", "encodings.iso8859_4",
            "encodings.iso8859_5", "encodings.iso8859_6",
            "encodings.iso8859_7", "encodings.iso8859_8",
            "encodings.iso8859_9", "encodings.johab",
            "encodings.koi8_r", "encodings.koi8_t",
            "encodings.koi8_u", "encodings.kz1048",
            "encodings.latin_1", "encodings.mac_arabic",
            "encodings.mac_centeuro", "encodings.mac_croatian",
            "encodings.mac_cyrillic", "encodings.mac_farsi",
            "encodings.mac_greek", "encodings.mac_iceland",
            "encodings.mac_latin2", "encodings.mac_roman",
            "encodings.mac_romanian", "encodings.mac_turkish",
            "encodings.mbcs", "encodings.oem", "encodings.palmos",
            "encodings.ptcp154", "encodings.punycode",
            "encodings.quopri_codec", "encodings.raw_unicode_escape",
            "encodings.rot_13", "encodings.shift_jis",
            "encodings.shift_jis_2004", "encodings.shift_jisx0213",
            "encodings.tis_620", "encodings.undefined",
            "encodings.unicode_escape", "encodings.utf_16",
            "encodings.utf_16_be", "encodings.utf_16_le",
            "encodings.utf_32", "encodings.utf_32_be",
            "encodings.utf_32_le", "encodings.utf_7",
            "encodings.utf_8", "encodings.utf_8_sig",
            "encodings.uu_codec", "encodings.zlib_codec", "ensurepip",
            "ensurepip._bundled", "ensurepip.__main__",
            "ensurepip._uninstall", "enum", "errno", "faulthandler",
            "fcntl", "filecmp", "fileinput", "fnmatch", "formatter",
            "fractions", "_frozen_importlib",
            "_frozen_importlib_external", "ftplib", "_functools",
            "functools", "__future__", "gc", "_gdbm", "genericpath",
            "getopt", "getpass", "gettext", "glob", "graphlib", "grp",
            "gzip", "_hashlib", "hashlib", "_heapq", "heapq", "hmac",
            "html", "html.entities", "html.parser", "http",
            "http.client", "http.cookiejar", "http.cookies",
            "http.server", "idlelib", "idlelib.autocomplete",
            "idlelib.autocomplete_w", "idlelib.autoexpand",
            "idlelib.browser", "idlelib.calltip", "idlelib.calltip_w",
            "idlelib.codecontext", "idlelib.colorizer",
            "idlelib.config", "idlelib.configdialog",
            "idlelib.config_key", "idlelib.debugger",
            "idlelib.debugger_r", "idlelib.debugobj",
            "idlelib.debugobj_r", "idlelib.delegator",
            "idlelib.dynoption", "idlelib.editor", "idlelib.filelist",
            "idlelib.format", "idlelib.grep", "idlelib.help",
            "idlelib.help_about", "idlelib.history",
            "idlelib.hyperparser", "idlelib.idle",
            "idlelib.idle_test", "idlelib.idle_test.htest",
            "idlelib.idle_test.mock_idle",
            "idlelib.idle_test.mock_tk", "idlelib.idle_test.template",
            "idlelib.idle_test.test_autocomplete",
            "idlelib.idle_test.test_autocomplete_w",
            "idlelib.idle_test.test_autoexpand",
            "idlelib.idle_test.test_browser",
            "idlelib.idle_test.test_calltip",
            "idlelib.idle_test.test_calltip_w",
            "idlelib.idle_test.test_codecontext",
            "idlelib.idle_test.test_colorizer",
            "idlelib.idle_test.test_config",
            "idlelib.idle_test.test_configdialog",
            "idlelib.idle_test.test_config_key",
            "idlelib.idle_test.test_debugger",
            "idlelib.idle_test.test_debugger_r",
            "idlelib.idle_test.test_debugobj",
            "idlelib.idle_test.test_debugobj_r",
            "idlelib.idle_test.test_delegator",
            "idlelib.idle_test.test_editmenu",
            "idlelib.idle_test.test_editor",
            "idlelib.idle_test.test_filelist",
            "idlelib.idle_test.test_format",
            "idlelib.idle_test.test_grep",
            "idlelib.idle_test.test_help",
            "idlelib.idle_test.test_help_about",
            "idlelib.idle_test.test_history",
            "idlelib.idle_test.test_hyperparser",
            "idlelib.idle_test.test_iomenu",
            "idlelib.idle_test.test_macosx",
            "idlelib.idle_test.test_mainmenu",
            "idlelib.idle_test.test_multicall",
            "idlelib.idle_test.test_outwin",
            "idlelib.idle_test.test_parenmatch",
            "idlelib.idle_test.test_pathbrowser",
            "idlelib.idle_test.test_percolator",
            "idlelib.idle_test.test_pyparse",
            "idlelib.idle_test.test_pyshell",
            "idlelib.idle_test.test_query",
            "idlelib.idle_test.test_redirector",
            "idlelib.idle_test.test_replace",
            "idlelib.idle_test.test_rpc",
            "idlelib.idle_test.test_run",
            "idlelib.idle_test.test_runscript",
            "idlelib.idle_test.test_scrolledlist",
            "idlelib.idle_test.test_search",
            "idlelib.idle_test.test_searchbase",
            "idlelib.idle_test.test_searchengine",
            "idlelib.idle_test.test_sidebar",
            "idlelib.idle_test.test_squeezer",
            "idlelib.idle_test.test_stackviewer",
            "idlelib.idle_test.test_statusbar",
            "idlelib.idle_test.test_text",
            "idlelib.idle_test.test_textview",
            "idlelib.idle_test.test_tooltip",
            "idlelib.idle_test.test_tree",
            "idlelib.idle_test.test_undo",
            "idlelib.idle_test.test_warning",
            "idlelib.idle_test.test_window",
            "idlelib.idle_test.test_zoomheight", "idlelib.iomenu",
            "idlelib.macosx", "idlelib.__main__", "idlelib.mainmenu",
            "idlelib.multicall", "idlelib.outwin",
            "idlelib.parenmatch", "idlelib.pathbrowser",
            "idlelib.percolator", "idlelib.pyparse",
            "idlelib.pyshell", "idlelib.query", "idlelib.redirector",
            "idlelib.replace", "idlelib.rpc", "idlelib.run",
            "idlelib.runscript", "idlelib.scrolledlist",
            "idlelib.search", "idlelib.searchbase",
            "idlelib.searchengine", "idlelib.sidebar",
            "idlelib.squeezer", "idlelib.stackviewer",
            "idlelib.statusbar", "idlelib.textview",
            "idlelib.tooltip", "idlelib.tree", "idlelib.undo",
            "idlelib.window", "idlelib.zoomheight", "idlelib.zzdummy",
            "imaplib", "imghdr", "_imp", "imp", "importlib",
            "importlib.abc", "importlib._bootstrap",
            "importlib._bootstrap_external", "importlib._common",
            "importlib.machinery", "importlib.metadata",
            "importlib.resources", "importlib.util", "inspect", "_io",
            "io", "ipaddress", "itertools", "_json", "json",
            "json.decoder", "json.encoder", "json.scanner",
            "json.tool", "keyword", "lib2to3", "lib2to3.btm_matcher",
            "lib2to3.btm_utils", "lib2to3.fixer_base",
            "lib2to3.fixer_util", "lib2to3.fixes",
            "lib2to3.fixes.fix_apply", "lib2to3.fixes.fix_asserts",
            "lib2to3.fixes.fix_basestring",
            "lib2to3.fixes.fix_buffer", "lib2to3.fixes.fix_dict",
            "lib2to3.fixes.fix_except", "lib2to3.fixes.fix_exec",
            "lib2to3.fixes.fix_execfile",
            "lib2to3.fixes.fix_exitfunc", "lib2to3.fixes.fix_filter",
            "lib2to3.fixes.fix_funcattrs", "lib2to3.fixes.fix_future",
            "lib2to3.fixes.fix_getcwdu", "lib2to3.fixes.fix_has_key",
            "lib2to3.fixes.fix_idioms", "lib2to3.fixes.fix_import",
            "lib2to3.fixes.fix_imports", "lib2to3.fixes.fix_imports2",
            "lib2to3.fixes.fix_input", "lib2to3.fixes.fix_intern",
            "lib2to3.fixes.fix_isinstance",
            "lib2to3.fixes.fix_itertools",
            "lib2to3.fixes.fix_itertools_imports",
            "lib2to3.fixes.fix_long", "lib2to3.fixes.fix_map",
            "lib2to3.fixes.fix_metaclass",
            "lib2to3.fixes.fix_methodattrs", "lib2to3.fixes.fix_ne",
            "lib2to3.fixes.fix_next", "lib2to3.fixes.fix_nonzero",
            "lib2to3.fixes.fix_numliterals",
            "lib2to3.fixes.fix_operator", "lib2to3.fixes.fix_paren",
            "lib2to3.fixes.fix_print", "lib2to3.fixes.fix_raise",
            "lib2to3.fixes.fix_raw_input", "lib2to3.fixes.fix_reduce",
            "lib2to3.fixes.fix_reload", "lib2to3.fixes.fix_renames",
            "lib2to3.fixes.fix_repr", "lib2to3.fixes.fix_set_literal",
            "lib2to3.fixes.fix_standarderror",
            "lib2to3.fixes.fix_sys_exc", "lib2to3.fixes.fix_throw",
            "lib2to3.fixes.fix_tuple_params",
            "lib2to3.fixes.fix_types", "lib2to3.fixes.fix_unicode",
            "lib2to3.fixes.fix_urllib", "lib2to3.fixes.fix_ws_comma",
            "lib2to3.fixes.fix_xrange",
            "lib2to3.fixes.fix_xreadlines", "lib2to3.fixes.fix_zip",
            "lib2to3.main", "lib2to3.__main__", "lib2to3.patcomp",
            "lib2to3.pgen2", "lib2to3.pgen2.conv",
            "lib2to3.pgen2.driver", "lib2to3.pgen2.grammar",
            "lib2to3.pgen2.literals", "lib2to3.pgen2.parse",
            "lib2to3.pgen2.pgen", "lib2to3.pgen2.token",
            "lib2to3.pgen2.tokenize", "lib2to3.pygram",
            "lib2to3.pytree", "lib2to3.refactor", "lib2to3.tests",
            "lib2to3.tests.data.bom", "lib2to3.tests.data.crlf",
            "lib2to3.tests.data.different_encoding",
            "lib2to3.tests.data.false_encoding",
            "lib2to3.tests.data.fixers.bad_order",
            "lib2to3.tests.data.fixers.myfixes",
            "lib2to3.tests.data.fixers.myfixes.fix_explicit",
            "lib2to3.tests.data.fixers.myfixes.fix_first",
            "lib2to3.tests.data.fixers.myfixes.fix_last",
            "lib2to3.tests.data.fixers.myfixes.fix_parrot",
            "lib2to3.tests.data.fixers.myfixes.fix_preorder",
            "lib2to3.tests.data.fixers.no_fixer_cls",
            "lib2to3.tests.data.fixers.parrot_example",
            "lib2to3.tests.data.infinite_recursion",
            "lib2to3.tests.data.py2_test_grammar",
            "lib2to3.tests.data.py3_test_grammar",
            "lib2to3.tests.__main__",
            "lib2to3.tests.pytree_idempotency",
            "lib2to3.tests.support", "lib2to3.tests.test_all_fixers",
            "lib2to3.tests.test_fixers", "lib2to3.tests.test_main",
            "lib2to3.tests.test_parser", "lib2to3.tests.test_pytree",
            "lib2to3.tests.test_refactor", "lib2to3.tests.test_util",
            "lib.libpython3", "linecache", "_locale", "locale",
            "logging", "logging.config", "logging.handlers",
            "_lsprof", "_lzma", "lzma", "mailbox", "mailcap",
            "__main__", "_markupbase", "marshal", "math", "_md5",
            "mimetypes", "mmap", "modulefinder", "msilib", "msvcrt",
            "_multibytecodec", "_multiprocessing", "multiprocessing",
            "multiprocessing.connection", "multiprocessing.context",
            "multiprocessing.dummy",
            "multiprocessing.dummy.connection",
            "multiprocessing.forkserver", "multiprocessing.heap",
            "multiprocessing.managers", "multiprocessing.pool",
            "multiprocessing.popen_fork",
            "multiprocessing.popen_forkserver",
            "multiprocessing.popen_spawn_posix",
            "multiprocessing.popen_spawn_win32",
            "multiprocessing.process", "multiprocessing.queues",
            "multiprocessing.reduction",
            "multiprocessing.resource_sharer",
            "multiprocessing.resource_tracker",
            "multiprocessing.sharedctypes",
            "multiprocessing.shared_memory", "multiprocessing.spawn",
            "multiprocessing.synchronize", "multiprocessing.util",
            "netrc", "nis", "nntplib", "ntpath", "nturl2path",
            "numbers", "_opcode", "opcode", "_operator", "operator",
            "optparse", "os", "os.path", "ossaudiodev",
            "_osx_support", "parser", "pathlib", "pdb",
            "__phello__.foo", "_pickle", "pickle", "pickletools",
            "pipes", "pkgutil", "platform", "plistlib", "poplib",
            "posix", "posixpath", "_posixshmem", "_posixsubprocess",
            "pprint", "profile", "pstats", "pty", "pwd", "_py_abc",
            "pyclbr", "py_compile", "_pydecimal", "pydoc",
            "pydoc_data", "pydoc_data.topics", "pyexpat", "_pyio",
            "_queue", "queue", "quopri", "_random", "random", "re",
            "readline", "reprlib", "resource", "rlcompleter", "runpy",
            "sched", "secrets", "select", "selectors", "_sha1",
            "_sha256", "_sha3", "_sha512", "shelve", "shlex",
            "shutil", "_signal", "signal", "site", "_sitebuiltins",
            "smtpd", "smtplib", "sndhdr", "_socket", "socket",
            "socketserver", "spwd", "_sqlite3", "sqlite3",
            "sqlite3.dbapi2", "sqlite3.dump", "sqlite3.test",
            "sqlite3.test.backup", "sqlite3.test.dbapi",
            "sqlite3.test.dump", "sqlite3.test.factory",
            "sqlite3.test.hooks", "sqlite3.test.regression",
            "sqlite3.test.transactions", "sqlite3.test.types",
            "sqlite3.test.userfunctions", "_sre", "sre_compile",
            "sre_constants", "sre_parse", "_ssl", "ssl", "_stat",
            "stat", "_statistics", "statistics", "_string", "string",
            "stringprep", "_strptime", "_struct", "struct",
            "subprocess", "sunau", "symbol", "_symtable", "symtable",
            "sys", "sysconfig",
            "_sysconfigdata_x86_64_conda_cos6_linux_gnu",
            "_sysconfigdata_x86_64_conda_linux_gnu", "syslog",
            "tabnanny", "tarfile", "telnetlib", "tempfile", "termios",
            "test", "test.ann_module", "test.ann_module2",
            "test.ann_module3", "test.audiotests", "test.autotest",
            "test.bad_coding", "test.bad_coding2", "test.bad_getattr",
            "test.bad_getattr2", "test.bad_getattr3",
            "test.badsyntax_3131", "test.badsyntax_future10",
            "test.badsyntax_future3", "test.badsyntax_future4",
            "test.badsyntax_future5", "test.badsyntax_future6",
            "test.badsyntax_future7", "test.badsyntax_future8",
            "test.badsyntax_future9", "test.badsyntax_pep3120",
            "test.bisect_cmd", "_testbuffer", "test.bytecode_helper",
            "_testcapi", "test.coding20731", "test.curses_tests",
            "test.dataclass_module_1", "test.dataclass_module_1_str",
            "test.dataclass_module_2", "test.dataclass_module_2_str",
            "test.datetimetester", "test.dis_module",
            "test.doctest_aliases", "test.double_const",
            "test.dtracedata.call_stack", "test.dtracedata.gc",
            "test.dtracedata.instance", "test.dtracedata.line",
            "test.eintrdata.eintr_tester", "test.encoded_modules",
            "test.encoded_modules.module_iso_8859_1",
            "test.encoded_modules.module_koi8_r", "test.final_a",
            "test.final_b", "test.fork_wait", "test.future_test1",
            "test.future_test2", "test.gdb_sample",
            "test.good_getattr", "test.imp_dummy",
            "_testimportmultiple", "test.inspect_fodder",
            "test.inspect_fodder2", "_testinternalcapi",
            "test.libregrtest", "test.libregrtest.cmdline",
            "test.libregrtest.main", "test.libregrtest.pgo",
            "test.libregrtest.refleak", "test.libregrtest.runtest",
            "test.libregrtest.runtest_mp",
            "test.libregrtest.save_env", "test.libregrtest.setup",
            "test.libregrtest.utils", "test.libregrtest.win_utils",
            "test.list_tests", "test.lock_tests", "test.__main__",
            "test.make_ssl_certs", "test.mapping_tests",
            "test.memory_watchdog", "test.mock_socket",
            "test.mod_generics_cache", "test.mp_fork_bomb",
            "test.mp_preload", "test.multibytecodec_support",
            "_testmultiphase", "test.outstanding_bugs",
            "test.pickletester", "test.profilee", "test.pyclbr_input",
            "test.pydocfodder", "test.pydoc_mod", "test.pythoninfo",
            "test.regrtest", "test.relimport", "test.reperf",
            "test.re_tests", "test.sample_doctest",
            "test.sample_doctest_no_docstrings",
            "test.sample_doctest_no_doctests", "test.seq_tests",
            "test.signalinterproctester", "test.sortperf",
            "test.ssl_servers", "test.ssltests", "test.string_tests",
            "test.subprocessdata.fd_status",
            "test.subprocessdata.input_reader",
            "test.subprocessdata.qcat", "test.subprocessdata.qgrep",
            "test.subprocessdata.sigchild_ignore", "test.support",
            "test.support.bytecode_helper",
            "test.support.hashlib_helper",
            "test.support.logging_helper",
            "test.support.script_helper",
            "test.support.socket_helper", "test.support.testresult",
            "test.test_abc", "test.test_abstract_numbers",
            "test.test_aifc", "test.test___all__",
            "test.test_argparse", "test.test_array",
            "test.test_asdl_parser", "test.test_ast",
            "test.test_asyncgen", "test.test_asynchat",
            "test.test_asyncio", "test.test_asyncio.echo",
            "test.test_asyncio.echo2", "test.test_asyncio.echo3",
            "test.test_asyncio.functional",
            "test.test_asyncio.__main__",
            "test.test_asyncio.test_base_events",
            "test.test_asyncio.test_buffered_proto",
            "test.test_asyncio.test_context",
            "test.test_asyncio.test_events",
            "test.test_asyncio.test_futures",
            "test.test_asyncio.test_locks",
            "test.test_asyncio.test_pep492",
            "test.test_asyncio.test_proactor_events",
            "test.test_asyncio.test_protocols",
            "test.test_asyncio.test_queues",
            "test.test_asyncio.test_runners",
            "test.test_asyncio.test_selector_events",
            "test.test_asyncio.test_sendfile",
            "test.test_asyncio.test_server",
            "test.test_asyncio.test_sock_lowlevel",
            "test.test_asyncio.test_sslproto",
            "test.test_asyncio.test_streams",
            "test.test_asyncio.test_subprocess",
            "test.test_asyncio.test_tasks",
            "test.test_asyncio.test_transports",
            "test.test_asyncio.test_unix_events",
            "test.test_asyncio.test_windows_events",
            "test.test_asyncio.test_windows_utils",
            "test.test_asyncio.utils", "test.test_asyncore",
            "test.test_atexit", "test.test_audioop",
            "test.test_audit", "test.test_augassign",
            "test.test_base64", "test.test_baseexception",
            "test.test_bdb", "test.test_bigaddrspace",
            "test.test_bigmem", "test.test_binascii",
            "test.test_binhex", "test.test_binop", "test.test_bisect",
            "test.test_bool", "test.test_buffer", "test.test_bufio",
            "test.test_builtin", "test.test_bytes", "test.test_bz2",
            "test.test_calendar", "test.test_call", "test.test_capi",
            "test.test_cgi", "test.test_cgitb",
            "test.test_charmapcodec", "test.test_class",
            "test.test_clinic", "test.test_c_locale_coercion",
            "test.test_cmath", "test.test_cmd", "test.test_cmd_line",
            "test.test_cmd_line_script", "test.test_code",
            "test.testcodec", "test.test_codeccallbacks",
            "test.test_codecencodings_cn",
            "test.test_codecencodings_hk",
            "test.test_codecencodings_iso2022",
            "test.test_codecencodings_jp",
            "test.test_codecencodings_kr",
            "test.test_codecencodings_tw", "test.test_codecmaps_cn",
            "test.test_codecmaps_hk", "test.test_codecmaps_jp",
            "test.test_codecmaps_kr", "test.test_codecmaps_tw",
            "test.test_codecs", "test.test_code_module",
            "test.test_codeop", "test.test_collections",
            "test.test_colorsys", "test.test_compare",
            "test.test_compile", "test.test_compileall",
            "test.test_complex", "test.test_concurrent_futures",
            "test.test_configparser", "test.test_contains",
            "test.test_context", "test.test_contextlib",
            "test.test_contextlib_async", "test.test_copy",
            "test.test_copyreg", "test.test_coroutines",
            "test.test_cprofile", "test.test_crashers",
            "test.test_crypt", "test.test_csv", "test.test_ctypes",
            "test.test_curses", "test.test_dataclasses",
            "test.test_datetime", "test.test_dbm",
            "test.test_dbm_dumb", "test.test_dbm_gnu",
            "test.test_dbm_ndbm", "test.test_decimal",
            "test.test_decorators", "test.test_defaultdict",
            "test.test_deque", "test.test_descr",
            "test.test_descrtut", "test.test_devpoll",
            "test.test_dict", "test.test_dictcomps",
            "test.test_dict_version", "test.test_dictviews",
            "test.test_difflib", "test.test_dis",
            "test.test_distutils", "test.test_doctest",
            "test.test_doctest2", "test.test_docxmlrpc",
            "test.test_dtrace", "test.test_dummy_thread",
            "test.test_dummy_threading", "test.test_dynamic",
            "test.test_dynamicclassattribute", "test.test_eintr",
            "test.test_email", "test.test_email.__main__",
            "test.test_email.test_asian_codecs",
            "test.test_email.test_contentmanager",
            "test.test_email.test_defect_handling",
            "test.test_email.test_email",
            "test.test_email.test__encoded_words",
            "test.test_email.test_generator",
            "test.test_email.test_headerregistry",
            "test.test_email.test__header_value_parser",
            "test.test_email.test_inversion",
            "test.test_email.test_message",
            "test.test_email.test_parser",
            "test.test_email.test_pickleable",
            "test.test_email.test_policy",
            "test.test_email.test_utils",
            "test.test_email.torture_test", "test.test_embed",
            "test.test_ensurepip", "test.test_enum",
            "test.test_enumerate", "test.test_eof", "test.test_epoll",
            "test.test_errno", "test.test_exception_hierarchy",
            "test.test_exceptions", "test.test_exception_variations",
            "test.test_extcall", "test.test_faulthandler",
            "test.test_fcntl", "test.test_file", "test.test_filecmp",
            "test.test_file_eintr", "test.test_fileinput",
            "test.test_fileio", "test.test_finalization",
            "test.test_float", "test.test_flufl", "test.test_fnmatch",
            "test.test_fork1", "test.test_format",
            "test.test_fractions", "test.test_frame",
            "test.test_frozen", "test.test_fstring",
            "test.test_ftplib", "test.test_funcattrs",
            "test.test_functools", "test.test___future__",
            "test.test_future", "test.test_future3",
            "test.test_future4", "test.test_future5", "test.test_gc",
            "test.test_gdb", "test.test_generators",
            "test.test_generator_stop", "test.test_genericclass",
            "test.test_genericpath", "test.test_genexps",
            "test.test_getargs2", "test.test_getopt",
            "test.test_getpass", "test.test_gettext",
            "test.test_glob", "test.test_global", "test.test_grammar",
            "test.test_grp", "test.test_gzip", "test.test_hash",
            "test.test_hashlib", "test.test_heapq", "test.test_hmac",
            "test.test_html", "test.test_htmlparser",
            "test.test_http_cookiejar", "test.test_http_cookies",
            "test.test_httplib", "test.test_httpservers",
            "test.test_idle", "test.test_imaplib", "test.test_imghdr",
            "test.test_imp", "test.test_import",
            "test.test_import.data.circular_imports.basic",
            "test.test_import.data.circular_imports.basic2",
            "test.test_import.data.circular_imports.binding",
            "test.test_import.data.circular_imports.binding2",
            "test.test_import.data.circular_imports.from_cycle1",
            "test.test_import.data.circular_imports.from_cycle2",
            "test.test_import.data.circular_imports.indirect",
            "test.test_import.data.circular_imports.rebinding",
            "test.test_import.data.circular_imports.rebinding2",
            "test.test_import.data.circular_imports.source",
            "test.test_import.data.circular_imports.subpackage",
            "test.test_import.data.circular_imports.subpkg.subpackage2",
            "test.test_import.data.circular_imports.subpkg.util",
            "test.test_import.data.circular_imports.use",
            "test.test_import.data.circular_imports.util",
            "test.test_import.data.package",
            "test.test_import.data.package2.submodule1",
            "test.test_import.data.package2.submodule2",
            "test.test_import.data.package.submodule",
            "test.test_importlib", "test.test_importlib.abc",
            "test.test_importlib.builtin",
            "test.test_importlib.builtin.__main__",
            "test.test_importlib.builtin.test_finder",
            "test.test_importlib.builtin.test_loader",
            "test.test_importlib.data", "test.test_importlib.data01",
            "test.test_importlib.data01.subdirectory",
            "test.test_importlib.data02",
            "test.test_importlib.data02.one",
            "test.test_importlib.data02.two",
            "test.test_importlib.data03",
            "test.test_importlib.data03.namespace.portion1",
            "test.test_importlib.data03.namespace.portion2",
            "test.test_importlib.extension",
            "test.test_importlib.extension.__main__",
            "test.test_importlib.extension.test_case_sensitivity",
            "test.test_importlib.extension.test_finder",
            "test.test_importlib.extension.test_loader",
            "test.test_importlib.extension.test_path_hook",
            "test.test_importlib.fixtures",
            "test.test_importlib.frozen",
            "test.test_importlib.frozen.__main__",
            "test.test_importlib.frozen.test_finder",
            "test.test_importlib.frozen.test_loader",
            "test.test_importlib.import_",
            "test.test_importlib.import_.__main__",
            "test.test_importlib.import_.test_api",
            "test.test_importlib.import_.test_caching",
            "test.test_importlib.import_.test_fromlist",
            "test.test_importlib.import_.test___loader__",
            "test.test_importlib.import_.test_meta_path",
            "test.test_importlib.import_.test___package__",
            "test.test_importlib.import_.test_packages",
            "test.test_importlib.import_.test_path",
            "test.test_importlib.import_.test_relative_imports",
            "test.test_importlib.__main__",
            "test.test_importlib.namespace_pkgs.both_portions.foo.one",
            "test.test_importlib.namespace_pkgs.both_portions.foo.two",
            "test.test_importlib.namespace_pkgs.module_and_namespace_package.a_test",
            "test.test_importlib.namespace_pkgs.not_a_namespace_pkg.foo",
            "test.test_importlib.namespace_pkgs.not_a_namespace_pkg.foo.one",
            "test.test_importlib.namespace_pkgs.portion1.foo.one",
            "test.test_importlib.namespace_pkgs.portion2.foo.two",
            "test.test_importlib.namespace_pkgs.project1.parent.child.one",
            "test.test_importlib.namespace_pkgs.project2.parent.child.two",
            "test.test_importlib.namespace_pkgs.project3.parent.child.three",
            "test.test_importlib.source",
            "test.test_importlib.source.__main__",
            "test.test_importlib.source.test_case_sensitivity",
            "test.test_importlib.source.test_file_loader",
            "test.test_importlib.source.test_finder",
            "test.test_importlib.source.test_path_hook",
            "test.test_importlib.source.test_source_encoding",
            "test.test_importlib.test_abc",
            "test.test_importlib.test_api",
            "test.test_importlib.test_lazy",
            "test.test_importlib.test_locks",
            "test.test_importlib.test_main",
            "test.test_importlib.test_metadata_api",
            "test.test_importlib.test_namespace_pkgs",
            "test.test_importlib.test_open",
            "test.test_importlib.test_path",
            "test.test_importlib.test_read",
            "test.test_importlib.test_resource",
            "test.test_importlib.test_spec",
            "test.test_importlib.test_util",
            "test.test_importlib.test_windows",
            "test.test_importlib.test_zip",
            "test.test_importlib.util",
            "test.test_importlib.zipdata01",
            "test.test_importlib.zipdata02",
            "test.test_import.__main__", "test.test_index",
            "test.test_inspect", "test.test_int",
            "test.test_int_literal", "test.test_io",
            "test.test_ioctl", "test.test_ipaddress",
            "test.test_isinstance", "test.test_iter",
            "test.test_iterlen", "test.test_itertools",
            "test.test_json", "test.test_json.__main__",
            "test.test_json.test_decode",
            "test.test_json.test_default", "test.test_json.test_dump",
            "test.test_json.test_encode_basestring_ascii",
            "test.test_json.test_enum", "test.test_json.test_fail",
            "test.test_json.test_float", "test.test_json.test_indent",
            "test.test_json.test_pass1", "test.test_json.test_pass2",
            "test.test_json.test_pass3",
            "test.test_json.test_recursion",
            "test.test_json.test_scanstring",
            "test.test_json.test_separators",
            "test.test_json.test_speedups",
            "test.test_json.test_tool", "test.test_json.test_unicode",
            "test.test_keyword", "test.test_keywordonlyarg",
            "test.test_kqueue", "test.test_largefile",
            "test.test_lib2to3", "test.test_linecache",
            "test.test_list", "test.test_listcomps",
            "test.test_lltrace", "test.test__locale",
            "test.test_locale", "test.test_logging", "test.test_long",
            "test.test_longexp", "test.test_lzma",
            "test.test_mailbox", "test.test_mailcap",
            "test.test_marshal", "test.test_math",
            "test.test_memoryio", "test.test_memoryview",
            "test.test_metaclass", "test.test_mimetypes",
            "test.test_minidom", "test.test_mmap", "test.test_module",
            "test.test_modulefinder", "test.test_msilib",
            "test.test_multibytecodec", "test._test_multiprocessing",
            "test.test_multiprocessing_fork",
            "test.test_multiprocessing_forkserver",
            "test.test_multiprocessing_main_handling",
            "test.test_multiprocessing_spawn",
            "test.test_named_expressions", "test.test_netrc",
            "test.test_nis", "test.test_nntplib",
            "test.test_normalization", "test.test_ntpath",
            "test.test_numeric_tower", "test.test__opcode",
            "test.test_opcodes", "test.test_openpty",
            "test.test_operator", "test.test_optparse",
            "test.test_ordered_dict", "test.test_os",
            "test.test_ossaudiodev", "test.test_osx_env",
            "test.test__osx_support", "test.test_parser",
            "test.test_pathlib", "test.test_pdb",
            "test.test_peepholer", "test.test_pickle",
            "test.test_picklebuffer", "test.test_pickletools",
            "test.test_pipes", "test.test_pkg", "test.test_pkgimport",
            "test.test_pkgutil", "test.test_platform",
            "test.test_plistlib", "test.test_poll", "test.test_popen",
            "test.test_poplib", "test.test_positional_only_arg",
            "test.test_posix", "test.test_posixpath", "test.test_pow",
            "test.test_pprint", "test.test_print",
            "test.test_profile", "test.test_property",
            "test.test_pstats", "test.test_pty", "test.test_pulldom",
            "test.test_pwd", "test.test_pyclbr",
            "test.test_py_compile", "test.test_pydoc",
            "test.test_pyexpat", "test.test_queue",
            "test.test_quopri", "test.test_raise", "test.test_random",
            "test.test_range", "test.test_re", "test.test_readline",
            "test.test_regrtest", "test.test_repl",
            "test.test_reprlib", "test.test_resource",
            "test.test_richcmp", "test.test_rlcompleter",
            "test.test_robotparser", "test.test_runpy",
            "test.test_sax", "test.test_sched", "test.test_scope",
            "test.test_script_helper", "test.test_secrets",
            "test.test_select", "test.test_selectors",
            "test.test_set", "test.test_setcomps", "test.test_shelve",
            "test.test_shlex", "test.test_shutil", "test.test_signal",
            "test.test_site", "test.test_slice", "test.test_smtpd",
            "test.test_smtplib", "test.test_smtpnet",
            "test.test_sndhdr", "test.test_socket",
            "test.test_socketserver", "test.test_sort",
            "test.test_source_encoding", "test.test_spwd",
            "test.test_sqlite", "test.test_ssl",
            "test.test_startfile", "test.test_stat",
            "test.test_statistics", "test.test_strftime",
            "test.test_string", "test.test_string_literals",
            "test.test_stringprep", "test.test_strptime",
            "test.test_strtod", "test.test_struct",
            "test.test_structmembers", "test.test_structseq",
            "test.test_subclassinit", "test.test_subprocess",
            "test.test_sunau", "test.test_sundry", "test.test_super",
            "test.test_support", "test.test_symbol",
            "test.test_symtable", "test.test_syntax", "test.test_sys",
            "test.test_sysconfig", "test.test_syslog",
            "test.test_sys_setprofile", "test.test_sys_settrace",
            "test.test_tabnanny", "test.test_tarfile",
            "test.test_tcl", "test.test_telnetlib",
            "test.test_tempfile", "test.test_textwrap",
            "test.test_thread", "test.test_threaded_import",
            "test.test_threadedtempfile", "test.test_threading",
            "test.test_threading_local", "test.test_threadsignals",
            "test.test_time", "test.test_timeit", "test.test_timeout",
            "test.test_tix", "test.test_tk", "test.test_tokenize",
            "test.test_tools", "test.test_tools.__main__",
            "test.test_tools.test_fixcid",
            "test.test_tools.test_gprof2html",
            "test.test_tools.test_i18n", "test.test_tools.test_lll",
            "test.test_tools.test_md5sum",
            "test.test_tools.test_pathfix",
            "test.test_tools.test_pdeps",
            "test.test_tools.test_pindent",
            "test.test_tools.test_reindent",
            "test.test_tools.test_sundry",
            "test.test_tools.test_unparse", "test.test_trace",
            "test.test_traceback", "test.test_tracemalloc",
            "test.test_ttk_guionly", "test.test_ttk_textonly",
            "test.test_tuple", "test.test_turtle",
            "test.test_typechecks", "test.test_type_comments",
            "test.test_types", "test.test_typing", "test.test_ucn",
            "test.test_unary", "test.test_unicode",
            "test.test_unicodedata", "test.test_unicode_file",
            "test.test_unicode_file_functions",
            "test.test_unicode_identifiers", "test.test_unittest",
            "test.test_univnewlines", "test.test_unpack",
            "test.test_unpack_ex", "test.test_urllib",
            "test.test_urllib2", "test.test_urllib2_localnet",
            "test.test_urllib2net", "test.test_urllibnet",
            "test.test_urllib_response", "test.test_urlparse",
            "test.test_userdict", "test.test_userlist",
            "test.test_userstring", "test.test_utf8_mode",
            "test.test_utf8source", "test.test_uu", "test.test_uuid",
            "test.test_venv", "test.test_wait3", "test.test_wait4",
            "test.test_warnings",
            "test.test_warnings.data.import_warning",
            "test.test_warnings.data.stacklevel",
            "test.test_warnings.__main__", "test.test_wave",
            "test.test_weakref", "test.test_weakset",
            "test.test_webbrowser", "test.test_winconsoleio",
            "test.test_winreg", "test.test_winsound",
            "test.test_with", "test.test_wsgiref", "test.test_xdrlib",
            "test.test_xml_dom_minicompat", "test.test_xml_etree",
            "test.test_xml_etree_c", "test.test_xmlrpc",
            "test.test_xmlrpc_net", "test.test__xxsubinterpreters",
            "test.test_xxtestfuzz", "test.test_yield_from",
            "test.test_zipapp", "test.test_zipfile",
            "test.test_zipfile64", "test.test_zipimport",
            "test.test_zipimport_support", "test.test_zlib",
            "test.tf_inherit_check", "test.threaded_import_hangers",
            "test.time_hashlib", "test.tracedmodules",
            "test.tracedmodules.testmod", "test.win_console_handler",
            "test.xmltests",
            "test.ziptestdata.testdata_module_inside_zip", "textwrap",
            "this", "_thread", "threading", "_threading_local",
            "time", "timeit", "_tkinter", "tkinter",
            "tkinter.colorchooser", "tkinter.commondialog",
            "tkinter.constants", "tkinter.dialog", "tkinter.dnd",
            "tkinter.filedialog", "tkinter.font", "tkinter.__main__",
            "tkinter.messagebox", "tkinter.scrolledtext",
            "tkinter.simpledialog", "tkinter.test",
            "tkinter.test.runtktests", "tkinter.test.support",
            "tkinter.test.test_tkinter",
            "tkinter.test.test_tkinter.test_font",
            "tkinter.test.test_tkinter.test_geometry_managers",
            "tkinter.test.test_tkinter.test_images",
            "tkinter.test.test_tkinter.test_loadtk",
            "tkinter.test.test_tkinter.test_misc",
            "tkinter.test.test_tkinter.test_text",
            "tkinter.test.test_tkinter.test_variables",
            "tkinter.test.test_tkinter.test_widgets",
            "tkinter.test.test_ttk",
            "tkinter.test.test_ttk.test_extensions",
            "tkinter.test.test_ttk.test_functions",
            "tkinter.test.test_ttk.test_style",
            "tkinter.test.test_ttk.test_widgets",
            "tkinter.test.widget_tests", "tkinter.tix", "tkinter.ttk",
            "token", "tokenize", "trace", "traceback", "_tracemalloc",
            "tracemalloc", "tty", "turtle", "turtledemo",
            "turtledemo.bytedesign", "turtledemo.chaos",
            "turtledemo.clock", "turtledemo.colormixer",
            "turtledemo.forest", "turtledemo.fractalcurves",
            "turtledemo.lindenmayer", "turtledemo.__main__",
            "turtledemo.minimal_hanoi", "turtledemo.nim",
            "turtledemo.paint", "turtledemo.peace",
            "turtledemo.penrose", "turtledemo.planet_and_moon",
            "turtledemo.rosette", "turtledemo.round_dance",
            "turtledemo.sorting_animate", "turtledemo.tree",
            "turtledemo.two_canvases", "turtledemo.yinyang", "types",
            "typing", "typing.io", "typing.re", "unicodedata",
            "unittest", "unittest.async_case", "unittest.case",
            "unittest.loader", "unittest._log", "unittest.__main__",
            "unittest.main", "unittest.mock", "unittest.result",
            "unittest.runner", "unittest.signals", "unittest.suite",
            "unittest.test", "unittest.test.dummy",
            "unittest.test.__main__", "unittest.test.support",
            "unittest.test.test_assertions",
            "unittest.test.test_async_case",
            "unittest.test.test_break", "unittest.test.test_case",
            "unittest.test.test_discovery",
            "unittest.test.test_functiontestcase",
            "unittest.test.test_loader", "unittest.test.testmock",
            "unittest.test.testmock.__main__",
            "unittest.test.testmock.support",
            "unittest.test.testmock.testasync",
            "unittest.test.testmock.testcallable",
            "unittest.test.testmock.testhelpers",
            "unittest.test.testmock.testmagicmethods",
            "unittest.test.testmock.testmock",
            "unittest.test.testmock.testpatch",
            "unittest.test.testmock.testsealable",
            "unittest.test.testmock.testsentinel",
            "unittest.test.testmock.testwith",
            "unittest.test.test_program", "unittest.test.test_result",
            "unittest.test.test_runner", "unittest.test.test_setups",
            "unittest.test.test_skipping", "unittest.test.test_suite",
            "unittest.test._test_warnings", "unittest.util", "urllib",
            "urllib.error", "urllib.parse", "urllib.request",
            "urllib.response", "urllib.robotparser", "uu", "_uuid",
            "uuid", "venv", "venv.__main__", "_warnings", "warnings",
            "wave", "_weakref", "weakref", "_weakrefset",
            "webbrowser", "winreg", "winsound", "wsgiref",
            "wsgiref.handlers", "wsgiref.headers",
            "wsgiref.simple_server", "wsgiref.util",
            "wsgiref.validate", "xdrlib", "xml", "xml.dom",
            "xml.dom.domreg", "xml.dom.expatbuilder",
            "xml.dom.minicompat", "xml.dom.minidom",
            "xml.dom.NodeFilter", "xml.dom.pulldom",
            "xml.dom.xmlbuilder", "xml.etree",
            "xml.etree.cElementTree", "xml.etree.ElementInclude",
            "xml.etree.ElementPath", "xml.etree.ElementTree",
            "xml.parsers", "xml.parsers.expat",
            "xml.parsers.expat.errors", "xml.parsers.expat.model",
            "xmlrpc", "xmlrpc.client", "xmlrpc.server", "xml.sax",
            "xml.sax._exceptions", "xml.sax.expatreader",
            "xml.sax.handler", "xml.sax.saxutils",
            "xml.sax.xmlreader", "xxlimited", "_xxsubinterpreters",
            "xxsubtype", "_xxtestfuzz", "zipapp", "zipfile",
            "zipimport", "zlib", "zoneinfo", "zoneinfo._common",
            "zoneinfo._tzpath", "zoneinfo._zoneinfo"})
        # Sometimes, a module is imported in python using a different name than is required in the "pip install" command. Keep track of these exceptions here.
        self.module_aliases: dict[str, str] = {
            # I added these manually by asking ChatGPT what pip aliases are different than their import commands:
            # "import name" : "pip install name"
            "osgeo": "gdal",  # osgeo is the import name for gdal
            "ffmpeg": "ffmpeg-python",
            "cv2": "opencv-python",
            "jnp": "jax.numpy",
            # "sm": "statsmodels",
            "netCDF4": "netcdf4",
            "skill_metrics": "SkillMetrics",
            "bugbear": "flake8-bugbear",
            "whisper": "openai-whisper",
            "mypy.api": "mypy",
            "speedtest": "speedtest-cli",
            # This list is from the pipreqs repo in file "mapping", retrieved on 2024-08-15 from here: https://github.com/bndr/pipreqs
            # There are a LOT of duplicate keys in this list! I don't know why. Python dicts will just use the last one.
            # "mapping" file is here: https://github.com/bndr/pipreqs/blob/master/pipreqs/mapping
            # It's used like this:
            # def get_pkg_names(pkgs):
            #     """Get PyPI package names from a list of imports.

            #     Args:
            #         pkgs (List[str]): List of import names.

            #     Returns:
            #         List[str]: The corresponding PyPI package names.

            #     """
            #     result = set()
            #     with open(join("mapping"), "r") as f:
            #         data = dict(x.strip().split(":") for x in f)
            #     for pkg in pkgs:
            #         # Look up the mapped requirement. If a mapping isn't found,
            #         # simply use the package name.
            #         result.add(data.get(pkg, pkg))
            #     # Return a sorted list for backward compatibility.
            #     return sorted(result, key=lambda s: s.lower())
            # Here's an alternative: https://pypi.org/project/pip-run/
            # Here's another alternative: https://pypi.org/project/coherent.deps/
            # Here's some relevant info from the coherent.deps project description:
            # Maintaining the mapping
            # There is a subpackage, distributions, which contains two scripts, load and process (invoked by python -m coherent.deps.distributions.{load,process}) to load the distributions from a "top downloads" summary and then process those by loading their data from PyPI.

            # To get the full set of "top downloaded" packages that contain at least one download, run this query:

            #   pipx run --python 3.13 pypinfo --json --indent 0 --limit 800000 --days 30 "" project > ~/Downloads/top-pypi-packages-30-days.json

            # Note that this pypinfo script requires a Google API key and with a very high limit like 800000, will cost several dollars to run, so the maintainer only runs it about twice a year.

            # Then, to refresh the database with the downloaded dataset:

            #   py -3.13 -m pip-run coherent.deps -- -m coherent.deps.distributions.load ~/Downloads/top-pypi-packages-30-days.json

            # This process will ensure that all packages are up-to-date with their latest download stats.

            # From there, ensure that any newly-added packages are processed:

            #   py -3.13 -m pip-run coherent.deps -- -m coherent.deps.distributions.process

            # Note that only those entries without an updated field will be processed. To re-process packgaes that may have grown stale, clear the updated field on those entries. For example, to mark stale any entries older than 6 months:

            # max_age = datetime.timedelta(days=6*30)
            # filter = {'updated': {'$lt': datetime.today() - max_age}}
            # op = {'$unset': 'updated'}
            # collection.update_many(filter, op)

            # Thereafter, re-run the process routine, which will re-process the packages without the updated field.
            "AFQ": "pyAFQ",
            "AG_fft_tools": "agpy",
            "ANSI": "pexpect",
            "Adafruit": "Adafruit_Libraries",
            "App": "Zope2",
            "Asterisk": "py_Asterisk",
            "BB_jekyll_hook": "bitbucket_jekyll_hook",
            "Banzai": "Banzai_NGS",
            "BeautifulSoupTests": "BeautifulSoup",
            "BioSQL": "biopython",
            "BuildbotStatusShields": "BuildbotEightStatusShields",
            "ComputedAttribute": "ExtensionClass",
            "constraint": "python-constraint",
            "Crypto": "pycryptodome",
            "Cryptodome": "pycryptodomex",
            "FSM": "pexpect",
            "FiftyOneDegrees": "51degrees_mobile_detector_v3_wrapper",
            "functional": "pyfunctional",
            "GeoBaseMain": "GeoBasesDev",
            "GeoBases": "GeoBasesDev",
            "Globals": "Zope2",
            "HelpSys": "Zope2",
            "IPython": "ipython",
            "Kittens": "astro_kittens",
            "Levenshtein": "python_Levenshtein",
            "Lifetime": "Zope2",
            "MethodObject": "ExtensionClass",
            "MySQLdb": "MySQL-python",
            "OFS": "Zope2",
            "OpenGL": "PyOpenGL",
            "OpenSSL": "pyOpenSSL",
            "PIL": "Pillow",
            "Products": "Zope2",
            "PyWCSTools": "astLib",
            "Pyxides": "astro_pyxis",
            "QtCore": "PySide",
            "S3": "s3cmd",
            "SCons": "pystick",
            "Shared": "Zope2",
            "Signals": "Zope2",
            "Stemmer": "PyStemmer",
            "Testing": "Zope2",
            "TopZooTools": "topzootools",
            "TreeDisplay": "DocumentTemplate",
            "WorkingWithDocumentConversion": "aspose_pdf_java_for_python",
            "ZPublisher": "Zope2",
            "ZServer": "Zope2",
            "ZTUtils": "Zope2",
            "aadb": "auto_adjust_display_brightness",
            "abakaffe": "abakaffe_cli",
            "abiosgaming": "abiosgaming.py",
            "abiquo": "abiquo_api",
            "abl": "abl.cssprocessor",
            "abl": "abl.robot",
            "abl": "abl.util",
            "abl": "abl.vpath",
            "abo": "abo_generator",
            "abris_transform": "abris",
            "abstract": "abstract.jwrotator",
            "abu": "abu.admin",
            "ac_flask": "AC_Flask_HipChat",
            "acg": "anikom15",
            "acme": "acme.dchat",
            "acme": "acme.hello",
            "acted": "acted.projects",
            "action": "ActionServer",
            "actionbar": "actionbar.panel",
            "activehomed": "afn",
            "activepapers": "ActivePapers.Py",
            "address_book": "address_book_lansry",
            "adi": "adi.commons",
            "adi": "adi.devgen",
            "adi": "adi.fullscreen",
            "adi": "adi.init",
            "adi": "adi.playlist",
            "adi": "adi.samplecontent",
            "adi": "adi.slickstyle",
            "adi": "adi.suite",
            "adi": "adi.trash",
            "adict": "aDict2",
            "aditam": "aditam.agent",
            "aditam": "aditam.core",
            "adiumsh": "adium_sh",
            "adjector": "AdjectorClient",
            "adjector": "AdjectorTracPlugin",
            "adkit": "Banner_Ad_Toolkit",
            "admin_tools": "django_admin_tools",
            "adminishcategories": "adminish_categories",
            "adminsortable": "django_admin_sortable",
            "adspygoogle": "adspygoogle.adwords",
            "advancedcaching": "agtl",
            "adytum": "Adytum_PyMonitor",
            "affinitic": "affinitic.docpyflakes",
            "affinitic": "affinitic.recipe.fakezope2eggs",
            "affinitic": "affinitic.simplecookiecuttr",
            "affinitic": "affinitic.verifyinterface",
            "affinitic": "affinitic.zamqp",
            "afpy": "afpy.xap",
            "agatesql": "agate_sql",
            "ageliaco": "ageliaco.recipe.csvconfig",
            "agent_http": "agent.http",
            "agora": "Agora_Client",
            "agora": "Agora_Fountain",
            "agora": "Agora_Fragment",
            "agora": "Agora_Planner",
            "agora": "Agora_Service_Provider",
            "agoraplex": "agoraplex.themes.sphinx",
            "agsci": "agsci.blognewsletter",
            "agx": "agx.core",
            "agx": "agx.dev",
            "agx": "agx.generator.buildout",
            "agx": "agx.generator.dexterity",
            "agx": "agx.generator.generator",
            "agx": "agx.generator.plone",
            "agx": "agx.generator.pyegg",
            "agx": "agx.generator.sql",
            "agx": "agx.generator.uml",
            "agx": "agx.generator.zca",
            "agx": "agx.transform.uml2fs",
            "agx": "agx.transform.xmi2uml",
            "aimes": "aimes.bundle",
            "aimes": "aimes.skeleton",
            "aio": "aio.app",
            "aio": "aio.config",
            "aio": "aio.core",
            "aio": "aio.signals",
            "aiohs2": "aio_hs2",
            "aioroutes": "aio_routes",
            "aios3": "aio_s3",
            "airbrake": "airbrake_flask",
            "airship": "airship_icloud",
            "airship": "airship_steamcloud",
            "airflow": "apache-airflow",
            "akamai": "edgegrid_python",
            "alation": "alation_api",
            "alba_client": "alba_client_python",
            "alburnum": "alburnum_maas_client",
            "alchemist": "alchemist.audit",
            "alchemist": "alchemist.security",
            "alchemist": "alchemist.traversal",
            "alchemist": "alchemist.ui",
            "alchemyapi": "alchemyapi_python",
            "alerta": "alerta_server",
            "alexandria_upload": "Alexandria_Upload_Utils",
            "alibaba": "alibaba_python_sdk",
            "aliyun": "aliyun_python_sdk",
            "aliyuncli": "alicloudcli",
            "aliyunsdkacs": "aliyun_python_sdk_acs",
            "aliyunsdkbatchcompute": "aliyun_python_sdk_batchcompute",
            "aliyunsdkbsn": "aliyun_python_sdk_bsn",
            "aliyunsdkbss": "aliyun_python_sdk_bss",
            "aliyunsdkcdn": "aliyun_python_sdk_cdn",
            "aliyunsdkcms": "aliyun_python_sdk_cms",
            "aliyunsdkcore": "aliyun_python_sdk_core",
            "aliyunsdkcrm": "aliyun_python_sdk_crm",
            "aliyunsdkcs": "aliyun_python_sdk_cs",
            "aliyunsdkdrds": "aliyun_python_sdk_drds",
            "aliyunsdkecs": "aliyun_python_sdk_ecs",
            "aliyunsdkess": "aliyun_python_sdk_ess",
            "aliyunsdkft": "aliyun_python_sdk_ft",
            "aliyunsdkmts": "aliyun_python_sdk_mts",
            "aliyunsdkocs": "aliyun_python_sdk_ocs",
            "aliyunsdkoms": "aliyun_python_sdk_oms",
            "aliyunsdkossadmin": "aliyun_python_sdk_ossadmin",
            "aliyunsdkr-kvstore": "aliyun_python_sdk_r_kvstore",
            "aliyunsdkram": "aliyun_python_sdk_ram",
            "aliyunsdkrds": "aliyun_python_sdk_rds",
            "aliyunsdkrisk": "aliyun_python_sdk_risk",
            "aliyunsdkros": "aliyun_python_sdk_ros",
            "aliyunsdkslb": "aliyun_python_sdk_slb",
            "aliyunsdksts": "aliyun_python_sdk_sts",
            "aliyunsdkubsms": "aliyun_python_sdk_ubsms",
            "aliyunsdkyundun": "aliyun_python_sdk_yundun",
            "allattachments": "AllAttachmentsMacro",
            "allocine": "allocine_wrapper",
            "allowedsites": "django_allowedsites",
            "alm": "alm.solrindex",
            "aloft": "aloft.py",
            "alpacalib": "alpaca",
            "alphabetic": "alphabetic_simple",
            "alphasms": "alphasms_client",
            "altered": "altered.states",
            "alterootheme": "alterootheme.busycity",
            "alterootheme": "alterootheme.intensesimplicity",
            "alterootheme": "alterootheme.lazydays",
            "alurinium": "alurinium_image_processing",
            "alxlib": "alx",
            "amara3": "amara3_iri",
            "amara3": "amara3_xml",
            "amazon": "AmazonAPIWrapper",
            "amazon": "python_amazon_simple_product_api",
            "ambikesh1349-1": "ambikesh1349_1",
            "ambilight": "AmbilightParty",
            "amifs": "amifs_core",
            "amiorganizer": "ami_organizer",
            "amitu": "amitu.lipy",
            "amitu": "amitu_putils",
            "amitu": "amitu_websocket_client",
            "amitu": "amitu_zutils",
            "amltlearn": "AMLT_learn",
            "amocrm": "amocrm_api",
            "amqpdispatcher": "amqp_dispatcher",
            "amqpstorm": "AMQP_Storm",
            "analytics": "analytics_python",
            "analyzedir": "AnalyzeDirectory",
            "ancientsolutions": "ancientsolutions_crypttools",
            "anderson_paginator": "anderson.paginator",
            "android_clean_app": "android_resource_remover",
            "anel_power_control": "AnelPowerControl",
            "angus": "angus_sdk_python",
            "annalist_root": "Annalist",
            "annogesiclib": "ANNOgesic",
            "ansible-role-apply": "ansible_role_apply",
            "ansibledebugger": "ansible_playbook_debugger",
            "ansibledocgen": "ansible_docgen",
            "ansibleflow": "ansible_flow",
            "ansibleinventorygrapher": "ansible_inventory_grapher",
            "ansiblelint": "ansible_lint",
            "ansiblerolesgraph": "ansible_roles_graph",
            "ansibletools": "ansible_tools",
            "anthill": "anthill.exampletheme",
            "anthill": "anthill.skinner",
            "anthill": "anthill.tal.macrorenderer",
            "anthrax": "AnthraxDojoFrontend",
            "anthrax": "AnthraxHTMLInput",
            "anthrax": "AnthraxImage",
            "antisphinx": "antiweb",
            "antispoofing": "antispoofing.evaluation",
            "antlr4": "antlr4_python2_runtime",
            "antlr4": "antlr4_python3_runtime",
            "antlr4": "antlr4_python_alt",
            "anybox": "anybox.buildbot.openerp",
            "anybox": "anybox.nose.odoo",
            "anybox": "anybox.paster.odoo",
            "anybox": "anybox.paster.openerp",
            "anybox": "anybox.recipe.sysdeps",
            "anybox": "anybox.scripts.odoo",
            "apiclient": "google_api_python_client",
            "apitools": "google_apitools",
            "apm": "arpm",
            "app_data": "django_appdata",
            "appconf": "django_appconf",
            "appd": "AppDynamicsDownloader",
            "appd": "AppDynamicsREST",
            "appdynamics_bindeps": "appdynamics_bindeps_linux_x64",
            "appdynamics_bindeps": "appdynamics_bindeps_linux_x86",
            "appdynamics_bindeps": "appdynamics_bindeps_osx_x64",
            "appdynamics_proxysupport": "appdynamics_proxysupport_linux_x64",
            "appdynamics_proxysupport": "appdynamics_proxysupport_linux_x86",
            "appdynamics_proxysupport": "appdynamics_proxysupport_osx_x64",
            "appium": "Appium_Python_Client",
            "appliapps": "applibase",
            "appserver": "broadwick",
            "archetypes": "archetypes.kss",
            "archetypes": "archetypes.multilingual",
            "archetypes": "archetypes.schemaextender",
            "arm": "ansible_role_manager",
            "armor": "armor_api",
            "armstrong": "armstrong.apps.related_content",
            "armstrong": "armstrong.apps.series",
            "armstrong": "armstrong.cli",
            "armstrong": "armstrong.core.arm_access",
            "armstrong": "armstrong.core.arm_layout",
            "armstrong": "armstrong.core.arm_sections",
            "armstrong": "armstrong.core.arm_wells",
            "armstrong": "armstrong.dev",
            "armstrong": "armstrong.esi",
            "armstrong": "armstrong.hatband",
            "armstrong": "armstrong.templates.standard",
            "armstrong": "armstrong.utils.backends",
            "armstrong": "armstrong.utils.celery",
            "arstecnica": "arstecnica.raccoon.autobahn",
            "arstecnica": "arstecnica.sqlalchemy.async",
            "article-downloader": "article_downloader",
            "artifactcli": "artifact_cli",
            "arvados": "arvados_python_client",
            "arvados_cwl": "arvados_cwl_runner",
            "arvnodeman": "arvados_node_manager",
            "asana_to_github": "AsanaToGithub",
            "asciibinary": "AsciiBinaryConverter",
            "asd": "AdvancedSearchDiscovery",
            "askbot": "askbot_tuan",
            "askbot": "askbot_tuanpa",
            "asnhistory": "asnhistory_redis",
            "aspen_jinja2_renderer": "aspen_jinja2",
            "aspen_tornado_engine": "aspen_tornado",
            "asprise_ocr_api": "asprise_ocr_sdk_python_api",
            "aspy": "aspy.refactor_imports",
            "aspy": "aspy.yaml",
            "asterisk": "asterisk_ami",
            "asts": "add_asts",
            "asymmetricbase": "asymmetricbase.enum",
            "asymmetricbase": "asymmetricbase.fields",
            "asymmetricbase": "asymmetricbase.logging",
            "asymmetricbase": "asymmetricbase.utils",
            "asyncirc": "asyncio_irc",
            "asyncmongoorm": "asyncmongoorm_je",
            "asyncssh": "asyncssh_unofficial",
            "athletelist": "athletelistyy",
            "atm": "automium",
            "atmosphere": "atmosphere_python_client",
            "atom": "gdata",
            "atomic": "AtomicWrite",
            "atomisator": "atomisator.db",
            "atomisator": "atomisator.enhancers",
            "atomisator": "atomisator.feed",
            "atomisator": "atomisator.indexer",
            "atomisator": "atomisator.outputs",
            "atomisator": "atomisator.parser",
            "atomisator": "atomisator.readers",
            "atreal": "atreal.cmfeditions.unlocker",
            "atreal": "atreal.filestorage.common",
            "atreal": "atreal.layouts",
            "atreal": "atreal.mailservices",
            "atreal": "atreal.massloader",
            "atreal": "atreal.monkeyplone",
            "atreal": "atreal.override.albumview",
            "atreal": "atreal.richfile.preview",
            "atreal": "atreal.richfile.qualifier",
            "atreal": "atreal.usersinout",
            "atsim": "atsim.potentials",
            "attractsdk": "attract_sdk",
            "audio": "audio.bitstream",
            "audio": "audio.coders",
            "audio": "audio.filters",
            "audio": "audio.fourier",
            "audio": "audio.frames",
            "audio": "audio.lp",
            "audio": "audio.psychoacoustics",
            "audio": "audio.quantizers",
            "audio": "audio.shrink",
            "audio": "audio.wave",
            "aufrefer": "auf_refer",
            "auslfe": "auslfe.formonline.content",
            "auspost": "auspost_apis",
            "auth0": "auth0_python",
            "auth_server_client": "AuthServerClient",
            "authorize": "AuthorizeSauce",
            "authzpolicy": "AuthzPolicyPlugin",
            "autobahn": "autobahn_rce",
            "avatar": "geonode_avatar",
            "awebview": "android_webview",
            "azure": "azure_common",
            "azure": "azure_mgmt_common",
            "azure": "azure_mgmt_compute",
            "azure": "azure_mgmt_network",
            "azure": "azure_mgmt_nspkg",
            "azure": "azure_mgmt_resource",
            "azure": "azure_mgmt_storage",
            "azure": "azure_nspkg",
            "azure": "azure_servicebus",
            "azure": "azure_servicemanagement_legacy",
            "azure": "azure_storage",
            "b2gcommands": "b2g_commands",
            "b2gperf": "b2gperf_v1.3",
            "b2gperf": "b2gperf_v1.4",
            "b2gperf": "b2gperf_v2.0",
            "b2gperf": "b2gperf_v2.1",
            "b2gperf": "b2gperf_v2.2",
            "b2gpopulate": "b2gpopulate_v1.3",
            "b2gpopulate": "b2gpopulate_v1.4",
            "b2gpopulate": "b2gpopulate_v2.0",
            "b2gpopulate": "b2gpopulate_v2.1",
            "b2gpopulate": "b2gpopulate_v2.2",
            "b3j0f": "b3j0f.annotation",
            "b3j0f": "b3j0f.aop",
            "b3j0f": "b3j0f.conf",
            "b3j0f": "b3j0f.sync",
            "b3j0f": "b3j0f.utils",
            "babel": "Babel",
            "babelglade": "BabelGladeExtractor",
            "backplane": "backplane2_pyclient",
            "backport_abcoll": "backport_collections",
            "backports": "backports.functools_lru_cache",
            "backports": "backports.inspect",
            "backports": "backports.pbkdf2",
            "backports": "backports.shutil_get_terminal_size",
            "backports": "backports.socketpair",
            "backports": "backports.ssl",
            "backports": "backports.ssl_match_hostname",
            "backports": "backports.statistics",
            "badgekit": "badgekit_api_client",
            "badlinks": "BadLinksPlugin",
            "bael": "bael.project",
            "baidu": "baidupy",
            "balrog": "buildtools",
            "baluhn": "baluhn_redux",
            "bamboo": "bamboo.pantrybell",
            "bamboo": "bamboo.scaffold",
            "bamboo": "bamboo.setuptools_version",
            "bamboo": "bamboo_data",
            "bamboo": "bamboo_server",
            "bambu": "bambu_codemirror",
            "bambu": "bambu_dataportability",
            "bambu": "bambu_enqueue",
            "bambu": "bambu_faq",
            "bambu": "bambu_ffmpeg",
            "bambu": "bambu_grids",
            "bambu": "bambu_international",
            "bambu": "bambu_jwplayer",
            "bambu": "bambu_minidetect",
            "bambu": "bambu_navigation",
            "bambu": "bambu_notifications",
            "bambu": "bambu_payments",
            "bambu": "bambu_pusher",
            "bambu": "bambu_saas",
            "bambu": "bambu_sites",
            "banana": "Bananas",
            "banana": "banana.maya",
            "bang": "bangtext",
            "barcode": "barcode_generator",
            "bark": "bark_ssg",
            "barking_owl": "BarkingOwl",
            "bart": "bart_py",
            "basalt": "basalt_tasks",
            "base62": "base_62",
            "basemap": "basemap_Jim",
            "bash": "bash_toolbelt",
            "bashutils": "Python_Bash_Utils",
            "basic_http": "BasicHttp",
            "basil": "basil_daq",
            "batchapps": "azure_batch_apps",
            "bcrypt": "python_bcrypt",
            "beaker": "Beaker",
            "beetsplug": "beets",
            "begin": "begins",
            "benchit": "bench_it",
            "beproud": "beproud.utils",
            "bfillings": "burrito_fillings",
            "bigjob": "BigJob",
            "billboard": "billboard.py",
            "binstar_build_client": "anaconda_build",
            "binstar_client": "anaconda_client",
            "biocommons": "biocommons.dev",
            "birdhousebuilder": "birdhousebuilder.recipe.conda",
            "birdhousebuilder": "birdhousebuilder.recipe.docker",
            "birdhousebuilder": "birdhousebuilder.recipe.redis",
            "birdhousebuilder": "birdhousebuilder.recipe.supervisor",
            "blender26-meshio": "pymeshio",
            "bootstrap": "BigJob",
            "borg": "borg.localrole",
            "bow": "bagofwords",
            "bpdb": "bpython",
            "bqapi": "bisque_api",
            "braces": "django_braces",
            "briefscaster": "briefs_caster",
            "brisa_media_server/plugins": "brisa_media_server_plugins",
            "brkt_requests": "brkt_sdk",
            "broadcastlogging": "broadcast_logging",
            "brocadetool": "brocade_tool",
            "bronto": "bronto_python",
            "brownie": "Brownie",
            "browsermobproxy": "browsermob_proxy",
            "brubeckmysql": "brubeck_mysql",
            "brubeckoauth": "brubeck_oauth",
            "brubeckservice": "brubeck_service",
            "brubeckuploader": "brubeck_uploader",
            "bs4": "beautifulsoup4",
            "bson": "pymongo",
            "bst": "bst.pygasus.core",
            "bst": "bst.pygasus.datamanager",
            "bst": "bst.pygasus.demo",
            "bst": "bst.pygasus.i18n",
            "bst": "bst.pygasus.resources",
            "bst": "bst.pygasus.scaffolding",
            "bst": "bst.pygasus.security",
            "bst": "bst.pygasus.session",
            "bst": "bst.pygasus.wsgi",
            "btable": "btable_py",
            "btapi": "bananatag_api",
            "btceapi": "btce_api",
            "btcebot": "btce_bot",
            "btsync": "btsync.py",
            "buck": "buck.pprint",
            "bud": "bud.nospam",
            "budy": "budy_api",
            "buffer": "buffer_alpaca",
            "buggd": "bug.gd",
            "bugle": "bugle_sites",
            "bugspots": "bug_spots",
            "bugzilla": "python_bugzilla",
            "bugzscout": "bugzscout_py",
            "buildTools": "ajk_ios_buildTools",
            "buildnotifylib": "BuildNotify",
            "buildout": "buildout.bootstrap",
            "buildout": "buildout.disablessl",
            "buildout": "buildout.dumppickedversions",
            "buildout": "buildout.dumppickedversions2",
            "buildout": "buildout.dumprequirements",
            "buildout": "buildout.eggnest",
            "buildout": "buildout.eggscleaner",
            "buildout": "buildout.eggsdirectories",
            "buildout": "buildout.eggtractor",
            "buildout": "buildout.extensionscripts",
            "buildout": "buildout.locallib",
            "buildout": "buildout.packagename",
            "buildout": "buildout.recipe.isolation",
            "buildout": "buildout.removeaddledeggs",
            "buildout": "buildout.requirements",
            "buildout": "buildout.sanitycheck",
            "buildout": "buildout.sendpickedversions",
            "buildout": "buildout.threatlevel",
            "buildout": "buildout.umask",
            "buildout": "buildout.variables",
            "buildslave": "buildbot_slave",
            "builtins": "pies2overrides",
            "bumper": "bumper_lib",
            "bumple": "bumple_downloader",
            "bundesliga": "bundesliga_cli",
            "bundlemaker": "bundlemanager",
            "burpui": "burp_ui",
            "busyflow": "busyflow.pivotal",
            "buttercms-django": "buttercms_django",
            "buzz": "buzz_python_client",
            "bvc": "buildout_versions_checker",
            "bvggrabber": "bvg_grabber",
            "byond": "BYONDTools",
            "bzETL": "Bugzilla_ETL",
            "bzlib": "bugzillatools",
            "bzrlib": "bzr",
            "bzrlib": "bzr_automirror",
            "bzrlib": "bzr_bash_completion",
            "bzrlib": "bzr_colo",
            "bzrlib": "bzr_killtrailing",
            "bzrlib": "bzr_pqm",
            "c2c": "c2c.cssmin",
            "c2c": "c2c.recipe.closurecompile",
            "c2c": "c2c.recipe.cssmin",
            "c2c": "c2c.recipe.jarfile",
            "c2c": "c2c.recipe.msgfmt",
            "c2c": "c2c.recipe.pkgversions",
            "c2c": "c2c.sqlalchemy.rest",
            "c2c": "c2c.versions",
            "c2c_recipe_facts": "c2c.recipe.facts",
            "cabalgata": "cabalgata_silla_de_montar",
            "cabalgata": "cabalgata_zookeeper",
            "cache_utils": "django_cache_utils",
            "captcha": "django_recaptcha",
            "cartridge": "Cartridge",
            "cassandra": "cassandra_driver",
            "cassandralauncher": "CassandraLauncher",
            "cc42": "42qucc",
            "cerberus": "Cerberus",
            "cfnlint": "cfn-lint",
            "chameleon": "Chameleon",
            "charmtools": "charm_tools",
            "chef": "PyChef",
            "chip8": "c8d",
            "cjson": "python_cjson",
            "classytags": "django_classy_tags",
            "cloghandler": "ConcurrentLogHandler",
            "clonevirtualenv": "virtualenv_clone",
            "cloud-insight": "al_cloudinsight",
            "cloud_admin": "adminapi",
            "cloudservers": "python_cloudservers",
            "clusterconsole": "cerebrod",
            "clustersitter": "cerebrod",
            "cms": "django_cms",
            "colander": "ba_colander",
            "colors": "ansicolors",
            "compile": "bf_lc3",
            "compose": "docker_compose",
            "compressor": "django_compressor",
            "concurrent": "futures",
            "configargparse": "ConfigArgParse",
            "configparser": "pies2overrides",
            "contracts": "PyContracts",
            "coordination": "BigJob",
            "copyreg": "pies2overrides",
            "corebio": "weblogo",
            "couchapp": "Couchapp",
            "couchdb": "CouchDB",
            "couchdbcurl": "couchdb_python_curl",
            "courseradownloader": "coursera_dl",
            "cow": "cow_framework",
            "creole": "python_creole",
            "creoleparser": "Creoleparser",
            "crispy_forms": "django_crispy_forms",
            "cronlog": "python_crontab",
            "crontab": "python_crontab",
            "ctff": "tff",
            "cups": "pycups",
            "curator": "elasticsearch_curator",
            "curl": "pycurl",
            "daemon": "python_daemon",
            "dare": "DARE",
            "dateutil": "python_dateutil",
            "dawg": "DAWG",
            "deb822": "python_debian",
            "debian": "python_debian",
            "decouple": "python-decouple",
            "demo": "webunit",
            "demosongs": "PySynth",
            "deployer": "juju_deployer",
            "depot": "filedepot",
            "devtools": "tg.devtools",
            "dgis": "2gis",
            "dhtmlparser": "pyDHTMLParser",
            "digitalocean": "python_digitalocean",
            "discord": "discord.py",
            "distribute_setup": "ez_setup",
            "distutils2": "Distutils2",
            "django": "Django",
            "django_hstore": "amitu_hstore",
            "djangobower": "django_bower",
            "djcelery": "django_celery",
            "djkombu": "django_kombu",
            "djorm_pgarray": "djorm_ext_pgarray",
            "dns": "dnspython",
            "docgen": "ansible_docgenerator",
            "docker": "docker_py",
            "dogpile": "dogpile.cache",
            "dogpile": "dogpile.core",
            "dogshell": "dogapi",
            "dot_parser": "pydot",
            "dot_parser": "pydot2",
            "dot_parser": "pydot3k",
            "dotenv": "python-dotenv",
            "dpkt": "dpkt_fix",
            "dsml": "python_ldap",
            "durationfield": "django_durationfield",
            "dzclient": "datazilla",
            "easybuild": "easybuild_framework",
            "editor": "python_editor",
            "elasticluster": "azure_elasticluster",
            "elasticluster": "azure_elasticluster_current",
            "elftools": "pyelftools",
            "elixir": "Elixir",
            "em": "empy",
            "emlib": "empy",
            "enchant": "pyenchant",
            "encutils": "cssutils",
            "engineio": "python_engineio",
            "enum": "enum34",
            "ephem": "pyephem",
            "errorreporter": "abl.errorreporter",
            "esplot": "beaker_es_plot",
            "example": "adrest",
            "examples": "tweepy",
            "ez_setup": "pycassa",
            "fabfile": "Fabric",
            "fabric": "Fabric",
            "faker": "Faker",
            "fdpexpect": "pexpect",
            "fedora": "python_fedora",
            "fias": "ailove_django_fias",
            "fiftyone_degrees": "51degrees_mobile_detector",
            "five": "five.customerize",
            "five": "five.globalrequest",
            "five": "five.intid",
            "five": "five.localsitemanager",
            "five": "five.pt",
            "flasher": "android_flasher",
            "flask": "Flask",
            "flask_frozen": "Frozen_Flask",
            "flask_redis": "Flask_And_Redis",
            "flaskext": "Flask_Bcrypt",
            "flvscreen": "vnc2flv",
            "followit": "django_followit",
            "forge": "pyforge",
            "formencode": "FormEncode",
            "formtools": "django_formtools",
            "fourch": "4ch",
            "franz": "allegrordf",
            "freetype": "freetype_py",
            "frontmatter": "python_frontmatter",
            "ftpcloudfs": "ftp_cloudfs",
            "funtests": "librabbitmq",
            "fuse": "fusepy",
            "fuzzy": "Fuzzy",
            "gabbi": "tiddlyweb",
            "gen_3dwallet": "3d_wallet_generator",
            "gendimen": "android_gendimen",
            "genshi": "Genshi",
            "geohash": "python_geohash",
            "geonode": "GeoNode",
            "geoserver": "gsconfig",
            "geraldo": "Geraldo",
            "getenv": "django_getenv",
            "geventwebsocket": "gevent_websocket",
            "gflags": "python_gflags",
            "git": "GitPython",
            "github": "PyGithub",
            "github3": "github3.py",
            "gitpy": "git_py",
            "globusonline": "globusonline_transfer_api_client",
            "google": "protobuf",
            "googleapiclient": "google_api_python_client",
            "grace-dizmo": "grace_dizmo",
            "grammar": "anovelmous_grammar",
            "grapheneapi": "graphenelib",
            "greplin": "scales",
            "gridfs": "pymongo",
            "grokcore": "grokcore.component",
            "gslib": "gsutil",
            "hamcrest": "PyHamcrest",
            "harpy": "HARPy",
            "hawk": "PyHawk_with_a_single_extra_commit",
            "haystack": "django_haystack",
            "hgext": "mercurial",
            "hggit": "hg_git",
            "hglib": "python_hglib",
            "ho": "pisa",
            "hola": "amarokHola",
            "hoover": "Hoover",
            "hostlist": "python_hostlist",
            "html": "pies2overrides",
            "htmloutput": "nosehtmloutput",
            "http": "pies2overrides",
            "hvad": "django_hvad",
            "hydra": "hydra-core",
            "i99fix": "199Fix",
            "igraph": "python_igraph",
            "imdb": "IMDbPY",
            "impala": "impyla",
            "inmemorystorage": "ambition_inmemorystorage",
            "ipaddress": "backport_ipaddress",
            "jaraco": "jaraco.timing",
            "jaraco": "jaraco.util",
            "jinja2": "Jinja2",
            "jiracli": "jira_cli",
            "johnny": "johnny_cache",
            "jpgrid": "python_geohash",
            "jpiarea": "python_geohash",
            "jpype": "JPype1",
            "jpypex": "JPype1",
            "jsonfield": "django_jsonfield",
            "jstools": "aino_jstools",
            "jupyterpip": "jupyter_pip",
            "jwt": "PyJWT",
            "kazoo": "asana_kazoo",
            "kernprof": "line_profiler",
            "keyczar": "python_keyczar",
            "keyedcache": "django_keyedcache",
            "keystoneclient": "python_keystoneclient",
            "kickstarter": "kickstart",
            "krbv": "krbV",
            "kss": "kss.core",
            "kuyruk": "Kuyruk",
            "langconv": "AdvancedLangConv",
            "lava": "lava_utils_interface",
            "lazr": "lazr.authentication",
            "lazr": "lazr.restfulclient",
            "lazr": "lazr.uri",
            "ldap": "python_ldap",
            "ldaplib": "adpasswd",
            "ldapurl": "python_ldap",
            "ldif": "python_ldap",
            "lib2or3": "2or3",
            "lib3to2": "3to2",
            "libaito": "Aito",
            "libbe": "bugs_everywhere",
            "libbucket": "bucket",
            "libcloud": "apache_libcloud",
            "libfuturize": "future",
            "libgenerateDS": "generateDS",
            "libmproxy": "mitmproxy",
            "libpasteurize": "future",
            "libsvm": "7lk_ocr_deploy",
            "lisa": "lisa_server",
            "loadingandsaving": "aspose_words_java_for_python",
            "locust": "locustio",
            "logbook": "Logbook",
            "logentries": "buildbot_status_logentries",
            "logilab": "logilab_mtconverter",
            "machineconsole": "cerebrod",
            "machinesitter": "cerebrod",
            "magic": "python_magic",
            "mako": "Mako",
            "manifestparser": "ManifestDestiny",
            "marionette": "marionette_client",
            "markdown": "Markdown",
            "marks": "pytest_marks",
            "markupsafe": "MarkupSafe",
            "mavnative": "pymavlink",
            "memcache": "python_memcached",
            "metacomm": "AllPairs",
            "metaphone": "Metafone",
            "metlog": "metlog_py",
            "mezzanine": "Mezzanine",
            "migrate": "sqlalchemy_migrate",
            "mimeparse": "python_mimeparse",
            "minitage": "minitage.paste",
            "minitage": "minitage.recipe.common",
            "missingdrawables": "android_missingdrawables",
            "mixfiles": "PySynth",
            "mkfreq": "PySynth",
            "mkrst_themes": "2lazy2rest",
            "mockredis": "mockredispy",
            "modargs": "python_modargs",
            "model_utils": "django_model_utils",
            "models": "asposebarcode",
            "models": "asposestorage",
            "moksha": "moksha.common",
            "moksha": "moksha.hub",
            "moksha": "moksha.wsgi",
            "moneyed": "py_moneyed",
            "mongoalchemy": "MongoAlchemy",
            "monthdelta": "MonthDelta",
            "mopidy": "Mopidy",
            "mopytools": "MoPyTools",
            "mptt": "django_mptt",
            "mpv": "python-mpv",
            "mrbob": "mr.bob",
            "msgpack": "msgpack_python",
            "mutations": "aino_mutations",
            "mws": "amazon_mws",
            "mysql": "mysql_connector_repackaged",
            "native_tags": "django_native_tags",
            "ndg": "ndg_httpsclient",
            "nereid": "trytond_nereid",
            "nested": "baojinhuan",
            "nester": "Amauri",
            "nester": "abofly",
            "nester": "bssm_pythonSig",
            "novaclient": "python_novaclient",
            "oauth2_provider": "alauda_django_oauth",
            "oauth2client": "oauth2client",
            "odf": "odfpy",
            "ometa": "Parsley",
            "openid": "python_openid",
            "opensearchsdk": "ali_opensearch",
            "oslo_i18n": "oslo.i18n",
            "oslo_serialization": "oslo.serialization",
            "oslo_utils": "oslo.utils",
            "oss": "alioss",
            "oss": "aliyun_python_sdk_oss",
            "oss": "aliyunoss",
            "output": "cashew",
            "owslib": "OWSLib",
            "packetdiag": "nwdiag",
            "paho": "paho_mqtt",
            "paintstore": "django_paintstore",
            "parler": "django_parler",
            "past": "future",
            "paste": "PasteScript",
            "path": "forked_path",
            "path": "path.py",
            "patricia": "patricia-trie",
            "paver": "Paver",
            "peak": "ProxyTypes",
            "picasso": "anderson.picasso",
            "picklefield": "django-picklefield",
            "pilot": "BigJob",
            "pivotal": "pivotal_py",
            "play_wav": "PySynth",
            "playhouse": "peewee",
            "plivoxml": "plivo",
            "plone": "plone.alterego",
            "plone": "plone.api",
            "plone": "plone.app.blob",
            "plone": "plone.app.collection",
            "plone": "plone.app.content",
            "plone": "plone.app.contentlisting",
            "plone": "plone.app.contentmenu",
            "plone": "plone.app.contentrules",
            "plone": "plone.app.contenttypes",
            "plone": "plone.app.controlpanel",
            "plone": "plone.app.customerize",
            "plone": "plone.app.dexterity",
            "plone": "plone.app.discussion",
            "plone": "plone.app.event",
            "plone": "plone.app.folder",
            "plone": "plone.app.i18n",
            "plone": "plone.app.imaging",
            "plone": "plone.app.intid",
            "plone": "plone.app.layout",
            "plone": "plone.app.linkintegrity",
            "plone": "plone.app.locales",
            "plone": "plone.app.lockingbehavior",
            "plone": "plone.app.multilingual",
            "plone": "plone.app.portlets",
            "plone": "plone.app.querystring",
            "plone": "plone.app.redirector",
            "plone": "plone.app.registry",
            "plone": "plone.app.relationfield",
            "plone": "plone.app.textfield",
            "plone": "plone.app.theming",
            "plone": "plone.app.users",
            "plone": "plone.app.uuid",
            "plone": "plone.app.versioningbehavior",
            "plone": "plone.app.viewletmanager",
            "plone": "plone.app.vocabularies",
            "plone": "plone.app.widgets",
            "plone": "plone.app.workflow",
            "plone": "plone.app.z3cform",
            "plone": "plone.autoform",
            "plone": "plone.batching",
            "plone": "plone.behavior",
            "plone": "plone.browserlayer",
            "plone": "plone.caching",
            "plone": "plone.contentrules",
            "plone": "plone.dexterity",
            "plone": "plone.event",
            "plone": "plone.folder",
            "plone": "plone.formwidget.namedfile",
            "plone": "plone.formwidget.recurrence",
            "plone": "plone.i18n",
            "plone": "plone.indexer",
            "plone": "plone.intelligenttext",
            "plone": "plone.keyring",
            "plone": "plone.locking",
            "plone": "plone.memoize",
            "plone": "plone.namedfile",
            "plone": "plone.outputfilters",
            "plone": "plone.portlet.collection",
            "plone": "plone.portlet.static",
            "plone": "plone.portlets",
            "plone": "plone.protect",
            "plone": "plone.recipe.zope2install",
            "plone": "plone.registry",
            "plone": "plone.resource",
            "plone": "plone.resourceeditor",
            "plone": "plone.rfc822",
            "plone": "plone.scale",
            "plone": "plone.schema",
            "plone": "plone.schemaeditor",
            "plone": "plone.session",
            "plone": "plone.stringinterp",
            "plone": "plone.subrequest",
            "plone": "plone.supermodel",
            "plone": "plone.synchronize",
            "plone": "plone.theme",
            "plone": "plone.transformchain",
            "plone": "plone.uuid",
            "plone": "plone.z3cform",
            "plonetheme": "plonetheme.barceloneta",
            "png": "pypng",
            "polymorphic": "django_polymorphic",
            "postmark": "python_postmark",
            "powerprompt": "bash_powerprompt",
            "prefetch": "django-prefetch",
            "printList": "AndrewList",
            "progressbar": "progressbar2",
            "progressbar": "progressbar33",
            "provider": "django_oauth2_provider",
            "puresasl": "pure_sasl",
            "pwiz": "peewee",
            "pxssh": "pexpect",
            "py7zlib": "pylzma",
            "pyAMI": "pyAMI_core",
            "pyarsespyder": "arsespyder",
            "pyasdf": "asdf",
            "pyaspell": "aspell_python_ctypes",
            "pybb": "pybbm",
            "pybloomfilter": "pybloomfiltermmap",
            "pyccuracy": "Pyccuracy",
            "pyck": "PyCK",
            "pycrfsuite": "python_crfsuite",
            "pydispatch": "PyDispatcher",
            "pygeolib": "pygeocoder",
            "pygments": "Pygments",
            "pygraph": "python_graph_core",
            "pyjon": "pyjon.utils",
            "pyjsonrpc": "python_jsonrpc",
            "pykka": "Pykka",
            "pylogo": "PyLogo",
            "pylons": "adhocracy_Pylons",
            "pymagic": "libmagic",
            "pymycraawler": "Amalwebcrawler",
            "pynma": "AbakaffeNotifier",
            "pyphen": "Pyphen",
            "pyrimaa": "AEI",
            "pysideuic": "PySide",
            "pysqlite2": "adhocracy_pysqlite",
            "pysqlite2": "pysqlite",
            "pysynth_b": "PySynth",
            "pysynth_beeper": "PySynth",
            "pysynth_c": "PySynth",
            "pysynth_d": "PySynth",
            "pysynth_e": "PySynth",
            "pysynth_p": "PySynth",
            "pysynth_s": "PySynth",
            "pysynth_samp": "PySynth",
            "pythongettext": "python_gettext",
            "pythonjsonlogger": "python_json_logger",
            "pyutilib": "PyUtilib",
            "pyximport": "Cython",
            "qs": "qserve",
            "quadtree": "python_geohash",
            "queue": "future",
            "quickapi": "django_quickapi",
            "quickunit": "nose_quickunit",
            "rackdiag": "nwdiag",
            "radical": "radical.pilot",
            "radical": "radical.utils",
            "reStructuredText": "Zope2",
            "readability": "readability_lxml",
            "readline": "gnureadline",
            "recaptcha_works": "django_recaptcha_works",
            "relstorage": "RelStorage",
            "reportapi": "django_reportapi",
            "reprlib": "pies2overrides",
            # "requests": "Requests", # This doesn't work on my Ubuntu machine.
            "requirements": "requirements_parser",
            "rest_framework": "djangorestframework",
            "restclient": "py_restclient",
            "retrial": "async_retrial",
            "reversion": "django_reversion",
            "rhaptos2": "rhaptos2.common",
            "robot": "robotframework",
            "robots": "django_robots",
            "rosdep2": "rosdep",
            "rsbackends": "RSFile",
            "ruamel": "ruamel.base",
            "s2repoze": "pysaml2",
            "saga": "saga_python",
            "saml2": "pysaml2",
            "samtranslator": "aws-sam-translator",
            "sass": "libsass",
            "sassc": "libsass",
            "sasstests": "libsass",
            "sassutils": "libsass",
            "sayhi": "alex_sayhi",
            "scalrtools": "scalr",
            "scikits": "scikits.talkbox",
            "scratch": "scratchpy",
            "screen": "pexpect",
            "scss": "pyScss",
            "sdict": "dict.sorted",
            "sdk_updater": "android_sdk_updater",
            "sekizai": "django_sekizai",
            "sendfile": "pysendfile",
            "serial": "pyserial",
            "setuputils": "astor",
            "shapefile": "pyshp",
            "shapely": "Shapely",
            "sika": "ahonya_sika",
            "singleton": "pysingleton",
            "sittercommon": "cerebrod",
            "skbio": "scikit_bio",
            "sklearn": "scikit_learn",
            "slack": "slackclient",
            "slugify": "unicode_slugify",
            "slugify": "python-slugify",
            "smarkets": "smk_python_sdk",
            "snappy": "ctypes_snappy",
            "socketio": "python-socketio",
            "socketserver": "pies2overrides",
            "sockjs": "sockjs_tornado",
            "socks": "SocksiPy_branch",
            "solr": "solrpy",
            "solution": "Solution",
            "sorl": "sorl_thumbnail",
            "south": "South",
            "sphinx": "Sphinx",
            "sphinx_pypi_upload": "ATD_document",
            "sphinxcontrib": "sphinxcontrib_programoutput",
            "sqlalchemy": "SQLAlchemy",
            "src": "atlas",
            "src": "auto_mix_prep",
            "stats_toolkit": "bw_stats_toolkit",
            "statsd": "dogstatsd_python",
            "stdnum": "python_stdnum",
            "stoneagehtml": "StoneageHTML",
            "storages": "django_storages",
            "stubout": "mox",
            "suds": "suds_jurko",
            "swiftclient": "python_swiftclient",
            "sx": "pisa",
            "tabix": "pytabix",
            "taggit": "django_taggit",
            "tasksitter": "cerebrod",
            "tastypie": "django_tastypie",
            "teamcity": "teamcity_messages",
            "telebot": "pyTelegramBotAPI",
            "telegram": "python-telegram-bot",
            "tempita": "Tempita",
            "tenjin": "Tenjin",
            "termstyle": "python_termstyle",
            "test": "pytabix",
            "thclient": "treeherder_client",
            "threaded_multihost": "django_threaded_multihost",
            "threecolor": "3color_Press",
            "tidylib": "pytidylib",
            "tkinter": "future",
            "tlw": "3lwg",
            "toredis": "toredis_fork",
            "tornadoredis": "tornado_redis",
            "tower_cli": "ansible_tower_cli",
            "trac": "Trac",
            "tracopt": "Trac",
            "translation_helper": "android_localization_helper",
            "treebeard": "django_treebeard",
            "trytond": "trytond_stock",
            "tsuru": "tsuru_circus",
            "tvrage": "python_tvrage",
            "tw2": "tw2.core",
            "tw2": "tw2.d3",
            "tw2": "tw2.dynforms",
            "tw2": "tw2.excanvas",
            "tw2": "tw2.forms",
            "tw2": "tw2.jit",
            "tw2": "tw2.jqplugins.flot",
            "tw2": "tw2.jqplugins.gritter",
            "tw2": "tw2.jqplugins.ui",
            "tw2": "tw2.jquery",
            "tw2": "tw2.sqla",
            "twisted": "Twisted",
            "twitter": "python_twitter",
            "txclib": "transifex_client",
            "u115": "115wangpan",
            # "unidecode": "Unidecode", # This doesn't work on my Ubuntu machine.
            "universe": "ansible_universe",
            "usb": "pyusb",
            "useless": "useless.pipes",
            "userpass": "auth_userpass",
            "utilities": "automakesetup.py",
            "utkik": "aino_utkik",
            "uwsgidecorators": "uWSGI",
            "valentine": "ab",
            "validate": "configobj",
            "version": "chartio",
            "virtualenvapi": "ar_virtualenv_api",
            "vyatta": "brocade_plugins",
            "webdav": "Zope2",
            "weblogolib": "weblogo",
            "webob": "WebOb",
            "websocket": "websocket_client",
            "webtest": "WebTest",
            "werkzeug": "Werkzeug",
            "wheezy": "wheezy.caching",
            "wheezy": "wheezy.core",
            "wheezy": "wheezy.http",
            "wikklytext": "tiddlywebwiki",
            "winreg": "future",
            "winrm": "pywinrm",
            "workflow": "Alfred_Workflow",
            "wsmeext": "WSME",
            "wtforms": "WTForms",
            "wtfpeewee": "wtf_peewee",
            "xdg": "pyxdg",
            "xdist": "pytest_xdist",
            "xmldsig": "pysaml2",
            "xmlenc": "pysaml2",
            "xmlrpc": "pies2overrides",
            "xmpp": "xmpppy",
            "xstatic": "XStatic_Font_Awesome",
            "xstatic": "XStatic_jQuery",
            "xstatic": "XStatic_jquery_ui",
            "yaml": "PyYAML",
            "z3c": "z3c.autoinclude",
            "z3c": "z3c.caching",
            "z3c": "z3c.form",
            "z3c": "z3c.formwidget.query",
            "z3c": "z3c.objpath",
            "z3c": "z3c.pt",
            "z3c": "z3c.relationfield",
            "z3c": "z3c.traverser",
            "z3c": "z3c.zcmlhook",
            "zmq": "pyzmq",
            "zopyx": "zopyx.textindexng3"}
        self.reversed_module_aliases = {v: k for k, v in self.module_aliases.items()}
        # Set of known bad imports that should be ignored.
        self.known_bad_imports: set[str] = {"__builtin__", "snakeClass", "GPUampcor", "pathfinding_salvo_rework", "seaborn", "DQN", "bayesOpt", "tkinter", "msvcrt", "BaseHTTPServer", "urlparse", "tkFileDialog", "tkMessageBox", "ConfigParser", "Cookie", "HTMLParser", "Queue", "SocketServer", "StringIO", "Tkinter", "UserDict", "cPickle", "cStringIO", "cookielib", "htmlentitydefs", "httplib", "tkFont", "urllib2", "non_existent_module"}  # "BaseHTTPServer", "urlparse", "tkFileDialog", "tkMessageBox", "ConfigParser", "Cookie", "HTMLParser", "Queue", "SocketServer", "StringIO", "Tkinter", "UserDict", "cPickle", "cStringIO", "cookielib", "htmlentitydefs", "httplib", "tkFont", "tkMessageBox", "urllib2" are Python 2 modules - we don't want to try to install them. A more general approach would involve importing stdlib_list and using that to filter out stdlib modules from Python 2 and Python 3: https://pypi.org/project/stdlib-list/
        # https://chatgpt.com/share/687000fd-be84-8006-a7f4-06af4b1e0eda
        # List of unusual imports that are not standard library modules or packages.
        self.unusual_imports: list[str] = ["a", "an", "dl", "the", "it", "x", "xx", "above", "another", "__builtin__", "within"]
        # List of directories to stay out of when searching for local custom imports because they're filled with standard library modules or other irrelevant files.
        self.stay_out_list: list[str] = ["myenv", ".venv", "anaconda3", "miniconda3", "miniforge3",
                                         ".conda", os.sep+"lib"+os.sep, ".vscode"]

    def set_venv_dir(self, venv_dir: str | os.PathLike[str]) -> None:
        """Set the directory for the virtual environment."""
        p = ud.ensure_path(venv_dir)
        self.venv_dir             = p
        self.venv_python          = p / "bin" / "python"  # Do NOT resolve() this symlink path
        self.venv_pip             = p / "bin" / "pip"     # Do NOT resolve() this symlink path
        self.requirements_file    = p / "requirements.txt"
        self.download_script_path = p / "download_packages.sh"
        p.mkdir(parents=True, exist_ok=True)  # Create the directory if it doesn't exist


def parse_arguments(options: Options) -> None:
    """
    Parse command-line arguments.

    Args:
        options: Options object to store parsed arguments. Contains:
            - my_name:             Name of the program.
            - manual_instructions: Instructions for manually adding the alias to the shell configuration file.
            - log_mode:            Logging mode (default is logging.INFO).
            - args:                Parsed arguments will be stored here.

    Returns:
        None, but updates options.args with parsed arguments.

    Raises:
        SystemExit: If "-version" or "-manual" flags are provided, the program will print the relevant information and exit.
        ValueError: If any of the arguments are invalid.
    """
    parser = argparse.ArgumentParser(description="Run a python script with optional flags.")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--manual", action="store_true",
                        help="Print instructions for manually adding the alias to the shell configuration file.")
    parser.add_argument("--feeling-lucky", action="store_true",
                        help="NOT FINISHED!!! Don't analyze imports, just try to run the script with the last used virtual environment. If that fails, try the latest virtual environment which has all the packages needed now.")
    parser.add_argument("-d", "--debug", action="store_true",
                        help="Run this program in debug mode, which prints additional debug messages.")
    parser.add_argument("--blank-slate", action="store_true",
                        help=f"Delete ~/{options.my_name}/ and all {options.my_name} .out and .err and .json and .pkl files in the current directory.")
    parser.add_argument("--full", action="store_true",
                        help="Build a virtual environment (venv) that can run every python script in the current directory. Cannot be used with a python script argument.")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="Automatically say yes to any prompts to allow this program to run without the need for user interaction.")
    parser.add_argument("--no-cache", action="store_true",
                        help="Don't search the cache. Instead, create a new virtual environment. Also, refresh the custom modules cache and the pip list.")
    parser.add_argument("--latest", action="store_true",
                        help="Load the latest cached venv which has all the packages needed now.")
    parser.add_argument("--oldest", action="store_true",
                        help="Load the oldest cached venv which has all the packages needed now.")
    parser.add_argument("--last-used", action="store_true",
                        help="Load the last used cached venv, but if that fails try the latest cached venv which has all the packages needed now.")
    parser.add_argument("--smallest", action="store_true",
                        help="Load the smallest cached venv (with the fewest packages) which has all the packages needed now.")
    parser.add_argument("--rc", action="store_true",
                        help="Refresh the custom modules cache and the pip list.")
    parser.add_argument("--reqs", action="store_true",
                        help="Read the extra_requirements.txt file in the current directory and install the packages listed there (with specific versions if present in the file) into the venv (along with the other packages needed to run the script as determined elsewhere in this program).")
    parser.add_argument("--alias", type=str,
                        help="Add an alias to the shell configuration file so that typing ALIAS anywhere runs this program.")
    parser.add_argument("--rawlog", action="store_true",
                        help=f"Do not add timestamps or INFO level to log messages, and do not add extra INFO level log statements. Just produce the same output that would be seen when running the program without {options.my_name}.")
    parser.add_argument("--justprint", action="store_true",
                        help="Don't run the script, just print its package requirements.")
    parser.add_argument("script", nargs="?",
                        help="The script to run.")
    parser.add_argument("script_args", nargs=argparse.REMAINDER,
                        help="Optional arguments for the python script.")

    # If no arguments are provided, print a short guide
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    # Otherwise, parse the arguments and store them in options.args for later use.
    options.args = parser.parse_args()
    assert options.args is not None  # for type-checkers

    # Print instructions for manually adding the alias to the shell configuration file, etc.
    if getattr(options.args, "manual", False):
        print(options.manual_instructions)
        sys.exit(0)

    if getattr(options.args, "debug", False):
        options.log_mode = logging.DEBUG


def main() -> None:
    """Main function."""
    start_time = dt.datetime.now()
    options: Options = Options()
    parse_arguments(options)
    script_string       = getattr(options.args, "script",       None)
    options.script_args = getattr(options.args, "script_args",    [])
    options.rawlog      = getattr(options.args, "rawlog",      False)
    if script_string is None:
        options.python_script = None
    else:
        options.python_script = ud.ensure_file(script_string, raise_on_empty=True).resolve(strict=True)
        options.script_dir    = options.python_script.parent.absolute()
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Directory where the script to run is located: %s", os.fspath(options.script_dir))

    if getattr(options.args, "feeling_lucky", False) and options.python_script:
        last_used_venv_python = load_last_used_venv_python(options)
        if last_used_venv_python:
            command_list = [os.fspath(last_used_venv_python), os.fspath(options.python_script)] + options.script_args
            result = subprocess.run(command_list)
            if result.returncode != 0 and not options.rawlog:
                print(f"Error running script: {result.stderr}")
            sys.exit(result.returncode)
        else:
            if not options.rawlog: print("No luck: no last used virtual environment found. Running the script as normal.")

    memory_handler = ud.configure_logging(options.my_name, log_level=options.log_mode,
                                          rawlog=options.rawlog)

    options.python_command = ud.find_preferred_python_version()
    if options.python_command:
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Python %s is available at: %s", ud.PY_VERSION, options.python_command)
    else:
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Python %s is not available.", ud.PY_VERSION)

    if not ud.safe_is_dir(options.my_dir):
        if not options.rawlog: logging.info("Directory %s does not exist yet, so it is being created.", options.my_dir)
        options.my_dir.mkdir(parents=True, exist_ok=True)
    if not ud.safe_is_dir(options.packages_dir):
        if not options.rawlog: logging.info("Directory %s does not exist yet, so it is being created.", options.packages_dir)
        options.packages_dir.mkdir(parents=True, exist_ok=True)

    ud.verify_script(options, options.univ_defs_sys_path_script, ud.UNIV_DEFS_SYS_PATH_SCRIPT)
    ud.verify_script(options, options.mydiff_path,               ud.MYDIFF_SCRIPT)
    ud.verify_script(options, options.myaudit_path,              ud.MYAUDIT_SCRIPT)
    ud.verify_script(options, options.multireplace_path,         ud.MULTIREPLACE_SCRIPT)
    ud.verify_script(options, options.treeview_path,             ud.TREEVIEW_SCRIPT)
    ud.verify_script(options, options.printall_path,             ud.PRINTALL_SCRIPT)

    if getattr(options.args, "alias", False):
        # Add the alias to the shell configuration file
        options.alias = options.args.alias
        add_alias(options)
        sys.exit(0)
    elif getattr(options.args, "full", False) and options.python_script:
        ud.my_critical_error("Full mode is not supported with a script argument.")
    elif options.python_script:
        pass  # If a script was provided as an argument, skip the rest of these checks.
    elif getattr(options.args, "blank_slate", False):
        if not getattr(options.args, "y", False):
            if not ud.prompt_then_confirm(f"Are you sure you want to delete everything in ~/{options.my_name}/"
                                          f" and all {options.my_name} .json files in the current directory? (y/n) "):
                logging.info("Exiting without deleting anything.")
                sys.exit(0)
        logging.info("Deleting everything in ~/%s/ and all %s .out and .err and .json and .pkl files in the current directory.",
                     options.my_name, options.my_name)
        shutil.rmtree(options.my_dir, ignore_errors=True)
        for file in options.cwd.iterdir():
            if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Checking %s", file)
            if ud.safe_is_file(file):
                if (file.name.startswith(f".{options.my_name}-")                      and file.suffix.casefold() == ".out" ) or \
                   (file.name.startswith(f".{options.my_name}-")                      and file.suffix.casefold() == ".err" ) or \
                   (file.name.startswith(f".{options.my_name}_custom_modules_")       and file.suffix.casefold() == ".pkl" ) or \
                   (file.name.startswith(".") and f"-{options.my_name}-" in file.name and file.suffix.casefold() == ".json"):
                    try:
                        logging.info("Deleting %s", file)
                        file.unlink()
                    except BaseException:
                        logging.exception("Error deleting %s", file)
        sys.exit(0)
    elif getattr(options.args, "full", False):  # implied by now: and not options.python_script:
        options.python_script = options.cwd
    else:
        logging.info("You must specify either a script to run or one of these arguments: alias, manual, blank-slate (be careful using blank-slate because it deletes all cached virtual environments, among other things!).")

    if getattr(options.args, "reqs", False):
        parse_extra_requirements(options)
        if not options.rawlog:
            logging.info("Loaded extra requirements from ./%s: %s", options.extra_requirements_file, options.extra_requirements)

    time1 = dt.datetime.now()
    options.custom_modules = dict_of_custom_modules(options)
    time2 = dt.datetime.now()
    elapsed_time = time2 - time1
    if not options.rawlog: logging.info("dict_of_custom_modules() took %s", elapsed_time)

    # Look for files in options.my_dir that start with pip_list and load the most recent one.
    options.pip_list = []
    pip_list_files = sorted([f for f in options.my_dir.iterdir() if f.name.startswith("pip_list")], reverse=True)
    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("pip_list_files = %s", " ".join(os.fspath(f) for f in pip_list_files))
    # If --rc was not specified, look for a text file with the pip list the last time this script was run.
    if not getattr(options.args, "rc", False) and pip_list_files:
        try:
            with open(options.my_dir / pip_list_files[0], "r") as file:
                for line in file:
                    options.pip_list.append(line.strip())
        except BaseException:
            logging.error(f"Error reading {pip_list_files[0]}")

    start_list_packages_time = dt.datetime.now()
    elapsed_time = start_list_packages_time - start_time
    if not options.rawlog: logging.info("Elapsed time: %s", elapsed_time)

    try:
        import pipreqs
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("pipreqs is available, so it will be used.")
        options.pipreqs_available = True
    except ImportError:
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("pipreqs is not available. Try installing it with 'pip install pipreqs'.")
        options.pipreqs_available = False

    list_packages(options)

    if not options.rawlog:
        logging.info("Uninstalled imports: %s", options.uninstalled_imports)
        if options.bad_imports:
            logging.warning("Bad imports: %s", options.bad_imports)
        if options.samedir_files:
            logging.info("Imported files in the same directory as the script: %s", list(map(os.fspath, options.samedir_files)))
        if options.subfolders:
            logging.info("Imported subfolders: %s", options.subfolders)

    if getattr(options.args, "justprint", False):
        ud.print_all_errors(memory_handler, options.rawlog)
        sys.exit(0)

    if not options.uninstalled_imports:
        if not options.rawlog: logging.info("All required packages are already installed.")
        start_raw_time = dt.datetime.now()
        subprocess.run([sys.executable, os.fspath(options.python_script)] + options.script_args)
        elapsed_raw_time = dt.datetime.now() - start_raw_time
        if not options.rawlog: logging.info("Runtime: %s", elapsed_raw_time)
    elif is_virtualenv():
        if not options.rawlog: logging.info("Already in a virtual environment.")
        if check_packages_in_venv(options):
            start_raw_time = dt.datetime.now()
            subprocess.run([sys.executable, os.fspath(options.python_script)] + options.script_args)
            elapsed_raw_time = dt.datetime.now() - start_raw_time
            if not options.rawlog: logging.info("Runtime: %s", elapsed_raw_time)
        else:
            logging.error("The current virtual environment does not have all the required packages.")
            if not options.rawlog: logging.info("Please deactivate the current virtual environment and run the script again.")
    else:
        if getattr(options.args, "no_cache", False):
            match_dir = None
        else:
            match_dir = find_match_dir_in_cache(options)
        if match_dir is None:
            if not options.rawlog: logging.info("Creating new virtual environment '%s'...", options.venv_name)
            if setup_virtualenv(options):
                match_dir        = options.venv_dir
                created_new_venv = True
            else:
                ud.my_critical_error("Failed to create a virtual environment.", choose_breakpoint=True)
        else:
            if not options.rawlog: logging.info("Using existing virtual environment: %s", match_dir)
            created_new_venv = False

        if match_dir:
            options.set_venv_dir(match_dir)
            start_venv_time = dt.datetime.now()
            elapsed_time    = start_venv_time - start_time
            if not options.rawlog: logging.info("Elapsed time: %s", elapsed_time)
            if not getattr(options.args, "full", False):
                command_list = [os.fspath(options.venv_python), os.fspath(options.python_script)] + \
                               [str(arg) for arg in options.script_args]
                if not options.rawlog: logging.info("Running command: %s", " ".join(shlex.quote(arg) for arg in command_list))
                result       = subprocess.run(command_list)
                end_time     = dt.datetime.now()
                elapsed_time = end_time - start_venv_time
                if not options.rawlog: logging.info("Elapsed time since activating virtual environment: %s",
                                                    elapsed_time)
                if result.returncode != 0 and not options.rawlog:
                    logging.error("Error running script: %s", result.stderr)
            if options.venv_dir.name.startswith("failed-") and options.simultaneous_success:
                # If the program has made it to this point, it has run successfully, so the venv directory can be renamed because it DIDN'T fail.
                new = options.venv_dir.with_name(options.venv_dir.name.removeprefix("failed-"))
                if new != options.venv_dir:
                    options.venv_dir.rename(new)
                options.set_venv_dir(new)
                cfg_file_path = options.venv_dir / "pyvenv.cfg"
                with open(cfg_file_path, "r") as file:
                    lines = file.readlines()
                modified_lines = []
                for line in lines:
                    if line.startswith("command = "):
                        line = line.replace(os.sep+"failed-", os.sep)
                    modified_lines.append(line)
                with open(cfg_file_path, "w") as file:
                    file.writelines(modified_lines)
                with open(options.download_script_path, "r") as file:
                    lines = file.readlines()
                modified_lines = []
                for line in lines:
                    line = line.replace(os.sep+"failed-", os.sep)
                    modified_lines.append(line)
                with open(options.download_script_path , "w") as file:
                    file.writelines(modified_lines)

            ud.save_options_to_json(options)

            if getattr(options.args, "full", False):
                built_or_found = "built" if created_new_venv else "found"
                logging.info("Successfully %s a virtual environment that can run all python scripts in %s.\n"
                             "Use this virtual environment:\n%s", built_or_found, options.script_dir, options.venv_dir)

    ud.print_all_errors(memory_handler, options.rawlog)
    logging.shutdown()


def define_alias_command(options: Options) -> None:
    """
    Define the alias command for the shell, store in options.alias_command.

    Args:
        options: Options object containing the alias, python_command, and my_filepath attributes.

    Returns:
        None, but updates options.alias_command with the appropriate alias command string.

    Raises:
        None, but logs an error if no alias is specified or if the shell is unsupported.
    """
    if not options.alias:
        logging.error("No alias specified, skipping alias command generation.")
        options.alias_command = None
        return

    cmd = f"{options.python_command} {options.my_filepath}"
    if options.shell in ["bash", "zsh"]:
        options.alias_command = f'alias {options.alias}="{cmd}"'
    elif options.shell == "fish":
        options.alias_command = (f"function {options.alias};\n"
                                 f"    {cmd} $argv;\n"
                                 f"end")
    elif options.shell in ["csh", "tcsh"]:
        options.alias_command = f"alias {options.alias} '{cmd}'"
    else:
        logging.error(f"Unsupported shell for alias command: {options.shell}")
        options.alias_command = None


def alias_exists(this_file: str | os.PathLike[str], alias_pattern: str) -> bool:
    """
    Check if an alias exists in this_file using a regex pattern "alias_pattern".

    Args:
        this_file:     The file to check for the alias.
        alias_pattern: The regex pattern to match the alias.

    Returns:
        True if the alias exists, False otherwise.

    Raises:
        None, but logs an error if the file cannot be found.
    """
    try:
        with open(this_file, "r") as file:
            lines = file.readlines()
        return any(re.search(alias_pattern, line) for line in lines)
    except FileNotFoundError:
        logging.error(f"File {this_file} not found while checking for alias.")
        return False


def add_alias_to_rc_file(options: Options) -> None:
    """Add an alias to the shell configuration file if it's not already there."""
    if not (options.rc_file and options.alias and options.alias_command):
        logging.error("Missing rc_file, alias, or alias_command. Skipping alias install.")
        return
    all_files = [options.rc_file] + options.additional_alias_files
    alias_name = re.escape(options.alias)
    # Only match alias <name> exactly, with optional spaces around "="
    alias_pattern = rf'^\s*alias\s+{alias_name}(?:\s*=\s*|\s+).+'
    # This "next" function will return the first file that contains the alias, or None if not found.
    found_file = next((f for f in all_files if f and alias_exists(f, alias_pattern)), None)
    if found_file:
        logging.info("Alias %s already exists in %s", options.alias, found_file)
        return
    the_prompt = (f"Type 'yes' or 'y' to write this alias/function:\n\n"
                  f"{options.alias_command}\n\n"
                  f"into {options.rc_file}\n"
                  f"...or anything else to cancel: ")
    try:
        if getattr(options.args, "y", False) or ud.prompt_then_confirm(the_prompt):
            with open(options.rc_file, "a") as f:
                f.write("\n" + options.alias_command + "\n")
            logging.info("Alias added to %s", options.rc_file)
    except OSError:
        logging.exception("Failed to write alias to %s", options.rc_file)
        logging.error(options.manual_instructions)


def add_alias(options: Options) -> None:
    """
    This function detects the shell, finds the appropriate rc file,
    and adds the alias command to it if it doesn't already exist.

    Args:
        options: Options object containing shell type, rc_file, alias, and alias_command attributes.

    Returns:
        None, but updates options.rc_file and options.alias_command as needed.

    Raises:
        None.
    """
    ud.detect_shell(options)
    if options.shell:
        ud.find_shell_rc_file(options)
        ud.find_additional_alias_files(options)
        if options.rc_file:
            define_alias_command(options)
            if options.alias_command:
                add_alias_to_rc_file(options)


def _literal_str(expr_node: ast.AST) -> str | None:
    """Extract a string from an AST node if it is a literal string."""
    if isinstance(expr_node, ast.Constant) and isinstance(expr_node.value, str):
        return expr_node.value
    return None


def get_evaluated_arg(expr_node: ast.AST, default: str = "") -> str:
    """
    Safely pull a string out of an AST node via safe_eval(), or return default.
    """
    val = safe_eval(ast.unparse(expr_node))
    if isinstance(val, str):
        return val
    return default


def _record_IO(options: Options, file_content: str,
               attr: str, target: str, node: ast.Call) -> None:
    """
    Record an IO operation by appending a target to an options attribute
    and logging the operation.

    Args:
        options:      Options object containing attributes for file operations.
        file_content: The content of the file being analyzed.
        attr:         The attribute of options to append the target to (e.g., 'read_files').
        target:       The target file or directory being read/written.
        node:         The AST node representing the operation.

    Returns:
        None, but logs the operation and appends the target to the specified attribute.

    Raises:
        None, but logs an error if the target is not a string or if the node does not have a source segment.
    """
    snippet = ast.get_source_segment(file_content, node) or ""
    if not options.rawlog: logging.info("I/O operation → %s: %r (line %d: %s - found by %s)",
                                        attr, target, node.lineno, snippet.strip(),
                                        ud.return_method_name(levels_up=2))
    if target not in getattr(options, attr):
        getattr(options, attr).append(target)


def _get_full_attr_name(node: ast.AST) -> str | None:
    """
    Recursively walk an ast.Name/ast.Attribute chain
    and return its full dotted name, e.g.:
    Name(id='ZipFile')         -> 'ZipFile'
    Attribute(Name('zipfile'), 'ZipFile')       -> 'zipfile.ZipFile'
    Attribute(Attribute(Name('pkg'), 'zipfile'), 'ZipFile')
        -> 'pkg.zipfile.ZipFile'
    Returns None on anything else.

    Args:
        node: The AST node to analyze, which can be a Name or Attribute.

    Returns:
        A string representing the full dotted name of the node, or None if the node is not a Name or Attribute.

    Raises:
        None, but logs an error if the node is not a Name or Attribute.
    """
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        parent = _get_full_attr_name(node.value)
        if parent:
            return f"{parent}.{node.attr}"
    return None


def unpack_method_call(node: ast.Call) -> tuple[ast.Call, str] | None:
    """
    If 'node' is a call of the form (<something>()).<method>(...),
    return (inner_call, method_name).  Otherwise return None.
    """
    func = node.func
    if not isinstance(func, ast.Attribute):
        return None
    inner = func.value
    if not isinstance(inner, ast.Call):
        return None
    return inner, func.attr


class FileOperationsVisitor(ast.NodeVisitor):
    """Visitor to find file read/write operations in the AST."""

    def __init__(self, options: Options, file_content: str) -> None:
        """Initialize the visitor with options and file content."""
        super().__init__()
        self.options = options
        self.file_content = file_content

    def visit_Call(self, node: ast.Call) -> None:
        """Visit Call nodes to find file operations."""
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("FileVisiting Call node: %s", ast.dump(node))
        if self._process_open(        node): return
        if self._process_pathlib(     node): return
        if self._process_shutil(      node): return
        if self._process_os_open(     node): return
        if self._process_subprocess(  node): return
        if self._process_ctypes_api(  node): return
        if self._process_zipfile(     node): return
        if self._process_tarfile(     node): return
        if self._process_pandas(      node): return
        if self._process_numpy(       node): return
        if self._process_netcdf4(     node): return
        if self._process_xarray(      node): return
        if self._process_json(        node): return
        if self._process_csv(         node): return
        if self._process_yaml(        node): return
        if self._process_configparser(node): return
        if self._process_h5py(        node): return
        if self._process_pillow(      node): return
        if self._process_wave(        node): return
        if self._process_soundfile(   node): return
        if self._process_sqlite(      node): return
        if self._process_gzip(        node): return
        if self._process_bz2(         node): return
        if self._process_unknown_open(node): return
        if self._process_generic_file(node): return
        self.generic_visit(           node)  # Keep digging into the AST

    def _process_open(self, node: ast.Call) -> bool:
        """Process open(...) calls."""
        # Only examine open(...) - (the 'and node.args' protects against calls without arguments)
        if (isinstance(node.func, ast.Name) and node.func.id == "open" and node.args):
            # Extract filename via safe_eval (never raises—returns None on unsupported)
            filename = safe_eval(ast.unparse(node.args[0]))
            for kw in node.keywords:
                if kw.arg == "file":
                    maybe = safe_eval(ast.unparse(kw.value))
                    if maybe:
                        filename = maybe
            # only proceed if we got a real string
            if isinstance(filename, str):
                # Extract mode from positional arg[1] or keyword "mode"
                mode = _literal_str(node.args[1]) if len(node.args) > 1 else None
                for kw in node.keywords:
                    if kw.arg == "mode":
                        maybe = _literal_str(kw.value)
                        if maybe:
                            mode = maybe
                # Default to "r" if not specified and remove "b" if present
                # because we don't care about binary mode.
                mode = (mode or "r").replace("b", "")
                if "r" in mode:
                    _record_IO(self.options, self.file_content, "read_files",
                               filename, node)
                elif any(m in mode for m in ("w", "a", "x")):
                    _record_IO(self.options, self.file_content, "write_files",
                               filename, node)
                return True
        return False

    def _process_pathlib(self, node: ast.Call) -> bool:
        """Process pathlib.Path(...) calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Call)
                and isinstance(node.func.value.func, ast.Attribute)
                and isinstance(node.func.value.func.value, ast.Name)
                and node.func.value.func.value.id == "pathlib"
                and node.func.value.func.attr     == "Path"):
            method = node.func.attr
            # first arg to Path(...) is the filename: evaluate it fully
            if not node.func.value.args:
                return False
            filename = safe_eval(ast.unparse(node.func.value.args[0]))
            if not isinstance(filename, str):
                return False
            # classify
            if method in ("read_text", "read_bytes"):
                _record_IO(self.options, self.file_content, "read_files",
                           filename, node)
                return True
            elif method in ("write_text", "write_bytes", "open"):
                _record_IO(self.options, self.file_content, "write_files",
                           filename, node)
                return True
        return False

    def _process_shutil(self, node: ast.Call) -> bool:
        """Process shutil operations like copy, move, etc."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "shutil"
                and node.func.attr in ("copy", "copy2", "move", "copytree", "rmtree")
                and len(node.args) >= 2):
            src = safe_eval(ast.unparse(node.args[0]))
            dst = safe_eval(ast.unparse(node.args[1]))
            if isinstance(src, str):
                _record_IO(self.options, self.file_content,  "read_files",
                           src, node)
                return True
            if isinstance(dst, str):
                _record_IO(self.options, self.file_content, "write_files",
                           dst, node)
                return True
        return False

    def _process_os_open(self, node: ast.Call) -> bool:
        """Detect os.open(path, flags, [mode]) and record read/write based on flags."""
        if not (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "os"
            and node.func.attr     == "open"
            and node.args
        ):
            return False
        # 2) Extract the filename literal
        filename = safe_eval(ast.unparse(node.args[0]))
        if not isinstance(filename, str):
            return False
        # 3) Parse the flags argument into (can_read, can_write)

        def _parse_flags(fn: ast.AST) -> tuple[bool, bool]:
            """Parse the flags AST node to determine read/write capabilities."""
            # base case: os.O_RDONLY, O_WRONLY, O_RDWR, O_CREAT, O_TRUNC, O_APPEND, O_EXCL
            if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) and fn.value.id == "os":
                f = fn.attr
                if f == "O_RDONLY":
                    return (True, False)
                if f == "O_WRONLY":
                    return (False, True)
                if f == "O_RDWR":
                    return (True, True)
                if f in ("O_CREAT", "O_TRUNC", "O_APPEND", "O_EXCL"):
                    return (False, True)
            # recursive for bitwise ORs: os.O_CREAT | os.O_WRONLY, etc.
            if isinstance(fn, ast.BinOp) and isinstance(fn.op, ast.BitOr):
                left  = _parse_flags(fn.left)
                right = _parse_flags(fn.right)
                return (left[0] or right[0], left[1] or right[1])
            # anything else: assume both
            return (True, True)

        flags_node = node.args[1] if len(node.args) > 1 else None
        can_read, can_write = _parse_flags(flags_node) if flags_node else (True, False)
        # 4) Record into the right lists
        if can_read:
            _record_IO(self.options, self.file_content, "read_files",
                       filename, node)
            return True
        if can_write:
            _record_IO(self.options, self.file_content, "write_files",
                       filename, node)
            return True
        return False

    def _process_subprocess(self, node: ast.Call) -> bool:
        """
        Detect calls that invoke an external shell to read/write files via redirection:
        - subprocess.run()/Popen()/call()/check_output()/etc. with shell=True
        - os.system(), os.popen()

        Parses any ">", ">>" or "<" in the literal command string to pull out filenames.
        """
        # 1) Identify the call as subprocess.* or os.system/os.popen
        is_sub = (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "subprocess"
            and node.func.attr in (
                "run", "Popen", "call",
                "check_output", "check_call",
                "getoutput", "getstatusoutput"
            )
        )
        is_os  = (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "os"
            and node.func.attr in ("system", "popen")
        )
        if not (is_sub or is_os):
            return False

        # 2) Extract the command string (only literal strings get caught)
        cmd = None
        # subprocess: only when shell=True will redirection fire
        if is_sub:
            shell_kw = next(
                (kw for kw in node.keywords
                if kw.arg == "shell"
                and isinstance(kw.value, ast.Constant)
                and isinstance(kw.value.value, bool)
                and kw.value.value),
                None
            )
            if not shell_kw:
                return False
            # look for literal command in args or keywords
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                cmd = node.args[0].value
            else:
                for kw in node.keywords:
                    if kw.arg in ("args", "command") and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        cmd = kw.value.value
                        break

        # os.system / os.popen always use a shell string
        if is_os:
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                cmd = node.args[0].value

        if not cmd:
            return False

        # 3) Scan the command for >, >>, and < redirections
        #    and record each filename we see
        for m in re.finditer(r'(?:^|\s)([<>]{1,2})\s*(\S+)', cmd):
            op, raw = m.groups()
            # strip any trailing shell punctuation
            filename = raw.rstrip(";|&")
            if not filename:
                continue
            attr = "write_files" if ">" in op else "read_files"
            _record_IO(self.options, self.file_content, attr,
                       filename, node)
            return True
        # If we reach here, no redirection was found
        return False

    def _process_ctypes_api(self, node: ast.Call) -> bool:
        """
        Detect direct libc open calls via ctypes (CDLL/pydll/...)
        and record the path literals passed to open/fopen as writes.
        """
        # 1) Must be an attribute call, e.g. (<something>).open(...)
        if not isinstance(node.func, ast.Attribute):
            return False

        # 2) The "something" must itself be a ctypes loader call:
        loader = node.func.value
        if not (
            isinstance(loader, ast.Call)
            and isinstance(loader.func, ast.Attribute)
            and isinstance(loader.func.value, ast.Name)
            and loader.func.value.id == "ctypes"
            and loader.func.attr in ("CDLL", "pydll", "windll", "oledll")
        ):
            return False

        # 3) We only care about open/fopen here (write‐only creation)
        fn = node.func.attr
        if fn not in ("open", "fopen"):
            return False

        # 4) Extract the filename literal from the first argument
        if not node.args:
            return False
        path_node = node.args[0]
        path = _literal_str(path_node)
        if not path:
            return False

        # 5) Record it as a write
        _record_IO(self.options, self.file_content, "write_files",
                   path, node)
        return True

    def _process_zipfile(self, node: ast.Call) -> bool:
        """Process zipfile.ZipFile(...) calls like extract, extractall, open."""
        unpacked = unpack_method_call(node)
        if not unpacked:
            return False
        inner_call, method = unpacked

        full_ctor = _get_full_attr_name(inner_call.func)
        if full_ctor is None or (full_ctor != "ZipFile" and not full_ctor.endswith("zipfile.ZipFile")):
            return False

        filename = get_evaluated_arg(inner_call.args[0])
        mode     = get_evaluated_arg(inner_call.args[1], default="r")
        if not isinstance(filename, str):
            return False

        if mode.startswith("r") and method in ("extract", "extractall", "open"):
            _record_IO(self.options, self.file_content, "read_files",
                       filename, node)
            return True
        elif mode.startswith(("w", "x", "a")):
            _record_IO(self.options, self.file_content, "write_files",
                       filename, node)
            return True
        return False

    def _process_tarfile(self, node: ast.Call) -> bool:
        """Process tarfile.open(...) calls like extract, extractall, open."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "tarfile"
                and node.func.attr     == "open"
                and node.args):
            filename = _literal_str(node.args[0])
            mode     = _literal_str(node.args[1]) if len(node.args) > 1 else "r"
            if filename:
                if mode.startswith("r"):
                    _record_IO(self.options, self.file_content, "read_files",
                               filename, node)
                    return True
                elif mode[0] in ("w", "a", "x"):
                    _record_IO(self.options, self.file_content, "write_files",
                               filename, node)
                    return True
        return False

    def _process_pandas(self, node: ast.Call) -> bool:
        """Process pandas.read_csv/excel, DataFrame.to_csv/excel calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in ("pd", "pandas")):
            fn = node.func.attr
            url = None
            if fn.startswith("read_") and node.args:
                url = _literal_str(node.args[0])
            elif fn.startswith("to_") and node.args:
                url = _literal_str(node.args[0])
            for kw in node.keywords:
                if kw.arg in ("filepath_or_buffer", "path", "path_or_buf"):
                    maybe = _literal_str(kw.value)
                    if maybe:
                        url = maybe
            if url:
                if fn.startswith("read_"):
                    _record_IO(self.options, self.file_content, "read_files",
                               url, node)
                    return True
                elif fn.startswith("to_"):
                    _record_IO(self.options, self.file_content, "write_files",
                               url, node)
                    return True
        return False

    def _process_numpy(self, node: ast.Call) -> bool:
        """Process numpy.load, save, savez, savez_compressed calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in ("np", "numpy")):
            fn = node.func.attr
            if fn in ("load",) and node.args:
                path = _literal_str(node.args[0])
                if path:
                    _record_IO(self.options, self.file_content, "read_files",
                               path, node)
            elif fn in ("save", "savez", "savez_compressed") and node.args:
                path = _literal_str(node.args[0])
                if path:
                    _record_IO(self.options, self.file_content, "write_files",
                               path, node)
                    return True
        return False

    def _process_netcdf4(self, node: ast.Call) -> bool:
        """Process netCDF4.Dataset(...) calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "netCDF4"
                and node.func.attr == "Dataset"
                and node.args):
            filename = _literal_str(node.args[0])
            mode     = _literal_str(node.args[1]) if len(node.args) > 1 else "r"
            if filename:
                if mode.startswith("r"):
                    _record_IO(self.options, self.file_content, "read_files",
                               filename, node)
                else:
                    _record_IO(self.options, self.file_content, "write_files",
                               filename, node)
                return True
        return False

    def _process_xarray(self, node: ast.Call) -> bool:
        """Process xarray.open_dataset/open_dataarray, to_netcdf calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in ("xr", "xarray")):
            fn = node.func.attr
            if fn in ("open_dataset", "open_dataarray") and node.args:
                path = _literal_str(node.args[0])
                if path:
                    _record_IO(self.options, self.file_content, "read_files",
                               path, node)
            elif fn == "to_netcdf" and node.args:
                path = _literal_str(node.args[0])
                for kw in node.keywords:
                    if kw.arg == "path":
                        maybe = _literal_str(kw.value)
                        if maybe:
                            path = maybe
                if path:
                    _record_IO(self.options, self.file_content, "write_files",
                               path, node)
                    return True
        return False

    def _process_json(self, node: ast.Call) -> bool:
        """Process json.load, loads, dump, dumps calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "json"
                and node.func.attr in ("load", "loads", "dump", "dumps")
                and node.args):
            target = _literal_str(node.args[0])
            if target:
                if node.func.attr.startswith("load"):
                    _record_IO(self.options, self.file_content, "read_files",
                               target, node)
                else:
                    _record_IO(self.options, self.file_content, "write_files",
                               target, node)
                return True
        return False

    def _process_csv(self, node: ast.Call) -> bool:
        """Process csv.reader, writer calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "csv"
                and node.func.attr in ("reader", "writer")
                and node.args):
            target = _literal_str(node.args[0])
            if target:
                if node.func.attr == "reader":
                    _record_IO(self.options, self.file_content,  "read_files",
                               target, node)
                else:
                    _record_IO(self.options, self.file_content, "write_files",
                               target, node)
                return True
        return False

    def _process_yaml(self, node: ast.Call) -> bool:
        """Process yaml.safe_load, load, dump calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in ("yaml", "ruamel.yaml")
                and node.func.attr in ("safe_load", "load", "dump")
                and node.args):
            target = _literal_str(node.args[-1])
            if target:
                if node.func.attr in ("safe_load", "load"):
                    _record_IO(self.options, self.file_content,  "read_files",
                               target, node)
                else:
                    _record_IO(self.options, self.file_content, "write_files",
                               target, node)
                return True
        return False

    def _process_configparser(self, node: ast.Call) -> bool:
        """Process configparser.ConfigParser(...) calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Call)
                and isinstance(node.func.value.func, ast.Attribute)
                and isinstance(node.func.value.func.value, ast.Name)
                and node.func.value.func.value.id == "configparser"
                and node.func.value.func.attr == "ConfigParser"):  # constructor
            mode_call = node.func.attr
            if mode_call == "read" and node.args:
                fp = _literal_str(node.args[0])
                if fp:
                    _record_IO(self.options, self.file_content, "read_files",
                               fp, node)
                    return True
            elif mode_call == "write" and node.args:
                fp = _literal_str(node.args[0])
                if fp:
                    _record_IO(self.options, self.file_content, "write_files",
                               fp, node)
                    return True
        return False

    def _process_h5py(self, node: ast.Call) -> bool:
        """Process h5py.File(...) calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "h5py"
                and node.func.attr == "File"
                and node.args):
            fn = _literal_str(node.args[0])
            mode = _literal_str(node.args[1]) if len(node.args) > 1 else "r"
            if fn:
                if mode.startswith("r"):
                    _record_IO(self.options, self.file_content, "read_files",
                               fn, node)
                else:
                    _record_IO(self.options, self.file_content, "write_files",
                               fn, node)
                return True
        return False

    def _process_pillow(self, node: ast.Call) -> bool:
        """Process PIL.Image.open, save calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "Image"):
            if node.func.attr == "open" and node.args:
                fp = _literal_str(node.args[0])
                if fp:
                    _record_IO(self.options, self.file_content, "read_files",
                               fp, node)
                    return True
            elif node.func.attr == "save" and node.args:
                fp = _literal_str(node.args[0])
                if fp:
                    _record_IO(self.options, self.file_content, "write_files",
                               fp, node)
                    return True
        return False

    def _process_wave(self, node: ast.Call) -> bool:
        """Process wave.open(...) calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "wave"
                and node.func.attr == "open"
                and node.args):
            fn = _literal_str(node.args[0])
            mode = _literal_str(node.args[1]) if len(node.args) > 1 else "rb"
            if fn:
                if mode.startswith("r"):
                    _record_IO(self.options, self.file_content, "read_files",
                               fn, node)
                else:
                    _record_IO(self.options, self.file_content, "write_files",
                               fn, node)
                return True
        return False

    def _process_soundfile(self, node: ast.Call) -> bool:
        """Process soundfile.read, write calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "soundfile"
                and node.func.attr in ("read", "write")
                and node.args):
            fn = _literal_str(node.args[0])
            if fn:
                if node.func.attr == "read":
                    _record_IO(self.options, self.file_content, "read_files",
                               fn, node)
                else:
                    _record_IO(self.options, self.file_content, "write_files",
                               fn, node)
                return True
        return False

    def _process_sqlite(self, node: ast.Call) -> bool:
        """Process sqlite3.connect(...) calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "sqlite3"
                and node.func.attr == "connect"
                and node.args):
            fn = _literal_str(node.args[0])
            if fn:
                _record_IO(self.options, self.file_content, "read_files",
                           fn, node)
                return True
        return False

    def _process_gzip(self, node: ast.Call) -> bool:
        """Process gzip.open(...) calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "gzip"
                and node.func.attr == "open"
                and node.args):
            fn = _literal_str(node.args[0])
            mode = _literal_str(node.args[1]) if len(node.args) > 1 else "rb"
            if fn:
                if mode.startswith("r"):
                    _record_IO(self.options, self.file_content, "read_files",
                               fn, node)
                else:
                    _record_IO(self.options, self.file_content, "write_files",
                               fn, node)
                return True
        return False

    def _process_bz2(self, node: ast.Call) -> bool:
        """Process bz2.open(...) calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "bz2"
                and node.func.attr == "open"
                and node.args):
            fn = _literal_str(node.args[0])
            mode = _literal_str(node.args[1]) if len(node.args) > 1 else "rb"
            if fn:
                if mode.startswith("r"):
                    _record_IO(self.options, self.file_content, "read_files",
                               fn, node)
                else:
                    _record_IO(self.options, self.file_content, "write_files",
                               fn, node)
                return True
        return False

    _KNOWN_OPEN_MODULES = {
        "open",       # built-in open (covered by _process_open)
        "pathlib",    # pathlib.Path.open
        "os",         # os.open
        "zipfile",    # zipfile.ZipFile()
        "tarfile",    # tarfile.open
        "gzip", "bz2"  # gzip.open, bz2.open
    }

    def _process_unknown_open(self, node: ast.Call) -> bool:
        """
        Heuristic catch-all for any MODULE.open(path, mode) calls
        on unknown modules that we haven't explicitly handled.
        """
        # 1) Must look like MODULE.open(...)
        if not (isinstance(node.func, ast.Attribute)
                and node.func.attr == "open"
                and node.args
                and isinstance(node.func.value, ast.Name)):
            return False

        mod = node.func.value.id
        # 2) Skip the ones we already handle
        if mod in self._KNOWN_OPEN_MODULES:
            return False

        # 3) Extract filename literal
        filename = _literal_str(node.args[0])
        if not filename:
            return False

        # 4) Extract mode literal if present
        mode = _literal_str(node.args[1]) if len(node.args) > 1 else None
        for kw in node.keywords:
            if kw.arg == "mode":
                maybe = _literal_str(kw.value)
                if maybe:
                    mode = maybe

        # 5) Default to "r", strip binary flag
        mode = (mode or "r").replace("b", "")

        # 6) Record
        if "r" in mode:
            _record_IO(self.options, self.file_content, "read_files",
                       filename, node)
            return True
        elif any(m in mode for m in ("w", "a", "x")):
            _record_IO(self.options, self.file_content, "write_files",
                       filename, node)
            return True
        return False

    def _process_generic_file(self, node: ast.Call) -> bool:
        """
        Heuristic fallback: if a function call takes a string literal
        that *looks* like a path, and the function name contains
        typical I/O verbs, record it.
        """
        # Must have at least one literal-string arg:
        if not node.args:
            return False
        candidate = _literal_str(node.args[0])
        if not candidate:
            return False

        # Check for path-like content:
        has_path_chars = any(sep in candidate for sep in ("/", "\\"))
        has_ext = "." in candidate and len(candidate.rsplit(".", 1)[-1]) <= 5
        if not (has_path_chars or has_ext):
            return False

        # Look for I/O-related function names:
        fn = None
        if isinstance(node.func, ast.Name):
            fn = node.func.id.casefold()
        elif isinstance(node.func, ast.Attribute):
            fn = node.func.attr.casefold()

        if fn and any(verb in fn for verb in ("open", "read", "write", "load", "save")):
            # If we see "read" or "load" in the name, treat it as read:
            mode = "read"       if any(fn.startswith(v) for v in ("read", "load")) else "write"
            attr = "read_files" if mode == "read"                                 else "write_files"
            _record_IO(self.options, self.file_content, attr,
                       candidate, node)
            return True
        return False


class TopLevelFileOperationsVisitor(FileOperationsVisitor):
    """
    Only look at calls at module scope — never descend into function defs.
    For classes, only inspect statements in the class body that are not defs or sub-classes.
    This is to avoid collecting file operations from within function bodies or class methods.
    """

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit FunctionDef nodes to find file operations. In practice,
        drop into nothing: stops recursion into function bodies"""
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit AsyncFunctionDef nodes to find file operations. In practice,
        drop into nothing: stops recursion into function bodies"""
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit ClassDef nodes to find file operations. In practice,
        only inspect statements in the class body that are not defs or sub-classes."""
        for stmt in node.body:
            if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.visit(stmt)


class NetworkOperationsVisitor(ast.NodeVisitor):
    """Visitor to find network operations in the AST."""

    def __init__(self, options: Options, file_content: str) -> None:
        """Initialize the visitor with options and file content."""
        super().__init__()
        self.options = options
        self.file_content = file_content

    def visit_Call(self, node: ast.Call) -> None:
        """Visit Call nodes to find network operations."""
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("NetworkVisiting Call node: %s", ast.dump(node))
        if self._process_requests(       node): return
        if self._process_urllib(         node): return
        if self._process_ftp(            node): return
        if self._process_httpx(          node): return
        if self._process_aiohttp(        node): return
        if self._process_socket(         node): return
        if self._process_http_client(    node): return
        if self._process_urllib3(        node): return
        if self._process_smtplib(        node): return
        if self._process_imaplib(        node): return
        if self._process_boto3(          node): return
        if self._process_paramiko(       node): return
        if self._process_requests_ftp(   node): return
        if self._process_websockets(     node): return
        if self._process_socketio(       node): return
        if self._process_mqtt(           node): return
        if self._process_grpc(           node): return
        if self._process_psycopg2(       node): return
        if self._process_redis(          node): return
        # if self._process_generic_network(node): return  # Too many false positives!
        self.generic_visit(              node)  # Keep digging into the AST

    def _process_requests(self, node: ast.Call) -> bool:
        """Process requests.get/post/put/...(...) calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.args  # protect against calls without arguments
                and node.func.value.id == "requests"
                and node.func.attr in ("get", "options", "head", "post",
                                    "put", "patch", "delete")):
            # Extract URL from arg[0] or keyword "url"
            url = _literal_str(node.args[0])
            for kw in node.keywords:
                if kw.arg == "url":
                    maybe = _literal_str(kw.value)
                    if maybe:
                        url = maybe
            if url:
                if node.func.attr == "get":
                    _record_IO(self.options, self.file_content, "download_urls",
                               url, node)
                else:
                    _record_IO(self.options, self.file_content,   "upload_urls",
                               url, node)
                return True
        return False

    def _process_urllib(self, node: ast.Call) -> bool:
        """Process urllib.request.urlopen(...) and urllib.request.Request(...) calls."""
        if (isinstance(node.func, ast.Attribute)
                and node.args  # protect against calls without arguments
                and isinstance(node.func.value, ast.Attribute)
                and node.func.attr in ("urlopen", "Request")):
            url = _literal_str(node.args[0])
            for kw in node.keywords:
                if kw.arg == "url":
                    maybe = _literal_str(kw.value)
                    if maybe:
                        url = maybe
            if url:
                _record_IO(self.options, self.file_content, "download_urls",
                           url, node)
                return True
        return False

    def _process_ftp(self, node: ast.Call) -> bool:
        """Process ftplib.FTP.retrbinary/storbinary/retrlines/storlines(...) calls."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Call)
                and isinstance(node.func.value.func, ast.Attribute)
                and isinstance(node.func.value.func.value, ast.Name)
                and node.func.value.func.value.id == "ftplib"
                and node.func.value.func.attr == "FTP"
                and node.args):
            cmd = _literal_str(node.args[0])
            if not cmd:
                return False
            parts = cmd.split()
            if len(parts) < 2:
                return False
            filename = parts[1]
            op = node.func.attr.casefold()
            if op in ("retrbinary", "retrlines"):
                # remote-to-local: treat as read
                _record_IO(self.options, self.file_content,  "read_files",
                           filename, node)
                return True
            elif op in ("storbinary", "storlines"):
                # local-to-remote: treat as write
                _record_IO(self.options, self.file_content, "write_files",
                           filename, node)
                return True
        return False

    def _process_httpx(self, node: ast.Call) -> bool:
        """Process httpx.get/post/put/...(...) and httpx.request(method, url) calls."""
        # httpx.get/post/...() and httpx.request(method, url)
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "httpx"
                and node.func.attr in ("get", "options", "head", "post", "put", "patch", "delete")
                and node.args):
            url = _literal_str(node.args[0])
            for kw in node.keywords:
                if kw.arg == "url":
                    maybe = _literal_str(kw.value)
                    if maybe:
                        url = maybe
            if url:
                if node.func.attr == "get":
                    _record_IO(self.options, self.file_content, "download_urls",
                               url, node)
                else:
                    _record_IO(self.options, self.file_content,   "upload_urls",
                               url, node)
                return True
        # handle httpx.request(method, url)
        elif (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "httpx"
                and node.func.attr == "request"
                and node.args and len(node.args) >= 2):
            method = _literal_str(node.args[0])
            url = _literal_str(node.args[1])
            for kw in node.keywords:
                if kw.arg == "method":
                    maybe = _literal_str(kw.value)
                    if maybe:
                        method = maybe
                if kw.arg == "url":
                    maybe = _literal_str(kw.value)
                    if maybe:
                        url = maybe
            if url:
                method = (method or "").casefold()
                if method == "get":
                    _record_IO(self.options, self.file_content, "download_urls",
                               url, node)
                else:
                    _record_IO(self.options, self.file_content,   "upload_urls",
                               url, node)
                return True
        return False

    def _process_aiohttp(self, node: ast.Call) -> bool:
        """Process aiohttp.request(...) and session.get/post/... calls."""
        # static aiohttp.request
        if (isinstance(node.func, ast.Name)
                and node.func.id == "request"
                and node.args and len(node.args) >= 2):
            method = _literal_str(node.args[0])
            url = _literal_str(node.args[1])
            for kw in node.keywords:
                if kw.arg == "method":
                    maybe = _literal_str(kw.value)
                    if maybe:
                        method = maybe
                if kw.arg == "url":
                    maybe = _literal_str(kw.value)
                    if maybe:
                        url = maybe
            if url:
                method = (method or "").casefold()
                if method == "get":
                    _record_IO(self.options, self.file_content, "download_urls",
                               url, node)
                else:
                    _record_IO(self.options, self.file_content,   "upload_urls",
                               url, node)
                return True
        # session-based calls: session.get/post/etc.
        elif (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.attr in ("get", "options", "head", "post", "put", "patch", "delete")
                and node.args):
            # e.g. session.get(url)
            url = _literal_str(node.args[0])
            for kw in node.keywords:
                if kw.arg == "url":
                    maybe = _literal_str(kw.value)
                    if maybe:
                        url = maybe
            if url:
                if node.func.attr == "get":
                    _record_IO(self.options, self.file_content, "download_urls",
                               url, node)
                else:
                    _record_IO(self.options, self.file_content,   "upload_urls",
                               url, node)
                return True
        return False

    def _process_socket(self, node: ast.Call) -> bool:
        """Process socket operations like create_connection, connect, send, recv."""
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "socket"
                and node.func.attr in ("create_connection", "connect", "send", "recv")
                and node.args):
            # for connect/create_connection, the first arg is (host, port)
            snippet = ast.get_source_segment(self.file_content, node) or ""
            _record_IO(self.options, self.file_content, "download_urls"
                       if node.func.attr in ("recv",) else "upload_urls",
                       snippet.strip(), node)
            return True
        return False

    def _process_http_client(self, node: ast.Call) -> bool:
        """Process http.client HTTPConnection().request calls."""
        unpacked = unpack_method_call(node)
        if not unpacked:
            return False
        inner_call, method_name = unpacked

        full_name = _get_full_attr_name(inner_call.func)
        if full_name is None or not (
            full_name == "HTTPConnection"
            or full_name.endswith(".HTTPConnection")
        ):
            return False

        if method_name != "request" or len(inner_call.args) < 2:
            return False

        method = _literal_str(inner_call.args[0]) or ""
        url = _literal_str(inner_call.args[1]) or ""
        kind = "download_urls" if method.casefold() == "get" else "upload_urls"
        _record_IO(self.options, self.file_content, kind,
                   url, node)
        return True

    def _process_urllib3(self, node: ast.Call) -> bool:
        """Process urllib3 requests (PoolManager().request)."""
        unpacked = unpack_method_call(node)
        if not unpacked:
            return False
        inner_call, method_name = unpacked

        full_name = _get_full_attr_name(inner_call.func)
        # must be exactly "PoolManager" or end with ".PoolManager"
        if full_name is None or not (
            full_name == "PoolManager"
            or full_name.endswith(".PoolManager")
        ):
            return False

        if method_name != "request" or len(inner_call.args) < 2:
            return False

        method = _literal_str(inner_call.args[0]) or ""
        url = _literal_str(inner_call.args[1]) or ""
        kind = "download_urls" if method.casefold() == "get" else "upload_urls"
        _record_IO(self.options, self.file_content, kind,
                   url, node)
        return True

    def _process_smtplib(self, node: ast.Call) -> bool:
        """Process smtplib SMTP.sendmail calls."""
        unpacked = unpack_method_call(node)
        if not unpacked:
            return False
        inner_call, method = unpacked

        # Match the constructor
        ctor = inner_call.func
        full_name = _get_full_attr_name(ctor)
        if full_name is None or not (
            full_name == "SMTP"
            or full_name.endswith("smtplib.SMTP")
        ):
            return False

        # Only sendmail + ≥3 args
        if method != "sendmail" or len(inner_call.args) < 3:
            return False

        to_addrs = ast.get_source_segment(self.file_content, inner_call.args[1]) or ""
        _record_IO(self.options, self.file_content, "upload_urls",
                   to_addrs, node)
        return True

    def _process_imaplib(self, node: ast.Call) -> bool:
        """Process imaplib operations (IMAP4/IMAP4_SSL().fetch/login/select)."""
        unpacked = unpack_method_call(node)
        if not unpacked:
            return False
        inner_call, method = unpacked

        full_name = _get_full_attr_name(inner_call.func)
        if full_name is None or not (
            full_name in ("IMAP4", "IMAP4_SSL")
            or full_name.endswith(".IMAP4")
            or full_name.endswith(".IMAP4_SSL")
        ):
            return False

        if method not in ("fetch", "login", "select") or not inner_call.args:
            return False

        snippet = ast.get_source_segment(self.file_content, inner_call.args[0]) or ""
        _record_IO(self.options, self.file_content, "download_urls",
                   snippet, node)
        return True

    def _process_boto3(self, node: ast.Call) -> bool:
        """Process boto3 S3 operations (...client().download_file/upload_file)."""
        unpacked = unpack_method_call(node)
        if not unpacked:
            return False
        inner_call, method = unpacked

        full_name = _get_full_attr_name(inner_call.func)
        # must be exactly "client" or end with ".client"
        if full_name is None or not (
            full_name == "client"
            or full_name.endswith(".client")
        ):
            return False

        if method not in ("download_file", "upload_file") or len(inner_call.args) < 3:
            return False

        fn = _literal_str(inner_call.args[2])
        if not fn:
            return False

        kind = "download_urls" if method == "download_file" else "upload_urls"
        _record_IO(self.options, self.file_content, kind,
                   fn, node)
        return True

    def _process_paramiko(self, node: ast.Call) -> bool:
        """Process paramiko SFTP operations (...open_sftp().get/put...)."""
        # 1) unpack the method call
        unpacked = unpack_method_call(node)
        if not unpacked:
            return False
        inner_call, method = unpacked

        # 2) match the constructor name
        full_name = _get_full_attr_name(inner_call.func)
        if full_name is None or not (
            full_name == "open_sftp"
            or full_name.endswith(".open_sftp")
        ):
            return False

        # 3) only handle .get or .put
        if method not in ("get", "put"):
            return False

        # 4) extract the local filename argument
        local = get_evaluated_arg(inner_call.args[1] if method == "get" else inner_call.args[0])
        if not local:
            return False

        # 5) record I/O
        kind = "download_urls" if method == "get" else "upload_urls"
        _record_IO(self.options, self.file_content, kind,
                   local, node)
        return True

    def _process_requests_ftp(self, node: ast.Call) -> bool:
        """Process requests_ftp operations."""
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "requests_ftp"
            and node.func.attr in ("get", "post", "put", "delete")
            and node.args
        ):
            url = _literal_str(node.args[0])
            if url:
                kind = "download_urls" if node.func.attr == "get" else "upload_urls"
                _record_IO(self.options, self.file_content, kind,
                           url, node)
                return True
        return False

    def _process_websockets(self, node: ast.Call) -> bool:
        """Process websockets.connect(...) calls."""
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "websockets"
            and node.func.attr == "connect"
            and node.args
        ):
            url = _literal_str(node.args[0])
            if url:
                _record_IO(self.options, self.file_content, "download_urls",
                           url, node)
                return True
        return False

    def _process_socketio(self, node: ast.Call) -> bool:
        """Process socketio.Client().connect(...) or emit(...) calls."""
        unpacked = unpack_method_call(node)
        if not unpacked:
            return False
        inner_call, method = unpacked

        full_name = _get_full_attr_name(inner_call.func)
        if full_name is None or not (
            full_name == "Client"
            or full_name.endswith(".Client")
        ):
            return False

        if method not in ("connect", "emit") or not inner_call.args:
            return False

        target = _literal_str(inner_call.args[0])
        if not target:
            return False

        kind = "download_urls" if method == "connect" else "upload_urls"
        _record_IO(self.options, self.file_content, kind,
                   target, node)
        return True

    def _process_mqtt(self, node: ast.Call) -> bool:
        """Process paho.mqtt.client.Client().connect(...) calls."""
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Call)
            and isinstance(node.func.value.func, ast.Attribute)
            and node.func.value.func.attr == "Client"
            and node.func.attr in ("connect", "publish", "subscribe")
            and node.args
        ):
            # first arg for connect is host, for others topic
            target = _literal_str(node.args[0])
            if target:
                kind = "download_urls" if node.func.attr == "subscribe" else "upload_urls"
                _record_IO(self.options, self.file_content, kind,
                           target, node)
                return True
        return False

    def _process_grpc(self, node: ast.Call) -> bool:
        """Process grpc.insecure_channel(...) or grpc.secure_channel(...) calls."""
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "grpc"
            and node.func.attr in ("insecure_channel", "secure_channel")
            and node.args
        ):
            target = _literal_str(node.args[0])
            if target:
                _record_IO(self.options, self.file_content, "download_urls",
                           target, node)
                return True
        return False

    def _process_psycopg2(self, node: ast.Call) -> bool:
        """Process psycopg2.connect(...) calls."""
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "psycopg2"
            and node.func.attr == "connect"
            and node.args
        ):
            target = _literal_str(node.args[0])
            if target:
                _record_IO(self.options, self.file_content, "download_urls",
                           target, node)
                return True
        return False

    def _process_redis(self, node: ast.Call) -> bool:
        """Process redis.Redis(...) calls."""
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "redis"
            and node.func.attr == "Redis"
        ):
            # look for host kwarg
            host = None
            for kw in node.keywords:
                if kw.arg == "host":
                    host = _literal_str(kw.value)
            if host:
                _record_IO(self.options, self.file_content, "download_urls",
                           host, node)
                return True
        return False

    def _process_generic_network(self, node: ast.Call) -> bool:
        """
        Heuristic fallback: if a call's first argument is a string literal
        that looks like a URL (http:// or https://), record it.
        """
        if not node.args:
            return False
        candidate = _literal_str(node.args[0])
        if not candidate:
            return False

        # Simple URL check:
        if candidate.startswith(("http://", "https://", "ftp://")):
            # If the function name starts with "get", assume download:
            fn = node.func.attr.casefold() if isinstance(node.func, ast.Attribute) else ""
            kind = "download_urls" if fn.startswith("get") else "upload_urls"
            _record_IO(self.options, self.file_content, kind,
                       candidate, node)
            return True
        return False


class TopLevelNetworkOperationsVisitor(NetworkOperationsVisitor):
    """
    Only look at calls at module scope — never descend into function defs.
    For classes, only inspect statements in the class body that are not defs or sub-classes.
    This is to avoid collecting network operations from within function bodies or class methods.
    """

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit FunctionDef nodes to find file operations. In practice,
        drop into nothing: stops recursion into function bodies."""
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit AsyncFunctionDef nodes to find file operations. In practice,
        drop into nothing: stops recursion into function bodies."""
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit ClassDef nodes to find file operations. In practice,
        only inspect statements in the class body that are not defs or sub-classes."""
        for stmt in node.body:
            if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.visit(stmt)


# ---- pathlib class sets ----
PATHLIB_CONCRETE = {"Path", "PosixPath", "WindowsPath"}
PATHLIB_PURE     = {"PurePath", "PurePosixPath", "PureWindowsPath"}
PATHLIB_ALL      = PATHLIB_CONCRETE | PATHLIB_PURE


def collect_pathlib_aliases(module: ast.Module) -> set[str]:
    """
    Return the set of local names that refer to pathlib classes (Path/PosixPath/WindowsPath and Pure*).
    Handles aliasing via 'as'.
    Works even if imports are nested; we just scan the whole tree.
    """
    aliases: set[str] = set()
    for node in ast.walk(module):
        if isinstance(node, ast.ImportFrom) and node.module == "pathlib":
            for alias in node.names:
                if alias.name in PATHLIB_ALL:
                    aliases.add(alias.asname or alias.name)
    return aliases


def is_pathlib_ctor(fn: ast.AST, pathlib_aliases: set[str], allow_pure: bool) -> bool:
    """
    True if 'fn' is a constructor for a pathlib *Path* type.
    - When allow_pure=False, only concrete (filesystem) paths are allowed.
    - When allow_pure=True, accept both concrete and pure paths.
    """
    allowed = PATHLIB_CONCRETE | (PATHLIB_PURE if allow_pure else set())

    # Case: Name (possibly aliased import) e.g., Path(...), P(...), PurePath(...)
    if isinstance(fn, ast.Name):
        if fn.id in allowed or fn.id in pathlib_aliases:
            return True

    # Case: attribute like pathlib.Path(...), pathlib.PurePath(...)
    if (
        isinstance(fn, ast.Attribute)
        and isinstance(fn.value, ast.Name)
        and fn.value.id == "pathlib"
        and fn.attr in allowed
    ):
        return True

    return False


def transform_call(node: ast.Call, pathlib_aliases: set[str]) -> str | None:
    """
    Return a replacement string if this call matches one of our handled patterns,
    or None to leave it unchanged.
    """

    # Handle: pathlib.Path(...).resolve()/absolute()
    if isinstance(node.func, ast.Attribute) and node.func.attr in {"resolve", "absolute"}:
        func = node.func
        if isinstance(func.value, ast.Call):
            inner = func.value
            if is_pathlib_ctor(inner.func, pathlib_aliases, allow_pure=False) and len(inner.args) == 1:
                arg = _safe_eval_node(inner.args[0], pathlib_aliases=pathlib_aliases)
                if isinstance(arg, str):
                    # Recompute using canonical 'Path' and same method name
                    return str(getattr(Path(arg), func.attr)())

    # Handle: pathlib.Path(...).joinpath(...)
    if isinstance(node.func, ast.Attribute) and node.func.attr == "joinpath":
        func = node.func
        if isinstance(func.value, ast.Call):
            inner = func.value
            if is_pathlib_ctor(inner.func, pathlib_aliases, allow_pure=True) and len(inner.args) == 1:
                base  =  _safe_eval_node(inner.args[0], pathlib_aliases=pathlib_aliases)
                parts = [_safe_eval_node(a,             pathlib_aliases=pathlib_aliases) for a in node.args]
                if isinstance(base, str) and all(isinstance(p, str) for p in parts):
                    return os.fspath(Path(base).joinpath(*parts))

    return None


def _safe_eval_node(node: ast.AST, pathlib_aliases: set[str] | None = None) -> Any:
    """
    Recursively evaluate a restricted subset of AST nodes:
    - Constants (strings, numbers, booleans, None)
    - Lists, tuples, dicts
    - os.getcwd()
    - os.path.(abspath|join|dirname|realpath)(<literal strings>)
    - pathlib.Path(<literal strings>).(resolve|absolute)() and .joinpath(<literal strings>...)
    - The "/" operator for joining pathlib Paths.

    Args:
        node:            The AST node to evaluate.
        pathlib_aliases: Optional set of local names that refer to pathlib classes.
    
    Returns:
        The evaluated Python object.
    
    Raises:
        ValueError: If the node contains unsupported syntax.
    """
    aliases = pathlib_aliases or set()
    # --- support "/" operator for path-like objects ---
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left  = _safe_eval_node(node.left, pathlib_aliases=aliases)
        right = _safe_eval_node(node.right, pathlib_aliases=aliases)
        # accept strings or any PathLike (Path, etc.)
        if isinstance(left, (str, os.PathLike)) and isinstance(right, (str, os.PathLike)):
            # Path(left) / right → Path; str(...) to get the string path
            return os.fspath(Path(left) / right)
        raise ValueError(f"Unsupported path division: {ast.unparse(node)}")

    # --- literals ---
    if isinstance(node, ast.Constant):
        # Python 3.8+: Constant covers str, int, float, bool, None
        return node.value

    # --- composite literals ---
    if isinstance(node, ast.List):
        return [_safe_eval_node(elt, pathlib_aliases=aliases) for elt in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_safe_eval_node(elt, pathlib_aliases=aliases) for elt in node.elts)
    if isinstance(node, ast.Dict):
        return {
            _safe_eval_node(k, pathlib_aliases=aliases): _safe_eval_node(v, pathlib_aliases=aliases)
            for k, v in zip(node.keys, node.values)
        }

    # --- calls ---
    if isinstance(node, ast.Call):
        func = node.func

        # os.getcwd()
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "os"
            and func.attr == "getcwd"
            and len(node.args) == 0
        ):
            return os.getcwd()

        # os.path.* calls
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "path"
            and isinstance(func.value.value, ast.Name)
            and func.value.value.id == "os"
        ):
            method = func.attr
            allowed = {"abspath", "join", "dirname", "realpath"}
            if method in allowed:
                arg_vals = [_safe_eval_node(arg, pathlib_aliases=aliases) for arg in node.args]
                if all(isinstance(v, str) for v in arg_vals):
                    path_fn = getattr(os.path, method)
                    return path_fn(*arg_vals)

        # pathlib.Path(...).resolve()/absolute()
        if isinstance(node.func, ast.Attribute) and node.func.attr in {"resolve", "absolute"}:
            func = node.func
            if isinstance(func.value, ast.Call):
                inner = func.value
                if is_pathlib_ctor(inner.func, aliases, allow_pure=False) and len(inner.args) == 1:
                    arg = _safe_eval_node(inner.args[0], pathlib_aliases=aliases)
                    if isinstance(arg, str):
                        # Recompute using canonical 'Path' and same method name
                        return os.fspath(getattr(Path(arg), func.attr)())

        # pathlib.Path(...).joinpath(...)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "joinpath":
            func = node.func
            if isinstance(func.value, ast.Call):
                inner = func.value
                if is_pathlib_ctor(inner.func, aliases, allow_pure=True) and len(inner.args) == 1:
                    base  =  _safe_eval_node(inner.args[0], pathlib_aliases=aliases)
                    parts = [_safe_eval_node(a,             pathlib_aliases=aliases) for a in node.args]
                    if isinstance(base, str) and all(isinstance(p, str) for p in parts):
                        return os.fspath(Path(base).joinpath(*parts))

        # unsupported call
        raise ValueError(f"Unsupported call: {ast.unparse(node)}")

    # anything else is disallowed
    raise ValueError(f"Unsupported expression: {ast.dump(node)}")


def safe_eval(expr: str, pathlib_aliases: set[str] | None = None) -> Any | None:
    """
    Safely evaluate a Python expression string containing only:
        - literals (str, int, float, bool, None)
        - lists, tuples, dicts of the above
        - os.getcwd()
        - os.path.(abspath|join|dirname|realpath)(<literal strings>)
        - pathlib.Path(<literal strings>).(resolve|absolute)() and
          .joinpath(<literal strings>...) and the "/" operator for joining paths.
        - The "/" operator for joining pathlib Paths.

    Args:
        expr:            The expression string to evaluate.
        pathlib_aliases: Optional set of local names that refer to pathlib classes.

    Returns:
        The evaluated Python object, or None on unsupported syntax.

    Raises:
        None: All errors are caught and None is returned.
    """
    try:
        # Parse in "eval" mode so we get an Expression node
        tree = ast.parse(expr, mode="eval")
        return _safe_eval_node(tree.body, pathlib_aliases=pathlib_aliases)  # tree.body is the root expr
    except (SyntaxError, ValueError) as e:
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("%s: Unsupported expression: %r: %s", ud.return_method_name(), expr, e)
        return None


class SysPathVisitor(ast.NodeVisitor):
    """Visitor class to extract sys.path modifications."""

    def __init__(self, pathlib_aliases: set[str] | None = None) -> None:
        """Initialize the sys.path visitor."""
        self.paths = set()
        self._aliases = pathlib_aliases or set()

    def visit_Assign(self, node: ast.Assign) -> None:
        """Visit an assignment statement and check if it's modifying sys.path."""
        if node.targets and isinstance(node.targets[0], ast.Attribute) and \
        isinstance(node.targets[0].value, ast.Name) and \
        node.targets[0].value.id == "sys" and \
        node.targets[0].attr     == "path":
            paths = safe_eval(ast.unparse(node.value), pathlib_aliases=self._aliases)
            if isinstance(paths, list):
                for path in paths:
                    self.paths.add(path)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Visit a function call and check if it's modifying sys.path."""
        if isinstance(node.func,             ast.Attribute) and \
           isinstance(node.func.value,       ast.Attribute) and \
           isinstance(node.func.value.value, ast.Name     ) and \
           node.func.value.value.id == "sys" and \
           node.func.value.attr == "path" and \
           node.func.attr in {"append", "insert"}:
            if node.args and (path := safe_eval(ast.unparse(node.args[-1]), pathlib_aliases=self._aliases)):
                self.paths.add(path)
        self.generic_visit(node)


def process_import(options: Options, module_name: str, file_path: str | os.PathLike[str]) -> bool:
    """Process an import by checking if it's a local custom module or a standard import, and handle it accordingly."""
    if module_name in options.standard_modules:
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Skipping standard library import: %s", module_name)
        return False

    file_path = ud.ensure_file(file_path)

    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Processing import: %s from file %s", module_name, file_path)

    base_dir        = file_path.parent
    module_path_str = module_name.replace(".", os.sep)

    # Avoid loopback to the same file
    if module_name == file_path.stem:
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Avoiding loopback to the same file: %s", module_name)
        return False
    if module_name == "pipreqs" and f"{options.my_name}.py" in str(file_path):
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Avoiding loopback to pipreqs in %s.py", options.my_name)
        return False
    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Constructed module path: %s", module_path_str)

    # Check if the import is a .py file in the same directory
    potential_file_path = (base_dir / f"{module_path_str}.py").expanduser().resolve()
    if ud.safe_is_file(potential_file_path) and potential_file_path not in options.samedir_files:
        options.custom_modules[module_name] = potential_file_path
        options.loaded_custom_modules.add(module_name)
        options.samedir_files.append(potential_file_path)
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Added same directory file: %s", potential_file_path)
        return True

    # Check if the import is a package (directory with __init__.py)
    potential_dir_path = (base_dir / module_path_str).expanduser().resolve()
    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Constructed potential directory path: %s", potential_dir_path)
    if ud.safe_is_dir(potential_dir_path) and ud.safe_is_file(potential_dir_path / "__init__.py") and module_path_str not in options.subfolders:
        options.custom_modules[module_name] = potential_dir_path
        options.loaded_custom_modules.add(module_name)
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Resolved local package to: %s", potential_dir_path)
        options.subfolders.append(module_path_str)
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Added subfolder: %s", module_path_str)
        return True

    # Check if this module is in the custom_modules dictionary.
    if module_name in options.custom_modules:
        module_file = options.custom_modules[module_name]
        if module_name not in options.loaded_custom_modules:
            options.loaded_custom_modules.add(module_name)
            if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Resolved via custom_modules: %s → %s", module_name, module_file)
        return True

    # --- fall back to sys.path hints (folders added at runtime) ---
    for root in getattr(options, "sys_path_hints", set()):
        # Look for a single-file module
        candidate = (root / f"{module_path_str}.py").expanduser().resolve()
        if ud.safe_is_file(candidate):
            options.custom_modules[module_name] = candidate
            options.loaded_custom_modules.add(module_name)
            if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Resolved via sys.path hint (file): %s → %s", module_name, candidate)
            return True

        # Look for a package dir with __init__.py
        pkg = (root / module_path_str).expanduser().resolve()
        if ud.safe_is_dir(pkg) and ud.safe_is_file(pkg / "__init__.py"):
            options.custom_modules[module_name] = pkg
            options.loaded_custom_modules.add(module_name)
            if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Resolved via sys.path hint (package): %s → %s", module_name, pkg)
            return True

    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Could not resolve local import, treating as external: %s", module_name)
    return False


class FunctionInfo:
    """Class to hold information about a function."""

    def __init__(self, function_name: str, node: ast.FunctionDef) -> None:
        """Initialize the function information, storing its AST node too."""
        self.function_name:            str = function_name
        self.ast_node:     ast.FunctionDef = node
        self.imports_in_function: set[str] = set()
        self.function_calls:      set[str] = set()


class ModuleInfo:
    """Class to hold information about a module."""

    def __init__(self, module_name: str) -> None:
        """Initialize the module information."""
        self.module_name:                   str = module_name
        self.top_level_imports:        set[str] = set()
        self.functions: dict[str, FunctionInfo] = {}
        self.top_level_calls:          set[str] = set()
        self.aliases:            dict[str, str] = {}
        self.classes:                  set[str] = set()
        self.base_classes: dict[str, list[str]] = {}


class ImportFunctionCollector(ast.NodeVisitor):
    """Visitor class to collect function and import information from a module."""

    def __init__(self, options: Options, module_name: str,
                 file_path: str | os.PathLike[str]) -> None:
        """Initialize the import function collector."""
        self.module_info:                      ModuleInfo = ModuleInfo(module_name)
        self.current_function:                 str | None = None
        self.current_class:                    str | None = None
        self.aliases:                      dict[str, str] = {}
        self.options:                             Options = options
        self.file_path:                              Path = ud.ensure_path(file_path)
        self.base_classes:           dict[str, list[str]] = {}
        self.attr_types: defaultdict[str, dict[str, str]] = defaultdict(dict)  # {class_name: {attr_name: "QualifiedTypeName"}}
        self._param_types:                 dict[str, str] = {}  # param name -> "QualifiedTypeName"

    def visit_Import(self, node: ast.Import) -> None:
        """Visit an import statement and add the imported module to the module's list of imports."""
        for alias in node.names:
            name               = alias.asname or alias.name
            full_name          = alias.name
            top_level_package  = full_name.split(".")[0]
            self.aliases[name] = full_name
            if self.current_function:
                self.module_info.functions[self.current_function].imports_in_function.add(top_level_package)
            else:
                self.module_info.top_level_imports.add(top_level_package)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Visit an import from statement and add the imported module to the module's list of imports."""
        module = node.module or ""
        # Extract the top-level package
        top_level_package = module.split(".")[0] if module else ""
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
        self.module_info.functions[func_name] = FunctionInfo(func_name, node)
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Added function: %s to module %s", func_name, self.module_info.module_name)
        prev_function         = self.current_function
        self.current_function = func_name
        # Track parameter annotations (only while inside this function)
        self._param_types = {}
        for a in node.args.args:
            if a.annotation is not None:
                t = self._type_name(a.annotation)
                if t:
                    self._param_types[a.arg] = t
        self.generic_visit(node)
        self.current_function = prev_function
        self._param_types = {}

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
                parts = base_name.split(".")
                if parts and parts[0] in self.aliases:
                    alias_target = self.aliases[parts[0]]
                    base_name = alias_target + "." + ".".join(parts[1:])
                base_class_names.append(base_name)
        self.base_classes[node.name] = base_class_names
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Recorded base classes for %s: %s", node.name, self.base_classes[node.name])
        # Now that base_classes is set, visit the class body
        self.generic_visit(node)
        self.current_class = prev_class

    def _qual(self, tail: str) -> str:
        """Prepend the current module name + '_SEP' to the input string."""
        return f"{self.module_info.module_name}{_SEP}{tail}"

    def extract_module_name_from_import(self, node: ast.Call) -> str | None:
        """Extract the module name from a dynamic import using __import__."""
        if node.args:
            module_arg = node.args[0]
            if isinstance(module_arg, ast.Constant) and isinstance(module_arg.value, str):
                module_name = module_arg.value.split(".")[0]  # Get top-level package
                return module_name
            else:
                # Handle cases where module name cannot be resolved
                logging.error(f"Cannot resolve dynamic import with non-constant module name: {ast.unparse(node)}")
                return None
        else:
            logging.error(f"No arguments provided to __import__(): {ast.unparse(node)}")
            return None

    def _record_call(self, qualified: str) -> None:
        """Record a function call, either in the current function or at the top level."""
        if self.current_function:
            self.module_info.functions[self.current_function].function_calls.add(qualified)
        else:
            self.module_info.top_level_calls.add(qualified)

    def _maybe_alias(self, name: str) -> str:
        """Replace the first part of 'name' with its alias if it exists."""
        parts = name.split(".")
        if parts and parts[0] in self.aliases:
            parts[0] = self.aliases[parts[0]]
        return ".".join(parts)

    def _maybe_record_func_ref(self, node: ast.AST) -> None:
        """If 'node' looks like a reference to a function, record it as a call."""
        ref = self.get_full_name(node)
        if not ref:
            return
        # Case 1: plain name referring to a function defined in this module
        if "." not in ref and ref in self.module_info.functions:
            self._record_call(ref)
            return
        # Case 2: class defined here passed as a constructor -> treat as __init__
        if "." not in ref and ref in self.module_info.classes:
            self._record_call(self._qual(f"{ref}.__init__"))
            return
        # Case 3: qualified like other_module.func
        if "." in ref:
            qualified = self._maybe_alias(ref)
            self._record_call(qualified)
            return

    def visit_Call(self, node: ast.Call) -> None:
        """Visit a function call and add it to the function's list of calls."""
        func_name = self.get_full_name(node.func)
        original_func_name = func_name
        # Resolve self.<attr>.<method> to the attribute's type
        if func_name and self.current_class:
            parts = func_name.split(".")
            # Pattern: CurrentClass.<attr>.<method>[.<more>]
            if len(parts) >= 3 and parts[0] == self.current_class:
                attr = parts[1]
                method_tail = ".".join(parts[2:])
                t = self.attr_types.get(self.current_class, {}).get(attr)
                if t:
                    # Qualify local classes with the current module
                    if t in self.module_info.classes:
                        func_name = self._qual(f"{t}.{method_tail}")
                    else:
                        # t might already be qualified by an alias (e.g., "ud.LLMs")
                        func_name = f"{t}.{method_tail}"
        if func_name:
            parts = func_name.split(".")
            if parts[0] in self.module_info.classes:
                # It's a class from this module
                if func_name in self.module_info.classes:
                    # func_name is exactly the class name, treat as constructor
                    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("%s is identified as a class. Converting to __init__ call.", func_name)
                    func_name = self._qual(f"{func_name}.__init__")
                else:
                    # It's a method/attribute call on a class from this module
                    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("%s is a method/attribute on a class from the same module. Qualifying with module name.", func_name)
                    func_name = self._qual(func_name)
            else:
                if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("%s is not a class, leaving as-is.", func_name)
            # If func_name corresponds to a class in this module, treat it as calling __init__
            if func_name in self.module_info.classes:
                func_name = f"{func_name}.__init__"
            # Handle dynamic imports
            if func_name == "__import__":
                module_name = self.extract_module_name_from_import(node)
                if module_name:
                    if self.current_function:
                        self.module_info.functions[self.current_function].imports_in_function.add(module_name)
                    else:
                        self.module_info.top_level_imports.add(module_name)
                else:
                    logging.warning("Cannot resolve dynamic import: %s", ast.unparse(node))
            # Handle importlib.import_module(...)
            elif func_name == "importlib.import_module":
                abs_name = self.extract_module_name_from_importlib_import_module(node)
                if abs_name:
                    self._register_import_name(abs_name)
                else:
                    logging.warning("Cannot resolve importlib.import_module call: %s", ast.unparse(node))
            # Handle importlib.util.spec_from_file_location(...)
            elif func_name == "importlib.util.spec_from_file_location":
                res = self.extract_from_importlib_spec_from_file_location(node)
                if res:
                    mod, loc = res
                    self._register_import_name(mod)
                    if loc:
                        self._register_constant_path_for_module(mod, loc)
            # Handle importlib.machinery.SourceFileLoader(...).load_module()
            # We match either the constructor itself or the chained .load_module():
            elif func_name == "importlib.machinery.SourceFileLoader":
                res = self.extract_from_importlib_sourcefileloader(node)
                if res:
                    mod, loc = res
                    self._register_import_name(mod)
                    if loc:
                        self._register_constant_path_for_module(mod, loc)
            # Also catch the chained call: importlib.machinery.SourceFileLoader(...).load_module()
            elif isinstance(node.func, ast.Attribute) and node.func.attr == "load_module":
                # node.func.value should be the Call to SourceFileLoader(...)
                loader_call = node.func.value
                if isinstance(loader_call, ast.Call):
                    callee = self.get_full_name(loader_call.func)
                    if callee == "importlib.machinery.SourceFileLoader":
                        res = self.extract_from_importlib_sourcefileloader(loader_call)
                        if res:
                            mod, loc = res
                            self._register_import_name(mod)
                            if loc:
                                self._register_constant_path_for_module(mod, loc)
                        else:
                            logging.warning("Cannot resolve SourceFileLoader(...).load_module() call: %s", ast.unparse(node))
            elif func_name.startswith("super."):
                # Handle super calls
                _, method_name = func_name.split(".", 1)
                if self.current_class and self.current_class in self.base_classes:
                    base_classes = self.base_classes[self.current_class]
                    if base_classes:
                        base_class = base_classes[0]  # Assuming single inheritance
                        func_name = f"{base_class}.{method_name}"
                self._record_call(func_name)
            else:
                # Normal calls
                self._record_call(func_name)
        for a in node.args:
            self._maybe_record_func_ref(a)
        for kw in node.keywords:
            if kw.value is not None:
                self._maybe_record_func_ref(kw.value)
        self.generic_visit(node)
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Call found: original func_name=%s, resolved func_name=%s", original_func_name, func_name)
        if self.current_function:
            if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Adding function call %s to %s", func_name, self.current_function)
        else:
            if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Adding top-level call: %s", func_name)

    def get_full_name(self, node: ast.AST) -> str | None:
        """Get the full name of a node, including any aliases."""
        if isinstance(node, ast.Name):  # Handle variable names
            if node.id in ("self", "cls"):  # Handle class methods
                if self.current_class:
                    return self.current_class
                else:
                    return node.id
            elif node.id == "super":  # Handle super() calls
                return "super"
            else:
                return self.aliases.get(node.id, node.id)
        elif isinstance(node, ast.Attribute):  # Handle attribute access
            value = self.get_full_name(node.value)
            return f"{value}.{node.attr}" if value else node.attr
        elif isinstance(node, ast.Call):  # Handle super() calls
            func_name = self.get_full_name(node.func)
            return func_name
        return None

    def _type_name(self, node: ast.AST) -> str | None:
        """
        Extract a string type name from an annotation or qualified name.
        Handles Name or Attribute, using aliases when needed.
        """
        if isinstance(node, ast.Name):
            return self.aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            base = self._type_name(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        return None

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """
        Visit an annotated assignment and record attribute types.
        e.g. self.options: Options = options
        """
        if (
            self.current_class and
            isinstance(node.target, ast.Attribute) and
            isinstance(node.target.value, ast.Name) and
            node.target.value.id == "self"
        ):
            t = self._type_name(node.annotation)
            if t:
                self.attr_types[self.current_class][node.target.attr] = t
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        """
        Visit an assignment and try to infer attribute types from RHS.
        e.g. self.options = options   (infer type from param annotation if possible)
        """
        for tgt in node.targets:
            if (
                self.current_class and
                isinstance(tgt, ast.Attribute) and
                isinstance(tgt.value, ast.Name) and
                tgt.value.id == "self"
            ):
                # Try to infer type from RHS if RHS is a Name that matches a typed param
                if isinstance(node.value, ast.Name):
                    pname = node.value.id
                    t = self._param_types.get(pname)
                    if t:
                        self.attr_types[self.current_class][tgt.attr] = t
        self.generic_visit(node)

    # --- Importlib helpers -------------------------------------------------

    def _const_str(self, node: ast.AST) -> str | None:
        """Return node.value if the node is a constant string; else None."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    def _resolve_relative_module(self, name: str, package: str | None) -> str | None:
        """
        Resolve 'name' that may start with dots against an absolute 'package'.
        Mirrors importlib semantics roughly; for our purposes we only need to
        resolve to a package string to feed the rest of the pipeline.
        """
        if not name:
            return None
        if not name.startswith("."):
            return name  # already absolute
        if not package:
            return None  # cannot resolve without a package
        # Count leading dots
        i = 0
        while i < len(name) and name[i] == ".":
            i += 1
        # Climb up 'i-1' levels from package
        pkg_parts = package.split(".")
        if i - 1 > len(pkg_parts):
            return None
        base = ".".join(pkg_parts[: len(pkg_parts) - (i - 1)])
        tail = name[i:]
        return f"{base}.{tail}" if tail else base

    def _register_import_name(self, module_name: str) -> None:
        """
        Record an import for the current function (or top-level) using the
        top-level package (to match your existing pipeline).
        """
        top_level = module_name.split(".")[0] if module_name else None
        if not top_level:
            return
        if self.current_function:
            self.module_info.functions[self.current_function].imports_in_function.add(top_level)
        else:
            self.module_info.top_level_imports.add(top_level)

    def _register_constant_path_for_module(self, module_name: str, path_str: str) -> None:
        """
        Best-effort: if we get a constant file path for a dynamically loaded module,
        map it immediately so later phases can resolve it as a local module.
        """
        try:
            # Resolve relative to the file we're analyzing
            base_dir = self.file_path.parent
            p = (base_dir / path_str).expanduser().resolve() if not os.path.isabs(path_str) else Path(path_str).expanduser().resolve()
        except Exception as e:
            if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Failed to resolve path %s given base_dir %s: %s", path_str, os.fspath(base_dir), e)
            return
        # Only accept .py files or a directory with __init__.py
        if p.suffix == ".py" and ud.safe_exists(p):
            self.options.custom_modules[module_name] = p
        elif ud.safe_is_dir(p) and ud.safe_exists(p / "__init__.py"):
            self.options.custom_modules[module_name] = p

    def extract_module_name_from_importlib_import_module(self, node: ast.Call) -> str | None:
        """
        Handle importlib.import_module(name, package=None) and aliased import_module().
        Only constant strings are supported.
        """
        if not node.args:
            return None
        name = self._const_str(node.args[0])
        if name is None:
            logging.error(f"Cannot resolve import_module with non-constant name: {ast.unparse(node)}")
            return None
        pkg = None
        if len(node.args) >= 2:
            pkg = self._const_str(node.args[1])
        else:
            for kw in node.keywords or []:
                if kw.arg == "package":
                    pkg = self._const_str(kw.value)
        if name.startswith("."):
            abs_name = self._resolve_relative_module(name, pkg)
            if abs_name is None:
                logging.error(f"Cannot resolve relative import_module without constant package: {ast.unparse(node)}")
                return None
            return abs_name
        return name

    def extract_from_importlib_spec_from_file_location(self, node: ast.Call) -> tuple[str, str] | None:
        """
        Handle importlib.util.spec_from_file_location(name, location, ...).
        Returns (module_name, location_path) if both are constant strings.
        """
        if len(node.args) < 2:
            return None
        mod = self._const_str(node.args[0])
        loc = self._const_str(node.args[1])
        if mod is None:
            logging.error(f"Cannot resolve spec_from_file_location with non-constant module name: {ast.unparse(node)}")
            return None
        if loc is None:
            # We can still record the import name, just no path to register
            return (mod, None)
        return (mod, loc)

    def extract_from_importlib_sourcefileloader(self, node: ast.Call) -> tuple[str, str] | None:
        """
        Handle importlib.machinery.SourceFileLoader(name, path).
        Returns (module_name, path) if both are constant strings.
        """
        if len(node.args) < 2:
            return None
        mod = self._const_str(node.args[0])
        loc = self._const_str(node.args[1])
        if mod is None:
            logging.error(f"Cannot resolve SourceFileLoader with non-constant module name: {ast.unparse(node)}")
            return None
        if loc is None:
            return (mod, None)
        return (mod, loc)


_SEP: str = "::"  # Path-safe separator to distinguish class methods


def split_function_name(called_func: str, default_module: str) -> tuple[str, str]:
    """
    Split a fully qualified function id into (module_key, func_part).

    Preferred separator is _SEP (path-safe). Fall back to the first dot
    for legacy strings that still look like 'module.func'.
    """
    if _SEP in called_func:
        m, f = called_func.split(_SEP, 1)
        return m, f
    # legacy fallback
    parts = called_func.split(".")
    if len(parts) > 1:
        return parts[0], ".".join(parts[1:])
    return default_module, called_func


def _resolve(name: str, alias_to_key: dict[str, str] | None) -> str:
    """Resolve an alias-based module name to its file-path-based key."""
    return alias_to_key.get(name, name) if alias_to_key else name


def build_call_graph(modules_info: dict[str, ModuleInfo],
                     alias_to_key: dict[str, str] | None = None) -> dict[str, set[str]]:
    """Build a call graph from the function calls in the modules."""
    call_graph = {}
    for module_key, module_info in modules_info.items():
        for func_name, func_info in module_info.functions.items():
            full_func_name = f"{module_key}{_SEP}{func_name}"
            call_graph[full_func_name] = set()
            for called_func in func_info.function_calls:
                called_module, called_name = split_function_name(called_func, module_key)
                called_module = _resolve(called_module, alias_to_key)

                # If target looks like Class.method and isn't present, try the base class.
                if called_module in modules_info:
                    mi = modules_info[called_module]
                    if "." in called_name:
                        cls, meth = called_name.split(".", 1)
                        if called_name not in mi.functions and cls in mi.base_classes:
                            bases = mi.base_classes.get(cls, [])
                            if bases:
                                base = bases[0]
                                if base in mi.classes:
                                    called_full_name = f"{called_module}{_SEP}{base}.{meth}"
                                else:
                                    if "." in base:
                                        base_mod, base_sym = base.split(".", 1)
                                        called_full_name = f"{_resolve(base_mod, alias_to_key)}{_SEP}{base_sym}.{meth}"
                                    else:
                                        called_full_name = f"{base}{_SEP}{meth}"
                                call_graph[full_func_name].add(called_full_name)
                                continue

                # Check if called_name is a class in the module
                if called_module in modules_info and called_name in modules_info[called_module].classes:
                    called_full_name = f"{called_module}{_SEP}{called_name}.__init__"
                else:
                    called_full_name = f"{called_module}{_SEP}{called_name}"
                call_graph[full_func_name].add(called_full_name)
    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Call graph constructed:")
    for func, calls in call_graph.items():
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("%s calls: %s", func, calls)
    return call_graph


def collect_used_imports(start_module: str, start_func: str,
                         call_graph:   dict[str, set[str]],
                         modules_info: dict[str, ModuleInfo],
                         visited: set[str] | None = None,
                         alias_to_key: dict[str, str] | None = None) -> set[str]:
    """
    Collect all imports used in a function and its callees.
    

    Args:
        start_module: The module where the function is defined.
        start_func:   The function name to start collecting imports from.
        call_graph:   A dictionary representing the call graph of functions.
        modules_info: A dictionary mapping module keys to ModuleInfo objects.
        visited:      A set of fully qualified function names that have already been visited.
        alias_to_key: A dictionary mapping module aliases to their file-path-based keys.

    Returns:
        A set of import statements used in the function and its callees.
    """
    if visited is None:
        visited = set()
    # Resolve alias-based module name to file-path-based key
    start_module        = _resolve(start_module, alias_to_key)
    full_func_name: str = f"{start_module}{_SEP}{start_func}"
    if full_func_name in visited:
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Already visited %s, skipping.", full_func_name)
        return set()
    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Visiting function: %s", full_func_name)
    visited.add(full_func_name)
    imports: set[str] = set()
    module_info       = modules_info.get(start_module)
    if module_info:
        func_info = module_info.functions.get(start_func)
        if func_info:
            if func_info.imports_in_function:
                if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Function %s imports: %s", full_func_name, func_info.imports_in_function)
            imports.update(func_info.imports_in_function)
    # Follow resolved edges from the call graph:
    edges = call_graph.get(full_func_name, set())
    for called_full in edges:
        called_module, called_name = split_function_name(called_full, start_module)
        imports.update(collect_used_imports(called_module, called_name, call_graph,
                                            modules_info, visited, alias_to_key))
    return imports


def _analyze_module(options:          Options,
                    module_path:      Path,
                    modules_info:     dict[str, ModuleInfo],
                    module_contents:  dict[str, str],
                    module_trees:     dict[str, ast.AST],
                    do_sys_path_scan: bool) -> tuple[str, ModuleInfo] | None:
    """
    Read, parse, and analyze one module file.
    - Optionally scans for sys.path mutations (current behavior: only for the first loop).
    - Updates modules_info / module_contents / module_trees.

    Args:
        options:          Options object containing configuration and state. Contains:
            - options.standard_modules: Set of standard library module names.
            - options.custom_modules:   Dictionary mapping custom module names to their file paths.
            - options.sys_path_hints:   Set of Path objects representing directories to add to sys.path.
            - options.rawlog:           Boolean indicating whether to log raw file contents.
        module_path:      Path to the module file to analyze.
        modules_info:     Dictionary mapping module keys to ModuleInfo objects.
        module_contents:  Dictionary mapping module keys to their source code.
        module_trees:     Dictionary mapping module keys to their ASTs.
        do_sys_path_scan: Whether to scan for sys.path mutations in this module.

    Returns:
        (module_key, module_info) or None on failure.
    """
    module_path = ud.ensure_path(module_path)
    module_key  = os.fspath(module_path.resolve())

    file_content = ud.my_fopen(module_path, rawlog=options.rawlog)
    if not file_content:
        logging.error(f"Could not read file: {module_path}")
        return None

    try:
        tree = ast.parse(file_content, module_key)
    except Exception:
        logging.error(f"Failed to parse the file: {module_path}")
        return None

    module_contents[module_key] = file_content
    module_trees[   module_key] = tree

    collector = ImportFunctionCollector(options, module_key, module_path)
    collector.visit(tree)

    # Keep behavior identical: only the first loop does sys.path scanning.
    if do_sys_path_scan:
        aliases = collect_pathlib_aliases(tree)
        spv = SysPathVisitor(aliases)
        spv.visit(tree)
        base_dir = module_path.parent
        for p in spv.paths:
            if not p:
                continue
            P = (base_dir / p).expanduser().resolve() if not os.path.isabs(p) else Path(p).expanduser().resolve()
            if ud.safe_is_dir(P):
                options.sys_path_hints.add(P)

    module_info = collector.module_info
    module_info.base_classes = collector.base_classes
    modules_info[module_key] = module_info
    return module_key, module_info


def _enqueue_top_level_imports(options:           Options,
                               module_path:          Path,
                               import_names:     set[str],
                               processed_paths: set[Path],
                               modules_to_process: "collections.deque[Path]") -> None:
    """
    Given top-level imports for a module, run your existing resolution logic and
    enqueue any newly found local modules/packages for the first pass queue.
    """
    for import_name in import_names:
        if import_name in options.standard_modules:
            continue  # Skip standard modules
        resolved = process_import(options, import_name, module_path)
        if not resolved:
            options.all_imports.add(import_name)
            continue
        possible_module_file_path = options.custom_modules.get(import_name)
        if possible_module_file_path is None:
            continue
        actual_module_file_path = ud.ensure_path(possible_module_file_path)
        if ud.safe_is_file(actual_module_file_path):
            if actual_module_file_path not in processed_paths and actual_module_file_path not in modules_to_process:
                modules_to_process.append(actual_module_file_path)


def find_imports_and_IO_in_script(options: Options, first_path: str | os.PathLike[str]) -> None:
    """
    Find all imports and I/O in the script (including functions and classes
    that it imports from its dependencies.)

    Args:
        options:    Options object containing paths to the python script and custom modules.
        first_path: Path to the Python script to analyze for imports and I/O.

    Returns:
        None - modifies options to include all imports and I/O operations found in the script.

    Raises:
        FileNotFoundError: If the first_path does not exist.
        IsADirectoryError: If the first_path exists but is a directory.
        ValueError:        If the first_path exists but is not a regular file.
    """
    from collections import deque  # Allows for efficient first in, first out processing of modules
    first_path = ud.ensure_file(first_path)
    if not ud.is_python_script(first_path) or not ud.compile_code(first_path):
        logging.error(f"Skipping invalid Python script: {first_path}")
        return
    options.read_files                  = []
    options.write_files                 = []
    options.download_urls               = []
    options.upload_urls                 = []
    processed_paths:          set[Path] = set()
    modules_info: dict[str, ModuleInfo] = {}
    modules_to_process:     deque[Path] = deque([first_path])
    module_contents:     dict[str, str] = {}
    module_trees:    dict[str, ast.AST] = {}
    while modules_to_process:
        module_path = modules_to_process.popleft()  # first in, first out
        if not options.rawlog: logging.info("Processing module: %s where %s", module_path, type(module_path))
        if ud.safe_is_dir(module_path):
            pkg_dir = module_path
            init_py = pkg_dir / "__init__.py"
            if ud.safe_is_file(init_py):
                # 1) Parse the package __init__.py
                module_path = init_py
                # 2) Also enqueue all other .py modules in that same folder
                for p in pkg_dir.iterdir():
                    if ud.is_python_script(p) and p.name != "__init__.py":
                        if p not in modules_to_process and p not in processed_paths:
                            modules_to_process.append(p)
            else:
                logging.error(f"No __init__.py in package directory {pkg_dir}, skipping.")
                continue
        elif not ud.safe_is_file(module_path):
            logging.error(f"Skipping {module_path} because it is not a file or directory.")
            continue
        if module_path in processed_paths:
            continue
        processed_paths.add(module_path)
        result = _analyze_module(options, module_path, modules_info, module_contents,
                                 module_trees, do_sys_path_scan=True)
        if result is None:
            continue
        module_key, module_info = result
        _enqueue_top_level_imports(
            options, module_path,
            module_info.top_level_imports,
            processed_paths,
            modules_to_process,
        )
    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Modules processed so far:")
    for module_key, m_info in modules_info.items():
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Module: %s, Classes: %s, Functions: %s", module_key, m_info.classes, list(m_info.functions.keys()))

    # Build alias → file-path-key mapping for local modules
    _alias_to_key: dict[str, str] = {}
    for _mod_name, _mod_path in options.custom_modules.items():
        _p = ud.ensure_path(_mod_path)
        if ud.safe_is_file(_p):
            _alias_to_key[_mod_name] = os.fspath(_p.resolve())

    # Now build the call graph
    call_graph = build_call_graph(modules_info, alias_to_key=_alias_to_key)

    # Collect used imports starting from the first module
    used_imports:  set[str] = set()
    visited_funcs: set[str] = set()

    def collect_imports_from_module(module_key: str) -> None:
        """Recursively collect used imports from a module."""
        module_info = modules_info[module_key]
        used_imports.update(module_info.top_level_imports)
        for func_name in module_info.top_level_calls:
            called_module, called_name = split_function_name(func_name, module_key)
            if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Collecting used imports for module '%s' and func_name '%s'", called_module, called_name)
            used_imports.update(
                collect_used_imports(
                    called_module,  # Use the extracted module name
                    called_name,    # Use the extracted function name
                    call_graph,
                    modules_info,
                    visited_funcs,
                    _alias_to_key
                )
            )
            if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Used imports collected from '%s' in '%s': %s", called_name, called_module, used_imports)
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Used imports after collecting from module %s: %s", module_key, used_imports)

    # Scan the *initial* script (first_path) everywhere:
    first_module_key = os.fspath(first_path.resolve())
    collect_imports_from_module(first_module_key)
    init_src  = module_contents[first_module_key]
    init_tree = module_trees[   first_module_key]

    FileOperationsVisitor(options,    init_src).visit(init_tree)
    NetworkOperationsVisitor(options, init_src).visit(init_tree)

    # Now process used imports and recursively dive into any new local modules.
    processed_used_imports: set[str] = set()
    new_modules_found = True
    while new_modules_found:
        new_modules_found = False
        for import_name in used_imports.copy():
            # Skip built-ins or any we've already handled this round
            if import_name in options.standard_modules or import_name in processed_used_imports:
                continue
            processed_used_imports.add(import_name)
            process_import(options, import_name, first_path)
            if import_name in options.custom_modules:
                # It's a known local module that we haven't processed yet
                module_file_path = ud.ensure_path(options.custom_modules[import_name])
                if not ud.safe_is_file(module_file_path):
                    logging.error(f"Custom module path for {import_name} is not a file: {module_file_path}")
                    continue
                new_module_key = os.fspath(module_file_path.resolve())
                if new_module_key in modules_info or \
                   module_file_path in processed_paths or \
                   module_file_path in modules_to_process:
                    # Already parsed, but still trace its top-level calls
                    if new_module_key in modules_info:
                        old_size = len(used_imports)
                        collect_imports_from_module(new_module_key)
                        if len(used_imports) > old_size:
                            new_modules_found = True
                    continue  # don't re-analyze
                modules_to_process.append(module_file_path)
                new_modules_found = True
                result = _analyze_module(options, module_file_path, modules_info,
                                         module_contents, module_trees, do_sys_path_scan=False)
                if result is None:
                    continue
                new_module_key, module_info = result
                # Rebuild alias map and call graph with the new module included
                _p = ud.ensure_path(module_file_path)
                if ud.safe_is_file(_p):
                    _alias_to_key[import_name] = os.fspath(_p.resolve())
                call_graph = build_call_graph(modules_info, _alias_to_key)
                collect_imports_from_module(new_module_key)
                _enqueue_top_level_imports(options, module_file_path,
                                           module_info.top_level_imports,
                                           processed_paths,
                                           modules_to_process)
            else:
                # If not a local module, add to options.all_imports
                options.all_imports.add(import_name)
    # For every *other* local module, do:
    #   (1) top-level only, plus
    #   (2) only in the function bodies that actually got visited
    for module_key, src in module_contents.items():
        if module_key == first_module_key:
            continue
        # Record any I/O at module scope
        TopLevelFileOperationsVisitor(options,    src).visit(module_trees[module_key])
        TopLevelNetworkOperationsVisitor(options, src).visit(module_trees[module_key])
        # Record any I/O in each reachable function or class method
        for full in visited_funcs:
            mod, func = split_function_name(full, default_module="")
            if _resolve(mod, _alias_to_key) != module_key:
                continue
            func_info = modules_info[mod].functions.get(func)
            if not func_info:
                continue
            func_src  = src
            func_node = func_info.ast_node
            # run your original visitor on that one FunctionDef
            FileOperationsVisitor(options,    func_src).visit(func_node)
            NetworkOperationsVisitor(options, func_src).visit(func_node)
    if not options.rawlog:
        discovered_operations = []
        if any([options.read_files, options.write_files]):
            discovered_operations.append("file")
        if any([options.download_urls, options.upload_urls]):
            discovered_operations.append("network")
        if discovered_operations:
            logging.info("Found %s operations:", " and ".join(discovered_operations))
            if options.read_files:
                logging.info("Files read:\n"    + "\n".join(os.fspath(f) for f in options.read_files))
            if options.write_files:
                logging.info("Files written:\n" + "\n".join(os.fspath(f) for f in options.write_files))
            if options.download_urls:
                logging.info("Download URLs:\n" + "\n".join(os.fspath(u) for u in options.download_urls))
            if options.upload_urls:
                logging.info("Upload URLs:\n"   + "\n".join(os.fspath(u) for u in options.upload_urls))
        else:
            logging.info("Found no file or network operations in the python script (%s) or custom modules (%s).",
                         options.python_script, ", ".join(options.loaded_custom_modules))


def add_dependencies(options: Options) -> None:
    """Add dependencies for uninstalled imports."""
    # Create a copy to iterate over since we'll be modifying the set
    initial_packages = options.uninstalled_imports.copy()

    for package in initial_packages:
        if package in options.also_needs:
            dependencies = options.also_needs[package]
            if not options.rawlog:
                logging.info("Adding dependencies for %s: %s", package, dependencies)
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
                        logging.info("Adding nested dependencies for %s: %s", package, new_dependencies)
                    options.uninstalled_imports.update(new_dependencies)
                    added = True


def check_packages_in_venv(options: Options, package: str | None = None,
                           venv_dir: str | os.PathLike[str] | None = None) -> bool:
    """
    Check if packages can be imported in the specified virtual environment.

    Args:
        options:    Options object containing settings and paths.
        package:    Optional package name to check. If None, checks all uninstalled imports.
        venv_dir:   Optional path to the virtual environment directory. If None, uses options.venv_dir.

    Returns:
        bool:       True if all packages can be imported successfully, False otherwise.

    Raises:
        None:       This function does not raise exceptions, but logs errors if the import fails.
    """
    if venv_dir is None:
        assert options.venv_dir is not None, "options.venv_dir must be set"
        venv_dir = options.venv_dir
    else:
        venv_dir = ud.ensure_dir(venv_dir)
    if sys.platform == "win32":
        venv_python = (venv_dir / "Scripts" / "python.exe").absolute()
    else:  # Do NOT use resolve() here because this is a symlink and resolve() would break it
        venv_python = (venv_dir / "bin" / "python").absolute()
    if package:
        packages = [options.reversed_module_aliases.get(package, package)]
    else:
        use_pip_list(options)
        packages = [options.reversed_module_aliases.get(pkg, pkg) for pkg in options.uninstalled_imports]
    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Packages to check in venv: %s", packages)
    python_code = f"""
import sys
from importlib import import_module
successes = []
failures = []
counter = 0
for package in {packages!r}:
    counter += 1
    try:
        import_module(package)
        successes.append(package)
    except ImportError:
        failures.append(package)
if failures:
    print("Failed packages: " + ", ".join(failures))
    sys.exit(1)
elif len(successes) != counter:
    print(f"Warning: No failures, but only recorded {{len(successes)}} successes out of {{counter}}.")
    sys.exit(2)
else:
    print(f"All {{len(successes)}} (out of {{counter}}) packages imported successfully.")
    sys.exit(0)
"""
    the_command = [os.fspath(venv_python), "-c", python_code]
    result = subprocess.run(the_command, capture_output=True, text=True, check=False)
    # if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("check_packages_in_venv command:\n%s", " ".join(shlex.quote(str(arg)) for arg in the_command))
    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("check_packages_in_venv stdout:\n%s", result.stdout)
    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("check_packages_in_venv stderr:\n%s", result.stderr)
    return "packages imported successfully" in result.stdout


def split_imports(options: Options) -> None:
    """Split imports into installed, uninstalled, and bad imports."""
    options.bad_imports = options.known_bad_imports.intersection(options.all_imports)
    options.bad_imports.update({imp for imp in options.all_imports if imp.startswith("_")})
    if options.bad_imports:
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Identified bad imports: %s", options.bad_imports)
    options.all_imports = options.all_imports - options.bad_imports
    options.installed_imports   = set()
    options.uninstalled_imports = set()
    if getattr(options.args, "reqs", False):
        options.all_imports = options.all_imports.union(options.extra_requirements.keys())
    options.total_imports = len(options.all_imports)
    if not options.total_imports:
        if not options.rawlog: logging.info("No imports found.")
        return

    max_length = max(len(imp) for imp in options.all_imports)  # Longest import name length, used for formatting
    max_digits = len(str(len(options.all_imports)))  # Maximum number of digits in import count, also used for formatting

    with tempfile.TemporaryDirectory() as venv_dir:
        venv.create(venv_dir, with_pip=True)
        for i, imp in enumerate(options.all_imports, 1):
            package_name = options.module_aliases.get(imp, imp)
            if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Checking if import %s is installed or uninstalled", imp)
            if imp in options.custom_modules.keys():
                if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Custom module %s has path %s", imp, os.fspath(options.custom_modules[imp]))
                status_str = f"{ud.ANSI_CYAN}YES - custom module{ud.ANSI_RESET}"
            elif check_packages_in_venv(options, package=package_name,
                                        venv_dir=venv_dir):
                if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Module %s can be imported in venv", imp)
                status_str = f"{ud.ANSI_GREEN}YES -     installed{ud.ANSI_RESET}"
                options.installed_imports.add(imp)
            else:
                if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Import %s is not installed and not a custom module", imp)
                status_str = " NO - NOT installed"
                options.uninstalled_imports.add(package_name)
            if not options.rawlog:
                logging.info("Checking import %-*s : %*d/%d - %s",
                             max_length,  # width for imp (left-aligned)
                             imp,
                             max_digits,  # width for i (right-aligned)
                             i, options.total_imports, status_str)
    if getattr(options.args, "reqs", False):
        options.uninstalled_imports = options.uninstalled_imports.union(options.extra_requirements.keys())
    add_dependencies(options)
    return


def list_packages(options: Options) -> None:
    """
    Examine command line arguments to determine if we're looking at a directory or a single python script. List all installed and uninstalled packages that are imported in that directory or python script. Return these sets inside the options object.

    Args:
        options: Options object containing command line arguments and settings. Contains:
            - python_script:           Path to the Python script or directory to analyze.
            - rawlog:                  Boolean indicating if raw logging is enabled.
            - pipreqs_available:       Boolean indicating if pipreqs is available for
                                       generating requirements.
            - script_dir:              Directory containing the script, used for logging.
            - all_imports:             Set to be populated with all imports found.
            - installed_imports:       Set to be populated with installed imports.
            - uninstalled_imports:     Set to be populated with uninstalled imports.
            - known_bad_imports:       Set of known bad imports to filter out.
            - standard_modules:        Set of standard library modules to ignore.
            - custom_modules:          Dictionary mapping custom module names to their file paths.
            - module_aliases:          Dictionary mapping import names to package names
                                       (e.g., 'PIL' -> 'Pillow').
            - reversed_module_aliases: Reverse mapping of module_aliases for checking installations.
            - also_needs:              Dictionary mapping packages to their dependencies.

    Returns:
        None - modifies options to include all imports found in the specified Python script or directory.

    Raises:
        ValueError:        If the provided path is not a valid Python script or directory.
        FileNotFoundError: If the specified file or directory does not exist.
    """
    assert options.python_script is not None, "options.python_script must be set"
    assert options.script_dir    is not None, "options.script_dir must be set"
    if getattr(options.args, "full", False):
        if not options.rawlog: logging.info("Building a virtual environment that can run every python script in %s", os.fspath(options.script_dir))

    if isinstance(options.python_script, (str, Path)):
        options.python_script         = ud.ensure_path(options.python_script)
        options.loaded_custom_modules = set()
        if ud.safe_is_file(options.python_script):
            if ud.is_python_script(options.python_script):
                if not options.rawlog: logging.info("Processing a single Python script: %s", os.fspath(options.python_script))
                python_file = options.python_script
                options.all_imports = set()
                find_imports_and_IO_in_script(options, python_file)
            else:
                raise ValueError(f"'{os.fspath(options.python_script)}' is not a valid Python script.")
        elif ud.safe_is_dir(options.python_script):
            if not options.rawlog: logging.info("Processing an entire folder of Python scripts: %s",
                                                os.fspath(options.python_script))
            python_dir = options.python_script
            if options.pipreqs_available:
                if not options.rawlog: logging.info("Using pipreqs to generate requirements.")
                generate_requirements(options.python_script)
                with open(python_dir / "requirements.txt", "r") as f:
                    options.all_imports = set(line.strip() for line in f)
            else:
                if not options.rawlog: logging.info("Using custom script to find imports.")
                get_all_imports(options, options.python_script)
        else:
            raise FileNotFoundError(f"The file or directory {os.fspath(options.python_script)} does not exist.")
    else:
        raise ValueError(f"Unexpected type for options.python_script: {type(options.python_script)}")

    # Filter out invalid imports before splitting
    options.all_imports = {imp for imp in options.all_imports if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', imp)}

    split_imports(options)


def stayed_out_dir(options: Options, p: str | os.PathLike[str]) -> bool:
    """Check if the parent directory of path p contains any substrings from the stay_out_list."""
    p          = ud.ensure_path(p)
    parent_str = os.fspath(p.parent)
    return any(sub in parent_str for sub in options.stay_out_list)


def get_all_imports(options: Options, directory: str | os.PathLike[str]) -> None:
    """Get all imports from all Python scripts in a directory."""
    directory = ud.ensure_path(directory)
    options.all_imports = set()
    # Build one iterator of candidate files (recursive)
    candidates = (p for p in directory.rglob("*") if ud.safe_is_file(p) and not stayed_out_dir(options, p))
    # If you want a progress denominator that matches what you'll actually process:
    total_files     = sum(1 for p in candidates if ud.is_python_script(p))
    max_digits      = len(str(total_files))  # For formatting progress output
    processed_files = 0
    # Recreate the iterator (generators are single-use)
    candidates = (p for p in directory.rglob("*") if ud.safe_is_file(p) and not stayed_out_dir(options, p))
    for file_path in candidates:
        if ud.is_python_script(file_path):
            find_imports_and_IO_in_script(options, file_path)
            processed_files += 1
            if not options.rawlog:
                # OLD: logging.info(f"Processing file {processed_files:>{max_digits}}/{total_files} : {file_path}")
                logging.info("Processing file %*d/%d : %s",
                             max_digits, processed_files, total_files, file_path)
    if not options.rawlog: logging.info("Finished processing files in %s", os.fspath(directory))


def generate_requirements(directory: str | os.PathLike[str]) -> None:
    """Generate a requirements file using pipreqs."""
    try:
        pipreqs.generate_requirements(directory)
    except (pipreqs.PipreqsError, pipreqs.PipreqsWarning) as e:
        raise ValueError(f"Error generating requirements file in {directory}: {e}") from e


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
        assert options.download_script_path is not None, "Download script path is not set."
        if not options.rawlog: logging.info("Writing download script to %s", options.download_script_path)
        options.download_script_path.write_text(download_script, encoding=ud.DEFAULT_ENCODING)
        options.download_script_path.chmod(0o755)
        # Run the initial download script and capture the output
        result = ud.my_popen([options.download_script_path])
        return result.returncode == 0
    except OSError:
        logging.exception("Error writing or executing download script.")
        return False


def install_packages_simultaneously(options: Options) -> bool:
    """Install all packages simultaneously in the virtual environment."""
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


def install_packages_individually(options: Options) -> bool:
    """Install packages individually in the virtual environment."""
    failed_packages = []
    for package in options.uninstalled_imports:
        if not install_package(package, options):
            failed_packages.append(package)

    if failed_packages:
        logging.error("Failed to install the following packages: %s", ", ".join(failed_packages))
        return False
    else:
        if not options.rawlog: logging.info("All packages installed successfully.")
        return True


def install_package(package_name: str, options: Options) -> bool:
    """Install a single package and return the success status (True if successful, False otherwise)."""
    assert options.venv_python  is not None, "Virtual environment Python executable is not set."
    assert options.packages_dir is not None, "Packages directory is not set."
    the_command = [os.fspath(options.venv_python), "-m", "pip", "install", package_name,
                   "--no-index", "--find-links", os.fspath(options.packages_dir)]
    logging.info("Running pip install: %s", " ".join(shlex.quote(str(arg)) for arg in the_command))
    result = subprocess.run(the_command, capture_output=True, text=True)
    if not options.rawlog: logging.info(result.stdout)
    if result.stderr:
        logging.error(result.stderr)
    if result.returncode != 0:
        # Use pip to download files for package_name to options.packages_dir
        download_command = [os.fspath(options.venv_python), "-m", "pip", "download", "--dest",
                            os.fspath(options.packages_dir), package_name]
        download_result = subprocess.run(download_command, capture_output=True, text=True)
        if download_result.returncode != 0:
            ud.my_critical_error(f"Failed to download {package_name}. Error: {download_result.stderr}")
        # Use pip to install package_name from the file that was just downloaded to options.packages_dir
        install_command = [os.fspath(options.venv_python), "-m", "pip", "install", "--no-index",
                           "--find-links", os.fspath(options.packages_dir), package_name]
        install_result = subprocess.run(install_command, capture_output=True, text=True)
        if install_result.returncode != 0:
            logging.error("Failed to install %s. Error: %s", package_name, install_result.stderr)
        else:
            if not options.rawlog: logging.info("Successfully installed %s", package_name)
        return result.returncode == 0
    return result.returncode == 0


def recover_pip_versions(output: str, options: Options) -> None:
    """Parse the output to recover the current and new pip versions."""
    if hasattr(output, "read"):
        output = output.read()
    current_version_pattern = re.compile(r"Current pip version: (.+)")
    new_version_pattern     = re.compile(r"New     pip version: (.+)")

    current_version_match = current_version_pattern.search(output)
    new_version_match     = new_version_pattern.search(    output)

    if current_version_match:
        options.current_pip_version = current_version_match.group(1)
        if not options.rawlog: logging.info("Recovered current pip version: %s", options.current_pip_version)
    else:
        logging.warning("Failed to recover current pip version from output.")

    if new_version_match:
        options.new_pip_version = new_version_match.group(1)
        if not options.rawlog: logging.info("Recovered new pip version: %s", options.new_pip_version)
    else:
        logging.warning("Failed to recover new pip version from output.")


def pretty_packages_list(options: Options) -> str:
    """Create a pretty string of the first five package names and the number of remaining packages."""
    maxnum = 5
    packages_list = sorted(list(options.uninstalled_imports))
    if len(packages_list) > maxnum:
        first_five = "-".join(packages_list[:maxnum])
        suffix = f"-and-{len(packages_list) - maxnum}-more"
    else:
        first_five = "-".join(packages_list)
        suffix = ""

    return first_five + suffix


def use_pip_list(options: Options) -> None:
    """Use the pip list command to find all installed packages and use that pip list to modify the uninstalled and installed imports. Add packages from the options.extra_requirements dictionary if "--reqs" is specified as a runtime argument."""
    # Add packages from the options.extra_requirements dictionary if "--reqs" is specified as a runtime argument.
    if getattr(options.args, "reqs", False):
        options.uninstalled_imports = options.uninstalled_imports.union(options.extra_requirements.keys())
    if len(options.pip_list) == 0:
        # Create virtual environment
        venv.create(options.test_dir, with_pip=True)
        python_executable = options.test_dir / "bin" / "python"

        # Run custom list command using the Python executable from the virtual environment
        list_command_script = """
import importlib.metadata
import pkgutil
import sys

def list_installed_packages():
    installed_packages = [dist.metadata["Name"] for dist in importlib.metadata.distributions()]
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

        list_command = [os.fspath(python_executable), "-c", list_command_script]

        try:
            result = subprocess.run(list_command, check=True, capture_output=True, text=True)
            if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Output:\n%s", result.stdout)
        except subprocess.CalledProcessError as e:
            logging.exception("%s\nException type: %s", e, type(e).__name__)

        # Use regular expressions to find all package names
        options.pip_list = re.findall(r'^[^\s]+', result.stdout, re.MULTILINE)
        options.pip_list = [pkg for pkg in options.pip_list if pkg != "Package" and not all(c == "-" for c in pkg)]
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("\noptions.pip_list = %s", options.pip_list)

        pip_list_filename = options.my_dir / f"pip_list_{options.timestamp}.txt"
        pip_list_filename.write_text("\n".join(options.pip_list), encoding=ud.DEFAULT_ENCODING)

    new_uninstalled_imports = options.installed_imports - set(options.pip_list)
    options.uninstalled_imports = options.uninstalled_imports.union(new_uninstalled_imports)
    if options.uninstalled_imports:
        if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("new_uninstalled_imports = %s", new_uninstalled_imports)
    options.installed_imports = options.installed_imports - new_uninstalled_imports
    # Once again, add packages from the options.extra_requirements dictionary if "--reqs" is specified as a runtime argument. (Do this again, just in case they got removed from the uninstalled_imports set above.)
    if getattr(options.args, "reqs", False):
        options.uninstalled_imports = options.uninstalled_imports.union(options.extra_requirements.keys())


def parse_extra_requirements(options: Options) -> None:
    """
    Parse an extra requirements file and return a dictionary of package names (and version specifiers, if present).
    The file should have one package per line, optionally with version specifiers (e.g., 'package>=1.0').
    Lines starting with '#' are treated as comments and ignored.
    
    Args:
        options: Options object containing the path to the extra requirements file.
    
    Returns:
        None. A dictionary where keys are package names and values are version specifiers is added
        to the options object as extra_requirements.
    """
    options.extra_requirements = {}
    file_content = ud.my_fopen(options.extra_requirements_file, suppress_errors=True, rawlog=options.rawlog)
    if not file_content:
        return
    # Regular expression to capture package name and version specifier
    pattern = re.compile(r'^\s*([A-Za-z0-9_\-\.]+)\s*(.*)$')
    for line in file_content.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            match = pattern.match(line)
            if match:
                package                             = match.group(1)
                version_spec                        = match.group(2).strip() if match.group(2) else ""
                options.extra_requirements[package] = version_spec


def write_requirements_file_with_extras(options: Options) -> None:
    """Write the requirements file with the extra requirements added and generate a 'pretty' requirements string."""
    if logging.getLogger().isEnabledFor(logging.DEBUG): logging.debug("Writing packages to %s", options.requirements_file)
    options.pretty_requirements = ""
    # Define the symbol replacements
    replacements = [(">=", "_ge"),
                    ("<=", "_le"),
                    ("==", "_eq"),
                    ("~=", "_approx"),
                    (">", "_gt"),
                    ("<", "_lt"),
                    (",", "_and")]
    assert options.requirements_file   is not None, "options.requirements_file must be set"
    assert options.uninstalled_imports is not None, "options.uninstalled_imports must be set"
    assert options.extra_requirements  is not None, "options.extra_requirements must be set"
    with open(options.requirements_file, "w") as f:
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
                options.pretty_requirements += "_"
            options.pretty_requirements += pretty_package


def setup_virtualenv(options: Options) -> bool:
    """Setup a virtual environment and install packages."""
    use_pip_list(options)
    options.pretty_list = pretty_packages_list(options)
    # Create a virtual environment directory that starts with "failed" in case the process fails. Only remove the "failed" part if this process completes successfully.
    options.set_venv_dir(options.my_dir / f"failed-{options.venv_name}-versionless-{options.timestamp}-{options.pretty_list}")

    write_requirements_file_with_extras(options)

    if not options.rawlog: logging.info("Creating virtual environment...")
    assert options.venv_dir is not None, "options.venv_dir must be set"
    subprocess.check_call([sys.executable, "-m", "venv", os.fspath(options.venv_dir)])
    if not options.rawlog: logging.info("Virtual environment created.")

    # Activate virtual environment and install wheel
    assert options.venv_pip is not None, "options.venv_pip must be set"
    install_command = [os.fspath(options.venv_pip), "install", "wheel"]
    logging.info("Running pip install: %s", " ".join(shlex.quote(str(arg)) for arg in install_command))
    subprocess.run(install_command, check=True)
    if not options.rawlog: logging.info("Wheel installed in the virtual environment.")

    download_packages(options)
    if install_packages_simultaneously(options):
        options.simultaneous_success = True
    else:
        options.simultaneous_success = False  # This is redundant, but it's here for clarity. The 'failed' part of the venv_dir will not be removed if this is False.
        logging.error("Failed to install packages simultaneously. Trying to install packages individually to see which fail, but this venv folder will still have 'failed-' in its name...")
        if not install_packages_individually(options):
            logging.error("Failed to install packages individually.")

    # Check that all packages can be imported in the venv.
    return check_packages_in_venv(options)


def is_virtualenv() -> bool:
    """Check if currently running in a virtual environment."""
    return sys.prefix != sys.base_prefix


def load_last_used_options(options: Options) -> Options | None:
    """Look for the most recent JSON file in the script directory that matches the script name and load it into a new Options object. Ignore any JSON files created before the options.pathlibcutoff timestamp."""
    assert options.script_dir    is not None, "options.script_dir must be set"
    assert options.python_script is not None, "options.python_script must be set"
    pattern = re.compile(r"last-used-on-(\d{8}-\d{6})")
    json_files = [
        f
        for f in options.script_dir.iterdir()
        if f.name.startswith("." + options.python_script.name)
        and f.suffix.casefold() == ".json"
        and (m := pattern.search(f.name))        # extract timestamp
        and m.group(1) >= options.pathlibcutoff  # compare as strings
    ]
    if not json_files:
        if not options.rawlog: logging.info("No previous JSON files found in the script directory.")
        return None
    if len(json_files) > 1:
        json_files.sort(key=lambda x: dt.datetime.strptime(x.name.split("-")[-2] + x.name.split("-")[-1].replace(".json", ""), "%Y%m%d%H%M%S"), reverse=True)
    return ud.load_options_from_json(options, options.script_dir / json_files[0])


def load_last_used_venv_dir(options: Options) -> Path | None:
    """Look for the most recent JSON file in the script directory that matches the script name and return the venv_dir from it."""
    last_used_options = load_last_used_options(options)
    if not last_used_options:
        if not options.rawlog: logging.info("No last used options found, so no venv directory to return.")
        return None
    elif not hasattr(last_used_options, "venv_dir"):
        if not options.rawlog: logging.info("Last used options do not have a venv_dir attribute.")
        return None
    elif last_used_options.venv_dir is None:
        if not options.rawlog: logging.info("Last used venv directory is None.")
        return None
    elif not ud.safe_is_dir(last_used_options.venv_dir):
        if not options.rawlog: logging.warning("Last used venv directory %s is no longer valid.",
                                               os.fspath(last_used_options.venv_dir))
        return None
    else:
        if not options.rawlog: logging.info("Last used venv directory found: %s",
                                            os.fspath(last_used_options.venv_dir))
        return last_used_options.venv_dir


def load_last_used_venv_python(options: Options) -> Path | None:
    """
    Look for the most recent JSON file in the script directory that matches the script name and return the venv_python from it.
    
    Args:
        options: Options object containing settings and paths.
    
    Returns:
        The Path object of the last used venv_python, or None if not found or invalid.
    """
    last_used_options = load_last_used_options(options)
    if not last_used_options:
        if not options.rawlog: logging.info("No last used options found, so no venv_python to return.")
        return None
    elif not hasattr(last_used_options, "venv_python"):
        if not options.rawlog: logging.info("Last used options do not have a venv_python attribute.")
        return None
    elif last_used_options.venv_python is None:
        if not options.rawlog: logging.info("Last used venv_python is None.")
        return None
    elif not ud.safe_is_file(last_used_options.venv_python):
        if not options.rawlog: logging.warning("Last used venv_python %s is no longer valid.",
                                               os.fspath(last_used_options.venv_python))
        return None
    else:
        if not options.rawlog: logging.info("Last used venv_python found: %s",
                                            os.fspath(last_used_options.venv_python))
        return last_used_options.venv_python


def latest_venv(final_venv_folders: dict[Path, dict[str, int]]) -> Path | None:
    """
    Return the folder Path that has the latest timestamp.
    
    Args:
        final_venv_folders: A dictionary where keys are folder paths (as strings or
                            os.PathLike objects) and values are dictionaries containing
                            metadata about each folder, including a 'timestamp' key.
    
    Returns:
        The Path object of the folder with the latest timestamp, or None if no valid
        folder is found.
    """
    latest_folder:   Path | None = None
    latest_timestamp: int | None = None
    for folder, data in final_venv_folders.items():
        if latest_timestamp is None or data['timestamp'] > latest_timestamp:
            latest_timestamp = data['timestamp']
            latest_folder    = folder
    return latest_folder


def oldest_venv(final_venv_folders: dict[Path, dict[str, int]]) -> Path | None:
    """
    Return the folder Path that has the oldest timestamp.

    Args:
        final_venv_folders: A dictionary where keys are folder paths (as strings or
                            os.PathLike objects) and values are dictionaries containing
                            metadata about each folder, including a 'timestamp' key.
    
    Returns:
        The Path object of the folder with the oldest timestamp, or None if no valid
        folder is found.
    """
    oldest_folder:   Path | None = None
    oldest_timestamp: int | None = None
    for folder, data in final_venv_folders.items():
        if oldest_timestamp is None or data['timestamp'] < oldest_timestamp:
            oldest_timestamp = data['timestamp']
            oldest_folder    = folder
    return oldest_folder


def smallest_venv(final_venv_folders: dict[Path, dict[str, int]]) -> Path | None:
    """
    Return the folder Path that has the fewest packages.

    Args:
        final_venv_folders: A dictionary where keys are folder paths (as strings or
                            os.PathLike objects) and values are dictionaries containing
                            metadata about each folder, including a 'num_packages' key.
    
    Returns:
        The Path object of the folder with the fewest packages, or None if no valid
        folder is found.
    """
    smallest_folder: Path | None = None
    smallest_num_packages: int | None = None
    for folder, data in final_venv_folders.items():
        if smallest_num_packages is None or data['num_packages'] < smallest_num_packages:
            smallest_num_packages = data['num_packages']
            smallest_folder       = folder
    return smallest_folder


def check_venv_dir(options: Options, options_from_cache: Options) -> bool:
    """
    Check if the last used venv is still valid.
    
    Args:
        options:            Options object containing the current settings.
        options_from_cache: Options object loaded from the last used JSON file.

    Returns:
        True if the cached venv directory is valid and meets the current requirements,
        False otherwise.
    """
    if hasattr(options_from_cache, "venv_dir") and options_from_cache.venv_dir is not None:
        # This might be loaded from an old options file which used strings.
        options_from_cache.venv_dir = ud.ensure_path(options_from_cache.venv_dir)
        if ud.safe_is_dir(options_from_cache.venv_dir):
            if options.uninstalled_imports.issubset(options_from_cache.uninstalled_imports):
                options_from_cache.uninstalled_imports = options.uninstalled_imports
                options_from_cache.installed_imports   = options.installed_imports
                if check_packages_in_venv(options_from_cache):
                    return True
                else:
                    logging.error("The cached venv directory %s failed check_packages_in_venv.",
                                  os.fspath(options_from_cache.venv_dir))
            else:
                if not options.rawlog:
                    logging.info("The cached venv directory %s does not have all the currently required packages.",
                                 os.fspath(options_from_cache.venv_dir))
        else:
            if not options.rawlog:
                logging.info("The cached venv directory %s is no longer valid.",
                             os.fspath(options_from_cache.venv_dir))
    return False


def find_match_dir_in_cache(options: Options) -> Path | None:
    """
    Try to find a matching virtual environment directory in the cache.

    Args:
        options: Options object containing the necessary parameters.

    Returns:
        The path to the matching virtual environment directory if found, otherwise None.

    Raises:
        None, but logs errors if the combination of flags is invalid, if no matching venv is found,
        or if the cached venv is invalid.
    """
    assert options.args is not None  # For mypy
    if not getattr(options.args, "latest",    False) and \
       not getattr(options.args, "oldest",    False) and \
       not getattr(options.args, "last_used", False) and \
       not getattr(options.args, "smallest",  False):
        options.args.last_used = True  # If no flags are set, then the default is to load the last used venv in the cache
    if     getattr(options.args, "last_used", False) and \
       not getattr(options.args, "latest",    False) and \
       not getattr(options.args, "smallest",  False):
        options_last_used = load_last_used_options(options)
        if options_last_used is not None and check_venv_dir(options, options_last_used):
            return options_last_used.venv_dir
        else:
            if not options.rawlog: logging.info("Trying to load the latest matching venv now.")
        options.args.latest    = True  # If that didn't work, try to load the latest venv in the cache
        options.args.last_used = False  # And set this to False because it failed
    if not options.rawlog: logging.info("Checking the cache for a virtual environment with all the required packages...")
    # Search for all venv_name folders in my_dir:
    all_venv_folders = [f for f in options.my_dir.iterdir()
                        if ud.safe_is_dir(f) and f.name.startswith(options.venv_name)]
    # Loop through the folders and eliminate folders that clearly don't have the right packages just based on their names:
    venv_folders = []
    for folder in all_venv_folders:
        # Extract the part of the folder name after the date/time:
        pretty_list = folder.name.split("-")[4:]
        # Create a known_packages set from the pretty_list:
        known_packages:     set[str] = set()
        number_unknown_packages: int = 0
        for item in pretty_list:
            if item == "and":
                # Extract the number of unknown packages from the last part of the pretty_list:
                number_unknown_packages = int(pretty_list[-2].split("-")[0])
                break
            known_packages.add(item)
        missing_packages = options.uninstalled_imports - known_packages
        if len(missing_packages) <= number_unknown_packages:
            venv_folders.append(folder)
    # Loop through possibly valid venv folders and compare requirements in detail.
    final_venv_folders: dict[Path, dict[str, int]] = {}
    for folder in venv_folders:
        this_requirements_file: Path = options.my_dir / folder / "requirements.txt"
        with open(this_requirements_file, "r") as file:
            requirements = set(file.read().splitlines())
        if options.uninstalled_imports.issubset(requirements):
            match = re.search(r'(\d{8})-(\d{6})', folder.name)
            if not match:
                if logging.getLogger().isEnabledFor(logging.DEBUG):
                    logging.debug("Skipping folder %s because no YYYYMMDD-HHMMSS timestamp was found.",
                                os.fspath(folder))
                continue
            ts_int = int(match.group(1) + match.group(2))
            final_venv_folders[folder] = {"timestamp"    : ts_int,
                                          "num_packages" : len(requirements)}
    if not final_venv_folders:
        if not options.rawlog: logging.info("No matching venv folders found in the cache.")
    else:
        if not options.rawlog: logging.info("Found %d matching venv folders in the cache.",
                                            len(final_venv_folders))
        if     getattr(options.args, "latest",    False) and \
           not getattr(options.args, "oldest",    False) and \
           not getattr(options.args, "last_used", False) and \
           not getattr(options.args, "smallest",  False):
            # Return the latest venv in the cache which has all the packages needed now
            options_latest = copy.deepcopy(options)
            latest_venv_folder: Path | None = latest_venv(final_venv_folders)
            if latest_venv_folder is None:
                if not options.rawlog:
                    logging.error("Could not determine the latest venv folder from the cache.")
                return None
            options_latest.set_venv_dir(latest_venv_folder)
            options_latest.uninstalled_imports = options.uninstalled_imports
            if check_venv_dir(options, options_latest):
                return options_latest.venv_dir
            else:
                if not options.rawlog:
                    logging.error("The latest venv in the cache is invalid. Giving up on the cache and starting from scratch.")
                return None
        elif        getattr(options.args, "oldest",    False) and \
                not getattr(options.args, "latest",    False) and \
                not getattr(options.args, "last_used", False) and \
                not getattr(options.args, "smallest",  False):
            # Return the oldest venv in the cache which has all the packages needed now
            options_oldest = copy.deepcopy(options)
            oldest_venv_folder: Path | None = oldest_venv(final_venv_folders)
            if oldest_venv_folder is None:
                if not options.rawlog:
                    logging.error("Could not determine the oldest venv folder from the cache.")
                return None
            options_oldest.set_venv_dir(oldest_venv_folder)
            options_oldest.uninstalled_imports = options.uninstalled_imports
            if check_venv_dir(options, options_oldest):
                return options_oldest.venv_dir
            else:
                if not options.rawlog:
                    logging.error("The oldest venv in the cache is invalid. Giving up on the cache and starting from scratch.")
                return None
        elif        getattr(options.args, "smallest",  False) and \
                not getattr(options.args, "latest",    False) and \
                not getattr(options.args, "oldest",    False) and \
                not getattr(options.args, "last_used", False):
            # Return the smallest venv in the cache which has all the packages needed now
            options_smallest = copy.deepcopy(options)
            smallest_venv_folder: Path | None = smallest_venv(final_venv_folders)
            if smallest_venv_folder is None:
                if not options.rawlog:
                    logging.error("Could not determine the smallest venv folder from the cache.")
                return None
            options_smallest.set_venv_dir(smallest_venv_folder)
            options_smallest.uninstalled_imports = options.uninstalled_imports
            if check_venv_dir(options, options_smallest):
                return options_smallest.venv_dir
            else:
                if not options.rawlog:
                    logging.error("The smallest venv in the cache is invalid. Giving up on the cache and starting from scratch.")
                return None
        else:  # This should never happen
            logging.error(f"Invalid combination of flags!\n"
                          f"{getattr(options.args, 'latest',    False) = }\n"
                          f"{getattr(options.args, 'oldest',    False) = }\n"
                          f"{getattr(options.args, 'last_used', False) = }\n"
                          f"{getattr(options.args, 'smallest',  False) = }")
    return None


STANDARD_LIB_PATHS: tuple[Path, ...] = (Path("/") / "usr" / "lib",
                                        Path("/") / "usr" / "local" / "lib",
                                        Path("/") / "usr" / "lib64",
                                        Path("/") / "usr" / "local" / "lib64")

STANDARD_LIB_NAMES: tuple[str, ...] = ("lib", "lib64")


def is_standard_path(options: Options, path: str | os.PathLike[str]) -> bool:
    """Check if the given path is a standard system path or part of a virtual environment."""
    p = ud.ensure_path(path)
    # Check if path is inside standard system paths
    for std_path in STANDARD_LIB_PATHS:
        if p.is_relative_to(std_path):  # Python 3.9+
            return True
    # Check if path contains anything in stay_out_list
    p_str = os.fspath(p)
    if any(s in p_str for s in options.stay_out_list):
        return True
    # Check for Virtualenv-style paths:
    # .../lib/python*/site-packages or .../lib64/python*/site-packages
    if "site-packages" in p_str:
        parts = p.parts
        for i in range(len(parts) - 1):
            comp = parts[i]
            if comp in STANDARD_LIB_NAMES:
                nxt = parts[i + 1]
                if nxt.startswith("python"):  # also matches "python"
                    return True
    return False


def only_search_here_filename_boolean(filename: str | os.PathLike[str], thestring: str) -> bool:
    """Check if the given filename contains thestring, which is used to determine if the search is limited to the current directory."""
    return thestring in os.fspath(filename)


def search_anywhere_filename_boolean(filename: str | os.PathLike[str], thestring: str) -> bool:
    """Check if the given filename does NOT contain thestring. By default, those files are assumed to have been created by searching above the current directory."""
    return thestring not in os.fspath(filename)


def only_search_here_path_boolean(options: Options, path: str | os.PathLike[str]) -> bool:
    """Check if the given path is in the current directory."""
    return Path(path).absolute().is_relative_to(options.cwd)


def search_anywhere_path_boolean(options: Options, path: str | os.PathLike[str]) -> bool:
    """Return True regardless."""
    return True


def dict_of_custom_modules(options: Options) -> dict[str, Path]:
    """Create (or load) a dictionary of all local custom modules in the non-standard sys.path directories and their associated filepaths."""
    # If --rc and --no-cache were not specified, look for a pickle file with the custom modules dictionary the last time this script was run.

    # I.f.f. options.search_above_this_dir is True, then search above the current directory for custom modules.
    # Either way, only load custom module pickle files that searched in the same places as requested.
    search_above_text_to_match = "only_search_here_"  # For legacy reasons, custom module pickle files are assumed to have searched above the current directory unless this text is present in the filename.
    if options.search_above_this_dir:
        search_above_text_to_write = "_"  # This will be added to the filename of the custom modules pickle file.
        search_constraint_filename_boolean = search_anywhere_filename_boolean
        search_constraint_path_boolean     = search_anywhere_path_boolean
    else:
        search_above_text_to_write = search_above_text_to_match  # This will be added to the filename of the custom modules pickle file.
        search_constraint_filename_boolean = only_search_here_filename_boolean
        search_constraint_path_boolean     = only_search_here_path_boolean

    log = logging.getLogger()  # Prebind the logger to avoid repeated global lookups in hot loop
    if log.isEnabledFor(logging.DEBUG): logging.debug("Searching for custom modules pickle files with constraint: search_above_text_to_match = %s",
                  search_above_text_to_match)
    if not getattr(options.args, "rc",       False) and \
       not getattr(options.args, "no_cache", False):
        try:
            potential_files = [file for file in options.cwd.iterdir()
                               if file.name.startswith(f".{options.my_name}_custom_modules_") and
                                  file.suffix.casefold() == ".pkl" and
                                  ud.COMPUTER_NAME in file.name and
                                  search_constraint_filename_boolean(file.name, search_above_text_to_match)]
            if not potential_files:
                if not options.rawlog:
                    logging.info("No existing custom modules pickle files found in the current directory.")
            else:
                # If multiple files are found, pick the most recent one based on the timestamp in the filename.
                potential_files_with_timestamps: list[tuple[Path, str]] = [
                    (file, ts)
                    for file in potential_files
                    if (ts := ud.extract_timestamp(file.name)) is not None
                ]
                if not potential_files_with_timestamps:
                    if not options.rawlog:
                        logging.info("No valid timestamps found in custom modules pickle filenames.")
                else:
                    # Sort by timestamp descending
                    potential_files_with_timestamps.sort(key=lambda x: x[1], reverse=True)
                    most_recent_file = potential_files_with_timestamps[0][0]
                    most_recent_timestamp = potential_files_with_timestamps[0][1]
                    if not options.rawlog:
                        logging.info("Loading custom modules from most recent pickle file: %s", most_recent_file)
                    with open(most_recent_file, "rb") as f:
                        loaded_modules = pickle.load(f)
                    if most_recent_timestamp < options.pathlibcutoff:
                        if not options.rawlog:
                            logging.info("Custom modules file %s is from date %s "
                                         "which is older than the point when "
                                         "paths were stored as Paths (which happened on %s). "
                                         "Converting all paths to pathlib.Path objects.",
                                         most_recent_file, most_recent_timestamp, options.pathlibcutoff)
                        normalized: dict[str, Path] = {k: ud.ensure_path(v) for k, v in loaded_modules.items()}
                    else:
                        # If the pickle already contains Paths, narrow the type for mypy
                        normalized = {k: (v if isinstance(v, Path) else ud.ensure_path(v)) for k, v in loaded_modules.items()}
                    return normalized
        except Exception:
            logging.exception("Error loading custom modules from pickle file.")
            logging.error("Falling back to regenerating the custom modules dictionary from sys.path.")

    custom_modules: dict[str, Path] = {}
    package_dirs:         set[Path] = set()  # directories confirmed to be packages

    # Use lru_cache to speed up repeated calls to is_standard_path()
    @lru_cache(maxsize=8192)
    def _is_std_path_cached(p: str | os.PathLike[str]) -> bool:
        """Check if a path is a standard library path. Cached for speed."""
        return is_standard_path(options, p)

    # Prebind a few globals/attributes to locals before os.walk to cut repeated global lookups:
    is_std       = _is_std_path_cached
    endswith_ext = ud.PYTHON_EXTENSIONS
    safe_is_file = ud.safe_is_file
    safe_is_dir  = ud.safe_is_dir

    if log.isEnabledFor(logging.DEBUG): logging.debug("Generating custom modules dictionary from sys.path...")
    for path in map(Path, sys.path):
        if not is_std(path) and safe_is_dir(path) and search_constraint_path_boolean(options, path):
            if log.isEnabledFor(logging.DEBUG): logging.debug("Checking path: %s", path)

            # Prebind a few globals/attributes to locals before os.walk to cut repeated global lookups:
            setdefault_mod   = custom_modules.setdefault
            package_dirs_add = package_dirs.add
            # Suppress any remaining (permissions related?) walking errors with onerror = ... None
            for root, dirs, files in os.walk(path, topdown=True, onerror=(lambda e: None)):
                root_path = Path(root)
                # If the root itself is standard, skip the whole subtree immediately
                if is_std(root_path):
                    dirs[:] = []  # stop descending
                    continue
                # PRUNE: remove standard subdirs in-place to avoid descending into them
                # Also collect package dirs (those with __init__.py) while we're here
                kept_dirs = []
                for d in dirs:
                    if d == "__pycache__":
                        continue
                    pkg = root_path / d
                    if is_std(pkg):
                        continue  # prune
                    kept_dirs.append(d)
                    if safe_is_file(pkg / "__init__.py"):
                        package_dirs_add(pkg)
                        # prefer packages; first occurrence wins
                        setdefault_mod(d, pkg)
                dirs[:] = kept_dirs  # apply pruning
                # Files: skip quickly by filename; only build Path when needed
                for fname in files:
                    fl = fname.casefold()
                    # fast extension + __init__ checks (exactly final extension)
                    if not fl.endswith(endswith_ext):
                        continue
                    if fl == "__init__.py":
                        continue
                    fpath = root_path / fname
                    if is_std(fpath):
                        continue
                    # if file lives inside a known package dir, skip (package already recorded)
                    if fpath.parent in package_dirs:
                        continue
                    setdefault_mod(fpath.stem, fpath)

    # Now save to a pickle file:
    current_time = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    custom_filename = f".{options.my_name}_custom_modules_{ud.COMPUTER_NAME}{search_above_text_to_write}{current_time}.pkl"
    with open(custom_filename, "wb") as f_out:
        if not options.rawlog:
            logging.info("Saving custom modules to %s", custom_filename)
        pickle.dump(custom_modules, f_out, protocol=pickle.HIGHEST_PROTOCOL)  # Use highest protocol for efficiency because we don't need backward compatibility for caching purposes
    return custom_modules


if __name__ == "__main__":
    main()
