# AGENTS.md

Guidance for every coding agent working in this repository. Follow it, and
the [contributor language policy](CONTRIBUTING.md#language), for every change.

## Development Commands

### Setup and Installation

```bash
# Install with uv (required for development)
uv sync --python 3.14 --locked --extra all --group dev

# Install pre-commit hooks
uv run -- pre-commit install

# Install for user use only
python -m pip install "pymedphys[user]"
```

### Testing

```bash
# Run default tests (slow/database selection has separate options)
uv run -- pymedphys dev tests

# Run specific test file or directory (relative to lib/pymedphys or the cwd)
uv run -- pymedphys dev tests tests/path/to/test.py

# Run with specific pytest options
uv run -- pymedphys dev tests -v -s -k "test_name"

# Add the slow tests to the default selection, or run only the slow tests
uv run -- pymedphys dev tests --include-slow
uv run -- pymedphys dev tests --slow

# Run tests in parallel, one worker per CPU (pytest-xdist)
uv run -- pymedphys dev tests --slow -n auto

# Run doctests
uv run -- pymedphys dev doctests
```

### Code Quality

```bash
# Run linting with ruff (automatically fixes issues)
uv run -- ruff check --fix .
uv run -- ruff format .

# Run type checking with pyright
uv run -- pyright

# Run pre-commit on all files
uv run -- pre-commit run --all-files

# Check imports are clean
uv run -- pymedphys dev imports
```

### Documentation

```bash
# Build documentation
uv run -- pymedphys dev docs

# The docs use Jupyter Book and are located in lib/pymedphys/docs/
```

Documentation notebooks must use declared, locked dependencies rather than
installing packages while running. Add documentation dependencies to both the
`docs` and `all` extras and regenerate `uv.lock`; CI and ReadTheDocs both
install the documentation environment from it.
Unexpected notebook errors and documentation build warnings fail the build.
An install cell kept for readers running a notebook elsewhere (for example on
Colab) must carry the `skip-execution` cell tag. Sphinx configuration is
generated into `lib/pymedphys/docs/conf.py` from `_config.yml`; the generated
file is gitignored, so edit `_config.yml`.

Write procedures as instructions with their success criteria. State each
fact once and link to it, prefer fixing a defect over documenting a workaround
for it, and keep incident history and evidence caveats on the pull request
rather than in the guide. Open a long procedure with a short checklist for
readers who already know it, and move one-time setup into an appendix.

Documents, decision logs, changelog entries, and pull request descriptions
describe the state being merged. Fold revisions made while a pull request is
open into the text; do not record them as superseded decisions, review logs,
or construction history.

Write changelog entries as informative release notes: state what changed, its effect, and what users should do, in declarative sentences. Do not phrase entries as answers to review questions or pre-empt objections ("is not limited to ...", "does not use ...", "has not been measured"); state the scope directly instead. When a fix changes results that earlier versions returned without an error, open the release section with a warning that says which inputs and functions were affected, by how much, and what to re-check, and also list the changed results and any changed return shapes or array order under (Potentially) breaking changes.

Use ordinary Markdown links in Markdown pages and notebook Markdown cells.
Follow the relative source-path and published-URL guidance in
[Writing portable links](lib/pymedphys/docs/contrib/info/docs-guide.rst#writing-portable-links).

Historical, site-specific deployment pages (for example the iCom listener,
tunnelling, and rsync how-tos) record what was done at the time. Do not
modernise, correct, or test their commands, versions, or links. Keep their text
as originally written, or at the latest as it stood before the September 2025
switch from Poetry to uv, and confine changes to a note marking the page as a
historical record.

## Architecture Overview

### Project Structure

PyMedPhys is a medical physics library organised as follows:

- **lib/pymedphys/**: Main library code
  - `_<module>/`: Private implementation modules (e.g., `_dicom/`, `_gamma/`, `_mosaiq/`)
  - `<module>.py`: Public API modules that expose the private implementations
  - `cli/`: Command-line interface implementations
  - `tests/`: Test suite organised by module
  - `_experimental/`: Experimental features not yet stable
  - `_streamlit/`: Streamlit web app components

### Project Maintainers

PyMedPhys is maintained by:

- SimonBiggs
- sjswerdloff
- Matthew-Jennings
- pchlap

Use this list wherever metadata needs the maintainers.

### Key Architectural Patterns

1. **Private/Public Module Pattern**: Implementation details are in `_module/` directories, with public APIs exposed through `module.py` files at the package root.

2. **Delivery Abstraction**: The `Delivery` class (`_base/delivery.py`) provides a unified interface for treatment delivery data from various sources (DICOM, TRF files, Mosaiq, Monaco).

3. **CLI Architecture**: The CLI is modular with subcommands defined in `cli/` subdirectory. Each major feature has its own CLI module (e.g., `dicom_cli`, `trf_cli`).

4. **Data Management**:
   - External data is managed through Zenodo with hashes stored in `_data/hashes.json`
   - The `_data` module provides utilities for downloading and caching external datasets

5. **Vendor-Specific Integrations**:
   - **Mosaiq**: SQL-based integration for Elekta's oncology information system
   - **Monaco**: Support for Elekta Monaco treatment planning system files
   - **Pinnacle**: DICOM export functionality for Philips Pinnacle
   - **iCOM**: Real-time treatment delivery monitoring for Elekta linacs

### Testing Strategy

- Unit tests are in `lib/pymedphys/tests/` mirroring the source structure
- Tests use pytest with fixtures defined in `conftest.py`
- `pymedphys dev tests` changes the working directory to `lib/pymedphys` before
  invoking pytest, so relative output paths (e.g. `--junitxml`) resolve there.
  Use absolute paths in CI. Test paths may be given relative to `lib/pymedphys`
  or to the caller's directory; the whole package is collected only when no
  path is given. Resolve positional paths after pytest parses its arguments;
  do not maintain a list of value-taking options, since plugins can add more.
  The `pymedphys._dev.pytest_paths` plugin does this in the controller and in
  every pytest-xdist worker, which parse the original arguments again.
- Tests marked `slow` (and `mosaiqdb`, `anthropic_key`) are skipped by
  `conftest.py` unless requested. `--include-slow` (and `--include-mosaiqdb`,
  `--include-anthropic`) adds them to the default selection. `--slow` (and
  `--mosaiqdb`, `--anthropic`, `--pydicom`) runs only the tests with that
  marker; several of these select the union. `--all` runs everything.
  `pytest -m slow` alone selects the slow tests but still skips every one.
- CI runs the slow tests in parallel (`-n auto`), so keep every test
  independent of the others: no shared output paths or ordering assumptions.
  Processes that share the data cache take turns with each file, and with
  each archive from downloading or repairing it to extracting it, so
  concurrent `data_path` and `zip_data_paths` calls are safe.
- `[tool.pytest.ini_options]` in `pyproject.toml` enforces strict markers and
  strict xfail, and stops any test after 900 s (`pytest-timeout`). Register a
  new marker in `MARKER_CONFIG` in the root conftest.
- The root conftest points `HOME` and `USERPROFILE` at a temporary directory for
  the whole session, so tests never read or write the real `~/.pymedphys` or
  `~/.streamlit`. The Zenodo cache stays shared through `PYMEDPHYS_DATA_DIR`,
  which `pymedphys._data.download.get_data_dir` honours. Write test outputs to
  `tmp_path`, never beside cached data files.
- `dev tests` and `dev doctests` bypass user logging configuration during CLI
  startup, before pytest can isolate the home directory. Keep this boundary:
  opening a configured log can modify user files before any test runs.
- Data downloads require recorded hashes by default and never write to
  `hashes.json`; record the hash of every file added to `urls.json`.
  `check_hash=False` explicitly accepts unverified data. Archives extracted
  into the cache are refreshed when the archive changes, extraction metadata
  is missing or invalid, an archived member is missing, or a file's size no
  longer matches. Directories a caller chooses, such as the GUI demo's working
  directory, only gain missing files, so user edits there survive.
- Prefer small, deterministic local fixtures for regression tests. Before
  retiring download-backed tests, record the tested revisions, fixture
  provenance and results, and retain their useful coverage locally. Distinguish
  changed expectations from unchanged baselines and previously skipped tests.
- Mock data and fixtures are in `_mocks/` and test data directories
- Test coordinate and geometry code against values derived independently
  from the governing definition (for DICOM, the voxel position formula in
  PS3.3), on off-centre grids with non-square spacing and every supported
  orientation. Never use a stored snapshot of the implementation's own
  output as the expected value: such snapshots can enshrine sign errors.
- Keep the mapping from array dimensions to physical coordinates explicit
  when reordering or comparing grids. Matching coordinate sets alone does
  not justify combining array elements. Validate fixed geometry once before
  repeated numerical work, while retaining validation at public boundaries.
- When replacing established geometry code, preserve its validated behaviour
  and explain every intended difference with an independently worked example.
  Test physical invariance across storage orientations and different grid
  extents; self-comparisons alone can hide a shared error. Changelog impact
  statements must distinguish expected usage frequency from error severity
  and must not imply that unmeasured incidence is known.
- For coordinate fixes, trace and document the affected public workflows.
  Distinguish physical positions from array storage order, and state which
  coordinates belong to each returned array. Include plotting and indexing
  guidance when an ordering change affects existing callers.
- Keep floating-point round-off, small physical discrepancies and clinical
  significance separate. Dose-grid equality accepts up to 0.01 mm silently,
  warns but still accepts above 0.01 mm through 0.1 mm, and rejects larger
  mismatches, with a separate 1e-9 mm numerical allowance. Apply these absolute
  limits to the maximum 3D displacement of corresponding voxel centres across
  every dataset pair. Combine origin, spacing and original encoded direction
  cosines; snapping cosines before comparison can conceal a growing edge
  error. Acceptance does not resample a grid or assess clinical significance.
  Keep orientation rounding and absolute-offset metadata validation separate.
- The Streamlit GUI is tested headlessly with `streamlit.testing.v1.AppTest` in
  `lib/pymedphys/tests/streamlit/`: apps are driven by widget label and assertions
  read the rendered markdown. Data-driven scenarios use the
  `metersetmap-gui-e2e-data.zip` demo archive and run from a temporary working
  directory because the apps extract it into the current directory. The apps
  memoise `get_config` with `st.cache_data` for the life of the pytest process,
  so a fixture that serves a different configuration must clear `st.cache_data`
  on entry and exit. The root conftest also pins `MPLBACKEND=Agg`, because the
  apps draw matplotlib figures on the AppTest worker thread and the GUI backends
  abort the interpreter off the main thread.

### Dependencies and Extras

The project uses uv with optional dependency groups:

- `user`: Standard user installation
- `ai`: The Anthropic dependencies of the experimental Mosaiq chat app; opt-in, never part of `user`
- `all`: All features including development tools
- `dev`: Development tools (linting, formatting)
- `docs`: Documentation building
- `tests`: Testing dependencies
- Specific features: `dicom`, `mosaiq`, `icom`, etc.

### Packaging

- `uv build` makes the sdist and then the wheel from it, so a file missing from
  the sdist also breaks the wheel. Check a build with
  `python .github/scripts/check_distributions.py dist`, which also installs the
  wheel into a fresh virtual environment.
- Set Hatchling file selection per build target, never build-wide: a build-wide
  `include` is an allow-list that also replaces the sdist's contents. The sdist
  uses `only-include`, because a full-tree walk reaches the repository-root
  `docs` symlink first and then skips `lib/pymedphys/docs` as already seen.
- Declare the licence as a PEP 639 SPDX expression (`license = "..."`) that
  covers bundled third-party code as well as PyMedPhys's own, and list every
  licence file in `license-files`. Update both when vendoring code under a new
  licence or removing the last code under one. Treat bundled data, such as
  vocabularies, datasets, and tables generated from standards, like code:
  bundle it only under terms compatible with Apache-2.0, never under
  non-commercial or no-derivatives terms, and include any required
  attribution. Keep the independent licence
  expectations in `.github/scripts/check_distributions.py` and its test
  fixtures in sync with these settings. Check declarations as well as file
  presence, so removing a metadata entry cannot bypass the release guard.
- Keep `version` in `pyproject.toml` in canonical PEP 440 form (`0.42.0.dev0`,
  not `0.42.0-dev0`); the release tag must be `v` followed by it. The build
  check fails a non-canonical version before publishing, because Hatchling
  copies it into the metadata unchanged but canonicalises the filenames.
- Distribution smoke tests must ignore the caller's Python path overrides,
  run outside the checkout, and verify that package imports come from the
  test environment. A fresh venv alone does not isolate `PYTHONPATH`, and
  `python -I` does not isolate pip configuration. Disable pip configuration
  files and inherited behavioural `PIP_*` settings for installs and their
  build subprocesses; preserve only explicit network settings such as proxy,
  certificate, time-out, and retry settings.
- Include every root-level input to documentation preparation in the sdist:
  `README.rst`, `CHANGELOG.md`, and `CONTRIBUTING.md`.
- Keep `release-guide.md` and `workflows.md` aligned with `release.yml`,
  including pre-releases, publishing destinations, and post-publication checks.
  Record release-test evidence on the release pull request.
- Verify a release from the published files, not the checkout: install the
  wheel and the sdist separately into fresh environments outside the checkout,
  force the sdist to build, and check which file pip installed and where it
  came from. `check_distributions.py --published` does this, and with
  `--tests` also runs the test suite against the published wheel; the release
  workflow runs both after publishing, and `--summary` writes the report for
  the release pull request. Extend the script or the workflow rather than
  documenting manual steps.
- `Release Summary` fails unless every release job succeeded; add each new
  release job to its `needs`.
- Publishing a GitHub release or pre-release is the only way to publish.
  There is no manual or TestPyPI route, as the maintainers decided a library
  release needs no rehearsal beyond the checks before publishing; rehearse a
  change to the release pipeline with a development release on PyPI.
- Tag a commit on `main`: for a stable release, the merge commit of its
  reviewed release pull request, which is the state of `main` that CI tested,
  never a commit from the release branch. After publishing, a separate pull
  request sets `main` to the next unpublished `.devN`, so a development
  release (`X.Y.Z.devN`, a GitHub pre-release) can be tagged from `main`
  without a release pull request. Only a stable release pull request needs the
  `full-test` label, and changelog entries stay under `## Unreleased` until
  the stable release.
- The publish job uses `skip-existing`, so a re-run after a partial upload is
  safe; `verify-published` then requires the files on the index to match the
  build. Release asset uploads must wait for that verification, so a skipped
  duplicate cannot overwrite GitHub assets with different bytes. They must not
  wait for `test-published`, whose dependencies and datasets change outside the
  repository; keep it a separate job that reports to `Release Summary`.
- Resolve PyMedPhys's published archive from PyPI's JSON Simple API and
  install its exact URL, so no other configured index can substitute it.
- Recover releases using their original distribution files. A rebuild of the
  same tag can differ when the build backend changes. A failed retry does not
  prove earlier attempts left PyPI untouched; preserve release tags and use a
  new version for changed files.

## Important Implementation Notes

1. **Beta Status**: PyMedPhys is in beta (version 0.x.x). APIs may change between releases.

2. **DICOM Handling**: The library provides extensive DICOM functionality including anonymisation, coordinate systems, dose calculations, and RT plan manipulation. Use only pydicom APIs that pydicom 4 keeps:
   - write with `enforce_file_format=True`, not `write_like_original=False`;
   - set the encoding through the file meta Transfer Syntax UID, the `implicit_vr` and `little_endian` arguments of `save_as` and `dcmwrite`, or the `FileDataset` constructor, never the `is_implicit_VR` and `is_little_endian` attributes, and read a decoded dataset's encoding from `original_encoding`.

   The test suite fails on pydicom's "will be removed in v4" deprecation warnings. Some deprecated APIs do not warn, so test new code that reads or writes DICOM encodings with the `pydicom_behaviour` fixture (`lib/pymedphys/tests/dicom/conftest.py`), which also runs the test with pydicom's future behaviour, in which they raise. Do not run the whole suite with `PYDICOM_FUTURE`: in pydicom 3.0, `Dataset.pixel_array` itself fails with the future behaviour.

3. **Gamma Analysis**: Core functionality for dose distribution comparison using efficient shell-based algorithm implementation.

4. **Anthropic Integration**: The experimental Mosaiq chat app and its SQL agent (`_ai/`) call Anthropic's API and need an API key. Their dependencies are in the opt-in `ai` extra, so import them only where they are used, and keep the rest of the GUI loadable without them.

5. **Streamlit Apps**: Web-based tools for various tasks (anonymisation, metersetmap, dose analysis) in `_streamlit/apps/`. `pymedphys gui` serves them, and is meant to be run either on one computer or on a server that other computers connect to, for example within a radiotherapy department. Keep network serving supported; the GUI has no login, so document that anyone who can reach it can use its apps.

6. **Database Connections**: Mosaiq integration requires appropriate database credentials and SQL Server access.

7. **DICOM De-identification**: The replacement for `pymedphys.dicom.anonymise` and experimental pseudonymisation is specified in `lib/pymedphys/docs/contrib/info/deidentification-design.md`. Follow its decisions, and update it in any pull request that changes one. Outside the design document and its requirements register, describe what a decision requires rather than citing its number, since decisions may be renumbered or removed. In new or modified code that handles DICOM data:
   - never put source attribute values, keys, or original paths in logs, standard output or standard error, warnings, exception messages, output file or directory names, or reports; use attribute paths and opaque identifiers;
   - never describe output as "anonymised", or as "de-identified" without naming the PS3.15 edition, profile, and options it has been validated against;
   - never claim the Clean Pixel Data or Clean Recognizable Visual Features Options, or change Burned In Annotation or Recognizable Visual Features to NO;
   - regenerate rule tables generated from the DICOM standard, and vocabularies converted from source spreadsheets, with their generators; never edit them by hand.

## Common Development Patterns

When implementing new features:

1. Place implementation in appropriate `_module/` directory
2. Expose public API through module-level `__init__.py` or dedicated public module
3. Add corresponding CLI command if user-facing
4. Include comprehensive tests following existing patterns
5. Use type hints and follow existing code style
6. Document with docstrings following NumPy style

When modifying DICOM functionality, be aware of:

- Coordinate system transformations
- Anonymisation requirements
- VR (Value Representation) handling
- RT-specific DICOM objects (RTDose, RTPlan, RTStruct)

Prefer "slices" for spatial image and dose planes in identifiers, comments,
docstrings, and documentation. Preserve official DICOM attribute names such as
`NumberOfFrames` and `GridFrameOffsetVector`.

When you find unmaintained or non-functional material, such as a packaging
recipe that no workflow builds or a CLI command whose inputs no longer exist,
remove it (and anything that exists only to support it) rather than annotating
it as a draft. Git history preserves it. Do not write documentation that hedges
around code that cannot work; fix or remove the code in the same PR, and record
contributor-facing removals in `CHANGELOG.md`. Historical documentation pages
are different: keep them as originally written, as described above.

Justify every removal in its pull request with evidence for each item: when it
was added and by whom, its last functional change (excluding formatting, lint,
renames, and other repository-wide passes), what imports or tests it, and
whether it still imports or runs. Code under `_experimental` is expected to be
unfinished, so being experimental or unfinished is not on its own a reason to
remove it; say plainly when removal is optional rather than required, and keep
anything with callers, tests, or recent functional changes.

### Copyright Headers

Most source files open with one or more `# Copyright (C) <years> <authors>` lines above the Apache 2.0 notice, one for each meaningful contribution.

- When a change is meaningful, credit its author in the header of each file it touches. For agent-assisted work, that is the person who directed it.
- Put a new line above the existing ones (newest first). If the author already has a line of their own, extend its years instead (`2025-2026`, `2021, 2025`). Leave joint lines unchanged.
- A change is meaningful when the author's net surviving contribution to the file is about 15 or more added or rewritten lines, cumulative across PRs. Mechanical edits do not count: API renames, import reordering, lint, typing-only and formatting fixes, and `nosec` comments.
- A new file starts with the full header, crediting its author and the current year. Do not add a header to an existing file that has none without the maintainers' agreement, since it must also credit the original authors.
- Every PyMedPhys copyright header must have the full Apache 2.0 licence
  notice immediately below its copyright lines, including when adding a
  header to an existing file. Preserve upstream licence and attribution
  notices in third-party code.

## Agent Workflow Guidelines

### Recording Maintainer Guidance

When maintainers give guidance that applies to future work, apply it to the
current task and record it where it belongs:

- guidance for every coding agent goes in `AGENTS.md`;
- guidance for one agent goes in that agent's file, such as `CLAUDE.md` for
  Claude Code;
- decisions for one programme of work go in its design document, and decisions
  for one change go in its pull request;
- rules for all contributors go in `CONTRIBUTING.md`, linked from here rather
  than restated;
- a maintainer's personal preferences, such as which areas they work on, stay
  in that person's own agent settings and never go in the repository.

Keep agent files to broadly applicable guidance: no one-off solutions or
detailed explanations of individual features.

### Pull Requests

- Before opening or updating a pull request, read and follow
  [Open and review a pull request](CONTRIBUTING.md#open-and-review-a-pull-request).
- Write pull request descriptions, issues, and reviews for the readers
  described there: a plain summary and concrete examples first, and the
  technical detail in a labelled section after them. When reviewing, use CI's
  results for the reviewed commit instead of repeating its checks.
- When a pull request's scope changes after it is opened, update its title and
  description to match the current diff and the validation actually run.
- Before a pull request exists, link a comparison against its actual base:
  `https://github.com/pymedphys/pymedphys/compare/<base>...<your-branch>`,
  where `<base>` is `main` unless the pull request is stacked on another
  branch. Use three dots (`...`), not two. Once the pull request exists, link
  it as `https://github.com/pymedphys/pymedphys/pull/<number>`.
- Quote branch names from `git status` or the remote, not from memory.

### CI Gates and Review Policy

- Optimise CI and releases without reducing validation: skip only checks whose
  inputs are known to be unaffected. Unknown paths select every standard check;
  symlinks, submodules and an unverifiable diff select every check a path can
  select. Integration and database tests and the full unit-test matrix are
  cost-gated, as the maintainers decided: beyond main and the `full-test` and
  `database` labels, integration and database tests run only for the inputs
  that no standard check validates, listed in `select_checks.py`. Add an input
  there when only a cost-gated job validates it. Packaging filters, slow-test
  modules, modules with doctests, and shared test fixtures and data are
  integration inputs. Policy tests require `SLOW_TEST_FILES` and `DOCTEST_FILES`
  to equal what a scan of the package finds, so update them in the pull request
  that adds, removes or renames such a module. `select_checks.py` alone reads
  labels, and a missing selection output must mean more validation, never less.
  Keep selection and summary conditions identical, with regression coverage for
  deletions, renames and missing outputs. Release optimisation must retain
  fresh package verification and every publishing gate.

- Main requires the GitHub Actions checks `CI Summary` and `Security Summary`.
  Keep these names unique across workflows; the release report is named
  `Release Summary`. Keep all constituent checks visible and add every new
  blocking job to the appropriate summary's `needs`.
- Document CI coverage, advisory exceptions, and check-name migrations in
  `lib/pymedphys/docs/contrib/info/workflows.md`.
- Non-admin collaborators with Write access may merge approved PRs. Admins may
  bypass the review ruleset for PR merges but not the separate CI ruleset.
- Keep stale-approval dismissal and last-push approval requirements off, as
  requested by the maintainers. Encourage renewed review for substantive
  changes without automatically discarding existing approvals.

### Security Scanning Policy

- `security.yml` runs three scanners through `uvx` at pinned versions: pip-audit
  on the exported lockfile, Bandit on the package, and zizmor on the workflows.
  The dependency audit is advisory on pull requests and pushes and blocking on
  scheduled and manual runs, where a failure opens or updates the issue labelled
  `security-audit`. Bandit and zizmor block on every event.
- Workflow files staged in `claude_created_workflows_preview/` are unclassified
  inputs to `.github/scripts/select_checks.py` and select every scan. Zizmor
  audits them in place, so a staged workflow must be clean before a maintainer
  moves it.
- Bandit is configured in `[tool.bandit]` in `pyproject.toml`: tests are excluded
  and a reviewed list of low-severity checks is skipped. Fix any other finding.
  Where a finding is a false positive, put the justification in a comment on the
  line above and a bare `# nosec Bxxx` on the offending line (Bandit treats words
  after the code as test names). Never widen the skip list to make a run green.
- Workflows must pass zizmor at medium severity: pass inputs, matrix values, and
  step outputs to `run:` blocks through `env:` rather than `${{ }}` expansions,
  set `persist-credentials: false` on checkouts that do not push, keep write
  permissions at the job level, and pin every action to a commit SHA with the
  exact upstream tag name as the trailing comment (`# v6.0.2`, never `# 6.0.2`).
  The online `ref-version-mismatch` audit resolves that comment as a ref in the
  action's repository and fails the Workflow Audit job when it does not exist or
  points at a different commit. The pre-commit zizmor hook runs the offline
  audits only and cannot check this, so confirm a new pin with
  `git ls-remote --tags https://github.com/<owner>/<repo> | grep <sha>` before
  pushing.
- Secret scanning and push protection are GitHub repository settings, not
  workflow jobs.

### Dependency Updates

When updating dependencies:

1. Update version constraints in `pyproject.toml`
2. Run `uv lock --upgrade` and then `uv sync --python 3.14 --locked --extra all --group dev` to regenerate `uv.lock`
3. Run `uv run pymedphys dev propagate` to regenerate the exported
   `requirements.txt`, `dependency-extra.txt`, and `pyproject.hash`; the integration workflow
   fails when these drift from `pyproject.toml` and `uv.lock`
4. Test changes to ensure nothing breaks

Do not add tests that restate a declared dependency constraint or the locked
version. The lockfile checks and CI's locked environment already cover them.

The `dependency-floors` job in `.github/workflows/unit-tests.yml` runs the unit
tests with NumPy and pandas at their declared minimum versions. When a change
needs a newer NumPy or pandas, raise the minimum in `pyproject.toml` and the
versions pinned in that job together, rather than working around a failure
there.

### GitHub Actions Pins and Dependabot

- Every action is pinned to a commit SHA with the tag in a trailing comment
  (`uses: owner/repo@<sha> # vX.Y.Z`). Dependabot (`.github/dependabot.yml`)
  updates the SHA and the comment together in one grouped weekly PR, so the
  comment must be exactly the tag name.
- Dependabot only raises security-fix PRs for Python packages. Version updates
  come from the weekly `deps.yml` run, which regenerates the propagated files
  and opens its PR with the CI bot's token so CI runs on it.
- CI pins uv (`version` on `setup-uv`) to the same version as the pre-commit
  `uv-lock` hook. Bump both together and confirm `uv lock` leaves `uv.lock`
  unchanged under the new version.
- When CI runs a tool that `uv.lock` already pins, give it a dependency group
  and install it with `uv sync --frozen --only-group <group>`, which checks the
  lockfile's hashes without installing the project. `uvx --constraints`
  applies the versions but ignores hashes. Install in a step of its own, before
  any `continue-on-error` step, so an installation failure is not misreported.
- Ruff is one such tool. The pre-commit `ruff` and `ruff-format` hooks are
  local hooks that run the ruff pinned in `uv.lock` (from the `pre-commit`
  group in CI), so `uv run -- ruff` and pre-commit always agree. Upgrade ruff
  through `uv lock`, never with a `ruff-pre-commit` hook `rev`, and keep the
  explicit `select` in `pyproject.toml` so an upgrade does not change the rules.
  Put a repository-wide reformat in a commit of its own and add its full SHA to
  `.git-blame-ignore-revs`.

**Never hand-edit `uv.lock`.** CI installs with `uv sync --frozen`, which reads the
resolved `[package.optional-dependencies]` tables, not the `requires-dist` metadata.
`uv lock --check` only validates `requires-dist` against `pyproject.toml`, so a
hand-edited lockfile can pass the check while CI silently omits the package.
Always regenerate the lockfile with `uv lock` after touching `pyproject.toml`.

### Pre-commit Hook Exclusions

When a file added by a pull request fails a pre-commit hook only because of
its format, add the exclusion to `.pre-commit-config.yaml` in the same pull
request rather than in a separate one. This applies to template languages such
as Jinja2, generated files with non-standard syntax, and configuration formats
that standard linters do not understand.
