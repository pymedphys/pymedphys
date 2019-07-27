============
Installation
============

In order to make use of the PyMedPhys library, you'll need Python installed on
your workstation. Although not essential, we recommend that you install the
`Anaconda Python distribution`_. Instructions for installing Anaconda can be
found `here`_.

.. _`Anaconda Python distribution`: https://www.anaconda.com/distribution/
.. _`here`: ../developer/contributing.html#python-anaconda

Once you have a suitable Python installation, you can install the latest stable
version of PyMedPhys via conda or pip as follows:


Installing via Conda from conda-forge (recommended)
---------------------------------------------------

PyMedPhys can be installed via the `conda-forge channel`_. To install, run the
following commands in your terminal:

.. _`conda-forge channel`: https://conda-forge.org/

.. code:: bash

    conda config --add channels conda-forge
    conda install pymedphys


Installing via pip from PyPI
----------------------------

Alternatively, you can install via pip as follows:

.. code:: bash

    pip install pymedphys


Note that issues with some of PyMedPhys' dependencies may arise if you choose
to install via this method.


Installing the "bleeding edge" version from GitHub
--------------------------------------------------

You can install the very latest, "bleeding edge", development version of
PyMedPhys, but you will first need Git and Yarn. In turn, Yarn requires Nodejs.
Perhaps the easiest way to install these is to install Chocolatey from within
a terminal in Administrator mode using `these instructions <https://chocolatey.org/docs/installation>`__.
Once installed, reload your terminal and run the following commands:

.. code:: bash

    choco install git nodejs yarn

If you already have Git installed, you can of course remove "``git``" from the
above command.

Once installation is complete, reload the terminal again and run the following
commands to clone the ``pymedphys`` GitHub repo and install the ``pymedphys``
package along with its dependencies:

.. code:: bash

    git clone git@github.com:pymedphys/pymedphys.git
    # If you prefer HTTPS, use this link instead: https://github.com/pymedphys/pymedphys.git
    cd pymedphys

    conda config --add channels conda-forge
    yarn bootstrap
