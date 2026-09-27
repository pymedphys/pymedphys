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

"""Gamma pass rates, and reproducible random subsets of reference points."""

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

import pymedphys
from pymedphys._gamma.utilities import calculate_pass_rate


def test_pass_rate_is_public():
    assert pymedphys.gamma_pass_rate is calculate_pass_rate


def test_pass_rate_of_a_gamma_calculation():
    axis = np.arange(5.0)
    reference = np.array([0.1, 1.0, 1.0, 1.0, 1.0])
    evaluation = np.array([0.1, 1.0, 1.02, 1.05, 1.0])
    gamma = pymedphys.gamma(axis, reference, axis, evaluation, 3, 0.1)

    # The first point is below the cutoff; 1.05 fails even at its neighbours.
    assert np.isnan(gamma[0])
    assert pymedphys.gamma_pass_rate(gamma) == pytest.approx(75)


def test_gamma_of_exactly_one_passes():
    # NaN points were not evaluated, so they are not counted.
    gamma = np.array([0.5, 1.0, np.nextafter(1.0, 2.0), np.nan])
    assert calculate_pass_rate(gamma) == pytest.approx(100 * 2 / 3)


def test_pass_rate_accepts_any_array_shape():
    gamma = [[0.2, 1.5], [np.nan, 0.9]]
    assert calculate_pass_rate(gamma) == pytest.approx(100 * 2 / 3)


@pytest.mark.parametrize("gamma", [np.array([np.nan, np.nan]), np.array([])])
def test_pass_rate_without_evaluated_points_is_rejected(gamma):
    with pytest.raises(ValueError, match="No reference point was analysed"):
        calculate_pass_rate(gamma)


def _subset(**kwargs):
    axis = np.arange(50.0)
    dose = np.ones(50)
    gamma = pymedphys.gamma(axis, dose, axis, dose, 3, 3, random_subset=10, **kwargs)
    return ~np.isnan(gamma)


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
