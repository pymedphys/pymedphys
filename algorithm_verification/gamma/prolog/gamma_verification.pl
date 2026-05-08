%% Source: lib/pymedphys/_gamma/implementation/shell.py
%%
%% Top-level verification entry point. Mirrors the ALGT_BEAM_VOLUME pattern
%% (`ok_<thing>/N` predicate as conjunction of per-aspect sub-predicates).

:- module(gamma_verification, [
    ok_gamma/3,                         % ok_gamma(+Inputs, +Output, ?HazardSummary)
    ok_gamma_full_suite/2,              % ok_gamma_full_suite(+FixtureName, ?HazardSummary)
    ok_gamma_against_fixture/2          % ok_gamma_against_fixture(+FixtureName, ?HazardSummary)
]).

:- use_module(verification_predicates).
:- use_module(gamma_invariants).
:- use_module(test_fixtures).
:- use_module(gamma_kernel_boundary).

% ============================================================
% Per-invocation property check
% ============================================================

%% PY: lib/pymedphys/_gamma/implementation/shell.py:34 (gamma_shell entry point)
%%
%% Universal output-property check: any single gamma_shell call must satisfy
%% these aspects regardless of the input fixture or option set:
%%   - range_nonneg
%%   - no_inf
%%   - shape_matches_reference
%%   - max_gamma_clamp (when max_gamma is finite)
%%
%% Inputs is a list [RefCoords, RefDose, EvalCoords, EvalDose, Options]
%% (Options is a dict).
ok_gamma(Inputs, Output, ok) :-
    Inputs = [_RefCoords, RefDose, _EvalCoords, _EvalDose, Options],
    format_log('  Running ok_gamma universal aspects...~n', []),
    ok_gamma_range_nonneg(Output),
    ok_gamma_no_inf(Output),
    ok_gamma_shape_matches_reference(Output, RefDose),
    %% The cutoff value depends on local vs global. Compute it here so the
    %% predicate body matches gamma_shell's internal contract.
    Cutoff = Options.lower_percent_dose_cutoff,
    ok_gamma_nan_at_low_dose(Output, RefDose, Cutoff),
    %% Conditional: only check max_gamma_clamp when MaxGamma is finite.
    (   Options.max_gamma == inf
    ->  true
    ;   ok_gamma_max_gamma_clamp(Output, Options.max_gamma)
    ),
    format_log('  ok_gamma universal aspects PASSED.~n', []).

% ============================================================
% Per-fixture verification
% ============================================================

%% PY: lib/pymedphys/tests/gamma/test_agnew_mcgarry.py
%%
%% Loads a named fixture, calls the kernel, runs ok_gamma + the fixture-
%% specific equivalence check.
ok_gamma_against_fixture(FixtureName, ok) :-
    gamma_fixture(FixtureName, Meta),
    format_log('**** ok_gamma_against_fixture(~p) ****~n', [FixtureName]),
    format_log('  Scenario: ~w~n', [Meta.scenario]),
    format_log('  Source:   ~w~n', [Meta.source]),
    format_log('  Hazards:  ~p~n', [Meta.hazard_categories]),

    %% Load the fixture inputs (DICOM dose-grid extraction is the harness's
    %% responsibility; the runner side replaces this with a real load).
    load_fixture_inputs(Meta, [RefCoords, RefDose, EvalCoords, EvalDose]),
    Options = Meta.options,
    Inputs = [RefCoords, RefDose, EvalCoords, EvalDose, Options],

    %% Call the kernel via the boundary primitive.
    call_gamma(RefCoords, RefDose, EvalCoords, EvalDose, Options, Output),

    %% Universal aspects.
    ok_gamma(Inputs, Output, _),

    %% Fixture-specific equivalence.
    Expected = Meta.expected_pass_rate,
    Tol = Meta.tolerance,
    (   is_dict(Expected)
    ->  ok_gamma_equiv_multi_criteria(Output, Expected, Tol)
    ;   number(Expected)
    ->  ok_gamma_equiv_pass_rate(Output, Expected, Tol)
    ;   Expected == deterministic_byte_identical
    ->  call_gamma(RefCoords, RefDose, EvalCoords, EvalDose, Options, Output2),
        ok_gamma_deterministic(Output, Output2)
    ;   Expected == 1.0
    ->  %% Reflexive fixture (gamma(D,D) == 0 everywhere defined).
        ok_gamma_reflexive(Output, 1.0e-6)
    ),

    format_log('**** ok_gamma_against_fixture(~p) PASSED ****~n~n', [FixtureName]).

%% Stub: load_fixture_inputs(+FixtureMeta, -InputsList)
%% Replaced by the runner with real DICOM-load + dose-grid-extraction.
%% In the orchestration-test build, this fails -- the pytest harness is the
%% canonical execution path for fixture-driven verification.
load_fixture_inputs(_Meta, _Inputs) :- fail.

% ============================================================
% Full per-fixture suite (universal + monotonicity + reflexive + determinism
% as applicable)
% ============================================================

%% Runs every aspect that's exercisable for the given fixture.
%% Monotonicity and local/global normalisation aspects require running the
%% kernel multiple times with varying options; this predicate orchestrates
%% those secondary calls.
ok_gamma_full_suite(FixtureName, ok) :-
    ok_gamma_against_fixture(FixtureName, _),
    %% Additional cross-invocation aspects (deterministic, monotonic, etc.)
    %% are exercised by the pytest harness rather than this Prolog runner;
    %% they require multiple kernel invocations with controlled option
    %% perturbations which are easier to drive from Python.
    format_log('**** ok_gamma_full_suite(~p) PASSED ****~n', [FixtureName]).
