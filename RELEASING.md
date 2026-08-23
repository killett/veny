# Releasing veny

Releases are tag-driven. Pushing a `v*` tag to GitHub is the *only* action
that publishes to PyPI. Nothing is ever uploaded from a laptop.

## The one-time setup (already done, recorded here so it can be redone)

PyPI publishes via **Trusted Publishing** (OIDC), so there is no API token
stored anywhere — not in the repository, not in GitHub secrets. The trust
relationship is registered once on PyPI itself, at
<https://pypi.org/manage/account/publishing/>:

| Field | Value |
| --- | --- |
| PyPI project name | `veny` |
| Owner | `killett` |
| Repository name | `veny` |
| Workflow name | `release.yml` |
| Environment name | `pypi` |

The `pypi` environment must also exist on the GitHub side (Settings →
Environments). The publish job declares `environment: pypi` and
`permissions: id-token: write`; without both, PyPI rejects the OIDC token.

The PyPI account needs 2FA enabled. This is a PyPI requirement, not ours.

## Cutting a release

1. Land everything you want in the release on `main`, and let `test.yml`
   go green.

2. Bump the version. veny single-sources it from one line:

   ```
   src/veny/__init__.py:    __version__: str = "0.2.2"
   ```

   Hatchling reads that line at build time (`[tool.hatch.version]` in
   `pyproject.toml`), so it is the only place the number lives. Commit the
   bump on its own.

3. Tag it, matching the version exactly with a leading `v`:

   ```
   git tag -a v0.2.3 -m "Release v0.2.3"
   ```

4. Confirm the build agrees before you push anything:

   ```
   pixi run build
   ls dist/
   ```

   The filenames must read `veny-0.2.3-*`. A local tag is cheap to delete
   and redo; a wrong version on PyPI is not (see below).

5. Push the tag — this is the irreversible step:

   ```
   git push origin v0.2.3
   ```

6. Watch it: `gh run watch`. The workflow builds the sdist and wheel,
   runs `twine check --strict`, **asserts that the tag equals
   `veny.__version__`**, and only then publishes.

7. Verify from the outside, in a throwaway environment:

   ```
   uv tool install veny==0.2.3
   veny --version
   ```

8. Cut the GitHub Release:

   ```
   gh release create v0.2.3 --verify-tag --generate-notes
   ```

## Why the workflow re-checks the tag against `__version__`

veny's version is a static string, not derived from git tags, so the two
*can* disagree — tag `v0.2.3` while `__init__.py` still says `0.2.2` and the
build happily produces `veny-0.2.2`, overwriting nothing and publishing the
wrong thing. The `Assert tag matches __version__` step in `release.yml`
fails the build in that case, before the publish job ever runs.

The alternative — deriving the version from the tag with `hatch-vcs` — was
considered and rejected: veny is not installed into its own development
environment (`pixi.toml` sets `PYTHONPATH=src` instead of doing an editable
install), so `importlib.metadata.version("veny")` raises
`PackageNotFoundError` there, and the `_version.py` file approach would put
an intra-package import into `src/veny/__init__.py`, which
`tests/test_layering.py` forbids by design.

## PyPI is immutable

A filename, once uploaded to PyPI, can never be reused — not after a
`yank`, not after a delete. If a release fails:

- **Nothing uploaded yet** (the build job failed, or the publish job failed
  before transferring a file): delete the tag locally and remotely, fix the
  problem, and re-tag the same version.

  ```
  git tag -d v0.2.3
  git push origin :refs/tags/v0.2.3
  ```

- **Something uploaded**: that version number is spent. Do not try to
  delete and re-upload. Fix the problem and release the next patch version.

## Not published to conda-forge

veny is on GitHub and PyPI only. A conda-forge recipe would also require a
recipe for `emmykit`, which has no conda-forge package, and co-maintaining
that feedstock. `uv`, the other runtime dependency, is already on
conda-forge.
