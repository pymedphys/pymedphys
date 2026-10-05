# Recover a release

For release maintainers diagnosing failed publication or verification. The existing [release procedure](../info/release-guide.md) remains authoritative for the full sequence.

**Prerequisites:** the tagged revision, Release run, access to relevant settings and the original built artefacts. **Inputs:** failed job logs, published filenames and SHA-256 hashes. **Outputs:** a verified recovery of that release, or a separately versioned corrective release. **Success:** Release Summary passes and its record is attached to the release PR; already published files retain their exact original bytes.

## Recover from failures

| Symptom | Action |
| --- | --- |
| No Release run started after publishing the GitHub release | Check that Actions is enabled and that `release.yml` at the tagged commit is valid. Then delete the GitHub release, keeping its tag, and publish a new release from the same tag. |
| The deployment is rejected by environment protection rules | Add or correct the `v*` tag rule on the `pypi` environment, then re-run the failed jobs. |
| PyPI reports `invalid-publisher` | Correct the owner, repository, workflow filename, or environment in PyPI's trusted publisher, then re-run the failed jobs. |
| The build job fails the tag check, or a test fails before publishing | This attempt did not publish. Re-run a download or network failure once. Otherwise check all earlier attempts, other runs for this version, and PyPI before deciding whether the version is unused. For a code or version change, keep the tag, fix the cause on `main`, and release a new version through the same procedure. |
| A failed run can no longer be re-run (GitHub allows 30 days) | If no file of this version reached PyPI, delete the GitHub release, keeping its tag, and publish a new release from the same tag to start a fresh run. Otherwise recover the original files as described below. |
| The upload failed before any file reached PyPI | Fix the cause, then re-run the failed jobs. |
| Only one of the two files reached PyPI | Re-run the failed jobs. The publish step skips files already on the index, and the **Verify published** jobs then confirm that both files match the build. |
| A **Verify published** job failed | The release is on PyPI, but the release assets are not uploaded. Inspect the job's log and its `install-reports` artefact to distinguish index propagation, network or certificate errors, dependency or build-tool failures, and defects in the package. Re-run transient failures. A SHA-256 mismatch means the built and published bytes differ; keep the original files and investigate before retrying or changing the release. |
| A **Test published** job failed | The release is on PyPI, and its assets were uploaded once verification passed. Inspect the job's log and its `test-reports` artefact. Re-run a data download or network failure once. A genuine failure with freshly resolved dependencies that passed with `uv.lock` usually comes from a new dependency release: constrain it on `main` and publish a new version. Yank the release if it is unusable. |
| `upload-release-assets` failed, including its read-back check | Re-run only that job while the original `dist` artefact is available. It replaces the assets with the verified files and does not publish to PyPI. |
| **De-identification requirements matrix** failed | Publishing is unaffected, and the matrix, if written, is attached and lists the traced tests that did not pass. Its summary also names any environment whose report is missing; re-run the failed unit-test jobs, which re-runs this one after them. A failed unit test fails the release anyway. A skip, or a test or case missing from one environment's report, is a gap in the release's de-identification evidence: fix the test or the register on `main`. |
| **Attach the requirements matrix** failed, including its read-back check | Re-run only that job while the run's `deid-matrix` artefact is available. It replaces the attached matrix. |

Re-run failed jobs, not the whole workflow: re-running failed jobs reuses the original run's `dist` artefact, retained for 30 days. A whole-workflow re-run rebuilds the files, and even unchanged source can produce different archive hashes when the build backend or environment changes.

If the artefact is unavailable, recover the original archives from the GitHub release assets or a retained copy, and require the files on PyPI to match them. GitHub's automatic **Source code** archives are repository snapshots, not the sdist.

```bash
gh release download vVERSION --pattern "pymedphys-*" --dir release-assets
uv run --no-project --python 3.14 python .github/scripts/check_distributions.py --published VERSION --compare-with release-assets
```

For missing GitHub assets, the original archives can also be downloaded from the URLs in pip's installation reports; verify them this way before attaching them with `gh release upload vVERSION release-assets/*`. If a PyPI upload is incomplete and the original files cannot be recovered, publish a new version. Keep the existing tag and release record; a fresh rebuild is not a replacement for the original files.

A published release cannot be replaced. To fix one, publish a new version through the same procedure: the next `.devN` for a development release, or the next patch version for a stable release. [Yank](https://pypi.org/help/#yanked) a broken release on PyPI rather than deleting it, so that installs pinned to it still work.


Keep the recovery record with the release, including failed and retried jobs, the retained original artefacts and verified file hashes. Recheck this procedure when publication or verification logic changes.
