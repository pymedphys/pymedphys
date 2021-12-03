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

from pymedphys._imports import numpy as np

import pymedphys._mocks.wlutz as wlutz_mocks

from pymedphys._experimental.wlutz import main as _wlutz
from pymedphys._experimental.wlutz import reporting


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


def test_small_bb():
    field_centre = [0, 0]
    field_side_lengths = [15, 35]
    field_penumbra = 2
    field_rotation = 0

    bb_centre = [2, -10]
    bb_diameter = 1
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


def run_test(
    field_centre,
    field_side_lengths,
    field_penumbra,
    field_rotation,
    bb_centre,
    bb_diameter,
    bb_max_attenuation,
):

    x = np.arange(-30, 30.1, 0.25)
    y = np.arange(-32, 32.1, 0.25)
    img = wlutz_mocks.create_test_image(
        x,
        y,
        field_centre,
        field_side_lengths,
        field_penumbra,
        field_rotation,
        bb_centre,
        bb_diameter,
        bb_max_attenuation,
    )

    (determined_field_centre, determined_bb_centre,) = _wlutz.pymedphys_wlutz_calculate(
        x,
        y,
        img,
        bb_diameter,
        field_side_lengths,
        field_penumbra,
        field_rotation,
        fill_errors_with_nan=False,
    )

    try:
        assert np.allclose(bb_centre, determined_bb_centre, atol=0.01)
        assert np.allclose(field_centre, determined_field_centre, atol=0.01)

    except:
        reporting.image_analysis_figure(
            x,
            y,
            img,
            determined_bb_centre,
            determined_field_centre,
            field_rotation,
            bb_diameter,
            field_side_lengths,
            field_penumbra,
        )
        raise
