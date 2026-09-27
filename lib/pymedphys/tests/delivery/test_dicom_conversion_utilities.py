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

"""Conversion of delivery angles and MLC positions to DICOM strings."""

from pymedphys._imports import numpy as np

from pymedphys._dicom.delivery import utilities


def test_angles_from_a_list_are_converted():
    angles, movement = utilities.angle_dd2dcm([-90.0, 0.0, 90.0, 90.0])

    assert angles == ["270.0", "0.0", "90.0", "90.0"]
    assert movement == ["CW", "CW", "NONE", "NONE"]
    # Plain strings, so DICOM datasets hold str rather than numpy.str_ values.
    assert {type(value) for value in angles + movement} == {str}


def test_angle_conversion_leaves_the_input_array_unchanged():
    angles = np.array([-90.0, -45.0, 10.0])

    converted, _ = utilities.angle_dd2dcm(angles)

    assert converted == ["270.0", "315.0", "10.0"]
    np.testing.assert_array_equal(angles, [-90.0, -45.0, 10.0])


def test_mlc_positions_from_nested_lists_are_converted():
    # One control point, two leaf pairs of (bank A, bank B) positions.
    mlc = [[[1.0, 2.0], [3.0, 4.0]]]

    assert utilities.mlc_dd2dcm(mlc) == [["-4.0", "-2.0", "3.0", "1.0"]]
