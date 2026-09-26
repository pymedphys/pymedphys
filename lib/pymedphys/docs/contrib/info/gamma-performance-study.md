# Gamma performance: a background workstation study

This study compares complete gamma-call times for **old and new PyMedPhys
source, each with the PyMedPhys and SciPy interpolators**. It measures absolute
seconds and scaling over much larger grids, checks the numerical results, and
packages the evidence for publication. Run it on one workstation to keep the
hardware consistent. The script runs independently of a notebook or terminal.

“Old/new SciPy” means the old/new gamma implementation using the **same SciPy
package version**, not a comparison of SciPy releases. The earlier
[fixed-grid notebook](gamma-performance.ipynb) explains the avoided copying
with a smaller recorded experiment. Its rasterised phantom differs from this
study's continuous field, so their timing observations must not be pooled.

## Start the study

Use a checkout containing PR #2066, Git and Python 3.12. Both source revisions
must be available locally; a shallow clone may need a fetch. Activate a Python
environment and, from the repository root, run:

```console
python -m pip install -r examples/gamma-scaling-requirements.txt
python examples/gamma_scaling_background.py --output gamma-scaling-local
```

Use a separate environment if installing those fixed dependencies would change
packages you need for other work. On Windows, the existing repository environment
can be used as `.\.venv\Scripts\python.exe` in place of `python`.

The launch command returns immediately. You can close the terminal, but keep
the workstation awake, connected to power and free of other heavy computation.
**Allow many hours and substantial free RAM.** The default is four Numba
threads and a four-hour timeout per whole worker, including its warm-up and
timed call. The 1.5 GiB RAM chunk budget does not cap total process memory.
Neither the launcher nor the benchmark changes your power settings.

The launcher resolves previous main `866f83edad8586a42a739094e488f45242b72c95`
and the checkout's committed `HEAD` to exact source identifiers before starting.
Use `--current-ref`, `--previous-ref`, `--threads` or `--worker-timeout` on the
initial launch to choose other values. Uncommitted library edits are not
measured. Temporary detached worktrees keep the comparison separate from your
working files; the benchmark removes its own worktrees afterwards.

It also freezes copies of the benchmark scripts inside the output directory,
so later edits to the repository's runner do not change an active study or its
resume path. Keep the Python environment unchanged until the study finishes.

For a small installation and background-launch check, use a separate directory:

```console
python examples/gamma_scaling_background.py --quick --output gamma-scaling-check
```

This exercises all six dimension/criterion combinations and all four variants
at small sizes, with one round. It is explicitly marked as a quick check and
cannot support the full scaling claim.

## Progress, stopping and resuming

```console
python examples/gamma_scaling_background.py --status gamma-scaling-local
```

Status reports completed four-way groups, recorded timed calls and the log
location. The full study has **120 groups and 480 timed calls**. `run.log`
reports the current grid, round and implementation, including warm-up time.
To follow it on Windows:

```powershell
Get-Content gamma-scaling-local/run.log -Tail 20 -Wait
```

To stop cleanly:

```console
python examples/gamma_scaling_background.py --stop gamma-scaling-local
```

Stopping waits for the **current worker to finish**; a large worker can take
a long time. It then preserves its checkpoint and closes the temporary
checkouts. To continue later:

```console
python examples/gamma_scaling_background.py --resume gamma-scaling-local
```

Resume restores the saved revisions and settings, uses the frozen scripts,
and requires the original Python environment and host. An operating-system
lock prevents concurrent runs from writing to the same study. Completed runs
cannot be resumed accidentally; start a new directory for another experiment.

## What the full study measures

Each dimension uses five nominal point multipliers, with axis lengths rounded
down to integer sizes:

| Multiplier | 2D shape (y, x) | 3D shape (z, y, x) |
| --- | --- | --- |
| 1× | 401 × 401 | 41 × 57 × 57 |
| 3× | 694 × 694 | 59 × 82 × 82 |
| 10× | 1268 × 1268 | 88 × 122 × 122 |
| 30× | 2196 × 2196 | 127 × 177 × 177 |
| 100× | 4010 × 4010 | 190 × 264 × 264 |

The maxima are **16,080,100 points in 2D** and **13,242,240 in 3D**. These
are total reference-grid points, not the number of interpolation queries made
during gamma. The 3D maximum is approximately 99.4 times its own baseline
after rounding. The very fine grids are stress tests, not clinical grid-size
recommendations.

Two large Gaussian-blurred boxes and a smaller boost form a smooth continuous
dose field, with 6 mm Gaussian standard deviation. It is sampled on a fixed
physical domain: ±100 mm along both 2D axes, or ±50, ±70 and ±70 mm along
the 3D axes. The evaluation field is scaled by 1.02 and translated by
(1.5, −2.0) mm in 2D or (1.5, −2.0, 0.75) mm in 3D, in the stated array-axis
order. Increasing resolution samples the same analytic field rather than
changing a rasterised box edge. The 2D field is a separate workload, not a
central slice of the 3D field.

Both revisions receive identical ascending, regularly spaced, coincident grids
and float64 arrays. These avoid cases the previous implementation mishandled.
Three settings give **30 workloads**:

| Profile | Dose and distance criteria | Search cap |
| --- | --- | --- |
| Global | 3% of a fixed 2 Gy normalisation; 3 mm | Unset |
| Capped global | The same global criteria | `max_gamma=2` |
| Local | 2% of the dose at each reference point; 2 mm | Unset |

The supplied global normalisation is exactly 2 Gy; the sampled maximum is not
rescaled to equal it. Every reference point at or above **0.2 Gy** is included.
There is no random subset or early exit simply because gamma passes.
`interp_fraction=10` controls search sampling, not input-grid spacing. A cap
need not save time if the uncapped search already finishes below it. The local
case changes both normalisation and criteria, so it does not isolate either
factor's cost.

## Timing and correctness

Four rounds balance the order of the four implementations: each occupies
each position once, and each directed consecutive pair occurs once. Each
worker imports one verified checkout in a fresh process, performs a complete
untimed warm-up, then times one complete gamma call. The full study therefore
has **480 timed calls and 480 full warm-ups**.

Imports, input generation, initial compilation/cache loading, verification and
file writing are excluded. Preparation inside the gamma call is included.
Numba uses four threads by default; OMP, OpenBLAS and MKL are set to one. This
measures warmed use, not the first-ever wait. Changing grid resolution also
changes discretisation and interpolation error, so scaling is not a pure
algorithmic-complexity experiment.

Every timed array must exactly match its warm-up. The controller compares
every old/new gamma value and NaN position **exactly for each interpolator**.
It additionally compares PyMedPhys with SciPy using absolute tolerance
`1e-10` in dimensionless gamma and zero relative tolerance, recording maximum
error and any pass-classification disagreements. This is an arithmetic
allowance, not a physical or clinical tolerance. All eligible points must have
finite gamma. Hashes are recorded for provenance; they do not replace the
full-array comparisons.

Only fully verified four-way groups enter the figures. Absolute curves show
median seconds on logarithmic axes. Relative curves use new/old ratios within
each matched round, then their median; this need not equal the ratio of the
absolute medians. Ranges show observed min–max, not confidence intervals.
Small differences near equality should not be promoted as reliable changes
from four rounds alone. A failed or timed-out case is reported as incomplete,
never as zero time or a speed gain.

## What to upload

When status says **completed**, upload just:

```text
gamma-scaling-local/gamma-scaling-upload.zip
```

The bundle contains:

- `study/results.json`: every timing, numerical check and source/environment record;
- `study/timings.csv` and `study/summary.csv`: individual and summarised values;
- three PNG/SVG comparison figures and the generated results table;
- `run.json`, `run-config.json` and `run.log`: completion state, launch settings and progress;
- `environment.json` and frozen benchmark scripts: package versions and reproducible source.

The large temporary `.npy` arrays and compilation caches are **excluded**.
Keep the whole output directory locally if you may need to resume. A stopped
or failed run also produces a bundle for diagnosis; its status is explicit
and its measurements must not be labelled a complete study. A quick-check
bundle is similarly identified.

The completed full-run JSON is the primary evidence for committing the new
scaling record to the repository, regenerating the performance notebook and
updating the changelog with a permanent result link. Share saved PNGs directly
when illustrating the run; a screenshot is optional.
