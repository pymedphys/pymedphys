%% Source: lib/pymedphys/tests/gamma/test_agnew_mcgarry.py
%%
%% Test runner for the gamma verification suite. Mirrors the
%% ALGT_BEAM_VOLUME pattern (`:- open_log, ..., close_log`) but loads
%% fixtures from test_fixtures.pl and dispatches to either subprocess-based
%% or janus_swi-based kernel invocation.
%%
%% Two runner modes (chosen via SWI-Prolog flag `gamma_runner_mode`):
%%
%%   subprocess    : Write inputs as .npz to a temp dir, invoke
%%                    `python -m algorithm_verification.gamma.runner_helper
%%                     --inputs in.npz --output out.npz`, read output back.
%%                   CI-friendly; requires no janus_swi. Mirrors ALGT's
%%                   shell-out-to-.exe pattern.
%%
%%   janus_swi     : py_call(pymedphys:gamma(...), Output) directly.
%%                    Faster, in-process. Requires janus_swi installed.
%%                    Verify availability with use_module(library(janus)).
%%
%% Default mode: subprocess (more portable; CI uses this).
%%
%% Usage (interactive):
%%
%%   ?- consult('algorithm_verification/gamma/prolog/gamma_runner.pl').
%%   ?- run_all_verifications.
%%
%%   ?- run_verification(agnew_mcgarry_local_1mm).
%%
%% Usage (CI / pytest):
%%
%%   The pytest harness at pytest/test_gamma_verification.py is the
%%   canonical CI entry point and does NOT call into Prolog -- it
%%   imports pymedphys.gamma directly and re-implements each ok_gamma_<aspect>
%%   predicate as a parameterized pytest function. The Prolog runner is
%%   the spec; the pytest harness is the execution.

:- module(gamma_runner, [
    run_all_verifications/0,
    run_verification/1,
    set_runner_mode/1,
    open_log/0,
    close_log/0,
    format_log/2
]).

:- use_module(gamma_verification).
:- use_module(test_fixtures).

% ============================================================
% Logging (mirrors ALGT's open_log/close_log/format_log idiom)
% ============================================================

:- dynamic(log_stream/1).

open_log :-
    open('temp/gamma_verification.log', write, Stream),
    assertz(log_stream(Stream)),
    format_log('==== gamma verification suite ====~n', []),
    get_time(T),
    stamp_date_time(T, DateTime, local),
    format_log('Started: ~w~n', [DateTime]).

close_log :-
    log_stream(Stream),
    format_log('==== suite ended ====~n', []),
    close(Stream),
    retractall(log_stream(_)).

format_log(Format, Args) :-
    log_stream(Stream),
    !,
    format(Stream, Format, Args),
    format(user_output, Format, Args).
format_log(Format, Args) :-
    %% No log stream open -- write to user_output only.
    format(user_output, Format, Args).

% ============================================================
% Runner-mode flag
% ============================================================

%% Default: subprocess mode (no janus_swi dependency).
:- nb_setval(gamma_runner_mode, subprocess).

set_runner_mode(Mode) :-
    member(Mode, [subprocess, janus_swi]),
    nb_setval(gamma_runner_mode, Mode),
    format_log('Runner mode set to: ~w~n', [Mode]).

% ============================================================
% Top-level: run all fixture verifications
% ============================================================

run_all_verifications :-
    open_log,
    catch(
        forall(gamma_fixture(Name, _Meta), run_verification(Name)),
        Error,
        (   format_log('**** SUITE FAILED with error: ~p ****~n', [Error]),
            close_log,
            throw(Error)
        )
    ),
    format_log('==== ALL VERIFICATIONS PASSED ====~n', []),
    close_log.

% ============================================================
% Per-fixture verification driver
% ============================================================

run_verification(FixtureName) :-
    ok_gamma_against_fixture(FixtureName, _).
