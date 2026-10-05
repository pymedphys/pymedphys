Windows prerequisites
=====================

This page prepares a Windows workstation for the current source checkout.
Its commands use PowerShell. When Git and uv are available, continue with
the shared :doc:`development environment procedure <../start/setup>`.

Install prerequisites
---------------------

Install `Git <https://git-scm.com/downloads>`_ and
`uv <https://docs.astral.sh/uv/getting-started/installation/>`_.
Choose a per-user installation where offered if you do not have administrator
access, and follow your organisation's software installation policy.
The standalone uv installer is:

.. code-block:: powershell

    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

Open a new PowerShell window if ``uv`` is not on your ``PATH``. Run
``git --version`` and ``uv --version``; each should print its installed version.

Optional tools
--------------

Install `Pandoc <https://pandoc.org/installing.html>`_ when you need notebook
or document conversion. It is not required for the normal HTML documentation
build. An editor such as `Visual Studio Code <https://code.visualstudio.com/>`_
is optional.

HTTPS cloning does not need an SSH key. For SSH authentication, see
:doc:`Git with SSH on Windows <../tips/win-open-ssh>`.
The shared setup guide owns the clone, locked environment, hook installation,
and success checks. Use :doc:`the Jupyter kernel instructions
<../tips/add-jupyter-kernel>` when working with notebooks.

.. raw:: html

    <span id="windows-setup"></span>
    <span id="create-the-development-environment"></span>
    <span id="next-steps"></span>

The shared :doc:`checkout setup <../start/setup>` replaces the former
platform-specific environment instructions. Continue with
:doc:`your first contribution <../start/first-contribution>`.
