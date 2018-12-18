# Copyright (C) 2016-2018 Simon Biggs, Matthew Jennings

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version (the "AGPL-3.0+").

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License and the additional terms for more
# details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

# ADDITIONAL TERMS are also included as allowed by Section 7 of the GNU
# Affero General Public License. These additional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


"""A Dicom Dose toolbox"""

import warnings

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import path

from scipy.interpolate import splprep, splev

import pydicom
import pydicom.uid

from .._level0.libutils import get_imports
IMPORTS = get_imports(globals())


# pylint: disable=C0103


def load_dose_from_dicom(dcm, set_transfer_syntax_uid=True, reshape=True):

    if set_transfer_syntax_uid:
        dcm.file_meta.TransferSyntaxUID = pydicom.uid.ImplicitVRLittleEndian

    if reshape:
        warnings.warn((
            '`load_dose_from_dicom` currently reshapes the dose grid. In a '
            'future version this will no longer occur. To begin using this '
            'function without the reshape pass the parameter `reshape=False` '
            'when calling `load_dose_from_dicom`.'), UserWarning)
        pixels = np.transpose(
            dcm.pixel_array, (1, 2, 0))
    else:
        pixels = dcm.pixel_array

    dose = pixels * dcm.DoseGridScaling

    return dose


def load_xyz_from_dicom(dcm):
    """This function is deprecated. It is due to be replaced with either
    `extract_iec_fixed_coords` or `extract_patient_coords`, depending on which
    coordinate system is desired.
    """

    warnings.warn((
        '`load_xyz_from_dicom` returns x, y & z values in the DICOM patient'
        'coordinate system and presumes the patient\'s orientation is HFS.'
        'This presumption may not be correct and so the function may return'
        'incorrect x, y, z values. In the future, this function will be removed. '
        'It is currently preserved for temporary backwards compatibility.'
    ), UserWarning)

    resolution = np.array(
        dcm.PixelSpacing).astype(float)
    dx = resolution[0]

    x = (
        dcm.ImagePositionPatient[0] +
        np.arange(0, dcm.Columns * dx, dx))

    dy = resolution[1]
    y = (
        dcm.ImagePositionPatient[1] +
        np.arange(0, dcm.Rows * dy, dy))

    z = (
        np.array(dcm.GridFrameOffsetVector) +
        dcm.ImagePositionPatient[2])

    return x, y, z


def extract_patient_coords(dcm):
    r"""Returns the x, y and z coordinates of a DICOM RT Dose file's dose grid
        in the DICOM patient coordinate system

    Parameters
    ----------
    dcm
       A pydicom FileDataset - ordinarily returned by pydicom.dcmread().
       Must represent a valid DICOM RT Dose file.

    Returns
    -------
    (x, y, z)
        A tuple of ndarrays containing the x, y and z coordinates of the DICOM
        RT Dose file's dose grid, given in the DICOM patient coordinate system
        [1]_.

    Notes
    -----
    Supported scan orientations [2]_:

    =========================== =======================
    Orientation                 ImageOrientationPatient
    =========================== =======================
    Feet First Decubitus Left   [0, 1, 0, 1, 0, 0]
    Feet First Decubitus Right  [0, -1, 0, -1, 0, 0]
    Feet First Prone            [1, 0, 0, 0, -1, 0]
    Feet First Supine           [-1, 0, 0, 0, 1, 0]
    Head First Decubitus Left   [0, -1, 0, 1, 0, 0]
    Head First Decubitus Right  [0, 1, 0, -1, 0, 0]
    Head First Prone            [-1, 0, 0, 0, -1, 0]
    Head First Supine           [1, 0, 0, 0, 1, 0]
    =========================== =======================

    References
    ----------
    .. [1] "C.7.6.2.1.1 Image Position and Image Orientation",
       "DICOM PS3.3 2016a - Information Object Definitions",
       http://dicom.nema.org/MEDICAL/dicom/2016a/output/chtml/part03/sect_C.7.6.2.html#sect_C.7.6.2.1.1

    .. [2] O. McNoleg, "Generalized coordinate transformations for Monte Carlo
       (DOSXYZnrc and VMC++) verifications of DICOM compatible radiotherapy
       treatment plans", arXiv:1406.0014, Table 1,
       https://arxiv.org/ftp/arxiv/papers/1406/1406.0014.pdf
    """

    position = np.array(dcm.ImagePositionPatient)
    orientation = np.array(dcm.ImageOrientationPatient)

    di = float(dcm.PixelSpacing[0])
    dj = float(dcm.PixelSpacing[1])

    is_prone_or_supine = np.array_equal(
        np.absolute(orientation), np.array([1., 0., 0., 0., 1., 0.]))

    is_decubitus = np.array_equal(
        np.absolute(orientation), np.array([0., 1., 0., 1., 0., 0.]))

    # Only proceed if the DICOM RT Dose file has a supported orientation.
    # I.e. no pitch, yaw or non-cardinal roll angle exists between the dose
    # grid and the 'patient'
    if is_prone_or_supine:
        xflip = (orientation[0] == -1)
        yflip = (orientation[4] == -1)
        head_first = (xflip == yflip)

        x = orientation[0]*position[0] + np.arange(0, dcm.Columns * di, di)
        y = orientation[4]*position[1] + np.arange(0, dcm.Rows * dj, dj)

    elif is_decubitus:
        xflip = (orientation[3] == -1)
        yflip = (orientation[1] == -1)
        head_first = (xflip != yflip)

        x = orientation[3]*position[0] + np.arange(0, dcm.Rows * dj, dj)
        y = orientation[1]*position[1] + np.arange(0, dcm.Columns * di, di)
    else:
        raise ValueError(
            "Dose grid orientation is not supported. "
            "Z-axis of dose grid must be parallel to z-axis of patient")

    if xflip:
        x = np.flip(x)
    if yflip:
        y = np.flip(y)

    if head_first:
        z = position[2] + np.array(dcm.GridFrameOffsetVector)
    else:
        z = np.flip(-position[2] + np.array(dcm.GridFrameOffsetVector))

    return x, y, z


def coords_and_dose_from_dcm(dcm_filepath):
    dcm = pydicom.read_file(dcm_filepath, force=True)
    x, y, z = load_xyz_from_dicom(dcm)
    coords = (y, x, z)
    dose = load_dose_from_dicom(dcm)

    return coords, dose


def load_dicom_data(dcm, depth_adjust):
    dose = load_dose_from_dicom(dcm)
    crossplane, vertical, inplane = load_xyz_from_dicom(dcm)

    depth = vertical + depth_adjust

    return inplane, crossplane, depth, dose


def extract_depth_dose(dcm, depth_adjust, averaging_distance=0):
    inplane, crossplane, depth, dose = load_dicom_data(dcm, depth_adjust)

    inplane_ref = abs(inplane) <= averaging_distance
    crossplane_ref = abs(crossplane) <= averaging_distance

    sheet_dose = dose[:, :, inplane_ref]
    column_dose = sheet_dose[:, crossplane_ref, :]

    depth_dose = np.mean(column_dose, axis=(1, 2))

    # uncertainty = np.std(column_dose, axis=(1, 2)) / depth_dose
    # assert np.all(uncertainty < 0.01),
    # "Shouldn't average over more than 1% uncertainty"

    return depth, depth_dose


def extract_profiles(dcm, depth_adjust, depth_lookup, averaging_distance=0):

    inplane, crossplane, depth, dose = load_dicom_data(dcm, depth_adjust)

    inplane_ref = abs(inplane) <= averaging_distance
    crossplane_ref = abs(crossplane) <= averaging_distance

    depth_reference = depth == depth_lookup

    dose_at_depth = dose[depth_reference, :, :]
    inplane_dose = np.mean(dose_at_depth[:, crossplane_ref, :], axis=(0, 1))
    crossplane_dose = np.mean(dose_at_depth[:, :, inplane_ref], axis=(0, 2))

    return inplane, inplane_dose, crossplane, crossplane_dose


def nearest_negative(diff):
    neg_diff = np.copy(diff)
    neg_diff[neg_diff > 0] = -np.inf
    return np.argmax(neg_diff)


def bounding_vals(test, values):
    npvalues = np.array(values).astype('float')
    diff = npvalues - test
    upper = nearest_negative(-diff)
    lower = nearest_negative(diff)

    return values[lower], values[upper]


def average_bounding_profiles(dcm, depth_adjust, depth_lookup,
                              averaging_distance=0):
    inplane, crossplane, depth, _ = load_dicom_data(dcm, depth_adjust)

    if depth_lookup in depth:
        return extract_profiles(
            dcm, depth_adjust, depth_lookup, averaging_distance)
    else:
        print(
            'Specific depth not found, interpolating from surrounding depths')
        shallower, deeper = bounding_vals(depth_lookup, depth)

        _, shallower_inplane, _, shallower_crossplane = np.array(
            extract_profiles(dcm, depth_adjust, shallower, averaging_distance))

        _, deeper_inplane, _, deeper_crossplane = np.array(
            extract_profiles(dcm, depth_adjust, deeper, averaging_distance))

        depth_range = deeper - shallower
        shallower_weight = 1 - (depth_lookup - shallower) / depth_range
        deeper_weight = 1 - (deeper - depth_lookup) / depth_range

        inplane_dose = (
            shallower_weight * shallower_inplane +
            deeper_weight * deeper_inplane)
        crossplane_dose = (
            shallower_weight * shallower_crossplane +
            deeper_weight * deeper_crossplane)

        return inplane, inplane_dose, crossplane, crossplane_dose


def pull_structure_by_number(number, dcm_struct):
    contours_by_slice_raw = [
        item.ContourData
        for item in dcm_struct.ROIContourSequence[number].ContourSequence
    ]
    x = [
        np.array(item[0::3])
        for item in contours_by_slice_raw]
    y = [
        np.array(item[1::3])
        for item in contours_by_slice_raw]
    z = [
        np.array(item[2::3])
        for item in contours_by_slice_raw]

    return x, y, z


def pull_structure(string, dcm_struct):
    structure_names = np.array(
        [item.ROIName for item in dcm_struct.StructureSetROISequence])
    reference = structure_names == string
    if np.all(reference == False):  # pylint: disable=C0121
        raise Exception("Structure not found (case sensitive)")

    index = int(np.where(reference)[0])
    x, y, z = pull_structure_by_number(
        index, dcm_struct)

    return x, y, z


def _get_index(z_list, z_val):
    indices = np.array([item[0] for item in z_list])
    # This will error if more than one contour exists on a given slice
    index = int(np.where(indices == z_val)[0])
    # Multiple contour sets per slice not yet implemented

    return index


def find_dose_within_structure(structure, dcm_struct, dcm_dose):
    x_dose, y_dose, z_dose = load_xyz_from_dicom(dcm_dose)
    dose = load_dose_from_dicom(dcm_dose)

    xx_dose, yy_dose = np.meshgrid(x_dose, y_dose)
    points = np.swapaxes(np.vstack([xx_dose.ravel(), yy_dose.ravel()]), 0, 1)

    x_structure, y_structure, z_structure = pull_structure(
        structure, dcm_struct)
    structure_z_values = np.array([item[0] for item in z_structure])

    structure_dose_values = np.array([])

    for z_val in structure_z_values:
        structure_index = _get_index(z_structure, z_val)
        dose_index = int(np.where(z_dose == z_val)[0])

        assert z_structure[structure_index][0] == z_dose[dose_index]

        structure_polygon = path.Path([
            (
                x_structure[structure_index][i],
                y_structure[structure_index][i]
            )
            for i in range(len(x_structure[structure_index]))
        ])
        mask = structure_polygon.contains_points(points).reshape(
            len(y_dose), len(x_dose))
        masked_dose = dose[:, :, dose_index]
        structure_dose_values = np.append(
            structure_dose_values, masked_dose[mask])

    return structure_dose_values


def create_dvh(structure, dcm_struct, dcm_dose):
    structure_dose_values = find_dose_within_structure(
        structure, dcm_struct, dcm_dose)
    hist = np.histogram(structure_dose_values, 100)
    freq = hist[0]
    bin_edge = hist[1]
    bin_mid = (bin_edge[1::] + bin_edge[:-1:])/2

    cumulative = np.cumsum(freq[::-1])
    cumulative = cumulative[::-1]
    bin_mid = np.append([0], bin_mid)

    cumulative = np.append(cumulative[0], cumulative)
    percent_cumulative = cumulative / cumulative[0] * 100

    plt.plot(bin_mid, percent_cumulative, label=structure)
    plt.title('DVH')
    plt.xlabel('Dose (Gy)')
    plt.ylabel('Relative Volume (%)')


def list_structures(dcm_struct):
    return [item.ROIName for item in dcm_struct.StructureSetROISequence]


def resample_contour(contour, n=50):
    tck, u = splprep(
        [contour[0], contour[1], contour[2]], s=0, k=1)
    new_points = splev(np.arange(0, 1, 1/n), tck)

    return new_points


def resample_contour_set(contours, n=50):

    resampled_contours = [
        resample_contour([x, y, z], n)
        for x, y, z in zip(*contours)
    ]

    return resampled_contours


def contour_to_points(contours):
    resampled_contours = resample_contour_set([
        contours[1], contours[0], contours[2]])
    contour_points = np.concatenate(resampled_contours, axis=1)

    return contour_points
