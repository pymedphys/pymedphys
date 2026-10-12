# Example status

The [reusable gamma benchmark](gamma_benchmark/README.md) compares named
PyMedPhys versions or checkouts, or both interpolators in one checkout, using
editable, fixed workload plans. It checks
every returned gamma array before accepting paired speed-ups and produces an
offline report. See its [comparison guide and measurement protocol](../lib/pymedphys/docs/contrib/info/gamma-benchmark.md)
for controlled sweeps of grid size, cutoff, search settings, and resource budgets.

`gamma_scaling_background.py` runs the comprehensive gamma performance study
in the background, with progress reporting, stop/resume and one upload ZIP:

```console
python -m pip install -r examples/gamma-scaling-requirements.txt
python examples/gamma_scaling_background.py --output gamma-audit-2h
```

Run from the repository root. The study compares old/new PyMedPhys and SciPy
paths with a **two-hour total limit**, including warm-ups and reporting.
Calibration selects three practical sizes for each of six dimension/profile
families, followed by four balanced rounds: 72 four-way comparisons. Each has a
45-second shared allowance. Two further comparisons use synthetic SABR-like
(1.25 mm) and prostate/nodal (2.5 mm) volumes, with 20 minutes each. The complete
audit contains 296 timed calls plus full warm-ups and separate calibration.
It records absolute times and PyMedPhys/SciPy speed ratios, plots logarithmic
scaling curves, checks every
completed gamma array and explicitly labels unfinished coverage. Resume never
extends the original deadline. Use a new directory for this bounded launcher;
older frozen runs cannot acquire its deadline by resuming.

See [the workstation study guide](../lib/pymedphys/docs/contrib/info/gamma-performance-study.md)
for methodology, installation checks, resource settings, progress, stop/resume
and exactly which artefact to upload. `gamma_scaling.py` remains available for
advanced custom selections, combining parts and plot-only mode. Use the background
launcher to enforce the overall deadline.

The [recorded workstation evidence](../lib/pymedphys/docs/contrib/info/gamma-scaling-workstation/index.md)
retains the verified portion of the earlier long run, with explicit coverage
limits. `gamma_scaling_evidence.py` regenerates that dated evidence without
running gamma calculations.

`gamma_performance.py` retains the earlier fixed-grid experiment used in the
[performance notebook](../lib/pymedphys/docs/contrib/info/gamma-performance.ipynb).
It uses a different, rasterised phantom; do not pool its timings with the
continuous-phantom scaling study.

The published, executed notebook tutorials live in
[the documentation how-to section](https://docs.pymedphys.com/en/latest/users/howto/index.html),
under `lib/pymedphys/docs/users/howto/`.

The notebooks in `drafts/` are unfinished experiments and are not executed by
the documentation build. Some use namespaces that have since been removed
(`pymedphys.labs` and `pymedphys.wlutz`) or deprecated (`pymedphys.mudensity`,
superseded by `pymedphys.metersetmap`). They are retained as historical development material, not current installation or API
instructions.

`github-issue-responses/` contains examples written for specific issue
discussions; the Winston–Lutz notebook deliberately targets an old development
release. Check its package versions and linked discussion before using it.

The separate `stackoverflow/gamma.py` example is exercised by the integration
workflow. That does not validate the draft or issue-response notebooks.
