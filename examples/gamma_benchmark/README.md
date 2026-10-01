# PyMedPhys gamma benchmark

Compare `pymedphys.gamma` across named versions, branches, or local checkouts,
or compare the SciPy and PyMedPhys interpolators in one checkout, using saved
workload plans and verified, paired timings.

The [comparison guide and measurement protocol](../../lib/pymedphys/docs/contrib/info/gamma-benchmark.md)
cover setup, configuration, workload design, running and resuming comparisons,
and interpretation of the offline report. Run commands from the repository root:

```console
uv run python examples/gamma_benchmark/gamma_benchmark.py --help
```

`init`, `plan`, `matrix`, `check`, and `report` prepare or inspect work without
importing PyMedPhys. Only `run` executes gamma. The [matrix-design.json](matrix-design.json)
file contains a factorial-design template. Generate an editable configuration
and preset plan with `init`.
