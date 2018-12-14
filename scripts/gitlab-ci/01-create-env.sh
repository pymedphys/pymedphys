#!/bin/bash

set -ex

conda config --set always_yes yes --set changeps1 no
conda config --add channels conda-forge

conda update -q conda
conda info -a # for debugging

conda create -q -n test pytest pymedphys
source activate test

pip install pytest-pylint

conda uninstall pymedphys

MATPLOTLIB_RC=`python -c "import matplotlib; print(matplotlib.matplotlib_fname())"`
echo "backend: Agg" > $MATPLOTLIB_RC

pip install -e .
