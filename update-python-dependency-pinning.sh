#!/bin/bash

set -ex

# conda create -n pymedphys python=3.7 pymedphys

source activate pymedphys
conda update --all -y
conda env export | grep -v "^prefix: " > environment.yml
