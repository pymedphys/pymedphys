# Installation options

PyMedPhys uses optional dependency groups so you can install either a broad
end-user stack or a narrower task-specific stack.

PyMedPhys currently supports Python 3.10, 3.11, and 3.12.

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
{doc}`Quick Start Guide <quick-start>`.

## Why there is more than one install

A plain `pymedphys` install keeps the core package small.
Many user-facing features need optional dependencies, so PyMedPhys exposes
extras for common workflows.

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
| `all`    | `uv pip install "pymedphys[all]"`    | contributors and power users                                         | large install that also pulls in development, test, and documentation tooling |

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
{doc}`Contributors Guide <../../contrib/index>` rather than treating this page
as your main setup guide.

## A note on `all`

The `all` extra exists, but it is not the best default for ordinary users.
It pulls in a large dependency set, including packages that are mainly useful
for testing, documentation, or development.
Choose it only when you deliberately want that trade-off.

## Next step

Once you know which install you want, continue to the
{doc}`Quick Start Guide <quick-start>`.

If you are still deciding how you want to use PyMedPhys, read
{doc}`Choose your path <choose-your-path>`.
