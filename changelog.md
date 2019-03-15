# Release Notes
All notable changes to this project will be documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
<br/>


## [Unreleased]

### Breaking Changes
- nil

### New Features
- nil

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
- The DICOM coordinate extraction functions:
    - `extract_dicom_patient_xyz()`,
    - `extract_iec_patient_xyz()` and
    - `extract_iec_fixed_xyz()`

  now return simple tuples rather than `Coords` namedtuples.


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
