# Copyright (C) 2026 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Making iCOM gantry and collimator angles continuous across ±180°."""

from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import pytest

pytest.importorskip("streamlit")

# The iView utilities use Streamlit at import time, so this import must come
# after the skip guard.
from pymedphys._experimental.streamlit.utilities.iview import _angles  # noqa: E402

# A continuous 4°/s rotation sampled at 4 Hz, as iCOM reports it: the sign
# flips where the angle passes 180°.
TIMES = pd.date_range("2025-01-01", periods=4, freq="250ms")
REPORTED = [178.0, 179.0, -180.0, -179.0]
CONTINUOUS = [178.0, 179.0, 180.0, 181.0]


@pytest.mark.parametrize(
    ("crossing", "still"), [("gantry", "collimator"), ("collimator", "gantry")]
)
def test_icom_angles_are_made_continuous(crossing, still):
    icom_datasets = pd.DataFrame(
        {"datetime": TIMES, crossing: REPORTED, still: [0.0] * len(TIMES)}
    )

    result = _angles.make_icom_angles_continuous(icom_datasets, quiet=True)

    np.testing.assert_allclose(result[crossing], CONTINUOUS)
    np.testing.assert_allclose(result[still], 0.0)


def test_read_only_angles_are_not_modified():
    """pandas 3 returns read-only views from ``Series.to_numpy()``."""
    angles = np.array(REPORTED)
    angles.setflags(write=False)

    result = _angles.attempt_to_make_angles_continuous(
        pd.Series(TIMES),
        angles,
        _angles.GANTRY_EXPECTED_SPEED_LIMIT * _angles.NOISE_BUFFER_FACTOR,
        quiet=True,
    )

    np.testing.assert_allclose(result, CONTINUOUS)
    np.testing.assert_allclose(angles, REPORTED)
