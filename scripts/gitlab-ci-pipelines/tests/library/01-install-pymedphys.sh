#!/bin/bash

set -ex

conda env update -f ./environment/environment.yml
conda uninstall pymedphys

pip install -e .
