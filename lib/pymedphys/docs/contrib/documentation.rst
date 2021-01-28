Writing documentation
=====================

This documentation site uses a toolbox called Sphinx. This particular
document aims to help contributors to improve the PyMedPhys
documentation.

Documentation structure and philosophy
--------------------------------------

The PyMedPhys documentation adheres to the `"Grand Unified Theory of
Documentation"
<https://documentation.divio.com/>`__ by Daniele Procida.


Starting a live update documentation server
-------------------------------------------

Assuming you have set up your machine according to the appropriate development
guide (:doc:`setups/setup-win`, :doc:`setups/setup-linux`,
:doc:`setups/setup-mac`) you can then run the following within a terminal to
build the documentation:

.. code:: bash

    poetry run pymedphys dev docs

.. note::

    On Windows to build the documentation you currently need to be using
    Python 3.7. To track the requirements for building the documentation on
    Windows see
    <https://jupyterbook.org/advanced/advanced.html#working-on-windows>

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
- `NumPyDoc docstring guide
  <https://numpydoc.readthedocs.io/en/latest/format.html>`__

See existing examples within PyMedPhys for how to include new function
docstrings into the main PyMedPhys documentation.
