macOS prerequisites
===================

This page prepares a macOS workstation for the current source checkout.
When Git, uv, and the platform build prerequisites are available, continue
with the shared :doc:`development environment procedure <../start/setup>`.

Install prerequisites
---------------------

Install `Git <https://git-scm.com/downloads>`_ and
`uv <https://docs.astral.sh/uv/getting-started/installation/>`_ through a
method allowed by your organisation. The standalone uv installer is:

.. code-block:: bash

    curl -LsSf https://astral.sh/uv/install.sh | sh

Open a new terminal if ``uv`` is not on your ``PATH``. Run ``git --version``
and ``uv --version``; each should print its installed version.

Before using Python 3.14, follow the macOS build prerequisites in
:doc:`Installation options <../../users/get-started/installation-options>`.
FreeTDS and Cython are not general setup prerequisites. Additional build
tools may be needed when a dependency has no wheel for the selected Python
and platform; follow the package's instructions if it reports a source-build
failure.

Optional tools
--------------

Install `Pandoc <https://pandoc.org/installing.html>`_ when you need notebook
or document conversion, for example ``brew install pandoc`` with
`Homebrew <https://brew.sh/>`_. It is not required for the normal HTML
documentation build. An editor such as
`Visual Studio Code <https://code.visualstudio.com/>`_ is optional.

The shared setup guide owns the clone, locked environment, hook installation,
and success checks. Use :doc:`the Jupyter kernel instructions
<../tips/add-jupyter-kernel>` when working with notebooks.

.. raw:: html

    <span id="macos-setup"></span>
    <span id="create-the-development-environment"></span>
    <span id="next-steps"></span>

The shared :doc:`checkout setup <../start/setup>` replaces the former
platform-specific environment instructions. Continue with
:doc:`your first contribution <../start/first-contribution>`.
