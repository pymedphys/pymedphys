# Copyright (C) 2019 Cancer Care Associates

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


import numpy as np

from .findbb import optimise_bb_centre
from .findfield import _initial_centre, field_centre_and_rotation_refining
from .imginterp import create_interpolated_field


def find_field_and_bb(
    x,
    y,
    img,
    edge_lengths,
    bb_diameter,
    penumbra=2,
    initial_rotation=0,
    rounding=True,
    pylinac_tol=0.2,
):
    field = create_interpolated_field(x, y, img)
    initial_centre = _initial_centre(x, y, img)

    field_centre, field_rotation = field_centre_and_rotation_refining(
        field,
        edge_lengths,
        penumbra,
        initial_centre,
        initial_rotation=initial_rotation,
        pylinac_tol=pylinac_tol,
    )

    bb_centre = optimise_bb_centre(
        field,
        bb_diameter,
        edge_lengths,
        penumbra,
        field_centre,
        field_rotation,
        pylinac_tol=pylinac_tol,
    )

    if rounding:
        bb_centre = np.round(bb_centre, decimals=2).tolist()
        field_centre = np.round(field_centre, decimals=2).tolist()
        field_rotation = np.round(field_rotation, decimals=1)

    return bb_centre, field_centre, field_rotation
