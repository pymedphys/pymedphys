# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Setup and Installation

```bash
# Install with Poetry (required for development)
poetry install -E all

# Install pre-commit hooks
poetry run pre-commit install

# Install for user use only
pip install pymedphys[user]
```

### Testing

```bash
# Run all tests
poetry run pymedphys dev tests

# Run specific test file or directory
poetry run pymedphys dev tests tests/path/to/test.py

# Run with specific pytest options
poetry run pymedphys dev tests -v -s -k "test_name"

# Run doctests
poetry run pymedphys dev doctests

# Run E2E tests with Cypress
poetry run pymedphys dev tests --cypress
```

### Code Quality

```bash
# Run linting with ruff (automatically fixes issues)
poetry run ruff check --fix .
poetry run ruff format .

# Run type checking with pyright
poetry run pyright

# Run pre-commit on all files
poetry run pre-commit run --all-files

# Check imports are clean
poetry run pymedphys dev imports
```

### Documentation

```bash
# Build documentation
poetry run pymedphys dev docs

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

The project uses Poetry with optional dependency groups:
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