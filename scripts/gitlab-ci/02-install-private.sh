#!/bin/bash

set -ex
source activate test

cd $EXTERNAL_GIT_DIR

git rev-parse --verify HEAD

cd monorepo/Libraries/level-2/decode_trf;
pip install -e .
