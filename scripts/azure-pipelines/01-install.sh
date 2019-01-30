set -ex

echo $PATH

which activate
source activate pymedphys
which pip

/usr/bin/sudo pip install -e .
