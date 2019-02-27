# Copyright (C) 2019 Paul King, Simon Biggs
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
# import pandas as pd
# import xarray as xr
# import copy

# from deepdiff import DeepDiff

from pymedphys._labs.paulking.profile import Profile

# pylint: disable = E1102


# def cubed(x):
#     return np.array(x) ** 3


# def test_conversion():
#     x = range(-3, 4)
#     profile = DoseProfile(x=x, data=cubed(x))

#     expected_x = [-3, -2, -1, 0, 1, 2, 3]
#     expected_data = [-27, -8, -1, 0, 1, 8, 27]

#     expected_pandas = pd.Series(
#         expected_data, pd.Index(expected_x, name='x'))
#     expected_xarray = xr.DataArray(
#         expected_data, coords=[('x', expected_x)], name='dose')

#     expected_dict = {
#         'coords': {'x': {'data': expected_x,
#                          'dims': ('x',),
#                          'attrs': {}}},
#         'attrs': {},
#         'dims': ('x',),
#         'data': expected_data,
#         'name': 'dose'}

#     assert np.array_equal(profile.x, np.array(expected_x))
#     assert np.array_equal(profile.data, np.array(expected_data))

#     # print(type(expected_pandas.astype(int)))
#     # print(profile.to_pandas().astype(int))
#     assert expected_pandas.astype(int).equals(profile.to_pandas())

#     assert expected_xarray.identical(profile.to_xarray())
#     assert DeepDiff(profile.to_dict(), expected_dict) == {}


# def test_function_updating_with_shift():
#     x = np.array([1, 2, 3])

#     profile = DoseProfile(x=x, data=x**2)
#     assert np.array_equal(profile.data, [1, 4, 9])

#     profile.shift(2, inplace=True)
#     assert np.array_equal(profile.data, [1, 4, 9])
#     assert np.array_equal(profile.x, [3, 4, 5])

#     # profile.x = [1, 2, 3]
#     # assert np.array_equal(profile.dose, [1, 0, 1])

#     profile.dist = [3, 4, 5]
#     assert np.array_equal(profile.data, [1, 4, 9])

#     # profile_copy = profile.shift(2)
#     # assert np.array_equal(profile.dist, [3, 4, 5])
#     # assert np.array_equal(profile_copy.dist, [5, 6, 7])


# def test_default_interp_function():
#     profile = DoseProfile(x=[-10, 0, 10], data=[3, 8, 2])

#     assert np.array_equal(profile.interp([1, 3, 4]), [7.4, 6.2, 5.6])


PROFILER = [(-16.4, 0.22), (-16, 0.3), (-15.6, 0.28), (-15.2, 0.3),
            (-14.8, 0.36), (-14.4, 0.38),  (-14, 0.41), (-13.6, 0.45),
            (-13.2, 0.47), (-12.8, 0.51), (-12.4, 0.55), (-12, 0.62),
            (-11.6, 0.67), (-11.2, 0.74), (-10.8, 0.81), (-10.4, 0.91),
            (-10, 0.97), (-9.6, 1.12), (-9.2, 1.24), (-8.8, 1.4),
            (-8.4, 1.56), (-8, 1.75), (-7.6, 2.06), (-7.2, 2.31),
            (-6.8, 2.56), (-6.4, 3.14), (-6, 3.83), (-5.6, 4.98),
            (-5.2, 8.17), (-4.8, 40.6), (-4.4, 43.34), (-4, 44.17),
            (-3.6, 44.44), (-3.2, 44.96), (-2.8, 44.18), (-2.4, 45.16),
            (-2, 45.54), (-1.6, 45.07), (-1.2, 45.28), (-0.8, 45.27),
            (-0.4, 44.57), (0, 45.23), (0.4, 45.19), (0.8, 45.18),
            (1.2, 45.37), (1.6, 45.34), (2, 45.39), (2.4, 45.32),
            (2.8, 45.25), (3.2, 44.84), (3.6, 44.76), (4, 44.23),
            (4.4, 43.22), (4.8, 39.14), (5.2, 7.98), (5.6, 4.89),
            (6, 3.71), (6.4, 3.11), (6.8, 2.59), (7.2, 2.27),
            (7.6, 1.95), (8, 1.71), (8.4, 1.46), (8.8, 1.35),
            (9.2, 1.18), (9.6, 1.11), (10, 0.93), (10.4, 0.87),
            (10.8, 0.78), (11.2, 0.7), (11.6, 0.64), (12, 0.6),
            (12.4, 0.54), (12.8, 0.49), (13.2, 0.47), (13.6, 0.43),
            (14, 0.4), (14.4, 0.39), (14.8, 0.34), (15.2, 0.33),
            (15.6, 0.32), (16, 0.3), (16.4, 0.3)]

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


def test_init():
    assert np.allclose(Profile(x=[0], data=[0]).x, [0])


def test_interp():
    assert Profile().interp == None
    assert np.isclose(Profile(x=[0, 1], data=[0, 1]).interp(0.5), 0.5)


def test_len():
    assert len(Profile()) == 0


def test_eq():
    assert Profile() == Profile()
    assert Profile(x=[], data=[]) == Profile()
    assert Profile(x=[0], data=[0]) != Profile()


def test_copy():
    original = Profile()
    a_copy = original
    assert a_copy == original


def test_str():
    profiler = Profile().from_tuples(PROFILER)
    assert profiler.__str__()
    # print(profiler.__str__())


def test_from_lists():
    empty = Profile()
    also_empty = empty
    also_empty.from_lists([], [])
    assert empty == also_empty


def test_from_tuples():
    empty = Profile()
    profiler = empty.from_tuples(PROFILER)
    assert len(profiler.x) == len(PROFILER)
    assert profiler.x[0] == PROFILER[0][0]


def test_from_snc_profiler():
    pass


def test_get_dose():
    empty = Profile()
    profiler = empty.from_tuples(PROFILER)
    assert np.isclose(profiler.get_dose(0), 45.23)
    assert np.isnan(profiler.get_dose(-100))


def test_DoseProfile_segment():
    profiler = Profile().from_tuples(PROFILER)
    # NO POINTS
    no_points = profiler.segment(start=1, stop=0)
    assert np.array_equal(no_points.x, [])
    assert np.array_equal(no_points.data, [])
    # ONE POINT
    profiler = Profile().from_tuples(PROFILER)
    one_point = profiler.segment(start=0, stop=0)
    assert np.array_equal(one_point.x, [0])
    assert np.array_equal(one_point.data, [45.23])
    # ALL POINTS
    profiler = Profile().from_tuples(PROFILER)
    all_points = profiler.segment()
    assert np.array_equal(all_points.x, profiler.x)
    assert np.array_equal(all_points.data, profiler.data)


def test_DoseProfile_resample():
    profiler = Profile()
    profiler.from_tuples(PROFILER, metadata={'depth': 10, 'medium': 'water'})
    # METADATA
    assert profiler.metadata['depth'] == 10
    assert profiler.metadata['medium'] == 'water'
    # CONSISTENT CONTENTS AFTER UPSAMPLING
    assert np.isclose(profiler.interp(0), profiler.resample(0.1).interp(0))
    assert np.isclose(profiler.interp(6.372),
                      profiler.resample(0.1).interp(6.372))
    # CORRECT RESAMPLE INCREMENTS
    resampled = profiler.resample(0.1)
    increments = np.diff([i for i in resampled.x])
    assert np.allclose(increments, 0.1)
    # START LOCATION UNCHANGED
    assert np.isclose(resampled.data[0], profiler.data[0])


def test_normalise_dose():  # also normalize
    profiler = Profile().from_tuples(PROFILER)
    assert np.isclose(profiler.normalise_dose(x=0).get_dose(0), 1.0)
    profiler = Profile().from_tuples(PROFILER)
    assert np.isclose(profiler.normalize_dose(x=0).get_dose(0), 1.0)


def test_edges():
    profiler = Profile().from_tuples(PROFILER)
    assert np.allclose(profiler.edges(0.1), (-5.2, 4.8))
    assert len(profiler) == len(PROFILER)


def test_normalise_distance():  # also normalize
    profiler = Profile().from_tuples(PROFILER)
    assert np.isclose(profiler.normalise_distance(
        0.1).x[0], -3.1538461538461533)
    profiler = Profile().from_tuples(PROFILER)
    assert np.isclose(profiler.normalize_distance(
        0.1).x[0], -3.1538461538461533)
    profiler = Profile().from_tuples(PROFILER)
    assert len(PROFILER) == len(profiler.normalize_distance(0.1).x)


def test_umbra():
    profiler = Profile().from_tuples(PROFILER).resample(0.1)
    profiler_length = len(profiler)
    umbra = profiler.umbra(0.1)
    assert len(umbra) < profiler_length


def test_flatness():
    profiler = Profile().from_tuples(PROFILER)
    profiler = profiler.resample(0.1)
    assert np.isclose(profiler.flatness(0.1), 0.03042644213284108)


def test_symmetry():
    profiler = Profile().from_tuples(PROFILER)
    profiler = profiler.resample(0.1)
    symmetry = profiler.symmetry(0.1)
    assert np.isclose(symmetry, 0.024152376510553037)


def test_as_pulse():
    pulse = 4 * Profile().as_pulse(0.0, 1, (-5, 5), 0.1)
    assert np.isclose(sum(pulse.data), 40)


# def test_overlay():
#     assert np.allclose(overlay(PROFILER, WEDGED), 0.2)

# def test_recentre():
#     assert np.allclose(recentre(PROFILER)[0][0], -16.3)

# def test_symmetrise():
#     symmetric = symmetrise(PROFILER)
#     assert symmetric[0][1] == symmetric[-1][1]
# def test_is_wedged():
#     assert not is_wedged(PROFILER)
#     assert is_wedged(WEDGED)


if __name__ == "__main__":
    # test_conversion()
    # test_function_updating_with_shift()
    # test_default_interp_function()
    test_init()
    test_interp()
    test_len()
    test_eq()
    test_copy()
    test_str()
    test_from_lists()
    test_from_tuples()
    test_from_snc_profiler()
    test_get_dose()
    test_DoseProfile_segment()
    test_DoseProfile_resample()
    test_normalise_dose()
    test_edges()
    test_normalise_distance()
    test_umbra()
    test_flatness()
    test_symmetry()
    test_as_pulse()
    #     test_overlay()
    #     test_recentre()
    #     test_symmetrise()
    #     test_is_wedged()
    pass
