#!/bin/bash

# Build script for Unix-like systems (Linux, macOS)
set -ex

# Install using pip with poetry-core as the build backend
${PYTHON} -m pip install . -vv --no-deps --no-build-isolation

# Copy license file to the conda environment
cp LICENSE "${PREFIX}/LICENSE-pymedphys"