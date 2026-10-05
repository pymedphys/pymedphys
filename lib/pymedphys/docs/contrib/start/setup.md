# Set up a development environment

This procedure is for contributors working on the current `main` branch.
It creates an editable PyMedPhys installation and the locked development tools.
Use the [installation guide](../../users/get-started/quick-start.rst) to install
PyMedPhys solely for use.

You need Git, uv, internet access for the initial dependencies, and a writable
directory for your checkout. Follow your organisation's software installation
policy. Read the platform prerequisites first:
[Windows](../setups/setup-win.rst), [Linux](../setups/setup-linux.rst), or
[macOS](../setups/setup-mac.rst).

## Setup checklist

1. Verify Git and uv are available.
2. Clone your fork, add the upstream repository, and enter the checkout.
3. Install Python and synchronise the locked environment.
4. Install pre-commit hooks and confirm the checkout is imported.
5. Create a working branch using the [first-contribution tutorial](first-contribution.md).

## 1. Check the prerequisites

Run these commands in PowerShell on Windows, or a POSIX shell on Linux/macOS:

```shell
git --version
uv --version
```

Both commands should print a version. Open a new terminal after installation
if either command is unavailable. uv can install Python for you; you do not
need a separate Python or pipx installation.

## 2. Create a checkout

If you cannot push to `pymedphys/pymedphys`, use GitHub's **Fork** button first.
Replace `YOUR-USERNAME` below with your GitHub username. The commands work in
PowerShell and POSIX shells:

```shell
git clone https://github.com/YOUR-USERNAME/pymedphys.git
cd pymedphys
git remote add upstream https://github.com/pymedphys/pymedphys.git
git fetch upstream
git remote -v
```

`origin` should point to your fork, and `upstream` to `pymedphys/pymedphys`.
This distinction lets you pull the project's updates while pushing your work
to a repository you control. HTTPS authentication can use Git Credential
Manager or GitHub CLI. [SSH on Windows](../tips/win-open-ssh.rst) is optional.

Contributors with repository push access can instead clone
`https://github.com/pymedphys/pymedphys.git` directly. In that checkout `origin`
is the project repository; use `origin/main` wherever the tutorial uses
`upstream/main`.

## 3. Install the locked environment

Run from the repository root:

```shell
uv python install 3.14
uv sync --python 3.14 --locked
uv run pre-commit install
```

The current source supports Python 3.11.4 or later in the 3.11 series, and
Python 3.12, 3.13, and 3.14. Python 3.14 matches the quick CI environment.
`uv sync` creates `.venv`, installs the checkout in editable mode, and installs
the default `dev` dependency group. That group includes every PyMedPhys extra
and the documentation, lint, and pre-commit tools. The resolved versions come
from `uv.lock`; do not change them merely to set up the project.

Use `uv run` from this directory for project commands. You do not need to
activate `.venv`. Re-run the locked sync after pulling dependency changes.
The distinction between published extras and checkout dependency groups is
explained in [the architecture guide](../architecture/index.md#dependencies-and-environments).

## 4. Confirm the installation

```shell
uv run python -c "import pathlib, pymedphys; print(pathlib.Path(pymedphys.__file__).resolve())"
uv run pymedphys --version
git status --short
```

The import path should end in this checkout's `lib/pymedphys/__init__.py`, and
the command should print the checkout's version. Setup should not leave changes
to tracked dependency files. If a sync reports that the lockfile is out of date,
check you are on the intended branch and report the inconsistency; do not
silently regenerate it as part of setup.

Set the author identity for commits in this checkout if needed. Use the name
and email you want attached to your contributions; GitHub offers a private
`noreply` address in its email settings:

```shell
git config user.name "Your Name"
git config user.email "YOUR-COMMIT-EMAIL"
```

You are ready to follow [Make your first contribution](first-contribution.md).
For notebooks, [register the checkout's Jupyter kernel](../tips/add-jupyter-kernel.rst).

## Resolve a setup failure

| Symptom | Next check |
| --- | --- |
| `git` or `uv` is not found | Reopen the terminal and check the relevant platform prerequisites. |
| A dependency attempts a source build | Read the package's error and platform instructions; the macOS guide links the Python 3.14 prerequisites. |
| A download fails behind a proxy | Use your organisation's approved proxy/certificate configuration and uv's installation guidance. Include the failing package and error when requesting help. |
| Python imports another PyMedPhys installation | Run from the repository root with `uv run`, confirm the printed path, and check whether the terminal/editor is using another environment. |
| A notebook cannot import project dependencies | Select the registered development kernel; re-register it after moving the checkout. |

Include the OS, Python version, command, and a redacted error in a help request.
Keep credentials, identifying paths, and patient data out of public posts.
