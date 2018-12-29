#!/bin/bash

set -ex

rm pytest.ini
mv pytest-no-testmon.ini pytest.ini

bash ./tests-all.sh