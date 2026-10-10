%% Source: lib/pymedphys/tests/gamma/test_agnew_mcgarry.py + downloaded data
%%
%% Registry of reference test corpora for gamma verification.
%%
%% Each fixture has:
%%   name             -- canonical short name used in ok_gamma_against_fixture/2
%%   ref_path         -- DICOM RT Dose file (reference)
%%   eval_path        -- DICOM RT Dose file (evaluation)
%%   options          -- gamma_options dict for this fixture
%%   expected_pass_rate -- baseline pass rate (rounded to 1 decimal)
%%   tolerance        -- pass_rate tolerance for the equivalence check
%%   source           -- publication / clinical case origin
%%   scenario         -- one-line clinical description
%%   hazard_categories -- list of hazards this fixture exercises
%%
%% Data files are fetched on first use via pymedphys._data.download from a
%% Zenodo-hosted gamma_test_data.zip (see PY:35 -- get_data_file/1).

:- module(test_fixtures, [
    gamma_fixture/2,                    % gamma_fixture(?Name, -Metadata)
    fixture_data_zip/1                  % fixture_data_zip(-FilenameAtom)
]).

fixture_data_zip('gamma_test_data.zip').

% ============================================================
% Agnew-McGarry corpus (Radiotherapy and Oncology 2016)
% ============================================================

%% PY: lib/pymedphys/tests/gamma/test_agnew_mcgarry.py:120-128 (test_max_gamma -- variant 1)
%% Ref: Agnew CE, McGarry CK. A tool to include gamma analysis software into a
%%      quality assurance program. Radiotherapy and Oncology 2016;118(3):568-573.
%%      <http://dx.doi.org/10.1016/j.radonc.2015.11.034>
gamma_fixture(agnew_mcgarry_local_1mm_max14, _{
    name: agnew_mcgarry_local_1mm_max14,
    ref_path:  'H&N_VMAT_Reference_1mmPx.dcm',
    eval_path: 'H&N_VMAT_Evaluated_1mmPx.dcm',
    options: _{
        dose_percent_threshold: 1,
        distance_mm_threshold: 1,
        lower_percent_dose_cutoff: 20,
        interp_fraction: 10,
        max_gamma: 1.4,
        local_gamma: true,
        skip_once_passed: true,
        random_subset: 50000          % seeded with np.random.seed(42) at PY:68
    },
    expected_pass_rate: 0.936,
    tolerance: 0.0005,
    source: 'Agnew & McGarry 2016',
    scenario: 'H&N VMAT 1mm pixel reference vs. evaluated; max_gamma=1.4',
    hazard_categories: [false_negative_qa, false_positive_qa, clamp_masking]
}).

%% PY: lib/pymedphys/tests/gamma/test_agnew_mcgarry.py:130-136 (test_max_gamma -- variant 2)
%% Same data, max_gamma=1.0001 -- exercises the clamp at PY:177-178 of shell.py
%% under tight constraint. Pass rate should be unchanged because clamping only
%% affects values above 1.0; pass criterion (gamma <= 1) is below the clamp.
gamma_fixture(agnew_mcgarry_local_1mm_max1p0001, _{
    name: agnew_mcgarry_local_1mm_max1p0001,
    ref_path:  'H&N_VMAT_Reference_1mmPx.dcm',
    eval_path: 'H&N_VMAT_Evaluated_1mmPx.dcm',
    options: _{
        dose_percent_threshold: 1,
        distance_mm_threshold: 1,
        lower_percent_dose_cutoff: 20,
        interp_fraction: 10,
        max_gamma: 1.0001,
        local_gamma: true,
        skip_once_passed: true,
        random_subset: 50000
    },
    expected_pass_rate: 0.936,
    tolerance: 0.0005,
    source: 'Agnew & McGarry 2016',
    scenario: 'H&N VMAT 1mm; max_gamma=1.0001 -- clamp-just-above-pass-threshold',
    hazard_categories: [clamp_masking, numerical_stability]
}).

%% PY: lib/pymedphys/tests/gamma/test_agnew_mcgarry.py:140-146 (test_local_gamma_1mm)
%% Default max_gamma=1.1; same data as above; baseline 93.6%.
gamma_fixture(agnew_mcgarry_local_1mm, _{
    name: agnew_mcgarry_local_1mm,
    ref_path:  'H&N_VMAT_Reference_1mmPx.dcm',
    eval_path: 'H&N_VMAT_Evaluated_1mmPx.dcm',
    options: _{
        dose_percent_threshold: 1,
        distance_mm_threshold: 1,
        lower_percent_dose_cutoff: 20,
        interp_fraction: 10,
        max_gamma: 1.1,
        local_gamma: true,
        skip_once_passed: true,
        random_subset: 50000
    },
    expected_pass_rate: 0.936,
    tolerance: 0.0005,
    source: 'Agnew & McGarry 2016',
    scenario: 'H&N VMAT 1mm; default max_gamma=1.1; canonical 1%/1mm local gamma reference',
    hazard_categories: [false_negative_qa, false_positive_qa, nondeterministic_subsetting]
}).

%% PY: lib/pymedphys/tests/gamma/test_agnew_mcgarry.py:152-159 (test_local_gamma_0_25mm)
%% Higher-resolution reference data; baseline 96.9% (LOCAL_GAMMA_0_25_BASELINE at PY:149).
gamma_fixture(agnew_mcgarry_local_0_25mm, _{
    name: agnew_mcgarry_local_0_25mm,
    ref_path:  'H&N_VMAT_Reference_0_25mmPx.dcm',
    eval_path: 'H&N_VMAT_Evaluated_0_25mmPx.dcm',
    options: _{
        dose_percent_threshold: 1,
        distance_mm_threshold: 1,
        lower_percent_dose_cutoff: 20,
        interp_fraction: 10,
        max_gamma: 1.1,
        local_gamma: true,
        skip_once_passed: true,
        random_subset: 50000
    },
    expected_pass_rate: 0.969,
    tolerance: 0.0005,
    source: 'Agnew & McGarry 2016',
    scenario: 'H&N VMAT 0.25mm; finer-grid reference; canonical 1%/1mm baseline',
    hazard_categories: [false_negative_qa, false_positive_qa]
}).

%% PY: lib/pymedphys/tests/gamma/test_agnew_mcgarry.py:163-179 (test_multi_inputs)
%% Multi-criteria gamma -- list-valued thresholds yield a dict output.
%% Exercises the multi-key code path at PY:167-180 of shell.py.
gamma_fixture(agnew_mcgarry_multi_criteria, _{
    name: agnew_mcgarry_multi_criteria,
    ref_path:  'H&N_VMAT_Reference_0_25mmPx.dcm',
    eval_path: 'H&N_VMAT_Evaluated_0_25mmPx.dcm',
    options: _{
        dose_percent_threshold: [1, 0.2],
        distance_mm_threshold: [1, 4],
        lower_percent_dose_cutoff: 20,
        interp_fraction: 10,
        max_gamma: 1.0001,
        local_gamma: true,
        skip_once_passed: true,
        random_subset: 50000
    },
    expected_pass_rate: _{
        '(1, 1)':   0.969,
        '(1, 4)':   0.998,
        '(0.2, 1)': 0.918,
        '(0.2, 4)': 0.992
    },
    tolerance: 0.0005,
    source: 'Agnew & McGarry 2016 + pymedphys multi-input baseline',
    scenario: 'Multi-criteria gamma; (pct, dist) pairs (1,1), (1,4), (0.2,1), (0.2,4)',
    hazard_categories: [false_negative_qa, multi_criteria_dispatch]
}).

% ============================================================
% Synthetic edge-case fixtures (no DICOM data; constructed in pytest)
% ============================================================

%% Reflexive: gamma(D, D) where D is a small synthetic dose array. Should
%% give all-zero gamma (modulo numerical interpolation noise). Exercises
%% ok_gamma_reflexive predicate.
gamma_fixture(synthetic_reflexive_2d, _{
    name: synthetic_reflexive_2d,
    ref_path:  synthetic,
    eval_path: synthetic_same_as_ref,
    options: _{
        dose_percent_threshold: 1,
        distance_mm_threshold: 1,
        lower_percent_dose_cutoff: 20,
        max_gamma: 2,
        local_gamma: false,
        random_subset: none
    },
    expected_pass_rate: 1.0,
    tolerance: 0.0,
    source: 'synthetic (constructed in pytest harness)',
    scenario: 'Self-comparison reflexive test; gamma(D, D) should be all zeros where defined',
    hazard_categories: [numerical_stability, silent_nan_propagation]
}).

%% Determinism: gamma(A, B, opts) called twice with same seed; outputs
%% should be byte-identical (not just approx-equal).
gamma_fixture(synthetic_determinism, _{
    name: synthetic_determinism,
    ref_path:  synthetic,
    eval_path: synthetic_random_perturbation,
    options: _{
        dose_percent_threshold: 1,
        distance_mm_threshold: 1,
        lower_percent_dose_cutoff: 20,
        max_gamma: 2,
        local_gamma: true,
        random_subset: 1000
        %% np.random.seed(42) called before each invocation in the harness
    },
    expected_pass_rate: deterministic_byte_identical,
    tolerance: 0.0,
    source: 'synthetic',
    scenario: 'Repeated invocation with same seed should produce byte-identical output',
    hazard_categories: [numerical_stability, nondeterministic_subsetting]
}).
