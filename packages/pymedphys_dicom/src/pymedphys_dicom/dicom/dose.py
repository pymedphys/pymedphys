# Copyright (C) 2016-2019 Matthew Jennings and Simon Biggs

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


"""A DICOM RT Dose toolbox"""

import warnings

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import path

import pydicom
import pydicom.uid

from .structure import pull_structure
from .coords import coords_from_xyz_axes, xyz_axes_from_dataset


# pylint: disable=C0103


def zyx_and_dose_from_dataset(dataset):
    x, y, z = xyz_axes_from_dataset(dataset)
    coords = (z, y, x)
    dose = dose_from_dataset(dataset, reshape=False)

    return coords, dose


def dose_from_dataset(ds, set_transfer_syntax_uid=True, reshape=True):
    r"""Extract the dose grid from a DICOM RT Dose file.

    .. deprecated:: 0.5.0
            `dose_from_dataset` will be removed in a future version of
            PyMedPhys in favour of a new & improved API.
    """

    if set_transfer_syntax_uid:
        ds.file_meta.TransferSyntaxUID = pydicom.uid.ImplicitVRLittleEndian

    if reshape:
        warnings.warn((
            '`dose_from_dataset` currently reshapes the dose grid. In a '
            'future version this will no longer occur. To begin using this '
            'function without the reshape pass the parameter `reshape=False` '
            'when calling `dose_from_dataset`.'), UserWarning)
        pixels = np.transpose(
            ds.pixel_array, (1, 2, 0))
    else:
        pixels = ds.pixel_array

    dose = pixels * ds.DoseGridScaling

    return dose


def axes_and_dose_from_dicom(dicom_filepath):
    ds = pydicom.dcmread(dicom_filepath, force=True)
    axes = xyz_axes_from_dataset(ds)
    dose = dose_from_dataset(ds)

    return axes, dose


def load_dicom_data(ds, depth_adjust):
    dose = dose_from_dataset(ds)
    crossplane, vertical, inplane = xyz_axes_from_dataset(ds)

    depth = vertical + depth_adjust

    return inplane, crossplane, depth, dose


def extract_depth_dose(ds, depth_adjust, averaging_distance=0):
    inplane, crossplane, depth, dose = load_dicom_data(ds, depth_adjust)

    inplane_ref = abs(inplane) <= averaging_distance
    crossplane_ref = abs(crossplane) <= averaging_distance

    sheet_dose = dose[:, :, inplane_ref]
    column_dose = sheet_dose[:, crossplane_ref, :]

    depth_dose = np.mean(column_dose, axis=(1, 2))

    # uncertainty = np.std(column_dose, axis=(1, 2)) / depth_dose
    # assert np.all(uncertainty < 0.01),
    # "Shouldn't average over more than 1% uncertainty"

    return depth, depth_dose


def extract_profiles(ds, depth_adjust, depth_lookup, averaging_distance=0):

    inplane, crossplane, depth, dose = load_dicom_data(ds, depth_adjust)

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


def average_bounding_profiles(ds, depth_adjust, depth_lookup,
                              averaging_distance=0):
    inplane, crossplane, depth, _ = load_dicom_data(ds, depth_adjust)

    if depth_lookup in depth:
        return extract_profiles(
            ds, depth_adjust, depth_lookup, averaging_distance)
    else:
        print(
            'Specific depth not found, interpolating from surrounding depths')
        shallower, deeper = bounding_vals(depth_lookup, depth)

        _, shallower_inplane, _, shallower_crossplane = np.array(
            extract_profiles(ds, depth_adjust, shallower, averaging_distance))

        _, deeper_inplane, _, deeper_crossplane = np.array(
            extract_profiles(ds, depth_adjust, deeper, averaging_distance))

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


def _get_indices(z_list, z_val):
    indices = np.array([item[0] for item in z_list])
    # This will error if more than one contour exists on a given slice
    desired_indices = np.where(indices == z_val)[0]
    # Multiple contour sets per slice not yet implemented

    return desired_indices


def get_dose_grid_structure_mask(structure_name, dcm_struct, dcm_dose):
    x_dose, y_dose, z_dose = xyz_axes_from_dataset(dcm_dose)
    dose = dose_from_dataset(dcm_dose)

    xx_dose, yy_dose = np.meshgrid(x_dose, y_dose)
    points = np.swapaxes(np.vstack([xx_dose.ravel(), yy_dose.ravel()]), 0, 1)

    x_structure, y_structure, z_structure = pull_structure(
        structure_name, dcm_struct)
    structure_z_values = np.array([item[0] for item in z_structure])

    mask = np.zeros((len(y_dose), len(x_dose), len(z_dose)), dtype=bool)

    for z_val in structure_z_values:
        structure_indices = _get_indices(z_structure, z_val)

        for structure_index in structure_indices:
            dose_index = int(np.where(z_dose == z_val)[0])

            assert z_structure[structure_index][0] == z_dose[dose_index]

            structure_polygon = path.Path([
                (
                    x_structure[structure_index][i],
                    y_structure[structure_index][i]
                )
                for i in range(len(x_structure[structure_index]))
            ])
            mask[:, :, dose_index] = mask[:, :, dose_index] | (
                structure_polygon.contains_points(points).reshape(
                    len(y_dose), len(x_dose)))

    return mask


def find_dose_within_structure(structure_name, dcm_struct, dcm_dose):
    dose = dose_from_dataset(dcm_dose)
    mask = get_dose_grid_structure_mask(structure_name, dcm_struct, dcm_dose)

    return dose[mask]


def create_dvh(structure, dcm_struct, dcm_dose):
    structure_dose_values = find_dose_within_structure(
        structure, dcm_struct, dcm_dose)
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
    plt.title('DVH')
    plt.xlabel('Dose (Gy)')
    plt.ylabel('Relative Volume (%)')
