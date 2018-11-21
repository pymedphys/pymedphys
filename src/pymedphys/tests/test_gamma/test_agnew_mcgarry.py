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
# Affrero General Public License. These aditional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


# pylint: disable=C0103,C1801

import os

import numpy as np

import pydicom

from pymedphys.gamma import gamma_shell


DATA_DIRECTORY = os.path.join(
    os.path.dirname(__file__), "../data/gamma/agnew_mcgarry_images")
REF_VMAT = os.path.abspath(os.path.join(
    DATA_DIRECTORY, 'H&N_VMAT_Reference_1mmPx.dcm'))
EVAL_VMAT = os.path.abspath(os.path.join(
    DATA_DIRECTORY, 'H&N_VMAT_Evaluated_1mmPx.dcm'))


def load_dose_from_dicom(dcm):
    pixels = dcm.pixel_array
    dose = pixels * dcm.DoseGridScaling

    return dose


def load_yx_from_dicom(dcm):
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

    return y, x


def test_local_gamma():
    """The results of MU Density calculation should not change
    """
    dcm_ref = pydicom.read_file(REF_VMAT)
    dcm_eval = pydicom.read_file(EVAL_VMAT)

    coords_reference = load_yx_from_dicom(dcm_ref)
    dose_reference = load_dose_from_dicom(dcm_ref)

    coords_evaluation = load_yx_from_dicom(dcm_eval)
    dose_evaluation = load_dose_from_dicom(dcm_eval)

    gamma = gamma_shell(
        coords_reference, dose_reference,
        coords_evaluation, dose_evaluation,
        1, 1,
        lower_percent_dose_cutoff=20,
        interp_fraction=10,
        max_gamma=1.1, local_gamma=True, skip_once_passed=True)

    valid_gamma = gamma[np.invert(np.isnan(gamma))]
    gamma_pass = 100 * np.sum(valid_gamma <= 1) / len(valid_gamma)

    assert np.round(gamma_pass, decimals=1) == 95.1
