#!/bin/bash

set -ex

echo $PATH

which activate
source activate pymedphys
which pip

pip install -e .
