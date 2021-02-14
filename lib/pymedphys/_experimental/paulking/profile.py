# Copyright (C) 2019 Paul King, Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

""" For importing, analyzing, and comparing dose or intensity profiles
    from different sources."""
# The following needs to be removed before leaving the experimental module
# pylint: skip-file

import copy
import os
from typing import Callable

from pymedphys._imports import PIL, matplotlib
from pymedphys._imports import numpy as np
from pymedphys._imports import plt, scipy

# from .._level1.coreobjects import _PyMedPhysBase

# pylint: disable = C0103, C0121, W0102


class Profile:
    """One-dimensional distribution of intensity vs position.

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

    Notes
    -----
    Requires Python PIL.

    """

    def __init__(self, x=tuple(), y=tuple(), meta={}):
        """create profile

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
            self.interp = scipy.interpolate.interp1d(
                self.x, self.y, bounds_error=False, fill_value=0.0
            )

    def __len__(self):
        """ # data points  """
        return len(self.x)

    def __eq__(self, other):  # SAME DATA POINTS
        """ same data points """
        if (
            np.array_equal(self.x, other.x)
            and np.array_equal(self.y, other.y)
            and self.meta == other.meta
        ):
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
            fmt_str = "Profile object: "
            fmt_str += "{} pts | x ({} cm -> {} cm) | y ({} -> {})"
            return fmt_str.format(
                len(self.x), min(self.x), max(self.x), min(self.y), max(self.y)
            )
        except ValueError:
            return ""  # EMPTY PROFILE

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
        """import x and y lists

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
        """import list of (x,y) tuples

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
        """create pulse of unit height

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
            if abs(x) > (centre + width / 2.0):
                y.append(0.0)
            elif abs(x) < (centre + width / 2.0):
                y.append(1.0)
            else:
                y.append(0.5)
        return Profile().from_lists(x_vals, y, meta=meta)

    def from_snc_profiler(self, file_name, axis):
        """import profile form SNC Profiler file

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
            munge = "\n".join(profiler_file.readlines())
            munge = munge.replace("\t", "").replace(": ", ":")
            munge = munge.replace(" Time:", "\nTime:")  # BREAK 2-ITEM ROWS
            munge = munge.replace(" Revision:", "\nRevision:")
            munge = munge.replace("Energy:", "\nEnergy:")
            munge = munge.replace("Dose:", "\nDose:")
            munge = munge.replace("Collimator Angle:", "\nCollimator Angle:")
            munge = munge.split("TYPE")[0].split("\n")  # DISCARD NON-METADATA
            munge = [i.split(":", 1) for i in munge if i and ":" in i]
            munge = [i for i in munge if i[1]]  # DISCARD EMPTY ITEMS
            meta = dict(munge)

        with open(file_name) as profiler_file:
            for row in profiler_file.readlines():
                if row[:11] == "Calibration" and "File" not in row:
                    calibs = np.array(row.split())[1:].astype(float)
                elif row[:5] == "Data:":
                    counts = np.array(row.split()[5:145]).astype(float)
                elif row[:15] == "Dose Per Count:":
                    dose_per_count = float(row.split()[-1])
        dose = counts * dose_per_count * calibs

        x_vals = [-11.2 + 0.4 * i for i in range(57)]
        x_prof = list(zip(x_vals, dose[:57]))
        y_vals = [-16.4 + 0.4 * i for i in range(83)]
        y_prof = list(zip(y_vals, dose[57:]))

        if axis == "tvs":
            return Profile().from_tuples(x_prof, meta=meta)
        elif axis == "rad":
            return Profile().from_tuples(y_prof, meta=meta)
        else:
            raise TypeError("axis must be 'tvs' or 'rad'")

    def from_narrow_png(self, file_name, step_size=0.1):
        """import from png file

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
        assert image_file.mode == "RGB"
        dpi_horiz, dpi_vert = image_file.info["dpi"]

        image_array = matplotlib.image.imread(file_name)

        # DIMENSIONS TO AVG ACROSS DIFFERENT FOR HORIZ VS VERT IMG
        if image_array.shape[0] > 5 * image_array.shape[1]:  # VERT
            image_vector = np.average(image_array, axis=(1, 2))
            pixel_size_in_cm = 2.54 / dpi_vert
        elif image_array.shape[1] > 5 * image_array.shape[0]:  # HORIZ
            image_vector = np.average(image_array, axis=(0, 2))
            pixel_size_in_cm = 2.54 / dpi_horiz
        else:
            raise ValueError("The PNG file is not a narrow strip.")
        assert step_size > 5 * pixel_size_in_cm, "step size too small"

        if image_vector.shape[0] % 2 == 0:
            image_vector = image_vector[:-1]  # SO ZERO DISTANCE IS MID-PIXEL

        length_in_cm = image_vector.shape[0] * pixel_size_in_cm
        full_resolution_distances = np.arange(
            -length_in_cm / 2, length_in_cm / 2, pixel_size_in_cm
        )

        # TO MOVE FROM FILM RESOLUTION TO DESIRED PROFILE RESOLUTION
        num_pixels_to_avg_over = int(step_size / pixel_size_in_cm)
        sample_indices = np.arange(
            num_pixels_to_avg_over / 2,
            len(full_resolution_distances),
            num_pixels_to_avg_over,
        ).astype(int)
        downsampled_distances = list(full_resolution_distances[sample_indices])

        downsampled_density = []
        for idx in sample_indices:  # AVERAGE OVER THE SAMPLING WINDOW
            avg_density = np.average(
                image_vector[
                    int(idx - num_pixels_to_avg_over / 2) : int(
                        idx + num_pixels_to_avg_over / 2
                    )
                ]
            )
            downsampled_density.append(avg_density)

        zipped_profile = list(zip(downsampled_distances, downsampled_density))
        return Profile().from_tuples(zipped_profile)

    def get_y(self, x):
        """y-value at distance x

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
        """tuple of x-values at intensity y

        Return distance values based on interpolation of source data for a
        supplied y value.

        Parameters
        ----------
        y : float

        Returns
        -------
        tuple : (x1, x2, ...)

        """

        dose_step = (max(self.y) - min(self.y)) / 100
        x_ = self.resample_y(dose_step).x
        y_ = self.resample_y(dose_step).y
        dists = []
        for i in range(1, len(x_)):
            val = None
            if (y_[i] - y) * (y_[i - 1] - y) < 0:
                val = x_[i] - ((y_[i] - y) / (y_[i] - y_[i - 1])) * (x_[i] - x_[i - 1])
            elif np.isclose(y_[i], y):
                val = x_[i]
            if val and (val not in dists):
                dists.append(val)
        return tuple(dists)

    def get_increment(self):
        """minimum step-size increment

        Returns
        -------
        increment : float

        """
        steps = np.diff(self.x)
        if np.isclose(steps.min(), steps.mean()):
            return steps.mean()
        else:
            return steps.min()

    def plot(self, marker="o-"):
        """profile plot

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

    def slice_segment(self, start=None, stop=None):
        """slice between given end-points

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

        if start is None:
            start = -np.inf

        if stop is None:
            stop = np.inf

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
        """resampled x-values at a given increment

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
        """resampled y-values at a given increment

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

        temp_x = np.arange(min(self.x), max(self.x), 0.01 * self.get_increment())
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
        """normalised to dose at distance

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
        """x-values of profile edges (left, right)

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
        """normalised to distance at edges

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
        cax = 0.5 * (lt_edge + rt_edge)

        new_x = []
        for _, dist in enumerate(self.x):
            if dist < cax:
                new_x.append(-dist / lt_edge)
            elif dist > cax:
                new_x.append(dist / rt_edge)
            else:
                new_x.append(0.0)

        return Profile(new_x, self.y, meta=self.meta)

    def slice_umbra(self):
        """umbra central 80%

        Source dose profile sliced to include only the central region between beam edges.

        Returns
        -------
        Profile

        """
        lt, rt = self.get_edges()
        idx = [i for i, d in enumerate(self.x) if d >= 0.8 * lt and d <= 0.8 * rt]
        new_x = self.x[idx[0] : idx[-1] + 1]
        new_y = self.y[idx[0] : idx[-1] + 1]

        return Profile(x=new_x, y=new_y, meta=self.meta)

    def slice_penumbra(self):
        """penumbra (20 -> 80%, 80 -> 20%)

        Source dose profile sliced to include only the penumbral edges, where the dose
        transitions from 20% - 80% of the umbra dose, as precent at the umbra edge,
        to support wedged profiles.

        Returns
        -------
        tuple
            (left penumbra Profile, right penumbra Profile)

        """

        not_umbra = {
            "lt": self.slice_segment(stop=self.slice_umbra().x[0]),
            "rt": self.slice_segment(start=self.slice_umbra().x[-1]),
        }

        lt_80pct = not_umbra["lt"].get_x(0.8 * not_umbra["lt"].y[-1])[-1]
        lt_20pct = not_umbra["lt"].get_x(0.2 * not_umbra["lt"].y[-1])[-1]
        lt_penum = self.slice_segment(start=lt_20pct, stop=lt_80pct)

        rt_80pct = not_umbra["rt"].get_x(0.8 * not_umbra["rt"].y[0])[-1]
        rt_20pct = not_umbra["rt"].get_x(0.2 * not_umbra["rt"].y[0])[-1]
        rt_penum = self.slice_segment(start=rt_80pct, stop=rt_20pct)

        return (lt_penum, rt_penum)

    def slice_shoulders(self):
        """shoulders (penumbra -> umbra, umbra -> penumbra)

        Source dose profile sliced to include only the profile shoulders,
        outside the central 80% of of the profile but inside the region bounded
        by the 20-80% transition.

        Returns
        -------
        tuple
            (left shoulder Profile, right shoulder Profile)

        """

        lt_start = self.slice_penumbra()[0].x[0]
        lt_stop = self.slice_umbra().x[0]

        rt_start = self.slice_umbra().x[-1]
        rt_stop = self.slice_penumbra()[-1].x[-1]

        lt_should = self.slice_segment(start=lt_start, stop=lt_stop)
        rt_should = self.slice_segment(start=rt_start, stop=rt_stop)

        return (lt_should, rt_should)

    def slice_tails(self):
        """tails (-> penumbra, penumbra ->)

        Source dose profile sliced to include only the profile tail,
        outside the beam penumbra.

        Returns
        -------
        tuple
            (left tail Profile, right tail Profile)

        """
        lt_start = self.x[0]
        lt_stop = self.slice_penumbra()[0].x[0]

        rt_start = self.slice_penumbra()[-1].x[-1]
        rt_stop = self.x[-1]

        lt_tail = self.slice_segment(start=lt_start, stop=lt_stop)
        rt_tail = self.slice_segment(start=rt_start, stop=rt_stop)

        return (lt_tail, rt_tail)

    def get_flatness(self):
        """dose range relative to mean

        Calculated as the dose range normalized to mean dose.

        Returns
        -------
        float

        """
        dose = self.slice_umbra().y
        return (max(dose) - min(dose)) / np.average(dose)

    def get_symmetry(self):
        """max point diff relative to mean

        Calculated as the maximum difference between corresponding points
        on opposite sides of the profile center, relative to mean dose.

        Returns
        -------
        float

        """
        dose = self.slice_umbra().y
        return max(np.abs(np.subtract(dose, dose[::-1]) / np.average(dose)))

    def make_symmetric(self):
        """avg of corresponding points

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
            new_y.append(0.5 * self.interp(n) + 0.5 * reflected.interp(n))
        new_y.append(reflected.y[0])

        return Profile(x=new_x, y=new_y, meta=self.meta)

    def make_centered(self):
        """shift to align edges

        Created by shifting the profile based on edge locations.

        Returns
        -------
        Profile

        """

        return self - np.average(self.get_edges())

    def make_flipped(self):
        """flip L -> R

        Created by reversing the sequence of y values.

        Returns
        -------
        Profile

        """

        return Profile(x=self.x, y=self.y[::-1], meta=self.meta)

    def align_to(self, other):
        """shift self to align to other

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
            -3 * abs(min(list(self.x) + list(other.x))),
            3 * abs(max(list(self.x) + list(other.x))),
            dist_step,
        )
        dose_vals_fixed = other.interp(dist_vals_fixed)
        fixed = Profile(x=dist_vals_fixed, y=dose_vals_fixed)

        possible_offsets = np.arange(
            max(min(self.x), min(other.x)),
            min(max(other.x), max(self.x)) + dist_step,
            dist_step,
        )

        best_fit_qual, best_offset, flipped = 0, -np.inf, False
        for offset in possible_offsets:
            fit_qual_norm = max(
                np.correlate(dose_vals_fixed, (self + offset).interp(fixed.x))
            )
            fit_qual_flip = max(
                np.correlate(
                    dose_vals_fixed, (self.make_flipped() + offset).interp(fixed.x)
                )
            )

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
        """density mapping, reference -> measured

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
        assert ext == ".prs"
        reference = Profile().from_snc_profiler(reference, "rad")
        _, ext = os.path.splitext(measured)
        assert ext == ".png"
        measured = Profile().from_narrow_png(measured)
        measured = measured.align_to(reference)

        dist_vals = np.arange(
            max(min(measured.x), min(reference.x)),
            min(max(measured.x), max(reference.x)),
            max(reference.get_increment(), measured.get_increment()),
        )

        calib_curve = [(measured.get_y(i), reference.get_y(i)) for i in dist_vals]

        return Profile().from_tuples(calib_curve)
