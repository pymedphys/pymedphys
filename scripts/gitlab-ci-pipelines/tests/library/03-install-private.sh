#!/bin/bash

set -ex
source activate pymedphys

cd $EXTERNAL_GIT_DIR

cd monorepo/Libraries/level-2/decode_trf;
git rev-parse HEAD | GREP_COLORS='ms=34;1' grep $(git rev-parse --short=0 HEAD)

pip install -e .
