#!/bin/bash

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

set -ex

export PATH="$MINICONDA_DIR/bin:$PATH"

conda remove --name test --all || true
conda create -q -n test python=$PYTHON pytest pymedphys
source activate test

conda uninstall pymedphys

pip install .