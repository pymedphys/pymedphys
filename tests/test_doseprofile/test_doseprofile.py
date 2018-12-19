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


import sys
import numpy as np
import os
# from pymedphys.doseprofile import *
from pymedphys.dose import crossings, edges
# print(pymedphys.doseprofile)


DATA_DIRECTORY = os.path.abspath(
    os.path.join(os.path.dirname(__file__),
                 os.pardir, 'data', 'doseprofile'))


def test_crossings():
    """ """

    # RISING EDGE
    dose_profile = [(0, 0), (1, 1)]
    assert crossings(dose_profile, 0.5) == [0.5]

    # FLAT TAIL
    dose_profile = [(0, 0), (1, 0), (2, 1)]
    assert crossings(dose_profile,  0.5) == [1.5]

    # IDEAL PULSE
    dose_profile = [(-10.1, 0), (-9.9, 1), (9.9, 1), (10.1, 0)]
    assert crossings(dose_profile, 0.5) == [-10.0, 10.0]


def test_edges():
    """ """
    # IDEAL PULSE
    dose_profile = [(-20, 0.0), (-10.1, 0.0), (-9.9, 1.0),
                    (9.9, 1.0), (10.1, 0.0), (20, 0.0)]
    assert np.allclose(edges(dose_profile), (-10.0, 10.0))


#     # profiler
#     a = read.profiler(TEST[0])
#     for k in a.keys():
#         assert abs(sum(edges(a[k]))) <= 0.3

# def test_move_to_match():
#     """ """
#     # DYNAMIC WEDGE, PROFILER -> TOMO_FILM PROFILE
#     p = read.profiler(TEST[1]);  to_move = p[p.keys()[0]]
#     f = read.tomo_film(TEST[2]); to_match= f[f.keys()[0]]
#     r = move_to_match(to_move, to_match, 0.1)
#     assert abs(r['shft'] - 9.3) < 0.1
#     assert np.allclose(r['flp'], True)
#     assert len(r['x1']) -len(r['y1']) + len(r['x2']) -len(r['y2']) == 0
#     if True: # POPUP PLOT
#         import pylab as plt
#         kwargs = {'markersize': 1,  'markeredgewidth': 0.2, 'marker': 'o',
#           'linestyle': '-', 'linewidth': .010, 'markeredgecolor': 'r',
#           'markerfacecolor': 'r'}
#         plt.plot(r['x1'],  r['y1'], **kwargs)
#         kwargs['markeredgecolor'] = 'b'; kwargs['markerfacecolor'] = 'b'
#         plt.plot(r['x2'],  r['y2'], **kwargs)
#         plt.show()
#     print 'move_to_match passed'


if __name__ == "__main__":
    test_crossings()
    test_edges()
    # test_move_to_match()
