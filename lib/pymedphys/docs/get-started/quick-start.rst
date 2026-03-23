==================
Quick Start Guide
==================

This page gets you to a working PyMedPhys installation quickly.

If you are unsure which installation to choose, read
:doc:`Installation options <installation-options>` first.
For most users, the recommended install is:

.. code:: bash

    uv python install 3.12
    uv venv --python 3.12
    uv pip install "pymedphys[user]"

PyMedPhys currently supports Python 3.10, 3.11, and 3.12.

We recommend using ``uv`` for this guide. It can install Python, create a
virtual environment, and install packages with one tool.

Windows users: the commands below assume PowerShell.
Linux and macOS users: the commands below assume a POSIX shell.

Install uv
==========

Any official uv installation method is fine. The standalone installer is shown
here because it works without a pre-existing Python installation.

Windows
-------

.. code:: powershell

    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

Open a new PowerShell window if ``uv`` is not found immediately, then confirm
the installation:

.. code:: powershell

    uv --version

Linux or macOS
--------------

.. code:: bash

    curl -LsSf https://astral.sh/uv/install.sh | sh

Open a new terminal if ``uv`` is not found immediately, then confirm the
installation:

.. code:: bash

    uv --version

Create a Python environment
===========================

From the folder where you want the environment to live, run:

.. code:: bash

    uv python install 3.12
    uv venv --python 3.12

This creates a ``.venv`` directory in the current folder.

Install PyMedPhys
=================

Recommended default
-------------------

For most users:

.. code:: bash

    uv pip install "pymedphys[user]"

Other common installs
---------------------

If you need a narrower install, here are some common patterns:

.. code:: bash

    uv pip install "pymedphys[dicom,cli]"
    uv pip install "pymedphys[mosaiq,cli]"
    uv pip install "pymedphys[user,icom]"

Because ``.venv`` exists in the current folder, ``uv pip install`` will
install into that environment automatically.

Read :doc:`Installation options <installation-options>` for guidance on which
combination to choose.

Use the environment
===================

Activate the environment so ``python`` and ``pymedphys`` resolve to the new
install.

Windows
-------

.. code:: powershell

    .venv\Scripts\activate

Linux or macOS
--------------

.. code:: bash

    source .venv/bin/activate

Once activated, confirm that Python can import PyMedPhys:

.. code:: bash

    python -c "import pymedphys; print(pymedphys.__version__)"

Then confirm that the command line entry point is available:

.. code:: bash

    pymedphys --help

If you plan to use command line workflows, continue to
:doc:`Using the CLI <cli>`.

Troubleshooting installation
============================

TLS or certificate issues
-------------------------

Some healthcare networks use a corporate trust root or HTTPS interception.
In that case, try telling uv to use the operating system certificate store.

Windows
^^^^^^^

.. code:: powershell

    $env:UV_NATIVE_TLS = "true"
    uv pip install "pymedphys[user]"

Linux or macOS
^^^^^^^^^^^^^^

.. code:: bash

    UV_NATIVE_TLS=true uv pip install "pymedphys[user]"

Proxy issues
------------

If your network requires an outbound proxy, define it before running
``uv pip install``. For PyPI access, ``HTTPS_PROXY`` is the most common
variable to set.

Windows
^^^^^^^

.. code:: powershell

    $env:HTTPS_PROXY = "http://username:password@host:port"
    uv pip install "pymedphys[user]"

Linux or macOS
^^^^^^^^^^^^^^

.. code:: bash

    export HTTPS_PROXY="http://username:password@host:port"
    uv pip install "pymedphys[user]"

Replace ``username``, ``password``, ``host``, and ``port`` with the values
used in your environment.
If you do not know them, ask your network administrator.

Fallback if you cannot use uv
=============================

If your workstation cannot install ``uv``, use a standard Python virtual
environment instead. This fallback assumes Python is already installed and
available on ``PATH``. If your existing installation uses ``py`` rather than
``python``, substitute ``py`` in the commands below.

Windows
-------

.. code:: powershell

    python -m venv .venv
    .venv\Scripts\activate
    python -m pip install --upgrade pip
    python -m pip install "pymedphys[user]"

Linux or macOS
--------------

.. code:: bash

    python -m venv .venv
    source .venv/bin/activate
    python -m pip install --upgrade pip
    python -m pip install "pymedphys[user]"

Next steps
==========

- Read :doc:`What PyMedPhys can do <what-pymedphys-can-do>` if you are still exploring.
- Read :doc:`Choose your path <choose-your-path>` if you are deciding between the library, CLI, and app layer.
- Read :doc:`Using the CLI <cli>` if you want scheduled or scripted workflows.
- Browse the :doc:`How-to Guides <../howto/index>` if you already know the task you want to solve.
