#!/bin/bash

set -ex

export PATH="$MINICONDA_DIR/bin:$PATH"
source activate test

cd $EXTERNAL_GIT_DIR

git clone https://gitlab-ci-token:${CI_JOB_TOKEN}@gitlab.instance/CCA-Physics/monorepo.git
cd monorepo/Libraries/level-2/decode_trf

pip install -e
