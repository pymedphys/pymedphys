# AGENTS.md

Guidance for every coding agent working in this repository. Follow it, and
the [contributor language policy](CONTRIBUTING.md#language), for every change.

## Development Instructions

Use uv for development and the locked checkout environment. Follow
[development setup](lib/pymedphys/docs/contrib/start/setup.md),
[the developer command reference](lib/pymedphys/docs/contrib/guides/dev-reference.rst),
[testing and code-quality checks](lib/pymedphys/docs/contrib/validation/testing.md),
and [documentation builds](lib/pymedphys/docs/contrib/info/docs-guide.rst).
Use [the user installation guide](lib/pymedphys/docs/users/get-started/quick-start.rst)
when installing solely for use.

Documentation notebooks must use declared, locked dependencies rather than
installing packages while running. Add documentation dependencies to the
`docs` dependency group and regenerate `uv.lock`; CI and ReadTheDocs both
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

The canonical [repository map](lib/pymedphys/docs/contrib/architecture/index.md)
describes the source layout, public/private modules, dependencies, generated
files, and packaging boundaries. Use
[feature anatomy](lib/pymedphys/docs/contrib/architecture/feature-anatomy.md)
to trace the affected API, CLI, GUI, tests, and documentation before a change.

### Project Maintainers

PyMedPhys is maintained by:

- SimonBiggs
- sjswerdloff
- Matthew-Jennings
- pchlap

Use this list wherever metadata needs the maintainers.

### Key Architectural Patterns

Follow the public/private implementation, shared Delivery, CLI, data-cache,
and vendor-integration patterns in
[Architecture](lib/pymedphys/docs/contrib/architecture/index.md).
For implementation recipes, use
[Make a change](lib/pymedphys/docs/contrib/guides/make-a-change.md).

### Testing Strategy

[Run and write tests](lib/pymedphys/docs/contrib/validation/testing.md) owns
test selection, opt-in marker flags, pytest configuration, isolated home
directories, and AppTest procedures.
[Scientific evidence](lib/pymedphys/docs/contrib/validation/scientific.md)
and [Fixtures and external data](lib/pymedphys/docs/contrib/validation/data.md)
explain independent expectations, fixture provenance, and the shared cache.

- Use absolute report paths in CI. Resolve positional test paths after pytest
  parses its arguments; do not maintain a list of value-taking options, since
  plugins can add more. Preserve the `_dev.pytest_paths` plugin's resolution
  in both the controller and pytest-xdist workers.
- Keep tests independent for parallel runs: no shared output paths or ordering
  assumptions. Write outputs to `tmp_path`, never beside cached data.
- Register a new project selection marker in `MARKER_CONFIG` in root conftest.
- Tests must also pass from an installed wheel. Read only files inside the
  package, and take package requirements from `importlib.metadata`, never
  from `pyproject.toml` or other files outside `lib/pymedphys`.
- Preserve the `dev tests` and `dev doctests` bypass of user logging
  configuration during CLI startup, before pytest can isolate home. Opening a
  configured log can modify user files before any test runs.
- Record the hash of every file added to `urls.json`; downloads require a
  recorded hash by default and must never write to `hashes.json`.
  `check_hash=False` explicitly accepts unverified data.
- Prefer small, deterministic local fixtures for regression tests. Before
  retiring download-backed tests, record tested revisions, fixture provenance,
  and results, and retain their useful coverage locally. Distinguish changed
  expectations from unchanged baselines and previously skipped tests.
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
- Follow the AppTest fixtures for temporary demo working directories. When
  serving a different configuration, clear `st.cache_data` on entry and exit.
  Preserve the non-interactive `Agg` backend for figures on AppTest's worker
  thread.

### Dependencies and Extras

The [dependency/environment map](lib/pymedphys/docs/contrib/architecture/index.md#dependencies-and-environments)
defines published extras and checkout-only groups. Follow the
[dependency recipe](lib/pymedphys/docs/contrib/guides/make-a-change.md#add-or-update-a-dependency)
when changing them.

- Every narrow extra must list every package its public functions and commands
  need, directly or through PyMedPhys, rather than relying on transitive
  installation. Every package in a feature extra must also be in `user`.
- Add a new feature extra only with its CI matrix entry.
- When a narrow-extra job fails because its feature needs a package, add it to
  that extra. Use `pytest.importorskip` only for a test of another feature,
  private code, or a plotting helper, and say which in a comment.
- Put contributor/CI-only tools in dependency groups, never published extras.

### Optional Dependencies

- Import every third-party package other than the base dependencies through `pymedphys._imports`, for example `from pymedphys._imports import numpy as np`. It imports the package on first use and, when the package is missing, names the extra that provides it. Register a new package in `lib/pymedphys/_imports/imports.py`, and add it to `DISTRIBUTION_FOR_IMPORT` in `lib/pymedphys/_extras.py` when its import name differs from its distribution name.
- Every module must import with only the base dependencies, except those listed in `REQUIRED_EXTRAS` in `lib/pymedphys/_dev/import_policy.py`: the Streamlit apps, the AI modules, and the tests. So outside those, do not use an optional package when a module is imported: not at module level, in decorators, default arguments, or class bodies, nor in annotations unless the module has `from __future__ import annotations`.
- [Lazy imports](lib/pymedphys/docs/contrib/info/lazy-imports.md) owns the
  mechanism, messages, examples, and policy-check descriptions. Update it
  when those rules change.

### Packaging

Follow [release preparation and distribution checks](lib/pymedphys/docs/contrib/maintainers/release.md),
and [release recovery](lib/pymedphys/docs/contrib/maintainers/recovery.md).
These guides explain the build targets, isolated verification, publishing
jobs, and recovery from the original distribution files.

- Set Hatchling file selection per build target, never build-wide. Keep the
  sdist's `only-include` selection so the root `docs` symlink cannot cause
  `lib/pymedphys/docs` to be skipped.
- Declare the licence as a PEP 639 SPDX expression that covers bundled
  third-party code as well as PyMedPhys's own, and list every licence file in
  `license-files`. Update both for changed vendoring. Bundle data,
  vocabularies, and standard-derived tables only under terms compatible with
  Apache-2.0, never non-commercial or no-derivatives terms, and retain required
  attribution. Keep the independent licence expectations and fixtures in
  `.github/scripts/check_distributions.py` in sync. Check declarations and
  file presence so removing metadata cannot bypass the release guard.
- Keep `version` in `pyproject.toml` in canonical PEP 440 form
  (`0.42.0.dev0`, not `0.42.0-dev0`); the release tag must be `v` followed by it.
- Distribution smoke tests must ignore Python path overrides, run outside the
  checkout, and verify imports come from the test environment. Disable pip
  configuration files and inherited behavioural `PIP_*` settings for installs
  and build subprocesses; preserve only explicit network settings such as
  proxy, certificate, time-out, and retry settings.
- Include root documentation-preparation inputs in the sdist: `README.rst`,
  `CHANGELOG.md`, and `CONTRIBUTING.md`.
- Keep release and CI documentation aligned with `release.yml`, including
  pre-releases, destinations, and post-publication checks. Record release-test
  evidence on the release PR.
- Verify published wheel and sdist files in separate fresh environments outside
  the checkout, forcing the sdist to build and checking the installed file and
  its source. Extend `check_distributions.py` or the workflow rather than
  documenting manual verification steps.
- Add every new release job to `Release Summary`'s `needs`.
- Publishing a GitHub release or pre-release is the only publishing route.
  Rehearse release-pipeline changes with a development release on PyPI; do not
  introduce a manual or TestPyPI route.
- Tag a commit on `main`: for a stable release, tag the merge commit of its
  reviewed release PR, never a release-branch commit. After publishing, use a
  separate PR to set the next unpublished `.devN`. Development pre-releases
  may be tagged from `main` without a release PR. Only stable release PRs need
  `full-test`, and changelog entries stay under `## Unreleased` until stable.
- Release asset uploads must wait for `verify-published`, so a skipped duplicate
  cannot overwrite assets with different bytes. Keep `test-published` separate
  and reporting to `Release Summary`; assets must not wait for that job.
- Resolve published archives through PyPI's JSON Simple API and install the
  exact URL so another configured index cannot substitute a package.
- Recover releases using their original distribution files. Preserve release
  tags and use a new version for changed files; a failed retry does not prove
  previous attempts left PyPI untouched.

## Important Implementation Notes

1. **Beta Status**: PyMedPhys is in beta (version 0.x.x). APIs may change between releases.

2. **DICOM Handling**: The library provides extensive DICOM functionality including anonymisation, coordinate systems, dose calculations, and RT plan manipulation. Use only pydicom APIs that pydicom 4 keeps:
   - write with `enforce_file_format=True`, not `write_like_original=False`;
   - set the encoding through the file meta Transfer Syntax UID, the `implicit_vr` and `little_endian` arguments of `save_as` and `dcmwrite`, or the `FileDataset` constructor, never the `is_implicit_VR` and `is_little_endian` attributes, and read a decoded dataset's encoding from `original_encoding`.

   The test suite fails on pydicom's "will be removed in v4" deprecation warnings. Some deprecated APIs do not warn, so test new code that reads or writes DICOM encodings with the `pydicom_behaviour` fixture (`lib/pymedphys/tests/dicom/conftest.py`), which also runs the test with pydicom's future behaviour, in which they raise. Do not run the whole suite with `PYDICOM_FUTURE`: in pydicom 3.0, `Dataset.pixel_array` itself fails with the future behaviour.

3. **Gamma Analysis**: Core functionality for dose distribution comparison using efficient shell-based algorithm implementation.

4. **Anthropic Integration**: The experimental Mosaiq chat app and its SQL agent (`_ai/`) call Anthropic's API and need an API key. Their dependencies are in the opt-in `ai` extra, so import them only where they are used, and keep the rest of the GUI loadable without them.

5. **Streamlit Apps**: Web-based tools for various tasks (anonymisation, metersetmap, dose analysis) in `_streamlit/apps/`. `pymedphys gui` serves them, and is meant to be run either on one computer or on a server that other computers connect to, for example within a radiotherapy department. As the maintainers decided, it listens only on the loopback address unless `--address` is given. Keep network serving supported through that option; the GUI has no login, so document that anyone who can reach it can use its apps.

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
  cost-gated on PRs, as the maintainers decided; merge groups and main pushes
  run them in full. Beyond the `full-test` and `database` labels, integration
  and database tests run on PRs only for inputs that no standard check validates,
  listed in `select_checks.py`.
  Add an input there when only a cost-gated job validates it. Packaging filters,
  slow-test modules, modules with doctests, and shared test fixtures and data are
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
  The dependency audit is advisory on pull requests, pushes and merge groups,
  and blocking on scheduled and manual runs, where a failure opens or updates
  the issue labelled `security-audit`. Bandit and zizmor block on every event.
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
- CodeQL code scanning, secret scanning with push protection, and Dependabot alerts, malware alerts, and security updates are repository settings (Settings, then Advanced Security), not workflow jobs. CodeQL uses default setup for Python and GitHub Actions with the default query suite. Fix its findings; where a finding is intended behaviour, dismiss it as won't fix with a comment that says why.
- PyMedPhys's tools are for clinical users behind strong network protections. Do not remove information that operators rely on, such as patient identifiers in local logs, or rename code and tests to avoid CodeQL's name-based heuristics. Where a risk matters to users, document it, and dismiss the finding as intended behaviour.

### Dependency Updates

When updating dependencies:

1. Update version constraints in `pyproject.toml`
2. Run `uv lock --upgrade` and then `uv sync --python 3.14 --locked` to regenerate `uv.lock`
3. Run `uv run pymedphys dev propagate` to regenerate the exported
   `requirements.txt`, `dependency-extra.txt`, and `pyproject.hash`; the integration workflow
   fails when these drift from `pyproject.toml` and `uv.lock`
4. Test changes to ensure nothing breaks

Do not add tests that restate a declared dependency constraint or the locked
version. The lockfile checks and CI's locked environment already cover them.

The `dependency-floors` job in `.github/workflows/unit-tests.yml` runs the unit
tests with NumPy and pandas at their declared minimum versions, and the
`pydicom-versions` job runs the de-identification tests with pydicom at its
declared minimum. When a change needs a newer NumPy, pandas, or pydicom, or a
minimum is raised for another reason such as a security fix, raise the minimum
in `pyproject.toml` and the version pinned in that job together, rather than
working around a failure there.

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
