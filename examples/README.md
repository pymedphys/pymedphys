# Example status

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
