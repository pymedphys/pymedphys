# Copyright (C) 2019 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from hypothesis import given, settings
from hypothesis.strategies import floats
from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

import pymedphys

from pymedphys._experimental.wlutz import findbb, imginterp, iview


@pytest.fixture
def test_field():
    image_path = pymedphys.data_path("wlutz_image.png", check_hash=False)
    (x, y, img) = iview.iview_image_transform_from_path(image_path)
    field = imginterp.create_interpolated_field(x, y, img)

    return field


@settings(deadline=None, max_examples=10)
@given(bb_centre_x_deviation=floats(-5, 5), bb_centre_y_deviation=floats(-5, 5))
def test_minimise_bb(
    bb_centre_x_deviation,
    bb_centre_y_deviation,
    test_field,  # pylint: disable = redefined-outer-name
):

    bb_diameter = 8

    reference_bb_centre = [1.47, -1.39]
    centre_to_test = [
        reference_bb_centre[0] + bb_centre_x_deviation,
        reference_bb_centre[1] + bb_centre_y_deviation,
    ]

    vectorised_to_minimise = findbb.create_bb_to_minimise(test_field, bb_diameter)
    simple_to_minimise = findbb.create_bb_to_minimise_simple(test_field, bb_diameter)

    assert np.allclose(
        vectorised_to_minimise(centre_to_test),
        simple_to_minimise(centre_to_test),
        atol=0.001,
    )
