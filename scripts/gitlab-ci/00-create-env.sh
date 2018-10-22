#!/bin/bash

set -ex

apt update
apt install libgl1-mesa-glx -y

conda config --set always_yes yes --set changeps1 no
conda config --add channels conda-forge

conda update -q conda
conda info -a # for debugging

conda create -q -n test pytest pymedphys
source activate test

conda uninstall pymedphys

pip install .