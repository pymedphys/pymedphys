Directory & File Structure
==================================

The PyMedPhys Repository
------------------------

The PyMedPhys repository has the following general structure:

.. code-block:: bash

   pymedphys/
   |   README.rst
   |   LICENSE
   |   Apache-2.0
   |   changelog.md
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


Just like most Python libraries, PyMedPhys contains a series of standard, 
top-level files. These include:

:``README.rst``: A simple text file containing general information on the
                 PyMedPhys repository with links to important sections. On 
                 `the PyMedPhys GitHub page`_, *README.rst* determines the text
                 you see below the file structure.

:``LICENSE``: A text file that contains a full copy of the AGPL-3.0 license.
              Since PyMedPhys is licensed under the AGPL-3.0 (with additional
              terms from the Apache-2.0), it is included for reference.

:``Apache-2.0``: A text file that contains a full copy of the Apache-2.0
                 license. Since the PyMedPhys license includes terms from the
                 Apache-2.0, it is included for reference.

:``changelog.md``: A text file containing release notes for the PyMedPhys
                   source code library. *changelog.md* determines the text
                   presented on the `Release Notes`_ documentation page.

:``setup.py``: A Python script that facilitates easy installation of the
               PyMedPhys library as a package for users and contributors alike.

You'll quickly note from a cursory look through PyMedPhys that there are
actually many more top-level files. Most of these help configure specific
tasks, such as automated testing. They are probably less critical and have been
omitted from this page in the interest of brevity.

(Most of) the rest of PyMedPhys is arranged in the following directories:

:``docs/``: Contains most of PyMedPhys' documentation. The files within *docs/*
            make up the text you are reading right now! A documentation
            generator called Sphinx converts the files in *docs/* into
            human-readable format. The same tool also pulls the docstrings from
            PyMedPhys' source code and displays them in the documentation
            pages.

:``notebooks/``: Contains a series of experimental `Jupyter notebooks`_.
                 Jupyter notebooks provide a highly convenient way to
                 experiment with code. Some PyMedPhys contributors prefer to
                 code in Jupyter notebooks to zero in on a solution before
                 attempting to add code to the PyMedPhys library. *notebooks/*
                 is a convenient place to store these experimental notebooks,
                 permitting both remote and collaborative raw development. 

:``scripts/``: Contains (or will contain) various scripts ready-made to run and
               perform simple tasks.

:``src/pympedhys/``: Contains the PyMedPhys source code library or *package*.
                     Code within this constitutes "PyMedPhys proper". In theory
                     (though not yet in practice), this code has been tested
                     and documented. Changes to code in this folder are tracked
                     in ``changelog.md``. See
                     `The PyMedPhys Source Code Package`_ section below for
                     further details, especially structure.

:``tests/``: Contains the PyMedPhys suite of automated tests. Any code present
             in *src/pymedphys/* should be covered by tests in this directory.
             Automated testing is essential for effective `continuous
             integration`_, which is a core development philosophy of
             PyMedPhys. If you would like to make meaningful contributions to
             PyMedPhys - and become a much better developer as a result - it
             pays to get very familiar with automated testing and the code
             within this directory.


.. _`the PyMedPhys GitHub page`: https://github.com/pymedphys/pymedphys
.. _`Release Notes`: /getting-started/changelog.html
.. _`Jupyter notebooks`: https://realpython.com/jupyter-notebook-introduction/
.. _`The PyMedPhys Source Code Package`: /developer/file-structure.html#id1
.. _`continuous integration`: https://en.wikipedia.org/wiki/Continuous_integration

The PyMedPhys Source Code Package
---------------------------------

All library source code for PyMedPhys is contained within ``src/pymedphys``.
Within this directory, the code is organised into a range of categories, such
as ``dicom``, ``gamma``, etc. These correspond to Python modules. Finally, code
within these categories is organised into levels:

.. code-block:: bash

   pymedphys/
   |
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
   |   
   |-- ...


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
