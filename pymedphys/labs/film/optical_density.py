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

import numpy as np

from .align import align_images, shift_and_rotate


def calc_net_od(prescan, postscan, dpcm=100, alignment=None):
    shifted_prescan, alignment = get_aligned_image(prescan, postscan, dpcm, alignment)
    net_od = np.log10(shifted_prescan[:, :, 0] / postscan[:, :, 0])

    return net_od, alignment


def get_aligned_image(prescan, postscan, dpcm=100, alignment=None):
    prescan_axes = create_axes(prescan, dpcm)
    postscan_axes = create_axes(postscan, dpcm)

    if alignment is None:
        alignment = align_images(
            postscan_axes, postscan, prescan_axes, prescan, max_shift=2, max_rotation=5
        )

    shifted_prescan = shift_and_rotate(prescan_axes, postscan_axes, prescan, *alignment)

    return shifted_prescan, alignment


def create_axes(image, dpcm=100):
    shape = np.shape(image)
    x_span = (np.arange(0, shape[0]) - shape[0] // 2) * 10 / dpcm
    y_span = (np.arange(0, shape[1]) - shape[1] // 2) * 10 / dpcm

    return x_span, y_span
