# Installation options

This page explains what the different ways of installing PyMedPhys give you.
For almost everyone, the answer is `pymedphys[user]`.

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
Most features need optional packages, so PyMedPhys offers **extras**: named
sets of optional packages, requested in square brackets, as in
`"pymedphys[user]"`.

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

For how this works inside PyMedPhys, see
[Lazy imports and optional dependencies](../../contrib/info/lazy-imports.md).

## Important note about the commands on this page

The example commands below assume you already created a virtual environment,
such as the `.venv` made in the Quick Start Guide.

All examples below use `uv pip install`.
If you are using the fallback Python + `venv` + `pip` path, replace
`uv pip install` with `python -m pip install`.

Use quotes around the requirement string.
They help on shells that would otherwise interpret square brackets.

## Extras

| Extra | Install command | What it adds |
| --- | --- | --- |
| none | `uv pip install pymedphys` | Only the core package. Most features stop with an error that says what to install. |
| `user` | `uv pip install "pymedphys[user]"` | Everything the library, the command line, and the GUI use. **Recommended for most people.** |
| `ai` | `uv pip install "pymedphys[user,ai]"` | The experimental Mosaiq AI chat app in the GUI. It sends questions and query results to Anthropic's API. |
| `tests` | `uv pip install "pymedphys[tests]"` | `user`, plus what you need to run PyMedPhys's own test suite with `pymedphys dev tests`, for example to check an installation. |
| `all` | `uv pip install "pymedphys[all]"` | `user`, `ai`, and `tests` together. |

### Smaller installs for one feature

If you use only one part of PyMedPhys, for example on a server that only
receives DICOM files, a feature extra installs just what that feature needs.
Combine them with commas, for example `"pymedphys[gamma,dicom]"` for gamma on
DICOM files.

| Extra | Covers |
| --- | --- |
| `gamma` | `pymedphys.gamma` and `pymedphys.gamma_pass_rate`. |
| `dicom` | `pymedphys.dicom` and the `pymedphys dicom` commands, including `listen` and `send`. |
| `mosaiq` | `pymedphys.mosaiq` and `pymedphys.Delivery.from_mosaiq`. |
| `icom` | `pymedphys icom listen` and `pymedphys.Delivery.from_icom`. |
| `trf` | `pymedphys.trf.read`, `pymedphys.Delivery.from_trf`, and the `pymedphys trf to-csv` command. Identifying TRF files against Mosaiq, with `pymedphys.trf.identify` or `pymedphys trf orchestrate`, needs `"pymedphys[trf,mosaiq]"`. |
| `cli` | The same as `user`, because the command line spans every feature. |

These extras do not cover plotting helpers, such as
`pymedphys.metersetmap.display`, which need matplotlib, or the GUI. `user`
covers everything. If a feature extra is missing a package, the error message
suggests `user`, which always works.

Before this release, the `dicom`, `icom`, and `mosaiq` extras did not include
everything their features needed: for example, `dicom` had no NumPy, which
DICOM anonymisation uses. They now do, and CI checks each extra on its own.
`mosaiq` no longer installs the packages that only TRF identification uses, so
install `"pymedphys[trf,mosaiq]"` for that.

## What most people should choose

Choose `user`. It suits workstation use, scripts and scheduled jobs, DICOM and
Mosaiq automation, iCOM services, and the GUI.

Choose a feature extra only when a smaller install matters, such as a
dedicated DICOM or iCOM service, and you use only that feature.

Add `ai` only if you want to try the experimental AI chat app, and `tests` only
if you want to run the test suite against your installation.

If you are contributing to PyMedPhys itself, follow the
[Contributors Guide](https://docs.pymedphys.com/en/latest/contrib/index.html)
instead. A source checkout uses dependency groups, which are not published to
PyPI, and `uv sync` installs everything a contributor needs.

## Next step

Once you know which install you want, continue to the
[Quick Start Guide](quick-start.rst).

If you are still deciding how you want to use PyMedPhys, read
[Choose your path](choose-your-path.md).
