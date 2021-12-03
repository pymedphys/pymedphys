# Copyright (C) 2016-2021 Matthew Jennings and Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A DICOM RT Dose toolbox"""

import copy
from typing import Sequence

from pymedphys._imports import matplotlib
from pymedphys._imports import numpy as np
from pymedphys._imports import plt, pydicom, scipy

from . import orientation
from .coords import coords_in_datasets_are_equal, xyz_axes_from_dataset
from .header import patient_ids_in_datasets_are_equal
from .rtplan import get_surface_entry_point_with_fallback, require_gantries_be_zero
from .structure import pull_structure

# pylint: disable=C0103


def zyx_and_dose_from_dataset(dataset):
    x, y, z = xyz_axes_from_dataset(dataset)
    coords = (z, y, x)
    dose = dose_from_dataset(dataset)

    return coords, dose


def dose_from_dataset(ds, set_transfer_syntax_uid=True):
    r"""Extract the dose grid from a DICOM RT Dose file."""

    if set_transfer_syntax_uid:
        ds.file_meta.TransferSyntaxUID = pydicom.uid.ImplicitVRLittleEndian

    dose = ds.pixel_array * ds.DoseGridScaling

    return dose


def dicom_dose_interpolate(interp_coords, dicom_dose_dataset):
    """Interpolates across a DICOM dose dataset.

    Parameters
    ----------
    interp_coords : tuple(z, y, x)
        A tuple of coordinates in DICOM order, z axis first, then y, then x
        where x, y, and z are DICOM axes.
    dose : pydicom.Dataset
        An RT DICOM Dose object
    """

    interp_z = np.array(interp_coords[0], copy=False)[:, None, None]
    interp_y = np.array(interp_coords[1], copy=False)[None, :, None]
    interp_x = np.array(interp_coords[2], copy=False)[None, None, :]

    coords, dicom_dose_dataset = zyx_and_dose_from_dataset(dicom_dose_dataset)
    interpolation = scipy.interpolate.RegularGridInterpolator(
        coords, dicom_dose_dataset
    )

    try:
        result = interpolation((interp_z, interp_y, interp_x))
    except ValueError:
        print(f"coords: {coords}")
        raise

    return result


def depth_dose(depths, dose_dataset, plan_dataset):
    """Interpolates dose for defined depths within a DICOM dose dataset.

    Since the DICOM dose dataset is in CT coordinates the corresponding
    DICOM plan is also required in order to calculate the conversion
    between CT coordinate space and depth.

    Currently, `depth_dose()` only supports a `dose_dataset` for which
    the patient orientation is HFS and that any beams in `plan_dataset`
    have gantry angle equal to 0 (head up). Depth is assumed to be
    purely in the y axis direction in DICOM coordinates.

    Parameters
    ----------
    depths : numpy.ndarray
        An array of depths to interpolate within the DICOM dose file. 0 is
        defined as the surface of the phantom using either the
        ``SurfaceEntryPoint`` parameter or a combination of
        ``SourceAxisDistance``, ``SourceToSurfaceDistance``, and
        ``IsocentrePosition``.
    dose_dataset : pydicom.dataset.Dataset
        The RT DICOM dose dataset to be interpolated
    plan_dataset : pydicom.dataset.Dataset
        The RT DICOM plan used to extract surface parameters and verify gantry
        angle 0 beams are used.
    """
    orientation.require_dicom_patient_position(dose_dataset, "HFS")
    require_gantries_be_zero(plan_dataset)
    depths = np.array(depths, copy=False)

    surface_entry_point = get_surface_entry_point_with_fallback(plan_dataset)
    depth_adjust = surface_entry_point.y

    y = depths + depth_adjust
    x, z = [surface_entry_point.x], [surface_entry_point.z]

    coords = (z, y, x)

    extracted_dose = np.squeeze(dicom_dose_interpolate(coords, dose_dataset))

    return extracted_dose


def profile(displacements, depth, direction, dose_dataset, plan_dataset):
    """Interpolates dose for cardinal angle horizontal profiles within a
    DICOM dose dataset.

    Since the DICOM dose dataset is in CT coordinates the corresponding
    DICOM plan is also required in order to calculate the conversion
    between CT coordinate space and depth and horizontal displacement.

    Currently, `profile()` only supports a `dose_dataset` for which
    the patient orientation is HFS and that any beams in `plan_dataset`
    have gantry angle equal to 0 (head up). Depth is assumed to be
    purely in the y axis direction in DICOM coordinates.

    Parameters
    ----------
    displacements : numpy.ndarray
        An array of displacements to interpolate within the DICOM dose
        file. 0 is defined in the DICOM z or x directions based either
        upon the ``SurfaceEntryPoint`` or the ``IsocenterPosition``
        depending on what is available within the DICOM plan file.
    depth : float
        The depth at which to interpolate within the DICOM dose file. 0 is
        defined as the surface of the phantom using either the
        ``SurfaceEntryPoint`` parameter or a combination of
        ``SourceAxisDistance``, ``SourceToSurfaceDistance``, and
        ``IsocentrePosition``.
    direction : str, one of ('inplane', 'inline', 'crossplane', 'crossline')
        Corresponds to the axis upon which to apply the displacements.
         - 'inplane' or 'inline' converts to DICOM z direction
         - 'crossplane' or 'crossline' converts to DICOM x direction
    dose_dataset : pydicom.dataset.Dataset
        The RT DICOM dose dataset to be interpolated
    plan_dataset : pydicom.dataset.Dataset
        The RT DICOM plan used to extract surface and isocentre
        parameters and verify gantry angle 0 beams are used.
    """

    orientation.require_dicom_patient_position(dose_dataset, "HFS")
    require_gantries_be_zero(plan_dataset)
    displacements = np.array(displacements, copy=False)

    surface_entry_point = get_surface_entry_point_with_fallback(plan_dataset)
    depth_adjust = surface_entry_point.y
    y = [depth + depth_adjust]

    if direction in ("inplane", "inline"):
        coords = (displacements + surface_entry_point.z, y, [surface_entry_point.x])
    elif direction in ("crossplane", "crossline"):
        coords = ([surface_entry_point.z], y, displacements + surface_entry_point.x)
    else:
        raise ValueError(
            "Expected direction to be equal to one of "
            "'inplane', 'inline', 'crossplane', or 'crossline'"
        )

    extracted_dose = np.squeeze(dicom_dose_interpolate(coords, dose_dataset))

    return extracted_dose


def get_dose_grid_structure_mask(
    structure_name: str,
    structure_dataset: "pydicom.Dataset",
    dose_dataset: "pydicom.Dataset",
):
    """Determines the 3D boolean mask defining whether or not a grid
    point is inside or outside of a defined structure.

    In its current implementation the dose grid and the planes upon
    which the structures are defined need to be aligned. This is due to
    the implementation only stepping through each structure plane and
    undergoing a 2D mask on the respective dose grid. In order to
    undergo a mask when the contours and dose grids do not align
    inter-slice contour interpolation would be required.

    For now, having two contours for the same structure name on a single
    slice is also not supported.

    Parameters
    ----------
    structure_name
        The name of the structure for which the mask is to be created
    structure_dataset : pydicom.Dataset
        An RT Structure DICOM object containing the respective
        structures.
    dose_dataset : pydicom.Dataset
        An RT Dose DICOM object from which the grid mask coordinates are
        determined.

    Raises
    ------
    ValueError
        If an unsupported contour is provided or the dose grid does not
        align with the structure planes.

    """
    x_dose, y_dose, z_dose = xyz_axes_from_dataset(dose_dataset)

    xx, yy = np.meshgrid(x_dose, y_dose)
    points = np.swapaxes(np.vstack([xx.ravel(), yy.ravel()]), 0, 1)

    x_structure, y_structure, z_structure = pull_structure(
        structure_name, structure_dataset
    )

    structure_z_values = []
    for item in z_structure:
        item = np.unique(item)
        if len(item) != 1:
            raise ValueError("Only one z value per contour supported")
        structure_z_values.append(item[0])

    structure_z_values = np.sort(structure_z_values)
    unique_structure_z_values = np.unique(structure_z_values)

    if np.any(structure_z_values != unique_structure_z_values):
        raise ValueError("Only one contour per slice is currently supported")

    sorted_dose_z = np.sort(z_dose)

    first_dose_index = np.where(sorted_dose_z == structure_z_values[0])[0][0]
    for i, z_val in enumerate(structure_z_values):
        dose_index = first_dose_index + i
        if structure_z_values[i] != sorted_dose_z[dose_index]:
            raise ValueError(
                "Only contours where both, there are no gaps in the "
                "z-axis of the contours, and the contour axis and dose "
                "axis, are aligned are supported."
            )

    mask_yxz = np.zeros((len(y_dose), len(x_dose), len(z_dose)), dtype=bool)

    for structure_index, z_val in enumerate(structure_z_values):
        dose_index = int(np.where(z_dose == z_val)[0])

        if z_structure[structure_index][0] != z_dose[dose_index]:
            raise ValueError("Structure and dose indices do not align")

        structure_polygon = matplotlib.path.Path(
            [
                (x_structure[structure_index][i], y_structure[structure_index][i])
                for i in range(len(x_structure[structure_index]))
            ]
        )

        # This logical "or" here is actually in place for the case where
        # there may be multiple contours on the one slice. That's not
        # going to be used at the moment however, as that case is not
        # yet supported in the logic above.
        mask_yxz[:, :, dose_index] = mask_yxz[:, :, dose_index] | (
            structure_polygon.contains_points(points).reshape(len(y_dose), len(x_dose))
        )

    mask_xyz = np.swapaxes(mask_yxz, 0, 1)
    mask_zyx = np.swapaxes(mask_xyz, 0, 2)

    return mask_zyx


def find_dose_within_structure(structure_name, structure_dataset, dose_dataset):
    dose = dose_from_dataset(dose_dataset)
    mask = get_dose_grid_structure_mask(structure_name, structure_dataset, dose_dataset)

    return dose[mask]


def create_dvh(structure, structure_dataset, dose_dataset):
    structure_dose_values = find_dose_within_structure(
        structure, structure_dataset, dose_dataset
    )
    hist = np.histogram(structure_dose_values, 100)
    freq = hist[0]
    bin_edge = hist[1]
    bin_mid = (bin_edge[1::] + bin_edge[:-1:]) / 2

    cumulative = np.cumsum(freq[::-1])
    cumulative = cumulative[::-1]
    bin_mid = np.append([0], bin_mid)

    cumulative = np.append(cumulative[0], cumulative)
    percent_cumulative = cumulative / cumulative[0] * 100

    plt.plot(bin_mid, percent_cumulative, label=structure)
    plt.title("DVH")
    plt.xlabel("Dose (Gy)")
    plt.ylabel("Relative Volume (%)")


def sum_doses_in_datasets(
    datasets: Sequence["pydicom.dataset.Dataset"],
) -> "pydicom.dataset.Dataset":
    """Sum two or more DICOM dose grids and save to new DICOM RT
    Dose dataset"

    Parameters
    ----------
    datasets : sequence of pydicom.dataset.Dataset
        A sequence of DICOM RT Dose datasets whose doses are to be
        summed.

    Returns
    -------
    pydicom.dataset.Dataset
        A new DICOM RT Dose dataset whose dose is the sum of all doses
        within `datasets`
    """

    if not all(ds.Modality == "RTDOSE" for ds in datasets):
        raise ValueError("`datasets` must only contain DICOM RT Dose datasets.")

    if not patient_ids_in_datasets_are_equal(datasets):
        raise ValueError("Patient ID must match for all datasets")

    if not all(ds.DoseSummationType == "PLAN" for ds in datasets):
        raise ValueError(
            "Only DICOM RT Doses whose DoseSummationTypes are 'PLAN' are supported"
        )

    if not all(ds.DoseUnits == datasets[0].DoseUnits for ds in datasets):
        raise ValueError(
            "All DICOM RT Doses must have the same units ('GY or 'RELATIVE')"
        )

    if not coords_in_datasets_are_equal(datasets):
        raise ValueError("All dose grids must have perfectly coincident coordinates")

    ds_summed = copy.deepcopy(datasets[0])

    ds_summed.BitsAllocated = 32
    ds_summed.BitsStored = 32
    ds_summed.HighBit = 31
    ds_summed.DoseSummationType = "MULTI_PLAN"
    ds_summed.DoseComment = "Summed Dose"

    if not all(ds.DoseType in ("PHYSICAL", "EFFECTIVE") for ds in datasets):
        raise ValueError(
            "Only DICOM RT Doses whose DoseTypes are 'PHYSICAL' or "
            "'EFFECTIVE' are supported"
        )
    if any(ds.DoseType == "EFFECTIVE" for ds in datasets):
        ds_summed.DoseType = "EFFECTIVE"
    else:
        ds_summed.DoseType = "PHYSICAL"

    doses = np.array([dose_from_dataset(ds) for ds in datasets])
    doses_summed = np.sum(doses, axis=0, dtype=np.float32)

    ds_summed.DoseGridScaling = np.max(doses_summed) / (2 ** int(ds_summed.HighBit))

    pixel_array_summed = (doses_summed / ds_summed.DoseGridScaling).astype(np.uint32)
    ds_summed.PixelData = pixel_array_summed.tobytes()

    return ds_summed
