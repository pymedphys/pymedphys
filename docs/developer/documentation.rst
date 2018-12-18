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


Docstring extraction
--------------------
Some documentation is best written right within a given function itself. This
type of documentation is called a docstring. However this documentation does
also need to be available on the main documentation and it is exceptionally
important that this isn't written twice. If it was written twice, as time goes
on one may go out of date, or be in consitent with the other. It is also an extra
unnecessary workload to maintain two sources of duplicated information. See
the DRY programming philosophy for more on this.

So, to solve this problem, most of the documentation is written as docstrings
and then automatically extracted into the documentation pages themselves.
To make this work docstrings need to be documented using the numpy style. See
the following sites for examples of how to conform to that style:

 - https://sphinxcontrib-napoleon.readthedocs.io/en/latest/example_numpy.html#example-numpy
 - https://numpydoc.readthedocs.io/en/latest/format.html

See examples within the documentation itself for how then to import those
functions into the docs.
