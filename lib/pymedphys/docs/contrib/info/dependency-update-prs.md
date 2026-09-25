# Reviewing automated dependency update PRs

Automated dependency update PRs should be boring. This page explains what the
automation does, what the reviewer should check, and when it is safe to merge.

## What creates these PRs?

Automated dependency update PRs are created by `.github/workflows/deps.yml`.

That workflow should:

1. run on a schedule and also allow manual dispatch
2. check out the repository
3. run `uv lock --upgrade`, sync the environment, and run
   `pymedphys dev propagate` so the exported requirements files,
   `dependency-extra.txt`, and `pyproject.hash` match the new lock
4. stop without opening a PR if `uv.lock` did not change
5. run a focused validation suite if `uv.lock` changed
6. open a PR, with the CI bot's token so CI runs on it, only if that
   validation passes

The PR should usually have:

- title: `chore: update dependencies`
- branch: `deps/update-<run_number>`
- label: `dependencies`

## What validation should run before the PR opens?

The dependency update workflow should run a focused smoke suite before opening a
PR:

- install from the updated lockfile
- run the unit tests (`pymedphys dev tests -m "not slow"`)
- build the docs
- build a wheel and install it into a clean virtual environment

This is intentionally smaller than the full CI suite. The goal is to avoid
opening obviously broken update PRs, not to duplicate every CI job.

## Fast review path

In the common case, these PRs are routine.

If all of the following are true, the PR is usually safe to merge once CI is
green:

- only dependency-related files changed
- the CI checks are green
- there are no surprising package additions or removals
- there are no unexpected major-version jumps

## What the reviewer should do

1. Read the PR title and body.
2. Open **Files changed** and inspect the full diff.
3. Confirm the diff is actually limited to dependency updates.
4. Look for:
   - new packages
   - removed packages
   - major-version bumps
   - changes to core scientific or build tooling
5. Check the workflow results, especially:
   - unit tests
   - docs build
   - wheel build/install smoke test
6. Merge if the diff is sensible and CI is green.

## Important note about the PR body

The PR body is only a summary. It is useful, but it is not the full review
surface.

Always inspect the full **Files changed** tab before merging.

## When to slow down

Do a more careful review if any of these are true:

- a major version changed
- a package was added or removed
- a core scientific dependency changed
  - for example: `numpy`, `scipy`, `pandas`, `pydicom`, `numba`,
    `matplotlib`, `scikit-learn`
- docs tooling changed and the docs build failed
- packaging/build tooling changed
- the PR touches files other than dependency-related files

In those cases, either push a fix to the branch or close the PR and handle the
update manually.

## Manual commands for a cautious reviewer

Run these preparation commands from the repository root in Bash or PowerShell:

```shell
uv sync --python 3.12 --locked --extra all --group dev
uv run pymedphys dev propagate

uv run pymedphys dev tests -m "not slow" --maxfail=3

uv run pymedphys dev docs

uv build --wheel
```

Then install and smoke-test the wheel using the block for your shell. Keep only
the newly built PyMedPhys wheel in `dist`; move any older wheels out first.

### Linux/macOS (Bash)

```bash
uv venv .wheel-test
source .wheel-test/bin/activate
uv pip install dist/*.whl
pymedphys --help
python -c "import pymedphys; print(pymedphys.__version__)"
```

### Windows (PowerShell)

```powershell
uv venv .wheel-test
.\.wheel-test\Scripts\Activate.ps1
$wheelFiles = @(Get-ChildItem -Path .\dist\pymedphys-*.whl -File)
if ($wheelFiles.Count -ne 1) {
    throw 'Expected exactly one PyMedPhys wheel in dist. Move older wheels out first.'
}
$wheelPath = $wheelFiles[0].FullName
uv pip install $wheelPath
pymedphys --help
python -c "import pymedphys; print(pymedphys.__version__)"
```

`$wheelPath` is the wheel's resolved absolute filename, so `uv pip install`
receives a concrete path rather than a wildcard or a hard-coded version.

## Merge checklist

- [ ] The PR only changes dependency-related files
- [ ] CI is green
- [ ] No unexpected package additions or removals
- [ ] No suspicious major-version jumps, or they were reviewed deliberately
- [ ] Docs build passed
- [ ] Wheel build/install smoke test passed

## What if no dependency update PR appeared?

That usually means one of two things:

1. `uv lock --upgrade` produced no changes
2. the workflow failed, including validation or CI bot authentication

If you suspect the second case, run the workflow manually and inspect the logs.
