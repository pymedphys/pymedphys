=====================================
Windows Setup
=====================================

All contributor installation steps can be completed without administration
access. To achieve this choose "Install for my user only" when prompted.


Overview
========

* `Install Python`_ (3.7, 3.8 or 3.9)
* `Install Poetry`_
* `Install git`_
* Clone the PyMedPhys git repo

  * eg. ``git clone https://github.com/pymedphys/pymedphys.git``
* Run ``poetry install -E all`` within the root of the repo
* Run ``poetry run pre-commit install``
* `Install pandoc`_

You're good to go.

.. _`Install Python`: https://www.python.org/downloads/
.. _`Install Poetry`: https://poetry.eustace.io/docs/#installation
.. _`Install git`: https://git-scm.com/download/win
.. _`Install pandoc`: https://pandoc.org/installing.html
.. _`raising an issue`: https://github.com/pymedphys/pymedphys/issues/new

More Advanced Options
=====================

* `Setting up OpenSSH on Windows 10`_
* `Add Jupyter Kernel to Poetry`_

.. _`Setting up OpenSSH on Windows 10`: ../other/win-open-ssh.html
.. _`Add Jupyter Kernel to Poetry`: ../other/add-jupyter-kernel.html


Opinionated Recommendations
===========================

* Install `VSCode`_ as your code editor
* Install `Jupyter Lab`_ to work with Notebooks


.. _`official distribution`: https://www.python.org/downloads/
.. _`VSCode`: https://code.visualstudio.com/Download
.. _`Jupyter Lab`: https://jupyterlab.readthedocs.io/en/stable/getting_started/installation.html#pip


More details
============

Install contributor system dependencies
---------------------------------------

Python
......

Download and install **Python 3** for Windows, preferably from the
`official distribution`_.

.. warning::
    At present, although PyMedPhys works with Python 3.10, not all of its
    dependencies do. For now, we recommend installing Python 3.7, 3.8 or 3.9.

VSCode
......

Download and install `VSCode`_. Make sure to tick the "Open with Code" boxes:

.. image:: /img/open_with_code.png


Git and pandoc
..............

Use the following links to install git and pandoc.

* `Install git`_
* `Install pandoc`_

If you don't have admin access make sure to install within your user account.
When installing git it will ask you what default text editor to use. If you
don't know what ``vim`` is make sure to change the default setting from ``vim``
to VSCode (that was just installed).


Install poetry
..............

To install Poetry run the following within a command prompt:

.. code:: bash

    curl -sSL https://raw.githubusercontent.com/sdispater/poetry/master/get-poetry.py | python

What this does is detailed in the `Install Poetry`_ docs. You will need to
close and reopen your command prompt after installing Poetry.


Install the development version of PyMedPhys and pre-commit
-----------------------------------------------------------

To download a copy of the PyMedPhys repository onto your machine run:

.. code:: bash

    git clone https://github.com/pymedphys/pymedphys.git

Then change into the newly created directory by running:

.. code:: bash

    cd pymedphys

Then install PyMedPhys and set up pre-commit by running:

.. code:: bash

    poetry install -E all
    poetry run pre-commit install


Install a Jupyter Lab kernel for the development install
--------------------------------------------------------

.. code:: bash

    poetry run python -m ipykernel install --user --name pymedphys
