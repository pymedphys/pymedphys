# Release Notes
All notable changes to this project will be documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
<br/>


## [Unreleased]

### Breaking Changes
- `anonymise_dicom` has been renamed to `anonymise_dicom_dataset`

### New Features
- Implementing a suite of Dicom objects, currently a work in progress:
  - `DicomBase`, a base DICOM class that wraps `pydicom`'s `Dataset` object.
    This class includes aditions such as an anonymisation method.
  - `DicomImage`, designed to hold a single DICOM image slice. Might someday
    contain methods such as `resample` and the like.
  - `DicomSeries`, a series of `DicomImage` objects creating a CT dataset.
  - `DicomStructure`, designed to house DICOM structure datasets.
  - `DicomPlan`, a class that holds RT plan DICOM datasets.
  - `DicomDose`, a class that to hold RT DICOM dose datasets. It has helper
    functions and parameters such as coordinate transforms built into it.
  - `DicomStudy`, a class designed to hold an interelated set of `DicomDose`,
    `DicomPlan`, `DicomStructure`, and `DicomSeries`. Not every type is
    required to create a `DicomStudy`. Certain methods will be
    available on `DicomStudy` depending what is housed within it. For example
    having both `DicomDose` and `DicomStructure` should enable DVH based
    methods.
  - `DicomCollection`, a class that can hold multiple studies, interellated or
    not. A common use case that will likely be implemented is
    `DicomCollection.from_directory(directory_path)` which would pull all DICOM
    files nested within a directory and sort them into `DicomStudy` objects
    based on their header UIDs.

### Bug Fixes
- nil

### Code Refactoring
- nil

### Performance Improvements
- nil
<br/>


## [0.6.0] -- 2019/03/15

### Breaking Changes
- All uses of "dcm" in directory names, module names, function names, etc.
  have been converted to "dicom". Anything that makes use of this code will need to be
  adjusted accordingly. Required changes include:
    - `pymedphys.dcm` --> `pymedphys.dicom`
    - `coords_and_dose_from_dcm()` --> `coords_and_dose_from_dicom()`
    - `dcmfromdict()` --> `dicom_dataset_from_dict()`
    - `gamma_dcm()` --> `gamma_dicom()`
- MU Density related functions are no longer available under the `pymedphys.coll` package,
  instead they are found within `pymedphys.mudensity` package.
- The DICOM coordinate extraction functions now return simple tuples rather than `Coords` namedtuples:
    - `extract_dicom_patient_xyz()`
    - `extract_iec_patient_xyz()`
    - `extract_iec_fixed_xyz()`

### New Features
- DICOM anonymisation now permits replacing deidentified values with suitable "dummy" values. This helps to
  maintain compatibility with DICOM software that includes checks (beyond those specified in the DICOM Standard)
  of valid DICOM tag values. Replacing tags with dummy values upon anonymisation is now the default behaviour.
- A set of 3D coordinate transformation functions, including rotations (passive or active) and translations.
  Transformations may be applied to a single coordinate triplet (an `ndarray`) or a list of arbitrarily many
  coordinate triplets (a 3 x n `ndarray`). **NB**: Documentation forthcoming.

### Code Refactoring
- All uses of `dcm` as a variable name for instances of PyDicom Datasets have been converted to `ds` to
  match PyDicom convention.

<br/>

## [0.5.1] -- 2019/01/05

### New Features
- Began keeping record of changes in `changelog.md`


[Unreleased]: https://github.com/pymedphys/pymedphys/compare/v0.6.0...master
[0.6.0]: https://github.com/pymedphys/pymedphys/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/pymedphys/pymedphys/compare/v0.4.3...v0.5.1
