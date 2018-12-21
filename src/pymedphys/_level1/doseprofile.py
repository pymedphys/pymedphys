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


def resample(dose_profile, step_size=0.1):
    """
    Resample a dose_profile at a new, uniform step_size.

    Parameters
    ----------
    dose_profile : [(distance, dose), ...]
        | where distance and dose are floats
    step_size : float increment at which to sample

    Returns
    -------
    resamp_profile : [(distance, dose), ...]
        | where distance and dose are floats
    """

    x = [float(i[0]) for i in dose_profile]  # DISTANCE
    d = [float(i[1]) for i in dose_profile]  # DOSE
    num_steps = int((max(x)-min(x)) / step_size)
    x_interp = [min(x) + i*step_size for i in range(num_steps + 1)]
    f = interpolate.interp1d(x, d, kind='linear')
    d_interp = [float(f(x)) for x in x_interp]
    resamp_profile = list(zip(x_interp, d_interp))
    return resamp_profile


def crossings(dose_profile, threshold):
    """
    Return a list of distances where dose_profile crosses threshold.

    Parameters
    ----------
    dose_profile : [(distance, dose), ...]
    threshold : [(distance, dose), ...]

    Returns
    -------
    intersections : list of floats
        | interpolated distances such that dose == threshold
    """

    x = [float(i[0]) for i in dose_profile]  # distance
    d = [float(i[1]) for i in dose_profile]  # dose
    t = float(threshold)                     # threshold dose

    result = []
    for i in range(1, len(x)):
        val = None
        if d[i] != d[i-1]:
            # bracket threshold
            if (d[i]-t)*(d[i-1]-t) < 0:
                # interpolate
                val = (x[i]-((d[i]-t)/(d[i]-d[i-1]))*(x[i]-x[i-1]))
        elif d[i] == t:
            val = x[i]
        if val and (val not in result):
            result.append(val)
    return result


def edges(dose_profile):
    """
    Find the edges of a dose_profile.

    Parameters
    ----------
    dose_profile : list of tuples [(distance, dose), ...]

    Returns
    -------
    edges : 2-tuple of distance values
    """

    resampled = resample(dose_profile)

    x_interp = [float(i[0]) for i in resampled]  # DISTANCE
    d_interp = [float(i[1]) for i in resampled]  # DOSE

    max_dose = max(d_interp)
    min_dose = min(d_interp)
    inc_dose = (max_dose - min_dose)/100
    test_doses = [max_dose - i*inc_dose for i in range(101)]

    for t in test_doses:
        cr = crossings(dose_profile, t/2.0)

    dydx = list(np.gradient(d_interp, x_interp))
    lt_edge = x_interp[dydx.index(max(dydx))]
    rt_edge = x_interp[dydx.index(min(dydx))]
    return (lt_edge, rt_edge)

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
