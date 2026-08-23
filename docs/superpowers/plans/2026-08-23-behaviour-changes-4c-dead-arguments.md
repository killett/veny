# The reconciled dead-argument list

This document supersedes the two prior "DEAD ARGUMENTS" sections: 4a's
"The 5 DEAD ARGUMENTS" in
`docs/superpowers/plans/2026-08-21-state-model-values-wiring-index.md`, and
4b's "The 8 DEAD ARGUMENTS" in
`docs/superpowers/plans/2026-08-21-last-used-persistence-wiring-index.md`.
Both named phase 4c as the owner of closing them; this table gives every row
from both a single, current disposition.

| Row (as the prior index named it) | From | Disposition |
|---|---|---|
| `run_script(rawlog=…)` at the three non-announcing sites | 4a | CLOSED by Task 4 — `announce=True` makes `rawlog` live at all four sites |
| `run_script(rawlog=…)` in `feeling_lucky` | 4b | CLOSED by Task 4 — the fourth site, same fix |
| `ResolvedImport(pip_name=import_name)` in the probe environment | 4a | OPEN — the two fields are the same string by construction and `check_packages_in_venv` reads only `import_name`; no substitution can distinguish them. Not a test gap and not deletable |
| `state.VenvHandle.for_dir(record_venv_state(...))` | 4a | OPEN, mis-filed — measured by driving, not dead. Belongs under "measured by driving"; the 4c index files it there |
| `getattr(args, 'feeling_lucky', False)` default | 4b | CLOSED by Task 5 |
| `getattr(args, 'reqs', False)` default | 4b | CLOSED by Task 5 |
| `getattr(args, 'last_used', False)` default | 4b | CLOSED by Task 5 |
| `getattr(args, 'rawlog', False)` default | 4b | CLOSED by Task 5 |
| `getattr(args, 'debug', False)` default | 4b | CLOSED by Task 5 |
| the `last_used` term inside `explicit` (both arguments) | 4b | CLOSED by Task 5 — deleted, with the 16-combination characterization test as the evidence it changed nothing |

A `getattr(args, …)` default that a test reaches is live and stays; the five
closed here were reachable from nothing, in production or in tests.
