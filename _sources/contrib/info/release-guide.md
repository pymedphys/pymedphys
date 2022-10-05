# pymedphys Release Procedure


> **NOTE:** Please ensure that you have followed the [setup guide](https://docs.pymedphys.com/en/latest/contrib/setups/index.html)
appropriate to you prior to commencing this release procedure.

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
[tool.poetry]
name = "pymedphys"
version = "VERSION"
readme = "README.rst"
...
```

Then run poetry update as well as propagate:

```bash
poetry update
poetry run pymedphys dev propagate
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

Commit all changes to your release branch and push to GitHub. Then create a Pull Request of this branch into main. This will run the CI tests. Before finalising the release, ensure all tests are passing.

### Troubleshooting issues

When preparing a release you will typically see certain steps of the CI failing. This is usually due to dependencies having been upgraded in the time since the last release and certain code within pymedphys is no longer compatible with the new versions.

To confirm this is indeed the problem, you can set an upper pin for these libraries (to constrain them to a previous version). By doing this you should hopefully see the CI pass.

In most instances, releasing pymedphys with an upper pin isn't appropriate, as this would be too restrictive for pymedphys users. Unfortunately there isn't a general solution to resolving these issues. You will need to remove the upper pins one-by-one and adjust the code in pymedphys to support the new version of the dependencies.

## Publish Release

Once the release pull request has been approved and merged, you're ready to release the new pymedphys version!

### PyPI Account & Token

Make sure you have an account at [PyPI](https://www.pypi.org) and your account has been added to the pymedphys project (contact the [pymedphys maintainers](https://github.com/pymedphys/pymedphys#maintainers) to be added).

Next, create a token on PyPI for the pymedphys project used by to authenticate and upload the release. Create the token under the [pymedphys settings page](https://pypi.org/manage/project/pymedphys/settings/). Then add the token to your poetry configuration:

```bash
poetry config pypi-token.pypi [your-pypi-token]
```

### Publish release to PyPI

```bash
poetry publish
```

### Publish release on GitHub

Create a new release on [GitHub](https://github.com/pymedphys/pymedphys/releases). Create a new tag in the format `vMAJOR.MINOR.PATCH` (e.g. `v0.39.0`). Enter the tag as the name for this release as well. Finally add in the change logs for this release (direct copy from CHANGELOG.md). Publish the release.

### Final sanity tests

Perform a final check to ensure the new version was released successfully. To do this, create a fresh Python virtual environment on your machine. Then install the new version of pymedphys and ensure all tests are passing as expected.

```python
pip install pymedphys[user,tests]
pymedphys dev tests
```
