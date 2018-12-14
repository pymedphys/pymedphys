#!/bin/bash

set -ex
source activate test

cd $EXTERNAL_GIT_DIR

cd monorepo/Libraries/level-2/decode_trf;
pip install -e .

