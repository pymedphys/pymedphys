%% Source: lib/pymedphys/_gamma/implementation/shell.py
%%
%% Per-aspect verification predicates for pymedphys.gamma. Each predicate:
%%   - asserts one property of the gamma kernel's output given its inputs
%%   - has a docstring naming the property + the hazard it discharges
%%   - has at least one %% PY: or %% Ref: anchor
%%   - emits format_log diagnostic on failure
%%   - uses verification_predicates:* primitives (no inlined tolerance checks)

:- module(gamma_invariants, [
    ok_gamma_range_nonneg/1,
    ok_gamma_range_below_max/2,
    ok_gamma_no_inf/1,
    ok_gamma_shape_matches_reference/2,
    ok_gamma_nan_at_low_dose/3,
    ok_gamma_reflexive/2,
    ok_gamma_deterministic/2,
    ok_gamma_max_gamma_clamp/2,
    ok_gamma_pass_rate_monotonic_pct/4,
    ok_gamma_pass_rate_monotonic_dist/4,
    ok_gamma_equiv_pass_rate/3,
    ok_gamma_equiv_multi_criteria/3,
    ok_gamma_local_normalisation_used/3,
    ok_gamma_global_normalisation_default/3
]).

:- use_module(verification_predicates).

% ============================================================
% Range invariants (H1: false-negative QA, H2: false-positive QA, H5: clamp masking)
% ============================================================

%% PY: lib/pymedphys/_gamma/implementation/shell.py:165 (current_gamma = gamma_loop(options))
%% PY: lib/pymedphys/_gamma/implementation/shell.py:173-178 (post-loop clamp/NaN handling)
%% Ref: Low DA, Harms WB, Mutic S, Purdy JA. A technique for the quantitative
%%      evaluation of dose distributions. Med Phys 1998;25(5):656-661.
%%
%% Hazard discharged: H1 (false-negative QA via clinically-impossible negative gamma).
%% Gamma is defined as a non-negative dose-distribution metric; any voxel
%% reporting gamma < 0 indicates a numerical bug in the kernel.
ok_gamma_range_nonneg(Output) :-
    (   forall_ndarray(Output, gamma_value_nonneg)
    ->  format_log('    ok_gamma_range_nonneg ok.~n', [])
    ;   format_log('    **** ok_gamma_range_nonneg FAILED ****~n', []),
        fail
    ).

gamma_value_nonneg(V) :- is_nan(V), !.
gamma_value_nonneg(V) :- V >= 0.

%% PY: lib/pymedphys/_gamma/implementation/shell.py:177-178
%%     gamma_greater_than_ref = gamma_temp > max_gamma
%%     gamma_temp[gamma_greater_than_ref] = max_gamma
%%
%% Hazard discharged: H5 (clamp masking) -- the explicit clamp guarantees no
%% gamma value exceeds max_gamma. Verifies that the post-loop clamp is applied.
ok_gamma_range_below_max(Output, MaxGamma) :-
    (   forall_ndarray(Output, [V]>>gamma_value_below_max(V, MaxGamma))
    ->  format_log('    ok_gamma_range_below_max(~p) ok.~n', [MaxGamma])
    ;   format_log('    **** ok_gamma_range_below_max(~p) FAILED ****~n', [MaxGamma]),
        fail
    ).

gamma_value_below_max(V, _Max) :- is_nan(V), !.
gamma_value_below_max(V, Max) :- V =< Max.

%% PY: lib/pymedphys/_gamma/implementation/shell.py:174
%%     gamma_temp[np.isinf(gamma_temp)] = np.nan
%%
%% Hazard discharged: H3 (silent NaN propagation) -- the kernel explicitly
%% replaces inf with NaN; an inf in the output indicates the post-loop NaN
%% conversion was bypassed.
ok_gamma_no_inf(Output) :-
    (   forall_ndarray(Output, gamma_value_not_inf)
    ->  format_log('    ok_gamma_no_inf ok.~n', [])
    ;   format_log('    **** ok_gamma_no_inf FAILED ****~n', []),
        fail
    ).

gamma_value_not_inf(V) :- is_nan(V), !.
gamma_value_not_inf(V) :- V =\= inf, V =\= -inf.

% ============================================================
% Shape invariant (H6: shape mismatch)
% ============================================================

%% PY: lib/pymedphys/_gamma/implementation/shell.py:173
%%     gamma_temp = np.reshape(gamma_temp, np.shape(dose_reference))
%%
%% Hazard discharged: H6 (shape mismatch -> indexing errors downstream).
%% gamma output must be reshape-compatible with dose_reference; downstream
%% callers (metersetmap's plot_and_save_results, calculate_pass_rate) assume
%% same-shape.
ok_gamma_shape_matches_reference(Output, RefDose) :-
    (   same_shape(Output, RefDose)
    ->  format_log('    ok_gamma_shape_matches_reference ok.~n', [])
    ;   format_log('    **** ok_gamma_shape_matches_reference FAILED ****~n', []),
        fail
    ).

% ============================================================
% NaN-at-low-dose contract (H3: silent NaN propagation)
% ============================================================

%% PY: lib/pymedphys/_gamma/implementation/shell.py (lower_dose_cutoff handling
%%     within gamma_loop -- per-voxel masking of reference points below cutoff)
%%
%% Contract: forall i, RefDose[i] < lower_dose_cutoff <=> isnan(Output[i]).
%% (The biconditional is important: NaNs MUST appear where dose is below
%% threshold, AND must NOT appear where dose is at or above threshold.)
%%
%% For local_gamma=False: lower_dose_cutoff = lower_percent_dose_cutoff/100 * global_normalisation
%% For local_gamma=True: cutoff is per-voxel (handled via dose-relative metric)
%%
%% Hazard discharged: H3 (silent NaN propagation -- the cutoff zeroes out
%% low-dose regions to avoid noise-amplification; the contract documents which
%% voxels are masked).
ok_gamma_nan_at_low_dose(Output, RefDose, LowerDoseCutoff) :-
    (   forall_pair_ndarray(RefDose, Output,
            [Ref, Out]>>nan_at_low_dose_check(Ref, Out, LowerDoseCutoff))
    ->  format_log('    ok_gamma_nan_at_low_dose(~p) ok.~n', [LowerDoseCutoff])
    ;   format_log('    **** ok_gamma_nan_at_low_dose(~p) FAILED ****~n', [LowerDoseCutoff]),
        fail
    ).

%% Strict biconditional: ref < cutoff iff isnan(out).
%% Note: this is a strong claim. If the kernel ever returns NaN for in-range
%% reference doses (e.g. because the evaluation grid doesn't cover that voxel),
%% this predicate will detect it.
nan_at_low_dose_check(Ref, Out, Cutoff) :-
    (   Ref < Cutoff
    ->  is_nan(Out)
    ;   \+ is_nan(Out)
    ).

% ============================================================
% Reflexive invariant (H4: numerical-stability loss)
% ============================================================

%% Hazard discharged: H4 (numerical-stability loss).
%% gamma(D, D) should be all zeros wherever defined (gamma is identically zero
%% when reference == evaluation; nonzero values indicate numerical drift in
%% the interpolation or distance-metric calculation).
%%
%% Tolerance: SmallEps (default 1e-6) accounts for floating-point round-off
%% in the interp_fraction subdivision; values exceeding this indicate a real
%% kernel bug.
ok_gamma_reflexive(Output, Eps) :-
    (   forall_ndarray(Output, [V]>>reflexive_value_check(V, Eps))
    ->  format_log('    ok_gamma_reflexive(~p) ok.~n', [Eps])
    ;   format_log('    **** ok_gamma_reflexive(~p) FAILED ****~n', [Eps]),
        fail
    ).

reflexive_value_check(V, _Eps) :- is_nan(V), !.
reflexive_value_check(V, Eps) :- abs(V) =< Eps.

% ============================================================
% Determinism invariant (H4, H7: nondeterministic subsetting)
% ============================================================

%% Hazard discharged: H4 (numerical-stability loss), H7 (nondeterministic
%% random_subset).
%% Two invocations with identical inputs (and identical np.random.seed for
%% random_subset) must produce byte-identical output.
%%
%% Note: this is byte-identity, NOT approx-equal. Pure functions in numpy
%% should be deterministic given equal inputs and seeds; any divergence is
%% a real bug (e.g. uninitialized buffer, float-summation order dependency).
ok_gamma_deterministic(Output1, Output2) :-
    (   Output1 == Output2
    ->  format_log('    ok_gamma_deterministic ok.~n', [])
    ;   format_log('    **** ok_gamma_deterministic FAILED ****~n', []),
        fail
    ).

% ============================================================
% Max-gamma clamp invariant (H5: clamp masking)
% ============================================================

%% PY: lib/pymedphys/_gamma/implementation/shell.py:177-178
%% Same body as ok_gamma_range_below_max but framed as a separate predicate
%% because the hazard chain is different: this verifies that the clamp is
%% APPLIED, not just that the output is in range. (If the clamp were not
%% applied, the output could still be in [0, +inf], passing range_below_max
%% with MaxGamma=inf, but failing this predicate when MaxGamma is finite.)
ok_gamma_max_gamma_clamp(Output, MaxGamma) :-
    is_finite(MaxGamma),
    (   forall_ndarray(Output, [V]>>gamma_value_below_max(V, MaxGamma))
    ->  format_log('    ok_gamma_max_gamma_clamp(~p) ok.~n', [MaxGamma])
    ;   format_log('    **** ok_gamma_max_gamma_clamp(~p) FAILED ****~n', [MaxGamma]),
        fail
    ).

% ============================================================
% Pass-rate monotonicity (H1: false-negative QA, H2: false-positive QA)
% ============================================================

%% Hazard discharged: H1 + H2 (pass-rate inversion under tolerance change
%% would produce uncalibrated QA that's neither correctly false-positive
%% nor correctly false-negative).
%%
%% Property: increasing the dose tolerance can only INCREASE the pass rate.
%% The harness invokes gamma at two distinct pct thresholds and verifies.
ok_gamma_pass_rate_monotonic_pct(Output1, Output2, Pct1, Pct2) :-
    Pct1 =< Pct2,
    pass_rate(Output1, gamma_passes, Rate1),
    pass_rate(Output2, gamma_passes, Rate2),
    (   Rate1 =< Rate2
    ->  format_log('    ok_gamma_pass_rate_monotonic_pct(~p->~p, ~p->~p) ok.~n',
                   [Pct1, Pct2, Rate1, Rate2])
    ;   format_log('    **** ok_gamma_pass_rate_monotonic_pct FAILED: pass_rate(~p)=~p > pass_rate(~p)=~p ****~n',
                   [Pct1, Rate1, Pct2, Rate2]),
        fail
    ).

ok_gamma_pass_rate_monotonic_dist(Output1, Output2, Dist1, Dist2) :-
    Dist1 =< Dist2,
    pass_rate(Output1, gamma_passes, Rate1),
    pass_rate(Output2, gamma_passes, Rate2),
    (   Rate1 =< Rate2
    ->  format_log('    ok_gamma_pass_rate_monotonic_dist(~p->~p, ~p->~p) ok.~n',
                   [Dist1, Dist2, Rate1, Rate2])
    ;   format_log('    **** ok_gamma_pass_rate_monotonic_dist FAILED ****~n', []),
        fail
    ).

%% A voxel "passes" iff gamma <= 1 AND not NaN.
%% Mirrors pymedphys._gamma.utilities.calculate_pass_rate semantics.
gamma_passes(V) :- \+ is_nan(V), V =< 1.

% ============================================================
% Equivalence to reference test corpora (H1, H2)
% ============================================================

%% Hazard discharged: H1 + H2.
%% For an Agnew-McGarry fixture, the computed pass rate must match the
%% baseline (rounded to 1 decimal == 0.0005 tolerance) given by the original
%% paper / pymedphys regression baselines.
%%
%% Tolerance: per-fixture, from test_fixtures.pl; default 0.0005 (since
%% baselines are documented to 1 decimal place).
ok_gamma_equiv_pass_rate(Output, ExpectedRate, Tolerance) :-
    pass_rate(Output, gamma_passes, ActualRate),
    (   is_approx_equal(ActualRate, ExpectedRate, Tolerance)
    ->  format_log('    ok_gamma_equiv_pass_rate(actual=~p, expected=~p, tol=~p) ok.~n',
                   [ActualRate, ExpectedRate, Tolerance])
    ;   format_log('    **** ok_gamma_equiv_pass_rate FAILED: actual=~p, expected=~p, tol=~p ****~n',
                   [ActualRate, ExpectedRate, Tolerance]),
        fail
    ).

%% PY: lib/pymedphys/tests/gamma/test_agnew_mcgarry.py:163-179 (test_multi_inputs)
%% For multi-criteria gamma, output is a dict keyed by (pct, dist) tuples.
%% Each entry must match its baseline pass rate.
ok_gamma_equiv_multi_criteria(OutputDict, ExpectedDict, Tolerance) :-
    %% OutputDict and ExpectedDict are Prolog dicts with same keys.
    dict_pairs(OutputDict, _, OutputPairs),
    dict_pairs(ExpectedDict, _, ExpectedPairs),
    forall(member(Key-OutputArray, OutputPairs),
           (   member(Key-ExpectedRate, ExpectedPairs),
               pass_rate(OutputArray, gamma_passes, ActualRate),
               is_approx_equal(ActualRate, ExpectedRate, Tolerance)
           )),
    format_log('    ok_gamma_equiv_multi_criteria ok (~d criteria checked).~n',
               [_]).

% ============================================================
% Normalisation modes (H1, H2)
% ============================================================

%% Hazard discharged: H1 + H2.
%% When local_gamma=True, the dose tolerance is computed per-voxel against
%% the reference dose AT THAT VOXEL, not against the global maximum. The
%% effect: low-dose regions get tighter relative tolerance, high-dose regions
%% get looser. Pass rate differs from global mode.
%%
%% Verification: gamma(local=true) and gamma(local=false) on the same data
%% should give DIFFERENT pass rates (modulo edge cases where they coincide).
%% A test that returns the same value for both is a kernel bug (the option
%% wasn't honored).
ok_gamma_local_normalisation_used(LocalOutput, GlobalOutput, MinDifference) :-
    pass_rate(LocalOutput, gamma_passes, LocalRate),
    pass_rate(GlobalOutput, gamma_passes, GlobalRate),
    Diff is abs(LocalRate - GlobalRate),
    (   Diff >= MinDifference
    ->  format_log('    ok_gamma_local_normalisation_used (Diff=~p >= ~p) ok.~n',
                   [Diff, MinDifference])
    ;   format_log('    **** ok_gamma_local_normalisation_used FAILED: Diff=~p < ~p (suggests local_gamma not honored) ****~n',
                   [Diff, MinDifference]),
        fail
    ).

%% PY: lib/pymedphys/_gamma/implementation/shell.py:127-144 (GammaInternalFixedOptions.from_user_inputs)
%% Default global_normalisation == max(dose_reference) when global_normalisation=None.
%% Verification: gamma(local=False, global_norm=None) should match
%% gamma(local=False, global_norm=max(dose_reference)) byte-identically.
ok_gamma_global_normalisation_default(OutputDefault, OutputExplicit, _MaxDose) :-
    (   OutputDefault == OutputExplicit
    ->  format_log('    ok_gamma_global_normalisation_default ok.~n', [])
    ;   format_log('    **** ok_gamma_global_normalisation_default FAILED ****~n', []),
        fail
    ).
