from typing import Tuple

import numpy as np
import pydicom
import xarray as xr

from pymedphys._dicom import constants, coords, dose


def xdose_from_dataset(ds, coord_system="SUPPORT", decimals_to_round_coords=-1):

    dose_values = dose.dose_from_dataset(ds)
    xr_dims = xarray_dims_from_dataset(ds, coord_system=coord_system)
    xr_coords = xarray_coords_from_dataset(
        ds,
        coord_system=coord_system,
        round_to_decimals=decimals_to_round_coords,
    )

    return xr.DataArray(
        data=dose_values,
        dims=xr_dims,
        coords=xr_coords,
        name="dose",
        attrs={"units": ds.DoseUnits, "coord_system": coord_system},
    )


def coords_from_dataset(
    ds: "pydicom.dataset.Dataset", coord_system: str = "SUPPORT"
) -> Tuple["np.ndarray", "np.ndarray", "np.ndarray"]:
    r"""Returns the x, y and z coordinates of a DICOM dataset's
    pixel array in the specified coordinate system.

    For DICOM RT Dose datasets, these are the x, y, z axes of the
    dose grid.

    Parameters
    ----------
    ds : pydicom.dataset.Dataset
        A DICOM dataset that contains pixel data. Supported modalities
        include 'CT' and 'RTDOSE'.

    coord_system : str, optional
        The coordinate system in which to return the `x`, `y` and `z`
        coordinates of the DICOM dataset. The accepted, case-insensitive
        values of `coord_system` are:

        'DICOM' or 'd':
            Return axes in the DICOM coordinate system.

        'patient', 'IEC patient' or 'p':
            Return axes in the IEC patient coordinate system.

        'support', 'IEC support' or 's':
            Return axes in the IEC support coordinate system.

    Returns
    -------
    (x, y, z)
        A tuple containing three `numpy.ndarray`s corresponding to the
        `x`, `y` and `z` coordinates of the DICOM dataset's pixel array
        in the specified coordinate system.

    Notes
    -----
    Supported scan orientations [1]_:

    =========================== ==========================
    Orientation                 ds.ImageOrientationPatient
    =========================== ==========================
    Feet First Decubitus Left   [0, 1, 0, 1, 0, 0]
    Feet First Decubitus Right  [0, -1, 0, -1, 0, 0]
    Feet First Prone            [1, 0, 0, 0, -1, 0]
    Feet First Supine           [-1, 0, 0, 0, 1, 0]
    Head First Decubitus Left   [0, -1, 0, 1, 0, 0]
    Head First Decubitus Right  [0, 1, 0, -1, 0, 0]
    Head First Prone            [-1, 0, 0, 0, -1, 0]
    Head First Supine           [1, 0, 0, 0, 1, 0]
    =========================== ==========================

    References
    ----------
    .. [1] O. McNoleg, "Generalized coordinate transformations for Monte
       Carlo (DOSXYZnrc and VMC++) verifications of DICOM compatible
       radiotherapy treatment plans", arXiv:1406.0014, Table 1,
       https://arxiv.org/ftp/arxiv/papers/1406/1406.0014.pdf
    """

    position = np.array(ds.ImagePositionPatient)
    orientation = np.array(ds.ImageOrientationPatient)

    if not (
        np.array_equal(np.abs(orientation), np.array([1, 0, 0, 0, 1, 0]))
        or np.array_equal(np.abs(orientation), np.array([0, 1, 0, 1, 0, 0]))
    ):
        raise ValueError(
            "Dose grid orientation is not supported. Dose "
            "grid slices must be aligned along the "
            "superoinferior axis of patient."
        )

    is_decubitus = orientation[0] == 0
    is_head_first = _orientation_is_head_first(orientation, is_decubitus)

    di = float(ds.PixelSpacing[0])
    dj = float(ds.PixelSpacing[1])

    col_range = np.arange(0, ds.Columns * di, di)
    row_range = np.arange(0, ds.Rows * dj, dj)

    if is_decubitus:
        x_support = orientation[1] * position[1] + col_range
        z_support = -(orientation[3] * position[0] + row_range)
    else:
        x_support = orientation[0] * position[0] + col_range
        z_support = -(orientation[4] * position[1] + row_range)

    if is_head_first:
        y_support = position[2] + np.array(ds.GridFrameOffsetVector)
    else:
        y_support = -position[2] + np.array(ds.GridFrameOffsetVector)

    if coord_system.upper() in ("SUPPORT", "IEC SUPPORT", "S"):
        return (x_support, y_support, z_support)

    elif coord_system.upper() in ("DICOM", "D", "PATIENT", "IEC PATIENT", "P"):

        x_patient = orientation[0] * x_support + orientation[3] * z_support
        z_patient = orientation[1] * x_support + orientation[4] * z_support

        if not is_head_first:
            y_patient = -y_support
        else:
            y_patient = y_support

        if coord_system.upper() in ("PATIENT", "IEC PATIENT", "P"):
            return (x_patient, y_patient, z_patient)

        elif coord_system.upper() in ("DICOM", "D"):

            x_dicom = x_patient
            y_dicom = -z_patient
            z_dicom = y_patient

            return (x_dicom, y_dicom, z_dicom)


def xarray_dims_from_dataset(ds, coord_system):

    IEC_NON_decubitus_DIMS = ["y", "z", "x"]

    if coord_system.upper() in ("SUPPORT", "IEC SUPPORT", "S"):
        return IEC_NON_decubitus_DIMS

    elif coord_system.upper() in ("PATIENT", "IEC PATIENT", "P"):
        if dataset_orient_is_decubitus(ds):
            return ["y", "x", "z"]
        else:
            return IEC_NON_decubitus_DIMS

    elif coord_system.upper() in ("DICOM", "D"):
        if dataset_orient_is_decubitus(ds):
            return ["z", "x", "y"]
        else:
            return ["z", "y", "x"]


def xarray_coords_from_dataset(
    ds, coord_system: str = "SUPPORT", round_to_decimals: int = -1
):
    x, y, z = coords_from_dataset(ds, coord_system=coord_system)

    xcoords = {"x": x, "y": y, "z": z}

    if round_to_decimals >= 0:
        return {
            dim: np.round(xc, decimals=round_to_decimals) for dim, xc in xcoords.items()
        }
    else:
        return xcoords


def _orientation_is_head_first(orientation_vector, is_decubitus):
    if is_decubitus:
        return np.abs(np.sum(orientation_vector)) != 2

    return np.abs(np.sum(orientation_vector)) == 2


def dataset_orient_is_decubitus(ds):
    return ds.ImageOrientationPatient[0] == 0
