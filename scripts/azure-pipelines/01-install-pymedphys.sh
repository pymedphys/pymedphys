#!/bin/bash

set -ex

conda uninstall pymedphys
conda install -q nbstripout pylint coverage mypy pytest

MATPLOTLIB_RC=`python -c "import matplotlib; print(matplotlib.matplotlib_fname())"`
echo "backend: Agg" > $MATPLOTLIB_RC

pip install -e .
