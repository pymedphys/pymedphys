# Copyright (C) 2019 Simon Biggs

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


from hypothesis import given, settings
from hypothesis.strategies import floats

import numpy as np

import pymedphys
import pymedphys._wlutz.findbb
import pymedphys._wlutz.imginterp
import pymedphys._wlutz.iview

image_path_cache = [None]


@settings(deadline=None, max_examples=10)
@given(floats(-5, 5), floats(-5, 5))
def test_minimise_bb(bb_centre_x_deviation, bb_centre_y_deviation):
    if image_path_cache[0] is None:
        image_path = pymedphys.data_path("wlutz_image.png", skip_hashing=True)
        image_path_cache[0] = image_path
    else:
        image_path = image_path_cache[0]
    x, y, img = pymedphys._wlutz.iview.iview_image_transform(image_path)
    field = pymedphys._wlutz.imginterp.create_interpolated_field(x, y, img)

    bb_diameter = 8

    reference_bb_centre = [1.47, -1.39]
    centre_to_test = [
        reference_bb_centre[0] + bb_centre_x_deviation,
        reference_bb_centre[1] + bb_centre_y_deviation,
    ]

    vectorised_to_minimise = pymedphys._wlutz.findbb.create_bb_to_minimise(
        field, bb_diameter
    )
    simple_to_minimise = pymedphys._wlutz.findbb.create_bb_to_minimise_simple(
        field, bb_diameter
    )

    assert np.allclose(
        vectorised_to_minimise(centre_to_test), simple_to_minimise(centre_to_test)
    )
