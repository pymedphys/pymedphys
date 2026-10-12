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

"""Fixture and plan checks only: no gamma call, timer, or benchmark execution."""

import json

import numpy as np
import pytest

from gamma_bench.workloads import case_id, make_inputs, make_plan


@pytest.fixture
def small_case():
    case = dict(make_plan("quick")["cases"][0])
    case.update(n=11, extent_mm=20.0, evaluation_padding_mm=3.0, field_width_mm=4.0)
    case["id"] = case_id(case)
    return case


@pytest.mark.parametrize(
    "preset,maximum", [("quick", 30), ("standard", 120), ("thorough", 260)]
)
def test_plan_is_json_serialisable_deterministic_and_has_unique_case_ids(
    preset, maximum
):
    plan = make_plan(preset)
    assert plan == make_plan(preset)
    assert json.loads(json.dumps(plan, allow_nan=False)) == plan
    assert 10 <= len(plan["cases"]) <= maximum
    assert len({case["id"] for case in plan["cases"]}) == len(plan["cases"])
    assert {case["dimension"] for case in plan["cases"]} == {2, 3}
    assert plan["notes"]


def test_study_membership_is_explicit_in_case_identity(small_case):
    reordered = dict(reversed(list(small_case.items())))
    assert case_id(reordered) == case_id(small_case)
    renamed = small_case | {"study": "another_study", "notes": "reader note"}
    assert case_id(renamed) != case_id(small_case)
    assert case_id(renamed).split("-")[-1] == case_id(small_case).split("-")[-1]
    assert case_id(small_case | {"shift_mm": 2.0}) != case_id(small_case)


def test_standard_contains_required_one_factor_and_interaction_studies():
    studies = {case["study"] for case in make_plan("standard")["cases"]}
    assert {
        "grid_size_fixed_extent",
        "cutoff_selection",
        "field_width_fixed_cutoff",
        "distance_threshold",
        "interpolation_resolution",
        "search_cap",
        "mismatch",
        "size_by_fraction",
        "distance_by_interpolation",
        "cap_by_mismatch",
        "memory_budget",
        "thread_count",
        "normalisation",
        "multiple_criteria",
    } <= studies


@pytest.mark.parametrize("dimension", [2, 3])
@pytest.mark.parametrize("field", ["gaussian", "double", "plateau"])
def test_inputs_are_deterministic_finite_arrays_with_matching_coordinates(
    small_case, dimension, field
):
    case = small_case | {"dimension": dimension, "field": field}
    args, kwargs, metadata = make_inputs(case)
    repeated, repeated_kwargs, repeated_metadata = make_inputs(case)
    reference_axes, reference, evaluation_axes, evaluation = args
    assert isinstance(reference_axes, tuple) and isinstance(evaluation_axes, tuple)
    assert reference.shape == (11,) * dimension
    assert evaluation.shape == (15,) * dimension
    for axes, dose in [(reference_axes, reference), (evaluation_axes, evaluation)]:
        assert dose.dtype == np.float64 and dose.flags.c_contiguous
        assert np.all(np.isfinite(dose)) and np.all(dose >= 0)
        assert tuple(len(axis) for axis in axes) == dose.shape
        for axis in axes:
            assert np.all(np.diff(axis) > 0)
            np.testing.assert_allclose(np.diff(axis), 2.0, rtol=0, atol=1e-12)
    np.testing.assert_array_equal(evaluation_axes[0][2:-2], reference_axes[0])
    np.testing.assert_array_equal(reference, repeated[1])
    np.testing.assert_array_equal(evaluation, repeated[3])
    assert kwargs == repeated_kwargs and metadata == repeated_metadata
    json.dumps(metadata, allow_nan=False)


def test_size_sweep_keeps_extent_and_field_fixed_at_shared_coordinates(small_case):
    small, _, smeta = make_inputs(small_case)
    large, _, lmeta = make_inputs(small_case | {"n": 21})
    assert smeta["extent_mm"] == lmeta["extent_mm"] == [20.0, 20.0]
    assert smeta["spacing_mm"] == [2.0, 2.0]
    assert lmeta["spacing_mm"] == [1.0, 1.0]
    np.testing.assert_array_equal(small[0][0], large[0][0][::2])
    np.testing.assert_array_equal(small[1], large[1][::2, ::2])


def test_fixed_spacing_growth_is_distinct_from_fixed_extent(small_case):
    _, _, metadata = make_inputs(
        small_case | {"grid_mode": "fixed_spacing", "spacing_mm": 1.5}
    )
    assert metadata["extent_mm"] == [15.0, 15.0]
    assert metadata["spacing_mm"] == [1.5, 1.5]


def test_cutoff_sweep_changes_selection_without_changing_dose_fields(small_case):
    low, low_kwargs, low_meta = make_inputs(
        small_case | {"fraction_mode": "cutoff", "above_fraction_target": 0.1}
    )
    high, high_kwargs, high_meta = make_inputs(
        small_case | {"fraction_mode": "cutoff", "above_fraction_target": 0.7}
    )
    np.testing.assert_array_equal(low[1], high[1])
    np.testing.assert_array_equal(low[3], high[3])
    assert (
        low_kwargs["lower_percent_dose_cutoff"]
        > high_kwargs["lower_percent_dose_cutoff"]
    )
    assert low_meta["eligible_points"] < high_meta["eligible_points"]
    for args, kwargs, metadata in [
        (low, low_kwargs, low_meta),
        (high, high_kwargs, high_meta),
    ]:
        cutoff = (
            kwargs["lower_percent_dose_cutoff"] / 100 * kwargs["global_normalisation"]
        )
        assert metadata["eligible_points"] == np.count_nonzero(args[1] >= cutoff)
        assert metadata["eligible_points"] >= metadata["target_eligible_points"]
        assert (
            metadata["eligible_points"] - metadata["target_eligible_points"]
            < metadata["cutoff_tie_points"]
        )


@pytest.mark.parametrize("fraction,points", [(0.0, 0), (1.0, 121)])
def test_cutoff_selection_endpoints(small_case, fraction, points):
    _, _, metadata = make_inputs(
        small_case | {"fraction_mode": "cutoff", "above_fraction_target": fraction}
    )
    assert metadata["eligible_points"] == points


@pytest.mark.parametrize("field", ["gaussian", "double", "plateau"])
def test_width_family_changes_field_at_fixed_cutoff_and_reports_achieved_fraction(
    small_case, field
):
    narrow, nkwargs, nmeta = make_inputs(
        small_case
        | {"field": field, "fraction_mode": "width", "above_fraction_target": 0.2}
    )
    wide, wkwargs, wmeta = make_inputs(
        small_case
        | {"field": field, "fraction_mode": "width", "above_fraction_target": 0.7}
    )
    assert (
        nkwargs["lower_percent_dose_cutoff"]
        == wkwargs["lower_percent_dose_cutoff"]
        == 20.0
    )
    assert nmeta["field_summary"]["width_mm"] < wmeta["field_summary"]["width_mm"]
    assert not np.array_equal(narrow[1], wide[1])
    assert nmeta["eligible_fraction"] < wmeta["eligible_fraction"]
    assert abs(nmeta["eligible_fraction"] - 0.2) < 0.05
    assert abs(wmeta["eligible_fraction"] - 0.7) < 0.05


def test_zero_mismatch_is_same_analytic_field_on_shared_coordinates(small_case):
    args, _, metadata = make_inputs(small_case | {"shift_mm": 0.0, "dose_scale": 1.0})
    np.testing.assert_array_equal(args[1], args[3][2:-2, 2:-2])
    assert metadata["field_summary"]["shift_vector_mm"] == [0.0, -0.0]


def test_displacement_norm_and_independent_normalisation_controls(small_case):
    _, kwargs, metadata = make_inputs(
        small_case | {"shift_mm": 2.5, "local_gamma": True, "ram_mib": 32, "threads": 4}
    )
    assert np.linalg.norm(
        metadata["field_summary"]["shift_vector_mm"]
    ) == pytest.approx(2.5)
    assert kwargs["global_normalisation"] == 100.0
    assert kwargs["local_gamma"] is True
    assert kwargs["ram_available"] == 32 * 2**20
    assert metadata["requested_threads"] == 4
    assert "threads" not in kwargs


def test_optional_subset_is_a_reproducible_count_control(small_case):
    _, kwargs, _ = make_inputs(
        small_case | {"random_subset": 5, "seed": 1234, "skip_once_passed": True}
    )
    assert kwargs["random_subset"] == 5
    assert kwargs["random_state"] == 1234
    assert kwargs["skip_once_passed"] is True


@pytest.mark.parametrize(
    "updates",
    [
        {"n": 1},
        {"dimension": 4},
        {"extent_mm": 0},
        {"evaluation_padding_mm": -1},
        {"fraction_mode": "cutoff", "above_fraction_target": 1.1},
        {"max_gamma": 1},
        {"interp_fraction": float("inf")},
        {"threads": 0},
        {"dose_percent_threshold": []},
        {"random_subset": -1},
    ],
)
def test_invalid_workload_controls_are_rejected(small_case, updates):
    with pytest.raises(ValueError):
        make_inputs(small_case | updates)
