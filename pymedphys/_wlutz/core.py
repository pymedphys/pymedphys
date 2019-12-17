# Copyright (C) 2019 Cancer Care Associates

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
