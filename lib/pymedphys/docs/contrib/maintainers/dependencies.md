# Review dependency updates

For maintainers reviewing the weekly dependency PR or an unexpected package change.

**Prerequisites:** the PR diff and its current workflow results. **Inputs:** `uv.lock`, declared constraints, propagated requirements and validation logs. **Outputs:** a reviewed dependency change or a separately scoped corrective PR. **Success:** the full diff is understood and required checks pass for the version set being merged.

The `deps.yml` workflow upgrades the lockfile, syncs and propagates exports, validates tests, documentation and a clean wheel installation, and opens or updates `deps/weekly-update` only after validation. The `dependencies` and `full-test` labels request broader CI. No changed lockfile produces no PR. A missing PR can also mean failed validation or bot authentication: inspect the run.

Follow the [detailed dependency review checklist and shell examples](../info/dependency-update-prs.md). Inspect the full diff, rather than relying on the PR body's summary. Unexpected additions, removals or major upgrades, and changes to numerical, DICOM or packaging libraries, require investigation of their consumers and evidence. Resolve an unrelated runtime defect in a prerequisite PR.

Dependency automation's implementation and pinned actions are documented in [Maintain CI](ci.md). Recheck this guide whenever `deps.yml`, constraints or dependency propagation changes.

```{toctree}
:hidden:

../info/dependency-update-prs
```
