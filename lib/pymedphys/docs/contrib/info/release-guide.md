# pymedphys Release Procedure

This guide follows the active
[release workflow](https://github.com/pymedphys/pymedphys/blob/main/.github/workflows/release.yml).
It covers stable releases, development releases on production PyPI, and optional
TestPyPI rehearsals. Keep it and the [workflow guide](workflows.md) in step with
changes to publishing.

```{note}
Please ensure that you have followed the [setup guide](https://docs.pymedphys.com/en/latest/contrib/setups/index.html)
appropriate to you prior to commencing this release procedure.
```

## Determine next release version

pymedphys uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html) in the format `MAJOR.MINOR.PATCH`. For a minor release, increment `MINOR` and reset `PATCH` to zero; for example, `0.41.2` becomes `0.42.0`. While the project is pre-1.0, minor releases may contain breaking changes.

In instances where the only changes since the last release are bug fixes and none of the pymedphys API has changed, you should increment the `PATCH` value: `MAJOR.MINOR.PATCH+1`

For a development release, append a canonical PEP 440 suffix such as `.dev1`
(for example, `0.42.0.dev1`). Use `0.42.0.dev1`, not `0.42.0-dev1`. Development
releases can be published to real PyPI without declaring a stable release;
ordinary pip installs prefer available stable releases, while testers can
request the exact development version. See the
[Python packaging versioning guide](https://packaging.python.org/en/latest/discussions/versioning/).

In the remainder of this guide, `VERSION` means the package version without a
leading `v`; the Git tag is `vVERSION`. Before choosing a version, check that it
has not already been uploaded to the intended package index. Examples in this
guide are illustrative, not reservations of unused versions.

## Create a branch to prepare the release

Start from current `main` in a clean checkout. These Git commands assume that
`origin` points to `pymedphys/pymedphys`. Replace `VERSION` with the chosen version:

```bash
git fetch origin main
git switch -c VERSION-release-prep origin/main
git push --set-upstream origin VERSION-release-prep
```

## Update version in pyproject.toml

Update the version code near the top of the file:

```toml
[project]
name = "pymedphys"
version = "VERSION"
readme = "README.rst"
...
```

Refresh the lockfile's project metadata, sync the environment, and regenerate
the version and dependency files. Keep dependency upgrades in a separately
reviewed change unless they are deliberately part of this release:

```bash
uv lock
uv sync --python 3.12 --locked --extra all --group dev
uv run -- pymedphys dev propagate
```

## Update CHANGELOG

Amend the `CHANGELOG.md` file to describe the changes since the last release. Insert information for this release near the top of the file and populate the sections as appropriate (remove unused sections):

```markdown
<!-- markdownlint-disable MD024 MD039 -->

# Release Notes

All notable changes are documented here.

This project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [VERSION]

### News around this release

### Breaking changes

### New features and enhancements

### Bug Fixes

...
```

To help determine what has changed since the last release, you can inspect the [merged pull requests](https://github.com/pymedphys/pymedphys/pulls?q=is%3Apr+is%3Amerged) during that time frame.

## Create release pull request

Commit all changes to your release branch and push to GitHub. Then create a Pull Request of this branch into main. Add the `full-test` label so the full unit-test matrix and integration checks run before merging. Require the CI and security summaries to pass, and inspect their constituent checks as described in the [workflow guide](workflows.md).

### Troubleshooting issues

Inspect the failing job before changing dependencies. CI uses the committed
lockfile; elapsed time alone does not mean its application dependencies have
been upgraded. Resolve a reproduced compatibility problem in the code or with
a justified dependency constraint, regenerate the lockfile and propagated
files, and rerun the affected checks. Network failures should be investigated
separately from package or dependency failures.

## Publish Release

Once the release pull request has been approved and merged, you're ready to release the new pymedphys version!

### Verify trusted publishing and deployment protection

The release workflow builds with `uv` and publishes through PyPI trusted
publishing. It does not use a PyPI API token or `poetry publish`.

Before the first release with this workflow, a repository admin and a PyPI
project owner must verify:

1. The GitHub environment `pypi` exists; `testpypi` is also configured if using
   that rehearsal route. Permit the `main` branch for manual runs and tags
   matching `v*`, as separate branch and tag rules when using selected refs.
   Configure production release approvers in `pypi`; these environment
   approvals are separate from PR reviews. If self-review is disabled, another
   authorised reviewer must approve a deployment started by the releaser.
2. Each package index has the matching trusted publisher for owner `pymedphys`,
   repository `pymedphys`, workflow `release.yml`, and environment `testpypi` or
   `pypi`, respectively. A matching GitHub environment alone does not configure
   the package index. The publisher's workflow field is the filename
   `release.yml`, without the `.github/workflows/` prefix. Follow the
   [PyPI trusted-publisher setup guide](https://docs.pypi.org/trusted-publishers/adding-a-publisher/).
3. The release commit has passed the required checks and is on `main`. A tag
   name matching `v*` does not itself prove that its commit came from `main`.

These are external settings, not protections created by the YAML file.
Do not assume that an environment or a trusted publisher already exists simply
because the workflow references its name.

### Choose the publishing route

| Trigger | Package index | GitHub distribution assets |
| --- | --- | --- |
| Publish a GitHub release, including a prerelease | Production PyPI | Uploaded after PyPI succeeds |
| Manual workflow with `dry_run=true` | TestPyPI only | Not uploaded |
| Manual workflow with `dry_run=false` | Production PyPI only | Not uploaded |

Each run publishes to one index. The manual input description currently says
"also to PyPI", but `dry_run=false` skips TestPyPI. Manual runs do not create
a GitHub release and do not perform the release-event tag/version check.

### Rehearse with TestPyPI (optional)

1. Open **Actions > Release > Run workflow** in GitHub.
2. Confirm that the current tip of `main` is the intended reviewed commit,
   then select `main`. Selecting the branch uses its tip at dispatch time;
   check the run's commit SHA rather than assuming it selects an older commit.
3. Leave **dry_run** set to **true** and run the workflow.
4. Check the quality jobs, build/install checks, and TestPyPI publish job.
   Inspect the uploaded distribution and install the intended version from
   TestPyPI in a fresh environment before proceeding.

The TestPyPI run still performs publishing to TestPyPI; it is not a local-only
simulation. It does not publish to production PyPI.

### Publish to production PyPI

1. Confirm the version in `pyproject.toml` and the generated files match the
   intended release, and that its preparation PR has merged into `main`.
2. Create the tag at the exact reviewed commit. Replace `RELEASE_COMMIT` with
   its full SHA and `VERSION` with the package version. These commands work in
   Bash and PowerShell and do not change the checked-out branch:

   ```bash
   git fetch origin main
   git show --no-patch --oneline RELEASE_COMMIT
   git tag -a vVERSION RELEASE_COMMIT -m "PyMedPhys VERSION"
   git push origin refs/tags/vVERSION
   ```

   Inspect an existing tag instead of force-replacing it. Creating a tag alone
   does not start the Release workflow.
3. In GitHub **Releases**, create a release using that existing tag. Use the
   version as the title and the corresponding changelog entries as the notes.
   For a development version, select **Set as a pre-release** and do not mark
   it as the latest stable release. Then **Publish release**; saving a draft
   does not start publishing.

   The `release: published` event also runs for
   [published prereleases](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#release).
   GitHub's prerelease checkbox controls presentation on GitHub; the `.devN`
   package-version suffix controls development-release selection by pip.

   The workflow runs lint, type checks, the full unit-test matrix, integration
   tests, and distribution checks. Plain `uv build` builds the sdist and then
   the wheel from it. The archive and isolated-install checks require the tag
   to equal `v` followed by the package version before publishing.
4. Approve the production deployment when the `pypi` environment requests it.
5. Verify the `publish-pypi` and `upload-release-assets` jobs succeeded, and
   inspect the resulting package-index release and GitHub assets.

Both destinations should contain `pymedphys-VERSION-py3-none-any.whl` and
`pymedphys-VERSION.tar.gz`. GitHub's automatic **Source code** downloads are
repository snapshots, not the Python source distribution to test. Confirm the
filenames and, when comparing the two destinations, their SHA-256 hashes.

The **Release Summary** job is a report, not a pass/fail gate. Inspect the
workflow result and its publishing jobs; a successful report alone does not
mean publishing succeeded. GitHub release publication precedes the workflow,
so a published GitHub release alone also does not confirm PyPI publication.

The workflow additionally supports a manual run with **dry_run=false**. This
publishes to production PyPI and should be reserved for a deliberate release
or recovery operation after checking the target commit and existing version.
It does not create a GitHub release or upload its assets. Do not run it in
parallel with a release-triggered publish of the same version.

### Verify both published distribution formats

Test the wheel and sdist separately, outside the checkout, with Python 3.12
(within the current supported range in `pyproject.toml`). The commands below
use explicit environment executables, so activation is unnecessary. Replace
`VERSION` with the exact published version and keep the same terminal open.
`uv` must be available; see the [setup guides](../setups/index.rst).

#### Create independent environments

Windows PowerShell:

```powershell
$releaseVersion = "VERSION"
$releaseTestRoot = Join-Path $env:TEMP ("pymedphys-release-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $releaseTestRoot | Out-Null
Set-Location $releaseTestRoot
uv venv --python 3.12 --seed wheel-env
uv venv --python 3.12 --seed source-env
$wheelPython = Join-Path $releaseTestRoot "wheel-env\Scripts\python.exe"
$sourcePython = Join-Path $releaseTestRoot "source-env\Scripts\python.exe"
```

Bash (Linux or macOS):

```bash
release_version="VERSION"
release_test_root=$(mktemp -d)
cd "$release_test_root"
uv venv --python 3.12 --seed wheel-env
uv venv --python 3.12 --seed source-env
wheel_python="$release_test_root/wheel-env/bin/python"
source_python="$release_test_root/source-env/bin/python"
```

Stop if environment creation fails. `--seed` supplies pip; neither environment
should already contain PyMedPhys.

#### Install the wheel and source archive

Windows PowerShell (stop if either command fails):

```powershell
& $wheelPython -I -m pip install --index-url https://pypi.org/simple --force-reinstall --no-cache-dir --only-binary=pymedphys --report wheel-install.json "pymedphys==$releaseVersion"
& $sourcePython -I -m pip install --index-url https://pypi.org/simple --force-reinstall --no-cache-dir --no-binary=pymedphys --report source-install.json "pymedphys==$releaseVersion"
```

Bash (stop if either command fails):

```bash
"$wheel_python" -I -m pip install --index-url https://pypi.org/simple --force-reinstall --no-cache-dir --only-binary=pymedphys --report wheel-install.json "pymedphys==$release_version"
"$source_python" -I -m pip install --index-url https://pypi.org/simple --force-reinstall --no-cache-dir --no-binary=pymedphys --report source-install.json "pymedphys==$release_version"
```

The wheel run must download the `.whl`. The source run must download the
`.tar.gz`, build a wheel for PyMedPhys, and install it successfully. Dependencies
may still use wheels. Keep the console output and installation reports; the
PyMedPhys entry's `download_info.url` records the selected archive. For these
production PyPI checks, verify that it points to the expected filename on
`files.pythonhosted.org`, especially if pip also has a configured extra index.

`--no-cache-dir` prevents a previously built wheel being reused, while
`--force-reinstall` prevents an existing installation satisfying the request.
`Requirement already satisfied: pymedphys` alone is not evidence of a fresh
source build. See the [pip install options](https://pip.pypa.io/en/stable/cli/pip_install/)
and [cache documentation](https://pip.pypa.io/en/stable/topics/caching/).

Python's `-I` isolates imports from the checkout and Python path overrides.
Pip's separate `--isolated` option is deliberately omitted here so required
user-level proxy or certificate settings remain available.

#### Check the installed versions, import locations, and CLI

Save the following as `check-published.py` in the temporary test directory:

```python
import importlib
import os
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

expected = sys.argv[1]
environment = Path(sys.prefix).resolve()
assert version("pymedphys") == expected

for name in ("pymedphys", "pymedphys._version", "pymedphys.dicom", "pymedphys.cli"):
    module = importlib.import_module(name)
    source = Path(module.__file__).resolve()
    assert source.is_relative_to(environment), (name, source, environment)
    if name == "pymedphys":
        assert module.__version__ == expected
        print("Package:", source)

cli_name = "pymedphys.exe" if sys.platform == "win32" else "pymedphys"
cli = Path(sys.executable).parent / cli_name
cli_env = os.environ.copy()
for name in ("PYTHONPATH", "PYTHONHOME"):
    cli_env.pop(name, None)
output = subprocess.check_output([str(cli), "--version"], env=cli_env, text=True)
assert output.strip() == f"pymedphys {expected}", output
subprocess.run([sys.executable, "-I", "-m", "pip", "check"], check=True)
print("PASS:", expected)
```

Run it with both interpreters. In PowerShell:

```powershell
& $wheelPython -I check-published.py $releaseVersion
& $sourcePython -I check-published.py $releaseVersion
```

In Bash:

```bash
"$wheel_python" -I check-published.py "$release_version"
"$source_python" -I check-published.py "$release_version"
```

Each run must print `PASS: VERSION`, a package path inside its own environment,
and `No broken requirements found.` Any traceback or non-zero exit is a failed
check. Imports and version checks alone cannot prove a source build occurred;
retain the successful build output from the installation step as well.

These are core-package smoke tests. Optionally install
`pymedphys[user,tests]==VERSION` into one test environment using its own Python,
then run `python -I -m pip check` and `python -I -m pymedphys dev tests` with
that same interpreter. The extended tests may download public datasets. Record
their results separately rather than implying the core smoke tests cover them.

### Recover from publishing or installation failures

| Symptom | Action |
| --- | --- |
| Publishing waits for approval or rejects the ref | Check the target GitHub environment's reviewers and separate branch/tag rules. |
| PyPI reports `invalid-publisher` | Check the owner, repository, `release.yml` filename, and environment in that index's trusted-publisher settings. |
| Upload fails before either file reaches the index | Correct the configuration, confirm no files were uploaded, and rerun the failed jobs. |
| A filename already exists, or only one distribution uploaded | Inspect the index and original run's artifacts before recovery. The workflow does not skip existing files automatically. |
| PyPI succeeds but GitHub asset upload fails | Check the asset job independently; do not republish to PyPI just to repair GitHub assets. |
| pip reports read timeouts followed by `No matching distribution found` | Check the failing URL and required network/proxy settings. A failed index request does not establish that a dependency is unavailable. |

For a slow connection, append `--timeout 120 --retries 1` to the relevant pip
install command. If pip's `--isolated` was added, it may exclude required user
configuration; retain Python's `-I` when retrying without that pip option.
A successful retry does not by itself establish which network setting caused
the failure. Repeat the source build with `--force-reinstall --no-cache-dir
--no-binary=pymedphys` so an earlier successful attempt cannot mask the result.

Published filenames [cannot be reused on PyPI](https://pypi.org/help/#file-name-reuse),
even after deletion. For changed package contents, choose a new version (for
example, the next `.devN`), update `pyproject.toml`, run `uv lock` and
`pymedphys dev propagate` as above, and merge the reviewed preparation change
before publishing its new tag. Do not move an existing release tag to new code.

The current workflow attaches GitHub assets after release publication.
[Immutable releases](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases)
prevent adding or replacing assets at that point. If enabling that feature,
first adapt the workflow to attach assets while the release is still a draft.

Record the version, release commit, workflow URL, OS/Python version, selected
archive formats, and actual verification results on the release-preparation PR
or release discussion. Keep observed results distinct from unrun optional
checks and unconfirmed explanations for failures.
