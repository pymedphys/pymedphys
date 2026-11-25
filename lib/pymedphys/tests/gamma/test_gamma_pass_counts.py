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

"""Counting analysed and passing points, and reproducible random subsets."""

import dataclasses

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

import pymedphys
from pymedphys import GammaPassCounts, gamma_pass_counts, gamma_percent_passed


def test_counts_of_a_gamma_calculation():
    axis = np.arange(5.0)
    reference = np.array([0.1, 1.0, 1.0, 1.0, 1.0])
    evaluation = np.array([0.1, 1.0, 1.02, 1.05, 1.0])
    result = pymedphys.gamma(axis, reference, axis, evaluation, 3, 0.1)
    gamma = result.gamma

    # The first point is below the cutoff; 1.05 fails even at its neighbours.
    assert np.isnan(gamma[0])
    assert gamma_pass_counts(gamma) == GammaPassCounts(passed=3, analysed=4)
    assert gamma_percent_passed(gamma) == pytest.approx(75)
    # The result reports the counts of its own array.
    assert (result.passed, result.analysed) == (3, 4)
    assert result.percent_passed == pytest.approx(75)


def test_nan_reference_points_left_out_of_gamma_are_not_counted():
    axis = np.arange(5.0)
    reference = np.array([np.nan, 1.0, 1.0, 1.0, 1.0])
    evaluation = np.array([1.0, 1.0, 1.02, 1.05, 1.0])
    result = pymedphys.gamma(
        axis, reference, axis, evaluation, 3, 0.1, exclude_nan_reference=True
    )
    gamma = result.gamma

    assert np.isnan(gamma[0])
    assert gamma_pass_counts(gamma) == GammaPassCounts(passed=3, analysed=4)
    assert gamma_percent_passed(gamma) == pytest.approx(75)
    assert (result.passed, result.analysed, result.eligible) == (3, 4, 4)


def test_gamma_of_exactly_one_passes():
    # NaN points were not evaluated, so they are not counted.
    gamma = np.array([0.5, 1.0, np.nextafter(1.0, 2.0), np.nan])
    assert gamma_pass_counts(gamma) == GammaPassCounts(passed=2, analysed=3)
    assert gamma_percent_passed(gamma) == pytest.approx(100 * 2 / 3)


def test_counts_accept_any_array_shape():
    gamma = [[0.2, 1.5], [np.nan, 0.9]]
    assert gamma_pass_counts(gamma) == GammaPassCounts(passed=2, analysed=3)
    assert gamma_percent_passed(gamma) == pytest.approx(100 * 2 / 3)


def test_masked_points_are_not_counted():
    # Counting the masked 3.0 would give 1 pass in 3 points.
    gamma = np.ma.masked_array(
        [0.5, 2.0, 3.0, np.nan], mask=[False, False, True, False]
    )
    assert gamma_pass_counts(gamma) == GammaPassCounts(passed=1, analysed=2)
    assert gamma_percent_passed(gamma) == pytest.approx(50)


def test_infinite_gamma_fails():
    assert gamma_pass_counts([0.5, np.inf]) == GammaPassCounts(passed=1, analysed=2)
    assert gamma_percent_passed([0.5, np.inf]) == pytest.approx(50)


def test_negative_zero_is_accepted():
    assert gamma_pass_counts([-0.0, 2.0]) == GammaPassCounts(passed=1, analysed=2)


@pytest.mark.parametrize("function", [gamma_pass_counts, gamma_percent_passed])
@pytest.mark.parametrize("negative", [-0.5, -np.inf])
def test_negative_gamma_is_rejected(function, negative):
    with pytest.raises(ValueError, match="Gamma cannot be negative"):
        function([0.5, negative])


@pytest.mark.parametrize("function", [gamma_pass_counts, gamma_percent_passed])
def test_results_are_rejected_in_favour_of_their_arrays(function):
    axis = np.arange(5.0)
    dose = np.ones(5)
    results = pymedphys.gamma(axis, dose, axis, dose, [2, 3], 3)

    with pytest.raises(TypeError, match=r"result\.gamma"):
        function(results)
    with pytest.raises(TypeError, match=r"result\.gamma"):
        function(results[0])
    assert gamma_percent_passed(results[0].gamma) == pytest.approx(100)


@pytest.mark.parametrize("function", [gamma_pass_counts, gamma_percent_passed])
def test_a_mapping_of_arrays_is_rejected(function):
    with pytest.raises(TypeError, match="one array at a time"):
        function({"target": np.array([0.5, 2.0])})


NO_ANALYSED_POINTS = [
    np.array([np.nan, np.nan]),
    np.array([]),
    np.ma.masked_array([0.5, np.nan], mask=[True, False]),
]


@pytest.mark.parametrize("gamma", NO_ANALYSED_POINTS)
def test_no_analysed_points_gives_zero_counts(gamma):
    assert gamma_pass_counts(gamma) == GammaPassCounts(passed=0, analysed=0)


@pytest.mark.parametrize("gamma", NO_ANALYSED_POINTS)
def test_percentage_without_analysed_points_is_rejected(gamma):
    with pytest.raises(ValueError, match="No reference point was analysed"):
        gamma_percent_passed(gamma)
    with pytest.raises(ValueError, match="No reference point was analysed"):
        _ = gamma_pass_counts(gamma).percent_passed


def test_percent_passed_is_out_of_one_hundred():
    counts = GammaPassCounts(passed=19, analysed=20)
    assert counts.percent_passed == pytest.approx(95)
    assert GammaPassCounts(passed=0, analysed=7).percent_passed == 0
    assert GammaPassCounts(passed=7, analysed=7).percent_passed == 100


@pytest.mark.parametrize(
    ("passed", "analysed", "percent"),
    [
        (np.uint8(19), np.uint8(20), 95),
        (np.int8(2), np.int8(3), 100 * 2 / 3),
        (np.int32(30_000_000), np.int32(40_000_000), 75),
    ],
    ids=["uint8", "int8", "int32"],
)
def test_percent_passed_of_numpy_integer_counts(passed, analysed, percent):
    # 100 times each of these counts overflows its NumPy integer type.
    counts = GammaPassCounts(passed=passed, analysed=analysed)
    assert counts.percent_passed == pytest.approx(percent)


@pytest.mark.parametrize(
    ("passed", "analysed"), [(-1, 3), (4, 3), (0, -1), (1.5, 3), (True, 3)]
)
def test_inconsistent_counts_are_rejected(passed, analysed):
    with pytest.raises((TypeError, ValueError)):
        GammaPassCounts(passed=passed, analysed=analysed)


def test_counts_cannot_be_changed():
    counts = GammaPassCounts(passed=1, analysed=2)
    with pytest.raises(dataclasses.FrozenInstanceError):
        counts.passed = 2  # type: ignore[misc]


def test_counts_are_plain_integers():
    counts = gamma_pass_counts(np.array([0.5, 2.0], dtype=np.float32))
    assert [type(counts.passed), type(counts.analysed)] == [int, int]


def _subset(**kwargs):
    axis = np.arange(50.0)
    dose = np.ones(50)
    result = pymedphys.gamma(axis, dose, axis, dose, 3, 3, random_subset=10, **kwargs)
    return ~np.isnan(result.gamma)


def test_random_subset_selects_the_requested_number_of_points():
    assert np.count_nonzero(_subset(random_state=0)) == 10


@pytest.mark.parametrize("seed", [0, 12345])
def test_random_state_seed_reproduces_the_subset(seed):
    np.testing.assert_array_equal(
        _subset(random_state=seed), _subset(random_state=seed)
    )
    np.testing.assert_array_equal(
        _subset(random_state=np.random.default_rng(seed)), _subset(random_state=seed)
    )


def test_random_state_is_independent_of_numpys_global_seed():
    np.random.seed(1)
    first = _subset(random_state=7)
    np.random.seed(2)
    np.testing.assert_array_equal(_subset(random_state=7), first)


def test_different_seeds_select_different_subsets():
    assert not np.array_equal(_subset(random_state=0), _subset(random_state=1))


def test_without_random_state_numpys_global_seed_still_applies():
    # Earlier analyses seeded NumPy's global random state; they must still
    # select the same subset.
    np.random.seed(42)
    first = _subset()
    np.random.seed(42)
    np.testing.assert_array_equal(_subset(), first)
