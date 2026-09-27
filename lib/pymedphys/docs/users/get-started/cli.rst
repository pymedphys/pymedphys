=============
Using the CLI
=============

PyMedPhys exposes part of its functionality as a command line interface (CLI).
The CLI is a good fit when you want to run a repeatable task without writing
much Python.

Common reasons to use the CLI include:

- scheduled jobs such as Windows Task Scheduler or cron
- shell scripts, batch files, and operational automation
- calling PyMedPhys from other tools or languages
- standardising a workflow so multiple people run the same command

If you have not installed PyMedPhys yet, read
:doc:`Installation options <installation-options>` first.
Common CLI-centred installs include:

.. code:: bash

    uv pip install "pymedphys[dicom,cli]"
    uv pip install "pymedphys[mosaiq,cli]"

If you used the fallback Python + ``venv`` + ``pip`` path, replace
``uv pip install`` with ``python -m pip install``.

After installation, start by viewing the top-level help:

.. code:: bash

    pymedphys --help

Then inspect the help for the command you care about:

.. code:: bash

    pymedphys <command> --help

The full technical reference for the current command set is available here:
:doc:`CLI Reference <../ref/cli/index>`.

If you are still deciding whether the CLI is the right interface, read
:doc:`Choose your path <choose-your-path>`.
