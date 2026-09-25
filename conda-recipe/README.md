# Conda recipe draft

This directory contains an unfinished recipe, not a tested distribution path
for the current PyMedPhys source. The GitHub Actions release workflow builds
a wheel and source distribution with uv and Hatchling and publishes to PyPI.
It does not build or publish this Conda recipe.

For a current installation, use the
[installation guide](https://docs.pymedphys.com/en/latest/users/get-started/quick-start.html).
A Conda environment can still be used with pip, but this draft does not
establish the availability or compatibility of a conda-forge package.

## What must be fixed before building

Compare the recipe with the exact release's `pyproject.toml` and source archive:

- Supply a real version and SHA-256. `meta.yaml` currently falls back to
  `0.0.0` and refers to an undefined `sha256` template variable; it does not
  extract the version from `pyproject.toml`.
- Replace the old Poetry backend requirement with the backend required by
  that release. Current source uses `hatchling.build`.
- Reconcile dependency versions and optional extras. The recipe's Streamlit
  and other constraints do not match the current project metadata.
- Resolve the combination of `noarch: python` and platform selectors.
- Correct the variant configuration: the zipped Python and NumPy variant
  lists currently have different lengths.
- Reconcile the inline `build.script` with the separate `build.sh` and
  `bld.bat` scripts, then validate the resulting build.
- Repair the smoke tests. `pymedphys.gamma` is a callable rather than an
  importable module, and the CLI has no `--version` option. Inspect the
  version with `python -c "import pymedphys; print(pymedphys.__version__)"`.

`generate_recipe.sh` records an optional Grayskull starting point. Generated
recipes still require review and Conda build/install testing. Use
[conda-forge's contribution guide](https://conda-forge.org/docs/maintainer/adding_pkgs/)
for submission or feedstock-update instructions after the recipe is working.
