==================
Get Started
==================

Install Python
==============

In order to make use of the PyMedPhys library, you'll need Python installed on
your workstation. Below are some recommended instructions for installing Python
based upon your OS.

Windows 10 or 11
----------------

Open up a command prompt and type:

.. code:: bash

    python

If python isn't already installed this will open the Windows store. At this
point you can click the "Get" button. It will ask you to sign in, but you can
skip the sign in step. It will still install.

Once installed, open a new command prompt and type:

.. code:: bash

    python

You should now see a python prompt within your console. To exit the console
type:

.. code:: python

    exit()


Linux or MacOS
--------------

On Linux or MacOS we recommend not using your system Python and instead
managing your Python installation using `pyenv`_.

To achieve this first install `the python build environment`_, and then follow
the `pyenv installation`_ steps. Once pyenv is installed run the following:

.. code:: bash

    pyenv install 3.9.7
    pyenv global 3.9.7

You can choose to adjust the version number provided above to be the latest
Python version if you wish.

.. _`pyenv`: https://github.com/pyenv/pyenv/blob/master/README.md
.. _`the python build environment`: https://github.com/pyenv/pyenv/wiki#suggested-build-environment
.. _`pyenv installation`: https://github.com/pyenv/pyenv-installer#install


Installing PyMedPhys
====================

Once you have Python you can now install PyMedPhys via pip by typing the
following in a terminal or command prompt:

.. code:: bash

    pip install pymedphys[user]

This command can be copied into a command prompt on Windows with a "Right Click"
of the mouse.

You may need to open and close your terminal if you have only just installed
Python. The ``[user]`` option is needed to install pymedphys with its
"batteries included" so-to-speak. It will go and install a range of
dependencies which you may need during your use of pymedphys.

SSL Issues
----------

Depending on your network set up you may see "SSL" warnings followed by an
error message when trying to install PyMedPhys with the above command. To fix
this issue you can instead install PyMedPhys with the following command:

.. code:: bash

    pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org pymedphys[user]
