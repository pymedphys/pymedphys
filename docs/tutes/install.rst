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
================================

Primary library optional dependencies
-------------------------------------

PyMedPhys has a range of optional dependencies. If while using PyMedPhys as
installed above you get ``ImportErrors`` you may install the primary optional
dependencies for the main library by typing the following:

.. code:: bash

    pip install pymedphys[library]


Labs optional dependencies
--------------------------

If you would like to use some of the experimental libraries within the labs
section of PyMedPhys then running the following will install the optional
dependencies needed by modules within the labs:

.. code:: bash

    pip install pymedphys[labs]


Difficult optional dependencies
-------------------------------

There are two optional dependencies which have some extra complications when
installing. ``shapely`` can be difficult to install on Windows, and ``pymssql``
can be difficult to install on MacOS.


``shapely`` for ``pymedphys.electronfactors`` module
****************************************************

If you wish to use the ``pymedphys.electronfactors`` module you will need to
install ``shapely`` which on MacOS or Linux is as simple as:

.. code:: bash

    pip install shapely


On Windows however you will need to download and install a wheel from the
following site -- <https://www.lfd.uci.edu/~gohlke/pythonlibs/#shapely>.


``pymssql`` for ``pymedphys.mosaiq`` module
*******************************************

If you wish to use the ``pymedphys.mosaiq`` module then you will need to
install a version of ``pymssql`` that is < 3. On Windows and Linux this is
achieved by running:

.. code:: bash

    pip install pymssql<3

On MacOS installing this dependency is a little more involved and can be
achieved by first installing both ``freetds`` via ``homebrew`` and ``Cython``.
To do this follow the steps below:

To install homebrew (as described at <https://brew.sh/>):

.. code:: bash

    /usr/bin/ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"

Then to install ``freetds`` open a new shell, then run:

.. code:: bash

    brew install freetds

And lastly to install cython run:

.. code:: bash

    pip install cython

Then you will be able to successfully run:

.. code:: bash

    pip install pymssql<3


Installing the Bleeding Edge version of PyMedPhys
=================================================

If you wish to be able to contribute to PyMedPhys itself you are going to want
to instead install PyMedPhys from the master branch on GitHub
<https://github.com/pymedphys/pymedphys>. To achieve this follow the OS
specific instructions within the contributor tutorials:

* :doc:`../contrib/tutes/setup-linux`
* :doc:`../contrib/tutes/setup-win`
* :doc:`../contrib/tutes/setup-mac`
