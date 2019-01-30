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

"""
Tools to read, write, adjust, & evaluate dose profiles.
"""

from functools import partial
from scipy import interpolate

import numpy as np

from pymedphys.libutils import get_imports
IMPORTS = get_imports(globals())


# PRIVATE FUNCTIONS ======================================

def _get_dist_vals(dose_prof):
    """ Unzip distance-values from dose-profile. """
    return list(list(zip(*dose_prof))[0])


def _get_dose_vals(dose_prof):
    """ Unzip dose-values from dose-profile. """
    return list(list(zip(*dose_prof))[1])


def _make_dose_vals(dist_vals, dose_func):
    """ Return list of dose-vals at distance-vals with generating function. """
    dose_vals = []
    for dist in dist_vals:
        try:
            dose_vals.append(float(dose_func(dist)))
        except ValueError:   # ZERO OUTSIDE DOSE_FUNC'S DOMAIN
            dose_vals.append(0.0)
    return dose_vals


def _find_umbra(dose_prof):
    """ Return a list of distances over the central 80% a dose profile. """
    e = edges(dose_prof)
    dist_strt = 0.8 * e[0]
    dist_stop = 0.8 * e[-1]
    umbra = [d for d in dose_prof if d[0] >= dist_strt and d[0] <= dist_stop]
    return umbra


def _find_dose(dose_prof, dist):
    """ Return the dose at a distance from a dose-profile. """
    dose_func = interpolate.interp1d(
        _get_dist_vals(dose_prof),
        _get_dose_vals(dose_prof),
        kind='linear')
    dose = dose_func(dist)
    return(dose)


def _find_dists(dose_prof, dose):
    """
    Return a list of distances where a dose-profile has value of dose.

    """

    x = _get_dist_vals(dose_prof)
    y = _get_dose_vals(dose_prof)
    dists = []
    for i in range(1, len(x)):
        val = None
        if y[i] != y[i-1]:
            if (y[i]-dose)*(y[i-1]-dose) < 0:
                val = (x[i]-((y[i]-dose)/(y[i]-y[i-1]))*(x[i]-x[i-1]))
        elif y[i] == dose:
            val = x[i]
        if val and (val not in dists):
            dists.append(val)
    return dists


def _shift_dose_prof(dose_prof, dist):
    """
    Return a dose-profile whose distances are shifted by a specified distance.
    """
    dist_vals = np.add(_get_dist_vals(dose_prof), dist)
    dose_vals = list(list(zip(*dose_prof))[1])
    dose_vals = _get_dose_vals(dose_prof)
    return list(zip(dist_vals, dose_vals))


# PUBLIC FUNCTIONS ==========================================

def pulse(centre=0.0, center=None, width=10.0,
          dist_strt=-20.0, dist_stop=20.0, dist_step=0.1):
    """
    Return a pulse shaped dose-profile; specified centre, width, and domain.
    """
    if center:  # US Eng -> UK Eng
        centre = center

    def pulse(centre, width, dist):
        if abs(dist) > (centre + width/2.0):
            return 0.0
        if abs(dist) < (centre + width/2.0):
            return 1.0
        return 0.5

    dist_vals = np.arange(dist_strt, dist_stop + dist_step, dist_step)
    dose_vals = _make_dose_vals(dist_vals, partial(pulse, centre, width))
    dose_prof = list(zip(dist_vals, dose_vals))
    return dose_prof


def resample(dose_prof, dist_strt=-np.inf, dist_stop=np.inf, dist_step=0.1):
    """
    Return a dose-profile extending from distance-start to distance-stop,
    by resampling a profile at the indicated increment.

    """

    dose_func = interpolate.interp1d(
        _get_dist_vals(dose_prof),
        _get_dose_vals(dose_prof),
        kind='linear')

    # FIND START AND STOP -------------------
    dist_vals = _get_dist_vals(dose_prof)

    if not dist_strt:
        dist_strt = -np.inf
    dist_strt = max(dist_strt, min(dist_vals))

    if not dist_stop:
        dist_stop = np.inf
    dist_stop = min(dist_stop, max(dist_vals))

    assert dist_stop > dist_strt
    # -----------------------------------------

    dist_vals = np.arange(dist_strt, dist_stop + dist_step, dist_step)
    dose_vals = _make_dose_vals(dist_vals, dose_func)

    resampled = list(zip(dist_vals, dose_vals))

    return resampled


def overlay(dose_prof_moves, dose_prof_fixed, dist_step=0.1):
    """
    Return as a float, the misalignment between two dose-profiles, i.e. the
    distance by which one would need to move to align to the other.

    """

    dist_vals_moves = _get_dist_vals(dose_prof_moves)

    dist_vals_fixed = _get_dist_vals(dose_prof_fixed)
    dose_vals_fixed = _get_dose_vals(dose_prof_fixed)

    # POSSIBLE OFFSETS --------------------------
    step = 0.5 * min(min(np.diff(dist_vals_moves)),
                     min(np.diff(dist_vals_fixed)))
    strt = max(min(dist_vals_moves), min(dist_vals_fixed))
    stop = min(max(dist_vals_moves), max(dist_vals_fixed)) + step
    possible_offsets = np.arange(strt, stop, step)
    # --------------------------------------------

    dose_func_fixed = interpolate.interp1d(dist_vals_fixed, dose_vals_fixed)

    # DISTANCE VALUES OF FIXED CURVE ------------------------
    strt = 3 * min(min(dist_vals_moves), min(dist_vals_fixed))
    stop = 3 * max(max(dist_vals_moves), max(dist_vals_fixed)) + dist_step
    dist_vals_fixed = np.arange(strt, stop, dist_step)
    # -------------------------------------------------------

    dose_vals_fixed = _make_dose_vals(dist_vals_fixed, dose_func_fixed)

    # EVALUATE FIT AT ALL CANDIDATE SHIFT POSITIONS -----------
    best_fit_qual = 0
    best_offset = -np.inf
    for offset in possible_offsets:
        moved_profile = _shift_dose_prof(dose_prof_moves, offset)
        moved_dist_vals = _get_dist_vals(moved_profile)
        moved_dose_vals = _get_dose_vals(moved_profile)
        dose_func_moves = interpolate.interp1d(moved_dist_vals,
                                               moved_dose_vals)
        fit_qual = np.correlate(
            dose_vals_fixed,
            _make_dose_vals(dist_vals_fixed, dose_func_moves))
        if max(fit_qual) > best_fit_qual:
            best_fit_qual = max(fit_qual)
            best_offset = offset
    # ----------------------------------------------------------

    return best_offset


def normalise_dose(dose_prof, dist=0.0, dose=100.0):
    """
    Return a dose-profile, with dose rescaled to yield a dose at distance.

    """

    norm_fact = dose / _find_dose(dose_prof, dist)
    d = [norm_fact * i for i in _get_dose_vals(dose_prof)]

    return list(zip(_get_dist_vals(dose_prof), d))


def normalize_dose(dose_prof, dist=0.0, dose=100.0):
    """ US Eng -> UK Eng """
    return normalise_dose(dose_prof, dist, dose)


def normalise_distance(dose_prof):
    """
    Return a dose-profile which is  rescaled to 2X/W distance
    so as to force the beam edges to distances of +/-1.

        | (1) Milan & Bentley, BJR Feb-74, The Storage and manipulation
              of radiation dose data in a small digital computer
        | (2) Heintz, King, & Childs, May-95, User Manual,
              Prowess 3000 CT Treatment Planning
    """

    x = _get_dist_vals(dose_prof)
    d = _get_dose_vals(dose_prof)

    lt_edge, rt_edge = edges(dose_prof)
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


def normalize_distance(dose_prof):
    """ US Eng -> UK Eng """
    return normalise_distance(dose_prof)


def edges(dose_prof):
    """
    Return profile edges as a tuple, distances of greatest + / - gradient.
    """

    resampled = resample(dose_prof)

    dist_vals = _get_dist_vals(resampled)
    dose_vals = _get_dose_vals(resampled)

    dydx = list(np.gradient(dose_vals, dist_vals))
    lt_edge = dist_vals[dydx.index(max(dydx))]
    rt_edge = dist_vals[dydx.index(min(dydx))]

    return (lt_edge, rt_edge)


def recentre(dose_prof):
    """
    Return a translated dose-profile in which the central-axis,
    midway between the edges, is defined as zero distance.
    Also, recenter().

    """

    dist_vals = _get_dist_vals(dose_prof)
    dose_vals = _get_dose_vals(dose_prof)
    cax = np.mean(edges(dose_prof))

    cent_prof = []
    for i, dist in enumerate(dist_vals):
        cent_prof.append((dist - cax, dose_vals[i]))
    return cent_prof


def recenter(dose_prof):
    """ US Eng -> UK Eng """
    return recentre(dose_prof)


def flatness(dose_prof):
    """
    Return float flatness of a dose-profile.
    """
    dose = _get_dose_vals(_find_umbra(dose_prof))
    flat = (max(dose)-min(dose))/np.average(dose)
    return flat


def symmetry(dose_prof):
    """
    Return float symmetry of a dose-profile.
    """
    dose = _get_dose_vals(_find_umbra(dose_prof))
    avg_dose = np.average(dose)
    dose_rev = dose[::-1]
    asymmetry = max(np.abs(np.subtract(dose, dose_rev)/avg_dose))
    return asymmetry


def symmetrise(dose_prof, dist_step=0.1):
    """
    Return a symmetric dose-profile, averaging dose values over
    locations across the CAX, and resampled. Also, symmetrize()

    """
    dist_vals = _get_dist_vals(dose_prof)

    strt = -min(-dist_vals[0], dist_vals[-1])
    stop = min(-dist_vals[0], dist_vals[-1])

    dose_prof = resample(dose_prof, dist_strt=strt,
                         dist_stop=stop, dist_step=dist_step)

    rev = dose_prof[::-1]

    result = [(dose_prof[i][0], (dose_prof[i][1]+rev[i][1])/2.0)
              for i, _ in enumerate(dose_prof)]

    return result


def symmetrize(dose_prof, dist_step=0.1):
    """ US Eng -> UK Eng """
    return symmetrise(dose_prof, dist_step)


def is_wedged(dose_prof):
    """ Return True iff dose-profile has significant gradient in the umbra. """
    wedginess = np.average(np.diff(_get_dose_vals(_find_umbra(dose_prof))))
    if wedginess > 0.05:  # 'magic number'
        return True
    else:
        return False
