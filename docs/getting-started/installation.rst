Installation
============

Conda from Conda-Forge
----------------------

To install use the `Anaconda Python distribution`_ with the
`conda-forge channel`_

.. _`Anaconda Python distribution`: https://www.continuum.io/anaconda-overview

.. _`conda-forge channel`: https://conda-forge.org/

.. code:: bash

    conda config --add channels conda-forge
    conda install pymedphys

Pip from PyPi
-------------

You can of course also use pip to install, but you may have trouble with some
of the dependencies without conda

.. code:: bash

    pip install pymedphys


Bleeding edge with GitHub
-------------------------

If you would like to have a bleeding edge installation of pymedphys use the
following commands to install the master branch from GitHub.

.. code:: bash

    git clone https://github.com/pymedphys/pymedphys.git
    cd pymedphys

    conda config --add channels conda-forge
    conda install pymedphys --only-deps
    pip install -e .