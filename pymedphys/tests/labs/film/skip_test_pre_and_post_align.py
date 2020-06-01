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


# The following needs to be removed before leaving labs
# pylint: skip-file

import json
import os

import pytest

import numpy as np

import matplotlib.pyplot as plt

from fixtures import BASELINES_DIR, postscans, prescans
from pymedphys.labs.film import get_aligned_image, shift_and_rotate
from pymedphys.labs.film.optical_density import create_axes

CREATE_BASELINE = False

ALIGNMENT_BASELINES_FILEPATH = os.path.join(BASELINES_DIR, "pre_post_alignment.json")


def test_multi_channel_shift_and_rotate(
    prescans
):  # pylint: disable=redefined-outer-name
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


def test_pre_and_post_align(
    prescans, postscans
):  # pylint: disable=redefined-outer-name
    keys = prescans.keys()
    assert keys == postscans.keys()

    if not CREATE_BASELINE:
        with open(ALIGNMENT_BASELINES_FILEPATH, "r") as a_file:
            baselines = json.load(a_file)
    else:
        baselines = {str(key): None for key in keys}

    results = {}

    # keys_to_use = keys
    keys_to_use = [0.0, 1000.0]

    for key in keys_to_use:
        results[key] = np.around(
            get_alignment(prescans[key], postscans[key], baseline=baselines[str(key)]),
            decimals=4,
        ).tolist()

    if CREATE_BASELINE:
        with open(ALIGNMENT_BASELINES_FILEPATH, "w") as a_file:
            json.dump(results, a_file)
