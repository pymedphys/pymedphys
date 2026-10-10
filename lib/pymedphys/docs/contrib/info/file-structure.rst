Repository File Structure
=========================

The PyMedPhys repository has the following general structure:

.. code-block:: bash

   pymedphys/
   |   README.rst
   |   LICENSE
   |   CHANGELOG.md
   |   pyproject.toml
   |   ...
   |
   |-- lib/pymedphys/
   |   | -- docs/
   |
   |-- ...


PyMedPhys contains a series of top-level files. These include:

:``README.rst``: A text file containing general information on the PyMedPhys
                 repository with links to important sections. On `the PyMedPhys
                 GitHub page`_, ``README.rst`` determines the text you see
                 below the file structure.

:``LICENSE``: A text file that contains a full copy of the license used by
              PyMedPhys.

:``CHANGELOG.md``: A text file containing release notes for the PyMedPhys
                   source code library. ``CHANGELOG.md`` determines the text
                   presented on the :doc:`Release Notes <../../release-notes>` page.

:``pyproject.toml``: Package metadata, supported Python versions, dependencies,
                     extras, and tool configuration. Hatchling is the build
                     backend; uv manages the development environment.

:``uv.lock``: The resolved dependencies used by uv and CI. Commit lockfile
              changes together with the generated dependency files.

:``.github/workflows/``: GitHub Actions workflows; see the
                         :doc:`workflow guide <workflows>`.

:``.readthedocs.yml``: The ReadTheDocs build configuration for the published
                       documentation.

:``requirements*.txt``: Exported dependency files. Regenerate these with
                        ``uv run pymedphys dev propagate`` after changing
                        dependencies; do not edit them by hand.

You'll quickly note from a cursory look through PyMedPhys that there are
actually many more top-level files. Most of these help configure specific
tasks, such as installation & automated testing. They are probably less
critical to understand in detail in order to comprehend PyMedPhys' structure,
so we'll disregard them for now in the interest of brevity.

(Most of) the rest of PyMedPhys is arranged in the following directories:

:``lib/pymedphys/``:    The main PyMedPhys package.

:``lib/pymedphys/docs/``: Contains most of PyMedPhys' documentation. The files within
            ``docs/`` make up the text you are reading right now! A
            documentation generator called Sphinx converts the files in
            ``docs/`` into human-readable format. The same tool also pulls the
            docstrings from PyMedPhys' source code and displays them in the
            documentation pages.


.. _`the PyMedPhys GitHub page`: https://github.com/pymedphys/pymedphys
