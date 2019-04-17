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

:``README.rst``: A text file containing general information on the PyMedPhys
                 repository with links to important sections. On `the PyMedPhys
                 GitHub page`_, *README.rst* determines the text you see below
                 the file structure.

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
                     in ``changelog.md``. See :ref:`source-code` section below
                     for further details, especially on structure.

:``tests/``: Contains the PyMedPhys suite of automated tests. Any code present
             in *src/pymedphys/* should be covered by tests in this directory.
             Automated testing is essential for effective `continuous
             integration`_, which is a core development philosophy of
             PyMedPhys. If you would like to make meaningful contributions to
             PyMedPhys - and become a much better developer as a result - it
             pays to get very familiar with automated testing and the code
             within this directory.


.. _`the PyMedPhys GitHub page`: https://github.com/pymedphys/pymedphys
.. _`Release Notes`: ../getting-started/changelog.html
.. _`Jupyter notebooks`: https://realpython.com/jupyter-notebook-introduction/
.. _`continuous integration`: https://en.wikipedia.org/wiki/Continuous_integration


.. _source-code:

The PyMedPhys Source Code Package
---------------------------------

All library source code for PyMedPhys is contained within ``src/pymedphys``.
Within this directory, the code is organised into a range of categories, such
as ``dicom``, ``gamma``, etc. These correspond to Python modules. Finally, code
within these categories is organised into levels. Levelling the source code
helps to prevent circular code dependencies. See diagram below:

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
   |   |   |   |-- d1a.py
   |   |   |   |-- d1b.py
   |   |   |
   |   |   |-- _level2/
   |   |   |   |-- __init__.py
   |   |   |   |-- d2a.py
   |   |   |   |-- d2b.py
   |   |   |
   |   |   |-- _level3/
   |   |   |   |-- __init__.py
   |   |   |   |-- d3a.py
   |   |   |
   |   |   |-- _level4/
   |   |   |   |-- __init__.py
   |   |   |   |-- d4a.py
   |   |
   |   |-- gamma/
   |   |   |-- __init__.py
   |   |   |
   |   |   |-- _level1/
   |   |   |   |-- __init__.py
   |   |   |   |-- g1a.py
   |   |   |
   |   |   |-- _level2/
   |   |   |   |-- __init__.py
   |   |   |   |-- g2a.py
   |   |   |   |-- g2b.py
   |   |   |   |-- g2c.py
   |   |   |
   |   |   |-- _level3/
   |   |   |   |-- __init__.py
   |   |   |   |-- g3a.py
   |   |   |
   |   |   |-- _level4/
   |   |   |   |-- __init__.py
   |   |   |   |-- g4a.py
   |   |
   |   |-- ...
   |   
   |-- ...

For the most part, the many ``__init__.py`` files just tell Python to treat
directories containing the files as *packages*. They form part of how
PyMedPhys' code is brought together as an installable package or library whose
modules can be imported.

Python files within the source code should have descriptive names indicating
the functions of the code within them. For example, ``dose.py`` in level 1 of
``dicom`` is so-named because it contains code that interacts with DICOM RT
Dose files. However, in order to illustrate how levelling works in PyMedPhys,
the files in the above diagram have been named according to their level and
module like so:

``<first-letter-of-module><level number><letter-to-differentiate-files-in-the-same-module-and-level>``

E.g. ``g2a.py`` is the first file in level 2 of the ``gamma`` module in the
above diagram.

The key to levelling is this: **The code contained in files of a particular
level should only depend on code in files of lower-numbered levels. Code should
never depend on code within files of the same level, nor of higher-numbered
levels.**

Note that, in practice, *"depend on"* really means *"import code from"* using
Python's ``import`` statement. 

In our example, ``g2a.py`` is in level 2, so code in ``g2a.py`` can import code
from ``g1a.py``, because ``g1a.py`` is in level 1 (a lower-numbered level). In
contrast, code in ``g2a.py`` *cannot* import code from ``g2b.py`` (which is in
the same level), ``g3a.py`` or ``g4a.py`` (which are in higher-numbered
levels).

*This philosophy applies for modules themselves as well.* Each module has an
assigned level. The level for a module is flexible and can be adjusted as
need be. To find out what level a module is currently see the file 
``layers.yml``. Higher level modules can import from lower level modules,
but same level modules cannot import from each other and lower cannot import
from higher. For example at the time of writing ``dicom`` is a level 2 module,
and ``gamma`` is a ``level 3`` module. This means that any file within 
``gamma`` such as ``g1a.py`` is free to import from any file within ``dicom``
such as ``d4a.py``, but no file within ``dicom`` is allowed to import from any
file in ``gamma``.

We are able to programatically check for any improper file levelling.
PyMedPhys' automated test suite includes a Python package called
``layer-linter``, which does just that!

For a further, in-depth explanation of the philosophy behind levelling
dependencies, see the :ref:`john-lakos` section.

.. _john-lakos:

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
