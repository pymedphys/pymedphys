# Copyright (C) 2018 Paul King

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
# Affrero General Public License. These aditional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


import numpy as np
import os

from pymedphys._labs.paulking.doseprofile import (
    pulse, resample, overlay, is_wedged, edges, normalise_distance,
    normalise_dose, recentre, flatness, symmetry, symmetrise)

DATA_DIRECTORY = os.path.abspath(
    os.path.join(os.path.dirname(__file__),
                 os.pardir, 'data', 'doseprofile'))

PROFILER = [(-16.4, 0.22), (-16, 0.3), (-15.6, 0.28),
            (-15.2, 0.3), (-14.8, 0.36), (-14.4, 0.38),
            (-14, 0.41), (-13.6, 0.45), (-13.2, 0.47),
            (-12.8, 0.51), (-12.4, 0.55), (-12, 0.62),
            (-11.6, 0.67), (-11.2, 0.74), (-10.8, 0.81),
            (-10.4, 0.91), (-10, 0.97), (-9.6, 1.12),
            (-9.2, 1.24),
            (-8.8, 1.4), (-8.4, 1.56), (-8, 1.75), (-7.6, 2.06),
            (-7.2, 2.31), (-6.8, 2.56), (-6.4, 3.14), (-6, 3.83),
            (-5.6, 4.98), (-5.2, 8.17), (-4.8, 40.6), (-4.4, 43.34),
            (-4, 44.17), (-3.6, 44.44), (-3.2, 44.96), (-2.8, 44.18),
            (-2.4, 45.16), (-2, 45.54), (-1.6, 45.07), (-1.2, 45.28),
            (-0.8, 45.27), (-0.4, 44.57), (0, 45.23), (0.4, 45.19),
            (0.8, 45.18), (1.2, 45.37), (1.6, 45.34), (2, 45.39),
            (2.4, 45.32), (2.8, 45.25), (3.2, 44.84), (3.6, 44.76),
            (4, 44.23), (4.4, 43.22), (4.8, 39.14), (5.2, 7.98),
            (5.6, 4.89), (6, 3.71), (6.4, 3.11), (6.8, 2.59),
            (7.2, 2.27), (7.6, 1.95), (8, 1.71), (8.4, 1.46),
            (8.8, 1.35), (9.2, 1.18), (9.6, 1.11), (10, 0.93),
            (10.4, 0.87), (10.8, 0.78), (11.2, 0.7),
            (11.6, 0.64), (12, 0.6), (12.4, 0.54),
            (12.8, 0.49), (13.2, 0.47), (13.6, 0.43),
            (14, 0.4), (14.4, 0.39), (14.8, 0.34),
            (15.2, 0.33), (15.6, 0.32), (16, 0.3), (16.4, 0.3)]

WEDGED = [(-16.4, 0.27), (-16, 0.31), (-15.6, 0.29), (-15.2, 0.29),
          (-14.8, 0.32), (-14.4, 0.33), (-14, 0.35), (-13.6, 0.38),
          (-13.2, 0.4), (-12.8, 0.44), (-12.4, 0.46), (-12, 0.51),
          (-11.6, 0.55), (-11.2, 0.6), (-10.8, 0.65), (-10.4, 0.7),
          (-10, 0.74), (-9.6, 0.84), (-9.2, 0.94), (-8.8, 1.04), (-8.4, 1.14),
          (-8, 1.25), (-7.6, 1.45), (-7.2, 1.6), (-6.8, 1.78), (-6.4, 2.14),
          (-6, 2.66), (-5.6, 3.62), (-5.2, 6.54), (-4.8, 17.55), (-4.4, 20.07),
          (-4, 21.37), (-3.6, 22.19), (-3.2, 23.1), (-2.8, 23.74), (-2.4, 24.56),
          (-2, 25.49), (-1.6, 26.35), (-1.2, 27), (-0.8, 28.06), (-0.4, 28.89),
          (0, 29.8), (0.4, 30.61), (0.8, 31.4), (1.2, 32.53), (1.6, 33.06),
          (2, 34.15), (2.4, 34.85), (2.8, 35.65), (3.2, 36.6), (3.6, 37.04),
          (4, 37.45), (4.4, 36.72), (4.8, 30.93), (5.2, 10.06), (5.6, 5.43),
          (6, 3.71), (6.4, 3.01), (6.8, 2.52), (7.2, 2.19), (7.6, 1.9), (8, 1.7),
          (8.4, 1.48), (8.8, 1.35), (9.2, 1.19), (9.6, 1.09), (10, 0.93),
          (10.4, 0.89), (10.8, 0.78), (11.2, 0.72), (11.6, 0.65), (12, 0.6),
          (12.4, 0.55), (12.8, 0.5), (13.2, 0.48), (13.6, 0.45), (14, 0.41),
          (14.4, 0.4), (14.8, 0.35), (15.2, 0.33), (15.6, 0.32),
          (16, 0.31), (16.4, 0.3)]


def test_pulse():
    assert pulse()[0] == (-20.0, 0.0)


def test_resample():
    resampled = resample(PROFILER)
    increments = np.diff([i[0] for i in resampled])
    assert np.allclose(increments, 0.1)
    assert np.allclose(resampled[0], PROFILER[0])


def test_overlay():
    assert np.allclose(overlay(PROFILER, WEDGED), 0.2)


def test_normalise_dose():
    assert normalise_dose(PROFILER, 0.0)[41][1] == 100.0


def test_normalise_distance():
    assert np.isclose(normalise_distance(PROFILER)[0][0], 3.215686274)


def test_edges():
    assert np.allclose(edges(PROFILER), (-5.1, 4.9))


def test_recentre():
    assert np.allclose(recentre(PROFILER)[0][0], -16.3)


def test_flatness():
    assert np.allclose(flatness(PROFILER), 0.03042720)


def test_symmetry():
    assert np.allclose(symmetry(PROFILER), 0.0253189859)


def test_symmetrise():
    symmetric = symmetrise(PROFILER)
    assert symmetric[0][1] == symmetric[-1][1]


def test_is_wedged():
    assert not is_wedged(PROFILER)
    assert is_wedged(WEDGED)


if __name__ == "__main__":
    test_pulse()
    test_resample()
    test_overlay()
    test_edges()
    test_normalise_dose()
    test_normalise_distance()
    test_recentre()
    test_flatness()
    test_symmetry()
    test_symmetrise()
    test_is_wedged()
