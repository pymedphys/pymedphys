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


from pymedphys.gamma import gamma_shell
import pydicom
import numpy as np
import os
import pytest
"""The tests given here are replicated using pymedphys.gamma from the method
given within the following paper:

> C. Agnew, C. McGarry, A tool to include gamma analysis software into a
> quality assurance program. Radiotherapy and Oncology (2016),
> http://dx.doi.org/10.1016/j.radonc.2015.11.034
"""

# pylint: disable=C0103,C1801


DATA_DIRECTORY = os.path.join(
    os.path.dirname(__file__), "../data/gamma/agnew_mcgarry_images")

REF_VMAT_1mm = os.path.abspath(os.path.join(
    DATA_DIRECTORY, 'H&N_VMAT_Reference_1mmPx.dcm'))
EVAL_VMAT_1mm = os.path.abspath(os.path.join(
    DATA_DIRECTORY, 'H&N_VMAT_Evaluated_1mmPx.dcm'))

REF_VMAT_0_25mm = os.path.abspath(os.path.join(
    DATA_DIRECTORY, 'H&N_VMAT_Reference_0_25mmPx.dcm'))
EVAL_VMAT_0_25mm = os.path.abspath(os.path.join(
    DATA_DIRECTORY, 'H&N_VMAT_Evaluated_0_25mmPx.dcm'))


RANDOM_SUBSET = 50000


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


def local_gamma(filepath_ref, filepath_eval, result, random_subset=None,
                max_gamma=1.1):
    """The results of MU Density calculation should not change
    """

    if random_subset is not None:
        np.random.seed(42)

    dcm_ref = pydicom.read_file(filepath_ref)
    dcm_eval = pydicom.read_file(filepath_eval)

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
        max_gamma=max_gamma, local_gamma=True, skip_once_passed=True,
        random_subset=random_subset)

    valid_gamma = gamma[np.invert(np.isnan(gamma))]
    gamma_pass = 100 * np.sum(valid_gamma <= 1) / len(valid_gamma)

    assert np.round(gamma_pass, decimals=1) == result


def test_max_gamma():
    local_gamma(REF_VMAT_1mm, EVAL_VMAT_1mm, 93.6,
                random_subset=RANDOM_SUBSET, max_gamma=1.4)

    local_gamma(REF_VMAT_1mm, EVAL_VMAT_1mm, 93.6,
                random_subset=RANDOM_SUBSET, max_gamma=1.0001)


def test_local_gamma_1mm():
    local_gamma(REF_VMAT_1mm, EVAL_VMAT_1mm, 93.6, random_subset=RANDOM_SUBSET)


def test_local_gamma_0_25mm():
    local_gamma(REF_VMAT_0_25mm, EVAL_VMAT_0_25mm,
                96.9, random_subset=RANDOM_SUBSET)
