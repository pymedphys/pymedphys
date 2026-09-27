================================
Documentation Guide
================================

This documentation site is built with Sphinx, MyST, and Jupyter Book 1.x. This particular
document aims to help contributors to improve the PyMedPhys
documentation.

Documentation structure and philosophy
--------------------------------------

The PyMedPhys documentation adheres to the `"Grand Unified Theory of
Documentation"
<https://documentation.divio.com/>`__ by Daniele Procida.


Building the documentation on your workstation
----------------------------------------------

Assuming you have set up your machine according to the appropriate development
guide (:doc:`../setups/setup-win`, :doc:`../setups/setup-linux`,
:doc:`../setups/setup-mac`) you can then run the following within a terminal to
build the documentation:

.. code:: bash

    uv run -- pymedphys dev docs

The build fails on Sphinx warnings and unexpected notebook execution errors.
Notebook dependencies belong in the project's ``docs`` extra; notebooks should
not install or change dependencies while building the documentation. An
install cell kept for readers who run a notebook elsewhere (for example on
Colab) must carry the ``skip-execution`` cell tag so the build never runs it.

Successful notebook executions are cached. To validate every notebook from a
fresh cache after changing dependencies, run:

.. code:: bash

    uv run -- jupyter-book clean --all lib/pymedphys/docs
    uv run -- pymedphys dev docs

Navigation is defined by the ``toctree`` directives in the index pages.
Add new pages to the relevant index so they appear in the site navigation.

The build generates ``conf.py`` from ``_config.yml``. The generated file is
ignored by git, so change ``_config.yml`` rather than ``conf.py``.


Previewing and checking the site
--------------------------------

The HTML output is in ``lib/pymedphys/docs/_build/html``. Serve it locally:

.. code-block:: bash

    uv run python -m http.server 8000 --bind 127.0.0.1 --directory lib/pymedphys/docs/_build/html

Open ``http://localhost:8000`` and inspect the pages you changed, including their
navigation, code examples, and links. Stop the server with Ctrl+C.

To produce the same external-link report as CI, run this after an HTML build:

.. code-block:: bash

    uv run python -m sphinx -b linkcheck -d lib/pymedphys/docs/_build/.doctrees lib/pymedphys/docs lib/pymedphys/docs/_build/linkcheck

Read ``output.txt`` or ``output.json`` in the linkcheck directory. A failed
request may be a rate limit, authentication requirement, or temporary outage;
verify it before replacing a link. CI reports external-link failures as
advisory, so a green summary alone does not establish that every link works.

Source files and publishing
---------------------------

Edit pages under ``lib/pymedphys/docs``. Three files are copied into that tree
by ``pymedphys dev docs --prep`` and by the normal build:

* Edit the root ``README.rst`` for the homepage's imported introduction.
* Edit the root ``CONTRIBUTING.md`` for the contributor landing page.
* Edit the root ``CHANGELOG.md`` for release notes.

Do not edit their generated copies.

GitHub Actions builds and uploads ``docs-html`` and ``docs-linkcheck``
artefacts for selected PRs. ReadTheDocs publishes the public site separately,
using ``.readthedocs.yml``. The ``latest`` site describes the development
branch; select the documentation version matching an installed release when
checking release-specific behaviour.

Writing portable links
----------------------

Use ordinary Markdown links, ``[descriptive text](destination)``, as the
standard in Markdown pages and notebook Markdown cells. GitHub, Jupyter, and
Colab do not interpret MyST roles as links.

For links between checked-in documentation pages, use a relative source path
including its extension, for example ``[Quick Start Guide](quick-start.rst)``
from another page in the same directory. This works when browsing the source,
and MyST resolves the source path to the corresponding page in the built site.
See the `MyST cross-reference documentation
<https://myst-parser.readthedocs.io/en/latest/syntax/cross-referencing.html>`_.

In notebooks that readers can download individually, use published
documentation URLs so links work without the rest of the repository. Also use
a published URL when the target is a generated page with no checked-in source
at that path, such as
``https://docs.pymedphys.com/en/latest/contrib/index.html``. Choose a release
version instead of ``latest`` when the surrounding instructions require one.

Check both the source-view destination and the built HTML after changing links.
Keep native reStructuredText cross-references such as ``:doc:`` in
reStructuredText files, and retain specialised Sphinx references when their
target requires them, for example a Python API object.

Keeping documentation current
-----------------------------

When changing code, dependencies, or CI, check the setup guides, examples, and
workflow/release instructions as well as the API docstrings. Compare commands
with the CLI's ``--help`` and dependency advice with ``pyproject.toml`` and
``uv.lock``. Re-run changed notebooks instead of relying on saved output.

Mark historical implementation write-ups and site-specific deployment examples
with their scope. Keep their original source permalinks and commands together;
substituting new tool names into old examples can make them impossible to
reproduce. Release notes and the published paper are historical records.

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
