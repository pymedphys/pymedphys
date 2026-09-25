# pymedphys Release Procedure

```{note}
Please ensure that you have followed the [setup guide](https://docs.pymedphys.com/en/latest/contrib/setups/index.html)
appropriate to you prior to commencing this release procedure.
```

## Determine next release version

pymedphys uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html) in the format `MAJOR.MINOR.PATCH`, the next release number should typically be `MAJOR.MINOR+1.PATCH`. For example, if the previous release was `0.38.0`, the upcoming release will be `0.39.0`.

In instances where the only changes since the last release are bug fixes and none of the pymedphys API has changed, you should increment the `PATCH` value: `MAJOR.MINOR.PATCH+1`

In the remainder of this guide this version code will be referred to as `VERSION`.

## Create a branch to prepare the release

Create a branch named `VERSION-release-prep`:

```bash
git checkout -b VERSION-release-prep
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

Then run uv lock --upgrade as well as propagate:

```bash
uv lock --upgrade
uv sync --extra all --group dev
uv run -- pymedphys dev propagate
```

## Update CHANGELOG

Amend the `CHANGELOG.md` file to describe the changes since the last release. Insert information for this release near the top of the file and populate the sections as appropriate (remove unused sections):

```markdown
<!-- markdownlint-disable MD024 MD039 -->

# Release Notes

All notable changes to are documented here.

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

When preparing a release you will typically see certain steps of the CI failing. This is usually due to dependencies having been upgraded in the time since the last release and certain code within pymedphys is no longer compatible with the new versions.

To confirm this is indeed the problem, you can set an upper pin for these libraries (to constrain them to a previous version). By doing this you should hopefully see the CI pass.

In most instances, releasing pymedphys with an upper pin isn't appropriate, as this would be too restrictive for pymedphys users. Unfortunately there isn't a general solution to resolving these issues. You will need to remove the upper pins one-by-one and adjust the code in pymedphys to support the new version of the dependencies.

## Publish Release

Once the release pull request has been approved and merged, you're ready to release the new pymedphys version!

### Verify trusted publishing and deployment protection

The release workflow builds with `uv` and publishes through PyPI trusted
publishing. It does not use a PyPI API token or `poetry publish`.

Before the first release with this workflow, a repository admin and a PyPI
project owner must verify:

1. The GitHub environments `testpypi` and `pypi` exist and have the intended
   deployment branch/tag restrictions. Permit the `main` branch for manual
   runs and release tags matching `v*`. Configure production release approvers
   in `pypi`; these environment approvals are separate from PR reviews.
2. Each package index has the matching trusted publisher for owner `pymedphys`,
   repository `pymedphys`, workflow `release.yml`, and environment `testpypi` or
   `pypi`, respectively. A matching GitHub environment alone does not configure
   the package index.
3. The release commit has passed the required checks and is on `main`. A tag
   name matching `v*` does not itself prove that its commit came from `main`.

These are external settings, not protections created by the YAML file.
Do not assume that an environment or a trusted publisher already exists simply
because the workflow references its name.

### Rehearse with TestPyPI

1. Open **Actions > Release > Run workflow** in GitHub.
2. Select `main`, using the reviewed release-preparation commit.
3. Leave **dry_run** set to **true** and run the workflow.
4. Check the quality jobs, build/install checks, and TestPyPI publish job.
   Inspect the uploaded distribution and install the intended version from
   TestPyPI in a fresh environment before proceeding.

The TestPyPI run still performs publishing to TestPyPI; it is not a local-only
simulation. It does not publish to production PyPI.

### Publish the production release

1. Confirm the version in `pyproject.toml` and the generated files match the
   intended release, and that its preparation PR has merged into `main`.
2. In GitHub **Releases**, draft a release with a new `vMAJOR.MINOR.PATCH` tag
   pointing to that reviewed commit on `main`. Use that version as the title
   and the corresponding changelog entries as the release notes.
3. Publish the GitHub release. The `release: published` event starts the Release
   workflow, which runs lint, type checks, the full unit-test matrix, integration
   tests, and distribution build/install checks before publishing.
4. Approve the production deployment when the `pypi` environment requests it.
5. Verify the `publish-pypi` and `upload-release-assets` jobs succeeded, and
   inspect the resulting package-index release and GitHub assets.

The **Release Summary** job is a report, not a pass/fail gate. Inspect the
workflow result and its publishing jobs; a successful report alone does not
mean publishing succeeded. GitHub release publication precedes the workflow,
so a published GitHub release alone also does not confirm PyPI publication.

The workflow additionally supports a manual run with **dry_run=false**. This
publishes to production PyPI and should be reserved for a deliberate release
or recovery operation after checking the target commit and existing version.
It does not create a GitHub release or upload its assets. Do not run it in
parallel with a release-triggered publish of the same version.

### Final sanity tests

Perform a final check to ensure the new version was released successfully. To do this, create a fresh Python virtual environment on your machine. Then install the new version of pymedphys and ensure all tests are passing as expected.

```python
pip install pymedphys[user,tests]
pymedphys dev tests
```
