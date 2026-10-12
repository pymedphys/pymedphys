---
myst:
  heading_anchors: 2
---

# Compare gamma performance across PyMedPhys versions

The [gamma benchmark script](https://github.com/pymedphys/pymedphys/tree/main/examples/gamma_benchmark)
compares `pymedphys.gamma` across named versions, branches, local checkouts,
or the SciPy and PyMedPhys interpolation backends in one checkout.
It saves an editable workload plan, checks every returned gamma array, and
reports runtime, memory use, and numerical differences. Reuse the same plan
for later changes, saving each comparison in a new results directory.

For a comparison:

1. Prepare the baseline and candidate checkouts and their Python environments.
2. Generate a configuration and plan with `init`, then inspect their settings.
3. Validate the files with `check`.
4. Execute `run` when ready to measure.
5. Open the resulting `index.html` and retain its raw evidence.

This workflow uses explicit, fixed workload sweeps. The complementary
[two-hour workstation audit](gamma-performance-study.md) calibrates a bounded
old/new comparison using both interpolation backends and supports a background
watchdog and runtime-model uncertainty studies.

## Prepare a comparison

Use the repository's [development environment](../setups/index.rst). Run the
following commands from the repository root; one-time setup and separate worker
environments are described in [Environment setup](#environment-setup).
Choose either the version-comparison initialisation below or the
[same-checkout interpolator comparison](#revisit-the-scipy-and-pymedphys-interpolators).
Each starts a new study in an empty directory.

```console
uv run python examples/gamma_benchmark/gamma_benchmark.py init --directory scratch-gamma-study --preset standard --baseline-checkout ../pymedphys-baseline --candidate-checkout ../pymedphys-candidate
```

`init` creates editable `scratch-gamma-study/config.json` and
`scratch-gamma-study/plan.json`. Checkout flags are optional: without them the configuration
contains placeholder paths. Flag paths resolve from the current directory;
paths written into the configuration resolve from that file's directory.

Configuration schema 2 names at least two PyMedPhys versions and selects one
baseline. For example:

```json
{
  "schema_version": 2,
  "baseline": "baseline",
  "versions": [
    {"name": "baseline", "checkout": "../../pymedphys-baseline", "interp_algo": "pymedphys"},
    {"name": "candidate", "checkout": "../../pymedphys-candidate", "interp_algo": "pymedphys"}
  ],
  "gamma_options": {},
  "settings": {"gamma_abs_tolerance": 1e-6}
}
```

Point `checkout` at the repository root; the script detects `lib/pymedphys` or
`pymedphys`. An optional `python` selects a separate environment, for example
`C:/env/Scripts/python.exe` or `/path/to/env/bin/python`. A null checkout uses
the PyMedPhys installed in that environment. Omit `python` to use the
controller's interpreter. Each version's `interp_algo` is `pymedphys` by default
and can be `pymedphys` or `scipy`. All versions call the public `pymedphys.gamma`
function with the same input arrays and shared `gamma_options`. Those shared
options cannot override controls defined by a case or select the interpolator;
set `interp_algo` on each version. Unsupported options fail explicitly.

Review the generated `settings` before running. Defaults are one warm-up, an
absolute gamma tolerance of `1e-6`, no pass/fail disagreements, exact
repeatability, ten minutes per worker, 8 GiB sampled process-tree RSS, and four
hours of active study time. Resource budgets are limits, not runtime estimates.

```console
uv run python examples/gamma_benchmark/gamma_benchmark.py check --config scratch-gamma-study/config.json --plan scratch-gamma-study/plan.json
```

A successful check reports the planned cases, rounds, and gamma-call count.
`init`, `plan`, `matrix`, `check`, and `report` neither import nor run PyMedPhys.
The check validates paths and settings; it does not test whether the chosen
PyMedPhys versions can be imported. Use `--allow-missing-checkouts` when
preparing plans with placeholder paths.

## Revisit the SciPy and PyMedPhys interpolators

To compare both interpolators in the same source checkout, initialise a focused
comparison from the repository root:

```console
uv run python examples/gamma_benchmark/gamma_benchmark.py init --directory scratch-gamma-study --preset thorough --compare-interpolators --baseline-checkout .
```

This selects `scipy` as the baseline and `pymedphys` as the candidate, both
using the specified checkout and the same Python interpreter. The
`--candidate-checkout` flag is unavailable in this mode. If the baseline path is
omitted, edit the shared placeholder path in both version entries. Preserve the
same checkout and dependency environment to isolate the interpolation choice.
Run `check` and `run` as shown elsewhere in this guide after inspecting the plan.

The `thorough` preset includes both dimensions, grid-size and eligible-fraction
sweeps, interpolation resolution, distance criterion, capped and uncapped
searches, mismatch, field shape, local/global gamma, RAM, threads, combined
criteria, and selected interactions. Its scope is fixed before execution and
can be filtered or extended. It does not calibrate sizes to a time allowance.
Report the achieved coverage if resource limits leave work unfinished.

Speed-up is **SciPy time divided by PyMedPhys time**: a value above one favours
the PyMedPhys interpolator. Read absolute times, verified output differences,
and memory beside that ratio. Compare matched controls within the new study.
The [Multilinear Interpolation Comparison](../../users/howto/interp/implementation_comparison.ipynb)
measures warmed standalone interpolation, including interpolator construction
and input checks where applicable. This same-checkout comparison measures the interpolation
choice's effect within complete gamma calls.
The [performance notebook](gamma-performance.ipynb),
[recorded scaling study](gamma-scaling-workstation/index.md), and
[uncertainty audit](gamma-uncertainty-workstation/index.md) retain their original
workloads, source revisions, environments, and timing schedules; their timings
form separate evidence rather than additional rounds of this comparison.

## Choose and freeze the workload

| Preset | Cases | Matched rounds per case |
|---|---:|---:|
| `quick` | 21 | 3 |
| `standard` | 94 | 5 |
| `thorough` | 188 | 7 |

The presets are starting points. Grid sizes are points per axis; reference and
evaluation point counts are recorded separately. The saved plan controls the
experiment, including its seed and repetition count.

| Study | Interpretation |
|---|---|
| Fixed-extent grid size | More points and smaller spacing sample the same physical field; array cost and discretisation both change |
| Fixed-spacing grid growth | Point count and physical extent grow together; available in `thorough` |
| Cutoff selection | Identical dose arrays select different reference points, including their changing difficulty |
| Field width at fixed cutoff | The field, gradients, occupancy, and mismatch difficulty change together |
| Distance criterion and interpolation fraction | Separately change the metric and requested search resolution |
| Gamma cap and mismatch | Vary search extent, physical displacement, and evaluation dose scale |
| Field shape and normalisation | Gaussian, double-feature, and smooth plateau fields; global/local gamma |
| RAM and threads | Vary requested chunk and thread budgets |
| Interactions and multiple criteria | Include size by fraction, distance by interpolation, cap by mismatch, and combined criterion calls |

Cutoff ties and discrete width fitting mean that achieved eligible fractions can
differ from their targets. Runtime sweeps use achieved fractions. Keep cutoff
and width studies separate, and retain padding, gradients, mismatch, and search
settings when interpreting the relationship between runtime and point count.
The synthetic fields describe computational workloads, not clinical acceptance
criteria or patient-data representativeness.

Edit the saved plan directly, or generate a filtered plan:

```console
uv run python examples/gamma_benchmark/gamma_benchmark.py plan --preset standard --study interpolation_resolution --dimension 3 --output scratch-gamma-study/interpolation-plan.json
```

For a factorial design, copy and edit
[matrix-design.json](https://github.com/pymedphys/pymedphys/blob/main/examples/gamma_benchmark/matrix-design.json),
then expand its template and factor lists:

```console
uv run python examples/gamma_benchmark/gamma_benchmark.py matrix --design examples/gamma_benchmark/matrix-design.json --output scratch-gamma-study/matrix-plan.json
```

Keep case IDs unique and re-run `check` after editing. Freeze the plan,
configuration, tolerances, warm-ups, repeats, resource settings, and source
versions before measuring. Keep source and environments unchanged during a run.
Each successful worker's recorded source, environment, and interpolation backend
must match the initial probe; detected drift stops the study.

## Execute and resume

Only `run` executes gamma:

```console
uv run python examples/gamma_benchmark/gamma_benchmark.py run --config scratch-gamma-study/config.json --plan scratch-gamma-study/plan.json --output scratch-gamma-results
```

Each case and round uses a fresh worker for each version. Workers run
sequentially, with seeded starting order and rotating positions between rounds.
A complete rotation balances positions; a partial rotation does not. Cases
follow saved-plan order. Keep the workstation awake and avoid competing heavy
computation; the script does not control power state or thermals.

The results directory records progress and includes an offline `index.html`.
Exit code 0 means the planned comparison completed successfully. Exit code 2
indicates incomplete or rejected work, or a configuration error; inspect the
saved status and logs. Failed, timed-out, memory-limited, mismatching, and
unattempted cases remain distinguishable.

To continue interrupted work:

```console
uv run python examples/gamma_benchmark/gamma_benchmark.py run --config scratch-gamma-study/config.json --plan scratch-gamma-study/plan.json --output scratch-gamma-results --resume
```

Resume imports and fingerprints the selected versions without calling gamma
before reusing results. It rejects detected changes to source, package versions,
the script, or scientific configuration. Final failed cases remain recorded;
use a new output directory to retry them or change settings. Remove a stale run
lock only after its recorded process has stopped.

## Measurement protocol

### Gamma semantics and verification

Coordinates and distance criteria are in millimetres. Analytic fields are
sampled directly on each grid in common arbitrary dose units, with explicit
global normalisation of 100. Arrays use `ij` indexing; returned gamma follows
the reference grid. Evaluation padding is physical and rounded upwards to
whole intervals. Displacement shifts the dose field, not the coordinates.

The lower cutoff uses the explicit global normalisation and includes equality.
Local gamma changes the dose-difference denominator; local cases exclude
analysed zero reference dose. Unanalysed points are NaN. Analysed values must be
finite and non-negative, including failing and out-of-grid points.

Finite gamma caps exceed one. Clipping above such a cap preserves the
`gamma <= 1` boundary, but agreement of capped values can conceal differences
above the cap. A null cap requests uncapped results. For shell search the
nominal step is distance divided by `interp_fraction`; that control is not a
universal gamma-error bound.

Principal comparisons analyse the full eligible set without
`skip_once_passed`. Custom random-subset or pass-only cases change requested
work or output semantics and must be interpreted separately. Equal seeds do
not prove identical random selections. The script checks subset membership,
count, and matching returned masks, without an independent oracle for the
randomly selected points. Pass-only values need not be fully minimised gamma.

Every point and every returned criterion is checked before accepting a
speed-up. Default acceptance requires identical NaN masks, finite non-negative
analysed values within the cap, absolute differences at most `1e-6` with zero
relative tolerance, and zero pass/fail disagreements. Full-set cases also
check the independently constructed eligible mask. First-call and timed
outputs, and outputs across fresh workers, must satisfy the configured
repeatability tolerance, zero by default.

Choose tolerances before examining timings. A numerical disagreement identifies
changed behaviour, not which version is correct. Baseline agreement can also
preserve shared defects. Intentional correctness changes need independent
expected results and an explained comparison; analytic cases, independent
references, and convergence studies provide additional scientific evidence.

### Timing and resource measurements

Input generation/loading, imports, provenance, and argument preparation occur
before timing. The first complete gamma call is measured separately and counts
as the first warm-up. After any additional configured warm-ups, the worker times
one complete gamma call. The timer includes setup, lazy imports, conversions,
and allocations performed inside that call; verification, output writing, and
plotting occur afterwards.

Process-first time is not guaranteed uncached compilation time. Per-version
compilation caches and operating-system caches can persist. Report first-call
and warmed measurements separately; their difference alone does not isolate
compilation cost. This protocol covers ordinary CPU PyMedPhys calls.

Requested thread settings apply to Numba, OMP, OpenBLAS, MKL, vecLib, and NumExpr
before numerical imports. They do not guarantee a universal thread limit or
equal CPU use. `ram_mib` sets `ram_available`, the interpolation/chunk budget.

Memory monitoring samples summed RSS across the observed worker process tree.
Timed-phase, first-call, and whole-worker peaks are retained separately. RSS
includes interpreters, inputs, caches, and allocations; shared pages may be
counted repeatedly and GPU memory is excluded. Samples can miss brief peaks
or short-lived processes. Preserve the sampling interval with the readings.
The report's peak-minus-pre-call diagnostic mixes a maximum process-tree peak
with median pre-call worker RSS across rounds; it is not allocated memory.

Worker timeout and memory limits cover loading, warm-up, verification, and
writing as well as gamma. RSS enforcement is sampled, not an instantaneous
operating-system limit. The overall budget can leave cases unattempted.
Absent runtimes are never replaced by zero or a limit value.

## Interpret and retain the report

Open `scratch-gamma-results/index.html` offline. Figures are also saved as PNG, SVG,
and PDF. The report covers workload inventory, runtime sweeps, verified
speed-ups, interaction heatmaps, RSS, numerical differences, pass disagreements,
timing variation, and available dose/gamma slices and distributions. Search
illustrations are labelled mathematical schematics, not measured query counts.
Missing observations remain missing and unfinished coverage stays visible.

Each speed-up is `baseline_seconds / candidate_seconds` within a matched round;
the report summarises these paired ratios. Only numerically accepted pairs enter
speed-up charts, while rejected timings remain labelled raw observations.
Absolute runtime accompanies the ratios. Observed minimum/maximum ranges are
not confidence intervals. Candidates sharing a baseline round are correlated;
these descriptive results apply to the measured machine and inputs.

Retain `config.resolved.json`, `plan.json`, `environment.json`, generated input
metadata and hashes, per-round JSON, `summary.json`, `summary.csv`, logs, and
figures. Set `keep_inputs` and `keep_arrays` before running when full arrays
will be needed for rechecking; slices and histograms cannot replace them.
Preserve dependency lockfiles alongside the recorded module paths, hashes,
package versions, and Git commit/dirty information. Provenance does not hash
every native dependency or external file; version numbers alone do not identify
dependency binaries.

To regenerate the report from saved evidence:

```console
uv run python examples/gamma_benchmark/gamma_benchmark.py report --output scratch-gamma-results
```

Reuse a frozen plan for later branches with a new configuration and results
directory. Version deliberate changes to workload generation, acceptance rules,
or timing boundaries so comparisons remain auditable.

## Environment setup

The repository's locked development environment provides the controller's
NumPy, Matplotlib, and psutil dependencies. Follow the
[workstation setup guide](../setups/index.rst), then synchronise from the
repository root:

```console
uv sync --python 3.14 --locked --extra all --group dev
```

Prepare each PyMedPhys checkout and its dependencies before selecting it.
The script reads checkouts without cloning repositories, changing branches, or
installing packages. Versions with different dependency requirements may need
separate Python environments; each worker needs NumPy, psutil, and that
version's PyMedPhys dependencies. Pin those dependencies and set the version's
`python` field accordingly. Workers ignore inherited `PYTHONPATH`, `PYTHONHOME`,
and user-site packages, so install dependencies in the selected environment.
Inspect recorded loaded-module paths after a run.

The script's tests use mock packages and labelled fabricated report inputs:

```console
uv run pymedphys dev tests examples/gamma_benchmark/tests
```

These tests check the runner and report without executing a real gamma
benchmark.
