#!/bin/bash

set -ex
source activate test

find . -iname \*.ipynb | xargs -d "\n" nbstripout
git add -A
git diff HEAD --name-only --exit-code -- '*ipynb'

