# Example status

`gamma_scaling_background.py` runs the comprehensive gamma performance study
in the background, with progress reporting, stop/resume and one upload ZIP:

```console
python -m pip install -r examples/gamma-scaling-requirements.txt
python examples/gamma_scaling_background.py --output gamma-scaling-local
```

Run from the repository root. The study compares old/new PyMedPhys and SciPy
paths across 30 workloads, four balanced rounds and grids up to 100 times the
former maximum. It records absolute times, plots logarithmic scaling curves,
and checks every gamma value. Allow many hours and substantial free memory.

See [the workstation study guide](../lib/pymedphys/docs/contrib/info/gamma-performance-study.md)
for methodology, installation checks, resource settings, progress, stop/resume
and exactly which artefact to upload. `gamma_scaling.py` remains available for
foreground runs, custom study selections, combining parts and plot-only mode.

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
