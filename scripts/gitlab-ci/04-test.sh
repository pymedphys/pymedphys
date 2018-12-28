#!/bin/bash

set -ex

rm pytest.ini
mv pytest-no-testmon.ini pytest.ini

pytest --pylint --pylint-error-types=EF
