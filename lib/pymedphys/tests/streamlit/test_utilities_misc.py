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

"""The 8-bit greyscale conversion behind the MetersetMap app's PNG records.

The expected pixel values are worked by hand from the documented mapping:
``vmin`` to 0, ``vmax`` to 255, linear in between and rounded down. Every
input is chosen so that its scaled value is exact in floating point, which
keeps the rounding unambiguous.
"""

import warnings

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

pytest.importorskip("streamlit")

# The Streamlit utilities use Streamlit at import time, so this import must
# come after the skip guard.
from pymedphys._streamlit.utilities import misc as st_misc  # noqa: E402


def _convert_without_warnings(data: np.ndarray, vmin: float, vmax: float) -> np.ndarray:
    """Convert ``data``, failing the test if the conversion warns at all."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")

        return st_misc.normalize_and_convert_to_uint8(data, vmin=vmin, vmax=vmax)


def test_nan_and_out_of_range_values_get_defined_pixel_values() -> None:
    # The app writes gamma with vmin=0 and vmax=2, and gamma is NaN at every
    # reference point that was not analysed.
    gamma = np.array([np.nan, -np.inf, -0.5, 0.0, 0.5, 1.0, 2.0, 3.0, np.inf])

    image = _convert_without_warnings(gamma, vmin=0, vmax=2)

    assert image.dtype == np.uint8
    # 255 * 0.5 / 2 = 63.75 and 255 * 1.0 / 2 = 127.5, both rounded down.
    assert image.tolist() == [0, 0, 0, 0, 63, 127, 255, 255, 255]


def test_nan_keeps_its_place_in_a_two_dimensional_image() -> None:
    gamma = np.array(
        [
            [np.nan, np.nan, np.nan],
            [np.nan, 0.0, 1.5],
            [np.nan, 4.0, np.nan],
        ]
    )

    image = _convert_without_warnings(gamma, vmin=0, vmax=2)

    assert image.dtype == np.uint8
    # 255 * 1.5 / 2 = 191.25, rounded down.
    assert image.tolist() == [[0, 0, 0], [0, 0, 191], [0, 255, 0]]


def test_an_image_of_only_nan_is_written_as_zero() -> None:
    image = _convert_without_warnings(np.full((2, 3), np.nan), vmin=0, vmax=2)

    assert image.dtype == np.uint8
    assert image.tolist() == [[0, 0, 0], [0, 0, 0]]


def test_metersetmap_scale_from_zero_to_the_largest_value() -> None:
    # The reference and evaluation images: vmin=0, vmax=the largest MU value.
    metersetmap = np.array([[0.0, 10.0], [25.0, 40.0]])

    image = _convert_without_warnings(metersetmap, vmin=0, vmax=40.0)

    assert image.dtype == np.uint8
    # 255 * 10 / 40 = 63.75 and 255 * 25 / 40 = 159.375, both rounded down.
    assert image.tolist() == [[0, 63], [159, 255]]


def test_difference_scale_centred_on_zero() -> None:
    # The difference image: vmin=-largest, vmax=+largest absolute difference,
    # so no difference lands on mid-grey.
    difference = np.array([-8.0, -2.0, 0.0, 2.0, 8.0])

    image = _convert_without_warnings(difference, vmin=-8.0, vmax=8.0)

    assert image.dtype == np.uint8
    # 255 * 6 / 16 = 95.625, 255 * 8 / 16 = 127.5 and 255 * 10 / 16 = 159.375,
    # each rounded down.
    assert image.tolist() == [0, 95, 127, 159, 255]
