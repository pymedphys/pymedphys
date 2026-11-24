# Copyright (C) 2026 Matthew Jennings
# Copyright (C) 2018 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""The tests given here are replicated using pymedphys.gamma from the
method given within the following paper:

> C. Agnew, C. McGarry, A tool to include gamma analysis software into a
> quality assurance program. Radiotherapy and Oncology (2016), >
http://dx.doi.org/10.1016/j.radonc.2015.11.034
"""

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

import pymedphys
from pymedphys._data import download

# pylint: disable=C0103,C1801


def get_data_file(filename):
    return download.get_file_within_data_zip("gamma_test_data.zip", filename)


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

    ds_ref = pydicom.dcmread(filepath_ref)
    ds_eval = pydicom.dcmread(filepath_eval)

    axes_reference = load_yx_from_dicom(ds_ref)
    dose_reference = dose_from_dataset(ds_ref)

    axes_evaluation = load_yx_from_dicom(ds_eval)
    dose_evaluation = dose_from_dataset(ds_eval)

    gamma = pymedphys.gamma(
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

    gamma_pass = pymedphys.gamma_percent_passed(gamma)

    assert np.round(gamma_pass, decimals=1) == result


@pytest.mark.pydicom
def test_max_gamma():
    local_gamma(
        get_data_file("H&N_VMAT_Reference_1mmPx.dcm"),
        get_data_file("H&N_VMAT_Evaluated_1mmPx.dcm"),
        93.6,
        random_subset=RANDOM_SUBSET,
        max_gamma=1.4,
    )

    local_gamma(
        get_data_file("H&N_VMAT_Reference_1mmPx.dcm"),
        get_data_file("H&N_VMAT_Evaluated_1mmPx.dcm"),
        93.6,
        random_subset=RANDOM_SUBSET,
        max_gamma=1.0001,
    )


@pytest.mark.pydicom
def test_local_gamma_1mm():
    local_gamma(
        get_data_file("H&N_VMAT_Reference_1mmPx.dcm"),
        get_data_file("H&N_VMAT_Evaluated_1mmPx.dcm"),
        93.6,
        random_subset=RANDOM_SUBSET,
    )


LOCAL_GAMMA_0_25_BASELINE = 96.9


@pytest.mark.pydicom
def test_local_gamma_0_25mm():
    local_gamma(
        get_data_file("H&N_VMAT_Reference_0_25mmPx.dcm"),
        get_data_file("H&N_VMAT_Evaluated_0_25mmPx.dcm"),
        LOCAL_GAMMA_0_25_BASELINE,
        random_subset=RANDOM_SUBSET,
    )


@pytest.mark.slow
@pytest.mark.pydicom
def test_multi_inputs():
    files = (
        get_data_file("H&N_VMAT_Reference_0_25mmPx.dcm"),
        get_data_file("H&N_VMAT_Evaluated_0_25mmPx.dcm"),
    )
    options = {"random_subset": RANDOM_SUBSET, "max_gamma": 1.0001}
    gamma = run_gamma(
        *files, dose_threshold=[1, 0.2], distance_threshold=[1, 4], **options
    )

    # Each pair is searched at its own step, the distance threshold divided
    # by interp_fraction, so a list gives what separate calls give. The 1 mm
    # pairs are unchanged. The 4 mm pairs were 99.8 and 99.2 while a list
    # searched them at a finer step than they get alone. With
    # interp_fraction=40 the four pairs give 97.1, 99.9, 94.3 and 99.6.
    baseline = {
        (1, 1): LOCAL_GAMMA_0_25_BASELINE,
        (1, 4): 99.4,
        (0.2, 1): 91.8,
        (0.2, 4): 90.4,
    }

    assert len(gamma) == len(baseline)
    for (dose_threshold, distance_threshold), value in gamma.items():
        pair = (dose_threshold, distance_threshold)
        assert (
            np.round(pymedphys.gamma_percent_passed(value), decimals=1)
            == baseline[pair]
        )

        alone = run_gamma(
            *files,
            dose_threshold=dose_threshold,
            distance_threshold=distance_threshold,
            **options,
        )
        np.testing.assert_array_equal(value, alone, err_msg=str(pair))
