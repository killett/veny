# Project: veny

## Session resume protocol (read this first, every session)
This project may be built across multiple sessions, and a session can die
mid-run. On **every** new or resumed session, before doing anything else:

1. Read `PROGRESS.md` at the repo root. It carries the index of the current
   active work AND the project's running notebook of deferred items,
   cross-cutting decisions, gotchas, and open questions. Read all of it.
2. Open the design doc and implementation plan that `PROGRESS.md` points to.
3. Run `git log --oneline -20` to see what is already committed.
4. Resume from the first unchecked task in the plan. **Do not** redo work
   that is already committed.

If `PROGRESS.md` does not exist yet, you are at the very start of the
project; create it (with the headings described in the Durability rules
below, sections initially empty) as soon as a design or plan exists.

If Superpowers is installed and this project uses it, prefer its native
resume mechanism (`/superpowers-extended-cc:executing-plans <plan-path>`)
over reading `PROGRESS.md`'s **Current work** section by hand — that
command reads the plan's `.tasks.json` and picks up exactly where the
last session stopped. The other PROGRESS.md sections (deferred items,
decisions, gotchas, open questions) are NOT covered by Superpowers, so
read them either way.

## Durability rules (always)
- **Git is the source of truth, not the conversation.** Commit after every
  completed task, with a clear message. Never end a step with completed
  work left uncommitted.
- **Keep `PROGRESS.md` current.** The **Current work** block is an index
  — point at the design doc, plan, and task tracker; do NOT duplicate the
  task checklist into PROGRESS.md (link to the plan instead, so there's
  one place to update task state). The other sections (deferred items,
  cross-cutting decisions, gotchas, open questions) hold canonical content
  that lives nowhere else; add to them as the project teaches you things
  worth not forgetting. Refresh the "next action" line and commit
  PROGRESS.md after each task.
- **Persist the brainstorm as it forms.** During brainstorming, append
  each validated design section to the design doc and commit it — never
  leave the agreed design only in the conversation.
- **Migrate, don't duplicate.** When a deferred item or open question
  becomes active work, move it out of PROGRESS.md into the new design/plan
  rather than leaving a copy behind.

## Environment & tools

- Use `rg` instead of `grep`, `fd` instead of `find`.

## Workspace scaffolding

This project has already been scaffolded. The following files
already exist and should NOT be recreated:

- `pyproject.toml` — project metadata + ruff/mypy/pytest/coverage config
- `pixi.toml` — pixi workspace with dev dependencies (ruff, mypy, pytest, pytest-cov, pre-commit)
- `.pre-commit-config.yaml` — pre-commit hooks (ruff, ruff-format, mypy, trailing-whitespace, end-of-file-fixer, etc.)
- `.gitignore` — standard Python ignores

**Do NOT run `pixi init` or `pre-commit sample-config`.**

## Project layout

Use a `src/` layout:

```
src/
  <package_name>/
    __init__.py
    __main__.py
    ...
tests/
  __init__.py
  test_*.py
```

The package name should be the project name normalized to a valid Python identifier
(lowercase, spaces/hyphens replaced with underscores).

## Running tools

All dev tools are installed via pixi. Use `pixi run` to invoke them:

- `pixi run test` — run tests (pytest)
- `pixi run lint` — lint (ruff check .)
- `pixi run format` — format (ruff format .)
- `pixi run typecheck` — type check (mypy .)
- `pixi run pre-commit run` — run pre-commit on staged files
- `pixi run pre-commit run --files <path>` — run pre-commit on specific files
- `pixi run pre-commit run --all-files` — run pre-commit on every file
- `pixi run pre-commit install` — install the git pre-commit hook
  (`pre-commit` is only available via `pixi run` — no system binary)

To add a new dependency: `pixi add <package>`
To add a PyPI-only dependency: `pixi add --pypi <package>`

## Cross-platform conda gotchas

This project's `pixi.toml` lists `platforms = ["linux-64", "linux-aarch64", "osx-arm64", "osx-64"]`,
so `pixi install` must solve cleanly on macOS even when the actual run happens in
the Linux container. Some conda-forge packages have no `osx-arm64` build and will
fail resolution on macOS with `No candidates were found`. Move them into
`[target.linux-64.dependencies]` (already scaffolded into your `pixi.toml`)
instead of `[dependencies]`.

Symptom: `pixi add <pkg>` (or `pixi install`) fails with
`No candidates were found for <pkg>` while the package clearly exists on
conda-forge for linux-64.

Fix: edit `pixi.toml` to add the package under `[target.linux-64.dependencies]`,
then `pixi install`. Or use `pixi add --platform linux-64 <pkg>`.

Known offenders (non-exhaustive):

- `pngquant` — pulled in by `ocrmypdf`; together they force linux-64-only.
- `pytorch-cuda` — CUDA runtime, linux-only by design.

If you can swap to a lighter cross-platform alternative, prefer that
(e.g. `tesseract` + `pytesseract` + `pypdfium2` instead of `ocrmypdf`).

## First-time setup

Already done by the container entrypoint — git repo
initialized, git identity configured, dependencies
installed, pre-commit hooks active, initial scaffold
committed.
