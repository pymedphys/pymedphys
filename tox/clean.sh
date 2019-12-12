#!/bin/bash
set -ex

pip install  --force-reinstall dist/*.whl
pymedphys --help
python -c "import pymedphys"
