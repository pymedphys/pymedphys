# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Setup and Installation

```bash
# Install with uv (required for development)
uv sync --all-extras

# Install pre-commit hooks
uv run pre-commit install

# Install for user use only
pip install pymedphys[user]
```

### Testing

```bash
# Run all tests
uv run pymedphys dev tests

# Run specific test file or directory
uv run pymedphys dev tests tests/path/to/test.py

# Run with specific pytest options
uv run pymedphys dev tests -v -s -k "test_name"

# Run doctests
uv run pymedphys dev doctests

# Run E2E tests with Cypress
uv run pymedphys dev tests --cypress
```

### Code Quality

```bash
# Run linting with ruff (automatically fixes issues)
uv run ruff check --fix .
uv run ruff format .

# Run type checking with pyright
uv run pyright

# Run pre-commit on all files
uv run pre-commit run --all-files

# Check imports are clean
uv run pymedphys dev imports
```

### Documentation

```bash
# Build documentation
uv run pymedphys dev docs

# The docs use Jupyter Book and are located in lib/pymedphys/docs/
```

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
- Mock data and fixtures are in `_mocks/` and test data directories
- E2E tests use Cypress for Streamlit app testing

### Dependencies and Extras

The project uses uv with optional dependency groups:
- `user`: Standard user installation
- `all`: All features including development tools
- `dev`: Development tools (linting, formatting)
- `docs`: Documentation building
- `tests`: Testing dependencies
- Specific features: `dicom`, `mosaiq`, `icom`, etc.

## Important Implementation Notes

1. **Beta Status**: PyMedPhys is in beta (version 0.x.x). APIs may change between releases.

2. **DICOM Handling**: The library provides extensive DICOM functionality including anonymization, coordinate systems, dose calculations, and RT plan manipulation.

3. **Gamma Analysis**: Core functionality for dose distribution comparison using efficient shell-based algorithm implementation.

4. **Anthropic Integration**: Built-in Claude integration for AI-assisted features (requires API key).

5. **Streamlit Apps**: Web-based tools for various tasks (anonymization, metersetmap, dose analysis) in `_streamlit/apps/`.

6. **Database Connections**: Mosaiq integration requires appropriate database credentials and SQL Server access.

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

### Dependency Updates

When updating dependencies:
1. Update version constraints in `pyproject.toml`
2. Run `uv lock` to regenerate `uv.lock`
3. Test changes to ensure nothing breaks
4. Note: If `uv lock` is not in allowed tools, request it be added

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
