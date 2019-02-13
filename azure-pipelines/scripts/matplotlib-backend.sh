set -ex

if [[ "$OSTYPE" == "msys" ]]; then
  source activate pymedphys
fi

which python

MATPLOTLIB_RC=`python -c "import matplotlib; print(matplotlib.matplotlib_fname())"`
echo "backend: Agg" > $MATPLOTLIB_RC