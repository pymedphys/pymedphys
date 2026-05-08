# Copyright (C) 2026

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Mirror of algorithm_verification/gamma/prolog/gamma_invariants.pl as a
pytest harness. Each pytest function corresponds to one ok_gamma_<aspect>
Prolog predicate; the docstring cites the predicate by name so divergence
between the two specs is grep-able.

This is the canonical CI execution path. Run via:

    uv run -- pytest algorithm_verification/gamma/pytest/

The Prolog spec at prolog/gamma_invariants.pl is what a regulator would read;
this file is what CI executes.

Uses the existing pymedphys test infrastructure:
  - lib/pymedphys/tests/gamma/test_agnew_mcgarry.py provides the data-load
    helpers (get_data_file, dose_from_dataset, load_yx_from_dicom, run_gamma)
  - pymedphys._data.download fetches the gamma_test_data.zip from Zenodo
"""

import math

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

import pymedphys
from pymedphys._data import download
from pymedphys._gamma.utilities import calculate_pass_rate

# pylint: disable=C0103,C1801


# ============================================================
# Fixture loaders (mirrors test_agnew_mcgarry.py helpers)
# ============================================================


def get_data_file(filename):
    """Mirror of pymedphys/tests/gamma/test_agnew_mcgarry.py:34-35."""
    return download.get_file_within_data_zip("gamma_test_data.zip", filename)


def dose_from_dataset(ds):
    return ds.pixel_array * ds.DoseGridScaling


def load_yx_from_dicom(ds):
    resolution = np.array(ds.PixelSpacing).astype(float)
    dx = resolution[0]
    x = ds.ImagePositionPatient[0] + np.arange(0, ds.Columns * dx, dx)
    dy = resolution[1]
    y = ds.ImagePositionPatient[1] + np.arange(0, ds.Rows * dy, dy)
    return y, x


RANDOM_SUBSET = 50000


def run_gamma_with_options(
    filepath_ref,
    filepath_eval,
    *,
    dose_threshold=1,
    distance_threshold=1,
    max_gamma=1.1,
    local_gamma=True,
    skip_once_passed=True,
    random_subset=RANDOM_SUBSET,
):
    """Drive pymedphys.gamma with explicit kwargs (one-stop fixture caller).

    Mirrors test_agnew_mcgarry.run_gamma but parameterized for the broader
    aspect set verified here.
    """
    if random_subset is not None:
        np.random.seed(42)

    ds_ref = pydicom.dcmread(filepath_ref)
    ds_eval = pydicom.dcmread(filepath_eval)

    axes_reference = load_yx_from_dicom(ds_ref)
    dose_reference = dose_from_dataset(ds_ref)
    axes_evaluation = load_yx_from_dicom(ds_eval)
    dose_evaluation = dose_from_dataset(ds_eval)

    return pymedphys.gamma(
        axes_reference,
        dose_reference,
        axes_evaluation,
        dose_evaluation,
        dose_threshold,
        distance_threshold,
        lower_percent_dose_cutoff=20,
        interp_fraction=10,
        max_gamma=max_gamma,
        local_gamma=local_gamma,
        skip_once_passed=skip_once_passed,
        random_subset=random_subset,
    )


# ============================================================
# Reusable property primitives (mirrors verification_predicates.pl)
# ============================================================


def is_approx_equal(a, b, eps):
    """Mirror of verification_predicates:is_approx_equal/3."""
    return abs(a - b) <= eps


# ============================================================
# Universal aspect tests (mirror gamma_invariants:ok_gamma_*)
#
# Each pytest function corresponds to one Prolog predicate; the docstring
# cites the predicate by name. Failure messages mirror the Prolog
# format_log diagnostics.
# ============================================================


@pytest.mark.pydicom
def test_gamma_range_nonneg_agnew_mcgarry_1mm():
    """Mirror of ok_gamma_range_nonneg/1.

    Hazard discharged: H1 (false-negative QA via clinically-impossible
    negative gamma).
    """
    output = run_gamma_with_options(
        get_data_file("H&N_VMAT_Reference_1mmPx.dcm"),
        get_data_file("H&N_VMAT_Evaluated_1mmPx.dcm"),
    )
    finite = output[~np.isnan(output)]
    assert (finite >= 0).all(), "ok_gamma_range_nonneg failed"


@pytest.mark.pydicom
def test_gamma_no_inf_agnew_mcgarry_1mm():
    """Mirror of ok_gamma_no_inf/1.

    Hazard discharged: H3 (silent NaN propagation -- inf in output indicates
    the post-loop NaN conversion at PY:174 was bypassed).
    """
    output = run_gamma_with_options(
        get_data_file("H&N_VMAT_Reference_1mmPx.dcm"),
        get_data_file("H&N_VMAT_Evaluated_1mmPx.dcm"),
    )
    assert not np.any(np.isinf(output)), "ok_gamma_no_inf failed"


@pytest.mark.pydicom
def test_gamma_shape_matches_reference_1mm():
    """Mirror of ok_gamma_shape_matches_reference/2.

    Hazard discharged: H6 (shape mismatch -> indexing errors downstream).
    """
    ref_path = get_data_file("H&N_VMAT_Reference_1mmPx.dcm")
    ds_ref = pydicom.dcmread(ref_path)
    dose_reference = dose_from_dataset(ds_ref)

    output = run_gamma_with_options(
        ref_path,
        get_data_file("H&N_VMAT_Evaluated_1mmPx.dcm"),
    )
    assert (
        output.shape == dose_reference.shape
    ), "ok_gamma_shape_matches_reference failed"


@pytest.mark.pydicom
def test_gamma_max_gamma_clamp_1mm():
    """Mirror of ok_gamma_max_gamma_clamp/2.

    Hazard discharged: H5 (clamp masking failure).
    Verifies the post-loop clamp at PY:177-178 is applied.
    """
    max_gamma = 1.1
    output = run_gamma_with_options(
        get_data_file("H&N_VMAT_Reference_1mmPx.dcm"),
        get_data_file("H&N_VMAT_Evaluated_1mmPx.dcm"),
        max_gamma=max_gamma,
    )
    finite = output[~np.isnan(output)]
    assert (finite <= max_gamma).all(), "ok_gamma_max_gamma_clamp failed"


@pytest.mark.pydicom
def test_gamma_nan_at_low_dose_1mm():
    """Mirror of ok_gamma_nan_at_low_dose/3.

    Hazard discharged: H3 (silent NaN propagation).
    Strict biconditional: ref < cutoff IFF isnan(out). For local_gamma=True
    the cutoff is applied as lower_percent_dose_cutoff/100 of the local dose.
    """
    ref_path = get_data_file("H&N_VMAT_Reference_1mmPx.dcm")
    ds_ref = pydicom.dcmread(ref_path)
    dose_reference = dose_from_dataset(ds_ref)

    output = run_gamma_with_options(
        ref_path,
        get_data_file("H&N_VMAT_Evaluated_1mmPx.dcm"),
        local_gamma=False,  # use global cutoff for cleaner contract check
    )
    # Global cutoff: 20% of max(dose_reference)
    cutoff = 0.20 * np.max(dose_reference)
    expected_nan_mask = dose_reference < cutoff
    actual_nan_mask = np.isnan(output)
    # Strict biconditional check
    np.testing.assert_array_equal(
        expected_nan_mask,
        actual_nan_mask,
        err_msg="ok_gamma_nan_at_low_dose biconditional failed",
    )


# ============================================================
# Reflexive aspect (synthetic fixture)
# ============================================================


@pytest.mark.pydicom
def test_gamma_reflexive_synthetic_2d():
    """Mirror of ok_gamma_reflexive/2.

    Hazard discharged: H4 (numerical-stability loss).
    gamma(D, D) should be approximately zero everywhere defined.
    """
    np.random.seed(42)
    # Construct a small synthetic dose grid with both high-dose and below-cutoff voxels.
    dose = np.zeros((20, 20))
    dose[5:15, 5:15] = 100.0  # high-dose central region
    axes = (np.arange(20).astype(float), np.arange(20).astype(float))

    output = pymedphys.gamma(
        axes,
        dose,
        axes,
        dose,
        1,
        1,
        lower_percent_dose_cutoff=20,
        max_gamma=2,
        local_gamma=False,
    )
    finite = output[~np.isnan(output)]
    assert (
        finite < 1e-6
    ).all(), "ok_gamma_reflexive failed: nonzero gamma in self-comparison"


# ============================================================
# Determinism aspect
# ============================================================


@pytest.mark.pydicom
def test_gamma_deterministic_seeded_subset():
    """Mirror of ok_gamma_deterministic/2.

    Hazard discharged: H4 (numerical-stability loss), H7 (nondeterministic
    random_subset).
    Two invocations with identical inputs and seeds must produce
    byte-identical output.
    """
    args = dict(
        filepath_ref=get_data_file("H&N_VMAT_Reference_1mmPx.dcm"),
        filepath_eval=get_data_file("H&N_VMAT_Evaluated_1mmPx.dcm"),
        random_subset=RANDOM_SUBSET,
    )
    output1 = run_gamma_with_options(**args)
    output2 = run_gamma_with_options(**args)
    # NaN-aware byte-identity: NaN in both, finite values exactly equal.
    assert output1.shape == output2.shape, "shape diverged"
    nan1, nan2 = np.isnan(output1), np.isnan(output2)
    assert np.array_equal(
        nan1, nan2
    ), "ok_gamma_deterministic failed: NaN positions differ"
    np.testing.assert_array_equal(
        output1[~nan1],
        output2[~nan2],
        err_msg="ok_gamma_deterministic failed: finite values diverge",
    )


# ============================================================
# Pass-rate monotonicity
# ============================================================


@pytest.mark.pydicom
def test_gamma_pass_rate_monotonic_pct():
    """Mirror of ok_gamma_pass_rate_monotonic_pct/4.

    Hazard discharged: H1 + H2 (pass-rate inversion under tolerance change
    would produce uncalibrated QA).
    """
    args = dict(
        filepath_ref=get_data_file("H&N_VMAT_Reference_1mmPx.dcm"),
        filepath_eval=get_data_file("H&N_VMAT_Evaluated_1mmPx.dcm"),
    )
    output_tight = run_gamma_with_options(**args, dose_threshold=1)
    output_loose = run_gamma_with_options(**args, dose_threshold=2)
    rate_tight = calculate_pass_rate(output_tight)
    rate_loose = calculate_pass_rate(output_loose)
    assert rate_tight <= rate_loose + 1e-6, (
        f"ok_gamma_pass_rate_monotonic_pct failed: "
        f"pass_rate(1%)={rate_tight} > pass_rate(2%)={rate_loose}"
    )


@pytest.mark.pydicom
def test_gamma_pass_rate_monotonic_dist():
    """Mirror of ok_gamma_pass_rate_monotonic_dist/4."""
    args = dict(
        filepath_ref=get_data_file("H&N_VMAT_Reference_1mmPx.dcm"),
        filepath_eval=get_data_file("H&N_VMAT_Evaluated_1mmPx.dcm"),
    )
    output_tight = run_gamma_with_options(**args, distance_threshold=1)
    output_loose = run_gamma_with_options(**args, distance_threshold=2)
    rate_tight = calculate_pass_rate(output_tight)
    rate_loose = calculate_pass_rate(output_loose)
    assert rate_tight <= rate_loose + 1e-6, (
        f"ok_gamma_pass_rate_monotonic_dist failed: "
        f"pass_rate(1mm)={rate_tight} > pass_rate(2mm)={rate_loose}"
    )


# ============================================================
# Equivalence to reference test corpora (Agnew-McGarry)
# ============================================================


@pytest.mark.pydicom
def test_gamma_equiv_agnew_mcgarry_local_1mm():
    """Mirror of ok_gamma_equiv_pass_rate/3 against fixture
    agnew_mcgarry_local_1mm (test_fixtures.pl).

    Hazard discharged: H1 + H2.
    Ref: Agnew CE, McGarry CK. Radiotherapy and Oncology 2016;118(3):568-573.
    Baseline 93.6% from test_agnew_mcgarry.py:144.
    """
    output = run_gamma_with_options(
        get_data_file("H&N_VMAT_Reference_1mmPx.dcm"),
        get_data_file("H&N_VMAT_Evaluated_1mmPx.dcm"),
    )
    rate = calculate_pass_rate(output)
    assert is_approx_equal(
        round(rate, 1), 93.6, 0.05
    ), f"ok_gamma_equiv_pass_rate failed: actual={rate:.2f}, expected=93.6"


@pytest.mark.pydicom
def test_gamma_equiv_agnew_mcgarry_local_0_25mm():
    """Mirror of ok_gamma_equiv_pass_rate/3 against fixture
    agnew_mcgarry_local_0_25mm (test_fixtures.pl).

    Hazard discharged: H1 + H2.
    Baseline 96.9% (LOCAL_GAMMA_0_25_BASELINE at test_agnew_mcgarry.py:149).
    """
    output = run_gamma_with_options(
        get_data_file("H&N_VMAT_Reference_0_25mmPx.dcm"),
        get_data_file("H&N_VMAT_Evaluated_0_25mmPx.dcm"),
    )
    rate = calculate_pass_rate(output)
    assert is_approx_equal(
        round(rate, 1), 96.9, 0.05
    ), f"ok_gamma_equiv_pass_rate failed: actual={rate:.2f}, expected=96.9"


@pytest.mark.slow
@pytest.mark.pydicom
def test_gamma_equiv_multi_criteria():
    """Mirror of ok_gamma_equiv_multi_criteria/3.

    Hazard discharged: H1 + H2 + multi_criteria_dispatch.
    Baselines from test_agnew_mcgarry.py:174-179.
    """
    if RANDOM_SUBSET is not None:
        np.random.seed(42)

    ref_path = get_data_file("H&N_VMAT_Reference_0_25mmPx.dcm")
    eval_path = get_data_file("H&N_VMAT_Evaluated_0_25mmPx.dcm")
    ds_ref = pydicom.dcmread(ref_path)
    ds_eval = pydicom.dcmread(eval_path)

    gamma_dict = pymedphys.gamma(
        load_yx_from_dicom(ds_ref),
        dose_from_dataset(ds_ref),
        load_yx_from_dicom(ds_eval),
        dose_from_dataset(ds_eval),
        [1, 0.2],
        [1, 4],
        lower_percent_dose_cutoff=20,
        interp_fraction=10,
        max_gamma=1.0001,
        local_gamma=True,
        skip_once_passed=True,
        random_subset=RANDOM_SUBSET,
    )

    baseline = {
        (1, 1): 96.9,
        (1, 4): 99.8,
        (0.2, 1): 91.8,
        (0.2, 4): 99.2,
    }
    for key, expected in baseline.items():
        actual = round(calculate_pass_rate(gamma_dict[key]), 1)
        assert is_approx_equal(
            actual, expected, 0.05
        ), f"ok_gamma_equiv_multi_criteria failed at {key}: actual={actual}, expected={expected}"


# ============================================================
# Normalisation modes
# ============================================================


@pytest.mark.pydicom
def test_gamma_local_vs_global_differ():
    """Mirror of ok_gamma_local_normalisation_used/3.

    Hazard discharged: H1 + H2.
    local_gamma=True and local_gamma=False on the same data should give
    distinct pass rates -- a coincident result suggests the option was not
    honored.
    """
    args = dict(
        filepath_ref=get_data_file("H&N_VMAT_Reference_1mmPx.dcm"),
        filepath_eval=get_data_file("H&N_VMAT_Evaluated_1mmPx.dcm"),
    )
    output_local = run_gamma_with_options(**args, local_gamma=True)
    output_global = run_gamma_with_options(**args, local_gamma=False)
    rate_local = calculate_pass_rate(output_local)
    rate_global = calculate_pass_rate(output_global)
    # Minimum expected difference; very small differences (<0.5%) indicate
    # the local_gamma option was not exercised.
    diff = abs(rate_local - rate_global)
    assert diff >= 0.5, (
        f"ok_gamma_local_normalisation_used failed: "
        f"local={rate_local}, global={rate_global}, diff={diff} (suggests option ignored)"
    )
