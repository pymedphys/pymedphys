# Copyright (C) 2020 Matthew Cooper

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import config

attrs_to_check = [
    "BATCH_SIZE",
    "DEVICE",
    "MODEL_OUTPUT_CHANNELS",
    "MODEL_WEIGHTS",
    "ROOT_UID",
    "SCP_AE_TITLE",
    "SCP_IP",
    "SCP_PORT",
    "SCP_STORAGE_PATH",
    "SCU_AE_TITLE",
    "SCU_IP",
    "SCU_PORT",
    "TEST_DATASET",
    "TRAINING_DATA_MEAN",
    "TRAINING_DATA_STD",
    "FORWARD_IMAGES",
]

has_attrs = dir(config)
missing_attrs = []
test_passed = True

for attr in attrs_to_check:
    try:
        assert attr in has_attrs
    except AssertionError:
        missing_attrs.append(attr)
        test_passed = False

print("\n------------------------------------")
print("TEST PASSED:", test_passed)
print("------------------------------------")
if not test_passed:
    print("Missing:")
    for attr in missing_attrs:
        print(attr)
