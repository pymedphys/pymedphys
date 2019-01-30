#!/bin/bash

set -ex

conda install --channel conda-forge pymedphys nbstripout pylint coverage mypy pytest
conda uninstall pymedphys

MATPLOTLIB_RC=`python -c "import matplotlib; print(matplotlib.matplotlib_fname())"`
echo "backend: Agg" > $MATPLOTLIB_RC

pip install -e .
