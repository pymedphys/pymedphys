# Copyright (C) 2026 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""The result of a gamma calculation: values, counts, settings and provenance.

A result is a snapshot. Its arrays are read-only copies that the result owns,
and its counts and settings are fixed when it is built, so the gamma values,
the pass counts and the record of how they were calculated cannot drift
apart.
"""

from __future__ import annotations

import dataclasses
import importlib.metadata
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal

from pymedphys._imports import numpy as np
from pymedphys._version import __version__

from .counts import (
    RESULT_IS_NOT_AN_ARRAY,
    GammaPassCounts,
    ResultMarker,
    gamma_pass_counts,
)

if TYPE_CHECKING:
    import numpy.typing as npt

_VERSIONED_PACKAGES = ("numpy", "scipy", "numba")


@dataclass(frozen=True, slots=True, kw_only=True)
class GammaSettings:
    """Every setting that a gamma result was calculated with.

    The record holds plain values only, so ``dataclasses.asdict`` gives a
    dictionary that can be written as JSON.

    Parameters
    ----------
    dose_criterion_percent : float
        The dose-difference criterion, in percent.
    distance_criterion_mm : float
        The distance-to-agreement criterion, in the units of the axes.
    normalisation : {"global", "local"}
        Whether the dose criterion is a percentage of ``normalisation_dose``
        or of each reference point's own dose.
    normalisation_dose : float
        The dose that 100% refers to, in the dose units of the input. It sets
        the lower dose cutoff for both kinds of normalisation.
    normalisation_dose_supplied : bool
        True if the caller passed the normalisation dose, and False if it was
        taken from the maximum reference dose.
    lower_dose_cutoff_percent : float
        The lower dose cutoff as passed, in percent of ``normalisation_dose``.
    lower_dose_cutoff : float
        The lower dose cutoff that was used, in the dose units of the input.
        Reference points below it were not analysed.
    exclude_nan_reference : bool
        Whether reference points with NaN dose were left out of the analysis.
    gamma_cap : float or None
        The largest gamma value reported, or None if values were not capped.
    skip_once_passed : bool
        Whether the search for a point stopped as soon as it passed. If so,
        the gamma values of passing points are upper bounds, not minima.
    random_subset : int or None
        The number of reference points that was asked for, or None if every
        eligible point was analysed.
    random_source : {"seed", "generator", "global"} or None
        Where the random subset came from: an integer seed, a
        ``numpy.random.Generator``, or NumPy's global random state. None if
        there was no random subset.
    random_seed : int or None
        The seed, when ``random_source`` is ``"seed"``.
    method : str
        The calculation method.
    search_step_fraction : float or None
        The search step as a fraction of the distance criterion. None for a
        method that has no search step.
    interpolator : str or None
        The interpolator that was used. None for a method that has none.
    """

    dose_criterion_percent: float
    distance_criterion_mm: float
    normalisation: Literal["global", "local"]
    normalisation_dose: float
    normalisation_dose_supplied: bool
    lower_dose_cutoff_percent: float
    lower_dose_cutoff: float
    exclude_nan_reference: bool
    gamma_cap: float | None
    skip_once_passed: bool
    random_subset: int | None
    random_source: Literal["seed", "generator", "global"] | None
    random_seed: int | None
    method: str
    search_step_fraction: float | None
    interpolator: str | None


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class GammaProvenance:
    """What produced a gamma result.

    Parameters
    ----------
    versions : Mapping[str, str]
        The installed version of each package the calculation depends on,
        by package name. It is read-only.
    """

    versions: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "versions", MappingProxyType(dict(self.versions)))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, GammaProvenance):
            return NotImplemented
        return self.versions == other.versions

    # Equal mappings can list their items in different orders, so hash them
    # without order.
    def __hash__(self) -> int:
        return hash(frozenset(self.versions.items()))

    # A read-only mapping view cannot be pickled or copied, so rebuild from a
    # plain dictionary.
    def __reduce__(self):
        return _rebuild_provenance, (dict(self.versions),)


def _rebuild_provenance(versions: dict[str, str]) -> GammaProvenance:
    return GammaProvenance(versions=versions)


def current_provenance() -> GammaProvenance:
    """The provenance of a calculation made now, in this environment."""
    versions = {"pymedphys": __version__}
    for package in _VERSIONED_PACKAGES:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            continue

    return GammaProvenance(versions=versions)


def _owned_read_only(array, dtype=None) -> npt.NDArray:
    """An array that owns its data, is C-contiguous, and cannot be written to.

    An array that views other data is copied: making a view read-only would
    leave the data writeable through its base.
    """
    array = np.asarray(array, dtype=dtype)
    if not (array.flags.owndata and array.flags.c_contiguous):
        array = np.array(array, order="C")
    array.flags.writeable = False

    return array


@dataclass(frozen=True, slots=True, kw_only=True, eq=False, repr=False)
class GammaResult(ResultMarker):
    """Gamma for one pair of criteria, with its counts and settings.

    Results are created by :func:`pymedphys.gamma`. Creating one directly is
    not supported, so that attributes can be added in later versions.

    A result is not an array. Use ``gamma`` for the values. NumPy functions
    given the result itself raise a ``TypeError`` that says so.

    Attributes
    ----------
    gamma : numpy.ndarray
        The gamma values, with the shape and index order of the reference
        dose. NaN marks reference points that were not analysed. The array
        is read-only; ``result.gamma.copy()`` gives one that can be edited.
    axes : tuple of numpy.ndarray
        The reference axes as they were passed, one read-only 1D array for
        each dimension of ``gamma``, in the order of its dimensions.
    passed : int
        The number of analysed points whose gamma is at most 1.
    analysed : int
        The number of reference points that were given a gamma value.
    eligible : int
        The number of reference points at or above the lower dose cutoff,
        before any random subset was drawn. It equals ``analysed`` unless
        there was a random subset.
    settings : GammaSettings
        Every setting the calculation used.
    provenance : GammaProvenance
        What produced the result.
    """

    gamma: npt.NDArray[np.float64]
    axes: tuple[npt.NDArray, ...]
    passed: int
    analysed: int
    eligible: int
    settings: GammaSettings
    provenance: GammaProvenance

    def __post_init__(self) -> None:
        gamma = _owned_read_only(self.gamma, dtype=float)
        axes = tuple(_owned_read_only(axis) for axis in self.axes)
        object.__setattr__(self, "gamma", gamma)
        object.__setattr__(self, "axes", axes)

        if any(axis.ndim != 1 for axis in axes) or gamma.shape != tuple(
            axis.size for axis in axes
        ):
            raise ValueError(
                f"The shape of gamma, {gamma.shape}, does not match the lengths "
                f"of the axes, {tuple(axis.shape for axis in axes)}."
            )
        if not 0 <= self.passed <= self.analysed <= self.eligible <= gamma.size:
            raise ValueError(
                "Counts must satisfy 0 <= passed <= analysed <= eligible <= "
                f"number of points, but passed is {self.passed}, analysed is "
                f"{self.analysed}, eligible is {self.eligible}, and there are "
                f"{gamma.size} points."
            )

    @property
    def percent_passed(self) -> float:
        """The percentage of analysed points that passed, from 0 to 100.

        Raises
        ------
        ValueError
            If no point was analysed, so that there is no percentage.
        """
        return GammaPassCounts(
            passed=self.passed, analysed=self.analysed
        ).percent_passed

    # Read-only flags do not survive pickling or copying, so rebuild through
    # the constructor, which sets them again.
    def __reduce__(self):
        return _rebuild_result, (
            {
                field.name: getattr(self, field.name)
                for field in dataclasses.fields(self)
            },
        )

    # Code written for the array that pymedphys.gamma used to return fails
    # with directions, not with an error from inside NumPy.
    def __array_ufunc__(self, ufunc, method, *inputs, **kwargs):
        raise TypeError(RESULT_IS_NOT_AN_ARRAY)

    def __array_function__(self, func, types, args, kwargs):
        raise TypeError(RESULT_IS_NOT_AN_ARRAY)

    def __repr__(self) -> str:
        settings = self.settings
        if self.analysed:
            summary = (
                f"{self.percent_passed:.1f}% passed "
                f"({self.passed} of {self.analysed} analysed)"
            )
        else:
            summary = "no points analysed"
        if settings.normalisation == "global":
            normalisation = f"global normalisation {settings.normalisation_dose:g}"
        else:
            normalisation = f"{settings.normalisation} normalisation"

        return (
            f"<GammaResult {summary}; {settings.dose_criterion_percent:g}%/"
            f"{settings.distance_criterion_mm:g} mm, {normalisation}, "
            f"{settings.lower_dose_cutoff_percent:g}% cutoff>"
        )


def _rebuild_result(fields: dict) -> GammaResult:
    return GammaResult(**fields)


def build_result(
    *,
    gamma,
    axes,
    eligible: int,
    settings: GammaSettings,
    provenance: GammaProvenance | None = None,
) -> GammaResult:
    """Make the result for one gamma array.

    The array and the axes are copied, so the result shares no memory with
    the calculation's working arrays or with the caller's inputs. The counts
    come from :func:`pymedphys.gamma_pass_counts`, the one place that decides
    which points were analysed and which passed.

    Parameters
    ----------
    gamma : array_like
        Gamma values on the reference grid, with NaN where a point was not
        analysed.
    axes : sequence of array_like
        The reference axes, one for each dimension of ``gamma``.
    eligible : int
        The number of reference points at or above the lower dose cutoff,
        before any random subset.
    settings : GammaSettings
        The settings the calculation used.
    provenance : GammaProvenance, optional
        What produced the values. Defaults to this environment.
    """
    gamma = np.array(gamma, dtype=float, order="C")
    counts = gamma_pass_counts(gamma)

    return GammaResult(
        gamma=gamma,
        axes=tuple(np.array(axis, order="C") for axis in axes),
        passed=counts.passed,
        analysed=counts.analysed,
        eligible=int(eligible),
        settings=settings,
        provenance=current_provenance() if provenance is None else provenance,
    )
