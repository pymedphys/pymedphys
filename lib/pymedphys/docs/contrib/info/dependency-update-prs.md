`lib/pymedphys/docs/contrib/info/dependency-update-prs.md`

```md
# Reviewing automated dependency update PRs

Automated dependency update PRs should be boring. This page explains what the
automation does, what the reviewer should check, and when it is safe to merge.

## What creates these PRs?

Automated dependency update PRs are created by `.github/workflows/deps.yml`.

That workflow should:

1. run on a schedule and also allow manual dispatch
2. check out the repository
3. run `uv lock --upgrade`
4. stop without opening a PR if `uv.lock` did not change
5. run a focused validation suite if `uv.lock` changed
6. open a PR only if that validation passes

The PR should usually have:

- title: `⬆️ Update dependencies`
- branch: `deps/update-<run_number>`
- label: `dependencies`

## What validation should run before the PR opens?

The dependency update workflow should run a focused smoke suite before opening a
PR:

- install from the updated lockfile
- run a representative pytest subset
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

If you want to reproduce the intended smoke suite locally:

```bash
uv sync --frozen --extra user --extra tests --extra docs

uv run pytest -q --maxfail=1 \
  -m "not slow and not cypress and not mosaiqdb and not anthropic_key" \
  lib/pymedphys/tests/coordinates \
  lib/pymedphys/tests/delivery \
  lib/pymedphys/tests/dicom \
  lib/pymedphys/tests/gamma \
  lib/pymedphys/tests/interp \
  lib/pymedphys/tests/logfiles \
  lib/pymedphys/tests/metersetmap \
  lib/pymedphys/tests/trf \
  lib/pymedphys/tests/utilities

uv run pymedphys dev docs

uv build --wheel
uv venv .wheel-test
source .wheel-test/bin/activate
uv pip install dist/*.whl
pymedphys --help
python -c "import pymedphys; print(pymedphys.__version__)"
```

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
2. the validation failed, so the workflow never opened the PR

If you suspect the second case, run the workflow manually and inspect the logs.
```
