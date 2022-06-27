# Creating a Streamlit Executable

## Document overview

This document details the process undergone to create an Electron application
that embeds streamlit. The result is an easily shareable binary built for each
of the major operating systems.

This document refers to the state of the PyMedPhys code base as at commit hash
[836f272d092f294099bb51db05bab80d2bfcb628](https://github.com/pymedphys/pymedphys/tree/836f272d092f294099bb51db05bab80d2bfcb628).
All code links will be pointing to the code base at that commit hash.

## Quick version

To actually build and create the binary all you actually need to do is the following:

- Install [Poetry](https://python-poetry.org/docs/#installation)
- Install [Node](https://nodejs.org/en/) and [Yarn](https://classic.yarnpkg.com/en/docs/install#debian-stable)
- Install PyOxidizer by installing all the project build dependencies:
  - poetry install -E build
- Then run `poetry run pymedphys dev build --install`
  - Which runs [this](https://github.com/pymedphys/pymedphys/blob/836f272d092f294099bb51db05bab80d2bfcb628/lib/pymedphys/_dev/build.py#L28-L51) under the hood.

The final built application for your current OS will be contained within
`js/app/dist`.

If you would like to dig deeper into what the above is doing under the hood,
then read on.

## Approach overview

To create this binary build four key steps were undergone:

- Create a completely system independent self contained Python environment
- Set up the electron desktop application wrapper
- Make the desktop application boot and connect to the streamlit running within
  the self contained Python environment.
- Use electron builder to create an installer, run this within GitHub actions
  across the three major OSs.

Further detail into each of these steps along with the corresponding code is
given below.

## Creating a self contained PyMedPhys python bundle

### Justification of approach

To create the self contained Python environment PyOxidizer was utilised. This
tool contains a range of embeddable Python distributions for each OS. There are
a range of issues with a standard Python install (venv) or otherwise that make
it hard to pick up the Python install off one computer onto another computer in
a portable fashion. One such issue is that the standard Python install
explicitly hardcodes the install location. Therefore, subsequent moving of the
installation causes issues.

There are many tools that can create embedded Python installations. PyInstaller
is one, however I have had issues where it gets flagged as the created program
gets flagged as a virus on Windows. It also, in the name of trying to make a
small install size, by default strips out a lot of dependencies. This
"stripping out" makes the resulting binary have many weird edge case issues.

At the end of the day, the goal was to utilise a tool that creates an embedded
Python distribution that is as close to "standard" as possible. PyOxidizer can
be configured to achieve that, so that was utilised.

### The `pyoxidizer.bzl` configuration file

The configuration file for building the binary can be found at
[pyoxidizer.bzl](https://github.com/pymedphys/pymedphys/blob/836f272d092f294099bb51db05bab80d2bfcb628/pyoxidizer.bzl).

We'll go into the key details that make this configuration file different here.
Further details about the PyOxidizer configuration file can be found in
[the official docs](https://pyoxidizer.readthedocs.io/en/stable/).

PyOxidizer comes with a range of amazing tooling to create custom binaries. We
however will be mostly turning all of this amazing tooling off for maximum
compatibility with a standard Python installation. The key steps are:

- Make resource handling be set to "files" mode (needed for NumPy at least) [#L20](https://github.com/pymedphys/pymedphys/blob/836f272d092f294099bb51db05bab80d2bfcb628/pyoxidizer.bzl)
- Use filesystem-relative for the resource location, and use a filename of
  "site-packages". [#L22-L24](https://github.com/pymedphys/pymedphys/blob/836f272d092f294099bb51db05bab80d2bfcb628/pyoxidizer.bzl#L22-L24)
- Disable the PyOxidizer importer [#L30-L31](https://github.com/pymedphys/pymedphys/blob/836f272d092f294099bb51db05bab80d2bfcb628/pyoxidizer.bzl#L30-L31)

A specific fix for Streamlit is the need to use "site-packages" within the
resource location
([#L22-L27](https://github.com/pymedphys/pymedphys/blob/836f272d092f294099bb51db05bab80d2bfcb628/pyoxidizer.bzl#L22-L27)).
This is due to Streamlit using [that file directory location as an indicator](https://github.com/streamlit/streamlit/blob/953dfdbeb51a4d0cb4ddb81aaad8e4321fe5db73/lib/streamlit/config.py#L255-L267)
that Streamlit is not running in developer mode.

Once that configuration file is created, and once PyOxidizer is installed then
running `poetry run pyoxidizer build install` will create a `pymedphys` binary
within a `dist` directory within the repository root.

## Setting up electron

## Booting the streamlit app and syncing the port with Electron

## Building for all OSs within GitHub Actions
