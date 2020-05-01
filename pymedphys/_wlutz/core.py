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


from . import findbb, findfield, imginterp


def find_field(
    x, y, img, edge_lengths, penumbra=2, fixed_rotation=None, pylinac_tol=0.2
):
    field = imginterp.create_interpolated_field(x, y, img)
    initial_centre = findfield.get_initial_centre(x, y, img)

    field_centre, field_rotation = findfield.field_centre_and_rotation_refining(
        field,
        edge_lengths,
        penumbra,
        initial_centre,
        fixed_rotation=fixed_rotation,
        pylinac_tol=pylinac_tol,
    )

    return field, field_centre, field_rotation


def find_field_and_bb(
    x,
    y,
    img,
    edge_lengths,
    bb_diameter,
    penumbra=2,
    fixed_rotation=None,
    pylinac_tol=0.2,
):
    field, field_centre, field_rotation = find_field(
        x,
        y,
        img,
        edge_lengths,
        penumbra=penumbra,
        fixed_rotation=fixed_rotation,
        pylinac_tol=pylinac_tol,
    )

    bb_centre = findbb.optimise_bb_centre(
        field,
        bb_diameter,
        edge_lengths,
        penumbra,
        field_centre,
        field_rotation,
        pylinac_tol=pylinac_tol,
    )

    return bb_centre, field_centre, field_rotation
