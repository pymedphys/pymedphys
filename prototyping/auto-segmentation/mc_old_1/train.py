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

import config
import data_generator
import model
import paths

input_paths, context_paths, label_paths = paths.get_paths(
    config.DATA_PATH, config.CONTEXT
)

train_paths, valid_paths, test_paths = paths.split_paths(input_paths, config.RATIO)

train_gen = data_generator.data_gen(
    train_paths,
    context_paths,
    label_paths,
    context=config.CONTEXT,
    batch_size=config.BATCH_SIZE,
    structure_names=config.STRUCTURE_NAMES,
    resize=config.GRID_SIZE,
)

valid_gen = data_generator.data_gen(
    valid_paths,
    context_paths,
    label_paths,
    context=config.CONTEXT,
    batch_size=config.BATCH_SIZE,
    structure_names=config.STRUCTURE_NAMES,
    resize=config.GRID_SIZE,
)

test_gen = data_generator.data_gen(
    test_paths,
    context_paths,
    label_paths,
    context=config.CONTEXT,
    batch_size=config.BATCH_SIZE,
    structure_names=config.STRUCTURE_NAMES,
    resize=config.GRID_SIZE,
)

model = model.Model()

model.compile(optimizer=config.OPTIMIZER, loss=config.LOSS)

steps_per_epoch = len(train_paths) // config.BATCH_SIZE

model.fit(
    train_gen,
    epochs=config.EPOCHS,
    steps_per_epoch=steps_per_epoch,
    validation_data=valid_gen,
)
