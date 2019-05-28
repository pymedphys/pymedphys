# Copyright (C) 2018 Simon Biggs
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


import warnings

import numpy as np

import pydicom

from pymedphys_dicom.dicom import (
    axes_and_dose_from_dicom,
    xyz_axes_from_dataset,
    dose_from_dataset)

from ..implementation import gamma_shell, gamma_filter_numpy
from ..utilities import calculate_pass_rate


def gamma_dicom(dicom_ref_filepath, dicom_eval_filepath,
                dose_percent_threshold, distance_mm_threshold,
                **kwargs):

    axes_reference, dose_reference = coords_and_dose_from_dicom(
        dicom_ref_filepath)
    axes_evaluation, dose_evaluation = coords_and_dose_from_dicom(
        dicom_eval_filepath)

    gamma = gamma_shell(
        axes_reference, dose_reference,
        axes_evaluation, dose_evaluation,
        dose_percent_threshold, distance_mm_threshold,
        **kwargs)

    return gamma


def gamma_percent_pass(dcm_ref_filepath, dcm_eval_filepath,
                       dose_percent_threshold, distance_mm_threshold,
                       method='shell', **kwargs):

    axes_reference, dose_reference = axes_and_dose_from_dicom(
        dcm_ref_filepath)
    axes_evaluation, dose_evaluation = axes_and_dose_from_dicom(
        dcm_eval_filepath)

    if method == 'shell':
        gamma = gamma_shell(
            axes_reference, dose_reference,
            axes_evaluation, dose_evaluation,
            dose_percent_threshold, distance_mm_threshold,
            **kwargs)

        percent_pass = calculate_pass_rate(gamma)

    elif method == 'filter':
        percent_pass = gamma_filter_numpy(
            axes_reference, dose_reference,
            axes_evaluation, dose_evaluation,
            dose_percent_threshold, distance_mm_threshold,
            **kwargs)
    else:
        raise ValueError('method should be either `shell` or `filter`')

    return percent_pass


def coords_and_dose_from_dicom(dicom_filepath):
    ds = pydicom.read_file(dicom_filepath, force=True)
    x, y, z = load_xyz_from_dicom(ds)
    coords = (y, x, z)
    dose = load_dose_from_dicom(ds)

    return coords, dose


def load_dose_from_dicom(ds, set_transfer_syntax_uid=True, reshape=True):
    r"""Extract the dose grid from a DICOM RT Dose file.
    .. deprecated:: 0.5.0
            `load_dose_from_dicom` will be removed in a future version of PyMedPhys.
            It is replaced by `extract_dose`, which provides additional dose-related
            information and conforms to a new coordinate system handling convention.
    """

    if set_transfer_syntax_uid:
        ds.file_meta.TransferSyntaxUID = pydicom.uid.ImplicitVRLittleEndian

    if reshape:
        warnings.warn((
            '`load_dose_from_dicom` currently reshapes the dose grid. In a '
            'future version this will no longer occur. To begin using this '
            'function without the reshape pass the parameter `reshape=False` '
            'when calling `load_dose_from_dicom`.'), UserWarning)
        pixels = np.transpose(
            ds.pixel_array, (1, 2, 0))
    else:
        pixels = ds.pixel_array

    dose = pixels * ds.DoseGridScaling

    return dose


def load_xyz_from_dicom(ds):
    r"""Extract the coordinates of a DICOM RT Dose file's dose grid.
    .. deprecated:: 0.5.0
            `load_xyz_from_dicom` will be removed in a future version of PyMedPhys.
            It is replaced by `extract_dicom_patient_coords`, `extract_iec_patient_coords`
            and `extract_iec_fixed_coords`, which explicitly work in their respective
            coordinate systems.
    """

    warnings.warn((
        '`load_xyz_from_dicom` returns x, y & z values in the DICOM patient '
        'coordinate system and presumes the patient\'s orientation is HFS. '
        'This presumption may not be correct and so the function may return '
        'incorrect x, y, z values. In the future, this function will be removed. '
        'It is currently preserved for temporary backwards compatibility.'
    ), UserWarning)

    resolution = np.array(ds.PixelSpacing).astype(float)

    dx = resolution[0]
    x = (ds.ImagePositionPatient[0] + np.arange(0, ds.Columns * dx, dx))

    dy = resolution[1]
    y = (ds.ImagePositionPatient[1] + np.arange(0, ds.Rows * dy, dy))

    z = (np.array(ds.GridFrameOffsetVector) + ds.ImagePositionPatient[2])

    return x, y, z
