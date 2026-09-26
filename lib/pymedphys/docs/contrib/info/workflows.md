# PyMedPhys CI/CD Workflows

## Overview

PyMedPhys uses GitHub Actions for continuous integration and deployment. The workflow architecture follows a modular design with separated concerns for better visibility and maintainability.

## Workflow Architecture

```text
Push / pull request -> ci.yml
                       |-- pre-commit.yml
                       |-- lint.yml
                       |-- type-check.yml
                       |-- unit-tests.yml
                       |-- integration-tests.yml (selected runs)
                       |-- mosaiq-db-tests.yml (selected runs)
                       |-- docs.yml (documentation PRs)
                       `-- CI Summary

Schedule / manual run / main push / PR -> security.yml
Schedule / manual run -> deps.yml
Published release -> release.yml -> quality checks, publishing, verification, and published-package tests
Issue comment -> claude.yml
```

## Workflow Structure

### Pull request checks

#### `ci.yml` - Main Orchestrator
Coordinates all CI checks based on file changes, labels, and event types.

- **Triggers**: Push to main, pull requests (including label changes, which queue
  behind an in-flight run rather than cancelling it)
- **Jobs**:
  - `changes`: Tests the selection/gating policy and reads the tested merge diff
  - `pre-commit`: Auto-formatting and basic checks
  - `lint`: Code quality
  - `type-check`: Static type checking
  - `unit-tests`: Fast unit tests when Python inputs change
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
| Mosaiq/database Python modules, `conftest.py`, top-level modules, or `_imports/`, `_data/`, `_utilities/` and `_base/` | The Python checks above, plus database tests |
| Dependencies, non-Python test data, build/CI configuration, symlinks, submodules or any unclassified path | Every check, including integration and database tests, with the quick unit-test matrix |
| `full-test` label | Every check and the full unit-test matrix |
| `database` label | Adds database tests |

Only recognised documentation inputs under `lib/pymedphys/docs/` are exempt
from Python checks; a Python file or new configuration format inside the docs
tree is not exempt. The repository-root `docs` is a symlink to that directory,
so git reports only the link itself, which selects every check. A symlink or
submodule is never exempt, whatever its name, because it can stand in for any
content. Package modules still select documentation because autodoc and
notebooks import them. The full OS/Python matrix and integration checks remain
unconditional on main. ReadTheDocs publishes main documentation independently.

If pre-commit pushes an auto-fix, dependent jobs are skipped for the superseded
commit and the summary fails until a fresh run passes on the new commit.
Otherwise every selected job still runs when pre-commit fails, so one run
reports every result. The summaries reject any other unexpected skip.
Integration jobs run alongside unit tests.

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
  - `lint`: Comprehensive Python linting with Pylint
- Ruff linting and formatting run through pre-commit
- Runs on PRs subject to the orchestrator's pre-commit dependency

#### `type-check.yml`
Static type checking for type safety.

- **Jobs**:
  - `pyright`: Primary type checker
  - `mypy`: Secondary checker (optional/non-blocking), run from the locked `dev` extra
- Runs on PRs subject to the orchestrator's pre-commit dependency

#### `unit-tests.yml`
Fast unit tests with smart matrix strategy.

- **Features**:
  - Full OS and Python matrix on main (Ubuntu, Windows, macOS; Python 3.10, 3.11, 3.12)
  - Quick mode for other PRs (Ubuntu + Python 3.12). The selector's
    `run-full-matrix` output decides, and only an explicit `false` keeps the
    quick matrix
  - Installs the `user` extra so the headless Streamlit GUI tests run
  - Full OS and Python matrix for PRs labelled `full-test`
  - Excludes slow tests for rapid feedback
  - JUnit XML report generation

### Extended Workflows (Conditional)

#### `integration-tests.yml`
Comprehensive testing beyond unit tests.

- **Test Types**:
  - `doctests`: Documentation code examples and the StackOverflow example
  - `slow-tests`: Long-running integration tests
  - `script-tests`: Runs the `.github/scripts` unit tests on Windows and
    macOS; `ci.yml` runs the full script suite on Ubuntu when selected,
    and the selection, summary and workflow-contract tests on every PR
  - `wheel-build`: Builds the sdist and then the wheel from it, and runs
    `.github/scripts/check_distributions.py`: both archives must contain the
    package, and the wheel must install into a fresh virtual environment,
    import, and report its version through `pymedphys --version`
  - `propagate`: `pymedphys dev propagate` must leave the generated files
    unchanged (exported requirements, `dependency-extra.txt`, `pyproject.hash`,
    `_version.py`)
- **Triggers**: Main branch, `full-test`, or an unclassified input, symlink or
  submodule

#### `mosaiq-db-tests.yml`
SQL Server integration tests for Mosaiq database functionality.

- **Service**: SQL Server 2022 container
- **Triggers**: Main pushes, database or shared code changes, unclassified
  inputs, or `database` / `full-test` labels
- **Features**: Waits for SQL Server to accept connections, then runs the tests once;
  test failures are not hidden by retries

#### `docs.yml`
Builds documentation on PRs that change documentation sources, package Python code, or build tooling.

- **HTML build**: Sphinx warnings and unexpected notebook errors fail the build
- **Link check**: Advisory external-link check with downloadable reports
- **Artefact**: Built HTML is uploaded for inspection
- **Publishing**: ReadTheDocs publishes docs.pymedphys.com independently using
  `.readthedocs.yml`

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
    OS/Python combination. Advisory on pull requests and pushes so a
    newly published advisory cannot turn an unrelated commit red; blocking on
    scheduled and manual runs, where a failure opens or updates the issue
    labelled `security-audit`
  - `python-security`: Bandit, configured in `[tool.bandit]` in
    `pyproject.toml`. Blocking when selected; SARIF is uploaded as an artefact and to
    code scanning when the event has permission (fork PRs cannot upload there)
  - `workflow-audit`: zizmor over `.github` and over any workflow files staged
    in `claude_created_workflows_preview/`, blocking at medium severity and
    above. The offline audits also run through pre-commit; the online ones,
    including the check that each pin's version comment names the tag that
    carries the pinned commit, run only here
- **Triggers**: Weekly, manually, on main pushes, and on every PR (including
  label changes); job-level selection chooses scans while `Security Summary`
  always runs. Python changes retain all three scans: online audits can discover
  new vulnerabilities without a lockfile or workflow edit. Unknown inputs also
  select all scans
- **Coverage**: Change selection applies only to PRs; scheduled and manual runs scan
  even when the last commit did not change security-related files
- **Summary**: Requires every selected scan to succeed
- **Not in the workflow**: secret scanning and push protection are GitHub
  repository settings (Settings, Code security and analysis), and Dependabot
  raises dependency alerts from the same lockfiles

#### `deps.yml`
Automated dependency updates for Python packages.

- **Schedule**: Weekly (Mondays), or manually
- **Steps**: `uv lock --upgrade`, then (only if the lockfile changed)
  `uv sync` and `pymedphys dev propagate` (so
  the exported requirements files, `dependency-extra.txt`, and `pyproject.hash`
  stay current), then the unit tests, the docs build, and a wheel build and
  install before a PR is opened. The data cache is restored only after the
  lockfile changes, because only those runs read data
- **PR**: opened with the CI bot's app token so the normal CI runs on it; a PR
  opened with `GITHUB_TOKEN` triggers no workflows
- **Dependabot** (`.github/dependabot.yml`) owns the GitHub Actions pins (one
  grouped weekly PR) and raises security-fix PRs for Python packages; it does
  not open version-update PRs for Python packages

### AI Assistance

#### `claude.yml`
Claude Code integration for automated code assistance.

- **Triggers**: Comments with `@claude` mention
- **Capabilities**: Code review, issue analysis, PR creation
- **Tools**: File operations, git, uv package management

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
and never restore across a change to `hashes.json`. Jobs that decide later
whether they need data, such as `deps.yml`, use it directly.

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

## Main Branch Workflow

On merge to main:

```
Every job except docs-check (ReadTheDocs publishes main), including:
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

- Ordinary PRs use Ubuntu and Python 3.12 when unit tests are selected. The
  full OS/Python matrix runs on main pushes and `full-test` PRs; integration
  tests also run on PRs with an unclassified input. A green ordinary PR
  therefore does not mean the full matrix ran before merging.
- Pyright is blocking. MyPy remains optional through `continue-on-error`.
- Dependency vulnerabilities are advisory on PRs and pushes. Requiring either
  `Dependency Audit` or `Security Summary` does not turn pip-audit findings into
  a blocking policy; scheduled/manual scans handle them as described above.
- Bandit and zizmor findings at the configured threshold are blocking when
  selected. Documentation builds are blocking when selected; external link
  failures remain advisory if the link checker produces its report.

### The two main-branch rulesets

| Ruleset | Policy | Bypass |
|---------|--------|--------|
| `main-integrity` | Require `CI Summary` and `Security Summary`, require an up-to-date branch, block force pushes and branch deletion | None, including admins |
| `main-reviews` | Require a PR, one approval by an eligible reviewer, and resolution of review conversations | Repository admins, for pull requests only |

Contributors with Write access may merge once these requirements pass. Review is
encouraged for admin-authored PRs too, but an admin may explicitly bypass the
review ruleset. GitHub grants bypass to the person merging, regardless of the
PR author. The bypass does not waive the separate CI ruleset or permit direct
pushes to main.

By maintainer choice, **Dismiss stale approvals when new commits are pushed**
and **Require approval of the most recent reviewable push** remain **off**.
An approval can therefore remain valid after later commits; authors should
request another review for substantive changes. Required checks still need to
pass for the current commit. Code Owner approval is not required. Keep the
additional-approval setting for unattributed Copilot PRs enabled.

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
uv sync --python 3.12 --locked --extra all --group dev

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

- **Python**: 3.10, 3.11, 3.12 (tested in CI; 3.10 reaches end of life in October 2026)
- **uv**: 0.12.15, pinned in CI (`setup-uv`) and in the pre-commit `uv-lock` hook
- **GitHub Actions**: Latest Ubuntu, Windows, and macOS runner images
- **SQL Server**: 2022 Latest (for Mosaiq tests)
