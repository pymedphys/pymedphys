#!/bin/bash

set -ex
source activate test

find . -iname \*.ipynb | xargs nbstripout
git add -A
git diff HEAD --exit-code
