from typing import Tuple
from typing_extensions import Literal

from matplotlib import pyplot as plt
import numpy as np
import pydicom
import xarray as xr

from pymedphys._dicom import dose


def xdose_from_dataset(
    ds: "pydicom.dataset.Dataset",
    name="Dose",
    coord_system: Literal["D", "P", "S"] = "S",
) -> "xr.DataArray":

    return xr.DataArray(
        data=dose.dose_from_dataset(ds),
        dims=xarray_dims_from_dataset(ds, coord_system=coord_system),
        coords=xarray_coords_from_dataset(
            ds,
            coord_system=coord_system,
        ),
        name=name,
        attrs={"units": ds.DoseUnits.title(), "coord_system": coord_system},
    )


def round_xdose_coords(xdose_to_round, decimals=2):
    xdose_rounded = xdose_to_round.copy()

    for dim, coord_vals in xdose_to_round.coords.items():
        xdose_rounded.coords[dim] = coord_vals.round(decimals=decimals)

    return xdose_rounded


def coords_from_dataset(
    ds: "pydicom.dataset.Dataset", coord_system: Literal["D", "P", "S"] = "S"
) -> Tuple["np.ndarray", "np.ndarray", "np.ndarray"]:
    r"""Returns the x, y and z coordinates of a DICOM dataset's
    pixel array in the specified coordinate system.

    For DICOM RT Dose datasets, these are the x, y, z coordinates of the
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

        'D':
            Return coordinates in the DICOM coordinate system.

        'P':
            Return coordinates in the IEC patient coordinate system.

        'S':
            Return coordinates in the IEC support coordinate system.

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
    Feet First Decubitus Left   [ 0,  1,  0,  1,  0,  0]
    Feet First Decubitus Right  [ 0, -1,  0, -1,  0,  0]
    Feet First Prone            [ 1,  0,  0,  0, -1,  0]
    Feet First Supine           [-1,  0,  0,  0,  1,  0]
    Head First Decubitus Left   [ 0, -1,  0,  1,  0,  0]
    Head First Decubitus Right  [ 0,  1,  0, -1,  0,  0]
    Head First Prone            [-1,  0,  0,  0, -1,  0]
    Head First Supine           [ 1,  0,  0,  0,  1,  0]
    =========================== ==========================

    References
    ----------
    .. [1] O. McNoleg, "Generalized coordinate transformations for Monte
       Carlo (DOSXYZnrc and VMC++) verifications of DICOM compatible
       radiotherapy treatment plans", arXiv:1406.0014, Table 1,
       https://arxiv.org/ftp/arxiv/papers/1406/1406.0014.pdf
    """

    _validate_coord_system(coord_system)

    if not (
        np.allclose(np.abs(ds.ImageOrientationPatient), np.array([1, 0, 0, 0, 1, 0]))
        or np.allclose(np.abs(ds.ImageOrientationPatient), np.array([0, 1, 0, 1, 0, 0]))
    ):
        raise ValueError(
            "Dose grid orientation is not supported. Dose "
            "grid slices must be aligned along the "
            "superoinferior axis of patient."
        )

    is_decubitus = dataset_orientation_is_decubitus(ds)
    is_head_first = dataset_orientation_is_head_first(ds)

    di = float(ds.PixelSpacing[0])
    dj = float(ds.PixelSpacing[1])

    col_range = np.arange(0, ds.Columns * di, di)
    row_range = np.arange(0, ds.Rows * dj, dj)

    if is_decubitus:
        x_support = (
            ds.ImageOrientationPatient[1] * ds.ImagePositionPatient[1] + col_range
        )
        z_support = -(
            ds.ImageOrientationPatient[3] * ds.ImagePositionPatient[0] + row_range
        )
    else:
        x_support = (
            ds.ImageOrientationPatient[0] * ds.ImagePositionPatient[0] + col_range
        )
        z_support = -(
            ds.ImageOrientationPatient[4] * ds.ImagePositionPatient[1] + row_range
        )

    if is_head_first:
        y_support = ds.ImagePositionPatient[2] + np.array(ds.GridFrameOffsetVector)
    else:
        y_support = -ds.ImagePositionPatient[2] + np.array(ds.GridFrameOffsetVector)

    if coord_system.upper() == "S":
        return (x_support, y_support, z_support)

    elif coord_system.upper() in ("D", "P"):

        x_patient = (
            ds.ImageOrientationPatient[0] * x_support
            + ds.ImageOrientationPatient[3] * z_support
        )
        z_patient = (
            ds.ImageOrientationPatient[1] * x_support
            + ds.ImageOrientationPatient[4] * z_support
        )

        if not is_head_first:
            y_patient = -y_support
        else:
            y_patient = y_support

        if coord_system.upper() == "P":
            return (x_patient, y_patient, z_patient)

        elif coord_system.upper() == "D":

            x_dicom = x_patient
            y_dicom = -z_patient
            z_dicom = y_patient

            return (x_dicom, y_dicom, z_dicom)


def xarray_dims_from_dataset(
    ds: "pydicom.dataset.Dataset", coord_system: Literal["D", "P", "S"] = "S"
):
    _validate_coord_system(coord_system)

    # fmt: off
    XARRAY_DIMS_BY_COORD_SYSTEM_AND_ORIENT = {
        "S":     ["y", "z", "x"],
        "P":     ["y", "z", "x"],
        "P dec": ["y", "x", "z"],
        "D":     ["z", "y", "x"],
        "D dec": ["z", "x", "y"],
    }
    # fmt: on

    if dataset_orientation_is_decubitus(ds) and coord_system.upper() != "S":
        dim_key = f"{coord_system.upper()} dec"
    else:
        dim_key = coord_system.upper()

    return XARRAY_DIMS_BY_COORD_SYSTEM_AND_ORIENT[dim_key]


def xarray_coords_from_dataset(
    ds: "pydicom.dataset.Dataset",
    coord_system: Literal["D", "P", "S"] = "S",
):
    x, y, z = coords_from_dataset(ds, coord_system=coord_system)

    return {"x": x, "y": y, "z": z}


def dataset_orientation_is_head_first(ds: "pydicom.dataset.Dataset"):
    if dataset_orientation_is_decubitus(ds):
        return np.abs(np.sum(ds.ImageOrientationPatient)) != 2
    else:
        return np.abs(np.sum(ds.ImageOrientationPatient)) == 2


def dataset_orientation_is_decubitus(ds: "pydicom.dataset.Dataset"):
    return np.allclose(np.abs(ds.ImageOrientationPatient), np.array([0, 1, 0, 1, 0, 0]))


def _validate_coord_system(coord_system):

    VALID_COORD_SYSTEMS = ("D", "P", "S")

    if coord_system.upper() not in VALID_COORD_SYSTEMS:
        raise ValueError(
            "The supplied coordinate system is invalid. Valid systems are:\n{}".format(
                "\n".join(VALID_COORD_SYSTEMS)
            )
        )


def plot_xdose_tcs_at_point(xdose_to_plot, point, coord_system="S"):
    LAT_2_LONG_RATIO = xdose_to_plot.x.size / xdose_to_plot.y.size
    VERT_2_LONG_RATIO = xdose_to_plot.z.size / xdose_to_plot.y.size

    xdose_to_plot = round_xdose_coords(xdose_to_plot)

    fig, axes = plt.subplots(
        nrows=2,
        ncols=2,
        figsize=(12, 8),
        gridspec_kw={
            "width_ratios": (LAT_2_LONG_RATIO, 1),
            "height_ratios": (VERT_2_LONG_RATIO, 1),
        },
    )

    fig.suptitle(xdose_to_plot.name, fontsize=24)

    axes[1, 1].axis("off")
    for ax in axes.ravel():
        ax.set_aspect("equal")

    xdose_to_plot.sel(y=point[1], method="nearest").plot(
        ax=axes[0, 0], cmap="jet", vmin=0, vmax=xdose_to_plot.max()
    )
    axes[0, 0].axhline(y=point[2], color="silver")
    axes[0, 0].axvline(x=point[0], color="silver")
    axes[0, 0].set_title("Transverse")

    xdose_to_plot.sel(x=point[0], method="nearest").T.plot(
        ax=axes[0, 1], cmap="jet", vmin=0, vmax=xdose_to_plot.max()
    )
    axes[0, 1].axhline(y=point[2], color="silver")
    axes[0, 1].axvline(x=point[1], color="silver")
    axes[0, 1].set_title("Sagittal")

    xdose_to_plot.sel(z=point[2], method="nearest").plot(
        ax=axes[1, 0], cmap="jet", vmin=0, vmax=xdose_to_plot.max()
    )
    axes[1, 0].axhline(y=point[1], color="silver")
    axes[1, 0].axvline(x=point[0], color="silver")
    axes[1, 0].set_title("Coronal")

    fig.tight_layout()


def zoom(
    xdose_to_zoom,
    x_start=None,
    x_end=None,
    y_start=None,
    y_end=None,
    z_start=None,
    z_end=None,
):

    if x_start is None:
        x_start = xdose_to_zoom["x"][0]
    if x_end is None:
        x_end = xdose_to_zoom["x"][-1]
    if y_start is None:
        y_start = xdose_to_zoom["y"][0]
    if y_end is None:
        y_end = xdose_to_zoom["y"][-1]
    if z_start is None:
        z_start = xdose_to_zoom["z"][0]
    if z_end is None:
        z_end = xdose_to_zoom["z"][-1]

    if xdose_to_zoom["x"][0] < xdose_to_zoom["x"][-1] and x_start > x_end:
        raise ValueError(
            "`x_start` must be less than `x_end` since the x coords are increasing in `xdose_to_zoom`"
        )
    elif xdose_to_zoom["x"][0] > xdose_to_zoom["x"][-1] and x_start < x_end:
        raise ValueError(
            "`x_start` must be greater than `x_end` since the x coords are decreasing in `xdose_to_zoom`"
        )
    if xdose_to_zoom["y"][0] < xdose_to_zoom["y"][-1] and y_start > y_end:
        raise ValueError(
            "`y_start` must be less than `y_end` since the y coords are increasing in `xdose_to_zoom`"
        )
    elif xdose_to_zoom["y"][0] > xdose_to_zoom["y"][-1] and x_start < x_end:
        raise ValueError(
            "`y_start` must be greater than `y_end` since the y coords are decreasing in `xdose_to_zoom`"
        )
    if xdose_to_zoom["z"][0] < xdose_to_zoom["z"][-1] and z_start > z_end:
        raise ValueError(
            "`z_start` must be less than `z_end` since the z coords are increasing in `xdose_to_zoom`"
        )
    elif xdose_to_zoom["z"][0] > xdose_to_zoom["z"][-1] and z_start < z_end:
        raise ValueError(
            "`z_start` must be greater than `z_end` since the z coords are decreasing in `xdose_to_zoom`"
        )

    return xdose_to_zoom.sel(
        x=slice(x_start, x_end), y=slice(y_start, y_end), z=slice(z_start, z_end)
    )
