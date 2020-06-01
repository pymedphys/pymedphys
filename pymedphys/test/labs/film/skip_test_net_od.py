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
"""Notes

Make the prescan be the moving image, that way the treatment field is
not interpolated during the netOD calc and is left in the same coords as
the laser marked image.

"""
# The following needs to be removed before leaving labs
# pylint: skip-file

import pytest

from fixtures import postscans, prescans
from pymedphys.labs.film import calc_net_od

# import numpy as np
# import matplotlib.pyplot as plt


def test_net_od(prescans, postscans):  # pylint: disable=redefined-outer-name
    keys = prescans.keys()
    assert keys == postscans.keys()

    results = {}

    keys_to_use = keys
    keys_to_use = [200, 600]

    for key in keys_to_use:
        results[key] = calc_net_od(prescans[key], postscans[key])
        # plt.pcolormesh(results[key])
        # plt.colorbar()
        # plt.axis('equal')

        # plt.show()
