# Architecture and repository map

This guide is for contributors navigating the current source checkout. After
[setup](../start/setup.md), use it to identify the public entry point,
implementation, tests, documentation, and generated inputs for a change.
[Feature anatomy](feature-anatomy.md) traces those connections in detail.

## Find the part you need

| Location | Responsibility |
| --- | --- |
| `lib/pymedphys/__init__.py` and public modules such as `dicom.py`, `trf.py`, and `mosaiq.py` | Names callers import; these expose implementations and public wrappers. |
| `lib/pymedphys/_<feature>/` | Private implementation packages, such as `_gamma/`, `_dicom/`, `_mosaiq/`, and `_trf/`. |
| `lib/pymedphys/_base/` and `_delivery.py` | Common delivery representation and the assembled `Delivery` class. |
| `lib/pymedphys/cli/` and `__main__.py` | Argument definitions, command registration, and CLI startup. |
| `lib/pymedphys/_streamlit/`, `_app.py`, and `_gui.py` | GUI index, apps, shared presentation helpers, and launch behaviour. |
| `lib/pymedphys/_experimental/` and `experimental/` | Experimental implementations and their exposed interfaces. Read their documented scope before relying on them. |
| `lib/pymedphys/tests/`, root package `conftest.py`, and `_mocks/` | Feature tests, shared pytest behaviour, and reusable mock data. |
| `lib/pymedphys/_imports/`, `_extras.py`, and `_dev/import_policy.py` | Lazy optional imports, missing-package messages, and importability rules. |
| `lib/pymedphys/_data/` | Download registries, verified data cache, and archive handling. |
| `lib/pymedphys/_dev/` | Documentation preparation, test runner, dependency propagation, and standard-derived generators. |
| `lib/pymedphys/docs/` | Checked-in documentation sources and locally generated build output. |
| `examples/` | Runnable examples, benchmark tooling, and drafts with their own scope. |
| `.github/workflows/`, `.github/actions/`, and `.github/scripts/` | CI, release automation, setup/cache actions, selection policy, and distribution checks. |
| `docker/mosaiq/` | Local mock SQL Server recipe used for database development. |
| `site-specific/` | Site-specific examples; understand their scope before treating them as a general deployment recipe. |

The repository-root `docs` is a symlink to `lib/pymedphys/docs`. Edit the real
directory; documentation generation and package selection use it explicitly.

## Root configuration and generated files

| File | Source of truth or generated output |
| --- | --- |
| `README.rst` | Repository introduction; a marked section is imported into the documentation homepage. |
| `CONTRIBUTING.md` | Contributor policy; copied to the documentation's `contrib/index.md`. |
| `CHANGELOG.md` | Release notes; copied to documentation `release-notes.md`. |
| `pyproject.toml` | Package metadata, supported Python, dependencies, build targets, and tool configuration. |
| `uv.lock` | Resolved extras and dependency groups. Regenerate with uv rather than editing by hand. |
| `requirements.txt`, `pyproject.hash`, `lib/pymedphys/dependency-extra.txt`, and `_version.py` | Outputs of `pymedphys dev propagate`. Change their inputs and regenerate them together. |
| `.pre-commit-config.yaml` | Hooks and file-format exclusions. |
| `.readthedocs.yml` | Environment and build procedure for the published documentation. |
| `lib/pymedphys/docs/_config.yml` | Documentation configuration; `conf.py` is generated from it and ignored by Git. |
| `LICENSE`, bundled licence files, and `pyproject.toml` licence metadata | Distribution licensing, including vendored code and data. |

Standard-derived tables have their own source records and generators.
For example, de-identification tables are generated from reviewed DICOM sources,
and the documentation's requirements matrix is generated from
`_dicom/deidentify/requirements.toml`. A generated matrix without test reports
describes traceability, rather than claiming those tests passed.
Use the [design document](../design/deidentification/index.md) before changing
these sources or outputs.

## Public interfaces and shared delivery data

Private implementations let an API, a command, and a GUI share calculations.
The public module is the place to find the supported import and any public
wrapper behaviour, including warnings. Changes to a private function can still
affect several public workflows; trace its callers before changing a return
shape, coordinate order, or file format.

`Delivery` unifies delivery data from DICOM, TRF, Mosaiq, Monaco, and iCOM.
`_base/delivery.py` defines the common fields (`monitor_units`, `gantry`,
`collimator`, `mlc`, and `jaw`); `_delivery.py` assembles the format readers
and processing mixins into the exported class. Preserve the relationships
between control points and these arrays when working on a reader.

Vendor integrations have different external boundaries: Mosaiq uses SQL Server,
Monaco and TRF read vendor-specific files, Pinnacle exports treatment-planning
data to DICOM, and iCOM reads delivery messages. A test of a shared calculation
does not by itself establish native-format compatibility. See
[scientific evidence](../validation/scientific.md) and
[fixture choice](../validation/data.md).

## Dependencies and environments

**Extras** under `[project.optional-dependencies]` are published with the package.
**Dependency groups** under `[dependency-groups]` are for source-checkout work
and are not published. `uv.lock` resolves both.

| Published extra | Scope |
| --- | --- |
| `user` | Library, CLI, and GUI feature dependencies; the recommended broad user install. |
| `ai` | Opt-in Anthropic dependencies for the experimental Mosaiq chat app and SQL agent. |
| `tests` | `user` plus the packages needed to run the installed test suite. |
| `all` | `user`, `ai`, and `tests`. |
| `gamma`, `dicom`, `mosaiq`, `icom`, `trf` | Public functions and commands for one feature; plotting helpers, private code, and the GUI need the broader `user` environment. |
| `cli` | Alias for `user`, because the CLI spans features. |

| Checkout group | Scope |
| --- | --- |
| `dev` | Default group: every PyMedPhys extra plus `docs`, `lint`, and `pre-commit`, giving a complete contributor environment. |
| `docs` | Documentation build and the dependencies executed notebooks need. |
| `lint` | Linters, type checkers, and stubs. |
| `pre-commit` and `script-tests` | The small locked sets installed by those CI jobs. |
| `test-runner` | pytest and test-side packages without a feature's dependencies, used to test narrow extras. |
| `mosaiq-db-fixtures` | Packages for loading the mock database, used with `mosaiq` and `test-runner`. |

CI installs only the extras and groups each job needs through the
`extras`/`groups` inputs of `.github/actions/setup-project`, which passes
`--no-default-groups`. A working broad development environment therefore cannot
prove that a narrow extra or the `docs` group is complete.

[Lazy imports and optional dependencies](../info/lazy-imports.md) is the
canonical explanation of import registration, import-time restrictions, and
missing-package messages. Use it when adding a package or changing imports.
The [dependency recipe](../guides/make-a-change.md#add-or-update-a-dependency)
explains regeneration; [dependency maintenance](../maintainers/dependencies.md)
covers the CI floors and automated update review.

## Packaging and checks

Hatchling builds the distributions declared by `pyproject.toml`. `uv build`
builds the source distribution and then the wheel from it, so an omitted source
input can affect both. Package selection is defined per target; this avoids
the root documentation symlink interfering with included sources.

Read [distribution checks](../maintainers/release.md#verify-packaging-before-a-release) before
changing build filters, licence metadata, or distribution content. Tests must
also work inside an installed wheel; the [testing guide](../validation/testing.md#keep-tests-runnable-from-an-installed-wheel)
explains that boundary. Published-release verification and recovery belong in
[release](../maintainers/release.md) and [recovery](../maintainers/recovery.md).

```{toctree}
:maxdepth: 1

feature-anatomy
../info/lazy-imports
../info/file-structure
```
