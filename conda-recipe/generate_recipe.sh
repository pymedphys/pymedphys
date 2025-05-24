#!/bin/bash
# Script to generate/update conda recipe using grayskull

# Install grayskull if not available
# conda install -c conda-forge grayskull

# Generate recipe from PyPI
grayskull pypi pymedphys

# Or generate from local setup
# grayskull pypi . --local

# The generated recipe will be in pymedphys/meta.yaml
# You'll need to:
# 1. Review and adjust dependencies
# 2. Add any platform-specific requirements
# 3. Update test commands
# 4. Add recipe maintainers
