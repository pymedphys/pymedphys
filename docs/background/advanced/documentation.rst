Writing documentation
=====================

.. contents::
    :local:
    :backlinks: entry

This documentation site uses a toolbox called Sphinx. This particular
document aims to help contributors to improve the PyMedPhys
documentation.

Starting a live update documentation server
-------------------------------------------
Within the root pymedphys directory run the following command:

.. code:: bash

    poetry run sphinx-autobuild -W -p 7070 docs docs/_build/html

Then within a web browser go to http://127.0.0.1:7070

You may now edit the documentation within the docs directory and see the
changes live update within your browser.


Docstring extraction
--------------------

Some documentation is best written right within a given function itself.
This type of documentation is called a **docstring**. However, this
documentation should also be available in the main documentation and it
is exceptionally important that this isn't written more than once.
Duplicating documentation increases `software entropy
<https://en.wikipedia.org/wiki/Software_entropy>`__. As time goes by,
documentation updates may result in one or more copies being missed and
becoming obsolete or inconsistent with the up-to-date copy. Even if all
copies are updated correctly, unnecessary duplication adds to ongoing
maintenance requirements. See the `DRY programming philosophy
<https://en.wikipedia.org/wiki/Don%27t_repeat_yourself>`__ for more on
this.

To solve this problem, most of PyMedPhys' documentation is written as
docstrings, which are then automatically extracted into the main
documentation pages. For this to work properly, docstrings need to be
formatted according to the numpy style. See the following sites for
examples of how to conform to that style:

- `Napoleon Docs - Example NumPy Style Python Docstrings
  <https://sphinxcontrib-napoleon.readthedocs.io/en/latest/example_numpy.html#example-numpy>`__
- `numpydoc docstring guide
  <https://numpydoc.readthedocs.io/en/latest/format.html>`__

See existing examples within PyMedPhys for how to include new function
docstrings into the main PyMedPhys documentation.
