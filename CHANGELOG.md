<!-- markdownlint-disable MD024 MD039 -->

# Release Notes

All notable changes to this project will be documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!--  Template
## [Unreleased]

### Breaking Changes

* nil

### New Features

* nil

### Bug Fixes

* nil

### Code Refactoring

* nil

### Package Changes

* nil

### Performance Improvements

* nil -->

## [Unreleased]

### New Features

- Added DICOM helpers functionality and updated the Mosaiq helpers as a part of
  the TPS/OIS comparison project. Not yet exposed as part of the API.

## [0.29.1]

### Bug fixes

* Fix issue in some Windows environments where running `pymedphys gui` would
  not find the streamlit installation. [[`_gui/__init__.py`]](https://github.com/pymedphys/pymedphys/blob/03ba546b603edcbaf7b2b33c6367146a95142d0d/pymedphys/_gui/__init__.py#L43)

## [0.29.0]

### Breaking changes

* Changed the `patient_directories` icom parameter to accept a list of paths
  instead of a single path within the pymedphys `config.toml`. [[`config.toml#L67-L72`]](https://github.com/pymedphys/pymedphys/blob/7a08a94185f94b1f7df304de8bd0274f0f1fcbc9/examples/site-specific/cancer-care-associates/config.toml#L67-L72)
* Changed `pymedphys gui` iCOM path resolution logic to instead search over
  a list of paths instead of just one path as before. [[`mudensity-compare.py#L668-L670`]](https://github.com/pymedphys/pymedphys/blob/7a08a94185f94b1f7df304de8bd0274f0f1fcbc9/pymedphys/_gui/streamlit/mudensity-compare.py#L668-L670)

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
  functionality has now been merged into the listener. [[`listener.py#L79`]](https://github.com/pymedphys/pymedphys/blob/d40a5ed238b2035bac00da1cb623c7f496ed0950/pymedphys/_icom/listener.py#L79)
* Should an error occur within `pymedphys icom listener` CLI it will now pause
  for 15 minutes and then reattempt a connection.
* Add in extra sanity checks within the iCOM patient indexing tooling.
* Added a `--debug` and `--verbose` flag to the PyMedPhys CLI which allows
  users to set the logging level. These logging levels are currently only
  utilised within the `pymedphys icom listen` CLI. [[`cli/main.py#L51-L70`]](https://github.com/pymedphys/pymedphys/blob/9c7c7e3c2d7fb49d30b418dca2fa28e6982ff97e/pymedphys/cli/main.py#L51-L70)

### Bug fixes

* Reduced the buffer size of the iCOM listener. [[`listener.py#L9`]](https://github.com/pymedphys/pymedphys/blob/d40a5ed238b2035bac00da1cb623c7f496ed0950/pymedphys/_icom/listener.py#L9)
* If either the listener is turned off and then on again, or it is interrupted
  the next time an iCOM stream socket is opened the Linac appears to send a
  larger batch containing prior irradiations. The listener code was adjusted
  to handle these extra bursts. [[`listener.py#L57-L83`]](https://github.com/pymedphys/pymedphys/blob/d40a5ed238b2035bac00da1cb623c7f496ed0950/pymedphys/_icom/listener.py#L57-L83)
* Made PyMedPhys GUI skip name formatting attempt if the original patient name
  format was not as expected. [[`mudensity-compare.py#L733-L738`]](https://github.com/pymedphys/pymedphys/blob/d40a5ed238b2035bac00da1cb623c7f496ed0950/pymedphys/_gui/streamlit/mudensity-compare.py#L733-L738)

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

[Unreleased]: https://github.com/pymedphys/pymedphys/compare/v0.29.1...master
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
