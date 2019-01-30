#!/bin/bash

set -ex

echo $PATH

which activate
source activate pymedphys
which xargs
which nbstripout

find . -iname \*.ipynb | xargs -d "\n" nbstripout
git add -A
git diff HEAD --name-only --exit-code -- '*ipynb'
