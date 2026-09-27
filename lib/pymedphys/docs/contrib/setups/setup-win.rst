Windows Setup
=============

Install prerequisites
=====================

Install `Git <https://git-scm.com/downloads>`_ and
`uv <https://docs.astral.sh/uv/getting-started/installation/>`_.
The commands on this page use PowerShell. The standalone uv installer is:

.. code-block:: powershell

    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

Choose a per-user installation where offered if you do not have administrator
access. Follow your organisation's software installation policy.

Open a new terminal if ``uv`` is not yet on your ``PATH``.

Create the development environment
===================================

Run these commands from the directory where you keep your projects. If you
will contribute through a fork, substitute your fork's clone URL.

.. code-block:: powershell

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
or document conversion. For SSH authentication, see
:doc:`Git with SSH on Windows <../tips/win-open-ssh>`.


Next steps
==========

* Run ``uv run pymedphys dev tests -m "not slow"``.
* Follow the :doc:`documentation guide <../info/docs-guide>` to build the site.
* Read the :doc:`workflow guide <../info/workflows>` before opening a PR.
* For notebooks, :doc:`register the project kernel <../tips/add-jupyter-kernel>`.
* An editor such as `Visual Studio Code <https://code.visualstudio.com/>`_ is
  optional.
