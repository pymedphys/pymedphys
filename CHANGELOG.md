<!-- markdownlint-disable MD024 -->

# Release Notes

All notable changes to this project will be documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!--  Template
## [Unreleased]

### Breaking Changes

- nil

### New Features

- nil

### Bug Fixes

- nil

### Code Refactoring

- nil

### Package changes

- nil

### Performance Improvements

- nil -->


## [0.16.2]

### Bug Fixes

- Fixed bug with optional dependency logic within `apipkg`. Occurred whenever
  an optional submodule was called.


## [0.16.1]

### Aesthetic Changes

- Updated the badges reported within the README.

## [0.16.0]

### Package changes

- The license of the package has changed from `AGPL-3.0-or-later` to
 `Apache-2.0`.

### New Features

- Expose `pymedphys.electronfactors.plot_model` as part of the public API.

## [0.15.0]

### New Features

- Experimental support for Elekta Unity trf log file decoding.

## [0.14.3]

### Package changes

- Updated wheel to correctly handle optional dependencies.

## [0.14.2]

### Bug Fixes

- Vendored in `apipkg` due to PyPI installation issues.

## [0.14.1]

### Bug Fixes

- Given the input to `pymedphys.gamma` is unitless, removed the units from
  the logging output of gamma. See <https://github.com/pymedphys/pymedphys/issues/611>

## [0.14.0]

### Breaking Changes

- Moved `pymedphys pinnacle` cli command to be nested under
 `pymedphys labs pinnacle`

### Dependency Changes

- Made the greater majority of the pymedphys dependencies optional. Should a
  dependency be required during usage an error is raised informing the user to
  install the package. To install all pymedphys dependencies as before now run
  `pip install pymedphys[library,labs]==0.14.0`.

## [0.13.2]

### Bug Fix

- Fixed issue where `pymedphys.mosaiq.connect` would not work for just one
  hostname.

## [0.13.1]

### Bug Fix

- Fixed issue where `pymedphys.mosaiq.connect` would not work for just one
  hostname.

## [0.13.0]

### New Feature

- Made `pymedphys.mosaiq.execute` a part of the API.

## [0.12.2]

### Package changes

- Fixed version number within package.

## [0.12.1]

### Package changes

- Re-added the license classifier to the PyPI upload.

## [0.12.0]

### Breaking Changes

- The API has undergone a complete redesign. Expect most code to be broken with
  this release.

## [0.11.0]

### Breaking Changes

- Within `dose_from_dataset` the `reshape` parameter has been removed.
- Removed the following functions:
  - `load_dicom_data`
  - `axes_and_dose_from_dicom`
  - `extract_depth_dose`
  - `extract_profiles`

### New Features

- Added functions `pymedphys.dicom.depth_dose` and `pymedphys.dicom.profiles`.
- Exposed the `trf2pandas` function via `pymedphys.fileformats.trf2pandas`.

### Improvements

- Made the resolution detection of `pymedphys.plt.pcolormesh_grid` more robust.

## [0.10.0]

### New Features

- Re-exposed `convert2_ratio_perim_area` and `create_transformed_mesh` from
  `pymedphys.electronfactors`.
- Pinnacle module providing a tool to export raw Pinnacle data to DICOM
  objects.
  - A CLI is provided: See
  [the Pinnacle CLI docs](https://docs.pymedphys.com/user/interfaces/cli/pinnacle.html).
  - As well as an API: See
  [the Pinnacle library docs](https://docs.pymedphys.com/user/library/pinnacle.html).

## [0.9.0] -- 2019/06/06

### New Features

- Re-exposed `multi_mosaiq_connect`, `multi_fetch_and_verify_mosaiq`,
  `get_qcls_by_date`, and `get_staff_name` from `pymedphys.msq`.

## [0.8.4] -- 2019/06/04

### Package changes

- Made `xlwings` not install by default if system is `Linux` within `setup.py`
- Removed unreleased `jupyter` based GUI

## [0.8.3] -- 2019/06/04

### Package changes

- Updated MANIFEST file within `pymedphys_fileformats` to appropriately include
  LICENSE files.

## [0.8.2] -- 2019/06/01

### Package changes

- Included license files within the subpackage distributions

## [0.8.1] -- 2019/06/01

### Dependency changes

- Removed numpy version upper-limit

## [0.8.0] -- 2019/06/01

### Breaking Changes

- `DeliveryData` has been renamed to `Delivery` and is now importable by
  running `from pymedphys import Delivery`
  - A range of functions that used to use `DeliveryData` are now instead
    accessible as methods on the `Delivery` object.
- A large number of functions that were previously exposed have now been made
  private in preparation for eventually stabilising the API. No function that
  was within the documentation has been removed. If there is a function that
  you were using that you would like to be exposed via `import` again, please
  let us know by
  [opening an issue on GitHub](https://github.com/pymedphys/pymedphys/issues)
  and we will happily re-expose it! However, please bear in mind that the
  entire API that is currently exposed will likely change before a 1.0.0
  release.
- `anonymise_dicom_dataset()` has been renamed to `anonymise_dataset()` to
  remove redundant labelling.
- `mu_density_from_delivery_data` moved from the `msq` module to the
  `mudensity` module.
- `compare_mosaiq_fields` moved from the `msq` module into the `plancompare`
  module.
- `pymedphys.dicom.get_structure_aligned_cube` has had its `x0` parameter
  changed from required to optional. It is no longer the first parameter
  passed to the function. By default `x0` is now determined using the min/max
  bounds of the structure.
- The DICOM coordinate extraction functions - `extract_dicom_patient_xyz()`,
  `extract_iec_patient_xyz()` and `extract_iec_fixed_xyz()` - have been
  combined into a single function called `xyz_from_dataset()`. The x, y, z axes
  can still be returned in either the DICOM, IEC fixed or IEC patient
  coordinate systems by passing the following case-insensitive strings to the
  `coord_system=` parameter of `xyz_from_dataset()`:
  - DICOM: `'d'` or `'DICOM'`
  - IEC fixed: `'f'`, `'fixed'` or `'IEC fixed'`
  - IEC patient: `'p'`, `'patient'` or `'IEC patient'`
- `gamma_dicom` now take datasets as opposed to filenames

### New Features

- A DICOM anonymisation CLI! See
  [the DICOM Files CLI docs](../user/interfaces/cli/dicom.rst).
- `anonymise_file()` and `anonymise_directory()`:
  - two new DICOM anonymisation
    wrapper functions that take a DICOM file and a directory as respective
    arguments.
- `is_anonymised_dataset()`, `is_anonymised_file()` and
  `is_anonymised_directory()`:
  - three new functions that check whether a pydicom
    dataset, a DICOM file or all files within a directory have been anonymised,
    respectively.
- `coords_from_xyz_axes()` is a previously internal function that has now been
  exposed in the API. It converts x, y, z axes returned by `xyz_from_dataset()`
  into a full grid of coordinate triplets that correspond to the original grid
  (pixel array or dose grid).

## [0.7.2] -- 2019/04/05

### Dependency changes

- Removed numpy version upper-limit

## [0.7.1] -- 2019/04/05

### Performance Improvements

- reduced PyPI package size by removing unnecessary development testing files.

## [0.7.0] -- 2019/04/05

### Breaking Changes

- `anonymise_dicom` has been renamed to `anonymise_dicom_dataset`
- The CLI interface `trf2csv` has been replaced with `pymedphys trf to-csv`.
  This has the same usage, just a changed name to come in line with the rest of
  the CLI interfaces exposed by PyMedPhys.

### New Features

- Implementing a suite of Dicom objects, currently a work in progress:
  - `DicomBase`, a base DICOM class that wraps `pydicom`'s `Dataset` object.
    This class includes additions such as an anonymisation method.
  - `DicomImage`, designed to hold a single DICOM image slice. Might someday
    contain methods such as `resample` and the like.
  - `DicomSeries`, a series of `DicomImage` objects creating a CT dataset.
  - `DicomStructure`, designed to house DICOM structure datasets.
  - `DicomPlan`, a class that holds RT plan DICOM datasets.
  - `DicomDose`, a class that to hold RT DICOM dose datasets. It has helper
    functions and parameters such as coordinate transforms built into it.
  - `DicomStudy`, a class designed to hold an interrelated set of `DicomDose`,
    `DicomPlan`, `DicomStructure`, and `DicomSeries`. Not every type is
    required to create a `DicomStudy`. Certain methods will be
    available on `DicomStudy` depending what is housed within it. For example
    having both `DicomDose` and `DicomStructure` should enable DVH based
    methods.
  - `DicomCollection`, a class that can hold multiple studies, interrelated or
    not. A common use case that will likely be implemented is
    `DicomCollection.from_directory(directory_path)` which would pull all DICOM
    files nested within a directory and sort them into `DicomStudy` objects
    based on their header UIDs.
- Added CLI commands for a WIP docker server, logfile orchestration, and DICOM
  editor tools.
- Added a range of xlwings tools that allow the use of PyMedPhys functions
  within Excel
- Added rudimentary code to pull profiles from Mephysto
  files.
- The previously separate `decodetrf` library is now distributed within
  PyMedPhys. You can now simply install PyMedPhys and run
  `pymedphys trf to-csv` within the command line to convert `.trf` files into
  `.csv` files.

## [0.6.0] -- 2019/03/15

### Breaking Changes

- All uses of "dcm" in directory names, module names, function names, etc.
  have been converted to "dicom". Anything that makes use of this code will
  need to be adjusted accordingly. Required changes include:
  - `pymedphys.dcm` --> `pymedphys.dicom`
  - `coords_and_dose_from_dcm()` --> `coords_and_dose_from_dicom()`
  - `dcmfromdict()` --> `dicom_dataset_from_dict()`
  - `gamma_dcm()` --> `gamma_dicom()`
- MU Density related functions are no longer available under the
  `pymedphys.coll` package, instead they are found within `pymedphys.mudensity`
  package.
- The DICOM coordinate extraction functions now return simple tuples rather
  than `Coords` namedtuples:
  - `extract_dicom_patient_xyz()`
  - `extract_iec_patient_xyz()`
  - `extract_iec_fixed_xyz()`

### New Features

- DICOM anonymisation now permits replacing deidentified values with suitable
  "dummy" values. This helps to maintain compatibility with DICOM software that
  includes checks (beyond those specified in the DICOM Standard) of valid DICOM
  tag values. Replacing tags with dummy values upon anonymisation is now the
  default behaviour.
- A set of 3D coordinate transformation functions, including rotations (passive
  or active) and translations. Transformations may be applied to a single
  coordinate triplet (an `ndarray`) or a list of arbitrarily many coordinate
  triplets (a 3 x n `ndarray`). **NB**: Documentation forthcoming.

### Code Refactoring

- All uses of `dcm` as a variable name for instances of PyDicom Datasets have
  been converted to `ds` to match PyDicom convention.

## [0.5.1] -- 2019/01/05

### New Features

- Began keeping record of changes in `changelog.md`

[Unreleased]: https://github.com/pymedphys/pymedphys/compare/v0.16.2...master
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
