# Contributing to PyMedPhys

Use a branch based on `main` and open a pull request for your changes.
The older `master` and release-maintenance branches are retained as read-only
history.

## Set up a development environment

Start with the [workstation setup guides](https://docs.pymedphys.com/en/latest/contrib/setups/index.html)
for Windows, Linux, or macOS. With Git and
[uv](https://docs.astral.sh/uv/getting-started/installation/) installed, run:

```bash
git clone https://github.com/pymedphys/pymedphys.git
cd pymedphys
uv python install 3.12
uv sync --python 3.12 --locked --extra all --group dev
uv run pre-commit install
```

If you do not have permission to push to this repository, fork it first and
clone your fork instead. Create a working branch before committing.

The development environment uses the dependencies recorded in `uv.lock`.
The current source supports Python 3.10–3.12; Python 3.12 matches the quick CI
run. See the [repository guide](https://docs.pymedphys.com/en/latest/contrib/info/file-structure.html)
for the source layout.

## Check your changes

From the repository root:

```bash
uv run pre-commit run --all-files
uv run pymedphys dev tests -m "not slow"
uv run pymedphys dev docs
```

The [documentation guide](https://docs.pymedphys.com/en/latest/contrib/info/docs-guide.html)
explains where to edit pages and how to inspect the built site.
The [workflow guide](https://docs.pymedphys.com/en/latest/contrib/info/workflows.html)
describes additional checks, conditional coverage, and troubleshooting.

## Open and review a pull request

Explain the problem, the change, and how you checked it. Ask a maintainer to add
the `full-test` label when broader OS/Python coverage and integration tests are
needed; the `database` label requests the database tests.

`CI Summary` and `Security Summary` are the required checks. The individual
jobs remain visible in the PR's checks list and **Checks** tab. A green summary
means the checks selected for that run passed, not that every possible test ran.

Contributors with Write access can merge once the branch is up to date, the
required checks pass, review conversations are resolved, and an eligible
reviewer has approved. Admins may explicitly bypass the review requirement;
review is encouraged for their PRs too. The CI requirements still apply.
Approvals are not automatically dismissed by later commits, so request another
review when making substantive changes after approval.

For help with Git and GitHub, see
[GitHub's pull request documentation](https://docs.github.com/en/pull-requests).
Use [Discussions](https://github.com/pymedphys/pymedphys/discussions) for questions
and [Issues](https://github.com/pymedphys/pymedphys/issues) for reproducible bugs.
Follow the [security policy](https://github.com/pymedphys/pymedphys/blob/main/SECURITY.md)
when reporting a suspected vulnerability.
