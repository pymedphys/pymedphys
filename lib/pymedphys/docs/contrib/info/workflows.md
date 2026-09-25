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
Published release / manual run -> release.yml -> quality checks, publishing, and PyPI verification
Issue comment -> claude.yml
```

## Workflow Structure

### Core Workflows (Run on All PRs)

#### `ci.yml` - Main Orchestrator
Coordinates all CI checks based on file changes, labels, and event types.

- **Triggers**: Push to main, pull requests (including label changes, which queue
  behind an in-flight run rather than cancelling it)
- **Jobs**:
  - `changes`: Detects file changes using path filters
  - `pre-commit`: Auto-formatting and basic checks
  - `lint`: Code quality
  - `type-check`: Static type checking
  - `unit-tests`: Fast unit tests
  - `integration-tests`: Extended tests (conditional)
  - `mosaiq-db-tests`: Database tests (conditional)
  - `docs-check`: Documentation build and artefact (conditional)
  - `summary`: Requires core checks and selected extended checks to succeed

Lint, type checks, and unit tests normally run on every PR. If pre-commit
pushes an auto-fix, those jobs are skipped for the superseded commit and the
summary fails until a fresh run passes on the new commit. Upstream failures
can also skip dependent jobs; the summaries reject those unexpected skips.

#### `pre-commit.yml`
Runs pre-commit hooks for code formatting and basic checks.

- **Features**:
  - Applies the configured hooks, including Ruff, actionlint, and offline zizmor
  - Can push fixes on same-repository PRs when bot credentials are available
  - Fork PR authors must apply and push their fixes themselves
  - Caches pre-commit environments

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
  - Quick mode for PRs (Ubuntu + Python 3.12)
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
  - `wheel-build`: Builds the sdist and then the wheel from it, and runs
    `.github/scripts/check_distributions.py`: both archives must contain the
    package, and the wheel must install into a fresh virtual environment,
    import, and report its version through `pymedphys --version`
  - `propagate`: `pymedphys dev propagate` must leave the generated files
    unchanged (exported requirements, `dependency-extra.txt`, `pyproject.hash`,
    `_version.py`)
- **Triggers**: Main branch or `full-test` label

#### `mosaiq-db-tests.yml`
SQL Server integration tests for Mosaiq database functionality.

- **Service**: SQL Server 2022 container
- **Triggers**: Main pushes, database code changes, or `database` / `full-test` labels
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

Publishes to PyPI or TestPyPI behind quality gates.

- **Triggers and destinations**: A published GitHub release, including a
  pre-release, publishes to PyPI and attaches the sdist and wheel only after
  published-file verification succeeds. A manual run publishes to TestPyPI
  only (`dry_run=true`) or PyPI only (`dry_run=false`), without the tag check
  or release assets
- **Before publishing**: Lint, type checks, the full unit-test matrix,
  integration tests, and the same distribution checks as `wheel-build`. For a
  release, the build also fails unless the tag is `v` followed by the package
  version
- **Publishing**: PyPI trusted publishing through the `pypi` or `testpypi`
  environment, with no stored API token. Files already on the index are
  skipped, so a re-run after a partial upload is safe
- **After publishing**: `verify-published` installs the wheel and the sdist
  from the index just published to, separately on Linux, Windows, and macOS,
  with `check_distributions.py --published`, and requires both to match the
  files built in the run. It also runs after a TestPyPI rehearsal, so the job
  is exercised before a release. PyMedPhys's exact archive URLs come from the
  selected index; runtime and build dependencies use PyPI
- **Recovery**: The original `dist` artefact is retained for 30 days. Retry
  failed jobs using those files; rebuilding an existing release need not
  reproduce its archive hashes. Never replace a published version's tag
- **Release Summary**: Reports every job's result; it is not a gate
- **Limitation**: Assets are attached after the release is published, which
  GitHub's [immutable releases](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases)
  forbid. Before enabling immutable releases, change the workflow to attach the
  assets while the release is still a draft

The [release procedure](release-guide.md) covers tagging, development releases,
and recovery.

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
- **Triggers**: Weekly, manually, on main pushes, and on every PR; job-level path
  filters select the scans, while `Security Summary` always runs
- **Coverage**: Path filtering applies only to PRs; scheduled and manual runs scan
  even when the last commit did not change security-related files
- **Summary**: Requires every selected scan to succeed
- **Not in the workflow**: secret scanning and push protection are GitHub
  repository settings (Settings, Code security and analysis), and Dependabot
  raises dependency alerts from the same lockfiles

#### `deps.yml`
Automated dependency updates for Python packages.

- **Schedule**: Weekly (Mondays), or manually
- **Steps**: `uv lock --upgrade`, `uv sync`, and `pymedphys dev propagate` (so
  the exported requirements files, `dependency-extra.txt`, and `pyproject.hash`
  stay current), then the unit tests, the docs build, and a wheel build and
  install before a PR is opened
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
  - uv package manager with caching
  - PyMedPhys data caching
  - Dependency installation with extras

## PR Workflow

For a typical pull request:

```
Core checks (subject to the pre-commit dependency above):
├── pre-commit       # Auto-formatting
├── lint             # Pylint; Ruff runs in pre-commit
├── type-check       # Pyright
└── unit-tests       # Quick mode (Ubuntu + Python 3.12)

Conditional (also recalculated when labels change):
├── integration-tests # full-test label
├── mosaiq-db-tests  # Database files changed, database or full-test label
├── docs-check       # Documentation sources or build tooling changed
└── security         # If Python/config files changed
```

## Main Branch Workflow

On merge to main:

```
Core checks, plus:
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
| `pypi` | Production publishing | Configure trusted publishing, release approvers, and allowed `main` branch / `v*` tag refs |
| `testpypi` | Manual release dry runs | Configure TestPyPI trusted publishing and allowed `main` branch / `v*` tag refs |

Environment protection is configured in GitHub Settings, not by the workflow's
`environment` field. Create and verify these environments before releasing;
referencing an absent environment can create it without protection rules.
The trusted publisher registered with PyPI or TestPyPI must match this
repository, `release.yml`, and the environment name; the
[release guide](release-guide.md) lists the settings.

## Required checks and pull request reviews

### Why the summaries are required

The required GitHub Actions check names for `main` are **`CI Summary`** (from
`ci.yml`) and **`Security Summary`** (from `security.yml`). Select GitHub Actions
as their expected source in the `main-integrity` ruleset. The release workflow's
**`Release Summary`** is a report, not a merge gate, and must not be required on
pull requests.

| Required check | Checks it covers |
|----------------|------------------|
| `CI Summary` | Change selection, pre-commit, Pylint, the type-check workflow, unit tests, and selected integration, database, and documentation checks |
| `Security Summary` | Change selection and selected dependency, Python security, and workflow security audits |

These are executable gates, not just reports. Both use `if: always()` and
`.github/scripts/check_workflow_status.py` to inspect their dependencies. A core
check must succeed. A selected conditional check must also succeed; a skipped
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

- Ordinary PRs use Ubuntu and Python 3.12 for unit tests. The full OS/Python
  matrix and integration tests run on main pushes and `full-test` PRs. A green
  ordinary PR therefore does not mean the full matrix ran before merging.
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
