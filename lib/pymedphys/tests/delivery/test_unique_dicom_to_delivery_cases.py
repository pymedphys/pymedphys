# Copyright (C) 2020 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


# pylint: disable = redefined-outer-name


from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

import pymedphys

LEAF_PAIR_WIDTHS = (10,) + (5,) * 78 + (10,)
MAX_LEAF_GAP = 410
GRID_RESOLUTION = 1


GAMMA_OPTIONS = {
    "dose_percent_threshold": 2,
    "distance_mm_threshold": 0.5,
    "local_gamma": True,
    "quiet": True,
    "max_gamma": 5,
    "lower_percent_dose_cutoff": 20,
}


@pytest.mark.xfail(reason="The unique cases being tested here are not yet supported")
def test_dicom_trf_comparison(_data_paths):
    """Focusing on unique DICOM header cases.

    See <https://github.com/pymedphys/pymedphys/issues/1142> for more
    details regarding the use case.
    """

    GRID = pymedphys.metersetmap.grid(
        max_leaf_gap=MAX_LEAF_GAP,
        grid_resolution=GRID_RESOLUTION,
        leaf_pair_widths=LEAF_PAIR_WIDTHS,
    )
    COORDS = (GRID["jaw"], GRID["mlc"])

    dicom_paths, trf_paths = _data_paths

    dicom_deliveries = [pymedphys.Delivery.from_dicom(path) for path in dicom_paths]
    trf_deliveries = [pymedphys.Delivery.from_trf(path) for path in trf_paths]

    for dicom_delivery, trf_delivery in zip(dicom_deliveries, trf_deliveries):
        dicom_metersetmap = dicom_delivery.metersetmap(
            max_leaf_gap=MAX_LEAF_GAP,
            grid_resolution=GRID_RESOLUTION,
            leaf_pair_widths=LEAF_PAIR_WIDTHS,
        )
        trf_metersetmap = trf_delivery.metersetmap(
            max_leaf_gap=MAX_LEAF_GAP,
            grid_resolution=GRID_RESOLUTION,
            leaf_pair_widths=LEAF_PAIR_WIDTHS,
        )

        gamma = pymedphys.gamma(
            COORDS,
            _to_tuple(dicom_metersetmap),
            COORDS,
            _to_tuple(trf_metersetmap),
            **GAMMA_OPTIONS,
        )

        valid_gamma = gamma[~np.isnan(gamma)]
        pass_ratio = np.sum(valid_gamma <= 1) / len(valid_gamma)

        assert pass_ratio >= 0.98


@pytest.fixture()
def _data_paths():
    testing_paths = pymedphys.zip_data_paths("dicom-trf-pairs.zip")
    dicom_paths = [path for path in testing_paths if path.suffix == ".dcm"]
    trf_paths = [path.with_suffix(".trf") for path in dicom_paths]

    for path in trf_paths:
        assert path.exists()

    return dicom_paths, trf_paths


def _to_tuple(array):
    return tuple(map(tuple, array))
