# Conda Recipe for PyMedPhys

This directory contains the conda recipe files needed to build PyMedPhys for conda/conda-forge.

## Files Overview

- **meta.yaml**: The main recipe file that defines package metadata, dependencies, and build instructions
- **build.sh**: Build script for Unix-like systems (Linux, macOS)
- **bld.bat**: Build script for Windows
- **conda_build_config.yaml**: Configuration for conda-build variants

## Building Locally

To build the conda package locally:

```bash
conda build conda-recipe/
```

## Testing the Package

After building, you can test the package:

```bash
conda create -n test-pymedphys python=3.11
conda activate test-pymedphys
conda install --use-local pymedphys
python -c "import pymedphys; print(pymedphys.__version__)"
```

## Submitting to conda-forge

To submit to conda-forge:

1. Fork https://github.com/conda-forge/staged-recipes
2. Create a new branch
3. Copy this recipe to `recipes/pymedphys/`
4. Create a pull request
5. Address any feedback from conda-forge reviewers

For updates to an existing feedstock:
1. Fork https://github.com/conda-forge/pymedphys-feedstock
2. Update the recipe files
3. Create a pull request
4. The conda-forge bot will help with the process

## Notes on Dependencies

- **pymssql**: Excluded on Windows due to build complexity
- **pywin32**: Only included on Windows platforms
- Some dependencies might need to be added to conda-forge if not already available
- The recipe uses `noarch: python` since PyMedPhys is pure Python

## Handling Poetry-based Projects

Since PyMedPhys uses Poetry, the recipe:
- Requires `poetry-core` as a host dependency
- Uses pip for installation with `--no-build-isolation`
- The version is automatically extracted from git tags or pyproject.toml