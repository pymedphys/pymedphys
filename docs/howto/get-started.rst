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

    pip install pymedphys[user]

You may need to open and close your terminal if you have only just installed
Python. The ``[user]`` option is needed to install pymedphys with its
"batteries included" so-to-speak. It will go and install a range of
dependencies which you may need during your use of pymedphys.


A minimal installation
----------------------

If you're not interested in installing PyMedPhys' dependencies you can choose
to skip the ``[user]`` option as so:

.. code:: bash

    pip install pymedphys


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

    pip install pymedphys[user]


Installing the Bleeding Edge version of PyMedPhys
=================================================

If you wish to be able to contribute to PyMedPhys itself you are going to want
to instead install PyMedPhys from the master branch on GitHub
<https://github.com/pymedphys/pymedphys>. To achieve this follow the OS
specific instructions within the contributor tutorials:

* :doc:`advanced/setup-linux`
* :doc:`advanced/setup-win`
* :doc:`advanced/setup-mac`
