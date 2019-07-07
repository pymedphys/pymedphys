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

import os
import json

import pytest

import numpy as np
import matplotlib.pyplot as plt

from pymedphys_analysis.film import shift_and_rotate, get_aligned_image
from pymedphys_analysis.film.optical_density import create_axes

from fixtures import BASELINES_DIR, prescans, postscans

CREATE_BASELINE = False

ALIGNMENT_BASELINES_FILEPATH = os.path.join(BASELINES_DIR,
                                            'pre_post_alignment.json')


def test_multi_channel_shift_and_rotate(prescans):  # pylint: disable=redefined-outer-name
    prescan = prescans[0]
    axes = create_axes(prescan)

    interpolated = shift_and_rotate(axes, axes, prescan, 0, 0, 0)

    assert np.allclose(interpolated, prescan)


def get_alignment(prescan, postscan, baseline=None):
    shifted_prescan, alignment = get_aligned_image(prescan, postscan)

    if baseline is None or not np.allclose(baseline, alignment, 0.01, 0.01):
        print(baseline)
        print(alignment)

        plt.figure()
        plt.imshow(postscan)

        plt.figure()
        plt.imshow(prescan)

        plt.figure()
        plt.imshow(shifted_prescan.astype(np.uint8))

        plt.show()

        if baseline is not None:
            raise AssertionError

    return alignment


def test_pre_and_post_align(prescans, postscans):  # pylint: disable=redefined-outer-name
    keys = prescans.keys()
    assert keys == postscans.keys()

    if not CREATE_BASELINE:
        with open(ALIGNMENT_BASELINES_FILEPATH, 'r') as a_file:
            baselines = json.load(a_file)
    else:
        baselines = {str(key): None for key in keys}

    results = {}

    # keys_to_use = keys
    keys_to_use = [0.0, 1000.0]

    for key in keys_to_use:
        results[key] = np.around(get_alignment(prescans[key],
                                               postscans[key],
                                               baseline=baselines[str(key)]),
                                 decimals=4).tolist()

    if CREATE_BASELINE:
        with open(ALIGNMENT_BASELINES_FILEPATH, 'w') as a_file:
            json.dump(results, a_file)
