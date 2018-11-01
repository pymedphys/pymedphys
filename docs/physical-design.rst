Physical File Structure and Design
==================================

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

.. image:: img/physical_aggregation.png

It is important that the packages themselves are levelled. See in the following
image, even though the individual components themselves form a nice dependency
tree, the packages to which those components belong end up interdepending on
one another:

.. image:: img/group_cycle.png

In this case, it might be able to be solved by appropriately dividing the
components up into differently structured packages:

.. image:: img/group_tree.png


The Layout of PyMedPhys
-----------------------

All source code for PyMedPhys is contained within `src/pymedphys`. Packages
are levelled and placed with respect to their dependency level by directory
name. The packages within _pack1 only depend on external packages, packages
within _pack2 only depend on _pack1 or external, and so on.

Inside each package, the component files are split up into directories by
level1, level2, level3. Once again level1 can only depend on either an external
dependency or a lower package. Those within level2 can depend on lower
pacakges, external dependencies, or level1, and so on.

So that the api to PyMedPhys doesn't vary with the physical structure of the
dependencies, each package is imported out to be directly accessable within
the top namespace of `src/pymedphys`.
