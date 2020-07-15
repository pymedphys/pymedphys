# Copyright (C) 2018 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


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
