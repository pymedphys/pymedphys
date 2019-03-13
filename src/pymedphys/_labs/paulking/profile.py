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

""" A dose profile tool box. """

import os
import copy

from typing import Callable
from scipy import interpolate

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

# from PIL import Image
import PIL

from ...libutils import get_imports

# from .._level1.coreobjects import _PyMedPhysBase
IMPORTS = get_imports(globals())

NumpyFunction = Callable[[np.ndarray], np.ndarray]


# pylint: disable = C0103, C0121, W0102

class Profile():
    """  One-dimensional distribution of dose or intensity information.

    Includes methods for import, analysis, and export.

    Attributes
    ----------
    x : np.array
        Displacement, +/- in cm
    data : np.array
        Intensity, units unspecified
    data : dict, optional
        Context-dependent, unspecified descriptors of the dataset.

    """

    def __init__(self, x=[], data=[], metadata={}):
        self.x = np.array(x)
        self.data = np.array(data)
        self.metadata = metadata
        if len(self.x) < 2:
            self.interp = None
        else:
            self.interp = interpolate.interp1d(self.x, self.data,
                                               bounds_error=False, fill_value=0.0)

    def __len__(self):  # NUMBER OF DATA POINTS
        return len(self.x)

    def __eq__(self, other):  # SAME DATA POINTS
        if np.array_equal(self.x, other.x) and \
           np.array_equal(self.data, other.data) and \
           self.metadata == other.metadata:
            return True
        else:
            return False

    # CONSIDER IMPLEMENTING > < AS "TO THE LEFT OF AND "TO THE RIGHT OF"

    def __copy__(self):
        return copy.deepcopy(self)

    def __str__(self):
        try:
            fmt_str = 'Profile object: '
            fmt_str += '{} pts | x ({} cm -> {} cm) | data ({} -> {})'
            return fmt_str.format(len(self.x),
                                  min(self.x), max(self.x),
                                  min(self.data), max(self.data))
        except ValueError:  # EMPTY PROFILE
            return ''

    def __add__(self, other):  # SHIFT RIGHT
        new_x = self.x + other
        # self.x += other
        return Profile(x=new_x, data=self.data, metadata=self.metadata)
    __radd__ = __add__
    __iadd__ = __add__

    def __sub__(self, other):  # SHIFT LEFT
        self.x -= other
        return Profile(x=self.x, data=self.data, metadata=self.metadata)
    __rsub__ = __sub__
    __isub__ = __sub__

    def __mul__(self, other):  # SCALE DOSE
        self.data *= other
        return self
    __rmul__ = __mul__
    __imul__ = __mul__

    def from_lists(self, x, data, metadata={}):
        """  Create profile from a x-list and y-list .

        Overwrite any existing dose profile data and metadata.

        Arguments
        ---------
        x : list
            List of float x values
        data : list
            List of float data values

        Keyword Arguments
        -----------------
        metadata : dict, optional
            Dictionary of key-value pairs that describe the profile

        Returns
        -------
        Profile

        """

        self.x = np.array(x)
        self.data = np.array(data)
        self.__init__(x=x, data=data, metadata=metadata)
        return Profile(x=x, data=data, metadata=metadata)

    def from_tuples(self, list_of_tuples, metadata={}):
        """  Create profile from a list of (x,data) tuples.

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
        Profile

        """
        x = list(list(zip(*list_of_tuples))[0])
        data = list(list(zip(*list_of_tuples))[1])
        self.__init__(x=x, data=data, metadata=metadata)
        return Profile(x=x, data=data, metadata=metadata)

    def from_pulse(self, centre, width, domain, increment, metadata={}):
        """ Create profile of unit height from pulse function parameters

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
        Profile

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
        return Profile().from_lists(x_vals, data, metadata=metadata)

    def from_snc_profiler(self, file_name, axis):
        """
        Return dose profiles from native profiler data file.

        Arguments
        ----------
        file_name : string
            long file name of Profiler file
        axis : string
            'x' or 'y'

        Returns
        -------
        Profile


        """

        with open(file_name) as profiler_file:
            munge = '\n'.join(profiler_file.readlines())
            munge = munge.replace('\t', '').replace(': ', ':')
            munge = munge.replace(' Time:', '\nTime:')  # BREAK 2-ITEM ROWS
            munge = munge.replace(' Revision:', '\nRevision:')
            munge = munge.replace('Energy:', '\nEnergy:')
            munge = munge.replace('Dose:', '\nDose:')
            munge = munge.replace('Collimator Angle:', '\nCollimator Angle:')
            munge = munge.split('TYPE')[0].split('\n')  # DISCARD NON-METADATA
            munge = [i.split(':', 1) for i in munge if i and ':' in i]
            munge = [i for i in munge if i[1]]  # DISCARD EMPTY ITEMS
            metadata = dict(munge)

        with open(file_name) as profiler_file:
            for row in profiler_file.readlines():
                if row[:11] == "Calibration" and "File" not in row:
                    calibs = np.array(row.split())[1:].astype(float)
                elif row[:5] == "Data:":
                    counts = np.array(row.split()[5:145]).astype(float)
                elif row[:15] == "Dose Per Count:":
                    dose_per_count = (float(row.split()[-1]))
        dose = counts * dose_per_count * calibs

        x_vals = [-11.2 + 0.4*i for i in range(57)]
        x_prof = list(zip(x_vals, dose[:57]))
        y_vals = [-16.4 + 0.4*i for i in range(83)]
        y_prof = list(zip(y_vals, dose[57:]))

        # return (Profile().from_tuples(x_prof, metadata=metadata),
        #         Profile().from_tuples(y_prof, metadata=metadata))

        if axis == 'x':
            return Profile().from_tuples(x_prof, metadata=metadata)
        elif axis == 'y':
            return Profile().from_tuples(y_prof, metadata=metadata)
        else:
            raise TypeError("axis must be 'x' or 'y'")

    def from_narrow_png(self, file_name, step_size=0.1):
        """  Extract a an relative-density profilee from a narrow png file.

        Source file is a full color PNG that is sufficiently narrow that
        density is uniform along its short dimension. The image density along
        its long dimension is reflective of a dose distribution. Requires
        Python PIL.

        Arguments
        ---------
        file_name : str

        Keyword Arguments
        -----------------
        step-size : float, optional
            Distance output increment in cm, defaults to 1 mm

        Returns
        -------
        Profile

        Raises
        ------
        ValueError
            Image is not narrow, i.e. aspect ratio <= 5
        AssertionError
            step_size is too small, i.e. step_size <= 12.7 / dpi

        """
        image_file = PIL.Image.open(file_name)
        assert image_file.mode == 'RGB'
        dpi_horiz, dpi_vert = image_file.info['dpi']

        image_array = mpimg.imread(file_name)

        # DIMENSIONS TO AVG ACROSS DIFFERENT FOR HORIZ VS VERT IMG
        if image_array.shape[0] > 5*image_array.shape[1]:    # VERT
            image_vector = np.average(image_array, axis=(1, 2))
            pixel_size_in_cm = (2.54 / dpi_vert)
        elif image_array.shape[1] > 5*image_array.shape[0]:  # HORIZ
            image_vector = np.average(image_array, axis=(0, 2))
            pixel_size_in_cm = (2.54 / dpi_horiz)
        else:
            raise ValueError('The PNG file is not a narrow strip.')
        assert step_size > 5 * pixel_size_in_cm, "step size too small"

        if image_vector.shape[0] % 2 == 0:
            image_vector = image_vector[:-1]  # SO ZERO DISTANCE IS MID-PIXEL

        length_in_cm = image_vector.shape[0] * pixel_size_in_cm
        full_resolution_distances = np.arange(-length_in_cm/2,
                                              length_in_cm/2,
                                              pixel_size_in_cm)

        # TO MOVE FROM FILM RESOLUTION TO DESIRED PROFILE RESOLUTION
        num_pixels_to_avg_over = int(step_size/pixel_size_in_cm)
        sample_indices = np.arange(num_pixels_to_avg_over/2,
                                   len(full_resolution_distances),
                                   num_pixels_to_avg_over).astype(int)
        downsampled_distances = list(full_resolution_distances[sample_indices])

        downsampled_density = []
        for idx in sample_indices:  # AVERAGE OVER THE SAMPLING WINDOW
            avg_density = np.average(
                image_vector[int(idx - num_pixels_to_avg_over / 2):
                             int(idx + num_pixels_to_avg_over / 2)])
            downsampled_density.append(avg_density)

        zipped_profile = list(zip(downsampled_distances, downsampled_density))
        return Profile().from_tuples(zipped_profile)

    def get_data(self, x):
        """ Profile dose value at distance.

        Return a data value based on interpolation of source data for a
        supplied distance.

        Argument
        -----------------
        x : float

        Returns
        -------
        float

         """
        try:
            return self.interp(x)
        except ValueError:
            return np.nan

    def get_x(self, data):
        """ Distance at which profile takes on data value.

        Return a distance value based on interpolation of source data for a
        supplied data value.

        Argument
        -----------------
        data : float

        Returns
        -------
        tuple

         """

        dose_step = (max(self.data)-min(self.data)) / 100
        x = self.resample_data(dose_step).x
        y = self.resample_data(dose_step).data
        dists = []
        for i in range(1, len(x)):
            val = None
            if (y[i]-data)*(y[i-1]-data) < 0:
                val = (x[i]-((y[i]-data)/(y[i]-y[i-1]))*(x[i]-x[i-1]))
            elif np.isclose(y[i], data):
                val = x[i]
            if val and (val not in dists):
                dists.append(val)
        return tuple(dists)

    def get_increment(self):
        """ The profile's step-size increment .

        Calculated at the minimum value, if variable, or as the mean value if
        all increments are close.

        Returns
        -------
        increment : float

        """
        steps = np.diff(self.x)
        if np.isclose(steps.min(), steps.mean()):
            return steps.mean()
        else:
            return steps.min()

    def plot(self, marker='o-'):
        """ Present a plot of the profile. """
        plt.plot(self.x, self.data, marker)
        plt.show()
        return

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

        return Profile(new_x, new_data)

    def resample_x(self, step):
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
        return Profile(new_x, new_data, self.metadata)

    def resample_data(self, step):
        """ Resample a dose profile at specified dose increment.

        Resulting profile has nonuniform step-size, but each step
        represents and approximately equal step in dose.

        Arguments
        -----------------
        step : float
            Sampling increment

        Returns
        -------
        Profile

        """

        temp_x = np.arange(min(self.x), max(self.x), 0.01*self.get_increment())
        temp_y = self.interp(temp_x)

        resamp_x = [temp_x[0]]
        resamp_y = [temp_y[0]]

        last_y = temp_y[0]

        for i, _ in enumerate(temp_x):
            if np.abs(temp_y[i] - last_y) >= step:
                resamp_x.append(temp_x[i])
                resamp_y.append(temp_y[i])
                last_y = temp_y[i]

        if temp_x[-1] not in resamp_x:
            resamp_x.append(temp_x[-1])
            resamp_y.append(temp_y[-1])

        return Profile().from_lists(resamp_x, resamp_y, metadata=self.metadata)

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
        norm_factor = data / self.get_data(x)
        new_x = self.x
        new_data = norm_factor * self.data
        return Profile(new_x, new_data, metadata=self.metadata)

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
        dydx = list(np.gradient(self.data, self.x))
        lt_edge = self.x[dydx.index(max(dydx))]
        rt_edge = self.x[dydx.index(min(dydx))]
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
        for _, dist in enumerate(self.x):
            if dist < cax:
                new_x.append(-dist/lt_edge)
            elif dist > cax:
                new_x.append(dist/rt_edge)
            else:
                new_x.append(0.0)

        return Profile(new_x, self.data, metadata=self.metadata)

    def normalize_distance(self):
        """ US Eng -> UK Eng """
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

    def penumbra(self):
        """ Penumbra of dose profile, 20-80%

        Source dose profile sliced to include only the penumbral edges, where the dose
        transitions from 20% - 80% of the umbra dose, as precent at the umbra edge,
        to support wedged profiles.

        Returns
        -------
        tuple
            (left penumbra Profile, right penumbra Profile)

        """

        not_umbra = {'lt': self.segment(stop=self.umbra().x[0]),
                     'rt': self.segment(start=self.umbra().x[-1])}

        lt_80pct = not_umbra['lt'].get_x(0.8 * not_umbra['lt'].data[-1])[-1]
        lt_20pct = not_umbra['lt'].get_x(0.2 * not_umbra['lt'].data[-1])[-1]
        lt_penum = self.segment(start=lt_20pct, stop=lt_80pct)

        rt_80pct = not_umbra['rt'].get_x(0.8 * not_umbra['rt'].data[0])[-1]
        rt_20pct = not_umbra['rt'].get_x(0.2 * not_umbra['rt'].data[0])[-1]
        rt_penum = self.segment(start=rt_80pct, stop=rt_20pct)

        return (lt_penum, rt_penum)

    def shoulders(self):
        """ Shoulders of dose profile, between the umbra and the penumbra.

        Source dose profile sliced to include only the profile shoulders,
        outside the central 80% of of the profile but inside the region bounded
        by the 20-80% transition.

        Returns
        -------
        tuple
            (left shoulder Profile, right shoulder Profile)

        """

        lt_start = self.penumbra()[0].x[0]
        lt_stop = self.umbra().x[0]

        rt_start = self.umbra().x[-1]
        rt_stop = self.penumbra()[-1].x[-1]

        lt_should = self.segment(start=lt_start, stop=lt_stop)
        rt_should = self.segment(start=rt_start, stop=rt_stop)

        return (lt_should, rt_should)

    def tails(self):
        """ Tails of dose profile, beyond the penumbra.

        Source dose profile sliced to include only the profile tail,
        outside the beam penumbra.

        Returns
        -------
        tuple
            (left tail Profile, right tail Profile)

        """
        lt_start = self.x[0]
        lt_stop = self.penumbra()[0].x[0]

        rt_start = self.penumbra()[-1].x[-1]
        rt_stop = self.x[-1]

        lt_tail = self.segment(start=lt_start, stop=lt_stop)
        rt_tail = self.segment(start=rt_start, stop=rt_stop)

        return (lt_tail, rt_tail)

    def flatness(self):
        """ Flatness of dose profile.

        Calculated as the dose range normalized to mean dose.

        Returns
        -------
        float

        """
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

        step = self.get_increment()
        new_x = np.arange(min(self.x), max(self.x), step)
        new_data = [self.data[0]]
        for n in new_x[1:-1]:  # TO AVOID EXTRAPOLATION
            new_data.append(0.5*self.interp(n) + 0.5*reflected.interp(n))
        new_data.append(reflected.data[0])

        return Profile(x=new_x, data=new_data, metadata=self.metadata)

    def symmetrize(self):
        """ US Eng -> UK Eng """
        return self.symmetrise()

    def recentre(self):
        """ Centered copy of dose profile.

        Created by shifting the profile based on edge locations.

        Returns
        -------
        Profile

        """

        return self - np.average(self.edges())

    def recenter(self):
        """ US Eng -> UK Eng """
        return self.recentre()

    def reversed(self):
        """ Flipped copy of dose profile.

        Created by reversing the sequence of data values.

        Returns
        -------
        Profile

        """

        return Profile(x=self.x, data=self.data[::-1], metadata=self.metadata)

    def overlay(self, other):
        """ Copy of dose profile, shifted to align to target profile.

        Calculated using shift that produces greatest peak correlation between
        the curves. Flips the curve left-to-right, if this creates a better fit.

        Arguments
        -----------------
        other : Profile
            Target profile being shifted to

        Returns
        -------
        Profile

        """

        dist_step = min(self.get_increment(), other.get_increment())

        dist_vals_fixed = np.arange(
            -3*abs(min(list(self.x) + list(other.x))),
            3*abs(max(list(self.x) + list(other.x))),
            dist_step)
        dose_vals_fixed = other.interp(dist_vals_fixed)
        fixed = Profile(x=dist_vals_fixed, data=dose_vals_fixed)

        possible_offsets = np.arange(
            max(min(self.x), min(other.x)),
            min(max(other.x), max(self.x)) + dist_step,
            dist_step)

        best_fit_qual, best_offset, flipped = 0, -np.inf, False
        for offset in possible_offsets:
            fit_qual_norm = max(np.correlate(
                dose_vals_fixed,
                (self + offset).interp(fixed.x)))
            fit_qual_flip = max(np.correlate(
                dose_vals_fixed,
                (self.reversed() + offset).interp(fixed.x)))

            if fit_qual_norm > best_fit_qual:
                best_fit_qual = fit_qual_norm
                best_offset = offset
                flipped = False
            if fit_qual_flip > best_fit_qual:
                best_fit_qual = fit_qual_flip
                best_offset = offset
                flipped = True

        if flipped:
            return self.reversed() + best_offset
        else:
            return self + best_offset

    def create_calibration(self, reference_file_name, measured_file_name):
        """ Calibration curve from profiler and film data.

        Calculated by overlaying intensity curves and observing values at
        corresponding points. Note that the result is an unsmoothed, collection
        of points.

        Arguments
        -----------------
        reference_file_name : string
            long file name of Profiler file, extension .prs
        measured_file_name : string
            long file name of png file, extension .png

        Returns
        -------
        Profile

        """

        _, ext = os.path.splitext(reference_file_name)
        assert ext == '.prs'
        reference = Profile().from_snc_profiler(reference_file_name, 'y')
        _, ext = os.path.splitext(measured_file_name)
        assert ext == '.png'
        measured = Profile().from_narrow_png(measured_file_name)
        measured = measured.overlay(reference)

        dist_vals = np.arange(
            max(min(measured.x), min(reference.x)),
            min(max(measured.x), max(reference.x)),
            max(reference.get_increment(), measured.get_increment()))

        calib_curve = [(measured.get_data(i), reference.get_data(i))
                       for i in dist_vals]

        return Profile().from_tuples(calib_curve)
