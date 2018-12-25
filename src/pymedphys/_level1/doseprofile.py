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

# ADD SYMMETRISE TEST
# REMOVE _UNZIP

<<<<<<< HEAD

def is_even_spaced(dose_prof):
=======
def _zip(x, dose):
>>>>>>> b427c4f03750a682222e3abd8b1e5c455f04c409
    """
    Determine if dose profile are spaced evenly.

    Parameters
    ----------
<<<<<<< HEAD
    dose_prof : dose profile
=======
    x   : [ distance, distance, ...]
    dose: [ dose, dose, ...]
        | where distance, dose are floats
>>>>>>> b427c4f03750a682222e3abd8b1e5c455f04c409

    Returns
    -------
    is_even_spaced : boolean
    """

<<<<<<< HEAD
    diffs = np.diff(get_dist_vals(dose_prof))
    avg_diff = np.mean(diffs)
    if(np.allclose(diffs, avg_diff)):
        return True
    else:
        return False

=======
    result = [(x[i], dose[i]) for i, _ in enumerate(x)]
    return result
>>>>>>> b427c4f03750a682222e3abd8b1e5c455f04c409

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
    num_steps = int((dist_stop - dist_strt) / dist_step)
    result = dist_strt + dist_step * np.array(range(num_steps + 1))

    num_digits = len(str(dist_step).split('.')[-1])
    result = list(np.round(result, num_digits))
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

<<<<<<< HEAD
    try:
        dist_vals = [float(i[0]) for i in dose_prof]
    except:
        dist_vals = None

    return dist_vals


def get_dose_vals(dose_prof):
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
        dose_vals = [float(i[1]) for i in dose_prof]
    except:
        dose_vals = None

    return dose_vals


def find_strt_stop(dose_prof, dist_strt, dist_stop):
    """
    Find the (dist_strt, dist_stop) distances for dose_prof,
    as either the supplied values, if supplied, or the endpoints
    of dose_prof, if supplied.

    Parameters
    ----------
    dose_prof : dose profile
    dist_strt : float
        | start distance
    dist_stop : float
        | stop distance

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


# def dose_profile_format(
#         dose_prof=None,
#         dist_step=None, dose_step=None,
#         dist_vals=None, dose_vals=None,
#         dist_start=None, dist_end=None,
#         interpolator=None):
#     """
#     A dose_profile is a list of tuples, where each tuple is a dose point.
#         | [(distance, dose), (distance, dose), ...]

#     """
#     # DoseProfile = namedtuple('DoseProfile',
#     #                          ['dose_profile', 'dist_step', 'dose_step',
#     #                           'dist_vals', 'dose_vals', 'interpolator'])

#     # result = DoseProfile(dose_profile, dist_step, dose_step,
#     #                      dist_vals, dose_vals, interpolator)

#     # DOSE_PROF -> DIST_VALS & DOSE_VALS
#     if dose_prof:
#         if not dist_vals:
#             dist_vals = get_dist_vals(dose_prof)
#         if not dose_vals:
#             dose_vals = get_dose_vals(dose_prof)

#     # DIST_VALS & DOSE_VALS -> DOSE_PROF
#     elif not dose_prof:
#         if dist_vals and dose_vals:
#             dose_prof = zip(dist_vals, dose_vals)

#     # DIST_VALS -> DIST_INCR
#     diffs = np.diff(dist_vals)
#     avg_diff = np.mean(diffs)
#     if(np.allclose(diffs, avg_diff)):
#         if not dist_step:
#             dist_step = avg_diff

#     # DIST_VALS & DOSE_VALS -> INTERPOLATOR
#     if not interpolator:
#         interpolator = interpolate.interp1d(dist_vals,
#                                             dose_vals,
#                                             kind='linear')

#     start, stop = find_strt_stop(dose_prof, dist_start, dist_end)

#     # INTERPOLATOR & DIST_STEP -> DOSE_PROF
#     if interpolator:
#         if dist_step:
#             num_steps = int((stop-start) / dist_step)
#             x_interp = [start + i*dist_step for i in range(num_steps + 1)]
#             d_interp = [interpolator(x) for x in x_interp]
#             dose_prof = zip(x_interp, d_interp)

#     # INTERPOLATOR & DIST_VALS -> DOSE_PROF


def _zip(x, d):
    """
    Combine distance and dose axes into dose_profile.

    Parameters
    ----------
    x   : [ distance, distance, ...]
    d   : [ dose, dose, ...]
        | where distance, dose are floats

    Returns
    -------
    dose_profile : [(distance, dose), ...]
    """

    x = [float(i) for i in x]  # ENFORCE TYPE
    d = [float(i) for i in d]

    return list(zip(x, d))
=======
    x = [i[0] for i in dose_profile]  # DISTANCE
    d = [i[1] for i in dose_profile]  # DOSE
    return x, d
>>>>>>> b427c4f03750a682222e3abd8b1e5c455f04c409


def _lookup(dose_profile, distance):
    """
    Return value of dose_profile at distance.

    Parameters
    ----------
    dose_profile : [(distance, dose), ...]
        | where distance and dose are floats
    distance : float distance at which to get value

    Returns
    -------
    value : float profile value at distance
    """
    x = get_dist_vals(dose_profile)
    d = get_dose_vals(dose_profile)
    f = interpolate.interp1d(x, d, kind='linear')
    return(f(distance))


def _slice(dose_prof, begin=-np.inf, end=np.inf):
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


def resample(dose_profile, step_size=0.1, start=-np.inf, stop=np.inf):
    """
    Resample a dose_profile at a new, uniform step_size.

    Parameters
    ----------
    dose_profile : [(distance, dose), ...]
        | where distance and dose are floats

    Keyword Arguments
    -----------------
    step_size : float increment at which to sample
    start     : starting distance, or from input
    stop      : stopping distance, or from input

    Returns
    -------
    resamp_profile : [(distance, dose), ...]
        | where distance and dose are floats
    """

    x = get_dist_vals(dose_profile)
    d = get_dose_vals(dose_profile)

    f = interpolate.interp1d(x, d, kind='linear')

    start, stop = find_strt_stop(dose_profile, start, stop)

    num_steps = int((stop-start) / step_size)
    x_interp = [start + i*step_size for i in range(num_steps + 1)]
    d_interp = [float(f(x)) for x in x_interp]

    resamp_profile = _zip(x_interp, d_interp)
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
    x = get_dist_vals(dose_profile)
    d = get_dose_vals(dose_profile)
    result = []
    for i in range(1, len(x)):
        val = None
        if d[i] != d[i-1]:
            # bracket threshold
            if (d[i]-threshold)*(d[i-1]-threshold) < 0:
                # interpolate
                val = (x[i]-((d[i]-threshold)/(d[i]-d[i-1]))*(x[i]-x[i-1]))
        elif d[i] == threshold:
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

    x_interp = get_dist_vals(resampled)
    d_interp = get_dose_vals(resampled)

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


def normalise_dose(dose_profile, location=0.0, dose=100.0):
    """
    Rescale profile doses to set dose to location.
        | also, normalize_dose()

    Parameters
    ----------
    dose_profile : list of tuples [(distance, dose), ...]

    KeyWord Arguments
    -----------------
    location : float or string
        |  float distance set to dose
        |  string 'max' at max dose point

    Returns
    -------
    norm_profile : list of tuples [(distance, dose), ...]
    """

    x = get_dist_vals(dose_profile)
    d = get_dose_vals(dose_profile)

    try:
        norm_fact = dose / _lookup(dose_profile, location)
<<<<<<< HEAD
    except:
=======
        assert type(location) in (float, int)
    except AssertionError:
>>>>>>> b427c4f03750a682222e3abd8b1e5c455f04c409
        norm_fact = dose / max(d)
        assert type(d) == str

<<<<<<< HEAD
    d = [norm_fact * i for i in d]

    return _zip(x, d)
=======
    norm_dose = [norm_fact * i for i in d]
    return _zip(x, norm_dose)
>>>>>>> b427c4f03750a682222e3abd8b1e5c455f04c409


def normalize_dose(dose_profile, location=0.0, dose=100.0):
    """ US English -> UK English """
    return normalise_dose(dose_profile, location=0.0, dose=100.0)


def normalise_distance(dose_profile):
    """
    Normalize profile distances as relative to beam edge.
        | also, normalize_distance()

    Parameters
    ----------
    dose_profile : list of tuples [(distance, dose), ...]

    KeyWord Arguments
    -----------------
    location : float or string
        |  float distance set to dose
        |  string 'max' at max dose point

    Returns
    -------
    norm_profile : list of tuples [(distance, dose), ...]
        | (1) Milan & Bentley, BJR Feb-74, The Storage and manipulation
        | of radiation dose data in a small digital computer
        | (2) Heintz, King, & Childs, May-95, User Manual,
        | Prowess 3000 CT Treatment Planning

    """

    x = get_dist_vals(dose_profile)
    d = get_dose_vals(dose_profile)

    lt_edge, rt_edge = edges(dose_profile)
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


def normalize_distance(dose_profile):
    """ US English -> UK English """
    return normalise_distance(dose_profile)


def recentre(dose_profile):
    """
    Adjusts profile distances so that the point midway between the edges is zero.
        | also, recenter()

    Parameters
    ----------
    dose_profile : list of tuples [(distance, dose), ...]

    Returns
    -------
    cent_profile : list of tuples [(distance, dose), ...]

    """

    x = get_dist_vals(dose_profile)
    d = get_dose_vals(dose_profile)

    lt_edge, rt_edge = edges(dose_profile)
    cax = (lt_edge + rt_edge)/2.0
    result = []
    for i, dist in enumerate(x):
        result.append((dist - cax, d[i]))
    return result


def recenter(dose_profile):
    """ US English -> UK English """
    return normalise_distance(dose_profile)


def symmetrise(dose_profile, step_size=0.1):  # STUB  ######
    """
    Return a symmetric version of a profile, in which the values are averaged
    across the central axis.
        | also, symetrize()

    Parameters
    ----------
    dose_profile : list of tuples [(distance, dose), ...]

    Returns
    -------
    sym_profile : list of tuples [(distance, dose), ...]
        | The length of the result will extend will be the shorter of
        | +/- extents of the original profile and will be resampled
        | at with the kwarg step-size.
    """
    x = get_dist_vals(dose_profile)
    d = get_dose_vals(dose_profile)

    start = max(x[0], -x[-1])
    stop = min(-x[0], x[-1])
    dose_profile = resample(dose_profile, start=start, stop=stop)
    rev = dose_profile[::-1]
    result = [(dose_profile[i][0],  (dose_profile[i][0]+rev[i][0])/2.0)
              for i in range(len(x))]
<<<<<<< HEAD
    # print(result)
=======
>>>>>>> b427c4f03750a682222e3abd8b1e5c455f04c409
    return result
    # PRETTY SURE THESE ANSWERS ARE NOT VERY GOOD


def symmetrize(dose_profile):
    """ US English -> UK English """
    return symmetrise(dose_profile)


def get_umbra(dose_profile):  # STUB  ######
    """ """
    pass


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


def symmetry(dose_profile):  # STUB  ######
    """ """
    pass


def flatness(dose_profile):  # STUB  ######
    """ """
    pass


def is_wedged(dose_profile):  # STUB  ######
    """ """
    pass


def is_fff(dose_profile):  # STUB  ######
    """ """
    pass
