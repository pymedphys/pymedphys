#!/bin/bash

set -ex

find . -iname \*.ipynb | xargs -d "\n" nbstripout
git add -A
git diff HEAD --name-only --exit-code -- '*ipynb'

