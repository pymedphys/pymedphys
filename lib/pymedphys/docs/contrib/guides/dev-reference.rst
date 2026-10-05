Developer command reference
===========================

This reference is for contributors with a source checkout set up according to
:doc:`../start/setup`. It is generated from the current command parser. Run
commands from the repository root with ``uv run pymedphys dev <command>``.
The guides below explain the preparation and observable result for each task.

Choose a task
-------------

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Command
     - Use and expected result
   * - ``tests``, ``doctests``
     - Run a selected suite; see :doc:`../validation/testing` for markers,
       opt-in flags, reports, and passing pytest options through the CLI.
   * - ``docs``
     - Build HTML, prepare sources, or check external links; see
       :doc:`../info/docs-guide` for output locations and preview checks.
   * - ``lint``
     - Run Pylint. Ruff and pre-commit have separate commands described in
       :doc:`../validation/testing`.
   * - ``imports``
     - Verify the base/extra import policy in fresh real installs. This needs
       network access; see :doc:`../info/lazy-imports`.
   * - ``propagate``
     - Regenerate dependency/version outputs from project metadata and the
       lockfile; see :doc:`make-a-change`. ``--update`` first upgrades the lock
       and synchronises the environment, so use it only for an intended upgrade.
   * - ``mssql``
     - Start or stop the local mock Mosaiq SQL Server through the repository's
       Docker Compose recipe; see :doc:`../validation/testing`. It needs Docker
       and the Compose command used by that recipe.
   * - ``deid-tables``
     - Generate or compare standard-derived de-identification tables. Follow
       :doc:`../info/deidentification-design` for the pinned sources and review
       procedure before changing tables.
   * - ``deid-matrix``
     - Render the requirements register, optionally with JUnit results. Follow
       :doc:`../info/deidentification-design` for what traceability establishes.
   * - ``tg263-check``
     - Report whether the reviewed TG-263 resource has changed. An available
       new download still needs review; see :doc:`../maintainers/project`.

Tests and doctests accept additional pytest arguments, for example a test path,
``-k``, ``-m``, ``-n``, or ``--junitxml``. These are parsed by pytest rather than
defined in the argparse reference below. The testing guide owns their meaning
and the opt-in marker flags.

Argument reference
------------------

.. argparse::
   :ref: pymedphys.cli.define_parser
   :prog: pymedphys
   :path: dev
