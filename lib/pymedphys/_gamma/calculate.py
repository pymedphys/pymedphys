# Copyright (C) 2026 Matthew Jennings
# Copyright (C) 2015-2018 Simon Biggs
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Compare two dose grids with the gamma index, and return results."""

from __future__ import annotations

import functools
import itertools
import numbers
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Literal, ParamSpec, TypeVar, overload

from pymedphys._imports import numpy as np

from .implementation import shell
from .result import GammaResult, GammaSettings, build_result, current_provenance
from .utilities import run_input_checks, warn_caller

if TYPE_CHECKING:
    import numpy.typing as npt

    _Criteria = Sequence[float] | npt.NDArray

_P = ParamSpec("_P")
_R = TypeVar("_R")

_DEFAULT_SEARCH_STEP_FRACTION = 0.1
_INTERPOLATORS = ("pymedphys", "scipy")

# Options as they were named before version 0.42.0, with what replaces each.
_RENAMED_OPTIONS = {
    "dose_percent_threshold": "dose_criterion_percent",
    "distance_mm_threshold": "distance_criterion_mm",
    "lower_percent_dose_cutoff": "lower_dose_cutoff_percent",
    "local_gamma": (
        'normalisation ("local" in place of True, "global" in place of False)'
    ),
    "global_normalisation": "normalisation_dose",
    "interp_fraction": (
        "search_step_fraction (one divided by the old value, so 10 becomes 0.1)"
    ),
    "interp_algo": "interpolator",
    "max_gamma": "gamma_cap",
    "ram_available": "memory_budget_bytes",
    "quiet": "nothing: remove it, and configure logging to see progress messages",
}


def _explain_renamed_options(function: Callable[_P, _R]) -> Callable[_P, _R]:
    """Answer a call that uses old option names with their replacements."""

    @functools.wraps(function)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        renamed = [name for name in kwargs if name in _RENAMED_OPTIONS]
        if renamed:
            replacements = "; ".join(
                f"{name} with {_RENAMED_OPTIONS[name]}" for name in renamed
            )
            raise TypeError(
                "pymedphys.gamma options were renamed in version 0.42.0. "
                f"Replace {replacements}."
            )

        return function(*args, **kwargs)

    return wrapper


def _real_number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise TypeError(f"{name} must be a number, not {value!r}.")

    return float(value)


def _whole_number(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, numbers.Integral):
        raise TypeError(f"{name} must be a whole number, not {value!r}.")

    return int(value)


def _criteria(value, name: str) -> tuple[tuple[float, ...], bool]:
    """The criteria as floats, and whether they were given as a list."""
    array = np.asarray(value)
    if array.dtype.kind not in "iuf":
        raise TypeError(f"{name} must be a number or a list of numbers, not {value!r}.")
    if array.ndim > 1:
        raise ValueError(f"{name} must be a number or a one-dimensional list.")

    values = tuple(float(item) for item in np.atleast_1d(array))
    if not values:
        raise ValueError(f"{name} is an empty list; give at least one value.")
    for item in values:
        if not (np.isfinite(item) and item > 0):
            raise ValueError(
                f"{name} must be finite and greater than zero, but got {item}."
            )
    if len(set(values)) != len(values):
        raise ValueError(f"{name} lists a value more than once: {list(values)}.")

    return values, array.ndim == 1


def _random_record(random_subset, random_state):
    """Check the sampling options and describe where the subset comes from."""
    if random_subset is not None:
        random_subset = _whole_number(random_subset, "random_subset")
        if random_subset < 0:
            raise ValueError(
                f"random_subset must not be negative, but got {random_subset}."
            )

    is_generator = isinstance(random_state, np.random.Generator)
    seed = None
    if random_state is not None and not is_generator:
        if isinstance(random_state, bool) or not isinstance(
            random_state, numbers.Integral
        ):
            raise TypeError(
                "random_state must be a whole-number seed or a "
                f"numpy.random.Generator, not {random_state!r}."
            )
        seed = int(random_state)
        if seed < 0:
            raise ValueError(f"random_state must not be negative, but got {seed}.")

    if random_subset is None:
        return None, None, None
    if random_state is None:
        return random_subset, "global", None
    if is_generator:
        return random_subset, "generator", None

    return random_subset, "seed", seed


@overload
def gamma(
    axes_reference,
    dose_reference,
    axes_evaluation,
    dose_evaluation,
    dose_criterion_percent: float,
    distance_criterion_mm: float,
    *,
    lower_dose_cutoff_percent: float = 20,
    normalisation: Literal["global", "local"] = "global",
    normalisation_dose: float | None = None,
    gamma_cap: float | None = None,
    skip_once_passed: bool = False,
    random_subset: int | None = None,
    random_state: int | np.random.Generator | None = None,
    exclude_nan_reference: bool = False,
    search_step_fraction: float | None = None,
    interpolator: Literal["pymedphys", "scipy"] | None = None,
    memory_budget_bytes: int | None = None,
) -> GammaResult: ...


@overload
def gamma(
    axes_reference,
    dose_reference,
    axes_evaluation,
    dose_evaluation,
    dose_criterion_percent: _Criteria,
    distance_criterion_mm: float | _Criteria,
    *,
    lower_dose_cutoff_percent: float = 20,
    normalisation: Literal["global", "local"] = "global",
    normalisation_dose: float | None = None,
    gamma_cap: float | None = None,
    skip_once_passed: bool = False,
    random_subset: int | None = None,
    random_state: int | np.random.Generator | None = None,
    exclude_nan_reference: bool = False,
    search_step_fraction: float | None = None,
    interpolator: Literal["pymedphys", "scipy"] | None = None,
    memory_budget_bytes: int | None = None,
) -> tuple[GammaResult, ...]: ...


@overload
def gamma(
    axes_reference,
    dose_reference,
    axes_evaluation,
    dose_evaluation,
    dose_criterion_percent: float,
    distance_criterion_mm: _Criteria,
    *,
    lower_dose_cutoff_percent: float = 20,
    normalisation: Literal["global", "local"] = "global",
    normalisation_dose: float | None = None,
    gamma_cap: float | None = None,
    skip_once_passed: bool = False,
    random_subset: int | None = None,
    random_state: int | np.random.Generator | None = None,
    exclude_nan_reference: bool = False,
    search_step_fraction: float | None = None,
    interpolator: Literal["pymedphys", "scipy"] | None = None,
    memory_budget_bytes: int | None = None,
) -> tuple[GammaResult, ...]: ...


@_explain_renamed_options
def gamma(
    axes_reference,
    dose_reference,
    axes_evaluation,
    dose_evaluation,
    dose_criterion_percent,
    distance_criterion_mm,
    *,
    lower_dose_cutoff_percent=20,
    normalisation="global",
    normalisation_dose=None,
    gamma_cap=None,
    skip_once_passed=False,
    random_subset=None,
    random_state=None,
    exclude_nan_reference=False,
    search_step_fraction=None,
    interpolator=None,
    memory_budget_bytes=None,
):
    """Compare two dose grids with the gamma index.

    Gamma is calculated for 1, 2, or 3 dimensional grids of any size. For
    each reference point, the evaluation dose is interpolated on shells of
    increasing radius, using ideas presented in
    <http://dx.doi.org/10.1118/1.2721657>.

    Parameters
    ----------
    axes_reference : tuple of array_like
        The reference coordinates: one 1D array for each dimension of
        ``dose_reference``, in the order of its dimensions. Ascending and
        descending axes are both accepted and keep their order in the
        result. A single 1D NumPy array is accepted for one-dimensional
        doses.
    dose_reference : array_like
        The reference dose grid. Gamma is found for each point of this grid
        and returned on it.
    axes_evaluation : tuple of array_like
        The evaluation coordinates, in the same form. Unevenly spaced axes
        need the SciPy interpolator. An axis with a single value makes the
        evaluation grid a plane, line or point with no thickness, such as a
        single-frame RT Dose. Gamma then searches within that plane, line or
        point only, and adds each reference point's distance from it, so
        results do not depend on the coordinate origin.
    dose_evaluation : array_like
        The evaluation dose grid, which is interpolated and searched around
        each reference point.
    dose_criterion_percent : float or list of float
        The dose-difference criterion, in percent of ``normalisation_dose``
        for global normalisation, or of each reference point's dose for
        local normalisation.
    distance_criterion_mm : float or list of float
        The distance-to-agreement criterion, in the units of the axes.
    lower_dose_cutoff_percent : float, optional
        Reference points whose dose is below this percentage of
        ``normalisation_dose`` are not analysed. Defaults to 20.
    normalisation : {"global", "local"}, optional
        ``"global"``, the default, takes the dose criterion as a percentage
        of ``normalisation_dose``. ``"local"`` takes it as a percentage of
        each reference point's own dose, which must then not be zero at any
        analysed point.
    normalisation_dose : float, optional
        The dose that 100% refers to. It sets the global dose criterion and,
        for both kinds of normalisation, the lower dose cutoff. Defaults to
        the maximum reference dose. It must be finite and greater than zero.
    gamma_cap : float, optional
        The largest gamma value reported. The search stops at the distance
        beyond which gamma would exceed the cap, and larger values are
        reported as the cap, which speeds up the calculation. It must be
        greater than 1, so that it never changes whether a point passes.
        Defaults to no cap.
    skip_once_passed : bool, optional
        Stop searching for a reference point as soon as its gamma is below 1.
        This is faster and does not change which points pass, but the gamma
        values of passing points are then upper bounds, not minima, so do not
        use it where the values themselves are reported. Defaults to False.
    random_subset : int, optional
        Analyse only this many reference points, chosen at random from those
        at or above the lower dose cutoff. It is a number of points, not a
        fraction. If it exceeds the number of eligible points, all of them
        are analysed.
    random_state : int or numpy.random.Generator, optional
        A seed or generator that selects the ``random_subset``. Defaults to
        NumPy's global random state, so :func:`numpy.random.seed` applies.
        The result identifies the analysed points exactly. A seed selects
        the same points again only with the same version of NumPy.
    exclude_nan_reference : bool, optional
        Leave reference points whose dose is NaN out of the analysis, for
        example unmeasured detector positions or points outside a region of
        interest. They are not analysed, and the default
        ``normalisation_dose`` ignores them. Defaults to False, which raises
        ``ValueError`` if ``dose_reference`` contains NaN, so that NaN from
        an upstream error is not silently dropped. Infinite reference doses,
        and NaN or infinite evaluation doses, always raise.
    search_step_fraction : float, optional
        The step between search shells, and between the points sampled on
        each shell, as a fraction of the distance criterion. It must be
        greater than 0 and at most 1, and defaults to 0.1. A smaller step
        finds gamma more accurately and takes longer. The search can only
        overestimate gamma, so too coarse a step reports passing points as
        failing, never the reverse. Where the evaluation dose changes by
        ``G`` dose criteria across one distance criterion, gamma can be
        overestimated by up to about ``search_step_fraction * sqrt(1 +
        G**2)``. Lower the step where a tight dose criterion meets a large
        distance criterion or a steep dose gradient, until the percentage
        passed stops changing.
    interpolator : {"pymedphys", "scipy"}, optional
        The implementation that interpolates the evaluation dose. Both
        interpolate linearly. By default the calculation uses "pymedphys",
        or "scipy" where the evaluation axes are unevenly spaced, and the
        result records which was used. Asking for "pymedphys" with unevenly
        spaced evaluation axes raises ``ValueError``.
    memory_budget_bytes : int, optional
        A budget for the search's working memory, used to split the work
        into chunks. It does not change results and is not a limit on the
        memory of the process. Defaults to 1.5 GiB.

    Returns
    -------
    GammaResult or tuple of GammaResult
        One result when both criteria are single numbers. When either is a
        list, a tuple with one result for each combination, in the order
        given with the dose criteria varying slowest. Each is what a call
        with that pair alone returns: a list shares work between the dose
        criteria and never changes a result.

        A result holds the gamma values on the reference grid, the reference
        axes, the numbers of eligible, analysed and passing points, and every
        setting used. ``result.gamma`` has the shape and index order of
        ``dose_reference``, and ``result.axes`` are its coordinates; use them
        when plotting. If the reference came from
        :func:`pymedphys.dicom.zyx_and_dose_from_dataset`, that order can
        differ from the DICOM dataset's raw ``pixel_array``.

        A reference point is analysed when its dose is at or above the lower
        dose cutoff and, if ``random_subset`` is set, it was selected. Every
        analysed point has a gamma value; NaN marks only the points that
        were not analysed.

        An analysed reference point outside the evaluation grid is compared
        with the evaluation data up to the grid's edge, so it may fail. A
        warning gives the number of such points more than one search step
        outside the grid. Crop the reference grid to the region the
        evaluation grid covers if only that region should be analysed.

    Raises
    ------
    TypeError
        If an option has the wrong type, or is one of the names used before
        version 0.42.0, in which case the message gives the replacement.
    ValueError
        If a criterion is not finite and greater than zero, a list of
        criteria is empty or repeats a value, the axes do not match the
        doses, either dose grid contains infinite values, ``dose_evaluation``
        contains NaN, ``dose_reference`` contains NaN (unless
        ``exclude_nan_reference=True``) or no finite values, local
        normalisation meets an analysed reference point of zero dose, or
        another option is outside its documented range.

    Warns
    -----
    UserWarning
        If no reference point was analysed, or if analysed reference points
        lie more than one search step outside the evaluation grid.

    See Also
    --------
    pymedphys.gamma_pass_counts : Count the analysed and passing points of
        part of a gamma array, such as a region of interest.

    Examples
    --------
    Compare two dose profiles sampled every millimetre, with criteria of 3%
    and 0.1 mm. The first reference point is below the lower dose cutoff, so
    it is not analysed, and one of the other four points fails.

    >>> import numpy as np
    >>> import pymedphys
    >>> position = np.arange(5.0)
    >>> reference = np.array([0.1, 1.0, 1.0, 1.0, 1.0])
    >>> evaluation = np.array([0.1, 1.0, 1.02, 1.05, 1.0])
    >>> result = pymedphys.gamma(position, reference, position, evaluation, 3, 0.1)
    >>> result.passed, result.analysed
    (3, 4)
    >>> result.percent_passed
    75.0
    >>> np.isnan(result.gamma)
    array([ True, False, False, False, False])
    >>> result.settings.lower_dose_cutoff_percent
    20.0

    A list of criteria gives one result for each combination.

    >>> results = pymedphys.gamma(
    ...     position, reference, position, evaluation, [3, 6], 0.1
    ... )
    >>> [(r.settings.dose_criterion_percent, r.passed) for r in results]
    [(3.0, 3), (6.0, 4)]
    """
    doses, dose_is_list = _criteria(dose_criterion_percent, "dose_criterion_percent")
    distances, distance_is_list = _criteria(
        distance_criterion_mm, "distance_criterion_mm"
    )

    lower_dose_cutoff_percent = _real_number(
        lower_dose_cutoff_percent, "lower_dose_cutoff_percent"
    )
    if not np.isfinite(lower_dose_cutoff_percent):
        raise ValueError("lower_dose_cutoff_percent must be finite.")

    if normalisation not in ("global", "local") or isinstance(normalisation, bool):
        raise ValueError(
            f'normalisation must be "global" or "local", not {normalisation!r}.'
        )

    if normalisation_dose is not None:
        normalisation_dose = _real_number(normalisation_dose, "normalisation_dose")
        if not (np.isfinite(normalisation_dose) and normalisation_dose > 0):
            raise ValueError(
                "normalisation_dose must be finite and greater than zero, but "
                f"got {normalisation_dose}."
            )

    if gamma_cap is not None:
        gamma_cap = _real_number(gamma_cap, "gamma_cap")
        if np.isnan(gamma_cap) or gamma_cap <= 1:
            raise ValueError(
                "gamma_cap must be greater than 1. Gamma values above it are "
                "reported as the cap, so a smaller cap would report failing "
                "points as passing."
            )

    random_subset, random_source, random_seed = _random_record(
        random_subset, random_state
    )

    if search_step_fraction is None:
        search_step_fraction = _DEFAULT_SEARCH_STEP_FRACTION
    else:
        search_step_fraction = _real_number(
            search_step_fraction, "search_step_fraction"
        )
        if not 0 < search_step_fraction <= 1:
            raise ValueError(
                "search_step_fraction must be greater than 0 and at most 1, "
                f"but got {search_step_fraction}. It is the search step as a "
                "fraction of the distance criterion."
            )

    if interpolator is not None and interpolator not in _INTERPOLATORS:
        raise ValueError(
            f'interpolator must be "pymedphys" or "scipy", not {interpolator!r}.'
        )

    if memory_budget_bytes is None:
        memory_budget_bytes = shell.DEFAULT_RAM
    else:
        memory_budget_bytes = _whole_number(memory_budget_bytes, "memory_budget_bytes")
        if memory_budget_bytes <= 0:
            raise ValueError("memory_budget_bytes must be greater than zero.")

    options = shell.GammaInternalFixedOptions.from_user_inputs(
        axes_reference,
        dose_reference,
        axes_evaluation,
        dose_evaluation,
        list(doses),
        list(distances),
        lower_percent_dose_cutoff=lower_dose_cutoff_percent,
        interp_fraction=1 / search_step_fraction,
        max_gamma=np.inf if gamma_cap is None else gamma_cap,
        local_gamma=normalisation == "local",
        global_normalisation=normalisation_dose,
        skip_once_passed=bool(skip_once_passed),
        random_subset=random_subset,
        ram_available=memory_budget_bytes,
        interp_algo="pymedphys" if interpolator is None else interpolator,
        random_state=random_state,
        exclude_nan_reference=bool(exclude_nan_reference),
        uneven_axes="switch" if interpolator is None else "raise",
    )

    arrays = shell.calculate_gamma_arrays(
        options, np.shape(dose_reference), lower_dose_cutoff_percent
    )

    with np.errstate(invalid="ignore"):
        eligible = int(
            np.count_nonzero(np.asarray(dose_reference) >= options.lower_dose_cutoff)
        )
    selected = int(np.count_nonzero(options.reference_points_to_calc))
    if selected == 0:
        warn_caller(
            "No reference point was analysed, so every gamma value is NaN. "
            "Check lower_dose_cutoff_percent, normalisation_dose and "
            "random_subset."
        )

    reference_axes, _ = run_input_checks(
        axes_reference, dose_reference, axes_evaluation, dose_evaluation
    )
    provenance = current_provenance()

    results = []
    for (dose, distance), values in zip(
        itertools.product(doses, distances), arrays.values(), strict=True
    ):
        result = build_result(
            gamma=values,
            axes=reference_axes,
            eligible=eligible,
            settings=GammaSettings(
                dose_criterion_percent=dose,
                distance_criterion_mm=distance,
                normalisation=normalisation,
                normalisation_dose=float(options.global_normalisation),
                normalisation_dose_supplied=normalisation_dose is not None,
                lower_dose_cutoff_percent=lower_dose_cutoff_percent,
                lower_dose_cutoff=float(options.lower_dose_cutoff),
                exclude_nan_reference=bool(exclude_nan_reference),
                gamma_cap=gamma_cap,
                skip_once_passed=bool(skip_once_passed),
                random_subset=random_subset,
                random_source=random_source,
                random_seed=random_seed,
                method="shell",
                search_step_fraction=search_step_fraction,
                interpolator=str(options.interp_algo).lower(),
            ),
            provenance=provenance,
        )
        if result.analysed != selected:
            raise RuntimeError(
                f"{result.analysed} reference points have a gamma value, but "
                f"{selected} were selected for analysis."
            )
        results.append(result)

    if dose_is_list or distance_is_list:
        return tuple(results)

    return results[0]


# pymedphys.gamma is this function's public name, so that is the module that
# help() gives for it. The documentation tool then also shows its one real
# signature, where it would otherwise list each typing overload above.
gamma.__module__ = "pymedphys"
