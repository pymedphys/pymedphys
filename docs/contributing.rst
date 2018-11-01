Set up required to be able to Contribute
========================================

Assumptions
-----------

These instructions assume you are using a Windows 10 machine and that you are
able to have administrator rights on your machine.

Your mission
------------

Your mission should you chose to accept it is to complete all the tasks within
this document. But while doing so, take notes of the pain points. Write down
what feedback you have. And then, by the end, instead of you emailing that
feedback to me, I want you to use your new set up to edit this file and submit
a merge request.


GitLab Account
--------------

Make a GitLab account. Contact me@simonbiggs.net to request the required
permissions to be able to make changes to the PyMedPhys repository.

A great piece of Git documentation can be found at the following link:
https://dont-be-afraid-to-commit.readthedocs.io/en/latest/git/index.html

Use that to begin to get a feel for what Git is.


Text Editor
-----------

Visual Studio Code is a great plain text editor, I think that will be the most
helpful. As an extra benefit it also has lots of features that help with both
Python and git. https://code.visualstudio.com/

When installing Visual Studio Code make sure to tick the “Open with Code” boxes:

.. image: open_with_code.png


A Command Prompt
----------------

Cmder is a good command prompt that fills the massive gap on Windows machines.
One would think syntax highlighting, copy and paste, and window resizing would
be common place in terminals everywhere. But it appears not. Nevertheless,
cmder to the rescue:

http://cmder.net/

Once you've downloaded cmder make sure to follow the steps given at
https://github.com/cmderdev/cmder#shortcut-to-open-cmder-in-a-chosen-folder

That will make it so that you can open a terminal in any directory by right
clicking in the file browser.


Python
------

For Python head on over to https://www.anaconda.com/download/ and download and
install the latest Python 3 version available.

When installing Anaconda make sure to install it for your user only, and tick
the option “add to path”


Chocolatey
----------

Chocolatey is a package manager for Windows. It makes installed software
development tools quite a breeze. To install chocolatey follow the instructions
at https://chocolatey.org/install


Git and Git LFS
---------------

Use chocolatey within an administrator command prompt to install git and
git-lfs as so:

.. code:: bash

    choco install git git-lfs


Some useful resources
---------------------

At this point you might find some of the following resources useful:

 * https://docs.scipy.org/doc/numpy/user/numpy-for-matlab-users.html
 * http://mathesaurus.sourceforge.net/matlab-numpy.html
 * https://github.com/trekhleb/learn-python
 * https://dont-be-afraid-to-commit.readthedocs.io/en/latest/git/index.html
 * Chapter 2 of https://www.nceclusters.no/globalassets/filer/nce/diverse/the-pragmatic-programmer.pdf

The don't be afraid to commit resource will be invaluable for these next few
steps.


Authenticate your computer to be able to access your GitLab account
-------------------------------------------------------------------

Before setting your SSH keys I recommend permanently setting your HOME
variable. This can clear up some potentially confusing issues. Do this by
running

.. code:: bash

    setx HOME "C:\Users\yourusername"


Follow the instructions at the following website to create and add an SSH key
to your GitLab account:

https://docs.gitlab.com/ee/ssh/

If all has gone well you should be able to run the following without being
prompted for a password.

.. code:: bash

    git clone git@gitlab.com:pymedphys/pymedphys.git
    cd pymedphys


This will download all of PyMedPhys to your local machine.

Next is to install and set up nbstripout.

.. WARNING::

    nbstripout is used to make it so that you do not post Jupyter Notebook
    outputs online. Depending on how you use notebooks these outputs may
    contain private and/or sensitive information. Should you uninstall Python
    it may be possible that nbstripout ends up disabled. Stay prudent, and
    be extra cautious when working with sensitive information stored within
    a notebook in a git repository.

.. code:: bash

    pip install nbstripout
    nbstripout --install


Install the development version of PyMedPhys
--------------------------------------------

Begin by installing the online version of PyMedPhys so that you get all of its
dependencies with conda:

.. code:: bash

    conda config --add channels conda-forge
    conda install pymedphys
    conda uninstall pymedphys
    pip install -e .


Add yourself to our team
------------------------

.. note::

    If you've made it this far, well done!
