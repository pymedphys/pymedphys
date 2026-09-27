Use the development environment in Jupyter
==========================================

After completing a :doc:`workstation setup <../setups/index>`, register the
repository's Python environment as a Jupyter kernel. Run from the repository
root:

.. code-block:: bash

    uv run python -m ipykernel install --user --name pymedphys --display-name "PyMedPhys (development)"

Select **PyMedPhys (development)** in your notebook editor. The kernel points
to this checkout's ``.venv``; register it again if you move the repository or
recreate the environment at another path.

JupyterLab itself is optional and is not included in the locked project
dependencies. To launch it with uv:

.. code-block:: bash

    uv run --with jupyterlab jupyter lab

See `uv's Jupyter guide
<https://docs.astral.sh/uv/guides/integration/jupyter/>`_ for other setups.
