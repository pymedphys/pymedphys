Set up required to be able to Contribute
========================================

Assumptions
-----------

These instructions assume you are using a Windows 10 machine and that you are
able to have administrator rights on your machine.


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
 * https://github.com/trekhleb/learn-python
 * https://dont-be-afraid-to-commit.readthedocs.io/en/latest/git/index.html

The don't be afraid to commit resource will be invaluable for these next few
steps.


Authenticate your computer to be able to access your GitLab account
-------------------------------------------------------------------

Follow the instructions at the following website to create and add an SSH key
to your GitLab account:

https://docs.gitlab.com/ee/ssh/





