# Copyright (C) 2026 Matthew Jennings
# Copyright (C) 2015 Simon Biggs
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Count the analysed reference points of a gamma array, and those that pass.

This is the one place that decides which gamma values count as analysed and
which as passing, so that a percentage always agrees with its counts.
"""

from __future__ import annotations

import numbers
from collections.abc import Mapping
from dataclasses import dataclass

from pymedphys._imports import numpy as np

_NO_ANALYSED_POINTS = (
    "No reference point was analysed, so there is no percentage passed. Every "
    "gamma value is NaN or masked; check the lower dose cutoff, random_subset, "
    "and any mask."
)


@dataclass(frozen=True, slots=True)
class GammaPassCounts:
    """How many reference points were analysed, and how many of them passed.

    Parameters
    ----------
    passed : int
        The number of analysed points whose gamma is at most 1.
    analysed : int
        The number of points that have a gamma value. Points whose gamma is
        NaN or masked were not analysed.

    Raises
    ------
    TypeError
        If either count is not an integer.
    ValueError
        If a count is negative, or ``passed`` is greater than ``analysed``.
    """

    passed: int
    analysed: int

    def __post_init__(self) -> None:
        for name in ("passed", "analysed"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, numbers.Integral):
                raise TypeError(f"{name} must be an integer, not {value!r}.")
        if not 0 <= self.passed <= self.analysed:
            raise ValueError(
                "Counts must satisfy 0 <= passed <= analysed, but passed is "
                f"{self.passed} and analysed is {self.analysed}."
            )

    @property
    def percent_passed(self) -> float:
        """The percentage of analysed points that passed, from 0 to 100.

        Raises
        ------
        ValueError
            If no point was analysed, so that there is no percentage.
        """
        if self.analysed == 0:
            raise ValueError(_NO_ANALYSED_POINTS)

        # Python integers, because 100 times a NumPy integer count can
        # overflow its fixed width.
        return 100 * int(self.passed) / int(self.analysed)


def gamma_pass_counts(gamma) -> GammaPassCounts:
    """Count the analysed reference points of a gamma array and those that pass.

    A point passes when its gamma is at most 1. NaN marks reference points
    that :func:`pymedphys.gamma` did not analyse (below the lower dose
    cutoff, not selected by ``random_subset``, or with NaN dose left out by
    ``exclude_nan_reference``), so they are left out of both counts, as are
    the masked values of a masked array. Positive infinity is an analysed
    point that fails.

    Every NaN is taken to mark a point that was not analysed. Gamma from other
    software, or from :func:`pymedphys.gamma` before version 0.42.0, can also
    be NaN at analysed points, which would then be left out. Recalculate such
    gamma with this version of :func:`pymedphys.gamma` first.

    Parameters
    ----------
    gamma : array_like
        Gamma values of any shape, as returned by :func:`pymedphys.gamma` for
        one pair of dose and distance thresholds, or any part of them, such
        as the points within a region of interest.

    Returns
    -------
    GammaPassCounts
        The numbers of passing and analysed points. Both are zero when no
        point was analysed.

    Raises
    ------
    TypeError
        If ``gamma`` is the dict that :func:`pymedphys.gamma` returns for
        several thresholds, rather than one of its values.
    ValueError
        If any gamma value is negative.

    See Also
    --------
    pymedphys.gamma_percent_passed : The percentage alone.
    """
    if isinstance(gamma, Mapping):
        raise TypeError(
            "gamma holds results for several thresholds, keyed by (dose, "
            "distance). Pass the result for one pair of thresholds, for "
            "example gamma[(3, 3)]."
        )

    # Masked values, like NaN, were not analysed.
    gamma = np.ma.filled(np.ma.asarray(gamma, dtype=float), np.nan)
    analysed_gamma = gamma[~np.isnan(gamma)]

    negative = np.count_nonzero(analysed_gamma < 0)
    if negative:
        raise ValueError(
            f"Gamma cannot be negative, but {negative} of the values are. "
            "Check that the input is a gamma array."
        )

    return GammaPassCounts(
        passed=int(np.count_nonzero(analysed_gamma <= 1)),
        analysed=int(analysed_gamma.size),
    )


def gamma_percent_passed(gamma) -> float:
    """The percentage of analysed reference points that pass gamma.

    This is :func:`pymedphys.gamma_pass_counts` reduced to one number: the
    passing points as a percentage of the analysed points, from 0 to 100. A
    percentage does not say how many points it rests on, so report the counts
    with it wherever the number of analysed points could be small.

    Parameters
    ----------
    gamma : array_like
        Gamma values of any shape, as returned by :func:`pymedphys.gamma` for
        one pair of dose and distance thresholds, or any part of them.

    Returns
    -------
    float
        The percentage of analysed points whose gamma is at most 1.

    Raises
    ------
    TypeError
        If ``gamma`` is the dict that :func:`pymedphys.gamma` returns for
        several thresholds, rather than one of its values.
    ValueError
        If no reference point was analysed, so every value is NaN or masked,
        or if any gamma value is negative.

    See Also
    --------
    pymedphys.gamma_pass_counts : The counts behind the percentage.
    """
    return gamma_pass_counts(gamma).percent_passed
