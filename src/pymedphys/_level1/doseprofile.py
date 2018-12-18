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


from collections import namedtuple
from scipy import interpolate

import csv
import numpy as np


from .._level0.libutils import get_imports
IMPORTS = get_imports(globals())


def crossings(dose_profile, threshold):
    """
    Read and return dose profiles and CAX dose from native Profiler data file.

    Arguments:
        dose_profile -- e.g. [(distance, dose), ...]
        threshold    -- float value being to be checked

    Returns:
        intersects   -- list of floats, interp distances ST dose == threshold
    """
    return
    # X, Y = scan.x, scan.y
    # t = float(threshold)
    # idx = range(len(X))
    # result = []
    # for i in idx[1:]:
    #     val = None
    #     if Y[i] != Y[i-1]:
    #         if (Y[i]-t)*(Y[i-1]-t) < 0:
    #             val = (X[i]-((Y[i]-t)/(Y[i]-Y[i-1]))*(X[i]-X[i-1]))
    #     elif Y[i] == t:
    #         val = X[i]
    #     if val and (val not in result):
    #         result.append(val)
    # return result

# def edges(scan):
#     """ input = read.Scan()
#         returns = 3 x-values, (left_edge, center, right_edge)"""
#     x,y = scan.x, scan.y
#     tol = max(np.diff(x))/1000

#     kinds = ['cubic', 'quadratic', 'slinear', 'linear', 'nearest', 'zero']
#     for k in kinds:
#         try:
#             f = interpolate.interp1d(x, y, kind = 'linear')
#             diff = np.inf
#             lt, rt, c = x[0], x[-1], np.average([x[0], x[-1]])
#             while diff > tol:
#                 last = [c, lt, rt]
#                 c = np.average([lt, rt])
#                 lt, rt  = tuple(crossings(scan, f(c)/2.0))
#                 diff = abs(max([c - last[0], lt - last[1], rt - last[2]]))
#             return lt, c, rt
#         except: pass

# def move_to_match(s1, s2, rez = 0.1):
#     """Calcs the offset and orientation between two scans
#        input:
#             s1  = read.Scan() # to move
#             s2  = read.Scan() # to match
#             rez = float  # precision in cm
#         returns:
#             r = {'flp':  # boolean, flipped or not
#                  'shft': # float , x-shift to agreement
#                  'x1':   # np.array([fitted-x for moved curve]),
#                  'x2':   # np.array([fitted-x for matched curve]),
#                  'y1':   # np.array([fitted-y for moved curve]),
#                  'y2':   # np.array([fitted-y for matched curve])}   """

#     r = {}

#     end_pt = int((1/rez)*np.round(max(abs(np.append(s1.x, s2.x))), 1))
#     x = np.array([rez*i for i in range(-end_pt, end_pt+1)])

#     y1, y2 = [], []
#     f1 = interpolate.interp1d(s1.x, s1.y)
#     f2 = interpolate.interp1d(s2.x, s2.y)
#     for i in x:
#         try: y1.append(f1(i))
#         except: y1.append(0)
#         try: y2.append(f2(i))
#         except: y2.append(0)
#     y1, r['y2'] = np.array(y1), np.array(y2)

#     # correlation
#     c1 = list(np.correlate(y2, y1, "same"))
#     c2 = list(np.correlate(y2, y1[::-1], "same"))
#     # best match
#     C1 = max(c1)
#     C2 = max(c2)
#     # shift
#     i1 = c1.index(C1)
#     i2 = c2.index(C2)

#     if C2 > C1:
#         r['flp'] = True
#         r['shft'] = x[0] + rez * i2
#         r['y1'] = y1[::-1]
#     else:
#         r['flp'] = False
#         r['shft'] = x[0] + rez * i1
#         r['y1'] = y1

#     r['x1'] = x + r['shft']
#     r['x2'] = x

#     return r
