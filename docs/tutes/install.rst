======================
PyMedPhys Installation
======================

.. contents::
    :local:
    :backlinks: entry


Install Python
==============

In order to make use of the PyMedPhys library, you'll need Python installed on
your workstation. On Windows we recommend that you install the
Anaconda Python distribution. Download the latest Anaconda **Python 3** (not 2)
version from `here <https://www.anaconda.com/download/>`__.

.. note::

    When installing Anaconda make sure to install it for your user only, and
    tick the option "add to path".

.. image:: ../img/add_anaconda_to_path.png

On Linux or MacOS we recommend not using your system Python and instead
managing your Python installation using something like `pyenv`_.

.. _`pyenv`: https://github.com/pyenv/pyenv-installer#install


Installing PyMedPhys
====================

Once you have Python you can now install PyMedPhys via pip by typing the
following in a terminal or command prompt:

.. code:: bash

    pip install pymedphys

You may need to open and close your terminal if you have only just installed
Python.

Installing optional dependencies
--------------------------------

PyMedPhys has a range of optional dependencies. If while using PyMedPhys as
installed above you get ``ImportErrors`` you may install all optional
dependencies by typing the following:

.. code:: bash

    pip install pymedphys[library]


If you would like to use some of the experimental libraries within the labs
section of PyMedPhys then running the following will install all those optional
dependencies:

.. code:: bash

    pip install pymedphys[labs]


If you need either ``shapely`` (for the ``pymedphys.electronfactors`` module)
or ``pymssql`` (for the ``pymedphys.mosaiq`` module) you can either install
those packages directly yourself using the following methods:

- ``shapely`` -- <https://github.com/Toblerity/Shapely#installing-shapely-16>
- ``pymssql`` -- ``pip install pymssql<3`` -- <https://pymssql.readthedocs.io/en/stable/intro.html#getting-started>

or you can try running:

.. code:: bash

    pip install pymedphys[difficult]


Installing the Bleeding Edge version of PyMedPhys
=================================================

If you wish to be able to contribute to PyMedPhys itself you are going to want
to instead install PyMedPhys from the master branch on GitHub
<https://github.com/pymedphys/pymedphys>. To achieve this follow the OS
specific instructions within the contributor tutorials:

* :doc:`../contrib/tutes/setup-linux`
* :doc:`../contrib/tutes/setup-win`
* :doc:`../contrib/tutes/setup-mac`
