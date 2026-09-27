macOS Setup
===========

Install prerequisites
=====================

Install `Git <https://git-scm.com/downloads>`_ and
`uv <https://docs.astral.sh/uv/getting-started/installation/>`_.
On macOS, the standalone uv installer is:

.. code-block:: bash

    curl -LsSf https://astral.sh/uv/install.sh | sh

Open a new terminal if ``uv`` is not yet on your ``PATH``.

Create the development environment
===================================

Run these commands from the directory where you keep your projects. If you
will contribute through a fork, substitute your fork's clone URL.

.. code-block:: bash

    git clone https://github.com/pymedphys/pymedphys.git
    cd pymedphys
    uv python install 3.12
    uv sync --python 3.12 --locked --extra all --group dev
    uv run pre-commit install

The current source supports Python 3.10, 3.11, and 3.12. Python 3.12 matches
the quick CI run; no particular patch version is required. uv can install
Python for you, so a separate Python or pipx installation is not required.

``uv sync`` creates the repository's ``.venv`` and installs an editable copy of
PyMedPhys with the contributor dependencies. Run project commands with
``uv run`` from the repository root.

Install `Pandoc <https://pandoc.org/installing.html>`_ if needed for notebook
or document conversion (for example, ``brew install pandoc`` with
`Homebrew <https://brew.sh/>`_). FreeTDS and Cython are not general setup
prerequisites: additional build tools may be needed if a dependency has no
wheel for your Python version and platform. Follow that package's build
instructions if installation reports a source-build failure.


Next steps
==========

* Run ``uv run pymedphys dev tests -m "not slow"``.
* Follow the :doc:`documentation guide <../info/docs-guide>` to build the site.
* Read the :doc:`workflow guide <../info/workflows>` before opening a PR.
* For notebooks, :doc:`register the project kernel <../tips/add-jupyter-kernel>`.
* An editor such as `Visual Studio Code <https://code.visualstudio.com/>`_ is
  optional.
