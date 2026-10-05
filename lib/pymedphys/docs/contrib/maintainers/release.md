# Release PyMedPhys

For maintainers preparing and verifying stable or development releases. Follow the [existing release checklist and procedure](../info/release-guide.md) in order; it retains version selection, changelog preparation, tagging, deployment approval, verification and next-version steps.

**Prerequisites:** a tested revision on `main` and the publishing access described in the procedure. **Inputs:** canonical version, changelog, source revision and release artefacts. **Outputs:** verified PyPI distributions, GitHub assets and a release record. **Success:** `Release Summary` passes, the record is posted on the version-setting PR and `main` carries its next unpublished development version.

## Verify packaging before a release

The release workflow builds an sdist and a wheel from that sdist, rather than relying on a wheel built only from the checkout. Hatchling's sdist and wheel include rules are independent; the root `docs` symlink does not replace explicit inclusion of `lib/pymedphys/docs`. Tests and the canonical de-identification decisions must be available in installed-package checks.

```shell
uv build
uv run --no-project --python 3.14 python .github/scripts/check_distributions.py dist
```

The build directory is positional. `--expected-version VERSION` also checks the intended version; `--skip-install` checks archive contents only and leaves wheel installation unverified. The checker's isolated installation avoids the checkout and inherited Python/pip configuration, except documented network settings. Inspect its output and exit status. Verify any changed include rules against both archive contents and actual installation. Retain bundled-data licences and licence metadata under PEP 639.

Version metadata, filenames and tags must agree in canonical PEP 440 form. PyPI rejects reuse of a filename, including a deleted file. Published verification installs exact wheel and sdist URLs and checks them against the artefacts built earlier; fresh dependency resolution in published tests is a separate check.

After publishing, `--published VERSION --compare-with dist` verifies the files on PyPI against retained original distributions. Add `--report-dir reports` to retain its installation reports and logs, and `--summary release-verification.md` to append a Markdown verification record. These options apply only with `--published`; `--tests` additionally runs the installed wheel's test suite with freshly resolved dependencies. Follow the release procedure's post-publication sequence and retain its record.

The release summary's `needs` must include every job needed to establish success. A standalone green publish job or GitHub release is insufficient. Keep release-specific requirements outcomes with their release, distinct from the generated documentation matrix. See [Requirements and evidence](../design/deidentification/requirements.md).

## Related procedures

- [Prepare, publish and record the release](../info/release-guide.md).
- [Recover a release](recovery.md), preserving original artefacts after partial uploads.
- [Understand selected checks](pr-checks.md) and [Maintain CI](ci.md).
- [Current compatibility and migration rules](../../project/compatibility.md).

Recheck this guide when build filters, licence inclusion, version propagation or release workflows change. Release support gaps are tracked in [#2140](https://github.com/pymedphys/pymedphys/issues/2140).

```{toctree}
:hidden:

../info/release-guide
```
