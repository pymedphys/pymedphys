# Copyright (C) 2020 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import os  # pylint: disable = unused-import
from typing import Any, Literal, Union, cast  # pylint: disable = unused-import

from pymedphys._imports import numpy as np

from pymedphys import _losslessjpeg as lljpeg

from . import findbb, findfield, imginterp, iview

path_or_numpy_array = Union["np.ndarray", "os.PathLike[Any]", str]
path_types = Union["os.PathLike[Any]", str]
Algorithms = Literal["pymedphys", "pylinac", "pylinac-v2.2.6", "pylinac-v2.2.7"]


class LosslessIViewWinstonLutz:
    def __init__(
        self,
        image: path_or_numpy_array,
        edge_lengths=None,
        penumbra=None,
        bb_diameter=None,
        algorithm="pymedphys",
    ):
        raw_image = _load_lossless_image(image)
        self._x, self._y, self._image = iview.iview_image_transform(raw_image)
        self.edge_lengths = edge_lengths
        self.penumbra = penumbra
        self.bb_diameter = bb_diameter
        self.algorithm = algorithm
        self._field = None
        self._field_centre = None
        self._field_rotation = None
        self._bb_centre = None

    def _reset(self):
        self._field_centre = None
        self._bb_centre = None

    @property
    def x(self):
        return self._x

    @property
    def y(self):
        return self._y

    @property
    def image(self):
        return self._image

    @property
    def field(self):
        if self._field is None:
            self._field = imginterp.create_interpolated_field(
                self.x, self.y, self.image
            )

        return self._field

    @property
    def field_centre(self):
        if self._field_centre is None:
            self._find_field()

        return self._field_centre

    @property
    def field_rotation(self):
        if self._field_rotation is None:
            if self.algorithm == "pymedphys":
                self._find_field()
            else:
                raise ValueError(
                    'Need to set `algorithm="pymedphys"` do be able to '
                    "determine `field_rotation`"
                )

        return self._field_rotation

    def _find_field_pymedphys(self):
        if self._field_centre is None:
            initial_centre = findfield.get_centre_of_mass(self.x, self.y, self.image)
        else:
            initial_centre = self._field_centre

        field_centre, field_rotation = findfield.field_centre_and_rotation_refining(
            self.field, self.edge_lengths, self.penumbra, initial_centre
        )

        self._field_centre = field_centre
        self._field_rotation = field_rotation

    def _find_field(self):
        algorithm_map = {"pymedphys": self._find_field_pymedphys}
        algorithm_map[self.algorithm]()

    @property
    def bb_centre(self):
        if self._bb_centre is None:
            self._bb_centre = findbb.optimise_bb_centre(
                self.field,
                self.bb_diameter,
                self.edge_lengths,
                self.penumbra,
                self.field_centre,
                self.field_rotation,
            )

        return self.bb_centre


def _load_lossless_image(image: path_or_numpy_array) -> "np.ndarray":
    if isinstance(path_or_numpy_array, np.ndarray):
        return image

    image_path = cast(path_types, image)

    return lljpeg.imread(image_path)
