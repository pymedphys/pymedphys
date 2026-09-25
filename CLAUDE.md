# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Setup and Installation

```bash
# Install with uv (required for development)
uv sync --python 3.12 --locked --extra all --group dev

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
`docs` and `all` extras and regenerate the exported ReadTheDocs requirements.
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

PyMedPhys is a medical physics library organized as follows:

- **lib/pymedphys/**: Main library code
  - `_<module>/`: Private implementation modules (e.g., `_dicom/`, `_gamma/`, `_mosaiq/`)
  - `<module>.py`: Public API modules that expose the private implementations
  - `cli/`: Command-line interface implementations
  - `tests/`: Test suite organized by module
  - `_experimental/`: Experimental features not yet stable
  - `_streamlit/`: Streamlit web app components

### Project Maintainers

PyMedPhys is maintained by:
- SimonBiggs
- sjswerdloff
- Matthew-Jennings
- pchlap

When creating conda recipes, pull requests, or other metadata that requires maintainer information, use this list.

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
- Tests marked `slow` (and `mosaiqdb`, `anthropic_key`) are skipped by
  `conftest.py` unless requested. `--include-slow` (and `--include-mosaiqdb`,
  `--include-anthropic`) adds them to the default selection. `--slow` (and
  `--mosaiqdb`, `--anthropic`, `--pydicom`) runs only the tests with that
  marker; several of these select the union. `--all` runs everything.
  `pytest -m slow` alone selects the slow tests but still skips every one.
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
- Data caches must not fall back across changes to `hashes.json`: ZIP archives
  are checked, but previously extracted files are not refreshed automatically.
- Mock data and fixtures are in `_mocks/` and test data directories
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
  licence or removing the last code under one. Keep the independent licence
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
  duplicate cannot overwrite GitHub assets with different bytes.
- Resolve PyMedPhys's published archive from PyPI's JSON Simple API and
  install its exact URL, so no other configured index can substitute it.
- Recover releases using their original distribution files. A rebuild of the
  same tag can differ when the build backend changes. A failed retry does not
  prove earlier attempts left PyPI untouched; preserve release tags and use a
  new version for changed files.

## Important Implementation Notes

1. **Beta Status**: PyMedPhys is in beta (version 0.x.x). APIs may change between releases.

2. **DICOM Handling**: The library provides extensive DICOM functionality including anonymization, coordinate systems, dose calculations, and RT plan manipulation.

3. **Gamma Analysis**: Core functionality for dose distribution comparison using efficient shell-based algorithm implementation.

4. **Anthropic Integration**: Built-in Claude integration for AI-assisted features (requires API key).

5. **Streamlit Apps**: Web-based tools for various tasks (anonymization, metersetmap, dose analysis) in `_streamlit/apps/`.

6. **Database Connections**: Mosaiq integration requires appropriate database credentials and SQL Server access.

7. **DICOM De-identification**: A standards-driven replacement for `pymedphys.dicom.anonymise` and the experimental pseudonymisation module is planned. `lib/pymedphys/docs/contrib/info/deidentification-design.md` is the source of truth for its active decisions, actual PR progress, outcome-based roadmap, and rolling next steps; update it in every de-identification PR. Distinguish planned behaviour from implemented and released support. Follow active decisions, not the separate superseded history, and keep user guidance and PR descriptions consistent with them.
   - Never put source DICOM attribute values, secret keys, or original file paths in logs, standard output, exception messages, or release reports. Use tag/keyword paths and opaque object identifiers. A confidential QC review pack may contain retained strings and image previews needed for human review; create it only in an explicitly designated restricted location, keep it separate from release outputs, and treat it as potentially identifying. Key and subject-profile stores remain separate custodian-controlled state.
   - Rule tables generated from the DICOM standard are regenerated with their generator, never edited by hand.
   - Claim "de-identified in accordance with" a named DICOM PS3.15 edition, profile, and options only after validating the effective policy and output. Validate both removal and retention overrides against IOD requirements and the claimed options. Explicitly label permitted nonconformant processing, including Private SOP Classes, and suppress unsupported conformance claims and method codes. Never describe output as "anonymised"; that is a legal conclusion about the release context that software cannot make.

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
- Anonymization requirements
- VR (Value Representation) handling
- RT-specific DICOM objects (RTDose, RTPlan, RTStruct)

When you find unmaintained or non-functional material, such as a packaging
recipe that no workflow builds or a CLI command whose inputs no longer exist,
remove it (and anything that exists only to support it) rather than annotating
it as a draft. Git history preserves it. Do not write documentation that hedges
around code that cannot work; fix or remove the code in the same PR, and record
contributor-facing removals in `CHANGELOG.md`. Historical documentation pages
are different: keep them as originally written, as described above.

### Copyright Headers

Most source files open with one or more `# Copyright (C) <years> <authors>` lines above the Apache 2.0 notice, one for each meaningful contribution.

- When a change is meaningful, credit its author in the header of each file it touches. For Claude-assisted work, that is the person who directed it.
- Put a new line above the existing ones (newest first). If the author already has a line of their own, extend its years instead (`2025-2026`, `2021, 2025`). Leave joint lines unchanged.
- A change is meaningful when the author's net surviving contribution to the file is about 15 or more added or rewritten lines, cumulative across PRs. Mechanical edits do not count: API renames, import reordering, lint, typing-only and formatting fixes, and `nosec` comments.
- A new file starts with the full header, crediting its author and the current year. Do not add a header to an existing file that has none without the maintainers' agreement, since it must also credit the original authors.
- Every PyMedPhys copyright header must have the full Apache 2.0 licence
  notice immediately below its copyright lines, including when adding a
  header to an existing file. Preserve upstream licence and attribution
  notices in third-party code.

## Claude Code Workflow Guidelines

### CRITICAL META-INSTRUCTION: Always Document General Feedback

**EXCEPTIONALLY IMPORTANT**: When maintainers provide ANY general feedback, guidance, or principles:

1. **IMMEDIATELY implement the feedback** in your current task
2. **AND SIMULTANEOUSLY update CLAUDE.md** to document the general principle
3. **BOTH actions are MANDATORY** - doing only one is incomplete

This meta-instruction is ABSOLUTE and MUST be followed by all future Claude Code instances. Failure to follow this results in maintainers having to repeatedly provide the same guidance, which wastes their time and degrades the development experience.

**Example scenarios where this applies**:
- When told how to handle certain types of files or situations
- When given preferences about workflow or process
- When corrected about general behavior patterns
- When learning important information about the project while completing tasks

**The goal**: Every interaction should make future interactions better by preserving knowledge.

### CLAUDE.md Content Guidelines

**Critical**: This file should only contain general principles and guidance that apply broadly across the codebase.

**What to include**:
- General development workflows and patterns
- Architectural principles and conventions
- Reusable commands and procedures
- General principles from maintainer feedback that prevent repetition

**What NOT to include**:
- Task-specific examples or solutions
- One-off fixes for specific issues
- Detailed explanations of individual features

**Most Important**: When maintainers provide general feedback or principles, ALWAYS update CLAUDE.md immediately to capture this knowledge. This prevents maintainers from having to repeat the same guidance and ensures consistent behavior across all Claude Code interactions.

### Bash Command Restrictions

When the Claude workflow uses restricted bash permissions (via `allowed_tools` with specific `Bash(command)` entries):

**Important**: Command chaining with `&` or `&&` is NOT allowed. Each `Bash(command)` entry is treated as an exact string match.

**Problem Example**:
```yaml
Bash(git add file.txt),
Bash(git commit -m "message")
```
This does NOT allow: `git add file.txt && git commit -m "message"`

**Solution**: Execute commands sequentially:
1. Execute first command
2. Check result
3. If successful, execute next command

This approach prioritizes security over efficiency, as confirmed by maintainer @sjswerdloff.

### Git and GitHub Tool Usage

#### Known Issues and Workarounds

1. **MCP GitHub commit tools**: The `mcp__github_file_ops__commit_files` tool may sometimes fail with undefined errors. When this happens:
   - Try using sequential git commands via Bash
   - Be aware that commit messages must be part of the allowed command string for restricted bash

2. **Timing Issues with PR Merges**: Be aware that workflow runs may start with a repository state from just before a recent PR merge. If permissions appear to be missing:
   - Check if a recent PR was merged that might have added those permissions
   - The workflow's checkout might be from before the merge

3. **GitHub Workflow File Restrictions**: The `mcp__github_file_ops__commit_files` tool cannot commit files to the `.github/workflows/` directory. This appears to be a security restriction to prevent automated creation or modification of GitHub Actions workflows. When creating workflow files:
   - The tool will return "undefined" errors when attempting to commit to `.github/workflows/`
   - You can successfully commit to other directories including `.github/` itself
   - Provide the workflow content in an expandable comment section for manual creation
   - This is NOT a general permission issue - the same tool works for other file locations

### PR Link Format

**Always use this exact format when providing PR links**:
```
https://github.com/pymedphys/pymedphys/compare/main...<your-branch>
```

**Important**:
- Use THREE dots (`...`) between branch names, not two (`..`)
- Correct: `compare/main...feature-branch`
- Wrong: `compare/main..feature-branch`

### PR Descriptions

When a pull request's scope changes after it is opened, update its title and
description to match the current diff and the validation actually run.

### Maintainer Guidance Documentation

**Critical**: Any time you receive guidance, feedback, or learn something important from maintainers:

1. **Immediately update CLAUDE.md** with the new information
2. **Commit the changes** to your branch
3. **Create a PR** using the format above
4. **Provide the PR link** to maintainers

This ensures that:
- Future Claude Code interactions will follow the same guidelines
- Maintainers don't need to repeatedly explain the same concepts
- Knowledge is preserved across different workflow runs

### Pull Request Scope and Documentation

These principles come from maintainer feedback and apply to all pull requests:

- **Keep pull requests small and reviewable by a human.** Each pull request has a single concern. As a sizing guide, aim for no more than about 400 lines of hand-written change, excluding tests and documentation; reviewability still matters for all files. Split work that grows beyond a digestible review before requesting review. Keep generated data (lock files, generated tables, propagated requirements) apart from hand-written logic where possible, so the reviewer checks the generator and its tests rather than the generated lines.
- **Every pull request ships its documentation and relevant evidence.** New or changed public functions, classes, and CLI options get NumPy-style docstrings that state behaviour, failure modes, and any standard clause they implement. User-visible changes are documented in the user docs in the same pull request. Add a `CHANGELOG.md` entry. Include relevant tests and requirements/conformance evidence as behaviour is implemented, rather than postponing them to a final documentation milestone. Documentation-only changes need appropriate documentation checks, not invented runtime tests or docstrings. The pull request description states the scope, what is deferred, how the change was verified, and what the reviewer should check first.
- **Consolidate related changelog entries made on the same branch.** Update the existing entry as review and follow-up commits refine the change; describe its final effect rather than the sequence of edits. Keep distinct user-facing and contributor-facing entries where useful, and preserve unrelated entries and release history.
- **Multi-PR programmes keep a living design document** under `lib/pymedphys/docs/contrib/info/`, with active decisions, separately marked superseded history, actual PR progress, an outcome-based roadmap, and a rolling near-term queue. Milestones and queue entries may expand into many PRs; do not assign a fixed total or speculative PR numbers. Link actual GitHub PRs once opened. Introduce dependencies with, or immediately before, their first verified consumer. Re-assess the plan at the start and end of each PR in light of what earlier work found.
- **Keep shared planning and documentation consistent.** Each PR maintains its own progress entry to reduce conflicts and also updates affected shared decisions, dependencies, user guidance, and PR descriptions. A near-term queue is not the whole programme. Distinguish planned, under-review, merged, and released behaviour; anchor deprecation windows to named releases once scheduled. Independent work may proceed concurrently when dependencies allow; declare stacked PR bases and reconcile changes from the base before review or merge.

### CI Gates and Review Policy

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
- Workflow files staged in `claude_created_workflows_preview/` count as workflow
  changes for the pull request path filter, and zizmor audits them in place, so
  a staged workflow must be clean before a maintainer moves it.
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
2. Run `uv lock --upgrade` and then `uv sync --python 3.12 --locked --extra all --group dev` to regenerate `uv.lock`
3. Run `uv run pymedphys dev propagate` to regenerate the exported requirements
   files, `dependency-extra.txt`, and `pyproject.hash`; the integration workflow
   fails when these drift from `pyproject.toml` and `uv.lock`
4. Test changes to ensure nothing breaks
5. Note: If `uv lock --upgrade` or `uv sync` is not in allowed tools, request it be added

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

**Never hand-edit `uv.lock`.** CI installs with `uv sync --frozen`, which reads the
resolved `[package.optional-dependencies]` tables, not the `requires-dist` metadata.
`uv lock --check` only validates `requires-dist` against `pyproject.toml`, so a
hand-edited lockfile can pass the check while CI silently omits the package.
Always regenerate the lockfile with `uv lock` after touching `pyproject.toml`.

### Working with Restricted Permissions

When working with restricted bash permissions:
1. Check the `.github/workflows/claude.yml` file for allowed commands
2. If a needed command is missing, create a PR to add it to `allowed_tools`
3. Be specific about which commands you need and why
4. Remember that exact string matching is used for command validation

### Pre-commit Hook Exclusions

When adding files that cause pre-commit validation to fail due to special syntax:

**Important Principle**: Do NOT create a separate PR for pre-commit fixes when they're blocking the current PR. Instead, add the necessary exclusion patterns directly to `.pre-commit-config.yaml` to fix the immediate issue.

This applies to files that use:
- Template languages (Jinja2, etc.) that conflict with file format validators
- Generated files with non-standard syntax
- Special configuration formats that don't match standard linters


### Branch and File Management

#### Branch Name Accuracy

**Critical**: Always provide accurate branch names when referencing branches. Incorrect branch names waste maintainer time searching for non-existent branches.

**Best Practices**:
- Double-check branch names before mentioning them
- Use the actual branch name from your current git status
- If unsure, explicitly state you're on a branch but need to verify the exact name

#### Git Timestamps

**Important**: Git commit timestamps reflect when commits are created, not when work began.

**Key Points**:
- "Branch timestamps" (as shown in GitHub's UI) indicate when the first commit was pushed to GitHub on a branch. This is not a standard Git term, but rather how GitHub displays branch activity.
- Timestamps cannot be retroactively changed as they're part of the commit SHA
- Work start times are not tracked by Git

#### Handling File Creation Failures

When unable to commit files due to permission issues:

**Fallback Strategy**:
1. Include the complete file content in a comment using expandable details sections
2. Clearly explain why the file couldn't be committed
3. Provide clear instructions for manual file creation

**Example Format**:
```markdown
<details>
<summary>Click to expand: path/to/file.ext</summary>

```yaml
# File content here
```

</details>
```

#### Permission Documentation

When discussing permissions needed for operations:

**Always Include**:
1. **Immediate Needs**: Minimal permissions to complete the current task
2. **Future Needs**: Additional permissions for full automation (if applicable)
3. **Security Considerations**: Why each permission is needed
4. **Fallback Options**: What can be done without the permissions

**Format Example**:
- Basic file operations: `git add`, `git commit`, `git push`
- GitHub API operations: `mcp__github__create_branch`, `mcp__github__push_files`
- External operations: Access to external repositories with justification

### GitHub Workflow File Creation

When asked to create GitHub workflow files (`.github/workflows/*.yml`):

**Important**: Due to permission restrictions on the `.github/workflows/` directory, use the following approach:

1. **Create a preview directory**: Use `claude_created_workflows_preview/` in the repository root
2. **Place the workflow file there** with the intended filename (e.g., `conda-package.yml`)
3. **Inform the user** that they need to:
   - Pull the branch locally
   - Move the file from `claude_created_workflows_preview/` to `.github/workflows/`
   - Push the change back using their own permissions
   - Give the move command for both shells. Maintainers often work in
     PowerShell, where `mv` is `Move-Item` and refuses to overwrite an
     existing file unless `-Force` is passed:
     - bash: `mv claude_created_workflows_preview/x.yml .github/workflows/x.yml`
     - PowerShell: `Move-Item -Force claude_created_workflows_preview/x.yml .github/workflows/x.yml`
4. **Provide the PR creation link** with the branch as-is

**Recommended PR Workflow**: Create the PR first, then move the file. This approach:
- Allows immediate visibility of the proposed workflow
- Enables discussion and review before the file is in its final location
- Permits the maintainer to make the move as part of the PR review process
- Avoids potential confusion if the branch is updated locally but not pushed

**Example response**:
```
I've created the workflow file at `claude_created_workflows_preview/my-workflow.yml`.

To move it to the correct location:
1. Pull this branch locally
2. Move the file: `mv claude_created_workflows_preview/my-workflow.yml .github/workflows/`
3. Commit and push the change

[Create PR](https://github.com/pymedphys/pymedphys/compare/main...branch-name)
```

This approach ensures successful workflow file delivery despite permission restrictions.
