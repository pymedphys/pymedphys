# Release Notes
All notable changes to this project will be documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
<br/>

## [Unreleased]

### Added
- ProfileDose object built ontop of xarray. [@SimonBiggs](https://github.com/SimonBiggs).

### Changed
- **Breaking Change**: All uses of "dcm" in directory names, module names, function names, etc.
  have been converted to "dicom". Anything that makes use of this code will need to be
  adjusted accordingly. Required changes include:
    - `pymedphys.dcm` --> `pymedphys.dicom`
    - `coords_and_dose_from_dcm()` --> `coords_and_dose_from_dicom()`
    - `dcmfromdict()` --> `dicom_from_dict()`
    - `gamma_dcm()` --> `gamma_dicom()`
- All uses of `dcm` as a variable name for storing a pydicom Dataset have been converted to `ds` to
  match PyDicom convention.
- MU Density related functions are no longer available under the `pymedphys.coll` package, instead they are found within `pymedphys.mudensity` package.

### Deprecated
- nil

### Removed
- nil

### Fixed
- nil

### Safety
- nil

##### Security
- nil
<br/>

## [0.5.1] -- 2019/01/05

### Added
- Began keeping record of changes in `changelog.md`


[Unreleased]: https://github.com/pymedphys/pymedphys/compare/v0.5.1...master
[0.5.1]: https://github.com/pymedphys/pymedphys/compare/v0.4.3...v0.5.1
