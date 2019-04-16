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
PyMedPhys by directly cloning its GitHub repo and installing its dependencies
using the following commands from within a terminal:

.. code:: bash

    git clone https://github.com/pymedphys/pymedphys.git
    cd pymedphys

    conda config --add channels conda-forge
    conda install pymedphys --only-deps
    pip install -e .


Note that this requires Git to be installed on your workstation. Instructions
for installing Git can be found in the `Developer Guide`_.

.. _`Developer Guide`: ../developer/contributing.html#chocolatey
