#!/bin/bash

set -ex
source activate test

pytest --pyargs pymedphys
