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

from .interppoints import apply_transform, translate_and_rotate_transform


def transform_point(point, field_centre, field_rotation):
    transform = translate_and_rotate_transform(field_centre, field_rotation)
    bb_centre = apply_transform(*point, transform)
    bb_centre = np.array(bb_centre).tolist()

    return bb_centre


def create_centralised_field(field, centre, rotation):

    transform = translate_and_rotate_transform(centre, rotation)

    def new_field(x, y):
        x_prime, y_prime = apply_transform(x, y, transform)
        return field(x_prime, y_prime)

    return new_field
