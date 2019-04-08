# Copyright (C) 2019 Paul King

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

""" For importing, analyzing, and comparing dose or intensity profiles
    from different sources."""

import os
import copy

from typing import Callable
from scipy import interpolate
from functools import partial

import PIL

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

import tkinter as tk
from tkinter.filedialog import askopenfilename
from matplotlib.backends.backend_tkagg import (
    FigureCanvasTkAgg, NavigationToolbar2Tk)
from matplotlib.backend_bases import key_press_handler
from matplotlib.figure import Figure


if "pymedphys" in __file__:
    try:
        from ...libutils import get_imports
        IMPORTS = get_imports(globals())
    except (ImportError, AssertionError, ValueError):
        pass

# if r"dosepro\dosepro" in __file__:
#     add_path = os.path.abspath(os.path.join(__file__, '..','..','..','..'))
#     add_path = os.path.join(add_path, 'src', 'dosepro', '_labs', 'paulking')
#     sys.path.insert(0,add_path)
#     from profile import Profile
# else:
#     from pymedphys._labs.paulking.profile import Profile

NumpyFunction = Callable[[np.ndarray], np.ndarray]

# pylint: disable = C0103, C0121, W0102

class Profile():
    """  One-dimensional distribution of intensity vs position.

    Attributes
    ----------
    x : np.array
        position, +/- in cm
    y : np.array
        intensity in unspecified units
    meta : dict, optional
        metadata

    Examples
    --------
    ``profiler = Profile().from_profiler("C:\\profiler.prs")``

    ``film = Profile().from_narrow_png("C:\\image.png")``

    ``profiler.cross_calibrate(film).plot(marker='o')``

    .. image:: calib_curve.png

    Notes
    -----
    Requires Python PIL.

    """

    def __init__(self, x=np.array([]),
                 y=np.array([]), meta={}):
        """ create profile

        Parameters
        ----------
        x : np.array, optional
        y : np.array, optional
        meta : dict, optional

        Notes
        -----
        Normally created empty, then filled using a method, which returns
        a new Profile.

        """
        self.x = np.array(x)
        self.y = np.array(y)
        self.meta = meta
        if len(self.x) < 2:
            self.interp = None
        else:
            self.interp = interpolate.interp1d(self.x, self.y,
                                               bounds_error=False, fill_value=0.0)

    def __len__(self):
        """ # data points  """
        return len(self.x)

    def __eq__(self, other):  # SAME DATA POINTS
        """ same data points """
        if np.array_equal(self.x, other.x) and \
           np.array_equal(self.y, other.y) and \
           self.meta == other.meta:
            return True
        else:
            return False

    def __copy__(self):
        """ deep copy """
        return copy.deepcopy(self)

    def __str__(self):
        """
        Examples
        --------
        ``Profile object: 83 pts | x (-16.4 cm -> 16.4 cm) | y (0.22 -> 45.54)``

        """
        try:
            fmt_str = 'Profile object: '
            fmt_str += '{} pts | x ({} cm -> {} cm) | y ({} -> {})'
            return fmt_str.format(len(self.x),
                                  min(self.x), max(self.x),
                                  min(self.y), max(self.y))
        except ValueError:
            return ''  # EMPTY PROFILE

    def __add__(self, other):
        """ shift right """
        new_x = self.x + other
        return Profile(x=new_x, y=self.y, meta=self.meta)
    __radd__ = __add__
    __iadd__ = __add__

    def __sub__(self, other):
        """ shift left """
        self.x -= other
        return Profile(x=self.x, y=self.y, meta=self.meta)
    __rsub__ = __sub__
    __isub__ = __sub__

    def __mul__(self, other):
        """ scale y """
        self.y *= other
        return self
    __rmul__ = __mul__
    __imul__ = __mul__

    def from_lists(self, x, y, meta={}):
        """  import x and y lists

        Parameters
        ----------
        x : list
            List of float x values
        y : list
            List of float y values
        meta : dict, optional

        Returns
        -------
        Profile

        Examples
        --------
        ``profile = Profile().fron_lists(x_list,data_list)``

        """

        self.x = np.array(x)
        self.y = np.array(y)
        self.__init__(x=x, y=y, meta=meta)
        return Profile(x=x, y=y, meta=meta)

    def from_tuples(self, list_of_tuples, meta={}):
        """  import list of (x,y) tuples

        Parameters
        ----------
        list_of_tuples : [(float x, float y), ...]
        meta : dict, optional

        Returns
        -------
        Profile

        Examples
        --------
        ``profile = Profile().fron_lists(list_of_tuples)``

        """
        x = list(list(zip(*list_of_tuples))[0])
        y = list(list(zip(*list_of_tuples))[1])
        self.__init__(x=x, y=y, meta=meta)
        return Profile(x=x, y=y, meta=meta)

    def from_pulse(self, centre, width, domain, increment, meta={}):
        """ create pulse of unit height

        Parameters
        ----------
        centre : float
        width : float
        domain : tuple
            (x_left, x_right)
        increment : float
        meta : dict, optional

        Returns
        -------
        Profile


        """
        x_vals = np.arange(domain[0], domain[1] + increment, increment)
        y = []
        for x in x_vals:
            if abs(x) > (centre + width/2.0):
                y.append(0.0)
            elif abs(x) < (centre + width/2.0):
                y.append(1.0)
            else:
                y.append(0.5)
        return Profile().from_lists(x_vals, y, meta=meta)

    def from_snc_profiler(self, file_name, axis):
        """ import profile form SNC Profiler file

        Parameters
        ----------
        file_name : string
            file name with path, .prs
        axis : string
            'tvs' or 'rad'

        Returns
        -------
        Profile

        Raises
        ------
        TypeError
            if axis invalid

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
            meta = dict(munge)

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

        if axis == 'tvs':
            return Profile().from_tuples(x_prof, meta=meta)
        elif axis == 'rad':
            return Profile().from_tuples(y_prof, meta=meta)
        else:
            raise TypeError("axis must be 'tvs' or 'rad'")

    def from_narrow_png(self, file_name, step_size=0.1):
        """ import from png file

        Source file is a full color PNG, sufficiently narrow that
        density is uniform along its short dimension. The image density along
        its long dimension is reflective of a dose distribution.

        Parameters
        ----------
        file_name : str
        step-size : float, optional

        Returns
        -------
        Profile

        Raises
        ------
        ValueError
            if aspect ratio <= 5, i.e. not narrow
        AssertionError
            if step_size <= 12.7 over dpi, i.e. small

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

    def get_y(self, x):
        """ y-value at distance x

        Return a y value based on interpolation of source data for a
        supplied distance.

        Parameters
        ----------
        x : float

        Returns
        -------
        float

        """
        try:
            return self.interp(x)
        except ValueError:
            return np.nan

    def get_x(self, y):
        """ tuple of x-values at intensity y

        Return distance values based on interpolation of source data for a
        supplied y value.

        Parameters
        ----------
        y : float

        Returns
        -------
        tuple : (x1, x2, ...)

         """

        dose_step = (max(self.y)-min(self.y)) / 100
        x_ = self.resample_y(dose_step).x
        y_ = self.resample_y(dose_step).y
        dists = []
        for i in range(1, len(x_)):
            val = None
            if (y_[i]-y)*(y_[i-1]-y) < 0:
                val = (x_[i]-((y_[i]-y)/(y_[i]-y_[i-1]))*(x_[i]-x_[i-1]))
            elif np.isclose(y_[i], y):
                val = x_[i]
            if val and (val not in dists):
                dists.append(val)
        return tuple(dists)

    def get_increment(self):
        """ minimum step-size increment

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
        """ profile plot

        Parameters
        ----------
        marker : string, optional

        Returns
        -------
        None

        """
        plt.plot(self.x, self.y, marker)
        plt.show()
        return

    def slice_segment(self, start=-np.inf, stop=np.inf):
        """ slice between given end-points

        Resulting profile is comprised of those points in the source
        profile whose distance values are not-less-than start and
        not-greater-than stop.

        Parameters
        ----------
        start : float, optional
        stop : float, optional

        Returns
        -------
        Profile

        """
        try:
            start = max(start, min(self.x))  # default & limit to curve ends
            stop = min(stop, max(self.x))
            new_x = self.x[np.logical_and(self.x >= start, self.x <= stop)]
            new_y = self.interp(new_x)
        except ValueError:
            new_x = []
            new_y = []

        return Profile(new_x, new_y)

    def resample_x(self, step):
        """ resampled x-values at a given increment

        Resulting profile has stepsize of the indicated step based on
        linear interpolation over the points of the source profile.

        Parameters
        ----------
        step : float
            sampling increment

        Returns
        -------
        Profile

        """

        new_x = np.arange(self.x[0], self.x[-1], step)
        new_y = self.interp(new_x)
        return Profile(new_x, new_y, self.meta)

    def resample_y(self, step):
        """ resampled y-values at a given increment

        Resulting profile has nonuniform step-size, but each step
        represents and approximately equal step in dose.

        Parameters
        ----------
        step : float
            sampling increment

        Returns
        -------
        Profile

        """

        temp_x = np.arange(min(self.x), max(self.x),
                           0.01*self.get_increment())
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

        return Profile().from_lists(resamp_x, resamp_y, meta=self.meta)

    def make_normal_y(self, x=0.0, y=1.0):
        """ normalised to dose at distance

        Source profile values multiplied by scaling factor to yield the specified dose at
        the specified distance. If distance is not specified, the central axis value is
        used. If dose is not specified, then normalization is to unity. With neither
        specified, resulting curve is the conventional off-center-ratio.

        Parameters
        ----------
        x : float, optional
        y : float, optional

        Returns
        -------
        Profile

        """
        norm_factor = y / self.get_y(x)
        new_x = self.x
        new_y = norm_factor * self.y
        return Profile(new_x, new_y, meta=self.meta)

    def get_edges(self):
        """ x-values of profile edges (left, right)

        Notes
        -----
        Points of greatest positive and greatest negative gradient.

        Returns
        -------
        tuple

        """
        dydx = list(np.gradient(self.y, self.x))
        lt_edge = self.x[dydx.index(max(dydx))]
        rt_edge = self.x[dydx.index(min(dydx))]
        return (lt_edge, rt_edge)

    def make_normal_x(self):
        """ normalised to distance at edges

        Source profile distances multiplied by scaling factor to yield unit distance
        at beam edges. [1]_ [2]_

        Returns
        -------
        Profile


        References
        ----------
        .. [1] Milan & Bentley, BJR Feb-74, The Storage and manipulationof radiation dose data
           in a small digital computer
        .. [2] Heintz, King, & Childs, May-95, User Manual, Prowess 3000 CT Treatment Planning


        """

        lt_edge, rt_edge = self.get_edges()
        cax = 0.5*(lt_edge + rt_edge)

        new_x = []
        for _, dist in enumerate(self.x):
            if dist < cax:
                new_x.append(-dist/lt_edge)
            elif dist > cax:
                new_x.append(dist/rt_edge)
            else:
                new_x.append(0.0)

        return Profile(new_x, self.y, meta=self.meta)

    def slice_umbra(self):
        """ umbra central 80%

        Source dose profile sliced to include only the central region between beam edges.

        Returns
        -------
        Profile

        """
        lt, rt = self.get_edges()
        idx = [i for i, d in enumerate(
            self.x) if d >= 0.8 * lt and d <= 0.8 * rt]
        new_x = self.x[idx[0]:idx[-1]+1]
        new_y = self.y[idx[0]:idx[-1]+1]

        return Profile(x=new_x, y=new_y, meta=self.meta)

    def slice_penumbra(self):
        """ penumbra (20 -> 80%, 80 -> 20%)

        Source dose profile sliced to include only the penumbral edges, where the dose
        transitions from 20% - 80% of the umbra dose, as precent at the umbra edge,
        to support wedged profiles.

        Returns
        -------
        tuple
            (left penumbra Profile, right penumbra Profile)

        """

        not_umbra = {'lt': self.slice_segment(stop=self.slice_umbra().x[0]),
                     'rt': self.slice_segment(start=self.slice_umbra().x[-1])}
        result = []
        for side in not_umbra:
            min_val = min(not_umbra[side].y)
            max_val = max(not_umbra[side].y)
            incr_val = 0.2 * (max_val - min_val)
            lo_x = not_umbra[side].get_x(min_val + incr_val)
            hi_x = not_umbra[side].get_x(max_val - incr_val)
            coords = [lo_x, hi_x]
            coords.sort()
            penum = not_umbra[side].slice_segment(start=coords[0], stop=coords[1])
            result.append(penum)
        return tuple(result)

    def slice_shoulders(self):
        """ shoulders (penumbra -> umbra, umbra -> penumbra)

        Source dose profile sliced to include only the profile shoulders,
        outside the central 80% of of the profile but inside the region bounded
        by the 20-80% transition.

        Returns
        -------
        tuple
            (left shoulder Profile, right shoulder Profile)

        """
        try:
            lt_start = self.slice_penumbra()[0].x[-1]
        except IndexError:
            lt_start = self.slice_umbra().x[-1]
        lt_stop = self.slice_umbra().x[0]

        rt_start = self.slice_umbra().x[-1]
        try:
            rt_stop = self.slice_penumbra()[-1].x[0]
        except IndexError:
            rt_stop = self.slice_umbra().x[0]

        lt_should = self.slice_segment(start=lt_start, stop=lt_stop)
        rt_should = self.slice_segment(start=rt_start, stop=rt_stop)

        return (lt_should, rt_should)

    def slice_tails(self):
        """ tails (-> penumbra, penumbra ->)

        Source dose profile sliced to include only the profile tail,
        outside the beam penumbra.

        Returns
        -------
        tuple
            (left tail Profile, right tail Profile)

        """
        lt_start = self.x[0]
        try:
            lt_stop = self.slice_penumbra()[0].x[0]
        except IndexError:
            lt_stop = self.slice_shoulders()[0].x[0]

        try:
            rt_start = self.slice_penumbra()[-1].x[-1]
        except IndexError:
            rt_start = self.slice_shoulders()[-1].x[-1]
        rt_stop = self.x[-1]

        lt_tail = self.slice_segment(start=lt_start, stop=lt_stop)
        rt_tail = self.slice_segment(start=rt_start, stop=rt_stop)

        return (lt_tail, rt_tail)

    def get_flatness(self):
        """ dose range relative to mean

        Calculated as the dose range normalized to mean dose.

        Returns
        -------
        float

        """
        dose = self.slice_umbra().y
        return (max(dose)-min(dose))/np.average(dose)

    def get_symmetry(self):
        """ max point diff relative to mean

        Calculated as the maximum difference between corresponding points
        on opposite sides of the profile center, relative to mean dose.

        Returns
        -------
        float

        """
        dose = self.slice_umbra().y
        return max(np.abs(np.subtract(dose, dose[::-1])/np.average(dose)))

    def make_symmetric(self):
        """ avg of corresponding points

        Created by averaging over corresponding +/- distances,
        except at the endpoints.

        Returns
        -------
        Profile

        """

        reflected = Profile(x=-self.x[::-1], y=self.y[::-1])

        step = self.get_increment()
        new_x = np.arange(min(self.x), max(self.x), step)
        new_y = [self.y[0]]
        for n in new_x[1:-1]:  # AVOID EXTRAPOLATION
            new_y.append(0.5*self.interp(n) + 0.5*reflected.interp(n))
        new_y.append(reflected.y[0])

        return Profile(x=new_x, y=new_y, meta=self.meta)

    def make_centered(self):
        """ shift to align edges

        Created by shifting the profile based on edge locations.

        Returns
        -------
        Profile

        """

        return self - np.average(self.get_edges())

    def make_flipped(self):
        """ flip L -> R

        Created by reversing the sequence of y values.

        Returns
        -------
        Profile

        """

        return Profile(x=self.x, y=self.y[::-1], meta=self.meta)

    def align_to(self, other):
        """ shift self to align to other

        Calculated using shift that produces greatest peak correlation between
        the curves. Flips the curve left-to-right, if this creates a better fit.

        Parameters
        ----------
        other : Profile
            profile to be be shifted to

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
        fixed = Profile(x=dist_vals_fixed, y=dose_vals_fixed)

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
                (self.make_flipped() + offset).interp(fixed.x)))

            if fit_qual_norm > best_fit_qual:
                best_fit_qual = fit_qual_norm
                best_offset = offset
                flipped = False
            if fit_qual_flip > best_fit_qual:
                best_fit_qual = fit_qual_flip
                best_offset = offset
                flipped = True

        if flipped:
            return self.make_flipped() + best_offset
        else:
            return self + best_offset

    def cross_calibrate(self, reference, measured):
        """ density mapping, reference -> measured

        Calculated by overlaying intensity curves and observing values at
        corresponding points. Note that the result is an unsmoothed, collection
        of points.

        Parameters
        ----------
        reference : string
        measured : string
            file names with path

        Returns
        -------
        Profile

        """

        _, ext = os.path.splitext(reference)
        assert ext == '.prs'
        reference = Profile().from_snc_profiler(reference, 'rad')
        _, ext = os.path.splitext(measured)
        assert ext == '.png'
        measured = Profile().from_narrow_png(measured)
        measured = measured.align_to(reference)

        dist_vals = np.arange(
            max(min(measured.x), min(reference.x)),
            min(max(measured.x), max(reference.x)),
            max(reference.get_increment(), measured.get_increment()))

        calib_curve = [(measured.get_y(i), reference.get_y(i))
                       for i in dist_vals]

        return Profile().from_tuples(calib_curve)

class UserInterface(tk.Frame):
    """ Graphical User Interface for Profile Class

    """

    def __init__(self, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.parent = parent
        root.wm_title("Profile Tool")
        root.resizable(False, False)

        selector_frame = tk.Frame(self, width=5, height=100, background="bisque")
        graph_frame = tk.Frame(self, width=90, height=100, background="bisque")

        selector_frame.pack(side=tk.LEFT, fill=tk.BOTH)
        graph_frame.pack(side=tk.RIGHT, fill=tk.BOTH)

        fig = Figure(figsize=(6, 5), dpi=100)
        self.canvas = FigureCanvasTkAgg(fig, master=graph_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)
        self.subplot = fig.add_subplot(111)
        self.toolbar = NavigationToolbar2Tk(self.canvas, graph_frame)
        self.toolbar.update()
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)
        self.canvas.mpl_connect("key_press_event", self.on_key_press)

        self.status = tk.StringVar()
        self.status_bar = tk.Frame(master=graph_frame, relief=tk.RIDGE, background="bisque")
        self.status_label=tk.Label(self.status_bar, bd=1, relief=tk.FLAT, anchor=tk.W,
                                   textvariable=self.status, background="bisque",
                                   font=('arial',10,'normal'))
        self.status_label.pack(fill=tk.X, expand=True, side=tk.LEFT)
        self.status_bar.pack(fill=tk.X, expand=False, side=tk.LEFT)

        self._color_palette = {'idx': 0, 'val': dict(enumerate(
            ['red', 'green', 'orange', 'blue', 'yellow', 'purple1', 'grey']*5))}

        menu = tk.Menu(root)
        root.config(menu=menu)
        ## ----------
        _file = tk.Menu(menu)
        __from = tk.Menu(_file)
        _edit = tk.Menu(menu)
        __resample = tk.Menu(_edit)
        __normalise = tk.Menu(_edit)
        _get = tk.Menu(menu)
        __value = tk.Menu(_get)
        __segment = tk.Menu(_get)
        _help = tk.Menu(menu)
        ## ----------
        menu.add_cascade(label="File", menu=_file)
        _file.add_cascade(label='From ...', menu=__from)
        __from.add_command(label="Film", command=self.from_narrow_png)
        __from.add_command(label="Pulse", command=self.from_pulse)
        __from.add_command(label="Profiler", command=self.from_snc_profiler)
        _file.add_command(label="Clear Selected", command=self.file_clr)
        _file.add_command(label="Clear All", command=self.file_clr_all)
        _file.add_command(label="Exit", command=self._quit)
        menu.add_cascade(label="Edit", menu=_edit)
        _edit.add_cascade(label='Resample ...', menu=__resample)
        __resample.add_command(label="X", command=self.resample_x)
        __resample.add_command(label="Y", command=self.resample_y)
        _edit.add_cascade(label='Normalise ...', menu=__normalise)
        __normalise.add_command(label="X", command=self.make_normal_x)
        __normalise.add_command(label="Y", command=self.make_normal_y)
        _edit.add_command(label="Flip", command=self.make_flipped)
        _edit.add_command(label="Symmetrise", command=self.make_symmetric)
        _edit.add_command(label="Centre", command=self.make_centered)
        menu.add_cascade(label="Get", menu=_get)
        _get.add_cascade(label='Value ...', menu=__value)
        __value.add_command(label="X", command=self.get_x)
        __value.add_command(label="Y", command=self.get_y)
        _get.add_command(label="Increment", command=self.get_increment)
        _get.add_command(label="Edges", command=self.get_edges)
        _get.add_command(label="Flatness", command=self.get_flatness)
        _get.add_command(label="Symmetry", command=self.get_symmetry)
        _get.add_cascade(label='Segment ...', menu=__segment)
        __segment.add_command(label="Defined", command=self.slice_segment)
        __segment.add_command(label="Umbra", command=self.slice_umbra)
        __segment.add_command(label="Penumbra", command=self.slice_penumbra)
        __segment.add_command(label="Shoulders", command=self.slice_shoulders)
        __segment.add_command(label="Tails", command=self.slice_tails)
        menu.add_cascade(label="Help", menu=_help)
        _help.add_command(label="About...", command=self.about)
        self.profiles = []
        self.data_folder = os.path.join(str.split(__file__, 'src')[0],
                           'tests', 'data', 'profile')
        self.selector = tk.Frame(selector_frame)
        self.selector.pack(side=tk.TOP, fill="both", expand=True)
        self.selected_profile = tk.IntVar(value=0)
        self.update('__init__')
        self.canvas.draw()

    def _color(self, cmd):
        assert cmd in ('get', 'next', 'reset')
        if cmd == 'next':
            self._color_palette['idx'] += 1
        elif cmd == 'reset':
            self._color_palette['idx'] = 0
        return self._color_palette['val'][self._color_palette['idx']]

    def select_active(self, i):
        for J in range(len(self.buttons)):
            self.buttons[J].config(relief=tk.RAISED)
        self.selected_profile.set(i)
        self.buttons[i].config(relief=tk.SUNKEN)

    def update(self, msg):
        self._color('reset')
        self.subplot.cla()
        self.buttons = []
        for button in self.selector.winfo_children():
            button.destroy()
        selector_title = tk.Label(master=self.selector, width=10,
                                  bg='white', text='Selector')
        selector_title.pack(side="top", fill="both", expand=True)
        for i,profile in enumerate(self.profiles):
            self.subplot.plot(profile.x, profile.y, color=self._color('get'))
            button = tk.Button(master=self.selector, bg=self._color('get'),
                               text=str(i), width=8,
                               command=partial(self.select_active, i))
            button.pack(side=tk.TOP, fill='both')
            self.buttons.append(button)
            self._color('next')
        try:
            self.select_active(self.selected_profile.get())
        except IndexError:
            pass
        self.status.set(msg)
        self.canvas.draw()

    def from_narrow_png(self):
        filename = askopenfilename(
            initialdir=self.data_folder, title="Film File",
            filetypes=(("Film Files", "*.png"), ("all files", "*.*")))
        self.profiles.append(Profile().from_narrow_png(filename))
        self.update('from_narrow_png')
        self.select_active(len(self.profiles)-1)

    def from_pulse(self):
        pulse_window = tk.Tk()
        pulse_window.title("Pulse Parameters")
        pulse_window.grid()
        variables = []
        params = [('Centre', 0.0), ('Width', 10.0), ('Start', -12.0),
                  ('End', 12.0), ('Step' ,0.1)]
        for i,(l,d) in enumerate(params):
            variable = tk.DoubleVar(pulse_window, value=d)
            variables.append(variable)
            label = tk.Label(pulse_window, text=l)
            entry = tk.Entry(pulse_window, width=10, textvariable=variable)
            label.grid(column=0, row=i, sticky=tk.E)
            entry.grid(column=1, row=i)
        def OK():
            p = [v.get() for v in variables]
            p = [p[0], p[1], (p[2], p[3]), p[4]]
            self.profiles.append(Profile().from_pulse(*p))
            self.selected_profile.set(len(self.profiles)-1)
            self.update('from_pulse')
            self.select_active(len(self.profiles)-1)
            pulse_window.destroy()
        ok_button = tk.Button(pulse_window, text="OK", command=OK)
        ok_button.grid(column=0, row=6, columnspan=2)
        pulse_window.mainloop()

    def from_snc_profiler(self):
        filename = askopenfilename(
            initialdir=self.data_folder, title="SNC Profiler",
            filetypes=(("Profiler Files", "*.prs"), ("all files", "*.*")))
        self.profiles.append(Profile().from_snc_profiler(filename, 'rad'))
        self.profiles.append(Profile().from_snc_profiler(filename, 'tvs'))
        self.update('from_snc_profiler')
        self.select_active(len(self.profiles)-1)

    def file_clr(self):
        self.profiles.pop(self.selected_profile.get())
        self.update('file_clr')

    def file_clr_all(self):
        self.profiles = []
        self.update('file_clr_all')

    def get_edges(self):
        try:
            p = self.selected_profile.get()
            e = self.profiles[p].get_edges()
            result = "Edges: ( {0:.1f}, {1:.1f})".format(e[0], e[1])
            self.update(result)
        except IndexError:
            pass

    def get_flatness(self):
        try:
            p = self.selected_profile.get()
            e = 100 * self.profiles[p].get_flatness()
            result = "Flatness: ( {0:.2f}%)".format(e)
            self.update(result)
        except IndexError:
            pass

    def get_increment(self):
        try:
            p = self.selected_profile.get()
            e = self.profiles[p].get_increment()
            result = "Spacing: {0:.1f} cm".format(e)
            self.update(result)
        except IndexError:
            pass

    def get_symmetry(self):
        try:
            p = self.selected_profile.get()
            e = 100 * self.profiles[p].get_symmetry()
            result = "Symmetry: ( {0:.2f}%)".format(e)
            self.update(result)
        except IndexError:
            pass

    def get_x(self):
        win = tk.Tk()
        win.title("Get Y")
        win.grid()
        y = tk.StringVar(win, value=100.0)
        label = tk.Label(win, width=10, text='y')
        entry = tk.Entry(win, width=10, textvariable=y)
        label.grid(column=0, row=0, sticky=tk.E)
        entry.grid(column=1, row=0)
        def OK():
            try:
                v = float(y.get())
                p = self.selected_profile.get()
                result = self.profiles[p].get_x(v)
                result_string = '('
                if result:
                    for r in result:
                        result_string += '{:.2f}'.format(r) + ', '
                    result_string = result_string[:-2] + ')'
                    self.update('x='+ str(v) +'  ->  '+'y='+result_string)
                else:
                    self.update('')
            except IndexError:
                pass
            win.destroy()
        ok_button = tk.Button(win, text="OK", command=OK)
        ok_button.grid(column=0, row=10, columnspan=2)
        win.mainloop()


    def get_y(self):
        win = tk.Tk()
        win.title("Get X")
        win.grid()
        x = tk.StringVar(win, value=0.0)
        label = tk.Label(win, width=10, text='x')
        entry = tk.Entry(win, width=10, textvariable=x)
        label.grid(column=0, row=0, sticky=tk.E)
        entry.grid(column=1, row=0)
        def OK():
            try:
                v = float(x.get())
                p = self.selected_profile.get()
                result = self.profiles[p].get_y(v)
                if result:
                    self.update('x='+ str(v) +'  ->  '+'y='+'{:.2f}'.format(result))
            except IndexError:
                pass
            win.destroy()
        ok_button = tk.Button(win, text="OK", command=OK)
        ok_button.grid(column=0, row=10, columnspan=2)
        win.mainloop()

    def make_centered(self):
        try:
            p = self.selected_profile.get()
            new_profile = self.profiles[p].make_centered()
            self.profiles = self.profiles[:p] + [new_profile] + self.profiles[(p+1):]
            self.update('make_centered')
        except IndexError:
            pass

    def make_flipped(self):
        try:
            p = self.selected_profile.get()
            new_profile = self.profiles[p].make_flipped()
            self.profiles = self.profiles[:p] + [new_profile] + self.profiles[(p+1):]
            self.update('make_flipped')
        except IndexError:
            pass

    def make_normal_x(self):
        try:
            p = self.selected_profile.get()
            new_profile = self.profiles[p].make_normal_x()
            self.profiles = self.profiles[:p] + [new_profile] + self.profiles[(p+1):]
            self.update('normalise_x')
        except IndexError:
            pass

    def make_normal_y(self):
        norm_window = tk.Tk()
        norm_window.title("Normalization")
        norm_window.grid()
        x = tk.StringVar(norm_window, value=0.0)
        y = tk.StringVar(norm_window, value=1.0)
        x_label = tk.Label(norm_window, width=10, text="Norm distance")
        y_label = tk.Label(norm_window, width=10, text="Norm value")
        x_entry = tk.Entry(norm_window, width=10, textvariable=x)
        y_entry = tk.Entry(norm_window, width=10, textvariable=y)
        x_label.grid(column=0, row=0, sticky=tk.E)
        y_label.grid(column=0, row=1, sticky=tk.E)
        x_entry.grid(column=1, row=0)
        y_entry.grid(column=1, row=1)
        def OK():
            try:
                p = self.selected_profile.get()
                new_profile = self.profiles[p].make_normal_y(x=float(x.get()), y=float(y.get()))
                self.profiles = self.profiles[:p] + [new_profile] + self.profiles[(p+1):]
                self.update('make_normal_y')
            except IndexError:
                pass
            norm_window.destroy()
        ok_button = tk.Button(norm_window, text="OK", command=OK)
        ok_button.grid(column=0, row=10, columnspan=2)
        norm_window.mainloop()

    def make_symmetric(self):
        try:
            p = self.selected_profile.get()
            new_profile = self.profiles[p].make_symmetric()
            self.profiles = self.profiles[:p] + [new_profile] + self.profiles[(p+1):]
            self.update('make_symmetric')
        except IndexError:
            pass

    def resample_x(self):
        step_window = tk.Tk()
        step_window.title("Step Size")
        step_window.grid()
        step = tk.StringVar(step_window, value=0.1)
        label = tk.Label(step_window, width=10, text="Step size")
        entry = tk.Entry(step_window, width=10, textvariable=step)
        label.grid(column=0, row=0, sticky=tk.E)
        entry.grid(column=1, row=0)
        def OK():
            try:
                p = self.selected_profile.get()
                new_profile = self.profiles[p].resample_x(float(step.get()))
                self.profiles = self.profiles[:p] + [new_profile] + self.profiles[(p+1):]
                self.update('resample_x')
            except IndexError:
                pass
            step_window.destroy()
        ok_button = tk.Button(step_window, text="OK", command=OK)
        ok_button.grid(column=0, row=10, columnspan=2)
        step_window.mainloop()

    def resample_y(self):
        step_window = tk.Tk()
        step_window.title("Step Size")
        step_window.grid()
        step = tk.StringVar(step_window, value=0.1)
        label = tk.Label(step_window, width=10, text="Step size")
        entry = tk.Entry(step_window, width=10, textvariable=step)
        label.grid(column=0, row=0, sticky=tk.E)
        entry.grid(column=1, row=0)
        def OK():
            try:
                p = self.selected_profile.get()
                new_profile = self.profiles[p].resample_y(float(step.get()))
                self.profiles = self.profiles[:p] + [new_profile] + self.profiles[(p+1):]
                self.update('resample_y')
            except IndexError:
                pass
            step_window.destroy()
        ok_button = tk.Button(step_window, text="OK", command=OK)
        ok_button.grid(column=0, row=10, columnspan=2)
        step_window.mainloop()

    def slice_penumbra(self):
        p = self.selected_profile.get()
        (new_profile1,new_profile2) = self.profiles[p].slice_penumbra()
        self.profiles = self.profiles[:p] + [new_profile1, new_profile2] + self.profiles[(p+2):]
        self.update('slice_penumbra')

    def slice_segment(self):
        seg_window = tk.Tk()
        seg_window.title("Slice Segment")
        seg_window.grid()
        start = tk.StringVar(seg_window, value=-5.0)
        stop = tk.StringVar(seg_window, value=5.0)
        start_label = tk.Label(seg_window, width=10, text="Start")
        stop_label = tk.Label(seg_window, width=10, text="Stop")
        start_entry = tk.Entry(seg_window, width=10, textvariable=start)
        stop_entry = tk.Entry(seg_window, width=10, textvariable=stop)
        start_label.grid(column=0, row=0, sticky=tk.E)
        stop_label.grid(column=0, row=1, sticky=tk.E)
        start_entry.grid(column=1, row=0)
        stop_entry.grid(column=1, row=1)
        def OK():
            try:
                p = self.selected_profile.get()
                new_profile = self.profiles[p].slice_segment(start=float(start.get()),stop=float(stop.get()))
                self.profiles = self.profiles[:p] + [new_profile] + self.profiles[(p+1):]
                self.update('slice_segment')
            except IndexError:
                pass
            seg_window.destroy()
        ok_button = tk.Button(seg_window, text="OK", command=OK)
        ok_button.grid(column=0, row=10, columnspan=2)
        seg_window.mainloop()

    def slice_shoulders(self):
        p = self.selected_profile.get()
        (new_profile1,new_profile2) = self.profiles[p].slice_shoulders()
        self.profiles = self.profiles[:p] + [new_profile1, new_profile2] + self.profiles[(p+2):]
        self.update('slice_shoulders')

    def slice_tails(self):
        p = self.selected_profile.get()
        (new_profile1,new_profile2) = self.profiles[p].slice_tails()
        self.profiles = self.profiles[:p] + [new_profile1, new_profile2] + self.profiles[(p+2):]
        self.update('slice_tails')

    def slice_umbra(self):
        p = self.selected_profile.get()
        new_profile = self.profiles[p].slice_umbra()
        self.profiles = self.profiles[:p] + [new_profile] + self.profiles[(p+1):]
        self.update('slice_umbra')

    def on_key_press(self, event):
        print("you pressed {}".format(event.key))
        key_press_handler(event, self.canvas, self.toolbar)

    def _quit(self):
        root.quit()
        root.destroy()

    def about(self):
        tk.messagebox.showinfo(
            "About", "Profile Tool \n king.r.paul@gmail.com")

if __name__ == "__main__":
    root = tk.Tk()
    UserInterface(root).pack(side="top", fill="both", expand=True)
    root.mainloop()