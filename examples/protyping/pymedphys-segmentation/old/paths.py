# Copyright (C) 2020 Matthew Cooper, Simon Biggs.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import glob
import random

import config


def get_paths(data_path, context):
    patient_paths = glob.glob(data_path + "/*")

    context_paths = glob.glob(data_path + "/*/*CT*", recursive=True)
    context_paths.sort()
    input_paths = [
        glob.glob(path + "/*CT*")[context:-context] for path in patient_paths
    ]
    input_paths = [item for sublist in input_paths for item in sublist]
    random.shuffle(input_paths)

    label_paths = glob.glob(data_path + "/*/*RS*", recursive=True)

    assert len(context_paths) - (len(label_paths) * 2 * context) == len(input_paths)

    print("----------")
    print("Patient paths found: ", len(label_paths))
    print("Total input paths:", len(input_paths))
    print("\n")
    return input_paths, context_paths, label_paths


def split_paths(input_paths, ratio):
    num = len(input_paths)
    num_train = int(num * ratio[0] // 1)
    num_valid = int(num * ratio[1] // 1)
    num_test = int(num * ratio[2] // 1)

    print("Training paths:", num_train)
    print("Valid paths:", num_valid)
    print("Test paths:", num_test)

    train_paths = input_paths[0:num_train]
    valid_paths = input_paths[num_train : num_train + num_valid]
    test_paths = input_paths[num_train + num_valid :]

    print("----------")
    print("Steps p. training epoch (# batches):", len(train_paths) // config.BATCH_SIZE)
    print("\n")

    return train_paths, valid_paths, test_paths
