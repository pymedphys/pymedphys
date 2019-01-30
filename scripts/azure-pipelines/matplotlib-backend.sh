set -ex

source activate matplotlib

MATPLOTLIB_RC=`python -c "import matplotlib; print(matplotlib.matplotlib_fname())"`
echo "backend: Agg" > $MATPLOTLIB_RC