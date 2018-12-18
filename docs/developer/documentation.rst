Editing documentation
=====================

This documentation site uses a toolbox called Sphinx. This particular document
aims to help contributors to improve the PyMedPhys documentation.

It presumes you have gone through the base contributing documentation.

Prerequisites
-------------
To work on the documentation on your machine you will need the following extra
libraries installed:

.. code:: bash

    pip install sphinx sphinx-autobuild numpydoc sphinx_rtd_theme


Starting a live update documentation server
-------------------------------------------
Within the root pymedphys directory run the following command:

.. code:: bash

    sphinx-autobuild docs docs/_build/html

Then within a web browser go to http://127.0.0.1:8000

You may now edit the documentation within the docs directory and see the
changes live update within your browser.