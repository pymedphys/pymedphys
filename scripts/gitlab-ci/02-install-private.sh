#!/bin/bash

set -ex
source activate test

cd $EXTERNAL_GIT_DIR

git rev-parse HEAD | GREP_COLORS='ms=34;1' grep $(git rev-parse --short=0 HEAD)

cd monorepo/Libraries/level-2/decode_trf;
pip install -e .

