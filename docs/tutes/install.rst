Installation
============

.. contents::
    :local:
    :backlinks: entry

In order to make use of the PyMedPhys library, you'll need Python installed on
your workstation. Although not essential, we recommend that you install the
Anaconda Python distribution which is an open source, optimized Python
(and R) distribution. Download the latest Anaconda Python **3** (not 2) version
from `here <https://www.anaconda.com/download/>`__.

.. note::
    When installing Anaconda make sure to install it for your user only, and
    tick the option "add to path".

.. image:: ../img/add_anaconda_to_path.png

Once you have a suitable Python installation, you can install the latest stable
version of PyMedPhys via conda or pip as described in the following sections.


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

Setting up a development environment
------------------------------------

To set up a development environment please follow the
`Developer Guide`_. That guide provides specific details
for Windows users, but similar steps work
on macOS and Linux also.


Installing the "bleeding edge" version from GitHub
--------------------------------------------------

You can install the very latest, "bleeding edge", development version of
PyMedPhys, but you will first need Git and Yarn. You can find instructions for
installing Git `here <https://www.atlassian.com/git/tutorials/install-git>`__
and Yarn `here <https://yarnpkg.com/en/docs/install>`__.

Once you have Git and Yarn, run the following commands in a terminal to clone
the ``pymedphys`` GitHub repo and install the ``pymedphys`` package along with
its dependencies:

.. code:: bash

    git clone https://github.com/pymedphys/pymedphys.git
    cd pymedphys
    yarn bootstrap


Windows users can find detailed instructions for installing Git and Yarn in the
`Developer Guide`_.


.. _`Developer Guide`: ../developer/contributing.html
