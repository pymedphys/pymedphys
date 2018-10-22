#!/bin/bash

set -ex

export PATH="$MINICONDA_DIR/bin:$PATH"
source activate test

conda install pymedphys --only-deps

pip install .