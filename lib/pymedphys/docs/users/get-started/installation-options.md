# Installation options

PyMedPhys uses optional dependency groups so you can install either a broad
end-user stack or a narrower task-specific stack.

PyMedPhys currently supports Python 3.11, 3.12, 3.13, and 3.14.

## Recommended approach

For most users, we recommend using `uv` to manage Python and the virtual
environment, then installing PyMedPhys into that environment.

A minimal recommended flow is:

```bash
uv python install 3.12
uv venv --python 3.12
uv pip install "pymedphys[user]"
```

If you cannot install `uv` on your workstation, use the fallback path in the
[Quick Start Guide](quick-start.rst).

## macOS with Python 3.14

The `user` and `all` extras include watchdog. Watchdog 6.0.0 has no macOS wheel
for Python 3.14, so building its FSEvents extension needs a C compiler and the
macOS SDK. Before installing either extra with Python 3.14, install
[Apple's Command Line Tools](https://developer.apple.com/documentation/xcode/installing-the-command-line-tools):

```bash
xcode-select --install
```

Complete the installer, then check that both the compiler and SDK are available:

```bash
xcrun --find clang
xcrun --show-sdk-path
```

Both commands should print a path. If Xcode or its Command Line Tools are
already installed, run these checks before installing PyMedPhys.

## Why there is more than one install

A plain `pymedphys` install keeps the core package small.
Many user-facing features need optional dependencies, so PyMedPhys exposes
extras for common workflows.

## What happens when a package is missing

PyMedPhys loads an optional package only when you use a feature that needs it.
So `import pymedphys` works on any install, and so does every feature whose
packages you have installed.

If you use a feature that needs a package you do not have, PyMedPhys stops with
an error that names the package and the command that installs it, for example:

```text
ModuleNotFoundError: PyMedPhys could not import "numpy" (needed for "numpy.inf"). It is provided by "numpy", which is in the optional "user" extra. Install the extra with:

    python -m pip install "pymedphys[user]==0.42.0"
```

Run that command in the same environment, then restart Python, your notebook
kernel, or `pymedphys gui`. The command keeps your installed version of
PyMedPhys and adds the missing packages. It suggests the `user` extra because
that extra covers every feature except the experimental AI chat app. If you
manage the environment with `uv`, run the same requirement with
`uv pip install` instead of `python -m pip install`.

If you installed a development version from a source checkout, the message
instead suggests `python -m pip install -e ".[user]"`, to run in that checkout.

A smaller install is quicker to set up and has fewer packages to keep up to
date, but only if it includes everything your work uses. For how this works
inside PyMedPhys, see
[Lazy imports and optional dependencies](../../contrib/info/lazy-imports.md).

## Important note about the commands on this page

The example commands below assume you already created a virtual environment,
such as the `.venv` made in the Quick Start Guide.

All examples below use `uv pip install`.
If you are using the fallback Python + `venv` + `pip` path, replace
`uv pip install` with `python -m pip install`.

Use quotes around the requirement string.
They help on shells that would otherwise interpret square brackets.

## User-facing extras

| Extra    | Install command                      | Best for                                                             | Notes                                                                         |
| -------- | ------------------------------------ | -------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| none     | `uv pip install pymedphys`           | advanced users who intentionally want the smallest base install      | many user-facing features will need more packages                             |
| `user`   | `uv pip install "pymedphys[user]"`   | most workstation users                                               | recommended default                                                           |
| `cli`    | `uv pip install "pymedphys[cli]"`    | command line usage when you already know the feature extras you need | usually combine with `dicom`, `mosaiq`, or other extras                       |
| `dicom`  | `uv pip install "pymedphys[dicom]"`  | DICOM read/write/network workflows                                   | good fit for DICOM-focused scripting or CLI work                              |
| `icom`   | `uv pip install "pymedphys[icom]"`   | iCom-related workflows                                               | often combined with `user` or `cli`                                           |
| `mosaiq` | `uv pip install "pymedphys[mosaiq]"` | Mosaiq data access and reporting                                     | site-specific connectivity and credentials are still required                 |
| `ai`     | `uv pip install "pymedphys[ai]"`     | the experimental Mosaiq chat app in the GUI                          | sends questions and query results to Anthropic's API; combine with `user`     |
| `all`    | `uv pip install "pymedphys[all]"`    | contributors and power users                                         | large install that also pulls in development, test, and documentation tooling |

```{note}
The narrower extras do not yet include everything their features need. For
example, `dicom` does not include NumPy, which `pymedphys.dicom.anonymise` and
`pymedphys dicom anonymise` use, and `mosaiq` does not include `keyring`, which
`pymedphys.mosaiq.connect` uses. Until they are fixed, prefer `user`, or install
the packages that the error messages name.
```

## Recommended combinations

### Broad workstation install

Use this if you want the least decision-making and expect to use notebooks,
plots, DICOM workflows, or the app layer.

```bash
uv pip install "pymedphys[user]"
```

### DICOM automation

Use this if you want DICOM-related workflows from scripts, batch files, or
schedulers.

```bash
uv pip install "pymedphys[dicom,cli]"
```

### Mosaiq automation

Use this if you plan to automate Mosaiq-backed reporting or data extraction.

```bash
uv pip install "pymedphys[mosaiq,cli]"
```

### Broad user install with iCom support

Use this if your normal user workflow also needs iCom-specific functionality.

```bash
uv pip install "pymedphys[user,icom]"
```

## What most users should choose

If you are a medical physicist working on one workstation and you are not
trying to minimise dependencies, choose `user`.

If you are building a scheduled or scripted DICOM workflow, start with
`dicom,cli`.

If you are building a Mosaiq-backed workflow, start with `mosaiq` and add
`cli` when you want shell automation.

If you are contributing to PyMedPhys itself, follow the
[Contributors Guide](https://docs.pymedphys.com/en/latest/contrib/index.html) rather than treating this page
as your main setup guide.

## A note on `all`

The `all` extra exists, but it is not the best default for ordinary users.
It pulls in a large dependency set, including packages that are mainly useful
for testing, documentation, or development.
Choose it only when you deliberately want that trade-off.

## Next step

Once you know which install you want, continue to the
[Quick Start Guide](quick-start.rst).

If you are still deciding how you want to use PyMedPhys, read
[Choose your path](choose-your-path.md).
