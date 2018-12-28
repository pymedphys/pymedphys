#!/bin/bash

set -ex
source activate test

rm pytest.ini
mv pytest-no-testmon.ini pytest.ini

pytest --pylint --pylint-error-types=EF
