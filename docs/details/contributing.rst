Set up required to be able to Contribute
========================================

Assumptions
-----------

These instructions assume you are using a Windows machine and that you are
able to have administrator rights on your machine. Although this document
is tailored to Windows users PyMedPhys itself works
on all three of Windows, Mac, and Linux.

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

.. image:: ../img/open_with_code.png


A Command Prompt
----------------

Cmder is a good command prompt that fills the massive gap on Windows machines.
One would think syntax highlighting, copy and paste, and window resizing would
be common place in terminals everywhere. But it appears not. Nevertheless,
cmder to the rescue. Install the full version of cmder to also get some extra
tools that will help us later:

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
to your GitLab account. You already have ssh built into cmder, so you can skip
the first steps of that tutorial.

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


Update this document
--------------------

.. note::

    If you've made it this far, well done!

Now that you've got this far, you have a copy of the code on your machine.

First things first is to make a branch. If you don't know what that is, head on
back over to https://dont-be-afraid-to-commit.readthedocs.io/en/latest/git/index.html
and scrub up on your terminology.

To make a branch you need to have cmder open and run the following:

.. code:: bash

    git checkout -b edit-contributing-document

Once you've run that you are now free to make some changes.

Right click on the top level pymedphys directory, and press
"Open with Code". This document that you're reading is located at
`docs/contributing.rst`. Use Visual Studio Code to navigate to that file up and
begin making your changes.

Once your changes are complete reopen your cmder and run:

.. code:: bash

    git add -A
    git commit -m "my first commit"
    git push --set-upstream origin edit-contributing-document

Now, you have successfully sent your branch online.

Now you need to open a merge request. Travel on over to:

https://gitlab.com/pymedphys/pymedphys/merge_requests/new

And select the source branch to be `pymedphys/edit-contributing-document`
and set the target branch to be `pymedphys/master`.

At that point I'll get notified and we can begin discussing the changes
you've made.

Thank you! Welcome to the team!
