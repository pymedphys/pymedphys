# Copyright (C) 2022-2026 Matthew Jennings
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


"""The shell search that :func:`pymedphys.gamma` calculates gamma with.

For each reference point the evaluation dose is interpolated on shells of
increasing radius. :mod:`pymedphys._gamma.calculate` checks the options that
users pass and builds the results; the names used here are internal.
"""

import logging
from dataclasses import dataclass
from functools import cached_property
from typing import Any, Optional

from pymedphys._imports import numpy as np
from pymedphys._imports import scipy

import pymedphys._utilities.createshells
from pymedphys._interp.interp import _interp_validated

from ..utilities import run_input_checks, warn_caller

DEFAULT_RAM = int(2**30 * 1.5)  # 1.5 GB

logger = logging.getLogger(__name__)


def calculate_gamma_arrays(
    options: "GammaInternalFixedOptions", shape, lower_percent_dose_cutoff
):
    """Run the search and return gamma on the reference grid for every pair.

    Returns a dict of arrays shaped ``shape``, keyed by ``(dose threshold,
    distance threshold)`` with the dose thresholds varying slowest. Reference
    points that were not analysed are NaN, and values above
    ``options.max_gamma`` are reported as ``options.max_gamma``.
    """
    logger.info(
        "Calculating gamma with %s normalisation",
        "local" if options.local_gamma else "global",
    )
    logger.info("Normalisation dose set to %.3f", options.global_normalisation)
    if options.local_gamma:
        logger.info(
            "Dose criterion set to %s%% of each reference point's dose",
            _listed(options.dose_percent_threshold),
        )
    else:
        logger.info(
            "Dose criterion set to %s (%s%% of the normalisation dose)",
            _listed(options.global_dose_threshold),
            _listed(options.dose_percent_threshold),
        )

    logger.info("Distance criterion set to %s", _listed(options.distance_mm_threshold))
    logger.info(
        "Lower dose cutoff set to %.3f (%.1f%% of the normalisation dose)",
        options.lower_dose_cutoff,
        lower_percent_dose_cutoff,
    )

    current_gamma = gamma_loop(options)

    gamma = {}
    for i, dose_threshold in enumerate(options.dose_percent_threshold):
        for j, distance_threshold in enumerate(options.distance_mm_threshold):
            key = (dose_threshold, distance_threshold)

            gamma_temp = current_gamma[:, i, j]
            gamma_temp = np.reshape(gamma_temp, shape)
            # Only points that were not analysed are still infinite.
            gamma_temp[np.isinf(gamma_temp)] = np.nan

            with np.errstate(invalid="ignore"):
                gamma_greater_than_ref = gamma_temp > options.max_gamma
                gamma_temp[gamma_greater_than_ref] = options.max_gamma

            gamma[key] = gamma_temp

    logger.info("Complete!")

    return gamma


def _listed(values):
    """Numbers as text for a log message: ``3, 2`` for the array [3.0, 2.0]."""
    return ", ".join(f"{value:g}" for value in np.atleast_1d(values))


def expand_dims_to_1d(array):
    array = np.array(array)
    dims = len(np.shape(array))

    if dims == 0:
        return array[None]

    if dims == 1:
        return array

    raise ValueError("Expected a 0-d or 1-d array")


def _prepare_evaluation_grid(
    axes_evaluation, dose_evaluation, interp_algo, uneven_axes="raise"
):
    """Return the evaluation grid as the interpolators require it.

    Each axis becomes a contiguous, strictly ascending float64 array, with
    the dose flipped along any axis that was descending, so that grids
    stored in either order (as DICOM data often is) give the same gamma.
    The reference grid is left as given, because gamma is returned on it.

    The 'pymedphys' interpolator needs evenly spaced axes. ``uneven_axes``
    says what to do when it was asked for and they are not: ``"switch"``
    uses the 'scipy' interpolator instead, and ``"raise"`` raises
    ``ValueError``.
    """
    if uneven_axes not in ("switch", "raise"):
        raise ValueError(
            f'uneven_axes must be "switch" or "raise", not {uneven_axes!r}'
        )

    axes = [np.asarray(axis, dtype=np.float64) for axis in axes_evaluation]
    dose = np.asarray(dose_evaluation, dtype=np.float64)

    for dimension, axis in enumerate(axes):
        if axis.ndim != 1 or axis.size == 0 or not np.all(np.isfinite(axis)):
            raise ValueError(
                f"Evaluation axis {dimension} must be a non-empty finite 1D array"
            )
        if axis.size == 1:
            # A fixed coordinate: the grid is a plane, line or point there.
            continue
        diff = np.diff(axis)
        if np.all(diff < 0):
            axes[dimension] = axis[::-1]
            dose = np.flip(dose, axis=dimension)
        elif not np.all(diff > 0):
            raise ValueError(
                f"Evaluation axis {dimension} must be strictly ascending or "
                "strictly descending"
            )

    is_uneven = any(
        axis.size > 1 and not np.allclose(np.diff(axis), axis[1] - axis[0])
        for axis in axes
    )
    if is_uneven and interp_algo.lower() == "pymedphys":
        if uneven_axes == "raise":
            raise ValueError(
                "The evaluation axes are not evenly spaced, which the "
                "'pymedphys' interpolator requires. Pass interpolator='scipy', "
                "or leave interpolator out so that the calculation chooses."
            )
        interp_algo = "scipy"

    axes = tuple(np.ascontiguousarray(axis) for axis in axes)

    return axes, np.ascontiguousarray(dose), interp_algo


def _grid_distance_bounds(axes_reference, axes_evaluation):
    """Bounds on distances between reference and evaluation points.

    Disjoint grids can have valid gamma values. Shells below the lower bound
    or above the upper bound cannot intersect the evaluation grid. The upper
    bound also ensures termination when no finite candidate is sampled.
    """
    nearest, farthest = [], []
    for dimension, (reference, evaluation) in enumerate(
        zip(axes_reference, axes_evaluation)
    ):
        reference = np.asarray(reference)
        if (
            reference.ndim != 1
            or reference.size == 0
            or not np.all(np.isfinite(reference))
        ):
            raise ValueError(
                f"Reference axis {dimension} must be a non-empty finite 1D array"
            )
        reference_min, reference_max = np.min(reference), np.max(reference)
        nearest.append(
            max(evaluation[0] - reference_max, reference_min - evaluation[-1], 0)
        )
        farthest.append(
            max(
                abs(reference_min - evaluation[-1]),
                abs(reference_max - evaluation[0]),
            )
        )

    return np.linalg.norm(nearest), np.linalg.norm(farthest)


def _nearest_grid_points(flat_mesh_axes_reference, index, axes_evaluation):
    """The nearest point of the evaluation grid's extent to each reference point.

    Returns the points that ``index`` selects, clipped to the grid's extent,
    with shape ``(points, dimensions)``.
    """
    return np.stack(
        [
            np.clip(coords[index], axis[0], axis[-1])
            for coords, axis in zip(flat_mesh_axes_reference, axes_evaluation)
        ],
        axis=-1,
    )


def _distance_outside_grid(flat_mesh_axes_reference, index, axes_evaluation):
    """Distance from each reference point that ``index`` selects to the
    evaluation grid's extent, zero inside it.

    Summed one dimension at a time to limit memory on large grids.
    """
    squared_distance = np.zeros(len(index))
    for coords, axis in zip(flat_mesh_axes_reference, axes_evaluation):
        coords = coords[index]
        squared_distance += (coords - np.clip(coords, axis[0], axis[-1])) ** 2
    return np.sqrt(squared_distance)


def _check_finite_doses(dose_reference, dose_evaluation, exclude_nan_reference):
    """Reject doses gamma cannot use, saying how to express the intent."""
    if np.any(np.isinf(dose_reference)):
        raise ValueError("dose_reference must be finite, but contains infinite values.")

    if not exclude_nan_reference and np.any(np.isnan(dose_reference)):
        raise ValueError(
            "dose_reference must be finite, but contains NaN values. To leave "
            "those reference points out of the analysis, pass "
            "exclude_nan_reference=True; they are then reported as NaN."
        )

    if np.all(np.isnan(dose_reference)):
        raise ValueError("dose_reference has no finite values to analyse.")

    if not np.all(np.isfinite(dose_evaluation)):
        raise ValueError(
            "dose_evaluation must be finite, but contains NaN or infinite "
            "values. Gamma searches the evaluation dose between grid points, "
            "so it cannot skip missing values. Crop the evaluation grid to "
            "the region with valid dose. If the missing values are "
            "unmeasured points, use the measurement as the reference instead, "
            "with exclude_nan_reference=True."
        )


def _warn_about_points_outside_the_grid(
    flat_mesh_axes_reference, reference_points_to_calc, axes_evaluation, resolution
):
    analysed = np.count_nonzero(reference_points_to_calc)
    if analysed == 0:
        return

    distance = _distance_outside_grid(
        flat_mesh_axes_reference,
        np.flatnonzero(reference_points_to_calc),
        axes_evaluation,
    )
    outside = np.count_nonzero(distance > resolution)
    if outside == 0:
        return

    warn_caller(
        f"{outside} of {analysed} analysed reference points "
        f"({100 * outside / analysed:.1f}%) lie more than one search step "
        f"({resolution:.3g}) outside the evaluation grid. Each is compared "
        "with the evaluation data up to the grid's edge, so these points may "
        "fail. To analyse only the region the evaluation grid covers, crop "
        "the reference grid to it."
    )


@dataclass(frozen=True)
class GammaInternalFixedOptions:
    axes_evaluation: Any
    dose_evaluation: Any
    flat_mesh_axes_reference: Any
    flat_dose_reference: Any
    reference_points_to_calc: Any
    dose_percent_threshold: Any
    distance_mm_threshold: Any
    interp_fraction: int
    max_gamma: float
    lower_dose_cutoff: float = 0
    maximum_test_distance: float = -1
    global_normalisation: Optional[float] = None
    local_gamma: bool = False
    skip_once_passed: bool = False
    ram_available: Optional[int] = DEFAULT_RAM
    interp_algo: str = "pymedphys"
    minimum_test_distance: float = 0.0
    # Evaluation axes with more than one value. The search runs over these
    # only; singleton axes fix a coordinate of a plane, line or point.
    free_axes: Optional[tuple] = None
    # Each reference point's distance from the fixed coordinates, or None
    # when every evaluation axis is free.
    flat_perpendicular_distance: Any = None

    def __post_init__(self):
        self.set_defaults()

    def set_defaults(self):
        if self.free_axes is None:
            object.__setattr__(
                self, "free_axes", tuple(range(len(self.axes_evaluation)))
            )

        if self.maximum_test_distance == -1:
            object.__setattr__(self, "maximum_test_distance", np.inf)

        if self.global_normalisation is None:
            object.__setattr__(
                self, "global_normalisation", np.max(self.flat_dose_reference)
            )

    @property
    def global_dose_threshold(self):
        return self.dose_percent_threshold / 100 * self.global_normalisation

    @property
    def free_axes_evaluation(self):
        return tuple(self.axes_evaluation[axis] for axis in self.free_axes)

    @cached_property
    def free_dose_evaluation(self):
        """The evaluation dose over the free axes alone.

        Singleton axes have one value each, so dropping them is a reshape.
        """
        shape = tuple(axis.size for axis in self.free_axes_evaluation)
        return np.ascontiguousarray(np.reshape(self.dose_evaluation, shape))

    @cached_property
    def scipy_interpolator(self):
        """Reuse the fixed evaluation grid across every shell and RAM chunk."""
        return scipy.interpolate.RegularGridInterpolator(
            self.free_axes_evaluation,
            self.free_dose_evaluation,
            bounds_error=False,
            fill_value=np.inf,
        )

    @classmethod
    def from_user_inputs(
        cls,
        axes_reference,
        dose_reference,
        axes_evaluation,
        dose_evaluation,
        dose_percent_threshold,
        distance_mm_threshold,
        *,
        lower_percent_dose_cutoff=20,
        interp_fraction=10,
        max_gamma=None,
        local_gamma=False,
        global_normalisation=None,
        skip_once_passed=False,
        random_subset=None,
        ram_available=None,
        interp_algo="pymedphys",
        random_state=None,
        exclude_nan_reference=False,
        uneven_axes="raise",
    ):
        """Check the grids and work out everything the search needs.

        The options have the names the search uses. Messages name them as
        :func:`pymedphys.gamma` does, because that is what its callers pass:
        ``max_gamma`` is its ``gamma_cap``, ``global_normalisation`` its
        ``normalisation_dose``, ``lower_percent_dose_cutoff`` its
        ``lower_dose_cutoff_percent``, ``interp_fraction`` one divided by its
        ``search_step_fraction``, ``local_gamma`` its ``normalisation``,
        ``ram_available`` its ``memory_budget_bytes``, and ``interp_algo``
        its ``interpolator``.
        """
        if max_gamma is None:
            max_gamma = np.inf

        if ram_available is None:
            ram_available = DEFAULT_RAM

        if np.isnan(max_gamma) or max_gamma <= 1:
            raise ValueError(
                "gamma_cap must be greater than 1. Gamma values above it are "
                "reported as the cap, so a smaller cap would report failing "
                "points as passing."
            )

        axes_reference, axes_evaluation = run_input_checks(
            axes_reference, dose_reference, axes_evaluation, dose_evaluation
        )
        _check_finite_doses(dose_reference, dose_evaluation, exclude_nan_reference)
        axes_evaluation, dose_evaluation, interp_algo = _prepare_evaluation_grid(
            axes_evaluation, dose_evaluation, interp_algo, uneven_axes
        )

        dose_percent_threshold = expand_dims_to_1d(dose_percent_threshold)
        distance_mm_threshold = expand_dims_to_1d(distance_mm_threshold)

        normalisation_is_default = global_normalisation is None
        if normalisation_is_default:
            global_normalisation = np.nanmax(dose_reference)

        if not (np.isfinite(global_normalisation) and global_normalisation > 0):
            if normalisation_is_default:
                raise ValueError(
                    "normalisation_dose defaults to the maximum reference dose, "
                    f"which is {global_normalisation}, but it must be finite "
                    "and greater than zero. Check dose_reference, or pass "
                    "normalisation_dose."
                )
            raise ValueError(
                "normalisation_dose must be finite and greater than zero, but "
                f"got {global_normalisation}."
            )

        lower_dose_cutoff = lower_percent_dose_cutoff / 100 * global_normalisation

        # Validates every reference axis; the search itself only moves
        # within the free evaluation axes.
        _grid_distance_bounds(axes_reference, axes_evaluation)
        free_axes = tuple(
            axis for axis, values in enumerate(axes_evaluation) if values.size > 1
        )
        minimum_test_distance, spatial_limit = _grid_distance_bounds(
            [axes_reference[axis] for axis in free_axes],
            [axes_evaluation[axis] for axis in free_axes],
        )
        maximum_test_distance = min(
            np.max(distance_mm_threshold) * max_gamma, spatial_limit
        )

        dose_reference = np.array(dose_reference)
        reference_dose_above_threshold = dose_reference >= lower_dose_cutoff

        mesh_axes_reference = np.meshgrid(*axes_reference, indexing="ij")
        flat_mesh_axes_reference = np.array(
            [np.ravel(item) for item in mesh_axes_reference]
        )

        flat_perpendicular_distance = None
        if len(free_axes) < len(axes_evaluation):
            squared_distance = np.zeros(flat_mesh_axes_reference.shape[1])
            for axis, values in enumerate(axes_evaluation):
                if axis not in free_axes:
                    squared_distance += (
                        flat_mesh_axes_reference[axis] - values[0]
                    ) ** 2
            flat_perpendicular_distance = np.sqrt(squared_distance)

        reference_points_to_calc = reference_dose_above_threshold
        reference_points_to_calc = np.ravel(reference_points_to_calc)

        if random_subset is not None:
            to_calc_index = np.where(reference_points_to_calc)[0]

            if random_state is None:
                np.random.shuffle(to_calc_index)
            else:
                to_calc_index = np.random.default_rng(random_state).permutation(
                    to_calc_index
                )
            random_subset_to_calc = np.full_like(
                reference_points_to_calc, False, dtype=bool
            )
            random_subset_to_calc[  # pylint: disable=unsupported-assignment-operation
                to_calc_index[0:random_subset]
            ] = True

            reference_points_to_calc = random_subset_to_calc

        flat_dose_reference = np.ravel(dose_reference)

        if local_gamma and np.any(flat_dose_reference[reference_points_to_calc] == 0):
            raise ValueError(
                "Local normalisation is undefined where the reference dose is "
                "zero, and some analysed reference points have zero dose. Raise "
                "lower_dose_cutoff_percent above zero to exclude them."
            )

        _warn_about_points_outside_the_grid(
            flat_mesh_axes_reference,
            reference_points_to_calc,
            axes_evaluation,
            resolution=np.min(distance_mm_threshold) / interp_fraction,
        )

        return cls(
            axes_evaluation=axes_evaluation,
            dose_evaluation=dose_evaluation,
            flat_mesh_axes_reference=flat_mesh_axes_reference,
            flat_dose_reference=flat_dose_reference,
            reference_points_to_calc=reference_points_to_calc,
            dose_percent_threshold=dose_percent_threshold,
            distance_mm_threshold=distance_mm_threshold,
            interp_fraction=interp_fraction,
            max_gamma=max_gamma,
            lower_dose_cutoff=lower_dose_cutoff,
            maximum_test_distance=maximum_test_distance,
            global_normalisation=global_normalisation,
            local_gamma=local_gamma,
            skip_once_passed=skip_once_passed,
            ram_available=ram_available,
            interp_algo=interp_algo,
            minimum_test_distance=minimum_test_distance,
            free_axes=free_axes,
            flat_perpendicular_distance=flat_perpendicular_distance,
        )


def gamma_loop(options: GammaInternalFixedOptions):
    """Gamma for every combination of dose and distance threshold.

    Returns an array shaped ``(reference points, dose thresholds, distance
    thresholds)``. Each distance threshold has a search of its own, at its
    own step, so the gamma for a combination is what a call with that pair
    alone gives, whatever else was requested with it. The dose thresholds
    share each search, which is what makes a list of them cheaper than
    separate calls.
    """
    current_gamma = np.empty(
        (
            len(options.flat_dose_reference),
            len(options.dose_percent_threshold),
            len(options.distance_mm_threshold),
        )
    )
    for index, distance_mm_threshold in enumerate(options.distance_mm_threshold):
        current_gamma[:, :, index] = _gamma_loop_for_one_distance(
            options, distance_mm_threshold
        )

    return current_gamma


def _gamma_loop_for_one_distance(
    options: GammaInternalFixedOptions, distance_mm_threshold
):
    """Search with one distance threshold and every dose threshold.

    Returns an array shaped ``(reference points, dose thresholds)``.
    """
    current_gamma = np.full(
        (len(options.flat_dose_reference), len(options.dose_percent_threshold)),
        np.inf,
    )
    current_gamma = gamma_at_nearest_grid_points(
        options, current_gamma, distance_mm_threshold
    )

    if not options.free_axes:
        # A single evaluation point: its gamma is the only candidate.
        return current_gamma

    maximum_test_distance = min(
        distance_mm_threshold * options.max_gamma, options.maximum_test_distance
    )
    distance_step_size = distance_mm_threshold / options.interp_fraction

    still_searching_for_gamma = np.full(current_gamma.shape, True)
    to_be_checked = options.reference_points_to_calc

    distance = options.minimum_test_distance

    # Include the spatial endpoint even when it is not a multiple of the
    # interpolation step; it can be the only sampled evaluation point.
    force_search_distances = np.unique([distance_mm_threshold, maximum_test_distance])
    force_search_distances = force_search_distances[force_search_distances > distance]
    while distance <= maximum_test_distance:
        logger.debug(
            "Current distance: %.2f mm | Number of reference points remaining: %i",
            distance,
            np.sum(to_be_checked),
        )

        min_relative_dose_difference = calculate_min_dose_difference(
            options, distance, to_be_checked, distance_step_size
        )

        current_gamma, still_searching_for_gamma = multi_thresholds_gamma_calc(
            options,
            current_gamma,
            min_relative_dose_difference,
            distance,
            to_be_checked,
            distance_mm_threshold,
            still_searching_for_gamma,
        )

        to_be_checked = options.reference_points_to_calc & np.any(
            still_searching_for_gamma, axis=-1
        )

        if np.sum(to_be_checked) == 0:
            break

        distance_step_size = np.max(
            [
                distance / options.interp_fraction / options.max_gamma,
                distance_mm_threshold / options.interp_fraction,
            ]
        )

        distance += distance_step_size
        if len(force_search_distances) != 0:
            if distance >= force_search_distances[0]:
                distance = force_search_distances[0]
                force_search_distances = np.delete(force_search_distances, 0)

    if not np.all(np.isfinite(current_gamma[options.reference_points_to_calc])):
        raise RuntimeError("Gamma was not found for every analysed reference point")

    return current_gamma


def gamma_at_nearest_grid_points(
    options: GammaInternalFixedOptions, current_gamma, distance_mm_threshold
):
    """Bound gamma at points outside the evaluation grid.

    The nearest point of the evaluation grid's extent is always a candidate,
    so every analysed reference point gets a gamma value, even where the search
    shells cannot sample the grid: a grid narrower than one search step, a
    singleton plane, or a grid more than ``max_gamma`` times the distance
    threshold away. The shells then search for any lower value. Points inside
    the grid are their own nearest point, which the zero-distance shell
    samples, so they are left to the search.
    """
    analysed = np.where(options.reference_points_to_calc)[0]
    distance = _distance_outside_grid(
        options.flat_mesh_axes_reference, analysed, options.axes_evaluation
    )
    # Points inside the grid are sampled by the zero-radius shell, unless
    # the grid is a single point, which has no shells.
    outside = distance > 0 if options.free_axes else np.full(distance.shape, True)
    analysed, distance = analysed[outside], distance[outside]
    if analysed.size == 0:
        return current_gamma

    num_dimensions = len(options.axes_evaluation)
    estimated_ram_needed = analysed.size * 32 * num_dimensions * 2
    num_slices = int(estimated_ram_needed // options.ram_available) + 1

    for current_slice in np.array_split(np.arange(analysed.size), num_slices):
        indices = analysed[current_slice]
        nearest = _nearest_grid_points(
            options.flat_mesh_axes_reference, indices, options.axes_evaluation
        )
        evaluation_dose = interpolate_evaluation_dose(
            options, nearest[None][..., list(options.free_axes or ())]
        )
        relative_dose_difference = np.abs(
            calculate_relative_dose_difference(options, evaluation_dose, indices)[0]
        )
        gamma_at_edge = np.sqrt(
            (
                relative_dose_difference[:, None]
                / (options.dose_percent_threshold[None, :] / 100)
            )
            ** 2
            + (distance[current_slice, None] / distance_mm_threshold) ** 2
        )
        current_gamma[indices] = np.minimum(current_gamma[indices], gamma_at_edge)

    return current_gamma


def multi_thresholds_gamma_calc(
    options: GammaInternalFixedOptions,
    current_gamma,
    min_relative_dose_difference,
    distance,
    to_be_checked,
    distance_mm_threshold,
    still_searching_for_gamma,
):
    """Update gamma for one shell and say which combinations keep searching.

    ``current_gamma`` and ``still_searching_for_gamma`` are shaped
    ``(reference points, dose thresholds)``. A combination that has stopped
    searching is left as it is, even while another dose threshold keeps its
    reference point in the search, so its gamma is what a call with that
    pair alone gives.
    """
    # The shell radius lies within the free axes. Off a plane, line or
    # point, the perpendicular distance adds in quadrature; hypot(r, 0) is
    # exactly r, so free-only grids are unaffected.
    if options.flat_perpendicular_distance is None:
        total_distance = np.full(len(options.flat_dose_reference), distance)
    else:
        total_distance = np.hypot(distance, options.flat_perpendicular_distance)
    total_distance = total_distance[:, None]

    gamma_at_distance = np.sqrt(
        (
            min_relative_dose_difference[:, None]
            / (options.dose_percent_threshold[None, :] / 100)
        )
        ** 2
        + (total_distance[to_be_checked] / distance_mm_threshold) ** 2
    )

    current_gamma[to_be_checked] = np.where(
        still_searching_for_gamma[to_be_checked],
        np.minimum(gamma_at_distance, current_gamma[to_be_checked]),
        current_gamma[to_be_checked],
    )

    still_searching_for_gamma = still_searching_for_gamma & (
        current_gamma > total_distance / distance_mm_threshold
    )

    if options.skip_once_passed:
        still_searching_for_gamma = still_searching_for_gamma & (current_gamma >= 1)

    return current_gamma, still_searching_for_gamma


def calculate_min_dose_difference(options, distance, to_be_checked, distance_step_size):
    """Determine the minimum dose difference.

    Calculated for a given distance from each reference point.
    """

    min_relative_dose_difference = np.nan * np.ones_like(
        options.flat_dose_reference[to_be_checked]
    )

    num_dimensions = len(options.free_axes)

    coordinates_at_distance_shell = (
        pymedphys._utilities.createshells.calculate_coordinates_shell(  # pylint: disable = protected-access
            distance, num_dimensions, distance_step_size
        )
    )

    num_points_in_shell = np.shape(coordinates_at_distance_shell)[1]

    estimated_ram_needed = (
        np.uint64(num_points_in_shell)
        * np.uint64(np.count_nonzero(to_be_checked))
        * np.uint64(32)
        * np.uint64(num_dimensions)
        * np.uint64(2)
    )

    num_slices = np.floor(estimated_ram_needed / options.ram_available).astype(int) + 1

    logger.debug(
        "Points tested per reference point: %i | RAM split count: %i",
        num_points_in_shell,
        num_slices,
    )

    all_checks = np.where(np.ravel(to_be_checked))[0]
    index = np.arange(len(all_checks))
    sliced = np.array_split(index, num_slices)

    sorted_sliced = [np.sort(current_slice) for current_slice in sliced]

    for current_slice in sorted_sliced:
        to_be_checked_sliced = np.full_like(to_be_checked, False, dtype=bool)
        to_be_checked_sliced[  # pylint: disable=unsupported-assignment-operation
            all_checks[current_slice]
        ] = True

        assert np.all(to_be_checked[to_be_checked_sliced])

        axes_reference_to_be_checked = options.flat_mesh_axes_reference[
            np.ix_(options.free_axes, to_be_checked_sliced)
        ]

        evaluation_dose = interpolate_evaluation_dose_at_distance(
            options,
            axes_reference_to_be_checked,
            coordinates_at_distance_shell,
        )
        relative_dose_difference = calculate_relative_dose_difference(
            options, evaluation_dose, to_be_checked_sliced
        )

        min_relative_dose_difference[current_slice] = np.min(
            np.abs(relative_dose_difference), axis=0
        )

    return min_relative_dose_difference


def calculate_relative_dose_difference(options, evaluation_dose, reference_index):
    """Dose differences relative to the global or local normalisation.

    ``evaluation_dose`` has a trailing axis over the reference points that
    ``reference_index`` selects. Local gamma inputs were checked for zero
    reference dose, and evaluation dose outside the grid is infinite.
    """
    reference_dose = options.flat_dose_reference[reference_index][None, :]
    normalisation = (
        reference_dose if options.local_gamma else options.global_normalisation
    )

    return (evaluation_dose - reference_dose) / normalisation


def interpolate_evaluation_dose_at_distance(
    options,
    axes_reference_to_be_checked,
    coordinates_at_distance_shell,
):
    """Determine the evaluation dose for the points a given distance away for
    each reference coordinate.
    """
    all_points = add_shells_to_ref_coords(
        axes_reference_to_be_checked, coordinates_at_distance_shell
    )

    return interpolate_evaluation_dose(options, all_points)


def interpolate_evaluation_dose(options, all_points):
    """Interpolate the evaluation dose at points shaped ``(..., free axes)``.

    Points give coordinates on the free evaluation axes only. Points outside
    the evaluation grid are given infinite dose.
    """
    if not options.free_axes:
        return np.full(all_points.shape[:-1], options.dose_evaluation.item())

    if options.interp_algo.lower() == "pymedphys":
        evaluation_dose = _run_custom_interp(options, all_points)
    elif options.interp_algo.lower() == "scipy":
        evaluation_dose = _run_interp_with_scipy(options, all_points)
    else:
        raise ValueError(
            f"Interpolation algorithm '{options.interp_algo}' not recognised"
        )
    return evaluation_dose


def _run_custom_interp(options, all_points):
    # add_shells_to_ref_coords returns contiguous points, so this is a view.
    points = all_points.reshape(-1, all_points.shape[-1])

    # _prepare_evaluation_grid has already validated and normalised these
    # arrays. Reuse that guarantee throughout the shell/chunk loop.
    return _interp_validated(
        axes_known=options.free_axes_evaluation,
        values=options.free_dose_evaluation,
        points_interp=points,
        extrap_fill_value=np.inf,
    ).reshape(all_points.shape[:-1])


def _run_interp_with_scipy(options, all_points):
    return options.scipy_interpolator(all_points)


def add_shells_to_ref_coords(
    axes_reference_to_be_checked, coordinates_at_distance_shell
):
    """Add the distance shells to each reference coordinate to make a set of
    points to be tested for this given distance"""

    coordinates_at_distance = []
    for shell_coord, ref_coord in zip(
        coordinates_at_distance_shell, axes_reference_to_be_checked
    ):
        coordinates_at_distance.append(
            np.array(ref_coord[None, :] + shell_coord[:, None])[:, :, None]
        )

    all_points = np.concatenate(coordinates_at_distance, axis=2)

    return all_points
