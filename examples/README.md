# Example status

`gamma_performance.py` is a runnable old-versus-new gamma benchmark. From the
repository root, with the PyMedPhys environment active, run
`python examples/gamma_performance.py`. It prepares temporary checkouts of
previous main and committed HEAD, checks complete gamma-array equality, and
saves a labelled PNG/SVG comparison with the raw timings and source provenance.
Use the saved PNG directly when sharing your workstation's results. See
[Faster gamma calculations: a reproducible benchmark](https://docs.pymedphys.com/en/latest/contrib/info/gamma-performance.html)
for workloads, methodology and interpretation; `--help` lists the options.

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
