Directory & File Structure
==================================

The PyMedPhys Repository
------------------------

The PyMedPhys repository is generally structured as follows:

.. code-block:: bash

   pymedphys/
   |   README.md
   |   changelog.md
   |   LICENSE
   |   setup.py
   |   ...
   |
   |-- docs/
   |
   |-- notebooks/
   |
   |-- scripts/
   |
   |-- src/pymedphys/
   |
   |-- tests/
   |
   |-- ...



.. TODO: Explain further (e.g. top-level files and purpose of directories).


The PyMedPhys Source Code Package
---------------------------------

All source code for PyMedPhys is contained within ``src/pymedphys``. Within
this directory, the code is organised into a range of categories, such as
``dicom``, ``gamma``, etc. These correspond to Python modules. Finally, code
within these categories are organised into levels:

.. code-block:: bash

   pymedphys/
   |-- src/pymedphys
   |   |
   |   |-- dicom/
   |   |   |-- __init__.py
   |   |   |
   |   |   |-- _level1/
   |   |   |   |-- __init__.py
   |   |   |   |-- a_python_source_code_file.py
   |   |   |   |-- another_python_source_code_file.py
   |   |   |
   |   |   |-- _level2/
   |   |   |
   |   |   |-- _level3/
   |   |   |
   |   |   |-- _level4/
   |   |
   |   |-- gamma/
   |   |   |-- __init__.py
   |   |   |
   |   |   |-- _level1/
   |   |   |   |-- __init__.py
   |   |   |   |-- and_yet_even_more_python_code.py
   |   |   |
   |   |   |-- _level2/
   |   |   |
   |   |   |-- _level3/
   |   |   |
   |   |   |-- _level4/
   |   |
   |   |-- ...


This levelling helps to prevent a cyclical code dependency tree. PyMedPhys'
automated test suite includes a Python package called ``layer-linter`` that
helps to enforce this structure. The following sections further explain the
philosophy behind levelling dependencies.


John Lakos and Physical Design
------------------------------

The physical design of PyMedPhys is inspired by
John Lakos at Bloomberg, writer of Large-Scale C++ Software Design. He
describes this methodology in a talk he gave which is available on YouTube:

.. raw:: html

    <div style="position: relative; padding-bottom: 56.25%; height: 0; overflow: hidden; max-width: 100%; height: auto;">
        <iframe src="https://www.youtube.com/embed/QjFpKJ8Xx78?t=39m10s" frameborder="0" allowfullscreen style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;"></iframe>
    </div></br>



The aim is to have an easy to understand hierarchy of component and package
dependencies that continues to be easy to hold in ones head even when there are
a very large number of these items.

This is achieved by levelling. The idea is that in each type of aggregation
there are only three levels, and each level can only depend on the levels lower
than it. Never those higher, nor those the same level. So as such, Level 1
components or packages can only depend on external dependencies. Level 2 can
depend on Level 1 or external, and then Level3 can depend ong Level 1, Level 2,
or external.

John Lakos uses three aggregation terms, component, package, and package group.
Primarily PyMedPhys avoids object oriented programming choosing functional
methods where appropriate. However within Python, a single python file itself
can act as a module object. This module object contains public and private
functions (or methods) and largely acts like an object in the object oriented
paradime. So the physical and logical component within PyMedPhys is being
interpreted as a single `.py` file that contains a range of functions.
A set of related components are levelled and grouped together in a package,
and then the set of these packages make up the package group of PyMedPhys
itself.

He presents the following diagram:

.. image:: ../img/physical_aggregation.png

It is important that the packages themselves are levelled. See in the following
image, even though the individual components themselves form a nice dependency
tree, the packages to which those components belong end up interdepending on
one another:

.. image:: ../img/group_cycle.png

In this case, it might be able to be solved by appropriately dividing the
components up into differently structured packages:

.. image:: ../img/group_tree.png
