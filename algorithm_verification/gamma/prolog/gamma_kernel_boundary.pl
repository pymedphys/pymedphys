%% Source: lib/pymedphys/_gamma/implementation/shell.py
%%        + lib/pymedphys/_gamma/api/core.py
%%
%% kernel: pymedphys.gamma -- THE star algorithm of metersetmap and other
%%         dose-comparison tools. The boundary primitive declared here is
%%         what gets called in test runs; the body fails by default and is
%%         replaced at test time by either:
%%
%%         (1) a subprocess shell-out (mirrors ALGT_BEAM_VOLUME.pl pattern):
%%             write inputs as .npz, invoke a small Python script, read
%%             outputs back. CI-friendly; no SWI Python interop needed.
%%
%%         (2) janus_swi in-process: py_call(pymedphys:gamma(...), Output).
%%             Faster, but requires janus_swi installed.
%%
%% This boundary primitive is referenced by the python-streamlit-state-model
%% deliverable for metersetmap at:
%%   lts_models/metersetmap/prolog/algorithm_kernels.pl:pymedphys_gamma/6
%% (cross-language reference -- see Section 7 of gamma_verification_model.md)

:- module(gamma_kernel_boundary, [
    call_gamma/6,                       % call_gamma(+RefCoords, +RefDose, +EvalCoords, +EvalDose, +Options, -Output)
    call_gamma_with_runner/3,           % call_gamma_with_runner(+RunnerMode, +InputsList, -Output)
    default_gamma_options/1             % default_gamma_options(-OptionsDict)
]).

% ============================================================
% The kernel-under-test as a boundary primitive
% ============================================================

%% PY: lib/pymedphys/_gamma/implementation/shell.py:34-187 (gamma_shell)
%% PY: lib/pymedphys/_gamma/api/core.py:20-40 (gamma_dicom -- DICOM-input wrapper)
%%
%% The user-facing entry point is `pymedphys.gamma` which dispatches to
%% gamma_shell. This boundary primitive models the canonical signature.
%%
%% Inputs:
%%   RefCoords  -- tuple of monotonic ndarrays (axes per dimension)
%%   RefDose    -- ndarray, shape == cartesian product of RefCoords lengths
%%   EvalCoords -- as RefCoords
%%   EvalDose   -- ndarray, shape matches EvalCoords
%%   Options    -- dict with keys:
%%                   dose_percent_threshold      :: Number | List[Number]
%%                   distance_mm_threshold        :: Number | List[Number]
%%                   lower_percent_dose_cutoff   :: Number  (default 20)
%%                   interp_fraction              :: Int     (default 10)
%%                   max_gamma                    :: Number  (default inf)
%%                   local_gamma                  :: Bool    (default false)
%%                   global_normalisation         :: Number | none (default max(RefDose))
%%                   skip_once_passed             :: Bool    (default false)
%%                   random_subset                :: Int | none (default none)
%%                   ram_available                :: Int     (default 1.5GB)
%%                   interp_algo                  :: Atom    (default 'pymedphys')
%%
%% Output:
%%   - When pct_thresh and dist_thresh are scalars: ndarray same shape as RefDose
%%   - When either is a list: dict keyed by (pct, dist) tuples
%%
%% Output value contract:
%%   - Values in [0, max_gamma]  (clamped at PY:177-178)
%%   - NaN where RefDose < lower_dose_cutoff (PY:174 also converts inf -> NaN)
%%   - When local_gamma=True: cutoff is per-voxel (RefDose[i] < lower_percent_dose_cutoff/100 * RefDose[i])
%%     == lower_percent_dose_cutoff/100 of LOCAL dose
%%   - When local_gamma=False: cutoff is global (RefDose[i] < lower_percent_dose_cutoff/100 * global_normalisation)
call_gamma(_RefCoords, _RefDose, _EvalCoords, _EvalDose, _Options, _Output) :- fail.

%% Two runner modes; the test harness picks one and replaces the body of
%% call_gamma above. See gamma_runner.pl for the dispatcher.
call_gamma_with_runner(subprocess, _InputsList, _Output) :- fail.
call_gamma_with_runner(janus_swi, _InputsList, _Output) :- fail.

% ============================================================
% Default options dict (matches gamma_shell defaults at PY:34-51)
% ============================================================

default_gamma_options(_{
    dose_percent_threshold: 1,
    distance_mm_threshold: 1,
    lower_percent_dose_cutoff: 20,
    interp_fraction: 10,
    max_gamma: inf,
    local_gamma: false,
    global_normalisation: none,
    skip_once_passed: false,
    random_subset: none,
    ram_available: 1610612736,         % 1.5 * 2^30
    interp_algo: pymedphys
}).
