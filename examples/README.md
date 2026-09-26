# Example status

`gamma_scaling.py` runs a four-way gamma performance study: previous and current
PyMedPhys source, each with the PyMedPhys and SciPy interpolators. From the
repository root, with Git and a Python 3.12 environment available, run:

```console
python -m pip install -r examples/gamma-scaling-requirements.txt
python examples/gamma_scaling.py --output gamma-scaling-run
```

The defaults cover 2D and 3D, three gamma settings, five grid sizes and four
balanced rounds, reaching 16,080,100 points in 2D and 13,242,240 in 3D. Allow
several hours and substantial free memory. Each worker has a one-hour timeout,
including its full warm-up and timed call. The 1.5 GiB RAM chunk budget is not
a cap on total memory use. A small installation check is:

```console
python examples/gamma_scaling.py --dimensions 2 3 --profiles global cap2 local --scales 0.02 --round-indices 0 --output gamma-scaling-smoke
```

The runner creates temporary detached checkouts of previous main and committed
HEAD and checks every gamma-array element. It preserves your working files;
uncommitted library changes are not measured. Both commit objects must exist
locally. Use `--previous-ref`, `--current-ref`, `--threads`, `--ram-mib` and
`--worker-timeout` to select revisions and resources; `--help` lists all options.
Install the requirements in a separate environment if you need to preserve an
existing environment's package versions.

Each profile produces a labelled PNG/SVG with absolute seconds on logarithmic
axes and new/old runtime ratios. `results.json` retains every measurement,
numerical check and source/environment record; `timings.csv` and `summary.csv`
make the values easy to inspect. Share the saved PNG directly, with the JSON,
rather than relying on a screenshot. Only verified four-way comparisons enter
the figures, and incomplete groups are reported explicitly.

Results are checkpointed after each worker. Resume an interrupted default run
with `python examples/gamma_scaling.py --resume gamma-scaling-run`; repeat the
same study options when resuming a customised run. Resume requires the same
host, revisions and benchmark source. To regenerate figures without measuring
again, use `--plot-only gamma-scaling-run/results.json --output gamma-scaling-plots`.

The opt-in `Gamma performance study` workflow runs the full study on GitHub
Actions when a `benchmarks/gamma-*` branch is pushed. Its matrix keeps all four
implementations on the same runner within each round, saves partial results,
and combines the verified observations. Ordinary PR pushes do not launch it.
The notebook identifies the canonical cloud run for PR #2066. See
[Faster gamma calculations: a reproducible benchmark](https://docs.pymedphys.com/en/latest/contrib/info/gamma-performance.html)
for workloads, methodology, recorded results and interpretation.

`gamma_performance.py` retains the earlier six-workload benchmark at fixed grid
sizes. It uses a different, rasterised phantom and its timings should not be
pooled with the continuous-phantom scaling study.

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
