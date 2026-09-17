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
                       `-- summary

Schedule / manual run / main push / relevant PR -> security.yml
Schedule -> deps.yml
Release -> release.yml -> lint, type-check, unit and integration tests
Issue comment -> claude-assistant.yml / claude.yml
```

## Workflow Structure

### Core Workflows (Run on All PRs)

#### `ci.yml` - Main Orchestrator
Coordinates all CI checks based on file changes, labels, and event types.

- **Triggers**: Push to main, pull requests (including label changes, which queue
  behind an in-flight run rather than cancelling it), workflow_call
- **Jobs**:
  - `changes`: Detects file changes using path filters
  - `pre-commit`: Auto-formatting and basic checks
  - `lint`: Code quality (always runs)
  - `type-check`: Static type checking (always runs)
  - `unit-tests`: Fast unit tests (always runs)
  - `integration-tests`: Extended tests (conditional)
  - `mosaiq-db-tests`: Database tests (conditional)
  - `docs-check`: Documentation build and artifact (conditional)
  - `summary`: Requires core checks and selected extended checks to succeed

#### `pre-commit.yml`
Runs pre-commit hooks for code formatting and basic checks.

- **Features**:
  - Auto-fixes issues on PRs
  - Commits fixes automatically with bot account
  - Caches pre-commit environments

#### `lint.yml`
Dedicated linting workflow for code quality.

- **Jobs**:
  - `lint`: Comprehensive Python linting with Pylint
- Ruff linting and formatting run through pre-commit
- **Always runs on PRs** for early issue detection

#### `type-check.yml`
Static type checking for type safety.

- **Jobs**:
  - `pyright`: Primary type checker
  - `mypy`: Secondary checker (optional/non-blocking)
- **Always runs on PRs** to ensure type safety

#### `unit-tests.yml`
Fast unit tests with smart matrix strategy.

- **Features**:
  - Full OS matrix on main (Ubuntu, Windows, macOS)
  - Quick mode for PRs (Ubuntu + latest supported Python version)
  - Installs the `user` extra so the headless Streamlit GUI tests run
  - Full OS and Python matrix for PRs labeled `full-test`
  - Excludes slow tests for rapid feedback
  - JUnit XML report generation

### Extended Workflows (Conditional)

#### `integration-tests.yml`
Comprehensive testing beyond unit tests.

- **Test Types**:
  - `doctests`: Documentation code examples
  - `slow-tests`: Long-running integration tests
  - `stackoverflow`: Example code validation
  - `wheel-build`: Package build verification
  - `propagate`: Propagation script tests
- **Triggers**: Main branch or `full-test` label

#### `mosaiq-db-tests.yml`
SQL Server integration tests for Mosaiq database functionality.

- **Service**: SQL Server 2022 container
- **Triggers**: Main pushes, database code changes, or `database` / `full-test` labels
- **Features**: Automatic retries for connection stability

#### `docs.yml`
Builds documentation on PRs that change documentation sources, package Python code, or build tooling.

- **HTML build**: Sphinx warnings and unexpected notebook errors fail the build
- **Link check**: Advisory external-link check with downloadable reports
- **Artifact**: Built HTML is uploaded for inspection
- **Publishing**: ReadTheDocs publishes docs.pymedphys.com independently using
  `.readthedocs.yml`

### Release & Maintenance

#### `release.yml`
Handles PyPI package publishing with quality gates.

- **Quality Checks**: Runs lint, type-check, unit, and integration tests
- **Features**:
  - TestPyPI dry-run capability
  - PyPI trusted publishing (no API tokens)
  - Automatic release asset upload
  - Installation verification

#### `security.yml`
Security scanning with pinned tools run through `uvx`, so nothing is installed
into the project environment.

- **Scans**:
  - `dependency-audit`: pip-audit over the exported `uv.lock`, which covers
    every extra and platform marker. Advisory on pull requests and pushes so a
    newly published advisory cannot turn an unrelated commit red; blocking on
    scheduled and manual runs, where a failure opens or updates the issue
    labelled `security-audit`
  - `python-security`: Bandit, configured in `[tool.bandit]` in
    `pyproject.toml`. Blocking on every event; the SARIF report is uploaded to
    code scanning
  - `workflow-audit`: zizmor over `.github` and over any workflow files staged
    in `claude_created_workflows_preview/`, blocking at medium severity and
    above. The offline audits also run through pre-commit; the online ones,
    including the check that each pin's version comment names the tag that
    carries the pinned commit, run only here
- **Triggers**: Weekly, manually, on main pushes, and on relevant PR changes
- **Coverage**: Path filtering applies only to PRs; scheduled and manual runs scan
  even when the last commit did not change security-related files
- **Summary**: Requires every selected scan to succeed
- **Not in the workflow**: secret scanning and push protection are GitHub
  repository settings (Settings, Code security and analysis), and Dependabot
  raises dependency alerts from the same lockfiles

#### `deps.yml`
Automated dependency updates.

- **Schedule**: Weekly (Mondays)
- **Features**:
  - Creates PR with uv lock updates
  - Includes changelog in PR description
  - Runs tests before creating PR

### AI Assistance

#### `claude.yml`
Claude Code integration for automated code assistance.

- **Triggers**: Comments with `@claude` mention
- **Capabilities**: Code review, issue analysis, PR creation
- **Tools**: File operations, git, uv package management

#### `claude-assistant.yml`
Claude chatbot for issue discussions.

- **Triggers**: Comments with `!claude` mention
- **Features**:
  - Rate limiting protection
  - Security filtering
  - Context-aware responses

## Composite Actions

### `actions/setup-project/action.yml`
Standardized project setup for all workflows.

- **Features**:
  - Python setup with configurable version
  - uv package manager with caching
  - PyMedPhys data caching
  - Dependency installation with extras

## PR Workflow

For a typical pull request:

```
Always Run:
├── pre-commit       # Auto-formatting
├── lint             # Ruff + Pylint
├── type-check       # Pyright
└── unit-tests       # Quick mode (Ubuntu + latest supported Python version)

Conditional (also recalculated when labels change):
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
| `ANTHROPIC_API_KEY` | Claude AI API access | claude.yml, claude-assistant.yml |
| `GITHUB_TOKEN` | GitHub API access (automatic) | All workflows |
| `PYMEDPHYS_CI_BOT_ID` | Bot app ID for auto-commits | pre-commit.yml (optional) |
| `PYMEDPHYS_CI_BOT_TOKEN` | Bot private key | pre-commit.yml (optional) |

## Environments

| Environment | Description | Protection Rules |
|-------------|-------------|------------------|
| `pypi` | PyPI publishing | Required reviewers, main branch only |
| `claude-api` | Claude API access | Rate limiting recommended |

## Branch Protection Settings

Configure branch protection to require the CI and security summary checks.
These summaries fail when a core check or a selected extended check fails,
is cancelled, or is unexpectedly skipped. The CI summary also prevents an
outdated commit from passing after pre-commit pushes automatic fixes.

The pre-commit workflow includes actionlint. Remove an obsolete standalone
Actionlint requirement if it remains in the repository settings.

## Labels for Manual Triggers

- `full-test` - Run the full unit-test matrix, slow integration tests, and database tests on a PR
- `database` - Force database tests to run


## Testing Workflows Locally

```bash
# Install act
brew install act  # or appropriate for your OS

# Test CI workflow
act push -W .github/workflows/ci.yml

# Test with specific inputs
act push -W .github/workflows/unit-tests.yml \
  --input python-matrix='["3.12"]' \
  --input quick=true

# Test PR workflow
act pull_request -W .github/workflows/ci.yml
```

### Local Development Commands

```bash
# Install with dev dependencies
uv sync --frozen --extra all --group dev

# Run all pre-commit hooks
uv run pre-commit run --all-files

# Run specific checks matching CI
uv run ruff check
uv run ruff format --check
uv run pyright
uv run pymedphys dev lint
uv run pymedphys dev tests -m "not slow"

# Run slow tests locally
uv run pymedphys dev tests --slow -m slow

# Build docs locally
uv run pymedphys dev docs
```


## Security Considerations

- **Never commit secrets**: Use GitHub Secrets
- **Review permissions**: Minimum required for each job; write permissions
  belong at the job level, never at the workflow level
- **Enable Dependabot**: Keep actions updated
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

- **Python**: 3.10, 3.12 (tested in CI)
- **uv**: Latest version (auto-updated)
- **GitHub Actions**: Latest Ubuntu, Windows, and macOS runner images
- **SQL Server**: 2022 Latest (for Mosaiq tests)
