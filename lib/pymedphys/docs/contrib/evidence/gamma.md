---
myst:
  heading_anchors: 3
---

# Gamma performance evidence

Choose a record by the question it answers. The experiments below used
different source revisions, dose fields, environments, and timing schedules.
Read absolute times and verified outputs alongside speed ratios, and retain
each experiment as a separate body of evidence.

| Record or procedure | Question it answers | Status and scope |
| --- | --- | --- |
| [Fixed-grid notebook](../info/gamma-performance.ipynb) | What did the combined source changes save on six fixed workloads, and which repeated work was avoided? | Recorded 26 September 2026; six workloads, three paired rounds, two timed calls per revision per round |
| [Scaling study](../info/gamma-scaling-workstation/index.md) | How did complete gamma-call times change across grid sizes and criteria? | Partial study, 26–27 September 2026; 98 of 120 planned four-way groups verified |
| [Uncertainty audit](../info/gamma-uncertainty-workstation/index.md) | How repeatable were timings, and did voxel-count runtime models transfer to different fields? | Completed 27 September 2026; all 84 four-way groups across 17 workloads verified |
| [Reusable benchmark](../info/gamma-benchmark.md) | How do chosen versions or interpolators compare on a frozen workload plan? | A procedure for a new experiment, with explicit workload sweeps and resource budgets |
| [Bounded workstation audit](../info/gamma-performance-study.md) | How can a calibrated old/new, two-interpolator audit finish within a two-hour overall limit? | A procedure for a new experiment; choose coverage or runtime-model uncertainty |

The source change measured by the recorded experiments was PR #2066.
The numerical comparisons establish preservation on the measured synthetic
inputs. The dose fields are computational workloads; the studies do not
establish performance on patient treatment plans or clinical suitability of
gamma criteria.

## Recorded fixed-grid experiment

The [notebook](../info/gamma-performance.ipynb) compares previous source
[`866f83edad8586a42a739094e488f45242b72c95`](https://github.com/pymedphys/pymedphys/commit/866f83edad8586a42a739094e488f45242b72c95)
with candidate
[`d99893b46e3adb34e384b100d9932d87f5e38804`](https://github.com/pymedphys/pymedphys/commit/d99893b46e3adb34e384b100d9932d87f5e38804).
Its embedded record completed at 14:55:14 UTC on 26 September 2026.

The environment was an Intel Core Ultra 7 265HX Windows 11 workstation,
Python 3.12.14, NumPy 1.26.4, SciPy 1.16.2, and Numba 0.61.2, with two Numba
threads. Its rasterised and Gaussian-smoothed field uses a 41 × 57 × 57
3D grid at 2.5 mm spacing and a 401 × 401 2D grid at 0.5 mm spacing.
The six cases cover default global 3% / 3 mm, capped global, and local
2% / 2 mm in 3D, plus selected 2D and SciPy-path comparisons. They do not
form the complete two-dimension, three-criterion, two-interpolator matrix.

Each worker warms up with a complete gamma call, then times two calls.
Three rounds alternate revision order. The record contains 72 timed calls
and checks exact output equality, including shape and NaN positions, across
revisions and repetitions. Imports, input generation, initial compilation or
cache loading, and verification are outside the timed gamma call.

The complete worker, controller, timings, input/output hashes, software
versions, and source identifiers are embedded in the notebook. Its default
execution redraws that archived evidence and validates its internal record;
it does not collect fresh timings. Section 7 describes collecting a new record
with exact source-checkout environment variables or
`python examples/gamma_performance.py`, and retaining `results.json`, CSVs,
and figures. Use the procedure's `--plot-only` mode when redrawing an existing
external record.

## Recorded partial scaling study

The [scaling report](../info/gamma-scaling-workstation/index.md) compares
previous source
[`866f83edad8586a42a739094e488f45242b72c95`](https://github.com/pymedphys/pymedphys/commit/866f83edad8586a42a739094e488f45242b72c95)
with candidate
[`e3baff7b9f6047bff77ea4603623540f5eecf45a`](https://github.com/pymedphys/pymedphys/commit/e3baff7b9f6047bff77ea4603623540f5eecf45a),
recorded on 26–27 September 2026 before the two-hour scheduler existed.

The environment was an Intel Core Ultra 7 265HX, 20 logical CPUs, Windows 11,
Python 3.12.14, NumPy 1.26.4, SciPy 1.17.1, and Numba 0.67.0. Numba used
four threads; OMP, OpenBLAS, and MKL each used one. The RAM chunk budget was
1.5 GiB. The continuous-field schedule used five point-count multipliers
(1, 3, 10, 30, and 100), four rounds, and case-first ordering.

Four-way groups compare old/new gamma source with both interpolation paths.
The run verified 98 of 120 planned groups: 392 plotted timed calls across
25 workloads. All 2D cases and 3D global cases completed four rounds;
the largest capped 3D case completed two. The five 3D local cases were not
measured. Another successfully timed call belongs to an unfinished group and
is retained in the raw record but excluded from the comparison plots.

Every plotted group has recorded exact old/new array equality within each
interpolator, exact timed/warm-up agreement, and PyMedPhys/SciPy differences
below the stated `1e-10` absolute gamma tolerance, with zero pass-classification
disagreements. Full arrays were removed after their recorded checks, so a
fresh array-level verification requires rerunning those workloads.

Retain the report's [raw checkpoint](../info/gamma-scaling-workstation/results.json.gz),
[individual timings](../info/gamma-scaling-workstation/timings.csv),
[absolute summaries](../info/gamma-scaling-workstation/summary.csv), and
[paired ratios](../info/gamma-scaling-workstation/speed-ratios.csv) with its figures.
The report gives the uncompressed checkpoint digest and the command
`python examples/gamma_scaling_evidence.py --input lib/pymedphys/docs/contrib/info/gamma-scaling-workstation/results.json.gz --output gamma-scaling-evidence-rebuilt`
to regenerate tables and plots without gamma calls. Its incomplete coverage
remains part of the record after regeneration.

## Recorded completed uncertainty audit

The [uncertainty report](../info/gamma-uncertainty-workstation/index.md) compares
previous source
[`866f83edad8586a42a739094e488f45242b72c95`](https://github.com/pymedphys/pymedphys/commit/866f83edad8586a42a739094e488f45242b72c95)
with candidate
[`9b3a8aa00b752fd70bd92acd6d24f1089288dde5`](https://github.com/pymedphys/pymedphys/commit/9b3a8aa00b752fd70bd92acd6d24f1089288dde5).
It ran on 27 September 2026 from 11:48:39 to 12:31:15 UTC, completing in
42 min 37 s. Its [provenance file](../info/gamma-uncertainty-workstation/provenance.json)
records the exact timestamps, host, environment, source IDs, and archive digests.

The environment was an Intel Core Ultra 7 265HX, 20 logical CPUs, Windows 11,
Python 3.12.14, NumPy 1.26.4, SciPy 1.17.1, and Numba 0.67.0, with four Numba
threads and one thread each for OMP, OpenBLAS, and MKL. The RAM chunk budget
was 1.5 GiB. This shares named hardware and packages with the partial study,
but it remains a separate session with a different candidate and schedule.

All 84 planned four-way groups completed: 336 verified timed calls, each with
a full warm-up, across 17 synthetic workloads. Coverage includes core 3D and
2D scaling, a padding/field-width/mismatch diagnostic matrix, and two separate
SABR-like and prostate/nodal volume examples. Core 3D cases have eight rounds;
other cases have four. This design covers global gamma, with capped diagnostic
cases; it does not cover local gamma. Its larger-volume criteria are global
3% / 3 mm, whereas the coverage-oriented audit design uses 3% / 2 mm.

The record reports exact old/new and timed/warm-up agreement, a largest
PyMedPhys/SciPy absolute gamma difference of `2.59e-14`, and zero pass/fail
classification disagreements. The publication checks independently regenerated
inputs and their hashes, checked pinned source and runner hashes, and
recalculated paired ratios and fitted models. Gamma was not rerun for the
authored report; its array comparisons rely on the runner's recorded checks.

The fitted models use eligible voxel count and include withheld-size checks,
whole-round bootstrap intervals, drift diagnostics, and transfer to the two
volume examples. Their repeat intervals apply to that workstation and those
workloads. The separate volumes also lie beyond the fitted eligible-count
range, so transfer and extrapolation are tested together. Query counts were
not measured. CPU affinity, background load, power state, and thermal
conditions were not controlled or logged in either workstation scaling session.

Retain the [raw checkpoint](../info/gamma-uncertainty-workstation/results.json.gz),
[provenance](../info/gamma-uncertainty-workstation/provenance.json),
[timings](../info/gamma-uncertainty-workstation/timings.csv),
[summaries](../info/gamma-uncertainty-workstation/summary.csv),
[model analysis](../info/gamma-uncertainty-workstation/uncertainty.json), and
the report's CSVs and figures together. Regenerate the tables and figures
without gamma calls using
`python examples/gamma_uncertainty_evidence.py --input lib/pymedphys/docs/contrib/info/gamma-uncertainty-workstation/results.json.gz --output gamma-uncertainty-evidence-rebuilt`.

## Collecting a new comparison

Use [Compare gamma performance across versions](../info/gamma-benchmark.md)
for an editable, frozen workload plan comparing named versions or interpolators.
It measures process-first and warmed calls separately, samples process-tree
RSS, verifies output masks and values, and records incomplete or rejected work.
Its numerical tolerances, workloads, budgets, and source/environment controls
are part of the experiment. This tool's runner/report tests use mock packages
and labelled fabricated inputs; passing them is evidence for the tool, not a
measurement of real gamma performance.

Use [Run the bounded workstation audit](../info/gamma-performance-study.md)
for the calibrated four-way study with a background supervisor and a two-hour
overall deadline. Choose its coverage design or its uncertainty design before
launching. Preserve the frozen plan, checkpoints, environment, scripts, and
results bundle. A quick installation check exercises less scope than either
full study.

For geometry demonstrations rather than timing experiments, the
[coordinate notebook](../info/dicom-coordinates-illustrated.ipynb) executes
synthetic examples and independent coordinate checks; its scientific claim is
different from redrawing the performance notebook's archived timings.
Follow the [documentation guide](../info/docs-guide.rst) for notebook execution
and inspecting build artefacts. Source files, successful rendering, and
recorded experiment results establish different parts of the evidence.

```{toctree}
:maxdepth: 1

../info/gamma-performance
../info/gamma-scaling-workstation/index
../info/gamma-uncertainty-workstation/index
../info/gamma-benchmark
../info/gamma-performance-study
```
