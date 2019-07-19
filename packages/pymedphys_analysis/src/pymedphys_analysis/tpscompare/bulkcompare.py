# Copyright (C) 2019 Cancer Care Associates

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version (the "AGPL-3.0+").

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License and the additional terms for more
# details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

# ADDITIONAL TERMS are also included as allowed by Section 7 of the GNU
# Affrero General Public License. These aditional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


import re
import pathlib

from .mephysto import absolute_scans_from_mephysto


def bulk_load_mephysto(directory, regex, absolute_doses, normalisation_depth):
    directory = pathlib.Path(directory)

    mephysto_files = list(directory.glob('*.mcc'))
    matches = [
        re.match(regex, filepath.name) for filepath in mephysto_files
    ]
    keys = [
        match.group(1) for match in matches if match
    ]

    if not set(keys).issubset(set(absolute_doses.keys())):
        raise ValueError("For each file key an absolute dose must be provided")

    mephysto_file_map = {
        key: filepath for key, filepath in zip(keys, mephysto_files)
    }

    absolute_scans_per_field = {
        key: absolute_scans_from_mephysto(
            mephysto_file_map[key], absolute_doses[key], normalisation_depth)
        for key in keys
    }

    return absolute_scans_per_field


def bulk_compare(doses, plan, ):
    pass
