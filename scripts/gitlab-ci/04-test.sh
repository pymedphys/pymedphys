#!/bin/bash

set -ex
source activate test

pytest --pylint --pylint-error-types=EF
