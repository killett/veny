# Prompt for the emmykit repository: audit the shell/alias helpers

Run this in a Claude Code session opened on the `emmykit` repository.

---

veny — until 2026-08-15 emmykit's only known consumer of these symbols — has
stopped calling emmykit's shell and alias helpers. It used to install itself by
appending an alias to a shell configuration file; it now ships a console-script
entry point (`[project.scripts] veny = "veny.cli:main"`), so the whole alias
installer was deleted.

That leaves the following symbols with no known caller:

**Functions** (`emmykit/python_env.py`, all three exported in `__init__.py`'s
`__all__`):

- `detect_shell(options)`
- `find_shell_rc_file(options)`
- `find_additional_alias_files(options)`

**`Options` fields** (`emmykit/options.py`, lines 16-20):

- `shell: str | None`
- `rc_file: Path | None`
- `alias: str | None`
- `alias_command: str | None`
- `additional_alias_files: list[Path]`

Please **audit, do not delete**. Specifically:

1. For each of the three functions, find every reference inside this
   repository — call sites, re-exports, `__all__` entries, tests, docstrings
   and documentation. Report them as `path:line`.
2. Do the same for each of the five `Options` fields. Note that `shell` and
   `alias` are short, common words: match `options.shell`, `self.shell`,
   `options.alias` and `self.alias` rather than the bare names, and say which
   spellings you searched.
3. Say whether each symbol is used **only** by the others in this list (that
   is, whether the group is self-contained and dead as a whole) or whether
   something outside the group depends on it.
4. Note that emmykit 0.4.0 is published on PyPI and all three functions are in
   `__all__`, so removing any of them is a breaking change. Recommend a
   disposition for the group — remove in a 0.5.0, deprecate with a warning
   first, or keep — with your reasoning. Do not make the change.

Report back with the reference table and the recommendation.

---

## Searching outside both repositories

The audit above covers emmykit only. To check for callers anywhere else — other
projects, scratch scripts, anything on disk — run this against whichever
directory you want to search (substitute it for `~/code`). `fd` selects the
files, `rg` counts within them, and the excludes keep vendored copies of
emmykit itself out of the count:

```bash
fd -t f -e py . ~/code \
   -E .pixi -E site-packages -E .git \
   -X rg -c -w \
      -e detect_shell \
      -e find_shell_rc_file \
      -e find_additional_alias_files
```

Output is one `path:count` line per file with at least one hit; no output means
no callers. For a single total instead of a per-file breakdown, append:

```bash
   | awk -F: '{ total += $NF } END { print total + 0 }'
```

The five `Options` fields need the attribute-access forms, since `shell` and
`alias` are too common to search bare:

```bash
fd -t f -e py . ~/code \
   -E .pixi -E site-packages -E .git \
   -X rg -c \
      -e '\.shell\b' \
      -e '\.rc_file\b' \
      -e '\.alias\b' \
      -e '\.alias_command\b' \
      -e '\.additional_alias_files\b'
```

That second one is deliberately loose and will pick up unrelated `.shell` and
`.alias` attributes on other objects; treat its output as a list of places to
look at by hand, not as a count of real callers.
