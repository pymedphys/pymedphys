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


import pytest
from pymedphys._imports import numpy as np

import pymedphys
import pymedphys._mocks.wlutz as wlutz_mocks
import pymedphys._wlutz.reporting as reporting


def test_normal_bb():
    field_centre = [0, 0]
    field_side_lengths = [20, 24]
    field_penumbra = 2
    field_rotation = 20

    bb_centre = [2, 2]
    bb_diameter = 8
    bb_max_attenuation = 0.3

    run_test(
        field_centre,
        field_side_lengths,
        field_penumbra,
        field_rotation,
        bb_centre,
        bb_diameter,
        bb_max_attenuation,
    )


@pytest.mark.skip(reason="This test currently demonstrates a limitation of the library")
def test_small_bb():
    field_centre = [0, 0]
    field_side_lengths = [20, 24]
    field_penumbra = 2
    field_rotation = 20

    bb_centre = [2, 2]
    bb_diameter = 3
    bb_max_attenuation = 0.3

    run_test(
        field_centre,
        field_side_lengths,
        field_penumbra,
        field_rotation,
        bb_centre,
        bb_diameter,
        bb_max_attenuation,
    )


def create_test_image(
    field_centre,
    field_side_lengths,
    field_penumbra,
    field_rotation,
    bb_centre,
    bb_diameter,
    bb_max_attenuation,
):
    field = wlutz_mocks.create_field_with_bb_func(
        field_centre,
        field_side_lengths,
        field_penumbra,
        field_rotation,
        bb_centre,
        bb_diameter,
        bb_max_attenuation,
    )

    x = np.arange(-20, 20.1, 0.1)
    y = np.arange(-22, 22.1, 0.1)
    xx, yy = np.meshgrid(x, y)

    img = field(xx, yy)

    return x, y, img


def run_test(
    field_centre,
    field_side_lengths,
    field_penumbra,
    field_rotation,
    bb_centre,
    bb_diameter,
    bb_max_attenuation,
):

    x, y, img = create_test_image(
        field_centre,
        field_side_lengths,
        field_penumbra,
        field_rotation,
        bb_centre,
        bb_diameter,
        bb_max_attenuation,
    )

    (
        determined_bb_centre,
        determined_field_centre,
        determined_field_rotation,
    ) = pymedphys.wlutz.find_field_and_bb(
        x,
        y,
        img,
        field_side_lengths,
        bb_diameter,
        penumbra=field_penumbra,
        pylinac_tol=None,
    )

    try:
        assert np.allclose(bb_centre, determined_bb_centre, atol=0.001)
        assert np.allclose(field_centre, determined_field_centre, atol=0.001)
        assert np.allclose(field_rotation, determined_field_rotation, atol=0.01)

    except:
        reporting.image_analysis_figure(
            x,
            y,
            img,
            determined_bb_centre,
            determined_field_centre,
            determined_field_rotation,
            bb_diameter,
            field_side_lengths,
            field_penumbra,
        )
        raise
