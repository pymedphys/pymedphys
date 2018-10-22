#!/bin/bash

set -ex
source activate test

mkdir $EXTERNAL_GIT_DIR
cd $EXTERNAL_GIT_DIR

git clone https://gitlab-ci-token:${CI_JOB_TOKEN}@gitlab.com/CCA-Physics/monorepo.git
cd monorepo/Libraries/level-2/decode_trf

pip install .
