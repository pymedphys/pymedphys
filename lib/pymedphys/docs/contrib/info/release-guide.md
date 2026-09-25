# pymedphys Release Procedure

This guide covers stable releases, development releases, and optional TestPyPI rehearsals. The [Release workflow](https://github.com/pymedphys/pymedphys/blob/main/.github/workflows/release.yml) builds, tests, and publishes every release; the [workflow guide](workflows.md) describes its jobs.

```{note}
Please ensure that you have followed the [setup guide](../setups/index.rst) appropriate to you prior to commencing this release procedure.
```

## Choose the version

In this guide, `VERSION` is the package version without a leading `v`, for example `0.42.0`, and the release tag is `vVERSION`.

pymedphys uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html) in the format `MAJOR.MINOR.PATCH`. For a minor release, increment `MINOR` and reset `PATCH` to zero; for example, `0.41.2` becomes `0.42.0`. While the project is pre-1.0, minor releases may contain breaking changes.

In instances where the only changes since the last release are bug fixes and none of the pymedphys API has changed, you should increment the `PATCH` value: `MAJOR.MINOR.PATCH+1`

A development release lets testers install unreleased changes from PyPI. Its version is the upcoming release with a [PEP 440](https://packaging.python.org/en/latest/specifications/version-specifiers/) `.devN` suffix: `0.42.0.dev1` is a development release of `0.42.0` and sorts before it. pip installs a development release only when it is requested explicitly (`pymedphys==0.42.0.dev1`, or `--pre`), or when no stable release satisfies the requirement (for example `pymedphys>=0.42` before `0.42.0` exists).

Write the version in canonical form: `0.42.0.dev1`, not `0.42.0-dev1`. The build copies the string in `pyproject.toml` into the package metadata unchanged, the release tag must equal `v` followed by that string, and the distribution filenames always use the canonical form, so any other spelling leaves them disagreeing.

`main` carries the next unpublished development version between releases (see "Prepare main for the next release" below). Before choosing a version, check that it is not already on PyPI: PyPI never accepts the same filename twice, even after the file is deleted.

## Prepare the release pull request

A stable release and a development release both need a reviewed pull request that sets the version on `main`, because the release tag must match `pyproject.toml` at the tagged commit.

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

For a stable release, add the `full-test` label so the full unit-test matrix and integration checks run before merging. For a development release the label is optional: the Release workflow runs the same checks before publishing, and a failure there only delays a pre-release.

### If checks fail

The `full-test` label runs checks that ordinary pull requests skip: the full OS and Python matrix, slow tests, and integration tests. A release pull request changes little besides the version, so a failure usually already exists on `main` or comes from outside the repository.

- Read the failing job's log. Download errors (for example from Zenodo) and network time-outs are not code failures: re-run the job once, and investigate if it fails again.
- Most jobs install the locked dependencies from `uv.lock`, so a new dependency release cannot break them. The distribution checks are the exception: they install the built wheel with pip, which resolves the newest compatible dependencies from PyPI.

Fix a genuine failure on `main` in its own pull request, including any dependency constraint, `uv lock`, and `pymedphys dev propagate`, then merge `main` into the release branch.

## Publish the release

Once the release pull request has been approved and merged, you're ready to release the new pymedphys version!

### Check the publishing settings

Publishing uses PyPI trusted publishing, with no stored API token. It depends on settings in GitHub and on each package index, not in `release.yml`; naming an environment or publisher in the workflow does not create it. Check them before the first release from a new setup, and after any change:

1. The GitHub environment `pypi` exists, and `testpypi` too if you rehearse. Under **Deployment branches and tags**, choose **Selected branches and tags**, then add a branch rule for `main` (manual runs) and a tag rule for `v*` (releases). `pypi` has required reviewers; approving a deployment is separate from reviewing a pull request. If **Prevent self-review** is enabled, someone other than the releaser must approve.
2. PyPI, and TestPyPI if you rehearse, each have a trusted publisher with owner `pymedphys`, repository `pymedphys`, workflow `release.yml` (the filename only), and environment `pypi` or `testpypi` respectively. See the [PyPI trusted-publisher guide](https://docs.pypi.org/trusted-publishers/adding-a-publisher/).

### Choose the route

| Trigger | Package index | Tag check | GitHub release assets |
| --- | --- | --- | --- |
| Publish a GitHub release or pre-release | PyPI | Yes | Attached after PyPI succeeds |
| Run the workflow manually with `dry_run=true` | TestPyPI only | No | None |
| Run the workflow manually with `dry_run=false` | PyPI only | No | None |

Publish every release through a GitHub release. A manual run with `dry_run=false` publishes whatever version `pyproject.toml` holds on the selected ref; keep it for recovery, run it from the release tag rather than `main`, and never alongside a release-triggered run of the same version.

### Rehearse on TestPyPI (optional)

1. Open **Actions > Release > Run workflow**, select `main`, and leave **dry_run** set to **true**. The run uses the tip of `main` when it is dispatched; check that its commit SHA is the reviewed release commit.
2. Check that the quality, build, and `publish-testpypi` jobs succeed.
3. Check what TestPyPI now serves, as in "Check the published files" below, adding `--index testpypi`.

Despite its name, `dry_run=true` uploads to TestPyPI, which also never reuses a filename, so each version can be rehearsed once. TestPyPI does not host the dependencies, so the check also searches PyPI. Anyone can upload to TestPyPI, and pip takes the highest version it finds on either index, so a dependency or build tool from TestPyPI can replace the PyPI one: run the TestPyPI check only where you would run untrusted code, such as a disposable container.

### Publish to PyPI

1. Confirm that the release pull request has merged, and find the full SHA of the merged commit on `main` (`RELEASE_COMMIT`).
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
4. Select **Publish release**. Publishing a release or a pre-release starts the workflow; saving a draft does not. The workflow runs lint, type checks, the full unit-test matrix, integration tests, and the distribution checks. The build job fails, and nothing is published, unless the tag is exactly `v` followed by the package version.
5. Approve the `pypi` deployment when it is requested, after the tests finish.
6. Check that `publish-pypi`, `upload-release-assets`, and the three **Verify PyPI** jobs succeeded. The **Release Summary** job only reports these results and passes regardless, and a published GitHub release does not mean that PyPI publishing succeeded.

### Check the published files

After PyPI publishing, the **Verify PyPI** jobs install the wheel and the sdist from PyPI separately on Linux, Windows, and macOS, and require both files to match those built and tested earlier in the run. Each job uploads its pip installation reports and logs as an artefact.

Run the same check yourself where the workflow cannot, for example on another platform or behind an institutional proxy. From the root of a checkout, in Bash or PowerShell:

```bash
uv run --no-project --python 3.12 python .github/scripts/check_distributions.py --published VERSION
```

For each format, the check:

- installs `pymedphys==VERSION` into a new environment with pip's cache disabled, forcing the sdist to be built (`--no-binary=pymedphys`); dependencies may still come as wheels;
- requires pip's installation report to name the expected file, served from `files.pythonhosted.org`, so an extra index in your pip configuration cannot substitute another file;
- checks the installed version, that `pymedphys`, `pymedphys.dicom`, and `pymedphys.cli` import from inside the environment, the `pymedphys --version` output, and `pip check`.

It prints `The distributions passed every check.` on success, and otherwise lists each failure and exits non-zero. The environments are created in temporary directories and run with `python -I`, so neither the checkout nor `PYTHONPATH` can affect them. The installation reports and pip logs, including the sdist build, are kept in the directory it prints, or in `--report-dir`.

To also require the files on PyPI to match the GitHub release assets, download the assets and pass their directory. GitHub's automatic **Source code** archives are repository snapshots, not the sdist.

```bash
gh release download vVERSION --pattern "pymedphys-*" --dir release-assets
uv run --no-project --python 3.12 python .github/scripts/check_distributions.py --published VERSION --compare-with release-assets
```

Your pip configuration still applies, apart from the index URL, so proxy and certificate settings keep working. On a slow connection, raise pip's 15-second network time-out by setting `PIP_TIMEOUT=120` in the environment first.

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

Comment on the release pull request with:

```markdown
- Version and release commit:
- Release workflow run:
- Verify PyPI jobs:
- Local published-file check (OS, Python, result), if run:
- Test suite against the published package (OS, Python, result), if run:
```

## Recover from failures

| Symptom | Action |
| --- | --- |
| The deployment is rejected by environment protection rules | Add or correct the `v*` tag rule on the `pypi` environment, then re-run the failed jobs. |
| PyPI reports `invalid-publisher` | Correct the owner, repository, workflow filename, or environment in that index's trusted publisher, then re-run the failed jobs. |
| The build job fails the tag check, or a test fails in the release run | Nothing was published. Re-run a download or network failure once. Otherwise delete the GitHub release and the tag (`git push origin --delete refs/tags/vVERSION` and `git tag -d vVERSION`), fix the cause on `main` through a pull request, and tag again. |
| The upload failed before any file reached PyPI | Fix the cause, then re-run the failed jobs. |
| Only one of the two files reached PyPI | Do not rebuild. Re-run the failed jobs, which reuse the built files. If PyPI refuses the file that is already there, publishing the other needs a one-off change setting `skip-existing: true` on the publish step; the **Verify PyPI** jobs then confirm that both files match the build. |
| PyPI succeeded but `upload-release-assets` failed | Re-run only that job. It replaces existing assets and does not publish to PyPI. |
| A **Verify PyPI** job failed | Read which check failed. If the version was not yet available, check the PyPI project page and re-run the job. Any other failure is a defect in the published files. |
| Locally, pip reports read time-outs and then `No matching distribution found` | This is a network failure, not a missing file. Check the proxy and certificate settings, and raise `PIP_TIMEOUT`. |

Re-running failed jobs reuses the built files only while the run's `dist` artefact exists, which is 7 days. After that, re-run the whole workflow from the release so that it builds again from the tag.

PyPI never accepts a filename twice, so a published release cannot be replaced. To fix one, publish a new version through the same preparation and review: the next `.devN` for a development release, or the next patch version for a stable release. [Yank](https://pypi.org/help/#yanked) a broken release on PyPI rather than deleting it, so that installs pinned to it still work.

## Prepare main for the next release

After publishing, open a pull request that sets `main` to the next unpublished development version, so that `main` never carries a published version: after `0.42.0.dev0`, `0.42.0.dev1`; after `0.42.0`, `0.43.0.dev0`. Run the commands in "Update the version" above. After a stable release, also add an empty `## Unreleased` heading above the new release's entries in `CHANGELOG.md`.
