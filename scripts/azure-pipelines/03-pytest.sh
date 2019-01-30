set -ex

echo $PATH

which activate
source activate pymedphys

which python
python setup.py test