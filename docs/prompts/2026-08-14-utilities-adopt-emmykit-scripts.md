# Prompt: adopt emmykit's five embedded scripts into the utilities repo

Paste everything below the line into a Claude Code session opened in the
`killett/utilities` repository.

---

Adopt five standalone command-line programs that currently live inside the
`emmykit` package as string constants, turning each into a real `.py` file in
this repository.

## Why here

Each of the five is an argparse command-line program with its own
`if __name__ == "__main__":` block, and each *consumes* `emmykit` as a library
— exactly the shape this repository already holds (`check_internet.py`,
`download_file.py`, `detect_country.py`), and exactly what its description
says: "General use python scripts. Most of them import emmykit."

Stored as string constants inside the library they import, they are the only
code in `emmykit` that cannot be linted, type-checked, tested, imported, or
navigated in an editor. Moving them here fixes all of that at once.

They were previously delivered by a third program (`veny`) writing them to
disk from those constants. `veny` is dropping that behaviour, and `emmykit`
0.4.0 removes the constants, so this repository becomes their only home.

## The five scripts

| Script | Lines | What it does |
| --- | --- | --- |
| `printall.py` | 260 | Search Python files and print full logical statements matching a pattern |
| `mydiff.py` | 71 | Diff two files using `emmykit`'s `my_diff()` |
| `myaudit.py` | 63 | Check Python formatting: flake8, mypy, interactive autopep8 |
| `multireplace.py` | 60 | Find files by glob and run interactive find/replace on each |
| `treeview.py` | 63 | Print a tree view of a directory |

## How to get their exact source

Do not rewrite them from memory or from the table above. Extract the current
text verbatim:

```bash
python -m venv /tmp/ekextract
/tmp/ekextract/bin/pip install 'emmykit==0.3.4'
/tmp/ekextract/bin/python - <<'PY'
from pathlib import Path
import emmykit as ek
out = Path("/tmp/ekextract/scripts"); out.mkdir(exist_ok=True)
for const, name in [("PRINTALL_SCRIPT", "printall.py"),
                    ("MYDIFF_SCRIPT", "mydiff.py"),
                    ("MYAUDIT_SCRIPT", "myaudit.py"),
                    ("MULTIREPLACE_SCRIPT", "multireplace.py"),
                    ("TREEVIEW_SCRIPT", "treeview.py")]:
    (out / name).write_text(getattr(ek, const), encoding="utf-8")
    print("wrote", name)
PY
```

Pin `0.3.4` specifically: 0.4.0 removes these constants.

## What to change in each script

1. **Replace the import preamble.** Each script currently opens with:

   ```python
   import univ_defs_sys_path_script  # Appends sys.path with the location of univ_defs.py
   import univ_defs as ud
   ```

   Both lines go. Use `import emmykit as ek` instead, matching this
   repository's existing scripts. The `sys.path` shim exists only because
   `univ_defs.py` was a loose file that nothing put on the path; `emmykit` is
   an installed package, so a plain import works.

2. **Rename the alias at every call site:** `ud.` becomes `ek.`. Between them
   the five scripts use roughly two dozen `emmykit` names — `ek.my_diff`,
   `ek.run_mypy`, `ek.interactive_flake8`, `ek.treeview_new_files`,
   `ek.ask_and_replace`, `ek.multireplace`, `ek.configure_logging`,
   `ek.print_all_errors`, `ek.safe_is_file`, `ek.my_fopen`,
   `ek.DEFAULT_EXCLUDE_DIRS`, `ek.IGNORED_CODES`, the ANSI colour constants,
   and others. Verify none remain: `rg '\bud\.' *.py` must come back empty.

3. **Match this repository's conventions**, using `check_internet.py` as the
   reference: `from __future__ import annotations` first, a `__version__`
   string, a local `Options` class holding globals, `main()`, and
   `if __name__ == "__main__": main()`.

4. **Check the dependency surface.** `myaudit.py` uses `ek.run_mypy` and
   `ek.interactive_flake8`, which need `emmykit[lint]` (flake8, flake8-bugbear,
   autopep8) and mypy. Note that requirement wherever this repository records
   such things, and make the script fail with a clear message rather than a
   raw `ImportError` if the tooling is absent.

## Verification

For each script, before considering it done:

- It runs `--help` successfully.
- It performs its actual job once against a real input — diff two files, tree
  a directory, search a pattern, and so on. A script that only proves
  `--help` works has proved nothing about the `ud.` → `ek.` rename.
- Lint and type-check it with this repository's configured tooling. These
  files have never been checked by anything, so expect genuine findings; fix
  what is real and record anything deliberately left.

Follow this repository's testing conventions for whatever test coverage is
appropriate here.

## Order of work

Nothing blocks starting: the extraction above pins `emmykit==0.3.4`, which
still has the constants. `emmykit` 0.4.0 removes them, so land this work
before upgrading this repository's `emmykit` pin past 0.3.4.
