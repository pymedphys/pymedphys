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

"""What pymedphys.gamma returns, and the options it accepts."""

import inspect
import warnings

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

import pymedphys
from pymedphys import GammaResult, gamma


def _field(shape=(30, 26), shift=2.0, noise=0.04, seed=1):
    rng = np.random.default_rng(seed)
    axes = tuple(np.arange(0.0, length) for length in shape)
    grids = np.meshgrid(*axes, indexing="ij")
    centre = [length / 2 for length in shape]
    width = (min(shape) / 5) ** 2

    squared_radius = sum((grid - c) ** 2 for grid, c in zip(grids, centre))
    shifted_squared_radius = (grids[0] - centre[0] - shift) ** 2 + sum(
        (grid - c) ** 2 for grid, c in zip(grids[1:], centre[1:])
    )
    reference = 100 * np.exp(-squared_radius / (2 * width))
    evaluation = 100 * np.exp(-shifted_squared_radius / (2 * width))
    evaluation = evaluation * (1 + noise * rng.standard_normal(shape))

    return axes, reference, axes, evaluation


def test_doubling_the_normalisation_dose_halves_the_percentages():
    # Percentages are of the normalisation dose, so 3% of 80 and 1.5% of 160
    # are the same dose criterion, and 10% and 5% the same cutoff.
    arguments = _field()

    result = gamma(
        *arguments, 3, 2, normalisation_dose=80.0, lower_dose_cutoff_percent=10
    )
    doubled = gamma(
        *arguments, 1.5, 2, normalisation_dose=160.0, lower_dose_cutoff_percent=5
    )

    assert doubled.settings.lower_dose_cutoff == result.settings.lower_dose_cutoff
    assert (doubled.passed, doubled.analysed) == (result.passed, result.analysed)
    assert 0 < result.passed < result.analysed
    np.testing.assert_allclose(doubled.gamma, result.gamma, rtol=1e-12, atol=0)


@pytest.mark.parametrize("normalisation", ["global", "local"])
def test_skipping_once_passed_bounds_gamma_without_changing_what_passes(
    normalisation,
):
    arguments = _field()

    searched = gamma(*arguments, 2, 2, normalisation=normalisation)
    skipped = gamma(
        *arguments, 2, 2, normalisation=normalisation, skip_once_passed=True
    )

    analysed = ~np.isnan(searched.gamma)
    np.testing.assert_array_equal(np.isnan(skipped.gamma), ~analysed)
    assert (skipped.passed, skipped.analysed) == (searched.passed, searched.analysed)
    assert 0 < searched.passed < searched.analysed
    # A search that stops early has seen fewer candidates, so its minimum is
    # an upper bound, and the search for a failing point never stops early.
    assert np.all(skipped.gamma[analysed] >= searched.gamma[analysed])
    assert np.any(skipped.gamma[analysed] > searched.gamma[analysed])
    failing = analysed & (searched.gamma > 1)
    np.testing.assert_array_equal(skipped.gamma[failing], searched.gamma[failing])
    assert skipped.settings.skip_once_passed is True


def test_result_carries_axes_counts_and_resolved_settings():
    axes_reference, reference, axes_evaluation, evaluation = _field()

    result = gamma(axes_reference, reference, axes_evaluation, evaluation, 2, 1.5)

    assert result.gamma.shape == reference.shape
    for stored, given in zip(result.axes, axes_reference):
        np.testing.assert_array_equal(stored, given)
        assert not np.shares_memory(stored, given)
    assert axes_reference[0].flags.writeable

    eligible = int(np.count_nonzero(reference >= 0.2 * reference.max()))
    assert result.eligible == result.analysed == eligible
    assert result.analysed == np.count_nonzero(~np.isnan(result.gamma))
    assert result.passed == np.count_nonzero(result.gamma <= 1)
    assert 0 < result.passed < result.analysed
    assert result.percent_passed == 100 * result.passed / result.analysed

    settings = result.settings
    assert (settings.dose_criterion_percent, settings.distance_criterion_mm) == (2, 1.5)
    assert settings.normalisation == "global"
    assert settings.normalisation_dose == reference.max()
    assert settings.normalisation_dose_supplied is False
    assert settings.lower_dose_cutoff_percent == 20
    assert settings.lower_dose_cutoff == 0.2 * reference.max()
    assert settings.gamma_cap is None
    assert settings.method == "shell"
    assert settings.search_step_fraction == 0.1
    assert settings.interpolator == "pymedphys"
    assert (settings.random_subset, settings.random_source, settings.random_seed) == (
        None,
        None,
        None,
    )
    assert "numpy" in result.provenance.versions


def test_supplied_normalisation_sets_the_cutoff_for_local_gamma():
    arguments = _field()

    result = gamma(
        *arguments,
        3,
        2,
        normalisation="local",
        normalisation_dose=50.0,
        lower_dose_cutoff_percent=40,
    )

    assert result.settings.normalisation == "local"
    assert result.settings.normalisation_dose == 50.0
    assert result.settings.normalisation_dose_supplied is True
    assert result.settings.lower_dose_cutoff == 20.0
    assert result.eligible == np.count_nonzero(arguments[1] >= 20.0)


def test_single_numbers_give_one_result_and_lists_give_a_tuple():
    arguments = _field()

    assert isinstance(gamma(*arguments, 3, 2), GammaResult)
    assert isinstance(gamma(*arguments, np.float64(3), np.int64(2)), GammaResult)

    for dose, distance in [([3], [2]), ([3], 2), (3, np.array([2.0])), ((3,), (2,))]:
        results = gamma(*arguments, dose, distance)
        assert isinstance(results, tuple) and len(results) == 1
        assert isinstance(results[0], GammaResult)


def test_list_results_are_in_order_and_equal_separate_calls():
    arguments = _field()

    results = gamma(*arguments, [3, 2], [3, 1.5, 1], gamma_cap=2)

    pairs = [
        (r.settings.dose_criterion_percent, r.settings.distance_criterion_mm)
        for r in results
    ]
    assert pairs == [(3, 3), (3, 1.5), (3, 1), (2, 3), (2, 1.5), (2, 1)]
    for result, (dose, distance) in zip(results, pairs):
        alone = gamma(*arguments, dose, distance, gamma_cap=2)
        np.testing.assert_array_equal(result.gamma, alone.gamma)
        assert (result.passed, result.analysed) == (alone.passed, alone.analysed)
        assert result.settings == alone.settings
    assert len({result.analysed for result in results}) == 1


def test_one_dimensional_axes_may_be_bare_arrays():
    axes_reference, reference, axes_evaluation, evaluation = _field((60,))

    result = gamma(axes_reference[0], reference, axes_evaluation[0], evaluation, 3, 2)

    assert len(result.axes) == 1
    np.testing.assert_array_equal(result.axes[0], axes_reference[0])


@pytest.mark.parametrize(
    ("random_state", "source", "seed"),
    [(11, "seed", 11), (np.int64(11), "seed", 11), (None, "global", None)],
)
def test_random_subset_is_recorded(random_state, source, seed):
    arguments = _field()

    result = gamma(*arguments, 3, 2, random_subset=40, random_state=random_state)

    assert result.analysed == 40
    assert result.eligible > 40
    settings = result.settings
    assert (settings.random_subset, settings.random_source, settings.random_seed) == (
        40,
        source,
        seed,
    )
    assert type(settings.random_seed) in (int, type(None))


def test_random_subset_from_a_generator_is_recorded():
    arguments = _field()

    result = gamma(
        *arguments, 3, 2, random_subset=40, random_state=np.random.default_rng(3)
    )
    seeded = gamma(*arguments, 3, 2, random_subset=40, random_state=3)

    assert result.settings.random_source == "generator"
    assert result.settings.random_seed is None
    np.testing.assert_array_equal(result.gamma, seeded.gamma)


def test_random_subset_larger_than_the_eligible_points_analyses_them_all():
    arguments = _field()

    result = gamma(*arguments, 3, 2, random_subset=10**6, random_state=0)

    assert result.settings.random_subset == 10**6
    assert result.analysed == result.eligible


def test_excluded_nan_reference_points_are_not_eligible():
    axes_reference, reference, axes_evaluation, evaluation = _field()
    reference = reference.copy()
    reference[15, 13] = np.nan

    result = gamma(
        axes_reference,
        reference,
        axes_evaluation,
        evaluation,
        3,
        2,
        exclude_nan_reference=True,
    )

    assert result.settings.exclude_nan_reference is True
    assert np.isnan(result.gamma[15, 13])
    with np.errstate(invalid="ignore"):
        expected = np.count_nonzero(reference >= 0.2 * np.nanmax(reference))
    assert result.eligible == result.analysed == expected


def test_no_analysed_points_warns_and_reports_zero_counts():
    arguments = _field()

    with pytest.warns(UserWarning, match="No reference point was analysed"):
        result = gamma(*arguments, 3, 2, normalisation_dose=1000.0)

    assert (result.passed, result.analysed, result.eligible) == (0, 0, 0)
    assert np.all(np.isnan(result.gamma))
    with pytest.raises(ValueError, match="No reference point was analysed"):
        _ = result.percent_passed


def test_warnings_name_the_line_that_called_gamma():
    arguments = _field()

    with pytest.warns(UserWarning, match="No reference point was analysed") as none:
        gamma(*arguments, 3, 2, normalisation_dose=1000.0)
    with pytest.warns(UserWarning, match="outside the evaluation grid") as outside:
        gamma(
            np.array([0.0, 1.0, 5.0]),
            np.ones(3),
            np.array([0.0, 1.0]),
            np.ones(2),
            [3, 2],
            3,
        )

    assert [warning.filename for warning in none] == [__file__]
    assert [warning.filename for warning in outside] == [__file__]


def test_the_calculation_chooses_an_interpolator_that_suits_the_axes():
    axes_reference, reference, _, evaluation = _field((40,))
    uneven = (np.cumsum(np.linspace(0.8, 1.2, 40)),)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        chosen = gamma(axes_reference, reference, uneven, evaluation, 3, 2)
        named = gamma(
            axes_reference, reference, uneven, evaluation, 3, 2, interpolator="scipy"
        )

    assert chosen.settings.interpolator == "scipy"
    np.testing.assert_array_equal(chosen.gamma, named.gamma)
    with pytest.raises(ValueError, match="not evenly spaced"):
        gamma(
            axes_reference,
            reference,
            uneven,
            evaluation,
            3,
            2,
            interpolator="pymedphys",
        )


def test_memory_budget_is_not_a_setting():
    arguments = _field()

    small = gamma(*arguments, 3, 2, memory_budget_bytes=2**16)
    default = gamma(*arguments, 3, 2)

    np.testing.assert_array_equal(small.gamma, default.gamma)
    assert small.settings == default.settings


def test_options_must_be_passed_by_keyword():
    arguments = _field()

    with pytest.raises(TypeError, match="positional"):
        gamma(*arguments, 3, 2, 20)  # type: ignore[misc]

    parameters = inspect.signature(gamma).parameters
    assert list(parameters)[:6] == [
        "axes_reference",
        "dose_reference",
        "axes_evaluation",
        "dose_evaluation",
        "dose_criterion_percent",
        "distance_criterion_mm",
    ]
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for parameter in list(parameters.values())[6:]
    )


def test_the_function_is_presented_under_its_public_name():
    # help() and the documentation name the module a user imports from.
    assert (gamma.__module__, gamma.__name__) == ("pymedphys", "gamma")
    assert pymedphys.gamma is gamma


INVALID_OPTIONS = [
    ({"dose": 0}, ValueError, "dose_criterion_percent"),
    ({"dose": -3}, ValueError, "dose_criterion_percent"),
    ({"dose": np.nan}, ValueError, "dose_criterion_percent"),
    ({"dose": []}, ValueError, "dose_criterion_percent"),
    ({"dose": [3, 2, 3]}, ValueError, "more than once"),
    ({"dose": [[3, 2]]}, ValueError, "dose_criterion_percent"),
    ({"dose": "3"}, TypeError, "dose_criterion_percent"),
    ({"dose": True}, TypeError, "dose_criterion_percent"),
    ({"distance": 0}, ValueError, "distance_criterion_mm"),
    ({"distance": np.inf}, ValueError, "distance_criterion_mm"),
    ({"distance": [2, 2.0]}, ValueError, "more than once"),
    ({"lower_dose_cutoff_percent": np.nan}, ValueError, "lower_dose_cutoff_percent"),
    ({"normalisation": "Local"}, ValueError, "normalisation"),
    ({"normalisation": True}, ValueError, "normalisation"),
    ({"normalisation_dose": 0}, ValueError, "normalisation_dose"),
    ({"normalisation_dose": np.inf}, ValueError, "normalisation_dose"),
    ({"gamma_cap": 1}, ValueError, "gamma_cap"),
    ({"gamma_cap": np.nan}, ValueError, "gamma_cap"),
    ({"random_subset": -1}, ValueError, "random_subset"),
    ({"random_subset": 2.5}, TypeError, "random_subset"),
    ({"random_subset": True}, TypeError, "random_subset"),
    ({"random_state": "7"}, TypeError, "random_state"),
    ({"random_state": [1, 2]}, TypeError, "random_state"),
    ({"random_state": -1}, ValueError, "random_state"),
    ({"search_step_fraction": 0}, ValueError, "search_step_fraction"),
    ({"search_step_fraction": 10}, ValueError, "search_step_fraction"),
    ({"search_step_fraction": np.nan}, ValueError, "search_step_fraction"),
    ({"interpolator": "linear"}, ValueError, "interpolator"),
    ({"memory_budget_bytes": 0}, ValueError, "memory_budget_bytes"),
    ({"memory_budget_bytes": 1.5}, TypeError, "memory_budget_bytes"),
]


@pytest.mark.parametrize(("changes", "error", "match"), INVALID_OPTIONS, ids=str)
def test_invalid_input_is_rejected_before_the_search(changes, error, match):
    arguments = _field((12, 10))
    changes = dict(changes)
    dose = changes.pop("dose", 3)
    distance = changes.pop("distance", 2)

    with pytest.raises(error, match=match):
        gamma(*arguments, dose, distance, **changes)
