# Releases, compatibility and migration

For users maintaining an installed workflow and contributors interpreting current support rules. Canonical inputs are README, `pyproject.toml`, SECURITY and CONTRIBUTING; review this page whenever those change.

## Confirmed current rules

- PyMedPhys remains in beta while its version is `0.x`. APIs are not guaranteed stable between releases; minor releases may contain breaking changes. Consult the [release notes](../release-notes.md), pin the version used by a validated workflow and verify its results when upgrading.
- Current source declares Python `>=3.11.4` and tests Python 3.11, 3.12, 3.13 and 3.14. The quick unit matrix uses 3.14; broader matrices exercise all four. An interpreter requirement is not a promise that every optional dependency supports every future Python version.
- Only the latest release receives security fixes, as specified in [SECURITY](https://github.com/pymedphys/pymedphys/blob/main/SECURITY.md#supported-versions). Upgrade before reporting an issue that cannot be reproduced on the current version.
- Development releases use `.devN` versions and require an explicit version or a suitable `--pre` constraint. Stable and development release procedures are in [Release PyMedPhys](../contrib/maintainers/release.md).
- Do not deprecate an interface until its replacement and migration guidance are released. Known limitations may be documented earlier. See [CONTRIBUTING](../contrib/index.md#open-and-review-a-pull-request).
- `master` and the existing release-maintenance branches are read-only history. New work is based on `main` or a named parent PR branch.

## Upgrade a validated workflow

**Prerequisites:** the current environment/version record and approved representative inputs. **Inputs:** release notes, pinned dependencies and baseline results. **Outputs:** a separately installed candidate environment and a comparison record. **Success:** supported inputs produce the expected results within justified tolerances, migration steps are recorded and downstream callers work.

1. Read all release notes between the installed and candidate versions, beginning with warnings and potentially breaking changes.
2. Create a separate environment using [Installation options](../users/get-started/installation-options.md). Install the candidate version explicitly and record optional extras and resolved dependencies.
3. Run the workflow with synthetic or approved representative inputs. Check units, coordinate conventions, failures and expected outputs, using independent references when results are scientific.
4. Apply the release's migration instructions to callers and configuration; record result differences and review them before adopting the version.

## Pending decisions

The historical [maintainer/support/1.0 proposal in #1376](https://github.com/pymedphys/pymedphys/issues/1376) is a discussion, not a replacement for current policy. Long-term support commitments, appointment rules and a stable 1.0 compatibility policy remain pending unless adopted through an explicit policy change. This restructure does not adopt them.

Track release guidance and unresolved release support in [#2140](https://github.com/pymedphys/pymedphys/issues/2140), and documentation completeness in [#1665](https://github.com/pymedphys/pymedphys/issues/1665). Describe current, experimental and planned functionality separately in each feature's guide.
