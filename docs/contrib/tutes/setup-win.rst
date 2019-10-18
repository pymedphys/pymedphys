=====================================
Windows Contributor Environment Setup
=====================================

.. contents::
    :local:
    :backlinks: entry


Overview
========

* Install Python 3.7
* `Install Poetry`_
* Clone the PyMedPhys git repo
* Run ``poetry install`` within the root of the repo
* Run ``poetry run pre-commit install``
* Install ``pandoc`` with `chocolatey`_

  * eg: ``choco install pandoc``

You're good to go.

.. _`Install Poetry`: https://poetry.eustace.io/docs/#installation
.. _`chocolatey`: https://chocolatey.org/install


Opinionated Recommendations
===========================

* Install Python with `Anaconda`_
* Install `VSCode`_ as your code editor
* Install `Jupyter Lab`_ to work with Notebooks


.. _`Anaconda`: https://www.anaconda.com/download
.. _`VSCode`: https://code.visualstudio.com/Download
.. _`Jupyter Lab`: https://jupyterlab.readthedocs.io/en/stable/getting_started/installation.html#pip


More details
============


Get Python & Anaconda
---------------------

Anaconda is a free, open source, optimized Python (and R) distrubution. It
includes:

- `conda <https://conda.io/docs/index.html>`__, a powerful package and
  environment management system.
- Python
- Over 100 automatically installed scientific packages (`numpy`, `scipy`, etc.)
  that have been tested to work well together, along with their dependencies.

Download the latest Anaconda Python **3** version from
`here <https://www.anaconda.com/download/>`__

When installing Anaconda make sure to install it for your user only, and tick
the option “add to path”.

.. image:: /img/add_anaconda_to_path.png

You might notice that Microsoft Visual Studio Code (VS Code) can be installed
via the Anaconda installation. However, we recommend installing VS Code from
its official install distribution as outlined below in
:ref:`text-editor-section`. The Anaconda installer does not provide the
opportunity to tick the “Open with Code” boxes detailed below.

.. _text-editor-section:

Get a text editor - VS Code
---------------------------

Microsoft's Visual Studio Code is an excellent, free, open-source code editor.
It comes with many great features for both Python and Git. You can download
the official release `here <https://code.visualstudio.com/>`__.

When installing VS Code, make sure to tick the “Open with Code” boxes:

.. image:: /img/open_with_code.png

You will need to install a few extensions in VS Code to complete your set up.
This is very easy to do via the Extensions Marketplace once VS Code is
installed. With VS Code running, access the marketplace by clicking this symbol
on the left toolbar:

.. image:: /img/vscode_extensions.png


Get a package manager - Chocolatey
------------------------------------------------------

Chocolatey is a package manager for Windows. It makes installing software
development tools quite a breeze. Follow
`these instructions <https://chocolatey.org/install>`__ to install Chocolatey.


.. _system-dependencies-section:

Install contributor system dependencies
---------------------------------------

Use Chocolatey within an administrator command prompt to install Git and pandoc

.. code:: bash

    choco install git pandoc


Configure Git and get a GitHub account
--------------------------------------

If you successfully completed the instructions in
:ref:`system-dependencies-section`, you should now have Git installed. It is
probably worth spending some time configuring Git according to your
preferences - you can find a good beginners' resource on this
`here <https://git-scm.com/book/en/v2/Getting-Started-First-Time-Git-Setup>`__.
There are lots of useful tips and tricks that can improve your Git experience.
At a minimum, we do recommend you set your username and email from within a
terminal as follows:

.. code:: bash

    git config --global user.name "Firstname Lastname"
    git config --global user.email "example@example.com"

Make a GitHub account `here <https://github.com/join>`__. Once you have an
account, you will need commit rights to this repository in order to make
contributions. Create an issue on GitHub within the PyMedPhys repository
`here <https://github.com/pymedphys/pymedphys/issues/new/>`__
and include "request for commit rights" or similar in your issue's content,
along with "@SimonBiggs" and "@Matthew-Jennings" to ensure it is seen!

Whenever you wish to discuss anything about PyMedPhys, please create an issue
on GitHub. It can be to ask for help, suggest a change, provide feedback, or
anything else regarding PyMedPhys. Write "@" followed by someone's username if
you would like to talk to someone specifically.

The real power of GitHub comes from Git itself. A great piece of Git
documentation can be found
`here <https://dont-be-afraid-to-commit.readthedocs.io/en/latest/git/index.html>`__.
Use this documentation to begin to get a feel for what Git is.


Peruse some useful resources
----------------------------

At this point you might find some of the following resources useful:

 * `Numpy for Matlab users (Scipy.org) <https://docs.scipy.org/doc/numpy/user/numpy-for-matlab-users.html>`__.
 * `NumPy for MATLAB users (Mathesaurus) <http://mathesaurus.sourceforge.net/matlab-numpy.html>`__.
 * `Playground and cheatsheet for learning Python <https://github.com/trekhleb/learn-python>`__.
 * `Don't be afraid to commit: Git and GitHub <https://dont-be-afraid-to-commit.readthedocs.io/en/latest/git/index.html>`__.
 * Chapter 2 of `The Pragmatic Programmer <https://www.nceclusters.no/globalassets/filer/nce/diverse/the-pragmatic-programmer.pdf>`__.

The "Don't be afraid to commit" resource will be invaluable for these next few
steps.


Authenticate your computer to be able to access your GitHub account
-------------------------------------------------------------------

Follow `these instructions <https://help.github.com/articles/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent/>`__
to create and add an SSH key to your GitHub account.

If all has gone well you should be able to run the following without being
prompted for a password.

.. code:: bash

    git clone git@github.com:pymedphys/pymedphys.git
    cd pymedphys

This will download all of PyMedPhys to your local machine.

If you find that you cannot connect to GitHub via SSH (possibly due to
IT restrictions at your institution), you can also clone via HTTPS as follows:

.. code:: bash

    git clone https://github.com/pymedphys/pymedphys.git


Install poetry
--------------

Within a command prompt run according to the instruction at <https://poetry.eustace.io/docs/#installation>:

.. code:: bash

    curl -sSL https://raw.githubusercontent.com/sdispater/poetry/master/get-poetry.py | python


Install the development version of PyMedPhys and pre-commit
-----------------------------------------------------------

Run the following within the root of PyMedPhys

.. code:: bash

    poetry install
    poetry run pre-commit install
