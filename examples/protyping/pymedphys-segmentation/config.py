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

import tensorflow as tf

# PATH
# DATA_PATH = "/home/jupyter/prostate_ct_small"
DATA_PATH = "/home/matthew/priv/PROSTATE_TEST/"

# STRUCTURES
STRUCTURE_NAMES = ["patient", "BLADDER"]

# DATA RATIO
# (training, validation, testing)
RATIO = (0.7, 0.2, 0.1)

# DATA SHAPE
GRID_SIZE = 512
CONTEXT = 3
BATCH_SIZE = 5

# MODEL COMPILING
EPOCHS = 1
OPTIMIZER = "adam"
LOSS = tf.nn.sigmoid_cross_entropy_with_logits
METRICS = ["accuracy"]

# DOES THIS BELONG HERE?
TENSOR_TYPE_STR = "float32"
tf.keras.backend.set_floatx(TENSOR_TYPE_STR)
TENSOR_TYPE = eval(f"tf.{TENSOR_TYPE_STR}")
