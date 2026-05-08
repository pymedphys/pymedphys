%% Source: lib/pymedphys/_streamlit/apps/metersetmap/main.py:638
%%        + lib/pymedphys/_streamlit/apps/metersetmap/_config.py:get_gamma_options
%%
%% The gamma_options dict consumed by the gamma kernel call at main.py:362-368.
%% Values are read from the on-disk config in non-advanced mode and exposed
%% as widgets in advanced mode (the advanced-mode path is NOT modeled in this
%% orchestration-first build; declared here for boundary completeness).
%%
%% Keys (matching pymedphys.gamma's keyword arguments):
%%   dose_percent_threshold   -- the gamma dose criterion in percent (e.g. 2 for 2%)
%%   distance_mm_threshold    -- the gamma distance criterion in mm (e.g. 0.5 for 0.5mm)
%%   local_gamma              -- True for local gamma, False for global gamma
%%   global_normalisation     -- (advanced) the value used to normalise dose for global gamma
%%   max_gamma                -- (advanced) early-cutoff value (gamma values >= max_gamma are clamped)
%%   random_subset            -- (advanced) optional subsampling for speed
%%   ram_available            -- (advanced) memory cap for the gamma compute

:- module(gamma_options_record, [
    initial_gamma_options/1,        % initial_gamma_options(-Options)
    is_local_gamma/1,               % is_local_gamma(+Options)
    gamma_threshold_percent/2,      % gamma_threshold_percent(+Options, -Percent)
    gamma_threshold_distance/2      % gamma_threshold_distance(+Options, -Distance)
]).

%% PY: lib/pymedphys/_streamlit/apps/metersetmap/_config.py:get_gamma_options
%% Reasonable defaults for the metersetmap comparison; the actual values come
%% from the per-config TOML at config["gamma"].
initial_gamma_options(_{
    dose_percent_threshold: 2,
    distance_mm_threshold: 0.5,
    local_gamma: true
}).

is_local_gamma(Options) :-
    Options.local_gamma == true.

gamma_threshold_percent(Options, Options.dose_percent_threshold).
gamma_threshold_distance(Options, Options.distance_mm_threshold).
