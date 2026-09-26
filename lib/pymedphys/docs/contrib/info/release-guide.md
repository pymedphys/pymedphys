# pymedphys Release Procedure

This guide covers stable releases, development releases, and optional TestPyPI rehearsals. The [Release workflow](https://github.com/pymedphys/pymedphys/blob/main/.github/workflows/release.yml) builds, tests, and publishes every release; the [workflow guide](workflows.md) describes its jobs.

```{note}
Please ensure that you have followed the [setup guide](../setups/index.rst) appropriate to you prior to commencing this release procedure.
```

## Choose the version

In this guide, `VERSION` is the package version without a leading `v`, for example `0.42.0`, and the release tag is `vVERSION`.

pymedphys uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html) in the format `MAJOR.MINOR.PATCH`. For a minor release, increment `MINOR` and reset `PATCH` to zero; for example, `0.41.2` becomes `0.42.0`. While the project is pre-1.0, minor releases may contain breaking changes.

In instances where the only changes since the last release are bug fixes and none of the pymedphys API has changed, you should increment the `PATCH` value: `MAJOR.MINOR.PATCH+1`

A development release lets testers install unreleased changes from PyPI. Its version is the upcoming release with a [PEP 440](https://packaging.python.org/en/latest/specifications/version-specifiers/) `.devN` suffix: `0.42.0.dev1` is a development release of `0.42.0` and sorts before it. Request it explicitly with `pymedphys==0.42.0.dev1`, or enable development releases with `--pre` and a compatible version constraint. For example, `pymedphys>=0.42.0.dev1` includes that development release; `pymedphys>=0.42` excludes it even with `--pre`.

Write the version in canonical form: `0.42.0.dev1`, not `0.42.0-dev1`. The build copies the string in `pyproject.toml` into the package metadata unchanged, the release tag must equal `v` followed by that string, and the distribution filenames always use the canonical form, so any other spelling leaves them disagreeing.

`main` carries the next unpublished development version between releases (see "Prepare main for the next release" below). Before choosing a version, check that it is not already on PyPI: PyPI never lets a filename be reused for different contents, even after the file is deleted.

## Prepare the release pull request

The release tag must match `pyproject.toml` at the tagged commit, so every release version is set on `main` through a reviewed pull request.

For a development release, `main` normally carries the version already: the pull request that bumped it after the previous release set it. Check that `pyproject.toml` on `main` holds the version you intend and that it is not on PyPI, then go to "Publish the release". Open a release pull request only to choose a different version.

A stable release always needs a release pull request, which sets the version and completes the changelog.

### Create a branch

From an up-to-date clone in which `origin` is `pymedphys/pymedphys`, replacing `VERSION`:

```bash
git fetch origin main
git switch -c VERSION-release-prep origin/main
git push --set-upstream origin VERSION-release-prep
```

### Update the version

Update the version code near the top of `pyproject.toml`:

```toml
[project]
name = "pymedphys"
version = "VERSION"
readme = "README.rst"
...
```

Refresh the lockfile's project metadata, sync the environment, and regenerate the version and dependency files. Keep dependency upgrades in a separately reviewed change unless they are deliberately part of this release:

```bash
uv lock
uv sync --python 3.12 --locked --extra all --group dev
uv run -- pymedphys dev propagate
```

### Update the changelog

For a development release, leave `CHANGELOG.md` unchanged: its entries stay under `## Unreleased` until the stable release.

For a stable release, rename the `## Unreleased` heading to `## [VERSION]`, complete its entries, and remove unused sections:

```markdown
<!-- markdownlint-disable MD024 MD039 -->

# Release Notes

...

## [VERSION]

### News around this release

### Breaking changes

### New features and enhancements

### Bug Fixes

...
```

To help determine what has changed since the last release, you can inspect the [merged pull requests](https://github.com/pymedphys/pymedphys/pulls?q=is%3Apr+is%3Amerged) during that time frame.

### Open the pull request

Commit all changes, push, and open a pull request into `main`. The CI and security summaries must pass; inspect their constituent checks as described in the [workflow guide](workflows.md).

For a stable release, add the `full-test` label so the full unit-test matrix and integration checks run before merging. A development-release pull request does not need the label: the Release workflow runs the full unit-test matrix and integration tests before publishing, and a failure there only delays a pre-release. It does not run the Mosaiq database tests, which `full-test` also selects.

### If checks fail

The `full-test` label runs checks that ordinary pull requests skip: the full OS and Python matrix, slow tests, and integration tests. A release pull request changes little besides the version, so a failure usually already exists on `main` or comes from outside the repository.

- Read the failing job's log. Download errors (for example from Zenodo) and network time-outs are not code failures: re-run the job once, and investigate if it fails again.
- Most jobs install the locked dependencies from `uv.lock`, so a new dependency release cannot break them. The distribution checks are the exception: they install the built wheel with pip, which resolves the newest compatible dependencies from PyPI.

Fix a genuine failure on `main` in its own pull request, including any dependency constraint, `uv lock`, and `pymedphys dev propagate`, then merge `main` into the release branch.

## Publish the release

Once `main` carries the version to release (for a stable release, once its release pull request has been approved and merged), you're ready to release the new pymedphys version!

### Check the publishing settings

Publishing uses PyPI trusted publishing, with no stored API token. Its protection rules and trusted publishers must be configured separately in GitHub and on each package index. A workflow that references a missing GitHub environment creates it without protection rules; it does not create a PyPI trusted publisher. Check these settings before the first release from a new setup, and after any change:

1. The GitHub environment `pypi` exists, and `testpypi` too if you rehearse. Under **Deployment branches and tags**, choose **Selected branches and tags**, then add a branch rule for `main` (manual runs) and a tag rule for `v*` (releases). `pypi` has required reviewers; approving a deployment is separate from reviewing a pull request. If **Prevent self-review** is enabled, someone other than the releaser must approve.
2. PyPI, and TestPyPI if you rehearse, each have a trusted publisher with owner `pymedphys`, repository `pymedphys`, workflow `release.yml` (the filename only), and environment `pypi` or `testpypi` respectively. See the [PyPI trusted-publisher guide](https://docs.pypi.org/trusted-publishers/adding-a-publisher/).

### Choose the route

| Trigger | Package index | Tag check | GitHub release assets |
| --- | --- | --- | --- |
| Publish a GitHub release or pre-release | PyPI | Yes | Attached after PyPI and verification succeed |
| Run the workflow manually with `dry_run=true` | TestPyPI only | No | None |
| Run the workflow manually with `dry_run=false` | PyPI only | No | None |

Publish every release through a GitHub release. A manual run with `dry_run=false` builds afresh and publishes whatever version `pyproject.toml` holds on the selected ref. Use it only when no file of that version is on PyPI and the release-triggered run cannot be re-run; run it from the release tag rather than `main`, and never alongside a release-triggered run of the same version.

### Rehearse on TestPyPI (optional)

1. Open **Actions > Release > Run workflow**, select `main`, and leave **dry_run** set to **true**. The run uses the tip of `main` when it is dispatched; check that its commit SHA is the reviewed release commit.
2. Check that the quality, build, `publish-testpypi`, and three **Verify published** jobs succeed. The verify jobs install the files from TestPyPI, as they will from PyPI after the release.

Despite its name, `dry_run=true` uploads to TestPyPI, which cannot replace a file once uploaded, so rehearse each version once, before tagging it. Verification selects the PyMedPhys archives from TestPyPI's JSON Simple API and installs their exact URLs. Runtime and build dependencies use PyPI. This also works when the same PyMedPhys version exists on both indexes.

### Publish to PyPI

1. Choose the reviewed commit on `main` to release and record its full SHA (`RELEASE_COMMIT`). For a stable release this is normally the merged release-preparation commit. For a development release, choose the commit containing the changes you intend to publish, which may be later than the pull request that set the version.
2. Tag that commit. These commands work in Bash and PowerShell and do not change your checked-out branch:

   ```bash
   git fetch origin main
   git branch --remotes --contains RELEASE_COMMIT
   git show RELEASE_COMMIT:pyproject.toml
   git tag -a vVERSION RELEASE_COMMIT -m "PyMedPhys VERSION"
   git push origin refs/tags/vVERSION
   ```

   The second command must list `origin/main`, and the `version` near the top of the third command's output must be `VERSION`. If `vVERSION` already exists, stop and investigate; never move or force-push a release tag. Pushing the tag does not start the workflow.
3. In GitHub **Releases**, draft a release from the existing tag, titled `VERSION`.
   - For a stable release, use the version's changelog entries as the notes, and leave **Set as the latest release** selected.
   - For a development release, summarise the `Unreleased` changelog entries and select **Set as a pre-release**.

   The checkbox affects only GitHub; pip decides from the version string alone. A stable version marked as a pre-release still installs by default, and an unmarked development release becomes, by default, the repository's latest release.
4. Select **Publish release**. Publishing a release or a pre-release starts the workflow; saving a draft does not. The workflow runs lint, type checks, the full unit-test matrix, integration tests, and the distribution checks. The build job fails, and nothing is published, unless the tag is exactly `v` followed by the package version and that version is in canonical form.
5. Approve the `pypi` deployment when it is requested, after the tests finish.
6. Check that `publish-pypi`, `upload-release-assets`, and the three **Verify published** jobs succeeded. The **Release Summary** job only reports these results and passes regardless, and a published GitHub release does not mean that PyPI publishing succeeded.

### Check the published files

After PyPI publishing, the **Verify published** jobs install the wheel and the sdist from PyPI separately on Linux, Windows, and macOS, and require both files to match those built and tested earlier in the run. Each job uploads its pip installation reports and logs as an artefact.

Run the same check yourself where the workflow cannot, for example on another platform or behind an institutional proxy. From the root of a checkout, in Bash or PowerShell:

```bash
uv run --no-project --python 3.12 python .github/scripts/check_distributions.py --published VERSION
```

For each format, the check:

- resolves the exact PyMedPhys archive from the selected index's JSON Simple API, then installs its URL into a new environment with pip's cache disabled and the sdist forced to build (`--no-binary=pymedphys`); runtime and build dependencies use PyPI and may come as wheels;
- requires pip's installation report to name that file, served from the index's file host (`files.pythonhosted.org` for PyPI);
- checks the installed version, that `pymedphys`, `pymedphys.dicom`, and `pymedphys.cli` import from inside the environment, the `pymedphys --version` output, and `pip check`.

It prints `The distributions passed every check.` on success, and otherwise lists each failure and exits non-zero. The environments are created in temporary directories and run with `python -I`, so neither the checkout nor `PYTHONPATH` can affect them. The installation reports and pip logs are kept in the directory it prints, or in `--report-dir`.

To also require the files on PyPI to match the GitHub release assets, download the assets and pass their directory; a file that differs is rejected before it is installed. GitHub's automatic **Source code** archives are repository snapshots, not the sdist.

```bash
gh release download vVERSION --pattern "pymedphys-*" --dir release-assets
uv run --no-project --python 3.12 python .github/scripts/check_distributions.py --published VERSION --compare-with release-assets
```

Archive discovery uses Python's HTTPS support, including `HTTPS_PROXY` and `SSL_CERT_FILE`, with a 30-second network time-out. Installation ignores pip configuration files and inherited `PIP_*` settings except the explicit network settings `PIP_PROXY`, `PIP_CERT`, `PIP_CLIENT_CERT`, `PIP_TIMEOUT`, `PIP_DEFAULT_TIMEOUT`, `PIP_RETRIES`, and `PIP_RESUME_RETRIES`. Standard proxy and certificate environment variables such as `HTTPS_PROXY` and `REQUESTS_CA_BUNDLE` remain available. If your proxy or certificate is configured only in `pip.ini` or `pip.conf`, set the corresponding environment variable before running the check. On a slow connection, set `PIP_TIMEOUT=120` first. This keeps dependency downloads on PyPI and installations inside the temporary environments.

These are smoke tests. To run the test suite against the published package, create an environment in an empty directory outside the checkout and use its interpreter. In Bash:

```bash
uv venv --python 3.12 --seed release-tests
release-tests/bin/python -I -m pip install --index-url https://pypi.org/simple/ "pymedphys[user,tests]==VERSION"
release-tests/bin/python -I -m pymedphys dev tests
```

In PowerShell:

```powershell
uv venv --python 3.12 --seed release-tests
release-tests\Scripts\python.exe -I -m pip install --index-url https://pypi.org/simple/ "pymedphys[user,tests]==VERSION"
release-tests\Scripts\python.exe -I -m pymedphys dev tests
```

The tests may download public datasets. They run without the repository's pytest settings in `pyproject.toml` (strict markers, strict xfail, and the 900-second time-out), which the wheel does not contain.

### Record the result

Comment on the pull request that set the version with:

```markdown
- Version and release commit:
- Release workflow run:
- Verify published jobs:
- Local published-file check (OS, Python, result), if run:
- Test suite against the published package (OS, Python, result), if run:
```

## Recover from failures

| Symptom | Action |
| --- | --- |
| The deployment is rejected by environment protection rules | Add or correct the `v*` tag rule on the `pypi` environment, then re-run the failed jobs. |
| PyPI reports `invalid-publisher` | Correct the owner, repository, workflow filename, or environment in that index's trusted publisher, then re-run the failed jobs. |
| The build job fails the tag check, or a test fails in the release run | This attempt did not publish. Check all earlier attempts, other runs for this version, and PyPI before deciding whether the version is unused. Re-run a download or network failure once. For a code or version change, preserve the tag and fix the cause on `main` through a pull request using a new version and tag. |
| The upload failed before any file reached PyPI | Fix the cause, then re-run the failed jobs. |
| Only one of the two files reached PyPI | Re-run the failed jobs. The publish step skips files already on the index, and the **Verify published** jobs then confirm that both files match the build. |
| PyPI and verification succeeded but `upload-release-assets` failed | Re-run only that job while the original `dist` artefact is available. It replaces existing assets with verified files and does not publish to PyPI. |
| A **Verify published** job failed | GitHub release assets are not uploaded by this attempt. Inspect the logs to distinguish index propagation, network or certificate errors, dependency or build-tool failures, and defects in the package. Retry transient failures. A SHA-256 mismatch means the built and published bytes differ; keep the original files and investigate before retrying or changing the release. |
| Locally, pip reports read time-outs and then `No matching distribution found` | This is a network failure, not a missing file. Check the proxy and certificate settings, and raise `PIP_TIMEOUT`. |

Re-run failed jobs using the original run's `dist` artefact, retained for 30 days. Do not re-run the whole release workflow to recover a published version: it rebuilds the files, and the build backend is not pinned. Even unchanged source can produce different archive hashes when the backend or build environment changes.

If the artefact is unavailable, recover the original archives from GitHub release assets or a retained copy and run the published-file check with `--compare-with`. For missing GitHub assets, original archives can also be downloaded from the URLs in pip's installation reports; verify them before attaching them with `gh release upload vVERSION release-assets/*`. If a PyPI upload is incomplete and the original workflow artefact cannot be recovered, publish a new version through the normal workflow. Keep the existing tag and release record; a fresh rebuild is not a replacement for the original files.

A published release cannot be replaced (see "Choose the version"). To fix one, publish a new version through the same preparation and review: the next `.devN` for a development release, or the next patch version for a stable release. [Yank](https://pypi.org/help/#yanked) a broken release on PyPI rather than deleting it, so that installs pinned to it still work.

## Prepare main for the next release

After publishing, open a pull request that sets `main` to the next unpublished development version, so that `main` never carries a published version: after `0.42.0.dev0`, `0.42.0.dev1`; after `0.42.0`, `0.43.0.dev0`. Run the commands in "Update the version" above. After a stable release, also add an empty `## Unreleased` heading above the new release's entries in `CHANGELOG.md`.
