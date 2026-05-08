%% Source: distilled from d:/MUSIQ/ALGT/algt_tests/pl/geom.pl + io_basics.pl
%%        + new predicates for ndarray verification (forall_ndarray, pass_rate)
%%
%% Reusable verification primitives for python-algorithm-verification deliverables.
%% Every algorithm-verification deliverable imports this module.
%%
%% Conventions:
%%   - Tolerance-based equality (is_approx_equal/3, is_approx_equal_relative/3)
%%   - Range checks (is_in_range_inclusive/3, is_in_range_exclusive/3)
%%   - Monotonicity probes (is_monotonic_in/4)
%%   - Sentinel checks (is_nan/1, is_finite/1)
%%   - Ndarray iteration (forall_ndarray/2, forall_pair_ndarray/3, count_passing/3,
%%                         pass_rate/3)

:- module(verification_predicates, [
    is_approx_equal/3,
    is_approx_equal_relative/3,
    is_in_range_inclusive/3,
    is_in_range_exclusive/3,
    is_monotonic_in/4,
    is_nan/1,
    is_finite/1,
    forall_ndarray/2,
    forall_pair_ndarray/3,
    count_passing/3,
    pass_rate/3,
    same_shape/2
]).

% ============================================================
% Approximate equality
% ============================================================

%% PY: equivalent to math.isclose(actual, expected, abs_tol=Epsilon)
%% Used throughout for tolerance-based numerical comparison; floating-point
%% equality with `==` is forbidden by SKILL.md quality gate.
is_approx_equal(Actual, Expected, Epsilon) :-
    Diff is abs(Actual - Expected),
    Diff =< Epsilon.

%% PY: math.isclose(actual, expected, rel_tol=RelEpsilon)
%% Relative tolerance; useful when absolute scale varies (dose values in cGy
%% may be 1e-3 or 1e3 across the same array).
is_approx_equal_relative(Actual, Expected, RelEpsilon) :-
    AbsActual is abs(Actual),
    AbsExpected is abs(Expected),
    Scale is max(AbsActual, AbsExpected),
    Scale > 0,
    Diff is abs(Actual - Expected),
    Diff =< RelEpsilon * Scale.

% ============================================================
% Range checks
% ============================================================

is_in_range_inclusive(V, Min, Max) :-
    V >= Min, V =< Max.

is_in_range_exclusive(V, Min, Max) :-
    V > Min, V < Max.

% ============================================================
% Monotonicity probe
% ============================================================

%% is_monotonic_in(+Pred, +Var, +V1, +V2)
%% For two probe values V1 <= V2, the predicate's value at V1 must be <=
%% the value at V2. Used for tolerance-monotonicity verification (pass_rate
%% at lower tolerance <= pass_rate at higher tolerance).
%%
%% Pred is called as Pred(V, Result) where V is bound to V1 then V2.
is_monotonic_in(Pred, _Var, V1, V2) :-
    V1 =< V2,
    call(Pred, V1, P1),
    call(Pred, V2, P2),
    P1 =< P2.

% ============================================================
% Sentinel checks
% ============================================================

%% is_nan(+X) -- succeeds if X is NaN.
%% Uses the IEEE 754 property: NaN != NaN, so X =:= X fails for NaN.
%% Catches arithmetic errors (e.g. comparing a non-number) so the predicate
%% is well-defined for any term.
is_nan(X) :-
    catch((X =\= X), _, fail).

%% is_finite(+X) -- succeeds if X is a finite number (not NaN, not +inf, not -inf).
is_finite(X) :-
    \+ is_nan(X),
    X =\= inf,
    X =\= -inf.

% ============================================================
% Ndarray iteration
% ============================================================
%
% The runner converts numpy arrays to nested Prolog lists (depth-first
% flattening; the outer list holds rows, inner lists hold values for 2D;
% deeper for 3D+). The forall_* predicates traverse depth-first.

%% forall_ndarray(+Array, :Goal)
%% Goal succeeds for every leaf-element of Array.
forall_ndarray([], _).
forall_ndarray([X | Xs], Goal) :-
    is_list(X),
    !,
    forall_ndarray(X, Goal),
    forall_ndarray(Xs, Goal).
forall_ndarray([X | Xs], Goal) :-
    call(Goal, X),
    forall_ndarray(Xs, Goal).

%% forall_pair_ndarray(+A, +B, :Goal)
%% Goal succeeds for every pair (a, b) of corresponding leaf-elements.
%% Both arrays must have the same nested-list structure.
forall_pair_ndarray([], [], _).
forall_pair_ndarray([X | Xs], [Y | Ys], Goal) :-
    is_list(X),
    is_list(Y),
    !,
    forall_pair_ndarray(X, Y, Goal),
    forall_pair_ndarray(Xs, Ys, Goal).
forall_pair_ndarray([X | Xs], [Y | Ys], Goal) :-
    call(Goal, X, Y),
    forall_pair_ndarray(Xs, Ys, Goal).

%% count_passing(+Array, :Goal, -Count)
%% Counts the number of leaf-elements for which Goal succeeds.
count_passing(Array, Goal, Count) :-
    count_passing_inner(Array, Goal, 0, Count).

count_passing_inner([], _, Count, Count).
count_passing_inner([X | Xs], Goal, Acc0, Count) :-
    is_list(X),
    !,
    count_passing_inner(X, Goal, Acc0, Acc1),
    count_passing_inner(Xs, Goal, Acc1, Count).
count_passing_inner([X | Xs], Goal, Acc0, Count) :-
    (   call(Goal, X)
    ->  Acc1 is Acc0 + 1
    ;   Acc1 = Acc0
    ),
    count_passing_inner(Xs, Goal, Acc1, Count).

%% Total non-NaN element count.
count_total_finite(Array, Total) :-
    count_passing(Array, [V]>>(\+ verification_predicates:is_nan(V)), Total).

%% pass_rate(+Array, :Goal, -Rate)
%% Rate = (count of leaf-elements satisfying Goal) / (count of finite elements).
%% Mirrors pymedphys._gamma.utilities.calculate_pass_rate at
%% lib/pymedphys/_gamma/utilities/core.py: a value passes iff (gamma <= 1)
%% AND not NaN; pass_rate denominator is the number of non-NaN elements.
pass_rate(Array, Goal, Rate) :-
    count_passing(Array, Goal, Numerator),
    count_total_finite(Array, Denominator),
    Denominator > 0,
    Rate is Numerator / Denominator.

% ============================================================
% Shape match
% ============================================================

%% same_shape(+A, +B) -- nested-list structures match (same length at every
%% depth). Used by ok_gamma_shape_matches_reference.
same_shape(A, B) :-
    \+ is_list(A),
    \+ is_list(B),
    !.
same_shape(A, B) :-
    is_list(A),
    is_list(B),
    length(A, N),
    length(B, N),
    maplist(same_shape, A, B).
