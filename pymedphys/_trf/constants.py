# Copyright (C) 2018 Cancer Care Associates

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
# Affero General Public License. These additional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


import json
import os

CONFIG_FILEPATH = os.path.join(os.path.dirname(__file__), "config.json")

with open(CONFIG_FILEPATH) as json_data_file:
    CONFIG = json.load(json_data_file)

Y1_LEAF_BANK_NAMES = [
    "Y1 Leaf {}/Scaled Actual (mm)".format(item) for item in range(1, 81)
]

Y2_LEAF_BANK_NAMES = [
    "Y2 Leaf {}/Scaled Actual (mm)".format(item) for item in range(1, 81)
]

JAW_NAMES = ["X1 Diaphragm/Scaled Actual (mm)", "X2 Diaphragm/Scaled Actual (mm)"]

GANTRY_NAME = "Step Gantry/Scaled Actual (deg)"
COLLIMATOR_NAME = "Step Collimator/Scaled Actual (deg)"
