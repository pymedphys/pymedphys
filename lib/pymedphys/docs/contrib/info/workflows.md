# PyMedPhys CI/CD Workflows

## Overview

PyMedPhys uses GitHub Actions for continuous integration and deployment. The workflow architecture follows a modular design with separated concerns for better visibility and maintainability.

## Workflow Architecture

```text
ci.yml <- pull request (selective), merge_group (comprehensive), main push
  |-- pre-commit.yml
  |-- lint.yml
  |-- type-check.yml
  |-- unit-tests.yml
  |-- integration-tests.yml (selected PRs; every merge group)
  |-- mosaiq-db-tests.yml (selected PRs; every merge group)
  |-- docs.yml (selected PRs; every merge group)
  `-- CI Summary

Manual run -> docs.yml
security.yml <- schedule, manual run, main push, PR, merge_group
  |-- dependency audit / Bandit / zizmor (selected PRs; every merge group)
  `-- Security Summary
Schedule / manual run -> deps.yml
Schedule / manual run -> deid-edition-check.yml
Published release -> release.yml -> quality checks, publishing, verification, and published-package tests
Issue comment -> claude.yml

Outside GitHub Actions:
Main push / PR labelled rtd-preview -> Read the Docs (see "Read the Docs" below)
```

## Workflow Structure

### Pull request checks

#### `ci.yml` - Main Orchestrator
Coordinates all CI checks based on file changes, labels, and event types.

- **Triggers**: Push to main, pull requests (including label changes, which queue
  behind an in-flight run rather than cancelling it), and merge groups
- **Jobs**:
  - `changes`: Tests the selection/gating policy and reads the tested merge diff
  - `pre-commit`: Auto-formatting and basic checks
  - `lint`: Code quality
  - `type-check`: Static type checking
  - `unit-tests`: Fast unit tests when selected
  - `script-tests`: Distribution/tooling regression tests when their inputs change
  - `integration-tests`: Extended tests (conditional)
  - `mosaiq-db-tests`: Database tests (conditional)
  - `docs-check`: Documentation build and artefact (conditional)
  - `summary`: Requires policy checks, pre-commit and every selected check to succeed

`.github/scripts/select_checks.py` owns selection for both CI and security,
including the `full-test` and `database` labels, which it matches
case-insensitively as GitHub's `contains()` does. For PRs it compares the tested
merge tree with its base parent. It verifies both parents against the event,
reads NUL-delimited raw diff records, and disables rename detection so deletions
and both sides of renames count. It needs only two checkout generations and has
no API file-list limit. If the merge cannot be verified, every check that a
changed path can select runs. The step summary gives each check's reason (the
event, a label, or the first path that selected it) and names the path behind
any fallback.

| PR changes | Selected checks, in addition to policy checks and pre-commit |
|------------|-------------------------------------------------------------|
| Known documentation prose, notebooks and rendered assets only | Documentation |
| Package Python modules | Lint, type checks, unit tests, generated documentation and all security scans |
| Python tests only | Lint, type checks, unit tests and all security scans |
| Other CI configuration or any unclassified path | Every standard check: lint, type checks, unit tests, script tests, documentation and all security scans |
| Dependency or build metadata (`pyproject.toml`, `uv.lock`, the exported requirements, `pyproject.hash`, `dependency-extra.txt`, `_version.py`), `ci.yml` or `.github/actions/` | Standard checks, plus integration and database tests |
| `.github/scripts/`, `integration-tests.yml`, `examples/`, or packaging filters (`.gitignore`, `.gitattributes`, `.hgignore`, including nested files) | Standard checks, plus integration tests |
| Slow-test modules, modules with doctests, or non-Python test fixtures | Adds integration tests |
| Any path naming Mosaiq or a database (except documentation) | Adds database tests |
| `conftest.py`, top-level package modules, or `_imports/`, `_data/`, `_utilities/` and `_base/` | Adds integration and database tests |
| A symlink, a submodule or an unverifiable merge diff | Every check a changed path can select, including integration and database tests |
| `full-test` label | Every check and the full unit-test matrix |
| `database` label | Adds database tests |

Only recognised documentation inputs under `lib/pymedphys/docs/` are exempt
from Python checks; a Python file or new configuration format inside the docs
tree is not exempt. The repository-root `docs` is a symlink to that directory,
so git reports only the link itself, which selects every check that a changed
path can select. A symlink or submodule is never exempt, whatever its name,
because it can stand in for any content. Package modules still select
documentation because autodoc and notebooks import them. The full OS/Python
matrix and integration checks run on merge groups and main pushes. Read the Docs
publishes main documentation independently, as "Read the Docs" below
describes.

Integration tests, database tests and the full unit-test matrix are too costly
for every PR. Apart from merge groups, main pushes and the labels, integration
and database tests run only when a PR changes an input that no standard check
validates, as the table lists: an input of the generated-file drift check, the wheel build, the
Windows and macOS tooling tests, the example scripts, the slow tests, the
doctests and their shared inputs, or the database code and its locked drivers.
An unclassified path selects every standard check, but not these. Unit tests
use the quick matrix unless the PR has the `full-test` label.

Unit runs skip the slow tests and never run doctests. `SLOW_TEST_FILES` and
`DOCTEST_FILES` in `select_checks.py` list the package modules that apply the
slow marker or hold doctests. The policy tests in the always-required `changes`
job scan the package and fail unless each list equals what they find, naming
each module to add or remove, so update the list in the PR that adds, removes
or renames such a module. Shared test data, including `_data/urls.json` and
`_data/hashes.json`, also selects integration tests because ordinary unit runs
exclude the slow tests that consume some datasets.

Changes outside the integration and database inputs listed above, such as
TRF decoding, Pinnacle export or gamma implementation code, leave those tests
unselected on a pull request. Add `full-test` to request both suites and the
full unit-test matrix; `database` requests only the database suite. Modules
with doctests, including `_metersetmap/metersetmap.py`, already select
integration tests through the existing path rules. Every push to `main` runs
both suites, and the release workflow runs the slow tests before publishing.
Add `full-test` to a pull request that substantially changes code exercised by
slow tests. Merge groups run both suites before merging. When CI fails on a
push to `main`, the `report-main-failure` job
opens or comments on the issue titled "CI failed on main", linking to the run.
Close the issue once `main` is green again.

Selected jobs need only `changes`, so they start alongside pre-commit and run
whatever its result, and one run reports every result. The summary waits for
pre-commit and fails when it fails. An auto-fix pushed with the bot's token
starts a new run, which cancels the run for the superseded commit; either way,
the summary fails until a fresh run passes on the new commit. The summaries
reject any other unexpected skip. Integration jobs run alongside unit tests.

#### `pre-commit.yml`
Runs pre-commit hooks for code formatting and basic checks.

- **Features**:
  - Applies the configured hooks, including Ruff, actionlint, and offline zizmor
  - Can push fixes on same-repository PRs when bot credentials are available
  - Fork PR authors must apply and push their fixes themselves
  - Caches pre-commit environments
  - Installs only the `pre-commit` dependency group, hash-checked from
    `uv.lock`, in its own step, without the project or its scientific
    dependencies. An installation failure therefore fails that step instead
    of being reported as a hook failure
  - Checks out the event's exact head commit before applying auto-fixes

#### `lint.yml`
Dedicated linting workflow for code quality.

- **Jobs**:
  - `lint`: Comprehensive Python linting with Pylint, one process per CPU
    (`jobs = 0` in `lib/pymedphys/.pylintrc`)
- Ruff linting and formatting run through pre-commit
- Runs when the selector chooses the Python checks, even if pre-commit fails

#### `type-check.yml`
Static type checking for type safety.

- **Jobs**:
  - `type-check`: Pyright, the blocking type checker, then MyPy, a secondary
    checker run from the locked `dev` extra. MyPy is optional: its step uses
    `continue-on-error`, so a MyPy failure marks the step and adds a run
    annotation but leaves the job green. It runs even when Pyright fails
- Runs when the selector chooses the Python checks, even if pre-commit fails

#### `unit-tests.yml`
Fast unit tests with smart matrix strategy.

- **Features**:
  - Full OS and Python matrix on merge groups and main pushes (Ubuntu, Windows,
    macOS; Python 3.11, 3.12, 3.13, 3.14)
  - Quick mode for other PRs (Ubuntu + Python 3.14). The selector's
    `run-full-matrix` output decides, and only an explicit `false` keeps the
    quick matrix
  - Installs the `user` extra so the headless Streamlit GUI tests run
  - Full OS and Python matrix for PRs labelled `full-test`
  - Excludes slow tests for rapid feedback
  - JUnit XML report generation

The `dependency-floors` job runs the unit tests (`-m "not slow"`, with the
data cache) at the declared minimum versions of NumPy (1.26.4) and pandas
(2.0.3), alongside both the quick and full matrices. It runs on Ubuntu with
Python 3.11, the only supported version with wheels for both: NumPy 1.26 has
none for Python 3.13 or later, and pandas 2.0 none for 3.12 or later. It
installs the same locked environment as the unit tests, overlays the two
packages with `uv run --no-sync --with numpy==1.26.4 --with pandas==2.0.3`,
and fails first if the overlay did not take effect. It uploads its JUnit
report as `junit-dependency-floors`. A failure fails the unit-test workflow and
therefore the required CI or release summary.

### Extended Workflows (Conditional)

#### `integration-tests.yml`
Comprehensive testing beyond unit tests.

- **Test Types**:
  - `doctests`: Documentation code examples, the StackOverflow example, and
    the unit tests of the gamma benchmark tooling in `examples/`
  - `slow-tests`: Long-running integration tests, run in parallel with
    pytest-xdist (`-n auto`). Processes that share the data cache take turns
    with each file, and with each archive from downloading or repairing it to
    extracting it, so parallel workers never replace an open file or read a
    partly written one
  - `script-tests`: Runs the `.github/scripts` unit tests on Windows and
    macOS; `ci.yml` runs the full script suite on Ubuntu when selected,
    and the selection, summary and workflow-contract tests on every PR. The
    full suite runs in parallel with pytest-xdist, installed with pytest from
    the locked `script-tests` dependency group without the project
  - `packaging`: One job for two checks that each take seconds. The wheel
    build, skipped when the release calls this workflow, builds the sdist and
    then the wheel from it, and runs `.github/scripts/check_distributions.py`:
    both archives must contain the package, and the wheel must install into a
    fresh virtual environment, import, and report its version through
    `pymedphys --version`. Then `pymedphys dev propagate` must leave the
    generated files unchanged (exported requirements, `dependency-extra.txt`,
    `pyproject.hash`, `_version.py`); this check reports even when the wheel
    checks fail
- **Triggers**: Merge groups, main pushes, `full-test`, or a PR that changes
  dependency or build metadata, `ci.yml`, `.github/actions/`, `.github/scripts/`,
  `integration-tests.yml` or `examples/`, or a symlink or submodule

#### `mosaiq-db-tests.yml`
SQL Server integration tests for Mosaiq database functionality.

- **Service**: SQL Server 2022 container
- **Triggers**: Merge groups, main pushes, database or shared code changes,
  dependency metadata or shared CI configuration, or `database` / `full-test`
  labels
- **Features**: Waits for SQL Server to accept connections, then runs the tests once;
  test failures are not hidden by retries. The CSV-backed tests load the mimic
  tables once per module through a read-only connection

#### `docs.yml`
Builds documentation on PRs that change documentation sources, package modules, or any unclassified input. It is the only documentation check on pull requests.

- **HTML build**: Sphinx warnings and unexpected notebook errors fail the build.
  The executed-notebook store (`_build/.jupyter_cache`) is cached between runs
  under an exact key over everything notebook execution can read: every
  tracked file under `lib/pymedphys` except documentation prose,
  `pyproject.toml`, `uv.lock`, the interpreter, and the runner image
  (`.github/scripts/notebook_cache_key.py`). A prose-only change reuses the
  outputs; any other change executes every notebook again
- **Link check**: Advisory external-link check with downloadable reports, in
  its own job alongside the HTML build (`pymedphys dev docs --linkcheck`). It
  reads the sources without executing notebooks, so it needs no data and
  finishes before the build
- **Artefact**: Built HTML is uploaded as `docs-html` for inspection, and the
  link-check report as `docs-linkcheck`
- **Manual run**: Someone with write access can run the `Documentation`
  workflow on any branch of this repository from the Actions tab
  (`workflow_dispatch`), for example when a PR's changes do not select the
  documentation check. The run builds and uploads the same artefacts
- **Publishing**: Read the Docs publishes the public site independently
  using `.readthedocs.yml`, as "Read the Docs" below describes

### Release & Maintenance

#### `release.yml`

Publishes to PyPI behind quality gates.

- **Trigger**: A published GitHub release, including a pre-release, is the
  only trigger and the only way to publish. There is no manual run and no
  TestPyPI route; a development release rehearses changes to the pipeline
- **Before publishing**: Lint, type checks, the full unit-test matrix,
  integration tests, and one distribution build run in parallel. The release
  build replaces the integration workflow's duplicate wheel build and retains
  its archive/install checks, plus Twine and tag/version validation. Publishing
  directly depends on every quality job succeeding. The tag must be `v` followed
  by the canonical PEP 440 package version; no checks are reused from earlier CI
- **Publishing**: PyPI trusted publishing through the `pypi` environment,
  with no stored API token. Files already on PyPI are skipped, so a re-run
  after a partial upload is safe
- **After publishing**: `verify-published` installs the wheel and the sdist
  from PyPI, separately on Linux, Windows, and macOS, with
  `check_distributions.py --published`, and requires both to match the files
  built in the run. `test-published` runs alongside it on each OS: it repeats
  that verification in its own fresh environments, adds the `user` and `tests`
  extras to the published wheel's environment, and runs the test suite
  (`--tests`), with dependencies resolved afresh from PyPI rather than from
  `uv.lock` and no restored cache. After verification, `upload-release-assets`
  attaches the files to the GitHub release and reads them back to confirm the
  release offers exactly those files. The assets do not wait for the published
  tests, whose dependencies and datasets change outside the repository; a
  failure there turns the Release Summary red
- **Concurrency**: Attempts for the same tag are serialised; publishing is
  never cancelled automatically by a newer attempt
- **Recovery**: The original `dist` artefact is retained for 30 days. Retry
  failed jobs using those files; rebuilding an existing release need not
  reproduce its archive hashes. Never replace a published version's tag
- **Release Summary**: Fails unless every job succeeded, and ends with a
  record to paste on the release pull request. It is not a pull request check
- **Limitation**: Assets are attached after the release is published, which
  GitHub's [immutable releases](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases)
  forbid. Before enabling immutable releases, change the workflow to attach the
  assets while the release is still a draft

The [release procedure](release-guide.md) covers the release pull request,
tagging, the next development version, and recovery.

#### `security.yml`
Security scanning with pinned tools run through `uvx`, so nothing is installed
into the project environment.

- **Scans**:
  - `dependency-audit`: pip-audit over an export of `uv.lock` containing all
    extras. The audit runs on Ubuntu/Python 3.12 and evaluates dependency
    markers for that environment; it is not a separate audit of every
    OS/Python combination. Advisory on pull requests, pushes and merge groups
    so a newly published advisory cannot turn an unrelated change red;
    blocking on scheduled and manual runs, where a failure opens or updates the
    issue labelled `security-audit`
  - `python-security`: Bandit, configured in `[tool.bandit]` in
    `pyproject.toml`. Blocking when selected; SARIF is uploaded as an artefact and to
    code scanning when the event has permission (fork PRs cannot upload there)
  - `workflow-audit`: zizmor over `.github` and over any workflow files staged
    in `claude_created_workflows_preview/`, blocking at medium severity and
    above. The offline audits also run through pre-commit; the online ones,
    including the check that each pin's version comment names the tag that
    carries the pinned commit, run only here
- **Triggers**: Weekly, manually, on main pushes, on merge groups, and on every
  PR (including label changes); job-level selection chooses scans while
  `Security Summary` always runs. Python changes retain all three scans: online
  audits can discover new vulnerabilities without a lockfile or workflow edit. Unknown inputs also
  select all scans
- **Coverage**: Change selection applies only to PRs; merge groups, main pushes,
  scheduled and manual runs scan even when the last commit did not change
  security-related files
- **Summary**: Requires every selected scan to succeed
- **Not in the workflow**: CodeQL code scanning uses GitHub's default setup for Python and GitHub Actions with the default query suite. It runs on pushes to `main`, on pull requests from branches of this repository (not forks), and weekly, and its pull request check is not required for merging. Secret scanning with push protection, and Dependabot alerts, malware alerts, and security updates, are also repository settings (Settings, then Advanced Security); Dependabot raises its alerts from the same lockfiles

#### `deps.yml`
Automated dependency updates for Python packages.

- **Schedule**: Weekly (Mondays), or manually on `main`; runs are serialised
  because they share one update branch
- **Steps**: `uv lock --upgrade`, then (only if the lockfile changed)
  `uv sync` and `pymedphys dev propagate` (so
  the exported `requirements.txt`, `dependency-extra.txt`, and `pyproject.hash`
  stay current), then the unit tests, the docs build, and a wheel build and
  install before a PR is opened. The data cache is restored only after the
  lockfile changes, because only those runs read data
- **PR**: creates or updates `deps/weekly-update` with the `dependencies` and
  `full-test` labels, selecting the full unit-test matrix, slow tests and
  database tests. The CI bot's app token is generated after validation,
  immediately before creating or updating the PR, so CI runs on the update
- **Failures**: a failed scheduled run opens or comments on the issue titled
  "Weekly dependency update failed", linking to the run. Close the issue after
  a successful update; a later failure opens a new one
- **Dependabot** (`.github/dependabot.yml`) owns the GitHub Actions pins (one
  grouped weekly PR) and raises security-fix PRs for Python packages; it does
  not open version-update PRs for Python packages

#### `deid-edition-check.yml`

Checks whether NEMA's current edition of the DICOM standard would change the
de-identification tables generated from the pinned edition, as the
[de-identification design](deidentification-design.md) requires.

- **Schedule**: Monthly (the 3rd), or manually
- **Steps**: installs the project with the `user` extra and runs
  `pymedphys dev deid-tables --check-current`, which downloads the pinned
  pages from NEMA's `current/` directory and compares the tables generated from
  them with the committed ones, without writing them. Its check job can only
  read the repository
- **Failures**: when a table would change, a page cannot be fetched, a table
  cannot be generated from the pages (as also happens when the pin's named
  corrections or its list of IODs with Functional Group Macros no longer match
  a new edition), or the check stops without a result, a separate job, the only one that can
  write issues and which runs no repository code, opens or comments on the
  issue titled "DICOM edition check: the de-identification tables need
  attention" with the check's report and a link to the run. Close the issue
  once the pin has moved; a later finding opens a new one

### AI Assistance

#### `claude.yml`
Claude Code integration for automated code assistance.

- **Triggers**: Comments with `@claude` mention
- **Capabilities**: Code review, issue analysis, and commits to a branch with a link to open the pull request; it cannot change `.github/workflows/`
- **Tools**: The action's defaults: file operations in the workspace, and git commits and pushes through the action's wrapper. It does not run tests or other repository code; CI tests the commits it pushes

## Composite Actions

### `actions/setup-project/action.yml`
Standardised project setup for all workflows.

- **Features**:
  - Python setup with configurable version
  - uv package manager with caches separated by extras (tool-only jobs use
    their job ID), so a small tool cache cannot claim the dependency cache
    needed by scientific jobs. setup-uv's own key adds the OS and the full
    Python version
  - PyMedPhys data caching, through `actions/cache-data`, only for jobs that
    consume data
  - Dependency installation with extras
  - Tool-only setup for jobs that do not need an installed project

### `actions/cache-data/action.yml`

Restores and saves the PyMedPhys data cache. Keys are per job and per manifest,
and never restore across a change to `hashes.json`. The key hashes
`lib/pymedphys/_data/hashes.json` by its exact path: the step runs after
`uv sync`, so a `**` pattern would walk the whole virtual environment and also
match pydicom's own `hashes.json`. Jobs that decide later whether they need
data, such as `deps.yml`, use it directly.

## PR Workflow

For a typical pull request:

```
Always:
├── changes          # Selection, summary and workflow-contract regression tests
├── pre-commit       # All configured hooks
├── CI Summary       # Requires every selected CI job to succeed
└── Security Summary # Requires every selected scan to succeed

Selected from the complete merge diff and labels:
├── lint / type-check / unit-tests
├── script-tests / integration-tests / mosaiq-db-tests
├── docs-check
└── dependency-audit / python-security / workflow-audit
```

## Merge Queue Workflow

An approved PR with passing ordinary checks and resolved review conversations
can enter the merge queue without first merging the latest `main` into its
branch. Contributors should normally add it to the queue instead of updating
the branch solely because another PR landed.

GitHub builds a prospective integrated state against the current `main` and
earlier queued PRs, then starts `ci.yml` and `security.yml` on `merge_group`.
Unlike ordinary PR runs, the selector enables the full OS/Python matrix,
integration and database tests, documentation build, and all security scans.
`CI Summary` and `Security Summary` must pass on that state before it merges.
The queue may test up to three prospective states concurrently and merges PRs
individually with merge commits.

## Main Branch Workflow

On merge to main:

```
Every job except docs-check (Read the Docs publishes main), including:
├── unit-tests         # Full matrix (all OS + Python versions)
├── integration-tests  # All extended tests
├── mosaiq-db-tests    # Database tests
└── security           # Full security scan
```

## Required Secrets

| Secret | Description | Used By |
|--------|-------------|---------|
| `ANTHROPIC_API_KEY` | Claude AI API access | claude.yml |
| `GITHUB_TOKEN` | GitHub API access (automatic) | All workflows |
| `PYMEDPHYS_CI_BOT_ID` | Bot app ID for auto-commits and update PRs | pre-commit.yml (optional), deps.yml |
| `PYMEDPHYS_CI_BOT_TOKEN` | Bot private key | pre-commit.yml (optional), deps.yml |

## Environments

| Environment | Purpose | Required setup |
|-------------|---------|----------------|
| `pypi` | Publishing releases | Configure trusted publishing, release approvers, and the allowed `v*` tag refs |

Environment protection is configured in GitHub Settings, not by the workflow's
`environment` field. Create and verify the environment before releasing;
referencing an absent environment can create it without protection rules.
The trusted publisher registered with PyPI must match this repository,
`release.yml`, and the environment name; the
[release guide](release-guide.md) lists the settings.

## Read the Docs

Read the Docs builds and hosts
[docs.pymedphys.com](https://docs.pymedphys.com/), outside GitHub Actions. It
reads `.readthedocs.yml`, which installs the same locked environment as the
`Documentation` workflow, with `uv sync` from `uv.lock` (the project, the
`docs` extra, and the default `dev` group), runs `pymedphys dev docs --prep`,
and fails on Sphinx warnings. Automation rules in the Read the Docs dashboard,
not this repository, decide which pushes and pull requests it builds:

| Event | GitHub Actions | Read the Docs |
|-------|----------------|---------------|
| Pull request | `docs-check` when selected, with the `docs-html` artefact | No build |
| Pull request labelled `rtd-preview` | The same | A hosted preview of each new commit |
| Push to `main` | No documentation build | Builds and publishes `latest` |
| Other branches and tags | No documentation build | Builds active versions |

A Read the Docs status on a pull request is informational and never a
required check. Without the rules below, Read the Docs builds every pull
request, and each build waits for and occupies one of the project's
concurrent build slots. The rules decide before a build exists, so an
unlabelled pull request never enters the queue. Filtering inside the build,
such as a `build.jobs` command that exits with code 183 to cancel it, runs
only once the build has been queued and started, so do not use it to limit
pull request builds.

### Dashboard configuration

A maintainer of the Read the Docs project sets this up once:

1. Connect the project to `pymedphys/pymedphys` through the Read the Docs
   GitHub App. Rules can filter on pull request labels only through it; with
   the older webhook integration, every pull request builds regardless of the
   rules.
2. Under **Settings**, **Pull request builds**, keep **Build pull requests for
   this project** enabled.
3. Under **Settings**, **Automation rules**, add these two rules. Set
   **Version predefined match pattern** to **Any version** and **Action** to
   **Trigger build for version** in both, and leave every field not listed
   here empty:

   | Description | Version types | Webhook labels match pattern |
   |-------------|---------------|------------------------------|
   | Build branches and tags | Branch, Tag | (empty) |
   | Build labelled pull request previews | Pull request | `^rtd-preview$` |

4. Create the `rtd-preview` label in the GitHub repository.

Read the Docs documents that once any rule with this action is enabled, only
events a rule matches trigger builds, so the first rule keeps `main` and tag
builds. It builds only active versions, as Read the Docs does without rules.
Keep its version pattern at **Any version**: rules match the Read the Docs
version name, and the version that tracks `main` is named `latest`, so a
custom pattern such as `^main$` would stop publishing it. Keep the label pattern off the first
rule: pushes carry no labels, so a label pattern there would stop every
branch and tag build. The label pattern is a regular expression that may
match anywhere in a label's name, so keep both anchors.

To confirm the setup, check that a pull request without the label adds
nothing to the project's build list and gets no Read the Docs status, and
that the next merge to `main` builds `latest`.

If the project cannot use the GitHub App, disable **Build pull requests for
this project** instead; hosted previews are then unavailable.

### Requesting a hosted preview

Anyone who can label pull requests (triage access or above) can request a
preview:

1. Add the `rtd-preview` label to the pull request.
2. Push a commit to the pull request. Read the Docs evaluates the rules only
   when a pull request is opened, reopened, or receives commits, so adding
   the label alone does not start a build.
3. Follow the Read the Docs status on the pull request to the preview.

While the label remains, every new commit builds a preview; remove it to
stop. Adding or removing any label also re-runs CI and the security workflow.

## Required checks and pull request reviews

### Why the summaries are required

The required GitHub Actions check names for `main` are **`CI Summary`** (from
`ci.yml`) and **`Security Summary`** (from `security.yml`). Select GitHub Actions
as their expected source in the `main-integrity` ruleset. The release workflow's
**`Release Summary`** shows whether a release completed; it is not a merge gate
and must not be required on pull requests.

| Required check | Checks it covers |
|----------------|------------------|
| `CI Summary` | Change-selection policy, pre-commit, and selected lint, type, unit, script, integration, database and documentation checks |
| `Security Summary` | Change selection and selected dependency, Python security, and workflow security audits |

These are executable gates, not just reports. Both use `if: always()` and
`.github/scripts/check_workflow_status.py` to inspect their dependencies. The policy and pre-commit
checks must succeed. A selected conditional check must also succeed; a skipped
conditional check is accepted only when its selection output explicitly says
`false`. Missing selection outputs, failures, cancellations, and unexpected skips
fail the summary. A pre-commit auto-fix must pass a fresh run on its new commit.

GitHub can accept a skipped individual job as a successful required check. The
summaries close that gap and apply one consistent policy to conditional tests.
They also provide stable required-check names when the OS/Python matrix or
internal job names change. Requiring every constituent check separately does not
add test coverage and can leave outdated names blocking otherwise valid PRs.
See [GitHub's required-check troubleshooting guide](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks).

### Seeing every constituent check

Making only the summaries required does **not** hide, combine, or stop the other
jobs. Expand the checks list in the PR's merge section to see individual results,
including non-required checks. GitHub controls how that list is grouped or
collapsed; the PR's **Checks** tab also lets you inspect each workflow and job.
Open a check's details for its logs. The CI and security workflow run summaries
include a table showing which checks were required for that run and their result.

A skipped integration or database job can be expected on a small PR. The summary
explains whether it was selected. The `full-test` and `database` labels below
request broader coverage and trigger another CI run.

### What a successful summary means

- Ordinary PRs use Ubuntu and Python 3.14 when unit tests are selected. The
  full OS/Python matrix runs on merge groups, main pushes and `full-test` PRs;
  integration tests also run on PRs that change their inputs. A green ordinary
  PR therefore does not mean the full matrix or the integration tests ran before
  entering the queue; merge-group validation runs them before merging.
- Pyright is blocking. MyPy remains optional through `continue-on-error`.
- Dependency vulnerabilities are advisory on PRs, pushes and merge groups.
  Requiring either `Dependency Audit` or `Security Summary` does not turn
  pip-audit findings into a blocking policy; scheduled/manual scans handle them
  as described above.
- Bandit and zizmor findings at the configured threshold are blocking when
  selected. Documentation builds are blocking when selected; external link
  failures remain advisory if the link checker produces its report.

### The two main-branch rulesets

| Ruleset | Policy | Bypass |
|---------|--------|--------|
| `main-integrity` | Require `CI Summary` and `Security Summary` on the prospective merge, use the merge queue instead of requiring PR branches to contain the latest `main`, block force pushes and branch deletion | None, including admins |
| `main-reviews` | Require a PR, one approval by an eligible reviewer, and resolution of review conversations | Repository admins, for pull requests only |

Contributors with Write access may queue a PR once its PR checks and review
requirements pass. GitHub merges it after the merge-group checks pass. Review is
encouraged for admin-authored PRs too, but an admin may explicitly bypass the
review ruleset. GitHub grants bypass to the person merging, regardless of the
PR author. The bypass does not waive the separate CI ruleset or permit direct
pushes to main.

By maintainer choice, **Dismiss stale approvals when new commits are pushed**
and **Require approval of the most recent reviewable push** remain **off**.
An approval can therefore remain valid after later commits; authors should
request another review for substantive changes. Required checks still need to
pass for the current PR commit and the prospective queued merge. Code Owner
approval is not required. Keep the additional-approval setting for unattributed
Copilot PRs enabled.

### Maintaining the gates

1. Add each new blocking job to the appropriate summary's `needs`. The helper
   cannot inspect jobs omitted from that list. Existing dependencies are
   required to succeed unless explicitly configured as conditional.
2. For a conditional job, use the same selection output for the job's `if` and
   the summary's `--conditional JOB=OUTPUT` argument. Add regression coverage
   when changing the selection policy.
3. Keep each required check name unique across workflows. `CI Summary` is the
   displayed CI check name; `summary` remains its internal YAML job ID.
4. If renaming a required check, first produce the new check on the change PR,
   then replace the old required context in GitHub Settings before merging.
   Update older PRs to use the new workflow. Never remove all required gates
   just to merge a naming change.
5. Run `python -m unittest discover -s .github/scripts -p 'test_*.py'` after
   changing the summary policy, then verify the PR's CI and security results.

Remove obsolete standalone requirements, such as the former Actionlint check;
actionlint now runs through pre-commit. Do not add required checks for advisory
review bots or for workflows that do not run on every PR.

Historical branches are managed separately from main. The `legacy-read-only`
ruleset freezes `master`, the existing `0.6.x` through `0.39.x` branches, and
`revert-1460-0.36.x` using explicit targets and no bypass. It prevents updates,
force pushes, and deletion. To resume maintenance, deliberately remove the
specific branch from that ruleset and configure working branch-specific CI and
review requirements first. Do not apply main's check names to an old branch
whose workflows do not emit them. Publishing branches such as `docs` and
`streamlit-app-staging` need a separate deployment review before retirement.

## Labels for Manual Triggers

- `full-test` - Run the full unit-test matrix, slow integration tests, and database tests on a PR
- `database` - Force database tests to run
- `rtd-preview` - Build a Read the Docs preview of each later commit on a PR. Read the Docs reads this label, not GitHub Actions; see "Read the Docs" above


## Testing Workflows Locally

Prefer the local commands below for reproducing individual checks.
[act](https://nektosact.com/) can help investigate Linux jobs, but it does not
reproduce GitHub-hosted Windows/macOS runners, repository permissions, secrets,
or environment approvals. A local run does not replace GitHub CI.

```bash
# Install act
brew install act  # or appropriate for your OS

# Test CI workflow
act push -W .github/workflows/ci.yml

# Test PR workflow
act pull_request -W .github/workflows/ci.yml
```

### Local Development Commands

```bash
# Install with dev dependencies
uv sync --python 3.14 --locked --extra all --group dev

# Run all pre-commit hooks
uv run pre-commit run --all-files

# Run specific checks matching CI
uv run ruff check
uv run ruff format --check
uv run pyright
uv run pymedphys dev lint
uv run pymedphys dev tests -m "not slow"

# Run only the slow tests locally
uv run pymedphys dev tests --slow

# Run the default tests plus the slow tests
uv run pymedphys dev tests --include-slow

# Build docs locally
uv run pymedphys dev docs
```


## Security Considerations

- **Never commit secrets**: Use GitHub Secrets
- **Review permissions**: Minimum required for each job; write permissions
  belong at the job level, never at the workflow level
- **Dependabot**: `.github/dependabot.yml` keeps the action pins current and
  raises security-fix PRs for Python packages
- **Audit third-party actions**: Pin to commit SHAs with the exact upstream tag
  name as the comment (`# v6.0.2`, never `# 6.0.2`); zizmor resolves the
  comment as a ref and fails when it does not exist or points elsewhere
- **Keep zizmor clean**: Pass inputs, matrix values, and step outputs to `run:`
  blocks through `env:`, set `persist-credentials: false` on checkouts that do
  not push, and pin every action to a commit SHA. The pre-commit hook cannot
  run the online audits, so confirm a pin's tag with
  `git ls-remote --tags https://github.com/<owner>/<repo> | grep <sha>`
- **Rotate keys periodically**: Especially API keys
- **Review security alerts**: Weekly scan results
- **Limit workflow triggers**: Avoid `pull_request_target` misuse


## Version Compatibility

- **Python**: 3.11, 3.12, 3.13, 3.14 (all in the full unit-test matrix; 3.14 runs the quick matrix and every other job except the NumPy and pandas minimum-version check, which uses 3.11; 3.11 reaches end of life in October 2027)
- **uv**: 0.12.15, pinned in CI (`setup-uv`) and in the pre-commit `uv-lock` hook
- **GitHub Actions**: Latest Ubuntu, Windows, and macOS runner images
- **SQL Server**: 2022 Latest (for Mosaiq tests)
