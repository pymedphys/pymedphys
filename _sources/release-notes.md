<!-- markdownlint-disable MD024 MD039 -->

# Release Notes

All notable changes to this project will be documented in this file.

This project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.37.1]

### Bug fixes

* Make it so that Mephysto files that have non-unicode characters can still
  be opened.
* Varying penumbra and ball bearing diameter within the Monthly WLutz
  application now accepts floating point numbers as well as numbers smaller
  than the default.
* Fixed a bug where `Delivery.from_monaco` wouldn't be able to load beams
  where the stop angle of one beam was +180 and the start angle of the
  subsequent beam was -180 (or visa-versa). The conversion from IEC to bipolar
  is now handled on a "per-beam" basis. This bug affected the MetersetMap
  application.

### Non-API changing enhancements

* The daily WLutz application can now have its bb size configured.
* Site can now be passed as a URL parameter to the daily WLutz application.
* Improved error messaging around the configuration of the iView machine alias.

## [0.37.0]

### News around this release

* [Jake Rembish](https://github.com/rembishj) has been undergoing his PhD with
  the output of his work being contributed to PyMedPhys. This release coincides
  with the culmination of Jake's PhD and this version will be the one
  referenced within his dissertation. It has been brilliant to see both Jake
  and his project grow to be what it is today. Thank you Jake 😊.

### Breaking changes

* The configuration for the TRF CLI now utilises the centralised `config.toml`
  file instead of the prior `CSV` files.

### New features and enhancements

* A range of application have been added to and improved on within the
  PyMedPhys GUI.
  * A Daily WLutz application was added which utilises the air cavity within
    an iso-cube, combined with morning run-up beams (as arcs) to record the
    beam position at every gantry angle for each photon beam each morning.
  * A range of configuration improvements, making more applications more widely
    able to be utilised. Of particular note are Jake's transfer check and
    weekly check applications which were written as a part of his PhD.
  * A QCL investigator tool, allowing one to produce plots and break downs
    of numbers of QCLs broken down either by QCL type, or the user who
    completed them.
  * An extend ct application was added providing the means to duplicate slices
    superiorly and inferiorly.
  * An application for the viewing of back-end iView jpg images.
  * An application for tweaking the WLutz algorithm options from iView back-end
    jpg images.
  * A range of fixes and improvements within the WLutz Arc and the MetersetMap
    applications.
* The docs are now distributed with the PyMedPhys package. These are accessible
  by opening `http://localhost:8501/docs/index.html` after running
  `pymedphys gui`. In the future it is intended to make this link more
  accessible.
* A range of error messaging has been improved. Of particular benefit to new
  users is the error message that occurs when a dependency is missing.
* The ball-bearing finding component of the WLutz algorithm was tweaked to
  be able to also support the finding of air-cavities within an iso-cube.
* The testing suite around Mosaiq was built upon and extended across the
  breadth of PyMedPhys.
* Fixed a bug which was making `pymedphys.Delivery.from_mosaiq` non functional.
* Fixed a bug where some TRF files where not able to be decoded. Thank you
  LipTeck for [the bug report](https://pymedphys.discourse.group/t/request-to-use-file-name-for-missing-field-id-and-field-name-in-trf/156/6).
* The `pymedphys.trf.identify` interface was moved out of beta. See the
  documentation for this newly stable API over at <https://docs.pymedphys.com/lib/ref/trf.html>.
* Improved the robustness of the internal `extend ct` routines.
* **[Contributor facing only]** created `pymedphys dev mssql` which boots up
  a docker image of the Developer edition of Microsoft SQL. This is for
  utilisation by the Mosaiq testing suite.
* **[Contributor facing only]** made `pymedphys dev tests --cypress`
  automatically include the options `-v` and `-s` for displaying the `cypress`
  printouts during testing as well as `--reruns 5` so that the test
  automatically reruns on failure in alignment with the CI procedure.

## [0.36.1]

### New features and enhancements

* Added the `icom` installation option which can be run by calling
  `pip install pymedphys[icom]==0.36.1`. This will install only the
  dependencies needed for the iCom listener.

## [0.36.0]

### News around this release

* We have a new team member, [Derek Lane](https://github.com/dg1an3) he has
  undergone swathes of work around improving the long term maintenance of the
  Mosaiq SQL code. Thank you Derek! 🎉 🎈 🥳.
* [Matt Jennings](https://github.com/Matthew-Jennings) has rejoined the team,
  picking up his previous hat of Maintainer, great to have you back Matt 😊.

### Breaking changes

* The modules `pymedphys.electronfactors` and `pymedphys.wlutz` were removed
  from the public API.
  * There did not appear to be any usage of these modules outside of Cancer
    Care Associates.
  * The electron factors module can be re-exposed upon request.
  * The Winston Lutz module is undergoing a significant re-work and will be
    re-exposed in its new form once complete.
* There have been a range of changes to the previously undocumented Mosaiq
  database connection and execution API.
  * `pymedphys.mosaiq.connect` now returns a `Connection` object instead of a
    `Cursor` object. This was so as to align with PEP0249. See <https://github.com/pymedphys/pymedphys/pull/1352>.
  * All instances where previously the argument name within a function or
    method was `cursor` have been changed to `connection`.
  * Previously a server and port could be provided to `pymedphys.mosaiq.connect`
    by passing it as a colon separated string, for example `"localhost:1234"`.
    This is no longer the case. Now, hostname and port need to be provided
    separately. There are also three extra arguments, `alias`, `username`, and
    `password`. See either the docs <https://docs.pymedphys.com/lib/ref/mosaiq.html>
    or the docstring for more details <https://github.com/pymedphys/pymedphys/blob/a124bc56fb576456cc6eec44a711ebd478a995f3/lib/pymedphys/_mosaiq/api.py#L33-L79>.
  * Removed `pymedphys.mosaiq.qcls`.
* **[Contributor facing only]** replaced `pymedphys dev tests --pylint` with
  `pymedphys dev lint`.

### New features and enhancements

* Added CLI argument for setting the hostname on the DICOM listen server. For
  example `pymedphys dicom listen 7779 --host 127.0.0.1`.
* Added DICOM send functionality to DICOM connect module and made it available on the CLI. For example `pymedphys dicom send 127.0.0.1 7779 path\to\dicom\*.dcm`
* A range of application changes and improvements. The PyMedPhys app can be
  accessed by running `pymedphys gui`.
* **[Streamlit users only]** A CLI command `pymedphys streamlit run` was added
  to facilitate utilising the custom PyMedPhys patches on the streamlit server
  for arbitrary streamlit apps. See <https://github.com/pymedphys/pymedphys/issues/1422>.
* **[Contributor facing only]** Added the following contributor CLI tools/options:
  * `pymedphys dev tests --mosaiqdb`, to load up the tests that depend on having
    a Microsoft SQL server running. Thanks to [Derek Lane](https://github.com/dg1an3)
    for all of his work building the Mosaiq CI workflow and the first set of
    Mosaiq tests.
  * `pymedphys dev doctests`, run doctests.
  * `pymedphys dev imports`, verify optional import logic by creating a clean
    Python install and attempting to import all modules.
  * `pymedphys dev lint`, run pylint.
  * `pymedphys dev cypress`, load up Cypress for interactively writing and
    running the end-to-end tests.

### Misc changes

* Significant work was undergone to improve the documentation layout. Thanks to
  [Matt Jennings](https://github.com/Matthew-Jennings) for all his work here.
* How Mosaiq username and passwords are saved has been updated. This will
  result in these credentials being requested once more.

## [0.35.0]

### News around this release

* PyMedPhys now has a Discourse group at <https://pymedphys.discourse.group>.
  The goal for this group is to build a community where we can discuss and
  collaborate around all things related to PyMedPhys.

### Breaking changes

* **Developer facing only**: The `--live` parameter within `pymedphys dev docs`
  has been removed.

### New features and enhancements

* `pymedphys dicom listen` stores incoming DICOM objects in a directory
  hierarchy: PatientID/Study Instance UID/Series Instance UID aligning with the
  DICOM Q/R hierarchy, and more suitable for use with tools like dicompyler and
  OnkoDICOM. See PR [#1208](https://github.com/pymedphys/pymedphys/pull/1208)
  for more details.

```{note}
This `pymedphys dicom listen` adjustment changes where a 3rd party or in-house
program would expect to find the DICOM data on the file system compared to the
previous release.

Please raise an issue on GitHub
<https://github.com/pymedphys/pymedphys/issues/new> if you believe changes like
this in the future should be considered a breaking change.
```

* Documentation now uses the new [Jupyter Book](https://jupyterbook.org/) tool
  from the [Executable Book Project](https://executablebooks.org/). Among other
  things this has enabled:
  * Live running of notebook documentation using
    [Thebe](https://thebelab.readthedocs.io/)
  * Discourse commenting now available directly within the hosted documentation
  * The ability to utilise the expanded
    [MyST](https://jupyterbook.org/content/myst.html) Documentation formatting.
* Increased docstring coverage of public functions
* Installation on MacOS (Intel) has been simplified and is now the same as for
  other platforms, thanks to [@termim](https://github.com/termim) who has taken
  on the mantle of maintaining `pymssql`. See PR
  [pymssql#677](https://github.com/pymssql/pymssql/pull/677) for more details.
* Streamlit development now supports reloading during development across the
  whole PyMedPhys library. See PR
  [#1202](https://github.com/pymedphys/pymedphys/pull/1202) for more details.
* A pre-release binary has been built and CI infrastructure around it has begun
  being built. Watch this space for a future release where it will be
  officially distributed. See PR
  [#1192](https://github.com/pymedphys/pymedphys/pull/1192) for more details.
* Create a [`__main__.py`](https://github.com/pymedphys/pymedphys/blob/56667dc84a532179f37a486e61663736c0f43eae/lib/pymedphys/__main__.py#L1-L19)
  so that the PyMedPhys CLI can be called using `python -m pymedphys`.
  * This is to support running the GUI and the tests within the binary.
* Created a `requirements-user.txt`, this will allow users to install PyMedPhys
  from the repo while using the exact dependencies that are being tested within
  the CI. See PR [#1266](https://github.com/pymedphys/pymedphys/pull/1266) for
  more details.
* `pymedphys dev propagate` had the `--copies` and `--pyproject` flags added.
  This allows for subsections of propagate to be undergone instead of the whole
  procedure.

### Bug fixes

* CLI initialisation was delayed by unused tensorflow imports
* Pseudonymisation of Decimal String (e.g. Patient Weight) was failing. See
  [#1244](https://github.com/pymedphys/pymedphys/pull/1244) for more details.
* Pseudonymisation of Date, Time or DateTime elements with embedded UTC offsets
  would fail.
* Improved Mosaiq username and password login. Thank you
  [@nickmenzies](https://github.com/nickmenzies) for reporting. See PR
  [#1199](https://github.com/pymedphys/pymedphys/pull/1199) for more details.
* `pymedphys gui` will use the Python used to run the CLI to boot streamlit as
  opposed to the streamlit able to be found on the user's PATH. See
  [pymedphys/_gui.py](https://github.com/pymedphys/pymedphys/blob/56667dc84a532179f37a486e61663736c0f43eae/lib/pymedphys/_gui.py#L48-L56) for
  more details. This is to support booting the GUI within the binary.
* `dateutil` dependency was removed for compatibility reasons with Streamlit's
  cache. This tool was replaced with an equivalent tool within `pandas`. See
  [pymedphys/_trf/manage/identify.py](https://github.com/pymedphys/pymedphys/blob/56667dc84a532179f37a486e61663736c0f43eae/lib/pymedphys/_trf/manage/identify.py#L31-L66)
  for more details.
* A range of fixes for the testing infrastructure for the case where the
  pymedphys CLI isn't on the user's path.
  * This was to support testing within the binary infrastructure.

### Library structure changes

* All GUI tools that are labelled experimental are now appropriately located
  within the experimental part of the library.

## [0.34.0]

### News around this release

* 🚀 Stuart Swerdloff ([@sjswerdloff](https://github.com/sjswerdloff)) has
  agreed to come on board as a maintainer of PyMedPhys. Thank you Stuart! You
  have been a massive help and encouragement.
* Created an online PyMedPhys GUI. It is accessible from
  <https://app.pymedphys.com>. This is in its early stages and most parts of
  the online GUI are not optimised for use in this fashion.
  * Of note, its main purpose is to demonstrate the GUI functionality. If you
    wish to begin using this GUI in your centre install PyMedPhys on your local
    machine and then start it by calling `pymedphys gui` within a
    terminal/command prompt.
  * The online demo GUI should not have sensitive information submitted to it.
* [@matthewdeancooper](https://github.com/matthewdeancooper) uploaded his
  Masters thesis on deep learning auto-segmentation to
  [the docs](https://docs.pymedphys.com/background/autocontouring.html#details).
* PyMedPhys was featured in a talk at the ACPSEM 2020 Summer School. Both the
  [video](https://simonbiggs.net/acpsem-summer-school-2020-video) and
  [slides](https://simonbiggs.net/acpsem-summer-school-2020-slides) are
  available online.

### "Stable" API changes

#### Breaking changes

* The parameter `fraction_number` within `pymedphys.Delivery.from_dicom` and
  `pymedphys.Delivery.to_dicom` has been changed to `fraction_group_number`.
* The name of the first argument to `pymedphys.Delivery.from_dicom` has been
  changed from `dicom_dataset` to `rtplan`. It now also accepts either a
  `pydicom.Dataset` or a filepath.
* A range of files utilised by `pymedphys.data_path` and related functions
  that contained the words "mudensity", "mu-density", or "mu_density" have
  been replaced with "metersetmap".
* The exceptions that `pymedphys.Delivery.from_mosaiq` raises when either
  no entry in Mosaiq is found (`NoMosaiqEntries`) or multiple entries are found
  (`MultipleMosaiqEntries`) now both inherit from `ValueError` instead of the
  base `Exception` class.

#### Deprecations

* All instances of `mudensity` have been replaced with `metersetmap`. The
  `mudensity` API is still currently available, but it will be removed in a
  future release.
* `pymedphys.Delivery.from_logfile` has been renamed as
  `pymedphys.Delivery.from_trf`. The previous name is still temporarily
  available but it will be removed in a future release.

#### New features

* Added CLI `pymedphys dicom listen` [#1161](https://github.com/pymedphys/pymedphys/pull/1161).
  This begins a DICOM listener which will store the DICOM files sent to it to
  disk. It accepts the arguments `--port`, `--aetitle`, and
  `--storage_directory`. Thanks [@pchlap](https://github.com/pchlap)!

#### Bug fixes

* Sometimes a range of DICOM API calls would require the downloading of a
  baseline DICOM dictionary. This is now distributed with the library.

### GUI changes

#### Logistics changes

* `pymedphys gui` now boots up a multi application index. This index breaks
  applications up into five categories, mature, maturing, raw, beta, and
  experimental.

#### Pseudonymise

* A new pseudonymise application has been created. This allows users to drag
  and drop DICOM files into the GUI and then download the resulting DICOM file
  in its pseudonymised form. Thanks
  [@sjswerdloff](https://github.com/sjswerdloff)!

#### MetersetMap

##### New Features

* The MetersetMap comparison application (which used to be MU density) is now
  able to work with a bare bones configuration file which can be used by just
  dragging and dropping TRF and DICOM files for comparison. See
  [#1117](https://github.com/pymedphys/pymedphys/pull/1117#issue-513765705)
  for details of the configuration file needed.
* Path configuration now supports expansion of `~` to the users home directory.

##### Bug fixes

* In some cases a patient having a middle name would cause the DICOM file
  upload method to crash. Thanks [@mchamberland](https://github.com/mchamberland)
  for reporting in [#1137](https://github.com/pymedphys/pymedphys/issues/1137)
  and thanks [@sjswerdloff](https://github.com/sjswerdloff) for the prompt fix
  in [#1144](https://github.com/pymedphys/pymedphys/pull/1144)!

#### Experimental applications

* A new "anonymise monaco" application has been exposed. This allows the
  back-end Monaco filesystem to be anonymised in such a way that Monaco can
  still open and work with the contents.
* A new "dashboard" application has been exposed. This connects to multiple
  Mosaiq sites and displays the QCLs across each site.
* A new "electrons" application has been exposed. This reads Monaco back-end
  files, extract the electron insert shape and then predicts the corresponding
  insert output factor.
* A new "iviewdb" application has been exposed. This allows for exploration of
  the iView database.
* Work has begun on a new Winston Lutz Arc GUI.

### Configuration changes

#### New keys

* `~/.pymedphys/config.toml` should now include a `version = 1` entry. This
  is to support undergoing breaking changes within `config.toml` but allowing
  PyMedPhys to still read in old configuration files without issue.
* For use within the up-coming Winston-Lutz Arc GUI a new key
  `site.export-directories.iviewdb` has been created.

### Beta API changes

* Nil

### Experimental API changes

#### Breaking changes

* Removed `pymedphys experimental gui`.

#### New Features

* Within `pymedphys.experimental.pseudonymisation` both `pseudonymise` and
  `is_valid_strategy_for_keywords` were added. `pseudonymise` provides
  a convenient simple API for pseudonymisation. See [the API docs](https://docs.pymedphys.com/ref/lib/experimental/pseudonymisation.html#api)
  for more information. Credit to [@sjswerdloff](https://github.com/sjswerdloff)
  for all his work here.

### Developer facing API changes

* The pymedphys library directory has moved to `lib/pymedphys`.
  After this move you will need to rerun `poetry install -E dev`
* The development branch of pymedphys has moved from [master](https://github.com/pymedphys/pymedphys/tree/master)
  to [main](https://github.com/pymedphys/pymedphys/tree/main)
* Documentation is now stored within the library, moving from `docs` to
  `lib/pymedphys/docs`
* Docs can now be built, viewed, and updated with hot-reloading by running
  `poetry run pymedphys dev docs --live`.
* The output directory for the docs building can now be controlled by passing
  an `--output` flag to `pymedphys dev docs`.
* A new CLI utility that propagates a range of files that depend upon each
  other files within the repo are "propagated" by calling
  `poetry run pymedphys dev propagate`. The files created/updated by this
  command are `lib/pymedphys/_version.py`, `requirements.txt` and
  `requirements-dev.txt`, `lib/pymedphys/.pylintrc`,
  `lib/pymedphys/docs/README.rst`, `lib/pymedphys/docs/CHANGELOG.md`, and the
  'extras' field within `pyproject.toml`.
* `pymedphys dev tests` includes simplified flags. `--run-only-slow` can
  be undergone with `--slow`, `--run-only-yarn` with `--cypress`,
  `--run-only-pydicom` with `--pydicom`, and `--run-only-pylinac` with
  `--pylinac`.
* Within cypress end to end testing the custom `cy.start` command now has a
  parameter `app` which refers to the URL app key of the application to be
  tested `http://localhost:8501/?app=${app}`.

## [0.33.0]

### "Stable" API changes

#### Installation changes

* To install pymedphys with all of its user dependencies now the following
  needs to be run:

```bash
pip install pymedphys[user]
```

* When `pip install pymedphys` is called, PyMedPhys will now be installed with
  minimal/no dependencies.
  * Pull request [#1036](https://github.com/pymedphys/pymedphys/pull/1036)

### Beta API changes

Nil

### Experimental API changes

#### Breaking changes

* Removed a range of unmaintained experimental package APIs; film, collimation,
  sinogram, and Profile. The underlying code has not been removed, but they
  are no longer exposed through the APIs.

#### Bug fixes

* Made it so that `import pymedphys.experimental` does not raise an
 `ImportError` when an optional dependency has not been installed.
  * Issue [#1035](https://github.com/pymedphys/pymedphys/issues/1035)
  * Pull request [#1036](https://github.com/pymedphys/pymedphys/pull/1036)
* Fixed a bug where pseudonymisation wouldn't work when in cases of identifying
  sequences.
  * Issue [#1034](https://github.com/pymedphys/pymedphys/issues/1034)
  * Pull request [#1038](https://github.com/pymedphys/pymedphys/pull/1038)

#### New Features

* Created a Mosaiq QCL dashboard that reads the QCLs from multiple Mosaiq
  installs across multiple sites. [_gui/streamlit/dashboard.py#L20-L78](https://github.com/pymedphys/pymedphys/blob/d0dbaf3d8ac15690602e3c92ab19704d450dad5a/pymedphys/_gui/streamlit/dashboard.py#L20-L78)

### Internal Changes

* Made it so that when developing streamlit apps an autoreload function can
  be used to have the streamlit app update on dependency changes.
  [_streamlit/rerun.py#L89-L96](https://github.com/pymedphys/pymedphys/blob/d0dbaf3d8ac15690602e3c92ab19704d450dad5a/pymedphys/_streamlit/rerun.py#L89-L96)
  * See discussion over on [streamlit's issue tracker](https://github.com/streamlit/streamlit/issues/653#issuecomment-678954708)
* Internal Mosaiq connection function now accepts custom functions for
  prompting the user for their database username, password, and prompting the
  user with responses. [_mosaiq/connect.py#L134-L147](https://github.com/pymedphys/pymedphys/blob/d0dbaf3d8ac15690602e3c92ab19704d450dad5a/pymedphys/_mosaiq/connect.py#L134-L147)
  * This was utilised for connecting to a fresh database within streamlit.
    [_streamlit/mosaiq.py#L20-L50](https://github.com/pymedphys/pymedphys/blob/d0dbaf3d8ac15690602e3c92ab19704d450dad5a/pymedphys/_streamlit/mosaiq.py#L20-L50)
* Created tool to manage `pyproject.toml` extras. [scripts/propagate-extras.py#L26-L51](https://github.com/pymedphys/pymedphys/blob/d0dbaf3d8ac15690602e3c92ab19704d450dad5a/scripts/propagate-extras.py#L26-L51)
  * See discussion on the poetry
  [issue tracker](https://github.com/python-poetry/poetry/issues/1644#issuecomment-688256688)
  for more details.

## [0.32.0]

### "Stable" API changes

#### Bug fixes

* Fixed bug in the PyMedPhys trf decoding logic where leaf pairs 77, 78, 79,
  and 80 on the Y2 bank were decoded into having the wrong sign.
  * See issue [#968](https://github.com/pymedphys/pymedphys/issues/968) and
    pull request [#970](https://github.com/pymedphys/pymedphys/pull/970) for
    more details.

#### Breaking changes

* `config.toml` has undergone a few breaking changes.
  * See [the example](https://github.com/pymedphys/pymedphys/blob/1241924d027163fccdc95750db0c984805bb83d4/site-specific/cancer-care-associates/config.toml)
    for a working config file.
  * See below for a comparison highlighting the key differences.

```toml
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
```

#### New Features

* Two new optional keywords were added to `pymedphys.dicom.anonymise`. These
  are `replacement_strategy` and `identifying_keywords`. This was designed to
  support alternative anonymisation methods. The API to the anonymise function
  is being flagged for a rework and simplification for which a breaking change
  is likely to occur in the near future.
* Added ability to configure logging via `config.toml`.

#### Data file changes

Refers to the data files accessible via `pymedphys.data_path`,
`pymedphys.zip_data_paths`, and `pymedphys.zenodo_data_paths`.

* The data file `pinnacle_test_data_no_image.zip` was removed and its contents
  were moved into `pinnacle_test_data.zip`.
* Data files `treatment-record-anonymisation.zip`, `negative-mu-density.trf`,
  and `trf-references-and-baselines.zip` were added.

### Beta API changes

Nil

### Experimental API changes

#### New Features

* Added pseudonymisation as an experimental extension of anonymise.
  * This API is undergoing refinement, however in its current form it is
    accessible via
    `pymedphys.experimental.pseudonymisation.pseudonymisation_dispatch`
    and `pymedphys.experimental.pseudonymisation.get_default_pseudonymisation_keywords`.
    These are designed to be passed to the new keywords `replacement_strategy`
    and `identifying_keywords` within `pymedphys.dicom.anonymise`.
  * The pseudonymisation strategy uses SHA3_256 hashing for text and UIDs, date
    shifting for dates, and jittering for Age. The intent is to enable sets of
    data that are correlated to remain correlated, and to prevent uncorrelated
    patient/study/series from clashing.
* Added experimental pseudonymisation CLI. Callable via
  `pymedphys experimental dicom anonymise --pseudo path/to/dicom.dcm`

* Added `pymedphys experimental gui`. This is a testing ground for new GUIs
  that are intended to appear within `pymedphys gui` in the future. The GUIs
  exposed under this experimental scope are minimally tested.
  * At this point in time, the new GUIs include a GUI index, an electron
    insert factor prediction tool, and a Monaco anonymisation tool.

#### Bug Fixes

* Pinnacle Export Tool now allows for the trial to be set using the CLI.
  See issue [#973](https://github.com/pymedphys/pymedphys/issues/973)
  and pull request [#995](https://github.com/pymedphys/pymedphys/pull/995) for
  more details.
* Fixed bug where the dose grid in the Pinnacle Export Tool was only correct
  when patients were in HFS. See
  [#929](https://github.com/pymedphys/pymedphys/pull/929) for more details.

## [0.31.0]

### "Stable" API changes

#### Critical bug fixes

* Fixed bug where `pymedphys dicom anonymise` and `pymedphys.dicom.anonymise`
  would not anonymise nested tags. Thanks
  [sjswerdloff](https://github.com/sjswerdloff) for finding and fixing
  [#920](https://github.com/pymedphys/pymedphys/pull/920).

#### Breaking changes

* Removed the `--publish` option from CLI `pymedphys dev docs`.
* Moved `pymedphys logfile orchestration` to `pymedphys trf orchestrate`

#### New features

* `pymedphys.zenodo_data_paths` has a new optional parameter `filenames` that
  can be used to only download some files.
* `pymedphys.data_path` has a new optional parameter `hash_filepath` which can
  be used to provide a custom hash record.
* Added usage warning to the MU Density GUI.

#### Deprecations

* `pymedphys.read_trf` has been replaced with `pymedphys.trf.read`. The old
  API is still available, but will be removed in a future version.

#### Bug fixes

* Cache data downloads now also retry when a `ConnectionResetError` occurs.

### Beta API changes

#### New features

* A new `pymedphys.beta` module created. This is intended to allow a section
  of the API to be exposed and iterated on but having breaking changes not
  induce a major version bump (when PyMedPhys goes to `v1.0.0+`)
* Added `pymedphys.beta.trf.identify` to allow the usage of Mosaiq to identify
  a trf logfile.

### Experimental API changes

#### Breaking changes

* Instances of `labs` has been changed to `experimental`. This affects all
  imports from the labs and the CLI usage.

#### Bug fixes

* Fixed issue with Pinnacle Export Tool crashing when an image is missing from
  the archive.

## [0.30.0]

### Breaking changes

* Removed the proof of concept `pymedphys bundle` CLI as well all of its
  associated code.
* Removed a range of unused files from the `pymedphys.data_path` API.
* The previous install options `pip install pymedphys[pytest]` and
  `pip install pymedphys[pylint]` have been removed and replaced with
  `pip install pymedphys[tests]`.

### New Features

* Added a new toolbox for retrieving PTW Quickcheck measurement data and write
  it to a csv file.
  `pymedphys labs quickcheck to-csv your.quickcheck.ip path/to/output.csv`
  * See [labs/quickcheck/qcheck.py](https://github.com/pymedphys/pymedphys/blob/2d5148e2eabce3a6a4fd54e43e7dc8d4e050f5ed/pymedphys/labs/quickcheck/qcheck.py)
* Added `pymedphys dev tests` to the CLI.
  * Moved all of tests into the pymedphys repo itself. Now the automated
    testing suite is able to be run from a pypi install.
  * This CLI has options such as `--run-only-pydicom`, `--run-only-slow`, and
    `--run-only-pylinac` so that upstream tools can run tests on this
    downstream project.
  * These extra options are directly passed through to `pytest`. To achieve
    this, made the `pymedphys` CLI be able to optionally handle arbitrary
    commands.
* Made the Zenodo download tool retry up to four times should the download
  fail.
* Added DICOM helpers functionality and updated the Mosaiq helpers as a part of
  the UTHSCSA TPS/OIS comparison project. Not yet exposed as part of the API.
  See [_mosaiq/helpers.py#L353-L482](https://github.com/pymedphys/pymedphys/blob/2d5148e2eabce3a6a4fd54e43e7dc8d4e050f5ed/pymedphys/_mosaiq/helpers.py#L353-L482)
* Added more debugging strings to the iCOM CLI. See these outputs by running
  `pymedphys --debug icom listen external.nss.ip.address your/output/directory`
  * These were added to support remotely debugging the iCOM listen software.
    To see the conversation around debugging that tool see the
    [PyMedPhys forum discussion](https://groups.google.com/forum/#!topic/pymedphys/2LczVpmc_Ak)
* Format of MU in logging display now rounded to one decimal.

### Dependency changes

* Now depending on `pylibjpeg-libjpeg` in order to decode lossless-jpeg files.
* `m2r` is no longer used to build the docs.
* No longer using `tox` for tests.

### Bug fixes

* Fixed an issue where the iCOM listener could not handle Machine IDs that
  were not entirely an integer.
  * See [_icom/mappings.py#L6](https://github.com/pymedphys/pymedphys/blob/2d5148e2eabce3a6a4fd54e43e7dc8d4e050f5ed/pymedphys/_icom/mappings.py#L6)
    for changes.
  * See the [PyMedPhys forum discussion](https://groups.google.com/d/msg/pymedphys/2LczVpmc_Ak/c5nUeUfQAQAJ) for details.
* Fixed a case where on some Windows environments `pymedphys dev docs` would
  not run.
* Fixed a case where on some Windows environments `pymedphys gui` would not
  run.
* Fixed issue where the `pymedphys logfile orchestration` CLI would not be able
  to create an `index.json`, or a range of the needed directories on its first
  run.
  * See the [PyMedPhys forum discussion](https://groups.google.com/d/msg/pymedphys/2LczVpmc_Ak/5mFZig1cAgAJ) for more details.

### Documentation updates

* Fixed an issue where the displayed CSV files for configuring
  `pymedphys logfile orchestration` would actually cause an error due to excess
  spaces used for display purposes.
  * See the [PyMedPhys forum discussion](https://groups.google.com/d/msg/pymedphys/2LczVpmc_Ak/m41v_LVRAgAJ) for more details.

### Development changes

* Removed any file that was larger than 300 kB from the git history bring down
  clone times to a manageable state.
  * The `pre-commit` tool now does not allow commits greater than 300 kB.
  * All testing files that were larger than 300 kB have been moved to Zenodo.
* All tests have been moved from `/tests` into `/pymedphys/tests`, running
  these tests can now be undergone by calling `pymedphys dev tests`
  * No longer using `tox`.

## [0.29.1]

### Bug fixes

* Fix issue in some Windows environments where running `pymedphys gui` would
  not find the streamlit installation. [_gui/__init__.py](https://github.com/pymedphys/pymedphys/blob/03ba546b603edcbaf7b2b33c6367146a95142d0d/pymedphys/_gui/__init__.py#L43)

## [0.29.0]

### Breaking changes

* Changed the `patient_directories` icom parameter to accept a list of paths
  instead of a single path within the pymedphys `config.toml`. [config.toml#L67-L72](https://github.com/pymedphys/pymedphys/blob/7a08a94185f94b1f7df304de8bd0274f0f1fcbc9/examples/site-specific/cancer-care-associates/config.toml#L67-L72)
* Changed `pymedphys gui` iCOM path resolution logic to instead search over
  a list of paths instead of just one path as before. [mudensity-compare.py#L668-L670](https://github.com/pymedphys/pymedphys/blob/7a08a94185f94b1f7df304de8bd0274f0f1fcbc9/pymedphys/_gui/streamlit/mudensity-compare.py#L668-L670)

## [0.28.0]

### Overview

This release primarily focused on changes regarding the iCOM listener and the
PyMedPhys GUI that utilises these iCOM records.

### Breaking changes

* Removed the `pymedphys icom archive` CLI command, this archiving is now built
  directly into the listener itself.

### New Features

* The `pymedphys icom listener` CLI command now will collect the icom stream
  into beam delivery batches and index them by patient name. This functionality
  used to be undergone within the `pymedphys icom archive` CLI, but this
  functionality has now been merged into the listener. [listener.py#L79](https://github.com/pymedphys/pymedphys/blob/d40a5ed238b2035bac00da1cb623c7f496ed0950/pymedphys/_icom/listener.py#L79)
* Should an error occur within `pymedphys icom listener` CLI it will now pause
  for 15 minutes and then reattempt a connection.
* Add in extra sanity checks within the iCOM patient indexing tooling.
* Added a `--debug` and `--verbose` flag to the PyMedPhys CLI which allows
  users to set the logging level. These logging levels are currently only
  utilised within the `pymedphys icom listen` CLI. [cli/main.py#L51-L70](https://github.com/pymedphys/pymedphys/blob/9c7c7e3c2d7fb49d30b418dca2fa28e6982ff97e/pymedphys/cli/main.py#L51-L70)

### Bug fixes

* Reduced the buffer size of the iCOM listener. [listener.py#L9](https://github.com/pymedphys/pymedphys/blob/d40a5ed238b2035bac00da1cb623c7f496ed0950/pymedphys/_icom/listener.py#L9)
* If either the listener is turned off and then on again, or it is interrupted
  the next time an iCOM stream socket is opened the Linac appears to send a
  larger batch containing prior irradiations. The listener code was adjusted
  to handle these extra bursts. [listener.py#L57-L83](https://github.com/pymedphys/pymedphys/blob/d40a5ed238b2035bac00da1cb623c7f496ed0950/pymedphys/_icom/listener.py#L57-L83)
* Made PyMedPhys GUI skip name formatting attempt if the original patient name
  format was not as expected. [mudensity-compare.py#L733-L738](https://github.com/pymedphys/pymedphys/blob/d40a5ed238b2035bac00da1cb623c7f496ed0950/pymedphys/_gui/streamlit/mudensity-compare.py#L733-L738)

## [0.27.0]

### New Features

* Added an optional `--structures` flag to `pymedphys dicom merge-contours`.
  This allows you to only compute the merge for those structures named.

## [0.26.0]

### New Features

* Created a function to merge overlapping contours that have the same name
  within a DICOM structure file.
  * Underlying function -- <https://github.com/pymedphys/pymedphys/blob/8b9284a8bc9a948646c9d8c0723d9959c61ae089/pymedphys/_dicom/structure/merge.py#L172-L200>
  * API exposure -- <https://github.com/pymedphys/pymedphys/blob/8b9284a8bc9a948646c9d8c0723d9959c61ae089/pymedphys/dicom.py#L13>
* Exposed the above command as a part of the CLI. It is runnable with `pymedphys dicom merge-contours`
  * CLI exposure -- <https://github.com/pymedphys/pymedphys/blob/8b9284a8bc9a948646c9d8c0723d9959c61ae089/pymedphys/cli/dicom.py#L42-L50>

## [0.25.1]

### Dependency Changes

* Now included `psutil` as an optional dependency.

### Quality of life improvements

* Now raises a descriptive error when a DICOM RT plan file's control point is
  missing a cumulative meterset weight.
  <https://github.com/pymedphys/pymedphys/blob/dfd418a6dd1b8b57ba6bbfd27a498596477ceb6f/pymedphys/_dicom/delivery/core.py#L180-L196>
* When running `pymedphys gui` for the first time, no longer does `streamlit`
  request credentials.
  <https://github.com/pymedphys/pymedphys/blob/dfd418a6dd1b8b57ba6bbfd27a498596477ceb6f/pymedphys/_gui/__init__.py#L24-L36>

### Development changes

* Implemented Cypress GUI testing infrastructure into the CI workflow. See
  details at <https://dashboard.cypress.io/projects/tgt8f6/runs>.
  * Tests -- <https://github.com/pymedphys/pymedphys/blob/dfd418a6dd1b8b57ba6bbfd27a498596477ceb6f/tests/e2e/cypress/integration/streamlit/mudensity-compare.js>
  * CI config -- <https://github.com/pymedphys/pymedphys/blob/dfd418a6dd1b8b57ba6bbfd27a498596477ceb6f/.github/workflows/cypress.yml>

## [0.25.0]

### New Features

* Created the command line tool `pymedphys gui` which boots the GUI for
  PyMedPhys within your browser. GUI at this stage is quite minimal.
* Created a tool to handle a PyMedPhys config file, by default stored within
  `~/.pymedphys/.config.toml`. That config file can have a `redirect` field
  to allow configuration to be stored in a different location such as
  within a git repo, or a network drive.
* `pymedphys.zip_data_paths` now has a new optional parameter
  `extract_directory`. When this parameter is passed the contents of the zip
  downloaded zip data will be extracted to the provided directory. For example
  now the following is possible:

```python
import pathlib

import pymedphys

CWD = pathlib.Path.cwd()
pymedphys.zip_data_paths("mu-density-gui-e2e-data.zip", extract_directory=CWD)
```

* `pymedphys.Delivery.from_dicom()` now supports step and shoot and 3DCRT DICOM
  plan files.
* Work on `pymedphys.Delivery.from_monaco()` was undergone with an attempt to
  support step and shoot plans. This work was preliminary.
* Created a utility to pretty print patient names
* Added ground work for e2e testing of `pymedphys gui` with the cypress tool.

## [0.24.3]

### Bug Fixes

* Within the bundle created by `pymedphys bundle` fixed a bug where
  the streamlit server will not start due stdout not flushing.

## [0.24.2]

### Bug Fixes

* Within the bundle created by `pymedphys bundle` fixed a bug where sometimes
  the streamlit server would not start should a stdout race condition occur.

## [0.24.1]

### Bug Fixes

* Include `matplotlib` within `streamlit` bundle. Streamlit requires this but
  has not labeled it as a dependency.
* Call `yarn` from `os.system`, for some reason on Windows
  `subprocess.check_call` could not find `yarn` on the path, although on Linux
  this worked fine.

## [0.24.0]

### Breaking Changes

* If `pymedphys.mosaiq.connect` is passed a list of length one, it will now
  return a cursor within a list of length 1 instead of just returning a cursor
  by itself.

### New Features

* Added a `pymedphys bundle` cli function which creates an electron streamlit
  installation bundle.
* Added the 'all' fractions option to `Delivery.from_dicom` which can be used
  as `pymedphys.Delivery.from_dicom(dicom_file, fraction_number='all')`
* Made the iCOM patient archiving only save the data if MU was delivered.
* Added wlutz mock image generation functions
* Handle more Monaco `tel.1` cases within `Delivery.from_monaco`
* `get_patient_name` added to `pymedphys._mosaiq.helpers`

### Algorithm Adjustments

* Wlutz bb finding cost function adjusted
  * Note, wlutz algorithm still not ready for the prime time

## [0.23.0]

### Breaking Changes

* Removed `jupyter`, `bundle`, and `app` sub commands from the CLI.
* Removed the `gui` and `jupyter` optional extra installation commands.
* In order to support Python 3.8, the `pymssql` dependency needed to be
  removed for that Python version. All tools that make SQL calls to Mosaiq
  will not currently work on Python 3.8.

### New Features

* PyMedPhys now is able to be installed on Python 3.8.

### Dependency Changes

* No longer depend upon `pymssql` for Python 3.8.

### Bug Fixes

* Fix `pymedphys._monaco` package path.
* Fixed issue where the following header adjustment DICOM CLI tools may not
  work with `pydicom==1.4.2`. See
  <https://github.com/pymedphys/pymedphys/pull/747> and
  <https://github.com/pymedphys/pymedphys/pull/748>.
  * `pymedphys dicom adjust-machine-name`
  * `pymedphys dicom adjust-RED`
  * `pymedphys dicom adjust-RED-by-structure-name`

## [0.22.0]

### New Features

* Implemented `from_icom` method on the `pymedphys.Delivery` object. This
  was to support calculating an MU Density from an iCOM stream.
  * See <https://github.com/pymedphys/pymedphys/pull/733>

## [0.21.0]

### Dependency Changes

* Once again made `shapely` a default dependency with the aim to make
  installation be "batteries included".
  * `Shapely` now ships wheels for Windows. This means `shapely` will install
    normally with pip. See
    <https://github.com/Toblerity/Shapely/issues/815#issuecomment-579945334>
* Pinned `pydicom` due to a currently unknown issue with a new version breaking
  a `pymedphys` test.

## [0.20.0]

### New Features

* Expose some portions of the Winston Lutz API.
* Add iCom listener CLI.

## [0.19.0]

### Breaking Changes

* Made shapely an optional dependency once more. No longer depending on
  `shapely-helper`.
  * Shapely can be installed by running `pip install pymedphys[difficult]==0.19.0`
  * This fixes an issue where `pip` refuses to install due to the
    `shapely-helper` workaround.

## [0.18.0]

### Breaking Changes

* Removed the optional extras tags of `library`, `labs`, and `difficult`. All
  of these now install by default. For example PyMedPhys can no longer be
  installed with `pip install pymedphys[library]`.

### Quality of life improvements

* Installation of PyMedPhys has been reverted to including all of its primary
  dependencies. This was done to make the default install less confusing.
  Nevertheless, these dependencies are mostly optional and if you wish you can
  install with `pip install pymedphys --no-deps` to have a minimal
  installation.
* Made a `shapely-helpers` package which automatically handles installation
  of `shapely` on Windows. PyMedPhys now depends on `shapely-helpers` instead
  of `shapely`.

## [0.17.1]

### Quality of life improvements

* Made wlutz determination less fussy.

## [0.17.0]

### New Features

* Initial alpha release of an experimental JupyterLab application bundler.
  Run with `pymedphys bundle` in a directory that contains a `notebooks` dir
  and a `requirements.txt` file.

## [0.16.3]

### Bug Fixes

* Gracefully reject ipython inspection for optional modules by returning `None`
  for '__file__' attribute requests for modules that are not currently
  installed.

## [0.16.2]

### Bug Fixes

* Fixed bug with optional dependency logic within `apipkg`. Occurred whenever
  an optional submodule was called, for example `scipy.interpolate`.

## [0.16.1]

### Aesthetic Changes

* Updated the badges reported within the README.

## [0.16.0]

### Package changes

* The license of the package has changed from `AGPL-3.0-or-later` to
 `Apache-2.0`.

### New Features

* Expose `pymedphys.electronfactors.plot_model` as part of the public API.

## [0.15.0]

### New Features

* Experimental support for Elekta Unity trf log file decoding.

## [0.14.3]

### Package changes

* Updated wheel to correctly handle optional dependencies.

## [0.14.2]

### Bug Fixes

* Vendored in `apipkg` due to PyPI installation issues.

## [0.14.1]

### Bug Fixes

* Given the input to `pymedphys.gamma` is unitless, removed the units from
  the logging output of gamma. See <https://github.com/pymedphys/pymedphys/issues/611>

## [0.14.0]

### Breaking Changes

* Moved `pymedphys pinnacle` cli command to be nested under
 `pymedphys labs pinnacle`

### Dependency Changes

* Made the greater majority of the pymedphys dependencies optional. Should a
  dependency be required during usage an error is raised informing the user to
  install the package. To install all pymedphys dependencies as before now run
  `pip install pymedphys[library,labs]==0.14.0`.

## [0.13.2]

### Bug Fix

* Fixed issue where `pymedphys.mosaiq.connect` would not work for just one
  hostname.

## [0.13.1]

### Bug Fix

* Fixed issue where `pymedphys.mosaiq.connect` would not work for just one
  hostname.

## [0.13.0]

### New Feature

* Made `pymedphys.mosaiq.execute` a part of the API.

## [0.12.2]

### Package changes

* Fixed version number within package.

## [0.12.1]

### Package changes

* Re-added the license classifier to the PyPI upload.

## [0.12.0]

### Breaking Changes

* The API has undergone a complete redesign. Expect most code to be broken with
  this release.

## [0.11.0]

### Breaking Changes

* Within `dose_from_dataset` the `reshape` parameter has been removed.
* Removed the following functions:
  * `load_dicom_data`
  * `axes_and_dose_from_dicom`
  * `extract_depth_dose`
  * `extract_profiles`

### New Features

* Added functions `pymedphys.dicom.depth_dose` and `pymedphys.dicom.profiles`.
* Exposed the `trf2pandas` function via `pymedphys.fileformats.trf2pandas`.

### Improvements

* Made the resolution detection of `pymedphys.plt.pcolormesh_grid` more robust.

## [0.10.0]

### New Features

* Re-exposed `convert2_ratio_perim_area` and `create_transformed_mesh` from
  `pymedphys.electronfactors`.
* Pinnacle module providing a tool to export raw Pinnacle data to DICOM
  objects.
  * A CLI is provided: See
  [the Pinnacle CLI docs](https://docs.pymedphys.com/user/interfaces/cli/pinnacle.html).
  * As well as an API: See
  [the Pinnacle library docs](https://docs.pymedphys.com/user/library/pinnacle.html).

## [0.9.0] -- 2019/06/06

### New Features

* Re-exposed `multi_mosaiq_connect`, `multi_fetch_and_verify_mosaiq`,
  `get_qcls_by_date`, and `get_staff_name` from `pymedphys.msq`.

## [0.8.4] -- 2019/06/04

### Package changes

* Made `xlwings` not install by default if system is `Linux` within `setup.py`
* Removed unreleased `jupyter` based GUI

## [0.8.3] -- 2019/06/04

### Package changes

* Updated MANIFEST file within `pymedphys_fileformats` to appropriately include
  LICENSE files.

## [0.8.2] -- 2019/06/01

### Package changes

* Included license files within the subpackage distributions

## [0.8.1] -- 2019/06/01

### Dependency changes

* Removed numpy version upper-limit

## [0.8.0] -- 2019/06/01

### Breaking Changes

* `DeliveryData` has been renamed to `Delivery` and is now importable by
  running `from pymedphys import Delivery`
  * A range of functions that used to use `DeliveryData` are now instead
    accessible as methods on the `Delivery` object.
* A large number of functions that were previously exposed have now been made
  private in preparation for eventually stabilising the API. No function that
  was within the documentation has been removed. If there is a function that
  you were using that you would like to be exposed via `import` again, please
  let us know by
  [opening an issue on GitHub](https://github.com/pymedphys/pymedphys/issues)
  and we will happily re-expose it! However, please bear in mind that the
  entire API that is currently exposed will likely change before a 1.0.0
  release.
* `anonymise_dicom_dataset()` has been renamed to `anonymise_dataset()` to
  remove redundant labelling.
* `mu_density_from_delivery_data` moved from the `msq` module to the
  `mudensity` module.
* `compare_mosaiq_fields` moved from the `msq` module into the `plancompare`
  module.
* `pymedphys.dicom.get_structure_aligned_cube` has had its `x0` parameter
  changed from required to optional. It is no longer the first parameter
  passed to the function. By default `x0` is now determined using the min/max
  bounds of the structure.
* The DICOM coordinate extraction functions - `extract_dicom_patient_xyz()`,
  `extract_iec_patient_xyz()` and `extract_iec_fixed_xyz()` - have been
  combined into a single function called `xyz_from_dataset()`. The x, y, z axes
  can still be returned in either the DICOM, IEC fixed or IEC patient
  coordinate systems by passing the following case-insensitive strings to the
  `coord_system=` parameter of `xyz_from_dataset()`:
  * DICOM: `'d'` or `'DICOM'`
  * IEC fixed: `'f'`, `'fixed'` or `'IEC fixed'`
  * IEC patient: `'p'`, `'patient'` or `'IEC patient'`
* `gamma_dicom` now take datasets as opposed to filenames

### New Features

* A DICOM anonymisation CLI! See
  [the DICOM Files CLI docs](../user/interfaces/cli/dicom.rst).
* `anonymise_file()` and `anonymise_directory()`:
  * two new DICOM anonymisation
    wrapper functions that take a DICOM file and a directory as respective
    arguments.
* `is_anonymised_dataset()`, `is_anonymised_file()` and
  `is_anonymised_directory()`:
  * three new functions that check whether a pydicom
    dataset, a DICOM file or all files within a directory have been anonymised,
    respectively.
* `coords_from_xyz_axes()` is a previously internal function that has now been
  exposed in the API. It converts x, y, z axes returned by `xyz_from_dataset()`
  into a full grid of coordinate triplets that correspond to the original grid
  (pixel array or dose grid).

## [0.7.2] -- 2019/04/05

### Dependency changes

* Removed numpy version upper-limit

## [0.7.1] -- 2019/04/05

### Performance Improvements

* reduced PyPI package size by removing unnecessary development testing files.

## [0.7.0] -- 2019/04/05

### Breaking Changes

* `anonymise_dicom` has been renamed to `anonymise_dicom_dataset`
* The CLI interface `trf2csv` has been replaced with `pymedphys trf to-csv`.
  This has the same usage, just a changed name to come in line with the rest of
  the CLI interfaces exposed by PyMedPhys.

### New Features

* Implementing a suite of Dicom objects, currently a work in progress:
  * `DicomBase`, a base DICOM class that wraps `pydicom`'s `Dataset` object.
    This class includes additions such as an anonymisation method.
  * `DicomImage`, designed to hold a single DICOM image slice. Might someday
    contain methods such as `resample` and the like.
  * `DicomSeries`, a series of `DicomImage` objects creating a CT dataset.
  * `DicomStructure`, designed to house DICOM structure datasets.
  * `DicomPlan`, a class that holds RT plan DICOM datasets.
  * `DicomDose`, a class that to hold RT DICOM dose datasets. It has helper
    functions and parameters such as coordinate transforms built into it.
  * `DicomStudy`, a class designed to hold an interrelated set of `DicomDose`,
    `DicomPlan`, `DicomStructure`, and `DicomSeries`. Not every type is
    required to create a `DicomStudy`. Certain methods will be
    available on `DicomStudy` depending what is housed within it. For example
    having both `DicomDose` and `DicomStructure` should enable DVH based
    methods.
  * `DicomCollection`, a class that can hold multiple studies, interrelated or
    not. A common use case that will likely be implemented is
    `DicomCollection.from_directory(directory_path)` which would pull all DICOM
    files nested within a directory and sort them into `DicomStudy` objects
    based on their header UIDs.
* Added CLI commands for a WIP docker server, logfile orchestration, and DICOM
  editor tools.
* Added a range of xlwings tools that allow the use of PyMedPhys functions
  within Excel
* Added rudimentary code to pull profiles from Mephysto
  files.
* The previously separate `decodetrf` library is now distributed within
  PyMedPhys. You can now simply install PyMedPhys and run
  `pymedphys trf to-csv` within the command line to convert `.trf` files into
  `.csv` files.

## [0.6.0] -- 2019/03/15

### Breaking Changes

* All uses of "dcm" in directory names, module names, function names, etc.
  have been converted to "dicom". Anything that makes use of this code will
  need to be adjusted accordingly. Required changes include:
  * `pymedphys.dcm` --> `pymedphys.dicom`
  * `coords_and_dose_from_dcm()` --> `coords_and_dose_from_dicom()`
  * `dcmfromdict()` --> `dicom_dataset_from_dict()`
  * `gamma_dcm()` --> `gamma_dicom()`
* MU Density related functions are no longer available under the
  `pymedphys.coll` package, instead they are found within `pymedphys.mudensity`
  package.
* The DICOM coordinate extraction functions now return simple tuples rather
  than `Coords` namedtuples:
  * `extract_dicom_patient_xyz()`
  * `extract_iec_patient_xyz()`
  * `extract_iec_fixed_xyz()`

### New Features

* DICOM anonymisation now permits replacing deidentified values with suitable
  "dummy" values. This helps to maintain compatibility with DICOM software that
  includes checks (beyond those specified in the DICOM Standard) of valid DICOM
  tag values. Replacing tags with dummy values upon anonymisation is now the
  default behaviour.
* A set of 3D coordinate transformation functions, including rotations (passive
  or active) and translations. Transformations may be applied to a single
  coordinate triplet (an `ndarray`) or a list of arbitrarily many coordinate
  triplets (a 3 x n `ndarray`). **NB**: Documentation forthcoming.

### Code Refactoring

* All uses of `dcm` as a variable name for instances of PyDicom Datasets have
  been converted to `ds` to match PyDicom convention.

## [0.5.1] -- 2019/01/05

### New Features

* Began keeping record of changes in `changelog.md`

[0.37.1]: https://github.com/pymedphys/pymedphys/compare/v0.37.0...v0.37.1
[0.37.0]: https://github.com/pymedphys/pymedphys/compare/v0.36.1...v0.37.0
[0.36.1]: https://github.com/pymedphys/pymedphys/compare/v0.36.0...v0.36.1
[0.36.0]: https://github.com/pymedphys/pymedphys/compare/v0.35.0...v0.36.0
[0.35.0]: https://github.com/pymedphys/pymedphys/compare/v0.34.0...v0.35.0
[0.34.0]: https://github.com/pymedphys/pymedphys/compare/v0.33.0...v0.34.0
[0.33.0]: https://github.com/pymedphys/pymedphys/compare/v0.32.0...v0.33.0
[0.32.0]: https://github.com/pymedphys/pymedphys/compare/v0.31.0...v0.32.0
[0.31.0]: https://github.com/pymedphys/pymedphys/compare/v0.30.0...v0.31.0
[0.30.0]: https://github.com/pymedphys/pymedphys/compare/v0.29.1...v0.30.0
[0.29.1]: https://github.com/pymedphys/pymedphys/compare/v0.29.0...v0.29.1
[0.29.0]: https://github.com/pymedphys/pymedphys/compare/v0.28.0...v0.29.0
[0.28.0]: https://github.com/pymedphys/pymedphys/compare/v0.27.0...v0.28.0
[0.27.0]: https://github.com/pymedphys/pymedphys/compare/v0.26.0...v0.27.0
[0.26.0]: https://github.com/pymedphys/pymedphys/compare/v0.25.1...v0.26.0
[0.25.1]: https://github.com/pymedphys/pymedphys/compare/v0.25.0...v0.25.1
[0.25.0]: https://github.com/pymedphys/pymedphys/compare/v0.24.3...v0.25.0
[0.24.3]: https://github.com/pymedphys/pymedphys/compare/v0.24.2...v0.24.3
[0.24.2]: https://github.com/pymedphys/pymedphys/compare/v0.24.1...v0.24.2
[0.24.1]: https://github.com/pymedphys/pymedphys/compare/v0.24.0...v0.24.1
[0.24.0]: https://github.com/pymedphys/pymedphys/compare/v0.23.0...v0.24.0
[0.23.0]: https://github.com/pymedphys/pymedphys/compare/v0.22.0...v0.23.0
[0.22.0]: https://github.com/pymedphys/pymedphys/compare/v0.21.0...v0.22.0
[0.21.0]: https://github.com/pymedphys/pymedphys/compare/v0.20.0...v0.21.0
[0.20.0]: https://github.com/pymedphys/pymedphys/compare/v0.19.0...v0.20.0
[0.19.0]: https://github.com/pymedphys/pymedphys/compare/v0.18.0...v0.19.0
[0.18.0]: https://github.com/pymedphys/pymedphys/compare/v0.17.1...v0.18.0
[0.17.1]: https://github.com/pymedphys/pymedphys/compare/v0.17.0...v0.17.1
[0.17.0]: https://github.com/pymedphys/pymedphys/compare/v0.16.3...v0.17.0
[0.16.3]: https://github.com/pymedphys/pymedphys/compare/v0.16.2...v0.16.3
[0.16.2]: https://github.com/pymedphys/pymedphys/compare/v0.16.1...v0.16.2
[0.16.1]: https://github.com/pymedphys/pymedphys/compare/v0.16.0...v0.16.1
[0.16.0]: https://github.com/pymedphys/pymedphys/compare/v0.15.0...v0.16.0
[0.15.0]: https://github.com/pymedphys/pymedphys/compare/v0.14.3...v0.15.0
[0.14.3]: https://github.com/pymedphys/pymedphys/compare/v0.14.2...v0.14.3
[0.14.2]: https://github.com/pymedphys/pymedphys/compare/v0.14.1...v0.14.2
[0.14.1]: https://github.com/pymedphys/pymedphys/compare/v0.14.0...v0.14.1
[0.14.0]: https://github.com/pymedphys/pymedphys/compare/v0.13.2...v0.14.0
[0.13.2]: https://github.com/pymedphys/pymedphys/compare/v0.13.1...v0.13.2
[0.13.1]: https://github.com/pymedphys/pymedphys/compare/v0.13.0...v0.13.1
[0.13.0]: https://github.com/pymedphys/pymedphys/compare/v0.12.2...v0.13.0
[0.12.2]: https://github.com/pymedphys/pymedphys/compare/v0.12.1...v0.12.2
[0.12.1]: https://github.com/pymedphys/pymedphys/compare/v0.12.0...v0.12.1
[0.12.0]: https://github.com/pymedphys/pymedphys/compare/v0.11.0...v0.12.0
[0.11.0]: https://github.com/pymedphys/pymedphys/compare/v0.10.0...v0.11.0
[0.10.0]: https://github.com/pymedphys/pymedphys/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/pymedphys/pymedphys/compare/v0.8.4...v0.9.0
[0.8.4]: https://github.com/pymedphys/pymedphys/compare/v0.8.3...v0.8.4
[0.8.3]: https://github.com/pymedphys/pymedphys/compare/v0.8.2...v0.8.3
[0.8.2]: https://github.com/pymedphys/pymedphys/compare/v0.8.1...v0.8.2
[0.8.1]: https://github.com/pymedphys/pymedphys/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/pymedphys/pymedphys/compare/v0.7.2...v0.8.0
[0.7.2]: https://github.com/pymedphys/pymedphys/compare/v0.7.1...v0.7.2
[0.7.1]: https://github.com/pymedphys/pymedphys/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/pymedphys/pymedphys/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/pymedphys/pymedphys/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/pymedphys/pymedphys/compare/v0.4.3...v0.5.1
