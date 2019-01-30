#!/bin/bash

set -ex

conda config --set always_yes yes --set changeps1 no
conda config --add channels conda-forge
conda info -a

conda update -q conda

conda env create -f ./environment.yml
source activate pymedphys

conda uninstall pymedphys
conda install -q nbstripout pylint coverage mypy pytest

MATPLOTLIB_RC=`python -c "import matplotlib; print(matplotlib.matplotlib_fname())"`
echo "backend: Agg" > $MATPLOTLIB_RC

pip install -e .
