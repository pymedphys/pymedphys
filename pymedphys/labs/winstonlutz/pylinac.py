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

import pymedphys._vendor.pylinac.winstonlutz

from .utilities import create_centralised_field, transform_point


class PyLinacFieldBBCentres:
    def __init__(self, field, edge_lengths, penumbra, field_centre, field_rotation):
        centralised_straight_field = create_centralised_field(
            field, field_centre, field_rotation
        )

        self._pymedphys_field_centre = field_centre
        self._pymedphys_field_rotation = field_rotation

        self._half_x_range = edge_lengths[0] / 2 + penumbra * 3
        self._half_y_range = edge_lengths[1] / 2 + penumbra * 3

        self._pixel_size = 0.1

        x_range = np.arange(
            -self._half_x_range, self._half_x_range + self._pixel_size, self._pixel_size
        )
        y_range = np.arange(
            -self._half_y_range, self._half_y_range + self._pixel_size, self._pixel_size
        )

        xx_range, yy_range = np.meshgrid(x_range, y_range)
        centralised_image = centralised_straight_field(xx_range, yy_range)

        self.wl_image = pymedphys._vendor.pylinac.winstonlutz.WLImage(  # pylint: disable = protected-access
            centralised_image
        )
        centralised_pylinac_field_centre = [
            self.wl_image.field_cax.x * self._pixel_size - self._half_x_range,
            self.wl_image.field_cax.y * self._pixel_size - self._half_y_range,
        ]

        self.field_centre = transform_point(
            centralised_pylinac_field_centre, field_centre, field_rotation
        )

        self._bb_centre = None

    @property
    def bb_centre(self):
        if self._bb_centre is None:
            centralised_pylinac_bb_centre = [
                self.wl_image.bb.x * self._pixel_size - self._half_x_range,
                self.wl_image.bb.y * self._pixel_size - self._half_y_range,
            ]

            self._bb_centre = transform_point(
                centralised_pylinac_bb_centre,
                self._pymedphys_field_centre,
                self._pymedphys_field_rotation,
            )

        return self._bb_centre
