#!/usr/bin/env bash
#
# smoke-install.sh — build the wheel, install it into a throwaway virtual
# environment, and prove the console script entry point works end to end.
#
# Nothing in-process can check [project.scripts]: that string is interpreted
# only by an installer. This is the only test that exercises it.
#
# Needs the network (pip resolves emmykit) and builds a real venv, so it is
# NOT part of `pixi run test`. Run it before publishing.

set -euo pipefail

repo_root=$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
cd "$repo_root"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

echo "smoke: building the wheel"
rm -rf dist
python -m build --wheel --outdir dist >/dev/null

wheel=$(ls dist/veny-*.whl | head -1)
[[ -n "$wheel" ]] || { echo "smoke: no wheel in dist/" >&2; exit 1; }
echo "smoke: built $wheel"

echo "smoke: installing into a throwaway venv"
python -m venv "$work/venv"
"$work/venv/bin/python" -m pip install --quiet "$wheel"

veny_bin="$work/venv/bin/veny"
[[ -x "$veny_bin" ]] || {
    echo "smoke: FAIL — $veny_bin missing; [project.scripts] did not take" >&2
    exit 1
}

# HOME is redirected for every veny invocation below so the check cannot
# write venvs or logs into the real ~/veny.
expected="veny $("$work/venv/bin/python" -c 'import veny; print(veny.__version__)')"
actual=$(HOME="$work" "$veny_bin" --version)
[[ "$actual" == "$expected" ]] || {
    echo "smoke: FAIL — --version printed '$actual', expected '$expected'" >&2
    exit 1
}

HOME="$work" "$veny_bin" --help >/dev/null || {
    echo "smoke: FAIL — --help did not run" >&2
    exit 1
}

echo "smoke: checking exit-status propagation"
printf 'import sys\nsys.exit(7)\n' > "$work/fixture.py"
set +e
(cd "$work" && HOME="$work" "$veny_bin" fixture.py >"$work/out.txt" 2>&1)
status=$?
set -e
[[ "$status" -eq 7 ]] || {
    echo "smoke: FAIL — fixture exited $status, expected 7" >&2
    tail -20 "$work/out.txt" >&2
    exit 1
}

echo "smoke: OK (console script installed, --version matched, exit status 7 propagated)"
