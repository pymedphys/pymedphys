#!/bin/bash

set -ex

mypy src/pymedphys
pytest -v --pylint --pylint-error-types=EF