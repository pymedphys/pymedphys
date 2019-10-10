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


"""The tests given here are replicated using pymedphys.gamma from the
method given within the following paper:

> C. Agnew, C. McGarry, A tool to include gamma analysis software into a
> quality assurance program. Radiotherapy and Oncology (2016), >
http://dx.doi.org/10.1016/j.radonc.2015.11.034
"""

import os

import pytest

import numpy as np

import pydicom

from pymedphys._gamma.implementation import gamma_shell
from pymedphys._gamma.utilities import calculate_pass_rate

# pylint: disable=C0103,C1801


DATA_DIRECTORY = os.path.join(os.path.dirname(__file__), "data", "agnew_mcgarry_images")

REF_VMAT_1mm = os.path.abspath(
    os.path.join(DATA_DIRECTORY, "H&N_VMAT_Reference_1mmPx.dcm")
)
EVAL_VMAT_1mm = os.path.abspath(
    os.path.join(DATA_DIRECTORY, "H&N_VMAT_Evaluated_1mmPx.dcm")
)

REF_VMAT_0_25mm = os.path.abspath(
    os.path.join(DATA_DIRECTORY, "H&N_VMAT_Reference_0_25mmPx.dcm")
)
EVAL_VMAT_0_25mm = os.path.abspath(
    os.path.join(DATA_DIRECTORY, "H&N_VMAT_Evaluated_0_25mmPx.dcm")
)


RANDOM_SUBSET = 50000


def dose_from_dataset(ds):
    pixels = ds.pixel_array
    dose = pixels * ds.DoseGridScaling

    return dose


def load_yx_from_dicom(ds):
    resolution = np.array(ds.PixelSpacing).astype(float)
    dx = resolution[0]
    x = ds.ImagePositionPatient[0] + np.arange(0, ds.Columns * dx, dx)

    dy = resolution[1]
    y = ds.ImagePositionPatient[1] + np.arange(0, ds.Rows * dy, dy)

    return y, x


def run_gamma(
    filepath_ref,
    filepath_eval,
    random_subset=None,
    max_gamma=1.1,
    dose_threshold=1,
    distance_threshold=1,
):

    if random_subset is not None:
        np.random.seed(42)

    ds_ref = pydicom.read_file(filepath_ref)
    ds_eval = pydicom.read_file(filepath_eval)

    axes_reference = load_yx_from_dicom(ds_ref)
    dose_reference = dose_from_dataset(ds_ref)

    axes_evaluation = load_yx_from_dicom(ds_eval)
    dose_evaluation = dose_from_dataset(ds_eval)

    gamma = gamma_shell(
        axes_reference,
        dose_reference,
        axes_evaluation,
        dose_evaluation,
        dose_threshold,
        distance_threshold,
        lower_percent_dose_cutoff=20,
        interp_fraction=10,
        max_gamma=max_gamma,
        local_gamma=True,
        skip_once_passed=True,
        random_subset=random_subset,
    )

    return gamma


def local_gamma(
    filepath_ref,
    filepath_eval,
    result,
    random_subset=None,
    max_gamma=1.1,
    dose_threshold=1,
    distance_threshold=1,
):

    gamma = run_gamma(
        filepath_ref,
        filepath_eval,
        random_subset,
        max_gamma,
        dose_threshold,
        distance_threshold,
    )

    gamma_pass = calculate_pass_rate(gamma)

    assert np.round(gamma_pass, decimals=1) == result


def test_max_gamma():
    local_gamma(
        REF_VMAT_1mm, EVAL_VMAT_1mm, 93.6, random_subset=RANDOM_SUBSET, max_gamma=1.4
    )

    local_gamma(
        REF_VMAT_1mm, EVAL_VMAT_1mm, 93.6, random_subset=RANDOM_SUBSET, max_gamma=1.0001
    )


def test_local_gamma_1mm():
    local_gamma(REF_VMAT_1mm, EVAL_VMAT_1mm, 93.6, random_subset=RANDOM_SUBSET)


LOCAL_GAMMA_0_25_BASELINE = 96.9


def test_local_gamma_0_25mm():
    local_gamma(
        REF_VMAT_0_25mm,
        EVAL_VMAT_0_25mm,
        LOCAL_GAMMA_0_25_BASELINE,
        random_subset=RANDOM_SUBSET,
    )


@pytest.mark.slow
def test_multi_inputs():
    gamma = run_gamma(
        REF_VMAT_0_25mm,
        EVAL_VMAT_0_25mm,
        random_subset=RANDOM_SUBSET,
        max_gamma=1.0001,
        dose_threshold=[1, 0.2],
        distance_threshold=[1, 4],
    )

    baseline = {
        (1, 1): LOCAL_GAMMA_0_25_BASELINE,
        (1, 4): 99.8,  # 99.9 with higher interp_fraction
        (0.2, 1): 91.8,  # 94.4 with higher interp_fraction
        (0.2, 4): 99.2,  # 99.7 with higher interp_fraction
    }

    for key, value in gamma.items():
        assert np.round(calculate_pass_rate(value), decimals=1) == baseline[key]
