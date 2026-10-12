# Copyright (C) 2026 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Equivalent-ellipse parameterisation of an electron insert."""

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._electronfactors import core


def test_elliptical_insert_is_parameterised_by_its_axes():
    # An off-centre ellipse, 6 cm by 4 cm, is its own equivalent ellipse.
    theta = np.linspace(0, 2 * np.pi, 120, endpoint=False)
    x = 3 * np.cos(theta) + 0.5
    y = 2 * np.sin(theta) - 0.25

    width, length, circle_centre = core.parameterise_insert(x, y)

    assert width == pytest.approx(4, abs=0.05)
    assert length == pytest.approx(6, abs=0.05)
    np.testing.assert_allclose(circle_centre, [0.5, -0.25], atol=0.05)
