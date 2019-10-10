Directory & File Structure
==================================

.. contents::
    :local:
    :backlinks: entry

The PyMedPhys Repository
------------------------

The PyMedPhys repository has the following general structure:

.. code-block:: bash

   pymedphys/
   |   README.rst
   |   LICENSE-AGPL-3.0-or-later
   |   LICENSE-Apache-2.0
   |   changelog.md
   |   setup.py
   |   ...
   |
   |-- docs/
   |
   |-- pymedphys/
   |
   |-- ...


Just like most Python libraries, PyMedPhys contains a series of standard,
top-level files. These include:

:``README.rst``: A text file containing general information on the PyMedPhys
                 repository with links to important sections. On `the PyMedPhys
                 GitHub page`_, ``README.rst`` determines the text you see
                 below the file structure.

:``LICENSE-AGPL-3.0-or-later``: A text file that contains a full copy of the
                                AGPL-3.0 license. Since PyMedPhys is licensed
                                under the AGPL-3.0 (with additional terms from
                                the Apache-2.0), it is included for reference.

:``LICENSE-Apache-2.0``: A text file that contains a full copy of the
                         Apache-2.0 license. Since the PyMedPhys license
                         includes terms from the Apache-2.0, it is included for
                         reference.

:``changelog.md``: A text file containing release notes for the PyMedPhys
                   source code library. ``changelog.md`` determines the text
                   presented on the `Release Notes`_ documentation page.

:``setup.py``: A Python script that facilitates easy installation of the
               PyMedPhys library as a package for users and contributors alike.

You'll quickly note from a cursory look through PyMedPhys that there are
actually many more top-level files. Most of these help configure specific
tasks, such as installation & automated testing. They are probably less
critical to understand in detail in order to comprehend PyMedPhys' structure,
so we'll disregard them for now in the interest of brevity.

(Most of) the rest of PyMedPhys is arranged in the following directories:

:``docs/``: Contains most of PyMedPhys' documentation. The files within
            ``docs/`` make up the text you are reading right now! A
            documentation generator called Sphinx converts the files in
            ``docs/`` into human-readable format. The same tool also pulls the
            docstrings from PyMedPhys' source code and displays them in the
            documentation pages.

:``pymedphys/``:    The main PyMedPhys package.


.. _`the PyMedPhys GitHub page`: https://github.com/pymedphys/pymedphys
.. _`examples`: ../user/examples/index.html
.. _`Installation`: ../getting-started/installation.html
.. _`Release Notes`: ../getting-started/changelog.html
.. _`Jupyter notebooks`: https://realpython.com/jupyter-notebook-introduction/
.. _`continuous integration`: https://en.wikipedia.org/wiki/Continuous_integration
