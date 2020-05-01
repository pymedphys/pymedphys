# Copyright (C) 2019 Simon Biggs

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
