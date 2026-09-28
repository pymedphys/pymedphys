# Lazy imports and optional dependencies

PyMedPhys can be installed with very few dependencies, but most of its features need optional packages such as NumPy, pydicom, or Streamlit. This page explains how the library copes with packages that may not be installed, what users see when one is missing, and the rules contributors follow so that this keeps working.

## Base install and extras

- `pip install pymedphys` is the **base install**. It installs PyMedPhys and its required dependencies only, which today is just `tomlkit`.
- `pip install "pymedphys[user]"` also installs the optional packages that PyMedPhys's features use. The name in square brackets is an **extra**: a named set of optional dependencies, declared under `[project.optional-dependencies]` in `pyproject.toml`.

`user` is the extra to recommend. It covers every feature except the experimental AI chat app, which has its own `ai` extra. The narrow feature extras, `gamma`, `dicom`, `mosaiq`, `icom`, and `trf`, each install only what one feature's public functions and commands use, for smaller installs.

Extras are for people who install PyMedPhys. The tools for working on PyMedPhys itself, such as linters and the documentation build, are in **dependency groups** under `[dependency-groups]`, which are not published to PyPI. `uv sync` in a source checkout installs every extra and every tool, through the default `dev` group.

## How lazy imports work

Library code never imports an optional package directly. Instead of

```python
import numpy as np
```

it writes

```python
from pymedphys._imports import numpy as np
```

This `np` is a stand-in object. Importing it costs nothing and cannot fail. The first time the code uses it, for example `np.array(...)`, the stand-in imports the real NumPy and passes the request on. From then on it behaves like NumPy.

So `import pymedphys` works on a base install, and a missing package only matters when a feature that needs it is used.

The pieces are:

- `lib/pymedphys/_imports/imports.py`, the **registry**. It lists every optional import as an ordinary `import` statement, such as `import numpy as np` or `import scipy.ndimage`. It is parsed, never run.
- `lib/pymedphys/_imports/__init__.py` turns the registry into stand-ins using a vendored and patched copy of [apipkg](https://github.com/pytest-dev/apipkg), in `lib/pymedphys/_vendor/apipkg/`.
- `lib/pymedphys/_extras.py` writes the message shown when a package is missing.

## What a user sees when a package is missing

Using a feature whose package is not installed raises `ModuleNotFoundError`, and the message says what to install. For a release of PyMedPhys:

```text
ModuleNotFoundError: PyMedPhys could not import "numpy" (needed for "numpy.inf"). It is provided by "numpy", which is in the optional "user" extra. Install the extra with:

    python -m pip install "pymedphys[user]==0.42.0"
```

The details:

- The command is quoted, so shells such as zsh, the default on macOS, do not treat the square brackets as a file pattern.
- It pins the installed version, so pip adds the extra's packages without upgrading PyMedPhys.
- On a development version, which is not on PyPI, the message instead suggests installing the extra from the source checkout, for example `python -m pip install -e ".[user]"`, so that pip does not replace the development version with a release.
- The error's `name` attribute is the missing package, for example `"numpy"`.
- The extra is found from the generated `lib/pymedphys/dependency-extra.txt`, using the distribution's name rather than the name it is imported under. `sklearn`, for example, comes from `scikit-learn`.
- The message suggests `user` even when a narrow extra, such as `dicom`, also has the package. One missing package usually means the rest of a feature is missing too, and PyMedPhys cannot tell which feature is being used, whereas `user` always covers it.

Two other cases get their own message:

- **The package is installed but broken**, for example because one of its own dependencies is missing. The original error is shown unchanged, because installing the extra would not help.
- **The package is part of the standard library but missing from this Python**, such as `tkinter` on a Python built without Tk. The message says so.

### Introspection

Tools such as `inspect`, `doctest`, and IDEs ask objects whether they have attributes like `__wrapped__`, usually with `hasattr`, which only treats `AttributeError` as "no". When the real package is missing, a stand-in therefore answers questions about double-underscore attributes as a module without them would: the attribute is absent. Every other attribute raises the `ModuleNotFoundError` above, so `hasattr(np, "array")` raises rather than returning `False`. That is deliberate: using a missing package should say how to install it.

## Rules for contributors

### Add a new optional dependency

1. Add the distribution to `user` in `pyproject.toml`, and also to the narrow extra of the feature that uses it, if its public functions or commands need it. A tool used only for working on PyMedPhys goes in a dependency group instead, such as `lint` or `docs`.
2. Run `uv lock` and `pymedphys dev propagate`, which regenerates `dependency-extra.txt` and the other generated files. CI fails if they are out of date.
3. Add an `import` statement for it to `lib/pymedphys/_imports/imports.py`. Register each submodule that code uses and that the package does not import itself (see below).
4. If the import name differs from the distribution name, as with `import yaml` from `PyYAML`, add the pair to `DISTRIBUTION_FOR_IMPORT` in `lib/pymedphys/_extras.py`.
5. Import it in library code with `from pymedphys._imports import ...`.

A test checks that every package in the registry is declared in `pyproject.toml`, and that the name table agrees with the installed packages.

### Register the submodules you use

A stand-in can only give access to what the real package itself provides. `matplotlib` does not import `matplotlib.sankey`, for example, so with only `matplotlib` registered, `matplotlib.sankey` raises `AttributeError`, unless some other code happened to import it first. Register the submodule, as the registry does for `matplotlib.pyplot` and `scipy.ndimage`, to make it available however the code is reached.

### Do not use an optional package while a module is being imported

A stand-in only helps if it is not used when the module is imported. Anything that runs at import time, when Python executes the module's top level, must not touch an optional package:

```python
from pymedphys._imports import numpy as np
from pymedphys._imports import streamlit as st

TWO_PI = 2 * np.pi                    # runs at import: fails on a base install

@st.cache_data                        # the decorator runs at import: fails
def load(path): ...

def scale(x, factor=np.float64(1)):   # default values run at import: fails
    ...

def total(values: np.ndarray): ...    # annotations run at import, unless the
                                      # module has `from __future__ import annotations`

def area(radius):
    return np.pi * radius**2          # fine: runs only when area() is called
```

Do not import an optional package directly either, even inside a `try` block, unless there is a documented fallback. The error would then lack the install instructions.

### Modules that may need an extra to be imported

Some modules cannot follow these rules without an unreasonable rewrite. The Streamlit apps use Streamlit at import time, for example in `@st.cache_data`, and the AI modules import Anthropic's SDK directly. `REQUIRED_EXTRAS` in `lib/pymedphys/_dev/import_policy.py` lists them, with the extra each needs:

| Modules | Extra needed to import them |
| --- | --- |
| `pymedphys._app`, `pymedphys._streamlit`, `pymedphys._experimental.streamlit` | `user` |
| `pymedphys._ai` and the Mosaiq chat app's `app` module | `ai` |
| `pymedphys.tests` and `pymedphys.conftest` | `tests` |

Every other module must import on a base install. Only add an entry when a module cannot reasonably defer its imports, and never for code that the public API or the CLI imports.

## How it is checked

- **In every unit test job**, `lib/pymedphys/tests/imports/test_optional_dependencies.py` starts a fresh Python interpreter and installs an import hook, from `base_install.py` in the same folder, that refuses every import except the standard library, PyMedPhys, and the base dependencies. It then imports every module that `import_policy` says must work on a base install. This imitates a base install without creating one, so it runs quickly on every operating system.
- The same file checks that the Streamlit modules import once `user` is installed, that the messages name the right extra, that introspection does not fail, and that the registry matches `pyproject.toml`. The check for the AI modules is skipped wherever the `ai` extra is not installed, which currently includes CI.
- **The `narrow-extras` job in `unit-tests.yml`** installs each narrow extra alone, with only the `test-runner` dependency group, and runs that feature's tests, so a package missing from the extra fails CI. `mosaiq-db-tests.yml` does the same for `mosaiq` against a SQL Server database. A test in those folders that exercises another feature, private code, or a plotting helper skips itself with `pytest.importorskip` when that package is missing.
- **`pymedphys dev imports`** checks the same policy against real installs. It creates a virtual environment, installs PyMedPhys without extras, imports each base-tier module in its own interpreter, then installs the `user`, `ai`, and `tests` extras and imports everything else. It needs network access, so CI does not run it.

## Known gap

- The command line reads `~/.pymedphys/config.toml` with the optional `toml` package, so on a base install every `pymedphys` command fails when that file exists.

[#2072](https://github.com/pymedphys/pymedphys/issues/2072) has the background to this page.
