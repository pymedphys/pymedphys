.. raw:: html

   <!-- markdownlint-disable MD024 MD039 -->

Release Notes
=============

All notable changes to this project will be documented in this file.

This project adheres to `Semantic
Versioning <https://semver.org/spec/v2.0.0.html>`__.

`0.33.0 <https://github.com/pymedphys/pymedphys/compare/v0.32.0...v0.33.0>`__
-----------------------------------------------------------------------------

“Stable” API changes
~~~~~~~~~~~~~~~~~~~~

(Won’t truly be stable until after a 1.0.0 release)

Installation changes
^^^^^^^^^^^^^^^^^^^^

-  To install pymedphys with all of its user dependencies now the
   following needs to be run:

.. code:: bash

   pip install pymedphys[user]

-  When ``pip install pymedphys`` is called, PyMedPhys will now be
   installed with minimal/no dependencies.

   -  Pull request
      `#1036 <https://github.com/pymedphys/pymedphys/pull/1036>`__

Beta API changes
~~~~~~~~~~~~~~~~

Nil

Experimental API changes
~~~~~~~~~~~~~~~~~~~~~~~~

Breaking changes
^^^^^^^^^^^^^^^^

-  Removed a range of unmaintained experimental package APIs; film,
   collimation, sinogram, and Profile. The underlying code has not been
   removed, but they are no longer exposed through the APIs.

Bug fixes
^^^^^^^^^

-  Made it so that ``import pymedphys.experimental`` does not raise an
   ``ImportError`` when an optional dependency has not been installed.

   -  Issue
      `#1035 <https://github.com/pymedphys/pymedphys/issues/1035>`__
   -  Pull request
      `#1036 <https://github.com/pymedphys/pymedphys/pull/1036>`__

-  Fixed a bug where pseudonymisation wouldn’t work when in cases of
   identifying sequences.

   -  Issue
      `#1034 <https://github.com/pymedphys/pymedphys/issues/1034>`__
   -  Pull request
      `#1038 <https://github.com/pymedphys/pymedphys/pull/1038>`__

New Features
^^^^^^^^^^^^

-  Created a Mosaiq QCL dashboard that reads the QCLs from multiple
   Mosaiq installs across multiple sites.
   `\_gui/streamlit/dashboard.py#L20-L78 <https://github.com/pymedphys/pymedphys/blob/d0dbaf3d8ac15690602e3c92ab19704d450dad5a/pymedphys/_gui/streamlit/dashboard.py#L20-L78>`__

Internal Changes
~~~~~~~~~~~~~~~~

-  Made it so that when developing streamlit apps an autoreload function
   can be used to have the streamlit app update on dependency changes.
   `\_streamlit/rerun.py#L89-L96 <https://github.com/pymedphys/pymedphys/blob/d0dbaf3d8ac15690602e3c92ab19704d450dad5a/pymedphys/_streamlit/rerun.py#L89-L96>`__

   -  See discussion over on `streamlit’s issue
      tracker <https://github.com/streamlit/streamlit/issues/653#issuecomment-678954708>`__

-  Internal Mosaiq connection function now accepts custom functions for
   prompting the user for their database username, password, and
   prompting the user with responses.
   `\_mosaiq/connect.py#L134-L147 <https://github.com/pymedphys/pymedphys/blob/d0dbaf3d8ac15690602e3c92ab19704d450dad5a/pymedphys/_mosaiq/connect.py#L134-L147>`__

   -  This was utilised for connecting to a fresh database within
      streamlit.
      `\_streamlit/mosaiq.py#L20-L50 <https://github.com/pymedphys/pymedphys/blob/d0dbaf3d8ac15690602e3c92ab19704d450dad5a/pymedphys/_streamlit/mosaiq.py#L20-L50>`__

-  Created tool to manage ``pyproject.toml`` extras.
   `scripts/propagate-extras.py#L26-L51 <https://github.com/pymedphys/pymedphys/blob/d0dbaf3d8ac15690602e3c92ab19704d450dad5a/scripts/propagate-extras.py#L26-L51>`__

   -  See discussion on the poetry `issue
      tracker <https://github.com/python-poetry/poetry/issues/1644#issuecomment-688256688>`__
      for more details.

.. _section-1:

`0.32.0 <https://github.com/pymedphys/pymedphys/compare/v0.31.0...v0.32.0>`__
-----------------------------------------------------------------------------

.. _stable-api-changes-1:

“Stable” API changes
~~~~~~~~~~~~~~~~~~~~

.. _bug-fixes-1:

Bug fixes
^^^^^^^^^

-  Fixed bug in the PyMedPhys trf decoding logic where leaf pairs 77,
   78, 79, and 80 on the Y2 bank were decoded into having the wrong
   sign.

   -  See issue
      `#968 <https://github.com/pymedphys/pymedphys/issues/968>`__ and
      pull request
      `#970 <https://github.com/pymedphys/pymedphys/pull/970>`__ for
      more details.

.. _breaking-changes-1:

Breaking changes
^^^^^^^^^^^^^^^^

-  ``config.toml`` has undergone a few breaking changes.

   -  See `the
      example <https://github.com/pymedphys/pymedphys/blob/1241924d027163fccdc95750db0c984805bb83d4/site-specific/cancer-care-associates/config.toml>`__
      for a working config file.
   -  See below for a comparison highlighting the key differences.

.. code:: toml

   # Previous version
   [[site]]
   name = "rccc"
   escan_directory = '\\pdc\Shared\Scanned Documents\RT\PhysChecks\Logfile PDFs'

       [[site.linac]]
       name = "2619"
       icom_live_directory = '\\rccc-physicssvr\iComLogFiles\live\192.168.100.200'


   # New version
   [[site]]
   name = "rccc"

       [site.export-directories]
       escan = '\\pdc\Shared\Scanned Documents\RT\PhysChecks\Logfile PDFs'
       anonymised_monaco = 'S:\DataExchange\anonymised-monaco'
       icom_live = '\\rccc-physicssvr\iComLogFiles\live'

       [[site.linac]]
       name = "2619"
       ip = '192.168.100.200'

.. _new-features-1:

New Features
^^^^^^^^^^^^

-  Two new optional keywords were added to
   ``pymedphys.dicom.anonymise``. These are ``replacement_strategy`` and
   ``identifying_keywords``. This was designed to support alternative
   anonymisation methods. The API to the anonymise function is being
   flagged for a rework and simplification for which a breaking change
   is likely to occur in the near future.
-  Added ability to configure logging via ``config.toml``.

Data file changes
^^^^^^^^^^^^^^^^^

Refers to the data files accessible via ``pymedphys.data_path``,
``pymedphys.zip_data_paths``, and ``pymedphys.zenodo_data_paths``.

-  The data file ``pinnacle_test_data_no_image.zip`` was removed and its
   contents were moved into ``pinnacle_test_data.zip``.
-  Data files ``treatment-record-anonymisation.zip``,
   ``negative-mu-density.trf``, and ``trf-references-and-baselines.zip``
   were added.

.. _beta-api-changes-1:

Beta API changes
~~~~~~~~~~~~~~~~

Nil

.. _experimental-api-changes-1:

Experimental API changes
~~~~~~~~~~~~~~~~~~~~~~~~

.. _new-features-2:

New Features
^^^^^^^^^^^^

-  Added pseudonymisation as an experimental extension of anonymise.

   -  This API is undergoing refinement, however in its current form it
      is accessible via
      ``pymedphys.experimental.pseudonymisation.pseudonymisation_dispatch``
      and
      ``pymedphys.experimental.pseudonymisation.get_default_pseudonymisation_keywords``.
      These are designed to be passed to the new keywords
      ``replacement_strategy`` and ``identifying_keywords`` within
      ``pymedphys.dicom.anonymise``.
   -  The pseudonymisation strategy uses SHA3_256 hashing for text and
      UIDs, date shifting for dates, and jittering for Age. The intent
      is to enable sets of data that are correlated to remain
      correlated, and to prevent uncorrelated patient/study/series from
      clashing.

-  Added experimental pseudonymisation CLI. Callable via
   ``pymedphys experimental dicom anonymise --pseudo path/to/dicom.dcm``

-  Added ``pymedphys experimental gui``. This is a testing ground for
   new GUIs that are intended to appear within ``pymedphys gui`` in the
   future. The GUIs exposed under this experimental scope are minimally
   tested.

   -  At this point in time, the new GUIs include a GUI index, an
      electron insert factor prediction tool, and a Monaco anonymisation
      tool.

.. _bug-fixes-2:

Bug Fixes
^^^^^^^^^

-  Pinnacle Export Tool now allows for the trial to be set using the
   CLI. See issue
   `#973 <https://github.com/pymedphys/pymedphys/issues/973>`__ and pull
   request `#995 <https://github.com/pymedphys/pymedphys/pull/995>`__
   for more details.
-  Fixed bug where the dose grid in the Pinnacle Export Tool was only
   correct when patients were in HFS. See
   `#929 <https://github.com/pymedphys/pymedphys/pull/929>`__ for more
   details.

.. _section-2:

`0.31.0 <https://github.com/pymedphys/pymedphys/compare/v0.30.0...v0.31.0>`__
-----------------------------------------------------------------------------

.. _stable-api-changes-2:

“Stable” API changes
~~~~~~~~~~~~~~~~~~~~

Critical bug fixes
^^^^^^^^^^^^^^^^^^

-  Fixed bug where ``pymedphys dicom anonymise`` and
   ``pymedphys.dicom.anonymise`` would not anonymise nested tags. Thanks
   `sjswerdloff <https://github.com/sjswerdloff>`__ for finding and
   fixing `#920 <https://github.com/pymedphys/pymedphys/pull/920>`__.

.. _breaking-changes-2:

Breaking changes
^^^^^^^^^^^^^^^^

-  Removed the ``--publish`` option from CLI ``pymedphys dev docs``.
-  Moved ``pymedphys logfile orchestration`` to
   ``pymedphys trf orchestrate``

.. _new-features-3:

New features
^^^^^^^^^^^^

-  ``pymedphys.zenodo_data_paths`` has a new optional parameter
   ``filenames`` that can be used to only download some files.
-  ``pymedphys.data_path`` has a new optional parameter
   ``hash_filepath`` which can be used to provide a custom hash record.
-  Added usage warning to the MU Density GUI.

Deprecations
^^^^^^^^^^^^

-  ``pymedphys.read_trf`` has been replaced with ``pymedphys.trf.read``.
   The old API is still available, but will be removed in a future
   version.

.. _bug-fixes-3:

Bug fixes
^^^^^^^^^

-  Cache data downloads now also retry when a ``ConnectionResetError``
   occurs.

.. _beta-api-changes-2:

Beta API changes
~~~~~~~~~~~~~~~~

.. _new-features-4:

New features
^^^^^^^^^^^^

-  A new ``pymedphys.beta`` module created. This is intended to allow a
   section of the API to be exposed and iterated on but having breaking
   changes not induce a major version bump (when PyMedPhys goes to
   ``v1.0.0+``)
-  Added ``pymedphys.beta.trf.identify`` to allow the usage of Mosaiq to
   identify a trf logfile.

.. _experimental-api-changes-2:

Experimental API changes
~~~~~~~~~~~~~~~~~~~~~~~~

.. _breaking-changes-3:

Breaking changes
^^^^^^^^^^^^^^^^

-  Instances of ``labs`` has been changed to ``experimental``. This
   affects all imports from the labs and the CLI usage.

.. _bug-fixes-4:

Bug fixes
^^^^^^^^^

-  Fixed issue with Pinnacle Export Tool crashing when an image is
   missing from the archive.

.. _section-3:

`0.30.0 <https://github.com/pymedphys/pymedphys/compare/v0.29.1...v0.30.0>`__
-----------------------------------------------------------------------------

.. _breaking-changes-4:

Breaking changes
~~~~~~~~~~~~~~~~

-  Removed the proof of concept ``pymedphys bundle`` CLI as well all of
   its associated code.
-  Removed a range of unused files from the ``pymedphys.data_path`` API.
-  The previous install options ``pip install pymedphys[pytest]`` and
   ``pip install pymedphys[pylint]`` have been removed and replaced with
   ``pip install pymedphys[tests]``.

.. _new-features-5:

New Features
~~~~~~~~~~~~

-  Added a new toolbox for retrieving PTW Quickcheck measurement data
   and write it to a csv file.
   ``pymedphys labs quickcheck to-csv your.quickcheck.ip path/to/output.csv``

   -  See
      `labs/quickcheck/qcheck.py <https://github.com/pymedphys/pymedphys/blob/2d5148e2eabce3a6a4fd54e43e7dc8d4e050f5ed/pymedphys/labs/quickcheck/qcheck.py>`__

-  Added ``pymedphys dev tests`` to the CLI.

   -  Moved all of tests into the pymedphys repo itself. Now the
      automated testing suite is able to be run from a pypi install.
   -  This CLI has options such as ``--run-only-pydicom``,
      ``--run-only-slow``, and ``--run-only-pylinac`` so that upstream
      tools can run tests on this downstream project.
   -  These extra options are directly passed through to ``pytest``. To
      achieve this, made the ``pymedphys`` CLI be able to optionally
      handle arbitrary commands.

-  Made the Zenodo download tool retry up to four times should the
   download fail.
-  Added DICOM helpers functionality and updated the Mosaiq helpers as a
   part of the UTHSCSA TPS/OIS comparison project. Not yet exposed as
   part of the API. See
   `\_mosaiq/helpers.py#L353-L482 <https://github.com/pymedphys/pymedphys/blob/2d5148e2eabce3a6a4fd54e43e7dc8d4e050f5ed/pymedphys/_mosaiq/helpers.py#L353-L482>`__
-  Added more debugging strings to the iCOM CLI. See these outputs by
   running
   ``pymedphys --debug icom listen external.nss.ip.address your/output/directory``

   -  These were added to support remotely debugging the iCOM listen
      software. To see the conversation around debugging that tool see
      the `PyMedPhys forum
      discussion <https://groups.google.com/forum/#!topic/pymedphys/2LczVpmc_Ak>`__

-  Format of MU in logging display now rounded to one decimal.

Dependency changes
~~~~~~~~~~~~~~~~~~

-  Now depending on ``pylibjpeg-libjpeg`` in order to decode
   lossless-jpeg files.
-  ``m2r`` is no longer used to build the docs.
-  No longer using ``tox`` for tests.

.. _bug-fixes-5:

Bug fixes
~~~~~~~~~

-  Fixed an issue where the iCOM listener could not handle Machine IDs
   that were not entirely an integer.

   -  See
      `\_icom/mappings.py#L6 <https://github.com/pymedphys/pymedphys/blob/2d5148e2eabce3a6a4fd54e43e7dc8d4e050f5ed/pymedphys/_icom/mappings.py#L6>`__
      for changes.
   -  See the `PyMedPhys forum
      discussion <https://groups.google.com/d/msg/pymedphys/2LczVpmc_Ak/c5nUeUfQAQAJ>`__
      for details.

-  Fixed a case where on some Windows environments
   ``pymedphys dev docs`` would not run.
-  Fixed a case where on some Windows environments ``pymedphys gui``
   would not run.
-  Fixed issue where the ``pymedphys logfile orchestration`` CLI would
   not be able to create an ``index.json``, or a range of the needed
   directories on its first run.

   -  See the `PyMedPhys forum
      discussion <https://groups.google.com/d/msg/pymedphys/2LczVpmc_Ak/5mFZig1cAgAJ>`__
      for more details.

Documentation updates
~~~~~~~~~~~~~~~~~~~~~

-  Fixed an issue where the displayed CSV files for configuring
   ``pymedphys logfile orchestration`` would actually cause an error due
   to excess spaces used for display purposes.

   -  See the `PyMedPhys forum
      discussion <https://groups.google.com/d/msg/pymedphys/2LczVpmc_Ak/m41v_LVRAgAJ>`__
      for more details.

Development changes
~~~~~~~~~~~~~~~~~~~

-  Removed any file that was larger than 300 kB from the git history
   bring down clone times to a manageable state.

   -  The ``pre-commit`` tool now does not allow commits greater than
      300 kB.
   -  All testing files that were larger than 300 kB have been moved to
      Zenodo.

-  All tests have been moved from ``/tests`` into ``/pymedphys/tests``,
   running these tests can now be undergone by calling
   ``pymedphys dev tests``

   -  No longer using ``tox``.

.. _section-4:

`0.29.1 <https://github.com/pymedphys/pymedphys/compare/v0.29.0...v0.29.1>`__
-----------------------------------------------------------------------------

.. _bug-fixes-6:

Bug fixes
~~~~~~~~~

-  Fix issue in some Windows environments where running
   ``pymedphys gui`` would not find the streamlit installation.
   `\_gui/init.py <https://github.com/pymedphys/pymedphys/blob/03ba546b603edcbaf7b2b33c6367146a95142d0d/pymedphys/_gui/__init__.py#L43>`__

.. _section-5:

`0.29.0 <https://github.com/pymedphys/pymedphys/compare/v0.28.0...v0.29.0>`__
-----------------------------------------------------------------------------

.. _breaking-changes-5:

Breaking changes
~~~~~~~~~~~~~~~~

-  Changed the ``patient_directories`` icom parameter to accept a list
   of paths instead of a single path within the pymedphys
   ``config.toml``.
   `config.toml#L67-L72 <https://github.com/pymedphys/pymedphys/blob/7a08a94185f94b1f7df304de8bd0274f0f1fcbc9/examples/site-specific/cancer-care-associates/config.toml#L67-L72>`__
-  Changed ``pymedphys gui`` iCOM path resolution logic to instead
   search over a list of paths instead of just one path as before.
   `mudensity-compare.py#L668-L670 <https://github.com/pymedphys/pymedphys/blob/7a08a94185f94b1f7df304de8bd0274f0f1fcbc9/pymedphys/_gui/streamlit/mudensity-compare.py#L668-L670>`__

.. _section-6:

`0.28.0 <https://github.com/pymedphys/pymedphys/compare/v0.27.0...v0.28.0>`__
-----------------------------------------------------------------------------

Overview
~~~~~~~~

This release primarily focused on changes regarding the iCOM listener
and the PyMedPhys GUI that utilises these iCOM records.

.. _breaking-changes-6:

Breaking changes
~~~~~~~~~~~~~~~~

-  Removed the ``pymedphys icom archive`` CLI command, this archiving is
   now built directly into the listener itself.

.. _new-features-6:

New Features
~~~~~~~~~~~~

-  The ``pymedphys icom listener`` CLI command now will collect the icom
   stream into beam delivery batches and index them by patient name.
   This functionality used to be undergone within the
   ``pymedphys icom archive`` CLI, but this functionality has now been
   merged into the listener.
   `listener.py#L79 <https://github.com/pymedphys/pymedphys/blob/d40a5ed238b2035bac00da1cb623c7f496ed0950/pymedphys/_icom/listener.py#L79>`__
-  Should an error occur within ``pymedphys icom listener`` CLI it will
   now pause for 15 minutes and then reattempt a connection.
-  Add in extra sanity checks within the iCOM patient indexing tooling.
-  Added a ``--debug`` and ``--verbose`` flag to the PyMedPhys CLI which
   allows users to set the logging level. These logging levels are
   currently only utilised within the ``pymedphys icom listen`` CLI.
   `cli/main.py#L51-L70 <https://github.com/pymedphys/pymedphys/blob/9c7c7e3c2d7fb49d30b418dca2fa28e6982ff97e/pymedphys/cli/main.py#L51-L70>`__

.. _bug-fixes-7:

Bug fixes
~~~~~~~~~

-  Reduced the buffer size of the iCOM listener.
   `listener.py#L9 <https://github.com/pymedphys/pymedphys/blob/d40a5ed238b2035bac00da1cb623c7f496ed0950/pymedphys/_icom/listener.py#L9>`__
-  If either the listener is turned off and then on again, or it is
   interrupted the next time an iCOM stream socket is opened the Linac
   appears to send a larger batch containing prior irradiations. The
   listener code was adjusted to handle these extra bursts.
   `listener.py#L57-L83 <https://github.com/pymedphys/pymedphys/blob/d40a5ed238b2035bac00da1cb623c7f496ed0950/pymedphys/_icom/listener.py#L57-L83>`__
-  Made PyMedPhys GUI skip name formatting attempt if the original
   patient name format was not as expected.
   `mudensity-compare.py#L733-L738 <https://github.com/pymedphys/pymedphys/blob/d40a5ed238b2035bac00da1cb623c7f496ed0950/pymedphys/_gui/streamlit/mudensity-compare.py#L733-L738>`__

.. _section-7:

`0.27.0 <https://github.com/pymedphys/pymedphys/compare/v0.26.0...v0.27.0>`__
-----------------------------------------------------------------------------

.. _new-features-7:

New Features
~~~~~~~~~~~~

-  Added an optional ``--structures`` flag to
   ``pymedphys dicom merge-contours``. This allows you to only compute
   the merge for those structures named.

.. _section-8:

`0.26.0 <https://github.com/pymedphys/pymedphys/compare/v0.25.1...v0.26.0>`__
-----------------------------------------------------------------------------

.. _new-features-8:

New Features
~~~~~~~~~~~~

-  Created a function to merge overlapping contours that have the same
   name within a DICOM structure file.

   -  Underlying function –
      https://github.com/pymedphys/pymedphys/blob/8b9284a8bc9a948646c9d8c0723d9959c61ae089/pymedphys/_dicom/structure/merge.py#L172-L200
   -  API exposure –
      https://github.com/pymedphys/pymedphys/blob/8b9284a8bc9a948646c9d8c0723d9959c61ae089/pymedphys/dicom.py#L13

-  Exposed the above command as a part of the CLI. It is runnable with
   ``pymedphys dicom merge-contours``

   -  CLI exposure –
      https://github.com/pymedphys/pymedphys/blob/8b9284a8bc9a948646c9d8c0723d9959c61ae089/pymedphys/cli/dicom.py#L42-L50

.. _section-9:

`0.25.1 <https://github.com/pymedphys/pymedphys/compare/v0.25.0...v0.25.1>`__
-----------------------------------------------------------------------------

.. _dependency-changes-1:

Dependency Changes
~~~~~~~~~~~~~~~~~~

-  Now included ``psutil`` as an optional dependency.

Quality of life improvements
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  Now raises a descriptive error when a DICOM RT plan file’s control
   point is missing a cumulative meterset weight.
   https://github.com/pymedphys/pymedphys/blob/dfd418a6dd1b8b57ba6bbfd27a498596477ceb6f/pymedphys/_dicom/delivery/core.py#L180-L196
-  When running ``pymedphys gui`` for the first time, no longer does
   ``streamlit`` request credentials.
   https://github.com/pymedphys/pymedphys/blob/dfd418a6dd1b8b57ba6bbfd27a498596477ceb6f/pymedphys/_gui/__init__.py#L24-L36

.. _development-changes-1:

Development changes
~~~~~~~~~~~~~~~~~~~

-  Implemented Cypress GUI testing infrastructure into the CI workflow.
   See details at https://dashboard.cypress.io/projects/tgt8f6/runs.

   -  Tests –
      https://github.com/pymedphys/pymedphys/blob/dfd418a6dd1b8b57ba6bbfd27a498596477ceb6f/tests/e2e/cypress/integration/streamlit/mudensity-compare.js
   -  CI config –
      https://github.com/pymedphys/pymedphys/blob/dfd418a6dd1b8b57ba6bbfd27a498596477ceb6f/.github/workflows/cypress.yml

.. _section-10:

`0.25.0 <https://github.com/pymedphys/pymedphys/compare/v0.24.3...v0.25.0>`__
-----------------------------------------------------------------------------

.. _new-features-9:

New Features
~~~~~~~~~~~~

-  Created the command line tool ``pymedphys gui`` which boots the GUI
   for PyMedPhys within your browser. GUI at this stage is quite
   minimal.
-  Created a tool to handle a PyMedPhys config file, by default stored
   within ``~/.pymedphys/.config.toml``. That config file can have a
   ``redirect`` field to allow configuration to be stored in a different
   location such as within a git repo, or a network drive.
-  ``pymedphys.zip_data_paths`` now has a new optional parameter
   ``extract_directory``. When this parameter is passed the contents of
   the zip downloaded zip data will be extracted to the provided
   directory. For example now the following is possible:

.. code:: python

   import pathlib

   import pymedphys

   CWD = pathlib.Path.cwd()
   pymedphys.zip_data_paths("mu-density-gui-e2e-data.zip", extract_directory=CWD)

-  ``pymedphys.Delivery.from_dicom()`` now supports step and shoot and
   3DCRT DICOM plan files.
-  Work on ``pymedphys.Delivery.from_monaco()`` was undergone with an
   attempt to support step and shoot plans. This work was preliminary.
-  Created a utility to pretty print patient names
-  Added ground work for e2e testing of ``pymedphys gui`` with the
   cypress tool.

.. _section-11:

`0.24.3 <https://github.com/pymedphys/pymedphys/compare/v0.24.2...v0.24.3>`__
-----------------------------------------------------------------------------

.. _bug-fixes-8:

Bug Fixes
~~~~~~~~~

-  Within the bundle created by ``pymedphys bundle`` fixed a bug where
   the streamlit server will not start due stdout not flushing.

.. _section-12:

`0.24.2 <https://github.com/pymedphys/pymedphys/compare/v0.24.1...v0.24.2>`__
-----------------------------------------------------------------------------

.. _bug-fixes-9:

Bug Fixes
~~~~~~~~~

-  Within the bundle created by ``pymedphys bundle`` fixed a bug where
   sometimes the streamlit server would not start should a stdout race
   condition occur.

.. _section-13:

`0.24.1 <https://github.com/pymedphys/pymedphys/compare/v0.24.0...v0.24.1>`__
-----------------------------------------------------------------------------

.. _bug-fixes-10:

Bug Fixes
~~~~~~~~~

-  Include ``matplotlib`` within ``streamlit`` bundle. Streamlit
   requires this but has not labeled it as a dependency.
-  Call ``yarn`` from ``os.system``, for some reason on Windows
   ``subprocess.check_call`` could not find ``yarn`` on the path,
   although on Linux this worked fine.

.. _section-14:

`0.24.0 <https://github.com/pymedphys/pymedphys/compare/v0.23.0...v0.24.0>`__
-----------------------------------------------------------------------------

.. _breaking-changes-7:

Breaking Changes
~~~~~~~~~~~~~~~~

-  If ``pymedphys.mosaiq.connect`` is passed a list of length one, it
   will now return a cursor within a list of length 1 instead of just
   returning a cursor by itself.

.. _new-features-10:

New Features
~~~~~~~~~~~~

-  Added a ``pymedphys bundle`` cli function which creates an electron
   streamlit installation bundle.
-  Added the ‘all’ fractions option to ``Delivery.from_dicom`` which can
   be used as
   ``pymedphys.Delivery.from_dicom(dicom_file, fraction_number='all')``
-  Made the iCOM patient archiving only save the data if MU was
   delivered.
-  Added wlutz mock image generation functions
-  Handle more Monaco ``tel.1`` cases within ``Delivery.from_monaco``
-  ``get_patient_name`` added to ``pymedphys._mosaiq.helpers``

Algorithm Adjustments
~~~~~~~~~~~~~~~~~~~~~

-  Wlutz bb finding cost function adjusted

   -  Note, wlutz algorithm still not ready for the prime time

.. _section-15:

`0.23.0 <https://github.com/pymedphys/pymedphys/compare/v0.22.0...v0.23.0>`__
-----------------------------------------------------------------------------

.. _breaking-changes-8:

Breaking Changes
~~~~~~~~~~~~~~~~

-  Removed ``jupyter``, ``bundle``, and ``app`` sub commands from the
   CLI.
-  Removed the ``gui`` and ``jupyter`` optional extra installation
   commands.
-  In order to support Python 3.8, the ``pymssql`` dependency needed to
   be removed for that Python version. All tools that make SQL calls to
   Mosaiq will not currently work on Python 3.8.

.. _new-features-11:

New Features
~~~~~~~~~~~~

-  PyMedPhys now is able to be installed on Python 3.8.

.. _dependency-changes-2:

Dependency Changes
~~~~~~~~~~~~~~~~~~

-  No longer depend upon ``pymssql`` for Python 3.8.

.. _bug-fixes-11:

Bug Fixes
~~~~~~~~~

-  Fix ``pymedphys._monaco`` package path.
-  Fixed issue where the following header adjustment DICOM CLI tools may
   not work with ``pydicom==1.4.2``. See
   https://github.com/pymedphys/pymedphys/pull/747 and
   https://github.com/pymedphys/pymedphys/pull/748.

   -  ``pymedphys dicom adjust-machine-name``
   -  ``pymedphys dicom adjust-RED``
   -  ``pymedphys dicom adjust-RED-by-structure-name``

.. _section-16:

`0.22.0 <https://github.com/pymedphys/pymedphys/compare/v0.21.0...v0.22.0>`__
-----------------------------------------------------------------------------

.. _new-features-12:

New Features
~~~~~~~~~~~~

-  Implemented ``from_icom`` method on the ``pymedphys.Delivery``
   object. This was to support calculating an MU Density from an iCOM
   stream.

   -  See https://github.com/pymedphys/pymedphys/pull/733

.. _section-17:

`0.21.0 <https://github.com/pymedphys/pymedphys/compare/v0.20.0...v0.21.0>`__
-----------------------------------------------------------------------------

.. _dependency-changes-3:

Dependency Changes
~~~~~~~~~~~~~~~~~~

-  Once again made ``shapely`` a default dependency with the aim to make
   installation be “batteries included”.

   -  ``Shapely`` now ships wheels for Windows. This means ``shapely``
      will install normally with pip. See
      https://github.com/Toblerity/Shapely/issues/815#issuecomment-579945334

-  Pinned ``pydicom`` due to a currently unknown issue with a new
   version breaking a ``pymedphys`` test.

.. _section-18:

`0.20.0 <https://github.com/pymedphys/pymedphys/compare/v0.19.0...v0.20.0>`__
-----------------------------------------------------------------------------

.. _new-features-13:

New Features
~~~~~~~~~~~~

-  Expose some portions of the Winston Lutz API.
-  Add iCom listener CLI.

.. _section-19:

`0.19.0 <https://github.com/pymedphys/pymedphys/compare/v0.18.0...v0.19.0>`__
-----------------------------------------------------------------------------

.. _breaking-changes-9:

Breaking Changes
~~~~~~~~~~~~~~~~

-  Made shapely an optional dependency once more. No longer depending on
   ``shapely-helper``.

   -  Shapely can be installed by running
      ``pip install pymedphys[difficult]==0.19.0``
   -  This fixes an issue where ``pip`` refuses to install due to the
      ``shapely-helper`` workaround.

.. _section-20:

`0.18.0 <https://github.com/pymedphys/pymedphys/compare/v0.17.1...v0.18.0>`__
-----------------------------------------------------------------------------

.. _breaking-changes-10:

Breaking Changes
~~~~~~~~~~~~~~~~

-  Removed the optional extras tags of ``library``, ``labs``, and
   ``difficult``. All of these now install by default. For example
   PyMedPhys can no longer be installed with
   ``pip install pymedphys[library]``.

.. _quality-of-life-improvements-1:

Quality of life improvements
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  Installation of PyMedPhys has been reverted to including all of its
   primary dependencies. This was done to make the default install less
   confusing. Nevertheless, these dependencies are mostly optional and
   if you wish you can install with ``pip install pymedphys --no-deps``
   to have a minimal installation.
-  Made a ``shapely-helpers`` package which automatically handles
   installation of ``shapely`` on Windows. PyMedPhys now depends on
   ``shapely-helpers`` instead of ``shapely``.

.. _section-21:

`0.17.1 <https://github.com/pymedphys/pymedphys/compare/v0.17.0...v0.17.1>`__
-----------------------------------------------------------------------------

.. _quality-of-life-improvements-2:

Quality of life improvements
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  Made wlutz determination less fussy.

.. _section-22:

`0.17.0 <https://github.com/pymedphys/pymedphys/compare/v0.16.3...v0.17.0>`__
-----------------------------------------------------------------------------

.. _new-features-14:

New Features
~~~~~~~~~~~~

-  Initial alpha release of an experimental JupyterLab application
   bundler. Run with ``pymedphys bundle`` in a directory that contains a
   ``notebooks`` dir and a ``requirements.txt`` file.

.. _section-23:

`0.16.3 <https://github.com/pymedphys/pymedphys/compare/v0.16.2...v0.16.3>`__
-----------------------------------------------------------------------------

.. _bug-fixes-12:

Bug Fixes
~~~~~~~~~

-  Gracefully reject ipython inspection for optional modules by
   returning ``None`` for ‘**file**’ attribute requests for modules that
   are not currently installed.

.. _section-24:

`0.16.2 <https://github.com/pymedphys/pymedphys/compare/v0.16.1...v0.16.2>`__
-----------------------------------------------------------------------------

.. _bug-fixes-13:

Bug Fixes
~~~~~~~~~

-  Fixed bug with optional dependency logic within ``apipkg``. Occurred
   whenever an optional submodule was called, for example
   ``scipy.interpolate``.

.. _section-25:

`0.16.1 <https://github.com/pymedphys/pymedphys/compare/v0.16.0...v0.16.1>`__
-----------------------------------------------------------------------------

Aesthetic Changes
~~~~~~~~~~~~~~~~~

-  Updated the badges reported within the README.

.. _section-26:

`0.16.0 <https://github.com/pymedphys/pymedphys/compare/v0.15.0...v0.16.0>`__
-----------------------------------------------------------------------------

Package changes
~~~~~~~~~~~~~~~

-  The license of the package has changed from ``AGPL-3.0-or-later`` to
   ``Apache-2.0``.

.. _new-features-15:

New Features
~~~~~~~~~~~~

-  Expose ``pymedphys.electronfactors.plot_model`` as part of the public
   API.

.. _section-27:

`0.15.0 <https://github.com/pymedphys/pymedphys/compare/v0.14.3...v0.15.0>`__
-----------------------------------------------------------------------------

.. _new-features-16:

New Features
~~~~~~~~~~~~

-  Experimental support for Elekta Unity trf log file decoding.

.. _section-28:

`0.14.3 <https://github.com/pymedphys/pymedphys/compare/v0.14.2...v0.14.3>`__
-----------------------------------------------------------------------------

.. _package-changes-1:

Package changes
~~~~~~~~~~~~~~~

-  Updated wheel to correctly handle optional dependencies.

.. _section-29:

`0.14.2 <https://github.com/pymedphys/pymedphys/compare/v0.14.1...v0.14.2>`__
-----------------------------------------------------------------------------

.. _bug-fixes-14:

Bug Fixes
~~~~~~~~~

-  Vendored in ``apipkg`` due to PyPI installation issues.

.. _section-30:

`0.14.1 <https://github.com/pymedphys/pymedphys/compare/v0.14.0...v0.14.1>`__
-----------------------------------------------------------------------------

.. _bug-fixes-15:

Bug Fixes
~~~~~~~~~

-  Given the input to ``pymedphys.gamma`` is unitless, removed the units
   from the logging output of gamma. See
   https://github.com/pymedphys/pymedphys/issues/611

.. _section-31:

`0.14.0 <https://github.com/pymedphys/pymedphys/compare/v0.13.2...v0.14.0>`__
-----------------------------------------------------------------------------

.. _breaking-changes-11:

Breaking Changes
~~~~~~~~~~~~~~~~

-  Moved ``pymedphys pinnacle`` cli command to be nested under
   ``pymedphys labs pinnacle``

.. _dependency-changes-4:

Dependency Changes
~~~~~~~~~~~~~~~~~~

-  Made the greater majority of the pymedphys dependencies optional.
   Should a dependency be required during usage an error is raised
   informing the user to install the package. To install all pymedphys
   dependencies as before now run
   ``pip install pymedphys[library,labs]==0.14.0``.

.. _section-32:

`0.13.2 <https://github.com/pymedphys/pymedphys/compare/v0.13.1...v0.13.2>`__
-----------------------------------------------------------------------------

Bug Fix
~~~~~~~

-  Fixed issue where ``pymedphys.mosaiq.connect`` would not work for
   just one hostname.

.. _section-33:

`0.13.1 <https://github.com/pymedphys/pymedphys/compare/v0.13.0...v0.13.1>`__
-----------------------------------------------------------------------------

.. _bug-fix-1:

Bug Fix
~~~~~~~

-  Fixed issue where ``pymedphys.mosaiq.connect`` would not work for
   just one hostname.

.. _section-34:

`0.13.0 <https://github.com/pymedphys/pymedphys/compare/v0.12.2...v0.13.0>`__
-----------------------------------------------------------------------------

New Feature
~~~~~~~~~~~

-  Made ``pymedphys.mosaiq.execute`` a part of the API.

.. _section-35:

`0.12.2 <https://github.com/pymedphys/pymedphys/compare/v0.12.1...v0.12.2>`__
-----------------------------------------------------------------------------

.. _package-changes-2:

Package changes
~~~~~~~~~~~~~~~

-  Fixed version number within package.

.. _section-36:

`0.12.1 <https://github.com/pymedphys/pymedphys/compare/v0.12.0...v0.12.1>`__
-----------------------------------------------------------------------------

.. _package-changes-3:

Package changes
~~~~~~~~~~~~~~~

-  Re-added the license classifier to the PyPI upload.

.. _section-37:

`0.12.0 <https://github.com/pymedphys/pymedphys/compare/v0.11.0...v0.12.0>`__
-----------------------------------------------------------------------------

.. _breaking-changes-12:

Breaking Changes
~~~~~~~~~~~~~~~~

-  The API has undergone a complete redesign. Expect most code to be
   broken with this release.

.. _section-38:

`0.11.0 <https://github.com/pymedphys/pymedphys/compare/v0.10.0...v0.11.0>`__
-----------------------------------------------------------------------------

.. _breaking-changes-13:

Breaking Changes
~~~~~~~~~~~~~~~~

-  Within ``dose_from_dataset`` the ``reshape`` parameter has been
   removed.
-  Removed the following functions:

   -  ``load_dicom_data``
   -  ``axes_and_dose_from_dicom``
   -  ``extract_depth_dose``
   -  ``extract_profiles``

.. _new-features-17:

New Features
~~~~~~~~~~~~

-  Added functions ``pymedphys.dicom.depth_dose`` and
   ``pymedphys.dicom.profiles``.
-  Exposed the ``trf2pandas`` function via
   ``pymedphys.fileformats.trf2pandas``.

Improvements
~~~~~~~~~~~~

-  Made the resolution detection of ``pymedphys.plt.pcolormesh_grid``
   more robust.

.. _section-39:

`0.10.0 <https://github.com/pymedphys/pymedphys/compare/v0.9.0...v0.10.0>`__
----------------------------------------------------------------------------

.. _new-features-18:

New Features
~~~~~~~~~~~~

-  Re-exposed ``convert2_ratio_perim_area`` and
   ``create_transformed_mesh`` from ``pymedphys.electronfactors``.
-  Pinnacle module providing a tool to export raw Pinnacle data to DICOM
   objects.

   -  A CLI is provided: See `the Pinnacle CLI
      docs <https://docs.pymedphys.com/user/interfaces/cli/pinnacle.html>`__.
   -  As well as an API: See `the Pinnacle library
      docs <https://docs.pymedphys.com/user/library/pinnacle.html>`__.

.. _section-40:

`0.9.0 <https://github.com/pymedphys/pymedphys/compare/v0.8.4...v0.9.0>`__ – 2019/06/06
---------------------------------------------------------------------------------------

.. _new-features-19:

New Features
~~~~~~~~~~~~

-  Re-exposed ``multi_mosaiq_connect``,
   ``multi_fetch_and_verify_mosaiq``, ``get_qcls_by_date``, and
   ``get_staff_name`` from ``pymedphys.msq``.

.. _section-41:

`0.8.4 <https://github.com/pymedphys/pymedphys/compare/v0.8.3...v0.8.4>`__ – 2019/06/04
---------------------------------------------------------------------------------------

.. _package-changes-4:

Package changes
~~~~~~~~~~~~~~~

-  Made ``xlwings`` not install by default if system is ``Linux`` within
   ``setup.py``
-  Removed unreleased ``jupyter`` based GUI

.. _section-42:

`0.8.3 <https://github.com/pymedphys/pymedphys/compare/v0.8.2...v0.8.3>`__ – 2019/06/04
---------------------------------------------------------------------------------------

.. _package-changes-5:

Package changes
~~~~~~~~~~~~~~~

-  Updated MANIFEST file within ``pymedphys_fileformats`` to
   appropriately include LICENSE files.

.. _section-43:

`0.8.2 <https://github.com/pymedphys/pymedphys/compare/v0.8.1...v0.8.2>`__ – 2019/06/01
---------------------------------------------------------------------------------------

.. _package-changes-6:

Package changes
~~~~~~~~~~~~~~~

-  Included license files within the subpackage distributions

.. _section-44:

`0.8.1 <https://github.com/pymedphys/pymedphys/compare/v0.8.0...v0.8.1>`__ – 2019/06/01
---------------------------------------------------------------------------------------

.. _dependency-changes-5:

Dependency changes
~~~~~~~~~~~~~~~~~~

-  Removed numpy version upper-limit

.. _section-45:

`0.8.0 <https://github.com/pymedphys/pymedphys/compare/v0.7.2...v0.8.0>`__ – 2019/06/01
---------------------------------------------------------------------------------------

.. _breaking-changes-14:

Breaking Changes
~~~~~~~~~~~~~~~~

-  ``DeliveryData`` has been renamed to ``Delivery`` and is now
   importable by running ``from pymedphys import Delivery``

   -  A range of functions that used to use ``DeliveryData`` are now
      instead accessible as methods on the ``Delivery`` object.

-  A large number of functions that were previously exposed have now
   been made private in preparation for eventually stabilising the API.
   No function that was within the documentation has been removed. If
   there is a function that you were using that you would like to be
   exposed via ``import`` again, please let us know by `opening an issue
   on GitHub <https://github.com/pymedphys/pymedphys/issues>`__ and we
   will happily re-expose it! However, please bear in mind that the
   entire API that is currently exposed will likely change before a
   1.0.0 release.
-  ``anonymise_dicom_dataset()`` has been renamed to
   ``anonymise_dataset()`` to remove redundant labelling.
-  ``mu_density_from_delivery_data`` moved from the ``msq`` module to
   the ``mudensity`` module.
-  ``compare_mosaiq_fields`` moved from the ``msq`` module into the
   ``plancompare`` module.
-  ``pymedphys.dicom.get_structure_aligned_cube`` has had its ``x0``
   parameter changed from required to optional. It is no longer the
   first parameter passed to the function. By default ``x0`` is now
   determined using the min/max bounds of the structure.
-  The DICOM coordinate extraction functions -
   ``extract_dicom_patient_xyz()``, ``extract_iec_patient_xyz()`` and
   ``extract_iec_fixed_xyz()`` - have been combined into a single
   function called ``xyz_from_dataset()``. The x, y, z axes can still be
   returned in either the DICOM, IEC fixed or IEC patient coordinate
   systems by passing the following case-insensitive strings to the
   ``coord_system=`` parameter of ``xyz_from_dataset()``:

   -  DICOM: ``'d'`` or ``'DICOM'``
   -  IEC fixed: ``'f'``, ``'fixed'`` or ``'IEC fixed'``
   -  IEC patient: ``'p'``, ``'patient'`` or ``'IEC patient'``

-  ``gamma_dicom`` now take datasets as opposed to filenames

.. _new-features-20:

New Features
~~~~~~~~~~~~

-  A DICOM anonymisation CLI! See `the DICOM Files CLI
   docs <../user/interfaces/cli/dicom.rst>`__.
-  ``anonymise_file()`` and ``anonymise_directory()``:

   -  two new DICOM anonymisation wrapper functions that take a DICOM
      file and a directory as respective arguments.

-  ``is_anonymised_dataset()``, ``is_anonymised_file()`` and
   ``is_anonymised_directory()``:

   -  three new functions that check whether a pydicom dataset, a DICOM
      file or all files within a directory have been anonymised,
      respectively.

-  ``coords_from_xyz_axes()`` is a previously internal function that has
   now been exposed in the API. It converts x, y, z axes returned by
   ``xyz_from_dataset()`` into a full grid of coordinate triplets that
   correspond to the original grid (pixel array or dose grid).

.. _section-46:

`0.7.2 <https://github.com/pymedphys/pymedphys/compare/v0.7.1...v0.7.2>`__ – 2019/04/05
---------------------------------------------------------------------------------------

.. _dependency-changes-6:

Dependency changes
~~~~~~~~~~~~~~~~~~

-  Removed numpy version upper-limit

.. _section-47:

`0.7.1 <https://github.com/pymedphys/pymedphys/compare/v0.7.0...v0.7.1>`__ – 2019/04/05
---------------------------------------------------------------------------------------

Performance Improvements
~~~~~~~~~~~~~~~~~~~~~~~~

-  reduced PyPI package size by removing unnecessary development testing
   files.

.. _section-48:

`0.7.0 <https://github.com/pymedphys/pymedphys/compare/v0.6.0...v0.7.0>`__ – 2019/04/05
---------------------------------------------------------------------------------------

.. _breaking-changes-15:

Breaking Changes
~~~~~~~~~~~~~~~~

-  ``anonymise_dicom`` has been renamed to ``anonymise_dicom_dataset``
-  The CLI interface ``trf2csv`` has been replaced with
   ``pymedphys trf to-csv``. This has the same usage, just a changed
   name to come in line with the rest of the CLI interfaces exposed by
   PyMedPhys.

.. _new-features-21:

New Features
~~~~~~~~~~~~

-  Implementing a suite of Dicom objects, currently a work in progress:

   -  ``DicomBase``, a base DICOM class that wraps ``pydicom``\ ’s
      ``Dataset`` object. This class includes additions such as an
      anonymisation method.
   -  ``DicomImage``, designed to hold a single DICOM image slice. Might
      someday contain methods such as ``resample`` and the like.
   -  ``DicomSeries``, a series of ``DicomImage`` objects creating a CT
      dataset.
   -  ``DicomStructure``, designed to house DICOM structure datasets.
   -  ``DicomPlan``, a class that holds RT plan DICOM datasets.
   -  ``DicomDose``, a class that to hold RT DICOM dose datasets. It has
      helper functions and parameters such as coordinate transforms
      built into it.
   -  ``DicomStudy``, a class designed to hold an interrelated set of
      ``DicomDose``, ``DicomPlan``, ``DicomStructure``, and
      ``DicomSeries``. Not every type is required to create a
      ``DicomStudy``. Certain methods will be available on
      ``DicomStudy`` depending what is housed within it. For example
      having both ``DicomDose`` and ``DicomStructure`` should enable DVH
      based methods.
   -  ``DicomCollection``, a class that can hold multiple studies,
      interrelated or not. A common use case that will likely be
      implemented is ``DicomCollection.from_directory(directory_path)``
      which would pull all DICOM files nested within a directory and
      sort them into ``DicomStudy`` objects based on their header UIDs.

-  Added CLI commands for a WIP docker server, logfile orchestration,
   and DICOM editor tools.
-  Added a range of xlwings tools that allow the use of PyMedPhys
   functions within Excel
-  Added rudimentary code to pull profiles from Mephysto files.
-  The previously separate ``decodetrf`` library is now distributed
   within PyMedPhys. You can now simply install PyMedPhys and run
   ``pymedphys trf to-csv`` within the command line to convert ``.trf``
   files into ``.csv`` files.

.. _section-49:

`0.6.0 <https://github.com/pymedphys/pymedphys/compare/v0.5.1...v0.6.0>`__ – 2019/03/15
---------------------------------------------------------------------------------------

.. _breaking-changes-16:

Breaking Changes
~~~~~~~~~~~~~~~~

-  All uses of “dcm” in directory names, module names, function names,
   etc. have been converted to “dicom”. Anything that makes use of this
   code will need to be adjusted accordingly. Required changes include:

   -  ``pymedphys.dcm`` –> ``pymedphys.dicom``
   -  ``coords_and_dose_from_dcm()`` –> ``coords_and_dose_from_dicom()``
   -  ``dcmfromdict()`` –> ``dicom_dataset_from_dict()``
   -  ``gamma_dcm()`` –> ``gamma_dicom()``

-  MU Density related functions are no longer available under the
   ``pymedphys.coll`` package, instead they are found within
   ``pymedphys.mudensity`` package.
-  The DICOM coordinate extraction functions now return simple tuples
   rather than ``Coords`` namedtuples:

   -  ``extract_dicom_patient_xyz()``
   -  ``extract_iec_patient_xyz()``
   -  ``extract_iec_fixed_xyz()``

.. _new-features-22:

New Features
~~~~~~~~~~~~

-  DICOM anonymisation now permits replacing deidentified values with
   suitable “dummy” values. This helps to maintain compatibility with
   DICOM software that includes checks (beyond those specified in the
   DICOM Standard) of valid DICOM tag values. Replacing tags with dummy
   values upon anonymisation is now the default behaviour.
-  A set of 3D coordinate transformation functions, including rotations
   (passive or active) and translations. Transformations may be applied
   to a single coordinate triplet (an ``ndarray``) or a list of
   arbitrarily many coordinate triplets (a 3 x n ``ndarray``). **NB**:
   Documentation forthcoming.

Code Refactoring
~~~~~~~~~~~~~~~~

-  All uses of ``dcm`` as a variable name for instances of PyDicom
   Datasets have been converted to ``ds`` to match PyDicom convention.

.. _section-50:

`0.5.1 <https://github.com/pymedphys/pymedphys/compare/v0.4.3...v0.5.1>`__ – 2019/01/05
---------------------------------------------------------------------------------------

.. _new-features-23:

New Features
~~~~~~~~~~~~

-  Began keeping record of changes in ``changelog.md``
