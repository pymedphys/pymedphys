#!/bin/bash
set -ex

pip install dist/*.whl
pymedphys --help
python -c "import pymedphys"
