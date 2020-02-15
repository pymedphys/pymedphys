==================
How to get started
==================

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


A minimal installation
----------------------

The greater majority of PyMedPhys' dependencies are actually optional. They are
only installed for simplicity for new users. You may however choose to install
PyMedPhys without these dependencies by running:

.. code:: bash

    pip install pymedphys --no-deps


Installation on MacOS
---------------------

One of PyMedPhys' dependencies is ``pymssql``. Before installing PyMedPhys on
MacOS you need first install both ``freetds`` via ``homebrew`` and ``Cython``.
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

    pip install pymedphys


Installing the Bleeding Edge version of PyMedPhys
=================================================

If you wish to be able to contribute to PyMedPhys itself you are going to want
to instead install PyMedPhys from the master branch on GitHub
<https://github.com/pymedphys/pymedphys>. To achieve this follow the OS
specific instructions within the contributor tutorials:

* :doc:`../contrib/tutes/setup-linux`
* :doc:`../contrib/tutes/setup-win`
* :doc:`../contrib/tutes/setup-mac`
