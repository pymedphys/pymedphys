# pymedphys Release Procedure

This guide covers stable and development releases. The [Release workflow](https://github.com/pymedphys/pymedphys/blob/main/.github/workflows/release.yml) builds, tests, publishes, and verifies every release; the [workflow guide](workflows.md) describes its jobs. One-time publishing setup and access requirements are in the appendix at the end.

```{note}
Please ensure that you have followed the [setup guide](../setups/index.rst) appropriate to you prior to commencing this release procedure.
```

## Checklist

`VERSION` is the version to release and `NEXT` is the development version `main` carries afterwards (see "Choose the versions").

```text
branch from main -> [Release VERSION] -> Start NEXT -> PR, merge commit
  -> tag the commit before "Start NEXT" -> GitHub release -> approve pypi
  -> Release Summary green -> paste its record on the PR
```

1. Branch from `origin/main`.
2. Stable release only: commit **Release VERSION**, which sets `VERSION` and completes the changelog. A development release skips this, because `main` already carries `VERSION`.
3. Record the release commit: `git rev-parse HEAD`.
4. Commit **Start NEXT**, which sets `NEXT` and, after a stable release, adds an empty `## Unreleased` heading.
5. Open the pull request; add the `full-test` label for a stable release. Once approved and green, merge it with **Create a merge commit**.
6. Tag the release commit `vVERSION` and push the tag.
7. Optional: rehearse on TestPyPI from the tag.
8. Publish a GitHub release from the tag; for a development release, select **Set as a pre-release**.
9. Approve the `pypi` deployment when the run requests it.
10. Wait for the **Release Summary** job to pass.
11. Paste the record from the Release Summary into a comment on the pull request.

## Choose the versions

Write versions without a leading `v`; the release tag is `vVERSION`. `NEXT` must be greater than `VERSION`, and neither may already be on PyPI, which never accepts a filename again, even after its file is deleted.

| Release | `main` before | `VERSION` | `NEXT` |
| --- | --- | --- | --- |
| Development | `0.42.0.dev1` | `0.42.0.dev1` | `0.42.0.dev2` |
| Stable (minor) | `0.42.0.dev2` | `0.42.0` | `0.43.0.dev0` |
| Stable (patch) | `0.43.0.dev0` | `0.42.1` | `0.43.0.dev0` |

pymedphys uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Increment `MINOR` and reset `PATCH` to zero for a release with new features or API changes; while the project is pre-1.0, minor releases may contain breaking changes. Increment only `PATCH` when the changes since the last release are bug fixes that leave the API unchanged.

A development release lets testers install unreleased changes from PyPI. Its version is the upcoming release with a [PEP 440](https://packaging.python.org/en/latest/specifications/version-specifiers/) `.devN` suffix, which sorts before that release. Testers request it explicitly with `pymedphys==0.42.0.dev1`, or with `--pre` and a constraint that admits it: `pymedphys>=0.42.0.dev1` does, `pymedphys>=0.42` does not.

Write versions in canonical form: `0.42.0.dev1`, not `0.42.0-dev1`. The build copies `pyproject.toml`'s string into the package metadata unchanged but names the files with the canonical form, so the build job fails on any other spelling before anything is published.

## Prepare the release pull request

The release commit, whose `pyproject.toml` holds `VERSION`, is followed by a **Start NEXT** commit, so that `main` never carries a published version. A stable release pull request adds both commits. For a development release, the release commit is the `main` commit you branch from, and the pull request adds only **Start NEXT**.

### Create the branch

From an up-to-date clone in which `origin` is `pymedphys/pymedphys`:

```bash
git fetch origin main
git switch -c VERSION-release origin/main
```

### Commit the release version (stable releases)

Set `version = "VERSION"` near the top of `pyproject.toml`, then refresh the lockfile's project metadata and regenerate the version and dependency files. Keep dependency upgrades in a separately reviewed change unless they are deliberately part of this release.

```bash
uv lock
uv sync --python 3.12 --locked --extra all --group dev
uv run -- pymedphys dev propagate
```

In `CHANGELOG.md`, rename `## Unreleased` to `## [VERSION]`, complete its entries, and remove unused sections. The [merged pull requests](https://github.com/pymedphys/pymedphys/pulls?q=is%3Apr+is%3Amerged) since the last release show what has changed. Then commit:

```bash
git commit --all --message "Release VERSION"
```

A development release leaves `CHANGELOG.md` unchanged: its entries stay under `## Unreleased` until the stable release.

### Record the release commit

```bash
git rev-parse HEAD
```

The output is `RELEASE_COMMIT`, used to tag the release. Keep it: bring the branch up to date by merging `main` into it (GitHub's **Update branch** button does this), not by rebasing, which gives the release commit a new SHA.

### Commit the next development version

Set `version = "NEXT"` in `pyproject.toml` and run the same three commands. After a stable release, also add an empty `## Unreleased` heading above `## [VERSION]` in `CHANGELOG.md`. Then commit and push:

```bash
git commit --all --message "Start NEXT"
git push --set-upstream origin VERSION-release
```

### Open and merge the pull request

Open a pull request into `main`. The CI and security summaries must pass; inspect their constituent checks as described in the [workflow guide](workflows.md).

For a stable release, add the `full-test` label so the full unit-test matrix, integration checks, and Mosaiq database tests run before merging. A development release does not need it: the Release workflow runs the full unit-test matrix and integration tests before publishing, and a failure there only delays a pre-release.

Merge with **Create a merge commit**. Squash and rebase merges replace the release commit, and the tagging commands below then fail.

### If checks fail

The `full-test` label runs checks that ordinary pull requests skip. A release pull request changes little besides the version, so a failure usually already exists on `main` or comes from outside the repository.

- Read the failing job's log. Download errors (for example from Zenodo) and network time-outs are not code failures: re-run the job once, and investigate if it fails again.
- Most jobs install the locked dependencies from `uv.lock`, so a new dependency release cannot break them. The distribution checks are the exception: they install the built wheel with pip, which resolves the newest compatible dependencies from PyPI.

Fix a genuine failure on `main` in its own pull request, including any dependency constraint, `uv lock`, and `pymedphys dev propagate`, then merge `main` into the release branch.

## Publish the release

### Tag the release commit

After the pull request has merged, in Bash or PowerShell:

```bash
git fetch origin main
git branch --remotes --contains RELEASE_COMMIT
git show RELEASE_COMMIT:pyproject.toml
git tag -a vVERSION RELEASE_COMMIT -m "PyMedPhys VERSION"
git push origin refs/tags/vVERSION
```

The second command must list `origin/main`, and the `version` near the top of the third command's output must be `VERSION`. If `vVERSION` already exists, stop and investigate; never move or force-push a release tag. Pushing the tag does not start the workflow.

### Rehearse on TestPyPI (optional)

A rehearsal runs the whole workflow against TestPyPI before anything reaches PyPI. It is worthwhile after changing `release.yml`, `.github/scripts/check_distributions.py`, or the publishing settings; otherwise the checks before publishing already protect PyPI. It needs the TestPyPI trusted publisher described in the appendix.

Start a manual run from the tag with **dry_run** ticked, as described in "Manual runs and dry_run", and wait for its **Release Summary** to pass. TestPyPI, like PyPI, never accepts a file again, so rehearse each version once.

### Publish the GitHub release

1. In GitHub **Releases**, draft a release from the existing tag, titled `VERSION`.
   - For a stable release, use the version's changelog entries as the notes, and leave **Set as the latest release** selected.
   - For a development release, summarise the `Unreleased` changelog entries and select **Set as a pre-release**.

   The checkbox affects only GitHub; pip decides from the version string alone. A stable version marked as a pre-release still installs by default, and an unmarked development release becomes the repository's latest release.
2. Select **Publish release**. Publishing a release or a pre-release starts the workflow; saving a draft does not. The build job fails, and nothing is published, unless the tag is `v` followed by the package version.
3. When the tests have passed, the run requests approval for the `pypi` environment. Select **Review deployments** on the run's page and approve it.

### Confirm the result

The run is complete when its **Release Summary** job passes. That job fails unless every job on the run's route succeeded:

- before publishing: lint, type checks, the full unit-test matrix, integration tests, and the build and distribution checks;
- `publish-pypi`;
- **Verify published** on Linux, Windows, and macOS, which installs the wheel and the sdist from PyPI separately and requires both to match the files built and tested earlier in the run;
- **Test published** on Linux, Windows, and macOS, which runs the test suite against the published wheel with its dependencies resolved afresh from PyPI, as a user's installation is, rather than from `uv.lock`;
- `upload-release-assets`, which attaches the verified files to the GitHub release and reads them back.

A published GitHub release does not by itself mean that PyPI publishing succeeded. If the summary fails, see "Recover from failures".

### Record the result

The Release Summary job's summary, on the run's **Summary** page, ends with a **Record for the release pull request** block. Paste it into a comment on the release pull request, followed by any reports from "Check the published files yourself".

## Manual runs and dry_run

The workflow can also be started by hand: open **Actions**, select **Release** in the list of workflows, and select **Run workflow** above its runs. Under **Use workflow from**, choose the ref to build, normally the release tag on the **Tags** tab. The **dry_run** checkbox is ticked by default. Select **Run workflow** to start.

| dry_run | Publishes to | Use it |
| --- | --- | --- |
| Ticked (`true`) | TestPyPI only | To rehearse a release from its tag. |
| Unticked (`false`) | PyPI only | Only to recover a release whose release-triggered run never started or can no longer be re-run, and when no file of that version is on PyPI. |

A manual run builds whatever version `pyproject.toml` holds on the selected ref, skips the tag check, and attaches no GitHub release assets. Despite its name, a dry run uploads to TestPyPI permanently. With **dry_run** unticked, the run still waits for approval of the `pypi` deployment; select the release tag, never `main`, and never start it alongside a release-triggered run of the same version. GitHub allows a run to be re-run for 30 days, so a failed release-triggered run is normally recovered by re-running it instead.

## Check the published files yourself

The workflow checks the published files with Python 3.12 on GitHub-hosted runners. To check them on another platform, Python version, or network, such as behind an institutional proxy, run from the root of a checkout, in Bash or PowerShell:

```bash
uv run --no-project --python 3.12 python .github/scripts/check_distributions.py --published VERSION --tests --summary release-check.md
```

This installs the wheel and the sdist from PyPI into separate fresh environments outside the checkout, as the **Verify published** jobs do, then adds the `user` and `tests` extras to the wheel's environment and runs the test suite there. The tests download public datasets and can take tens of minutes; omit `--tests` for a check of a few minutes. Neither the checkout nor `PYTHONPATH` can affect the environments.

It prints `The distributions passed every check.` on success, and otherwise lists each failure and exits non-zero. It appends a Markdown report of the platform, each file's SHA-256, and each result to `release-check.md`, ready to paste into the release pull request. Installation reports, pip logs, and the test log are kept in the directory it prints, or in `--report-dir`. Use `--index testpypi` to check a rehearsal. The test suite runs without the repository's pytest settings in `pyproject.toml` (strict markers, strict xfail, and the 900-second time-out), which the wheel does not contain.

Installation ignores pip configuration files and inherited `PIP_*` settings except the network settings `PIP_PROXY`, `PIP_CERT`, `PIP_CLIENT_CERT`, `PIP_TIMEOUT`, `PIP_DEFAULT_TIMEOUT`, `PIP_RETRIES`, and `PIP_RESUME_RETRIES`, so dependencies always come from PyPI. Standard variables such as `HTTPS_PROXY`, `SSL_CERT_FILE`, and `REQUESTS_CA_BUNDLE` remain available. If your proxy or certificate is configured only in `pip.ini` or `pip.conf`, set the corresponding environment variable first. If pip reports read time-outs and then `No matching distribution found`, the network failed, not the release: check the proxy and certificate settings and set `PIP_TIMEOUT=120`.

## Recover from failures

| Symptom | Action |
| --- | --- |
| The deployment is rejected by environment protection rules | Add or correct the `v*` tag rule on the `pypi` environment, then re-run the failed jobs. |
| PyPI reports `invalid-publisher` | Correct the owner, repository, workflow filename, or environment in that index's trusted publisher, then re-run the failed jobs. |
| The build job fails the tag check, or a test fails before publishing | This attempt did not publish. Re-run a download or network failure once. Otherwise check all earlier attempts, other runs for this version, and PyPI before deciding whether the version is unused. For a code or version change, keep the tag, fix the cause on `main`, and release a new version through a new release pull request. Because `main` already carries `NEXT`, its release commit sets the new version and moves the unpublished changelog entries under it, and its **Start NEXT** commit restores `NEXT`. |
| The upload failed before any file reached PyPI | Fix the cause, then re-run the failed jobs. |
| Only one of the two files reached PyPI | Re-run the failed jobs. The publish step skips files already on the index, and the **Verify published** jobs then confirm that both files match the build. |
| A **Verify published** job failed | The release assets are not uploaded. Inspect the job's log and its `install-reports` artefact to distinguish index propagation, network or certificate errors, dependency or build-tool failures, and defects in the package. Re-run transient failures. A SHA-256 mismatch means the built and published bytes differ; keep the original files and investigate before retrying or changing the release. |
| A **Test published** job failed | The release is on PyPI. Inspect the job's log and its `test-reports` artefact. Re-run a data download or network failure once. A genuine failure with freshly resolved dependencies that passed with `uv.lock` usually comes from a new dependency release: constrain it on `main` and publish a new version. Yank the release if it is unusable. |
| `upload-release-assets` failed, including its read-back check | Re-run only that job while the original `dist` artefact is available. It replaces the assets with the verified files and does not publish to PyPI. |

Re-run failed jobs, not the whole workflow: re-running failed jobs reuses the original run's `dist` artefact, retained for 30 days. A whole-workflow re-run rebuilds the files, and even unchanged source can produce different archive hashes when the build backend or environment changes.

If the artefact is unavailable, recover the original archives from the GitHub release assets or a retained copy, and require the files on PyPI to match them. GitHub's automatic **Source code** archives are repository snapshots, not the sdist.

```bash
gh release download vVERSION --pattern "pymedphys-*" --dir release-assets
uv run --no-project --python 3.12 python .github/scripts/check_distributions.py --published VERSION --compare-with release-assets
```

For missing GitHub assets, the original archives can also be downloaded from the URLs in pip's installation reports; verify them this way before attaching them with `gh release upload vVERSION release-assets/*`. If a PyPI upload is incomplete and the original files cannot be recovered, publish a new version. Keep the existing tag and release record; a fresh rebuild is not a replacement for the original files.

A published release cannot be replaced. To fix one, publish a new version through the same procedure: the next `.devN` for a development release, or the next patch version for a stable release. [Yank](https://pypi.org/help/#yanked) a broken release on PyPI rather than deleting it, so that installs pinned to it still work.

## Appendix: publishing setup and access

### Who can release

Publishing uses PyPI trusted publishing. PyPI trusts the `release.yml` workflow of this repository running in its `pypi` environment, whoever starts the run, so once the settings below are in place any maintainer can release without a PyPI account or API token.

| Task | Needs |
| --- | --- |
| Push a release tag and publish a GitHub release | Write role or higher on the GitHub repository |
| Approve the `pypi` deployment | Being a required reviewer of the `pypi` environment |
| Add or change a trusted publisher, or yank a release | Owner role on the index's `pymedphys` project; the Maintainer role can only upload |
| Change environments and their protection rules | Admin role on the GitHub repository |

### Check the publishing settings

Environment protection and trusted publishers are configured separately in GitHub and on each package index. A workflow that references a missing GitHub environment creates it without protection rules; it does not create a trusted publisher. Check these settings before the first release from a new setup, and after any change.

1. In the repository's **Settings > Environments**, the environment `pypi` exists, and `testpypi` too if you rehearse. Under **Deployment branches and tags**, each allows **Selected branches and tags**: a branch rule for `main` and a tag rule for `v*`. `pypi` has required reviewers; approving a deployment is separate from reviewing a pull request. If **Prevent self-review** is enabled, someone other than the person who started the run must approve.
2. On PyPI, the `pymedphys` project's **Publishing** page lists a GitHub trusted publisher with owner `pymedphys`, repository `pymedphys`, workflow `release.yml` (the filename only), and environment `pypi`. See the [PyPI trusted-publisher guide](https://docs.pypi.org/trusted-publishers/adding-a-publisher/).
3. For rehearsals only, TestPyPI's `pymedphys` project lists the same publisher with environment `testpypi`. TestPyPI (`test.pypi.org`) is a separate service with its own accounts, project roles, and trusted publishers; the PyPI publisher does not cover it, and adding one needs the Owner role on the TestPyPI project.
