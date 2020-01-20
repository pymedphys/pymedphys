# Copyright (c) 2014-2019 James Kerns

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions
# of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED
# TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF
# CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.

# Adapted from https://raw.githubusercontent.com/jrkerns/pylinac/v2.2.6/pylinac/core/profile.py


# pylint: disable = no-else-return, no-else-raise, inconsistent-return-statements, too-many-nested-blocks, too-many-lines

"""Module of objects that resemble or contain a profile, i.e. a 1 or 2-D f(x) representation."""
import copy
from functools import lru_cache
from typing import List, Tuple, Union

from pymedphys._imports import matplotlib
from pymedphys._imports import numpy as np
from pymedphys._imports import plt, scipy

from .decorators import value_accept
from .geometry import Circle, Point
from .utilities import is_float_like, is_int_like

LEFT = "left"
RIGHT = "right"
VALUE = "value"
INDEX = "index"
BOTH = "both"


def stretch(
    array,
    min: int = 0,  # pylint: disable = redefined-builtin
    max: int = 1,  # pylint: disable = redefined-builtin
    fill_dtype=None,
):
    """'Stretch' the profile to the fit a new min and max value and interpolate in between.
    From: http://www.labri.fr/perso/nrougier/teaching/numpy.100/  exercise #17

    Parameters
    ----------
    array: numpy.ndarray
        The numpy array to stretch.
    min : number
        The new minimum of the values.
    max : number
        The new maximum value.
    fill_dtype : numpy data type
        If None (default), the array will be stretched to the passed min and max.
        If a numpy data type (e.g. np.int16), the array will be stretched to fit the full range of values
        of that data type. If a value is given for this parameter, it overrides ``min`` and ``max``.
    """
    new_max = max
    new_min = min
    if fill_dtype is not None:
        try:
            di = np.iinfo(fill_dtype)
        except ValueError:
            di = np.finfo(fill_dtype)
        new_max = di.max
        new_min = di.min
    # perfectly normalize the array (0..1)
    stretched_array = (array - array.min()) / (array.max() - array.min())
    # stretch normalized array to new max/min
    stretched_array *= new_max  # pylint: disable = undefined-variable
    stretched_array += new_min  # pylint: disable = undefined-variable
    return stretched_array.astype(array.dtype)


class ProfileMixin:
    """A mixin to provide various manipulations of 1D profile data."""

    def invert(self):
        """Invert (imcomplement) the profile."""
        orig_array = self.values
        self.values = (
            -orig_array  # pylint: disable = invalid-unary-operand-type
            + orig_array.max()
            + orig_array.min()
        )

    def normalize(self, norm_val="max"):
        """Normalize the profile to the given value.

        Parameters
        ----------
        norm_val : str, number
            If a string, must be 'max', which normalizes the values to the maximum value.
            If a number, normalizes all values to that number.
        """
        if norm_val == "max":
            val = self.values.max()
        else:
            val = norm_val
        self.values /= val

    def stretch(self, min=0, max=1):  # pylint: disable = redefined-builtin
        """'Stretch' the profile to the min and max parameter values.

        Parameters
        ----------
        min : number
            The new minimum of the values
        max : number
            The new maximum value.
        """
        self.values = stretch(self.values, min=min, max=max)

    def ground(self):
        """Ground the profile such that the lowest value is 0.

        Returns
        -------
        float
            The minimum value that was used as the grounding value.
        """
        min_val = self.values.min()
        self.values = self.values - min_val
        return min_val

    @value_accept(kind=("median", "gaussian"))
    def filter(self, size=0.05, kind: str = "median"):
        """Filter the profile.

        Parameters
        ----------
        size : float, int
            Size of the median filter to apply.
            If a float, the size is the ratio of the length. Must be in the range 0-1.
            E.g. if size=0.1 for a 1000-element array, the filter will be 100 elements.
            If an int, the filter is the size passed.
        kind : {'median', 'gaussian'}
            The kind of filter to apply. If gaussian, `size` is the sigma value.
        """
        if isinstance(size, float):
            if 0 < size < 1:
                size = int(round(len(self.values) * size))
                size = max(size, 1)
            else:
                raise TypeError("Float was passed but was not between 0 and 1")

        if kind == "median":
            self.values = scipy.ndimage.median_filter(self.values, size=size)
        elif kind == "gaussian":
            self.values = scipy.ndimage.gaussian_filter(self.values, sigma=size)

    def __len__(self):
        return len(self.values)

    def __getitem__(self, items):
        return self.values[items]


class SingleProfile(ProfileMixin):
    """A profile that has one large signal, e.g. a radiation beam profile.
    Signal analysis methods are given, mostly based on FWXM calculations.
    Profiles with multiple peaks are better suited by the MultiProfile class.
    """

    interpolation_factor: int = 100
    interpolation_type: str = "linear"

    def __init__(self, values, normalize_sides: bool = True, initial_peak: int = None):
        """
        Parameters
        ----------
        values : ndarray
            The profile numpy array. Must be 1D.
        normalize_sides : bool, optional
            If True (default), each side of the profile will be grounded independently.
            If False, the profile will be grounded by the profile global minimum.
        initial_peak : int, optional
            If the approximate peak of the profile is known it can be passed in. Not needed unless there is more than
            one major peak in the profile, e.g. a very high edge.
        """
        self.values = values
        self._passed_initial_peak = initial_peak
        self._normalize_sides = normalize_sides

    @property
    def values(self):
        """The profile array."""
        return self._values

    @values.setter
    def values(self, value):
        if not isinstance(value, np.ndarray):
            raise TypeError("Values must be a numpy array")
        self._values = value.astype(float)

    @property
    def _right_side_min(self):
        """The minimum on the right side of the peak."""
        return self.values[self._initial_peak_idx :].min()

    @property
    def _left_side_min(self):
        """The minimum on the left side of the peak."""
        return self.values[: self._initial_peak_idx].min()

    @property
    def _values_right(self):
        """The "right side" y data."""
        if self._normalize_sides:
            return self.values - self._right_side_min
        else:
            return self._grounded_values

    @property
    def _values_left(self):
        """The "left side" y data."""
        if self._normalize_sides:
            return self.values - self._left_side_min
        else:
            return self._grounded_values

    @property
    def _grounded_values(self):
        """Ground the profile such that the lowest value is 0.
        """
        min_val = self.values.min()
        grounded_values = self.values - min_val
        return grounded_values

    @property
    def _initial_peak_idx(self) -> int:
        """The initial peak index."""
        x_idx = self._get_initial_peak(self._passed_initial_peak)
        return int(x_idx)

    @_initial_peak_idx.setter
    def _initial_peak_idx(self, value):
        self._passed_initial_peak = value

    def _get_initial_peak(self, initial_peak: int = None):
        """Determine an initial peak to use as a rough guideline.

        Parameters
        ----------
        initial_peak : int, None
            If None, a peak is automatically determined and used.
            If an integer, must be within the range of index values of the profile array.
        """
        # if not passed, get one by peak searching.
        if initial_peak is None:
            lf_edge = 0.2
            rt_edge = 0.8
            while True:
                _, initial_peak_arr = peak_detect(
                    self.values, max_number=1, search_region=(lf_edge, rt_edge)
                )
                try:
                    initial_peak = initial_peak_arr[0]
                    break
                except IndexError:
                    lf_edge -= 0.01
                    rt_edge -= 0.01
                    if lf_edge < 0:
                        raise ValueError(
                            "A reasonable initial peak was not found in the profile. Ensure peak is not at profile edge"
                        )
        # otherwise use the one passed.
        elif len(self.values) < initial_peak < 0:
            raise IndexError(
                "Initial peak that was passed was not reasonably within the profile x_data range"
            )

        return initial_peak

    @value_accept(side=(LEFT, RIGHT), kind=(VALUE, INDEX))
    @lru_cache()
    def _penumbra_point(
        self,
        side: str = "left",
        x: int = 50,
        interpolate: bool = False,
        kind: str = "index",
    ):
        """Return the index of the given penumbra. Search starts at the peak and moves index-by-index
        outward until the penumbra value is hit.

        Parameters
        ----------
        side : {'left', 'right'}
            Which side to look for the penumbra.
        x : int
            The penumbra value to search for. E.g. if passed 20, the method finds
            the index of 0.2*max profile value.
        interpolate : bool
            Whether to interpolate the profile array values to get subpixel precision.
        kind : {'value', 'index'}
            What kind of return is given. If 'index' (default), returns the *index* of the point
            desired. If 'value', returns the value of the profile at the given index.

        Returns
        -------
        int, float
            The index or value of the penumbra point desired.
        """
        # get peak
        peak = copy.copy(self._initial_peak_idx)
        peak = int(peak * self.interpolation_factor if interpolate else peak)

        # get y-data
        if side == LEFT:
            y_data = self._values_left_interp if interpolate else self._values_left
        else:
            y_data = self._values_right_interp if interpolate else self._values_right

        # get threshold
        max_point = y_data.max()
        threshold = max_point * (x / 100)

        # find the index, moving 1 element at a time until the value is encountered
        found = False
        at_end = False
        try:
            while not found and not at_end:
                if y_data[peak] < threshold:
                    found = True
                    peak -= 1 if side == RIGHT else -1
                elif peak == 0:
                    at_end = True
                peak += 1 if side == RIGHT else -1
        except IndexError:
            raise IndexError(
                "The point of interest was beyond the profile; i.e. the profile may be cut off on the side"
            )

        if kind == VALUE:
            return self._values_interp[peak] if interpolate else self.values[peak]
        elif kind == INDEX:
            if interpolate:
                peak /= self.interpolation_factor  # type: ignore
            return peak

    @property
    def _values_left_interp(self):
        """Interpolated values of the "left side" profile data."""
        ydata_f = scipy.interpolate.interp1d(
            self._indices, self._values_left, kind=self.interpolation_type
        )
        y_data = ydata_f(self._indices_interp)
        return y_data

    @property
    def _values_right_interp(self):
        """Interpolated values of the "right side" profile data."""
        ydata_f = scipy.interpolate.interp1d(
            self._indices, self._values_right, kind=self.interpolation_type
        )
        y_data = ydata_f(self._indices_interp)
        return y_data

    @property
    def _values_interp(self):
        """Interpolated values of the entire profile array."""
        ydata_f = scipy.interpolate.interp1d(
            self._indices, self.values, kind=self.interpolation_type
        )
        y_data = ydata_f(self._indices_interp)
        return y_data

    @property
    def _indices_interp(self):
        """Interpolated values of the profile index data."""
        return np.linspace(
            start=0,
            stop=len(self.values) - 1,
            num=(len(self.values) - 1) * self.interpolation_factor,
        )

    @property
    def _indices(self):
        """Values of the profile index data."""
        return np.linspace(start=0, stop=len(self.values) - 1, num=len(self.values))

    def fwxm(self, x: int = 50, interpolate: bool = False):
        """Return the width at X-Max, where X is the percentage height.

        Parameters
        ----------
        x : int
            The percent height of the profile. E.g. x = 50 is 50% height,
            i.e. FWHM.
        interpolate : bool
            If True, interpolates the values to give a more accurate FWXM.

        Returns
        -------
        int, float
            The width in number of elements of the FWXM.
        """
        li = self._penumbra_point(LEFT, x, interpolate)
        ri = self._penumbra_point(RIGHT, x, interpolate)
        fwxm = np.abs(ri - li)
        return fwxm

    def fwxm_center(self, x: int = 50, interpolate: bool = False, kind: str = "index"):
        """Return the center index of the FWXM.

        See Also
        --------
        fwxm() : Further parameter info
        """
        fwxm = self.fwxm(x, interpolate=interpolate)
        li = self._penumbra_point(LEFT, x, interpolate)
        fwxmcen = np.abs(li + fwxm / 2)
        if not interpolate:
            fwxmcen = int(round(fwxmcen))
        if kind == VALUE:
            return (
                self.values[fwxmcen]
                if not interpolate
                else self._values_interp[int(fwxmcen * self.interpolation_factor)]
            )
        else:
            return fwxmcen

    @value_accept(side=(LEFT, RIGHT, BOTH), lower=(0, 100), upper=(0, 100))
    def penumbra_width(
        self,
        side: str = "left",
        lower: int = 20,
        upper: int = 80,
        interpolate: bool = False,
    ):
        """Return the penumbra width of the profile.

        This is the standard "penumbra width" calculation that medical physics talks about in
        radiation profiles. Standard is the 80/20 width, although 90/10
        is sometimes used.

        Parameters
        ----------
        side : {'left', 'right', 'both'}
            Which side of the profile to determined penumbra.
            If 'both', the left and right sides are averaged.
        lower : int
            The "lower" penumbra value used to calculate penumbra. Must be lower than upper.
        upper : int
            The "upper" penumbra value used to calculate penumbra.
        interpolate : bool
            Whether to interpolate the profile to get more accurate values.

        Raises
        ------
        ValueError
            If lower penumbra is larger than upper penumbra
        """
        if lower > upper:
            raise ValueError(
                "Upper penumbra value must be larger than the lower penumbra value"
            )

        if side in (LEFT, RIGHT):
            li = self._penumbra_point(side, lower, interpolate)
            ui = self._penumbra_point(side, upper, interpolate)
            pen = np.abs(ui - li)
        elif side == BOTH:
            li = self._penumbra_point(LEFT, lower, interpolate)
            ui = self._penumbra_point(LEFT, upper, interpolate)
            lpen = np.abs(ui - li)
            li = self._penumbra_point(RIGHT, lower, interpolate)
            ui = self._penumbra_point(RIGHT, upper, interpolate)
            rpen = np.abs(ui - li)
            pen = np.mean([lpen, rpen])

        return pen

    @value_accept(field_width=(0, 1))
    def field_values(self, field_width: float = 0.8):
        """Return a subarray of the values of the profile for the given field width.
        This is helpful for doing, e.g., flatness or symmetry calculations, where you
        want to calculate something over the field, not the whole profile.

        Parameters
        ----------
        field_width : float
            The field width of the profile, based on the fwhm. Must be between 0 and 1.

        Returns
        -------
        ndarray
        """
        left, right = self.field_edges(field_width)
        field_values = self.values[left:right]
        return field_values

    @value_accept(field_width=(0, 1))
    def field_edges(self, field_width: float = 0.8, interpolate: bool = False):
        """Return the indices of the field width edges, based on the FWHM.

        See Also
        --------
        field_values() : Further parameter info.

        Returns
        -------
        left_index, right_index
        """
        fwhmc = self.fwxm_center(interpolate=interpolate)
        field_width *= self.fwxm(interpolate=interpolate)
        if interpolate:
            left = fwhmc - (field_width / 2)
            right = fwhmc + (field_width / 2)
        else:
            left = int(round(fwhmc - field_width / 2))
            right = int(round(fwhmc + field_width / 2))
        return left, right

    @value_accept(
        field_width=(0, 1), calculation=("mean", "median", "max", "min", "area")
    )
    def field_calculation(self, field_width: float = 0.8, calculation: str = "mean"):
        """Perform an operation on the field values of the profile.
        This function is useful for determining field symmetry and flatness.

        Parameters
        ----------
        calculation : {'mean', 'median', 'max', 'min', 'area'}
            Calculation to perform on the field values.

        Returns
        -------
        float

        See Also
        --------
        field_values() : Further parameter info.
        """
        field_values = self.field_values(field_width)

        if calculation == "mean":
            return field_values.mean()
        elif calculation == "median":
            return np.median(field_values)
        elif calculation == "max":
            return field_values.max()
        elif calculation == "min":
            return field_values.min()
        elif calculation == "area":
            cax = self.fwxm_center()
            lt_area = field_values[: cax + 1]
            rt_area = field_values[cax:]
            return lt_area, rt_area

    def plot(self):
        """Plot the profile."""
        plt.plot(self.values)
        plt.show()


class MultiProfile(ProfileMixin):
    """A class for analyzing 1-D profiles that contain multiple signals. Methods are mostly for *finding & filtering*
    the signals, peaks, valleys, etc. Profiles with a single peak (e.g. radiation beam profiles) are better suited by the SingleProfile class.

    Attributes
    ----------
    values : ndarray
        The array of values passed in on instantiation.
    peaks : list
        List of Points, containing value and index information.
    valleys : list
        Same as peaks, but for valleys.

    """

    peaks: List
    valleys: List

    def __init__(self, values):
        """
        Parameters
        ----------
        values : iterable
            Array of profile values.
        """
        self.values = values
        self.peaks = []
        self.valleys = []

    def plot(self, show_peaks: bool = True):
        """Plot the profile.

        Parameters
        ----------
        show_peaks : bool
            Whether to plot the peak locations as well. Will not show if a peak search has
            not yet been done.
        """
        _, ax = plt.subplots()
        ax.plot(self.values)
        if show_peaks:
            peaks_x = [peak.idx for peak in self.peaks]
            peaks_y = [peak.value for peak in self.peaks]
            ax.plot(peaks_x, peaks_y, "go")

    @value_accept(kind=(INDEX, VALUE))
    def find_peaks(
        self,
        threshold: Union[float, int] = 0.3,
        min_distance: Union[float, int] = 0.05,
        max_number: int = None,
        search_region: Tuple = (0.0, 1.0),
        kind: str = "index",
    ):
        """Find the peaks of the profile using a simple maximum value search. This also sets the `peaks` attribute.

        Parameters
        ----------
        threshold : int, float
            The value the peak must be above to be considered a peak. This removes "peaks"
            that are in a low-value region.
            If passed an int, the actual value is the threshold.
            E.g. when passed 15, any peak less with a value <15 is removed.
            If passed a float, it will threshold as a percent. Must be between 0 and 1.
            E.g. when passed 0.4, any peak <40% of the maximum value will be removed.
        min_distance : int, float
            If passed an int, parameter is the number of elements apart a peak must be from neighboring peaks.
            If passed a float, must be between 0 and 1 and represents the ratio of the profile to exclude.
            E.g. if passed 0.05 with a 1000-element profile, the minimum peak width will be 0.05*1000 = 50 elements.
        max_number : int, None
            Specify up to how many peaks will be returned. E.g. if 3 is passed in and 5 peaks are found, only the 3 largest
            peaks will be returned. If None, no limit will be applied.
        search_region : tuple of ints, floats, or both
            The region within the profile to search. The tuple specifies the (left, right) edges to search.
            This allows exclusion of edges from the search. If a value is an int, it is taken as is. If a float, must
            be between 0 and 1 and is the ratio of the profile length. The left value must be less than the right.
        kind : {'value', 'index'}
            What kind of return is given. If 'index' (default), returns the index of the point
            desired. If 'value', returns the value of the profile at the given index.

        Returns
        -------
        ndarray
            Either the values or indices of the peaks.
        """
        peak_vals, peak_idxs = peak_detect(
            self.values,
            threshold,
            min_distance,
            max_number,
            search_region=search_region,
        )
        self.peaks = [
            Point(value=peak_val, idx=peak_idx)
            for peak_idx, peak_val in zip(peak_idxs, peak_vals)
        ]

        return peak_idxs if kind == INDEX else peak_vals

    def find_valleys(
        self,
        threshold: Union[float, int] = 0.3,
        min_distance: Union[float, int] = 0.05,
        max_number: int = None,
        search_region: Tuple = (0.0, 1.0),
        kind: str = "index",
    ):
        """Find the valleys (minimums) of the profile using a simple minimum value search.

        Returns
        -------
        ndarray
            Either the values or indices of the peaks.

        See Also
        --------
        :meth:`~pylinac.core.profile.MultiProfile.find_peaks` : Further parameter info.
        """
        valley_vals, valley_idxs = peak_detect(
            self.values,
            threshold,
            min_distance,
            max_number,
            search_region=search_region,
            find_min_instead=True,
        )
        self.valleys = [
            Point(value=valley_val, idx=valley_idx)
            for valley_idx, valley_val in zip(valley_idxs, valley_vals)
        ]

        return valley_idxs if kind == INDEX else valley_vals

    @value_accept(x=(0, 100))
    def find_fwxm_peaks(
        self,
        x: int = 50,
        threshold: Union[float, int] = 0.3,
        min_distance: Union[float, int] = 0.05,
        max_number: int = None,
        search_region: Tuple = (0.0, 1.0),
        kind: str = "index",
        interpolate: bool = False,
        interpolation_factor: int = 100,
        interpolation_type: str = "linear",
    ):
        """Find peaks using the center of the FWXM (rather than by max value).

        Parameters
        ----------
        x : int, float
            The Full-Width-X-Maximum desired. E.g. 0.7 will return the FW70%M.
            Values must be between 0 and 100.
        interpolate : bool
            Whether to interpolate the profile to determine a more accurate peak location.
        interpolation_factor : int
            The interpolation multiplication factor. E.g. if 10, the profile is interpolated to have 10x the number
            of values. Only used if `interpolate` is True.
        interpolation_type : {'linear', 'cubic'}
            The type of interpolation to perform. Only used if `interpolate` is True.

        See Also
        --------
        find_peaks : Further parameter info
        """
        self.find_peaks(
            threshold, min_distance, max_number, search_region=search_region
        )
        if not self.peaks:
            return [], []

        # subdivide the profiles into SingleProfile's
        subprofiles = self.subdivide(interpolation_factor, interpolation_type)

        # update peak indices with the FWHM value instead of maximum value
        original_peaks = copy.deepcopy(self.peaks)
        for num, (peak, profile) in enumerate(zip(self.peaks, subprofiles)):
            shift = original_peaks[num - 1].idx if num > 0 else 0
            # shift = sum(len(profile.values) for profile in subprofiles[:num])
            fwhmc = profile.fwxm_center(x, interpolate=interpolate)
            peak.idx = fwhmc + shift

        if kind == INDEX:
            return [peak.idx for peak in self.peaks]
        else:
            return [peak.value for peak in self.peaks]

    def subdivide(
        self, interpolation_factor: int = 100, interpolation_type: str = "linear"
    ) -> List[SingleProfile]:
        """Subdivide the profile data into SingleProfiles.

        Returns
        -------
        list
            List of :class:`~pylinac.core.profile.SingleProfile`
        """
        # append the peak list to include the endpoints of the profile
        peaks = self.peaks.copy()
        peaks.insert(0, Point(idx=0))
        peaks.append(Point(idx=len(self.values)))

        # create a list of single profiles from segments of original profile data.
        # New profiles are segmented by initial peak locations.
        subprofiles = []
        for idx in range(len(peaks) - 2):
            left_end = peaks[idx].idx
            peak_idx = peaks[idx + 1].idx - left_end
            right_end = peaks[idx + 2].idx

            values = self.values[int(left_end) : int(right_end)]

            subprofile = SingleProfile(values, initial_peak=peak_idx)
            subprofile.interpolation_factor = interpolation_factor
            subprofile.interpolation_type = interpolation_type
            subprofiles.append(subprofile)

        return subprofiles


class CircleProfile(MultiProfile, Circle):
    """A profile in the shape of a circle.

    Attributes
    ----------
    image_array : ndarray
        The 2D image array.
    start_angle : int, float
        Starting position of the profile in radians; 0 is right (0 on unit circle).
    ccw : bool
        How the profile is/was taken; clockwise or counter-clockwise.
    """

    start_angle: Union[float, int]
    ccw: bool
    sampling_ratio: float

    def __init__(
        self,
        center: Point,
        radius,
        image_array,
        start_angle: Union[float, int] = 0,
        ccw: bool = True,
        sampling_ratio: float = 1.0,
    ):
        """
        Parameters
        ----------
        image_array : ndarray
            The 2D image array.
        start_angle : int, float
            Starting position of the profile in radians; 0 is right (0 on unit circle).
        ccw : bool
            If True (default), the profile will proceed counter-clockwise (the direction on the unit circle).
            If False, will proceed clockwise.
        sampling_ratio : float
            The ratio of pixel sampling to real pixels. E.g. if 1.0, the profile will have approximately
            the same number of elements as was encountered in the profile. A value of 2.0 will sample
            the profile at 2x the number of elements.

        See Also
        --------
        :class:`~pylinac.core.geometry.Circle` : Further parameter info.
        """
        Circle.__init__(self, center, radius)
        self._ensure_array_size(
            image_array, self.radius + self.center.x, self.radius + self.center.y
        )
        self.image_array = image_array
        self.start_angle = start_angle
        self.ccw = ccw
        self.sampling_ratio = sampling_ratio
        self._x_locations = None
        self._y_locations = None
        MultiProfile.__init__(self, self._profile)

    @property
    def size(self):
        """The elemental size of the profile."""
        return np.pi * self.radius * 2 * self.sampling_ratio

    @property
    def _radians(self):
        interval = (2 * np.pi) / self.size
        rads = np.arange(
            0 + self.start_angle, (2 * np.pi) + self.start_angle - interval, interval
        )
        if self.ccw:
            rads = rads[::-1]
        return rads

    @property
    def x_locations(self):
        """The x-locations of the profile values."""
        if self._x_locations is None:
            return np.cos(self._radians) * self.radius + self.center.x
        else:
            return self._x_locations

    @x_locations.setter
    def x_locations(self, array):
        self._x_locations = array

    @property
    def y_locations(self):
        """The x-locations of the profile values."""
        if self._y_locations is None:
            return np.sin(self._radians) * self.radius + self.center.y
        else:
            return self._y_locations

    @y_locations.setter
    def y_locations(self, array):
        self._y_locations = array

    @property
    def _profile(self):
        """The actual profile array; private attr that is passed to MultiProfile."""
        return scipy.ndimage.map_coordinates(
            self.image_array, [self.y_locations, self.x_locations], order=0
        )

    def find_peaks(
        self,
        threshold: Union[float, int] = 0.3,
        min_distance: Union[float, int] = 0.05,
        max_number: int = None,
        search_region: Tuple[float, float] = (0.0, 1.0),
        kind: str = "index",
    ):
        """Overloads Profile to also map peak locations to the image."""
        array = super().find_peaks(
            threshold, min_distance, max_number, search_region, kind
        )
        self._map_peaks()
        return array

    def find_valleys(
        self,
        threshold: Union[float, int] = 0.3,
        min_distance: Union[float, int] = 0.05,
        max_number: int = None,
        search_region=(0.0, 1.0),
        kind: str = "index",
    ):
        """Overload Profile to also map valley locations to the image."""
        array = super().find_valleys(
            threshold, min_distance, max_number, search_region, kind
        )
        self._map_peaks()
        return array

    def find_fwxm_peaks(
        self,
        x: int = 50,
        threshold: Union[float, int] = 0.3,
        min_distance: Union[float, int] = 0.05,
        max_number: int = None,
        search_region: Tuple[float, float] = (0.0, 1.0),
        kind: str = "index",
        interpolate: bool = False,
        interpolation_factor: int = 100,
        interpolation_type: str = "linear",
    ):
        """Overloads Profile to also map the peak locations to the image."""
        array = super().find_fwxm_peaks(
            x,
            threshold,
            min_distance,
            max_number,
            interpolate=interpolate,
            search_region=search_region,
            kind=kind,
            interpolation_type=interpolation_type,
            interpolation_factor=interpolation_factor,
        )
        self._map_peaks()
        return array

    def _map_peaks(self):
        """Map found peaks to the x,y locations on the image/array; i.e. adds x,y coordinates to the peak locations"""
        for peak in self.peaks:
            peak.x = self.x_locations[int(peak.idx)]
            peak.y = self.y_locations[int(peak.idx)]

    def roll(self, amount: int):
        """Roll the profile and x and y coordinates."""
        self.values = np.roll(self.values, -amount)
        self.x_locations = np.roll(self.x_locations, -amount)
        self.y_locations = np.roll(self.y_locations, -amount)

    def plot2axes(  # pylint: disable = arguments-differ
        self,
        axes=None,
        edgecolor: str = "black",
        fill: bool = False,
        plot_peaks: bool = True,
    ):
        """Plot the circle to an axes.

        Parameters
        ----------
        axes : matplotlib.Axes, None
            The axes to plot on. If None, will create a new figure of the image array.
        edgecolor : str
            Color of the Circle; must be a valid matplotlib color.
        fill : bool
            Whether to fill the circle. matplotlib keyword.
        plot_peaks : bool
            If True, plots the found peaks as well.
        """
        if axes is None:
            _, axes = plt.subplots()
            axes.imshow(self.image_array)
        axes.add_patch(
            matplotlib.patches.Circle(
                (self.center.x, self.center.y),
                edgecolor=edgecolor,
                radius=self.radius,
                fill=fill,
            )
        )
        if plot_peaks:
            x_locs = [peak.x for peak in self.peaks]
            y_locs = [peak.y for peak in self.peaks]
            axes.autoscale(enable=False)
            axes.scatter(x_locs, y_locs, s=40, marker="x", c=edgecolor)

    @staticmethod
    def _ensure_array_size(array, min_width, min_height):
        """Ensure the array size of inputs are greater than the minimums."""
        height = array.shape[0]
        width = array.shape[1]
        if width < min_width or height < min_height:
            raise ValueError("Array size not large enough to compute profile")


class CollapsedCircleProfile(CircleProfile):
    """A circular profile that samples a thick band around the nominal circle, rather than just a 1-pixel-wide profile
    to give a mean value.
    """

    width_ratio: float
    num_profiles: int

    @value_accept(width_ratio=(0, 1))
    def __init__(
        self,
        center: Point,
        radius,
        image_array,
        start_angle: int = 0,
        ccw: bool = True,
        sampling_ratio: float = 1.0,
        width_ratio: float = 0.1,
        num_profiles: int = 20,
    ):
        """
        Parameters
        ----------
        width_ratio : float
            The "thickness" of the band to sample. The ratio is relative to the radius. E.g. if the radius is 20
            and the width_ratio is 0.2, the "thickness" will be 4 pixels.
        num_profiles : int
            The number of profiles to sample in the band. Profiles are distributed evenly within the band.

        See Also
        --------
        :class:`~pylinac.core.profile.CircleProfile` : Further parameter info.
        """
        self.width_ratio = width_ratio
        self.num_profiles = num_profiles
        super().__init__(center, radius, image_array, start_angle, ccw, sampling_ratio)

    @property
    def _radii(self):
        return np.linspace(
            start=self.radius * (1 - self.width_ratio),
            stop=self.radius * (1 + self.width_ratio),
            num=self.num_profiles,
        )

    @property
    def size(self):
        return np.pi * max(self._radii) * 2 * self.sampling_ratio

    @property
    def _multi_x_locations(self) -> List:
        """List of x-locations of the sampling profiles"""
        x = []
        cos = np.cos(self._radians)
        # extract profile for each circle radii
        for radius in self._radii:
            x.append(cos * radius + self.center.x)
        return x

    @property
    def _multi_y_locations(self) -> List:
        """List of x-locations of the sampling profiles"""
        y = []
        sin = np.sin(self._radians)
        # extract profile for each circle radii
        for radius in self._radii:
            y.append(sin * radius + self.center.y)
        return y

    @property
    def _profile(self):
        """The actual profile array; private attr that is passed to MultiProfile."""
        profile = np.zeros(len(self._multi_x_locations[0]))
        for _, x, y in zip(
            self._radii, self._multi_x_locations, self._multi_y_locations
        ):
            profile += scipy.ndimage.map_coordinates(self.image_array, [y, x], order=0)
        profile /= self.num_profiles
        return profile

    def plot2axes(
        self,
        axes=None,
        edgecolor: str = "black",
        fill: bool = False,
        plot_peaks: bool = True,
    ):
        """Add 2 circles to the axes: one at the maximum and minimum radius of the ROI.

        See Also
        --------
        :meth:`~pylinac.core.profile.CircleProfile.plot2axes` : Further parameter info.
        """
        if axes is None:
            _, axes = plt.subplots()
            axes.imshow(self.image_array)
        axes.add_patch(
            matplotlib.patches.Circle(
                (self.center.x, self.center.y),
                edgecolor=edgecolor,
                radius=self.radius * (1 + self.width_ratio),
                fill=fill,
            )
        )
        axes.add_patch(
            matplotlib.patches.Circle(
                (self.center.x, self.center.y),
                edgecolor=edgecolor,
                radius=self.radius * (1 - self.width_ratio),
                fill=fill,
            )
        )
        if plot_peaks:
            x_locs = [peak.x for peak in self.peaks]
            y_locs = [peak.y for peak in self.peaks]
            axes.autoscale(enable=False)
            axes.scatter(x_locs, y_locs, s=20, marker="x", c=edgecolor)


def peak_detect(
    values,
    threshold: Union[float, int] = None,
    min_distance: Union[float, int] = 10,
    max_number: int = None,
    search_region=(0.0, 1.0),
    find_min_instead: bool = False,
):
    """Find the peaks or valleys of a 1D signal.

    Uses the difference (np.diff) in signal to find peaks. Current limitations include:
        1) Only for use in 1-D data; 2D may be possible with the gradient function.
        2) Will not detect peaks at the very edge of array (i.e. 0 or -1 index)

    Parameters
    ----------
    values : array-like
        Signal values to search for peaks within.
    threshold : int, float
        The value the peak must be above to be considered a peak. This removes "peaks"
        that are in a low-value region.
        If passed an int, the actual value is the threshold.
        E.g. when passed 15, any peak less with a value <15 is removed.
        If passed a float, it will threshold as a percent. Must be between 0 and 1.
        E.g. when passed 0.4, any peak <40% of the maximum value will be removed.
    min_distance : int, float
        If passed an int, parameter is the number of elements apart a peak must be from neighboring peaks.
        If passed a float, must be between 0 and 1 and represents the ratio of the profile to exclude.
        E.g. if passed 0.05 with a 1000-element profile, the minimum peak width will be 0.05*1000 = 50 elements.
    max_number : int
        Specify up to how many peaks will be returned. E.g. if 3 is passed in and 5 peaks are found, only the 3 largest
        peaks will be returned.
    find_min_instead : bool
        If False (default), peaks will be returned.
        If True, valleys will be returned.

    Returns
    -------
    max_vals : numpy.array
        The values of the peaks found.
    max_idxs : numpy.array
        The x-indices (locations) of the peaks.

    Raises
    ------
    ValueError
        If float not between 0 and 1 passed to threshold.
    """
    peak_vals = (
        []
    )  # a list to hold the y-values of the peaks. Will be converted to a numpy array
    peak_idxs = []  # ditto for x-values (index) of y data.

    if find_min_instead:
        values = -values

    # """Limit search to search region"""
    left_end = search_region[0]
    if is_float_like(left_end):
        left_index = int(left_end * len(values))
    elif is_int_like(left_end):
        left_index = left_end
    else:
        raise ValueError(f"{left_end} must be a float or int")

    right_end = search_region[1]
    if is_float_like(right_end):
        right_index = int(right_end * len(values))
    elif is_int_like(right_end):
        right_index = right_end
    else:
        raise ValueError(f"{right_end} must be a float or int")

    # minimum peak spacing calc
    if isinstance(min_distance, float):
        if 0 > min_distance >= 1:
            raise ValueError(
                "When min_peak_width is passed a float, value must be between 0 and 1"
            )
        else:
            min_distance = int(min_distance * len(values))

    values = values[left_index:right_index]

    # """Determine threshold value"""
    if isinstance(threshold, float) and threshold < 1:
        data_range = values.max() - values.min()
        threshold = threshold * data_range + values.min()
    elif isinstance(threshold, float) and threshold >= 1:
        raise ValueError("When threshold is passed a float, value must be less than 1")
    elif threshold is None:
        threshold = values.min()

    # """Take difference"""
    values_diff = np.diff(
        values.astype(float)
    )  # y and y_diff must be converted to signed type.

    # """Find all potential peaks"""
    for idx in range(len(values_diff) - 1):
        # For each item of the diff array, check if:
        # 1) The y-value is above the threshold.
        # 2) The value of y_diff is positive (negative for valley search), it means the y-value changed upward.
        # 3) The next y_diff value is zero or negative (or positive for valley search); a positive-then-negative diff value means the value
        # is a peak of some kind. If the diff is zero it could be a flat peak, which still counts.

        # 1)
        if values[idx + 1] < threshold:
            continue

        y1_gradient = values_diff[idx] > 0
        y2_gradient = values_diff[idx + 1] <= 0

        # 2) & 3)
        if y1_gradient and y2_gradient:
            # If the next value isn't zero it's a single-pixel peak. Easy enough.
            if values_diff[idx + 1] != 0:
                peak_vals.append(values[idx + 1])
                peak_idxs.append(idx + 1 + left_index)
            # elif idx >= len(y_diff) - 1:
            #     pass
            # Else if the diff value is zero, it could be a flat peak, or it could keep going up; we don't know yet.
            else:
                # Continue on until we find the next nonzero diff value.
                try:
                    shift = 0
                    while values_diff[(idx + 1) + shift] == 0:
                        shift += 1
                        if (idx + 1 + shift) >= (len(values_diff) - 1):
                            break
                    # If the next diff is negative (or positive for min), we've found a peak. Also put the peak at the center of the flat
                    # region.
                    is_a_peak = values_diff[(idx + 1) + shift] < 0
                    if is_a_peak:
                        peak_vals.append(values[int((idx + 1) + np.round(shift / 2))])
                        peak_idxs.append((idx + 1 + left_index) + np.round(shift / 2))
                except IndexError:
                    pass

    # convert to numpy arrays
    peak_vals = np.array(peak_vals)
    peak_idxs = np.array(peak_idxs)

    # """Enforce the min_peak_distance by removing smaller peaks."""
    # For each peak, determine if the next peak is within the min peak width range.
    index = 0
    while index < len(peak_idxs) - 1:

        # If the second peak is closer than min_peak_distance to the first peak, find the larger peak and remove the other one.
        if peak_idxs[index] > peak_idxs[index + 1] - min_distance:
            if peak_vals[index] > peak_vals[index + 1]:
                idx2del = index + 1
            else:
                idx2del = index
            peak_vals = np.delete(peak_vals, idx2del)
            peak_idxs = np.delete(peak_idxs, idx2del)
        else:
            index += 1

    # """If Maximum Number passed, return only up to number given based on a sort of peak values."""
    if max_number is not None and len(peak_idxs) > max_number:
        sorted_peak_vals = peak_vals.argsort()  # type: ignore  # sorts low to high
        peak_vals = peak_vals[
            sorted_peak_vals[
                -max_number:  # pylint: disable = invalid-unary-operand-type
            ]
        ]
        peak_idxs = peak_idxs[
            sorted_peak_vals[
                -max_number:  # pylint: disable = invalid-unary-operand-type
            ]
        ]

    # If we were looking for minimums, convert the values back to the original sign
    if find_min_instead:
        peak_vals = (
            -peak_vals  # type: ignore  # pylint: disable = invalid-unary-operand-type
        )

    return peak_vals, peak_idxs
