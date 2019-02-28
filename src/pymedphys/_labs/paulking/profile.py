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


from typing import Callable
from scipy import interpolate

import copy
import numpy as np
import matplotlib.pyplot as plt

from ...libutils import get_imports

# from .._level1.coreobjects import _PyMedPhysBase
IMPORTS = get_imports(globals())

NumpyFunction = Callable[[np.ndarray], np.ndarray]


# pylint: disable = C0103, C0121

class Profile():
    def __init__(self, x=[], data=[], metadata={}):
        self.x = np.array(x)
        self.data = np.array(data)
        self.metadata = metadata
        if len(self.x) < 2:
            self.interp = None
        else:
            self.interp = interpolate.interp1d(self.x, self.data,
                                               bounds_error=False, fill_value=np.nan)

    def __len__(self):  # NUMBER OF DATA POINTS
        assert len(self.x) == len(self.data)
        return len(self.x)

    def __eq__(self, other):  # SAME DATA POINTS
        if np.array_equal(self.x, other.x) and \
           np.array_equal(self.data, other.data) and \
           self.metadata == other.metadata:
            return True
        else:
            return False

    def __copy__(self):
        return copy.deepcopy(self)

    def __str__(self):
        try:
            fmt_str = 'Profile object: '
            fmt_str += '{} pts | x ({} cm -> {} cm) | data ({} -> {})'
            return fmt_str.format(len(self),
                                  min(self.x), max(self.x),
                                  min(self.data), max(self.data))
        except:
            return ''

    def __mul__(self, other):  # SCALE PROFILE DOSE
        self.data *= other
        return(self)
    __rmul__ = __mul__
    __imul__ = __mul__

# CONSIDER DIVIDE AS RESAMPLE
# CHANGE X,DATA VARIABLE NAMES?
# CONSIDER +/- AS SHIFT RIGHT/LEFT
# CONSIDER DIVIDE AS RESAMPLE
# CONSIDER ASCII GRAPH AS PRINT
# CONSIDER LEN AS X EXTENT OF GRAPH

    def from_lists(self, x, data, metadata={}):
        self.x = np.array(x)
        self.data = np.array(data)
        self.__init__(x=x, data=data, metadata=metadata)
        return(Profile(x=x, data=data, metadata=metadata))

    def from_tuples(self, list_of_tuples, metadata={}):
        """ Load a list of (x,data) tuples.

        Overwrite any existing dose profile data and metadata.

        Arguments
        ---------
        list_of_tuples : list
            List of (float x, float data) tuples.

        Keyword Arguments
        -----------------
        metadata : dict, optional
            Dictionary of key-value pairs that describe the profile

        Returns
        -------
        array_like

        """
        x = list(list(zip(*list_of_tuples))[0])
        data = list(list(zip(*list_of_tuples))[1])
        self.__init__(x=x, data=data, metadata=metadata)
        return Profile(x=x, data=data, metadata=metadata)

    def from_pulse(self, centre, width, domain, increment, metadata={}):
        """ Create of unit height from pulse function parameters

        Overwrite any existing dose profile data and metadata.

        Arguments
        ---------
        centre : float
            Location of pulse mid-point
        width : float
            Width of pulse (cm)
        domain : tuple
            (leftmost distance, rightmost distance)
        increment : float
            Profile distance spacing

        Keyword Arguments
        -----------------
        metadata : dict, optional
            Dictionary of key-value pairs that describe the profile

        Returns
        -------
        array_like

        """
        x_vals = np.arange(domain[0], domain[1] + increment, increment)
        data = []
        for x in x_vals:
            if abs(x) > (centre + width/2.0):
                data.append(0.0)
            elif abs(x) < (centre + width/2.0):
                data.append(1.0)
            else:
                data.append(0.5)
        return Profile().from_lists(x_vals, data)

    def from_snc_profiler(self):
        """ """
        pass

    def get_dose(self, x) -> float:
        """ Profile dose value at distance.

        Return value based on interpolation of source data.

        Argument
        -----------------
        x : float
            End points for incluion, default to source profile end-points

        Returns
        -------
        float

         """
        try:
            return self.interp(x)
        except ValueError:
            return np.nan

    def _get_increment(self):
        steps = np.diff(self.x)
        if np.isclose(steps.min(), steps.mean()):
            return steps.mean()
        else:
            return steps.min()

    def plot(self):
        plt.plot(self.x, self.data, 'o-')
        plt.show()
        return  # plt.plot(self.x, self.data, 'o-')

    def segment(self, start=-np.inf, stop=np.inf):
        """ Part of dose profile between begin and end.

        Resulting profile is comprised of those points in the source
        profile whose distance values are not-less-than start and
        not-greater-than stop.

        Keyword Arguments
        -----------------
        start, stop : float, optional
            Result end points, default to source end-points

        Returns
        -------
        Profile

        """
        try:
            start = max(start, min(self.x))  # default & limit to curve ends
            stop = min(stop, max(self.x))
            new_x = self.x[np.logical_and(self.x >= start, self.x <= stop)]
            new_data = self.interp(new_x)
        except ValueError:
            new_x = []
            new_data = []

        self.__init__(new_x, new_data)
        return Profile(new_x, new_data)

    def resample(self, step):  # convert this to magic divide?
        """ Resample a dose profile at a specified increment.

        Resulting profile has stepsize of the indicated step based on
        linear interpolation over the points of the source profile.

        Arguments
        -----------------
        step : float
            Sampling increment

        Returns
        -------
        Profile

        """

        new_x = np.arange(self.x[0], self.x[-1], step)
        new_data = self.interp(new_x)
        # self.__init__(new_x, new_data, self.metadata)
        return Profile(new_x, new_data, self.metadata)

    def normalise_dose(self, x=0.0, data=1.0):
        """ Renormalise to specified dose at distance.

        Source profile values multiplied by scaling factor to yield the specified dose at
        the specified distance. If distance is not specified, the central axis value is
        used. If dose is not specified, then normalization is to unity. With neither
        specified, resulting curve is the conventional off-center-ratio.

        Keywork Arguments
        -----------------
        x : float
        data : float

        Returns
        -------
        Profile

        """
        norm_factor = data / self.get_dose(x)
        new_x = self.x
        new_data = norm_factor * self.data
        metadata = self.metadata
        return Profile(new_x, new_data)  # USE THE MAGIC METHOD!

    def normalize_dose(self, x=0.0, data=1.0):
        """ US Eng -> UK Eng """
        return self.normalise_dose(x=x, data=data)

    def edges(self):
        """ Edges of a profile, as a tuple.

        Return left and right edges of a profile, identified
        as the points of greatest positive and greatest negative
        gradient.

        Arguments
        -----------------
        step : float
            Precision of result

        Returns
        -------
        tuple

        """
        step = self._get_increment()
        unmod = copy.deepcopy(self)
        resampled = self.resample(step)
        dydx = list(np.gradient(self.data, self.x))
        lt_edge = self.x[dydx.index(max(dydx))]
        rt_edge = self.x[dydx.index(min(dydx))]

        # self.__init__(x=unmod.x, data=unmod.data, metadata=unmod.metadata)
        return (lt_edge, rt_edge)

    def normalise_distance(self):
        """ Renormalise distance to beam edges.

        Source profile distances multiplied by scaling factor to yield unit distance
        at beam edges.
            | (1) Milan & Bentley, BJR Feb-74, The Storage and manipulation
                of radiation dose data in a small digital computer
            | (2) Heintz, King, & Childs, May-95, User Manual,
                Prowess 3000 CT Treatment Planning

        Arguments
        -----------------
        step : float
            Precision of result

        Returns
        -------
        Profile

        """

        lt_edge, rt_edge = self.edges()
        cax = 0.5*(lt_edge + rt_edge)

        new_x = []
        for i, dist in enumerate(self.x):
            if dist < cax:
                new_x.append(-dist/lt_edge)
            elif dist > cax:
                new_x.append(dist/rt_edge)
            else:
                new_x.append(0.0)

        return Profile(new_x, self.data, metadata=self.metadata)

    def normalize_distance(self):
        return self.normalise_distance()

    def umbra(self):
        """ Central 80% of dose profile.

        Source dose profile sliced to include only the central region between beam edges.

        Arguments
        -----------------
        step : float
            Precision of result

        Returns
        -------
        Profile

        """
        lt, rt = self.edges()
        idx = [i for i, d in enumerate(
            self.x) if d >= 0.8 * lt and d <= 0.8 * rt]
        new_x = self.x[idx[0]:idx[-1]+1]
        new_data = self.data[idx[0]:idx[-1]+1]

        return Profile(x=new_x, data=new_data, metadata=self.metadata)

    def flatness(self):
        """ Flatness of dose profile.

        Calculated as the dose range normalized to mean dose.

        Arguments
        -----------------
        step : float
            Precision of result

        Returns
        -------
        float

        """
        step = self._get_increment()
        dose = self.umbra().data
        return (max(dose)-min(dose))/np.average(dose)

    def symmetry(self):
        """ Symmetry of dose profile.

        Calculated as the maximum difference between corresponding points
        on opposite sides of the profile center, relativ to mean dose.

        Arguments
        -----------------
        step : float
            Precision of result

        Returns
        -------
        float

        """
        step = self._get_increment()
        dose = self.umbra().data
        return max(np.abs(np.subtract(dose, dose[::-1])/np.average(dose)))

    def symmetrise(self):
        """ Symmetric copy of dose profile.

        Created by averaging over corresponding +/- distances,
        except at the endpoints.

        Returns
        -------
        Profile

        """

        reflected = Profile(x=-self.x[::-1], data=self.data[::-1])

        step = self._get_increment()
        new_x = np.arange(min(self.x), max(self.x), step)
        new_data = [self.data[0]]
        for n in new_x[1:-1]:  # TO AVOID EXTRAPOLATION
            new_data.append(0.5*self.interp(n) + 0.5*reflected.interp(n))
        new_data.append(reflected.data[0])

        return Profile(x=new_x, data=new_data, metadata=self.metadata)

    def symmetrize(self):
        """ US Eng -> UK Eng """
        return self.symmetrise()


#############

    # def centre(self):
    #     pass

    # def shift_to_centre(self):
    #     pass

class DoseDepth():
    pass


# def _find_dists(dose_prof, dose):
#     """
#     Return a list of distances where a dose-profile has value of dose.

#     """

#     x = _get_dist_vals(dose_prof)
#     y = _get_dose_vals(dose_prof)
#     dists = []
#     for i in range(1, len(x)):
#         val = None
#         if y[i] != y[i-1]:
#             if (y[i]-dose)*(y[i-1]-dose) < 0:
#                 val = (x[i]-((y[i]-dose)/(y[i]-y[i-1]))*(x[i]-x[i-1]))
#         elif y[i] == dose:
#             val = x[i]
#         if val and (val not in dists):
#             dists.append(val)
#     return dists

# def _shift_dose_prof(dose_prof, dist):
#     """
#     Return a dose-profile whose distances are shifted by a specified distance.
#     """
#     dist_vals = np.add(_get_dist_vals(dose_prof), dist)
#     dose_vals = list(list(zip(*dose_prof))[1])
#     dose_vals = _get_dose_vals(dose_prof)
#     return list(zip(dist_vals, dose_vals))

# def overlay(dose_prof_moves, dose_prof_fixed, dist_step=0.1):
#     """
#     Return as a float, the misalignment between two dose-profiles, i.e. the
#     distance by which one would need to move to align to the other.

#     """

#     dist_vals_moves = _get_dist_vals(dose_prof_moves)

#     dist_vals_fixed = _get_dist_vals(dose_prof_fixed)
#     dose_vals_fixed = _get_dose_vals(dose_prof_fixed)

#     # POSSIBLE OFFSETS --------------------------
#     step = 0.5 * min(min(np.diff(dist_vals_moves)),
#                      min(np.diff(dist_vals_fixed)))
#     strt = max(min(dist_vals_moves), min(dist_vals_fixed))
#     stop = min(max(dist_vals_moves), max(dist_vals_fixed)) + step
#     possible_offsets = np.arange(strt, stop, step)
#     # --------------------------------------------

#     dose_func_fixed = interpolate.interp1d(dist_vals_fixed, dose_vals_fixed)

#     # DISTANCE VALUES OF FIXED CURVE ------------------------
#     strt = 3 * min(min(dist_vals_moves), min(dist_vals_fixed))
#     stop = 3 * max(max(dist_vals_moves), max(dist_vals_fixed)) + dist_step
#     dist_vals_fixed = np.arange(strt, stop, dist_step)
#     # -------------------------------------------------------

#     dose_vals_fixed = _make_dose_vals(dist_vals_fixed, dose_func_fixed)

#     # EVALUATE FIT AT ALL CANDIDATE SHIFT POSITIONS -----------
#     best_fit_qual = 0
#     best_offset = -np.inf
#     for offset in possible_offsets:
#         moved_profile = _shift_dose_prof(dose_prof_moves, offset)
#         moved_dist_vals = _get_dist_vals(moved_profile)
#         moved_dose_vals = _get_dose_vals(moved_profile)
#         dose_func_moves = interpolate.interp1d(moved_dist_vals,
#                                                moved_dose_vals)
#         fit_qual = np.correlate(
#             dose_vals_fixed,
#             _make_dose_vals(dist_vals_fixed, dose_func_moves))
#         if max(fit_qual) > best_fit_qual:
#             best_fit_qual = max(fit_qual)
#             best_offset = offset
#     # ----------------------------------------------------------

#     return best_offset


# def recentre(dose_prof):
#     """
#     Return a translated dose-profile in which the central-axis,
#     midway between the edges, is defined as zero distance.
#     Also, recenter().

#     """

#     dist_vals = _get_dist_vals(dose_prof)
#     dose_vals = _get_dose_vals(dose_prof)
#     cax = np.mean(edges(dose_prof))

#     cent_prof = []
#     for i, dist in enumerate(dist_vals):
#         cent_prof.append((dist - cax, dose_vals[i]))
#     return cent_prof


# def recenter(dose_prof):
#     """ US Eng -> UK Eng """
#     return recentre(dose_prof)


# def is_wedged(dose_prof):
#     """ Return True iff dose-profile has significant gradient in the umbra. """
#     wedginess = np.average(np.diff(_get_dose_vals(_find_umbra(dose_prof))))
#     if wedginess > 0.05:  # 'magic number'
#         return True
#     else:
#         return False
