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

import numpy as np

import pymedphys
import pymedphys._wlutz.findbb
import pymedphys._wlutz.imginterp
import pymedphys._wlutz.iview


@settings(deadline=None, max_examples=10)
@given(floats(-5, 5), floats(-5, 5))
def test_minimise_bb(bb_centre_x_deviation, bb_centre_y_deviation):
    image_path = pymedphys.data_path("wlutz_image.png", check_hash=False)
    (
        x,
        y,
        img,
    ) = pymedphys._wlutz.iview.iview_image_transform_from_path(  # pylint:disable = protected-access
        image_path
    )
    field = pymedphys._wlutz.imginterp.create_interpolated_field(  # pylint:disable = protected-access
        x, y, img
    )

    bb_diameter = 8

    reference_bb_centre = [1.47, -1.39]
    centre_to_test = [
        reference_bb_centre[0] + bb_centre_x_deviation,
        reference_bb_centre[1] + bb_centre_y_deviation,
    ]

    vectorised_to_minimise = pymedphys._wlutz.findbb.create_bb_to_minimise(  # pylint:disable = protected-access
        field, bb_diameter
    )
    simple_to_minimise = pymedphys._wlutz.findbb.create_bb_to_minimise_simple(  # pylint:disable = protected-access
        field, bb_diameter
    )

    assert np.allclose(
        vectorised_to_minimise[0](centre_to_test), simple_to_minimise[0](centre_to_test)
    )

    assert np.allclose(
        vectorised_to_minimise[1](centre_to_test), simple_to_minimise[1](centre_to_test)
    )
