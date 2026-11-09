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
from pymedphys._imports import shapely

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


L_SHAPE_WIDTH = 8 - 4 * np.sqrt(2)


def _l_shape():
    # An L with arms 2 cm thick, the largest circle sits in the inner corner.
    polygon = shapely.geometry.Polygon(
        [(0, 0), (10, 0), (10, 2), (2, 2), (2, 10), (0, 10)]
    )
    x, y = polygon.exterior.xy
    return np.array(x), np.array(y)


def test_l_shape_matches_the_analytic_largest_circle():
    x, y = _l_shape()

    width, _, circle_centre = core.parameterise_insert(x, y)

    assert width == pytest.approx(L_SHAPE_WIDTH, abs=1e-4)
    np.testing.assert_allclose(circle_centre, [L_SHAPE_WIDTH / 2] * 2, atol=1e-3)


def test_l_shape_width_is_the_same_on_every_run():
    x, y = _l_shape()

    widths = [core.parameterise_insert(x, y)[0] for _ in range(10)]

    assert len(set(widths)) == 1


def test_callback_is_called_once_with_the_final_circle():
    x, y = _l_shape()
    calls = []

    def record(centre, objective, accepted):
        calls.append((np.array(centre), objective, accepted))

    width, _, circle_centre = core.parameterise_insert(x, y, callback=record)

    assert len(calls) == 1
    np.testing.assert_allclose(calls[0][0], circle_centre)
    assert calls[0][1] == pytest.approx(-width / 2)
    assert calls[0][2] is True
