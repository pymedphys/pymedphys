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


def make_dist_vals(dist_strt, dist_stop, dist_step):
    """
    Make the list of distance values from endpoints and increment.

    Parameters
    ----------
    dist_strt : float
        | starting distance
    dist_stop : float
        | ending distance
    dist_step : float
        | distance increment

    Returns
    -------
    dist_vals : distance values as list
    """

    start, stop = dist_strt, dist_stop
    num_steps = int(np.ceil((dist_stop - dist_strt) / dist_step))
    result = dist_strt + dist_step * np.array(range(num_steps + 1))

    num_digits = len(str(dist_step).split('.')[-1])
    result = list(np.round(result, num_digits))
    return result


def make_dose_vals(dist_vals, dose_func):
    """
    Create a list of dose values from a distance list and dose function.

    Parameters
    ----------
    dose_prof : dose profile

    Returns
    -------
    dose_vals : dose values as list
    """
    result = []
    for x in dist_vals:
        try:
            result.append(float(dose_func(x)))
        except ValueError:
            result.append(0.0)
    return result


def get_dist_vals(dose_prof):
    """
    Get the list of distance values from a dose profile.

    Parameters
    ----------
    dose_prof : dose profile

    Returns
    -------
    dist_vals : distance values as list
    """

    try:
        dist_vals = [float(i[0]) for i in dose_prof]
    except:
        dist_vals = None

    return dist_vals


def get_dose_vals(dose_prof):
    """
    Get the list of dose values from a dose profile.

    Parameters
    ----------
    dose_prof : dose profile

    Returns
    -------
    dose_vals : distance values as list
    """

    try:
        dose_vals = [float(i[1]) for i in dose_prof]
    except:
        dose_vals = None

    return dose_vals


def find_strt_stop(dose_prof, dist_strt, dist_stop):
    """
    Find the start and stop distances for a dose profile, as the supplied
    values (optional) or the end-points of the dose profile (optional).

    Parameters
    ----------
    dose_prof : dose profile
    dist_strt : float, start distance
    dist_stop : float, stop distance

    Returns
    -------
    (dist_strt, dist_stop) : tuple of floats
    """

    dist_vals = get_dist_vals(dose_prof)

    if not dist_strt:
        dist_strt = -np.inf
    dist_strt = max(dist_strt, min(dist_vals))

    if not dist_stop:
        dist_stop = np.inf
    dist_stop = min(dist_stop, max(dist_vals))

    assert dist_stop > dist_strt
    return (dist_strt, dist_stop)


def is_even_spaced(dose_prof):
    """
    Determine if dose profile are spaced evenly.

    Parameters
    ----------
    dose_prof : dose profile

    Returns
    -------
    is_even_spaced : boolean
    """

    diffs = np.diff(get_dist_vals(dose_prof))
    avg_diff = np.mean(diffs)
    if(np.allclose(diffs, avg_diff)):
        return True
    else:
        return False


def make_dose_prof(dist_vals, dose_vals):
    """
    Combine distance and dose axes into dose_profile.

    Parameters
    ----------
    dist_vals : distance values
    dose_vals : dose values

    Returns
    -------
    dose_prof : dose profile
    """

    result = list(
        zip([float(i) for i in dist_vals],
            [float(i) for i in dose_vals]))
    return result


def find_dose(dose_prof, dist):
    """
    Value of dose_profile at distance.

    Parameters
    ----------
    dose_prof : dose profile
    dist      : float distance

    Returns
    -------
    dose_val  : float profile value at distance
    """

    dose_func = interpolate.interp1d(
        get_dist_vals(dose_prof),
        get_dose_vals(dose_prof),
        kind='linear')
    dose_val = dose_func(dist)

    return(dose_val)


def find_dists(dose_prof, dose):
    """
    List of distances where dose profile intersects a threshold dose.

    Parameters
    ----------
    dose_prof : dose profile
    dose      : float threshold dose

    Returns
    -------
    dists : list of floats
    """

    x = get_dist_vals(dose_prof)
    d = get_dose_vals(dose_prof)
    dists = []
    for i in range(1, len(x)):
        val = None
        if d[i] != d[i-1]:
            # bracket threshold
            if (d[i]-dose)*(d[i-1]-dose) < 0:
                # interpolate
                val = (x[i]-((d[i]-dose)/(d[i]-d[i-1]))*(x[i]-x[i-1]))
        elif d[i] == dose:
            val = x[i]
        if val and (val not in dists):
            dists.append(val)
    return dists


def slice_dose_prof(dose_prof, begin=-np.inf, end=np.inf):
    """
    Extract slice from a dose profile, excluduing points
    before begin or after end.

    Parameters
    ----------
    dose_profile : dose profile
    begin : float start of profile
    end   : float end of profile

    Returns
    -------
    slice_profile : [(distance, dose), ...]
    """
    return [d for d in dose_prof if d[0] >= begin and d[0] <= end]


def find_umbra(dose_prof):
    """
    Extract the central 80% of the flattened part of dose profile.

    Parameters
    ----------
    dose_profile : dose profile

    Returns
    -------
    umbra        : dose profile
    """
    edges = find_edges(dose_prof)
    umbra = slice_dose_prof(dose_prof, begin=0.8*edges[0], end=0.8*edges[-1])
    return umbra


def resample(dose_prof, dist_strt=-np.inf, dist_stop=np.inf, dist_step=0.1):
    """
    Create a dose profile with specified end-points and distance increment,
    by resampling an existing dose profile.

    Parameters
    ----------
    dose_prof : dose profile

    Keyword Arguments
    -----------------
    dist_strt : float start
    dist_stop : float stop
    dist_step : float increment

    Returns
    -------
    resampled : dose profile

    """

    dose_func = interpolate.interp1d(
        get_dist_vals(dose_prof),
        get_dose_vals(dose_prof),
        kind='linear')
    dist_strt, dist_stop = find_strt_stop(dose_prof, dist_strt, dist_stop)

    dist_vals = make_dist_vals(dist_strt, dist_stop, dist_step)
    dose_vals = make_dose_vals(dist_vals, dose_func)

    resampled = make_dose_prof(dist_vals, dose_vals)

    return resampled


def find_edges(dose_prof):
    """
    Find edges of a dose profile as location of greatest gradient.

    Parameters
    ----------
    dose_prof           : dose profile

    Returns
    -------
     (lt_edge, rt_edge) : tuple of float dists
    """

    resampled = resample(dose_prof)

    dist_vals = get_dist_vals(resampled)
    dose_vals = get_dose_vals(resampled)

    max_dose = max(dose_vals)
    min_dose = min(dose_vals)
    inc_dose = (max_dose - min_dose)/100
    test_doses = [max_dose - i*inc_dose for i in range(101)]

    for t in test_doses:
        cr = find_dists(dose_prof, t/2.0)

    dydx = list(np.gradient(dose_vals, dist_vals))
    lt_edge = dist_vals[dydx.index(max(dydx))]
    rt_edge = dist_vals[dydx.index(min(dydx))]
    return (lt_edge, rt_edge)


def norm_dose_vals(dose_prof, dist=0.0, dose=100.0):
    """
    Ccale profile doses so as to achieve specified dose at dist.

    Parameters
    ----------
    dose_profile : dose profile

    KeyWord Arguments
    -----------------
    dist : float

    Returns
    -------
    norm_prof : dose profile
    """

    norm_fact = dose / find_dose(dose_prof, dist)
    d = [norm_fact * i for i in get_dose_vals(dose_prof)]

    return make_dose_prof(get_dist_vals(dose_prof), d)


def norm_dist_vals(dose_prof):
    """
    Scale profile distances so as to place beam edges at dist = +/- 1.

    Parameters
    ----------
    dose_prof : dose profile

    Returns
    -------
    norm_profile : dose profile
        | (1) Milan & Bentley, BJR Feb-74, The Storage and manipulation
              of radiation dose data in a small digital computer
        | (2) Heintz, King, & Childs, May-95, User Manual,
              Prowess 3000 CT Treatment Planning
    """

    x = get_dist_vals(dose_prof)
    d = get_dose_vals(dose_prof)

    lt_edge, rt_edge = find_edges(dose_prof)
    cax = (lt_edge + rt_edge)/2.0

    result = []
    for i, dist in enumerate(x):
        if dist < cax:
            result.append((dist/lt_edge, d[i]))
        elif dist == cax:
            result.append((0.0, d[i]))
        elif dist > cax:
            result.append((dist/rt_edge, d[i]))
    return result


def cent_dose_prof(dose_prof):
    """
    Translate profile so as to place the point, midway between the edges, at dist = 0.0.

    Parameters
    ----------
    dose_prof : dose profile

    Returns
    -------
    cent_prof : dose profile

    """

    dist_vals = get_dist_vals(dose_prof)
    dose_vals = get_dose_vals(dose_prof)
    cax = np.mean(find_edges(dose_prof))

    cent_prof = []
    for i, dist in enumerate(dist_vals):
        cent_prof.append((dist - cax, dose_vals[i]))
    return cent_prof


def make_dose_prof_sym(dose_prof, dist_step=0.1):  # STUB  ######
    """
    Create a symmetric dose profile by averaging the corresponding points on
    either side of the central axis of the resampled source profile.

    Parameters
    ----------
    dose_prof : dose profile

    Returns
    -------
    sym_profile : dose profile
    """
    dist_vals = get_dist_vals(dose_prof)

    start = -min(-dist_vals[0], dist_vals[-1])
    stop = min(-dist_vals[0], dist_vals[-1])

    dose_prof = resample(dose_prof, dist_strt=start, dist_stop=stop)

    rev = dose_prof[::-1]

    result = [(dose_prof[i][0], (dose_prof[i][1]+rev[i][1])/2.0)
              for i, _ in enumerate(dose_prof)]

    return result


def symmetry(dose_prof):  # STUB  ######
    """
    Find symmtry for a dose profile.

    Parameters
    ----------
    dose_prof : dose profile

    Returns
    -------
    sym       : float
    """
    umbra = find_umbra(dose_prof)
    dose = get_dose_vals(umbra)
    avg_dose = np.average(dose)
    dose_rev = dose[::-1]
    asym = max(np.abs(np.subtract(dose, dose_rev)/avg_dose))
    return asym


def align_to(s1, s2, rez=0.1):  # STUB  ######
    pass
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


def flatness(dose_profile):  # STUB  ######
    """ """
    pass


def is_wedged(dose_profile):  # STUB  ######
    """ """
    pass


def is_fff(dose_profile):  # STUB  ######
    """ """
    pass
