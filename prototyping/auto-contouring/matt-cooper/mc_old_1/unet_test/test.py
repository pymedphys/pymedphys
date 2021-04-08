import matplotlib.pyplot as plt

from generator import DataGen
from header import *
from model_test1 import *
from paths import *

input_paths, context_paths, label_paths = get_paths(DATA_PATH, CONTEXT)

train_paths, valid_paths, test_paths = split_paths(input_paths, SPLIT_RATIO)

# For quick training
train_paths = train_paths[0:20]
valid_paths = valid_paths[0:10]
test_paths = test_paths[0:10]

train_gen = DataGen(
    train_paths,
    context_paths,
    label_paths,
    context=CONTEXT,
    batch_size=BATCH_SIZE,
    structure_names=STRUCTURE_NAMES,
)

valid_gen = DataGen(
    valid_paths,
    context_paths,
    label_paths,
    context=CONTEXT,
    batch_size=BATCH_SIZE,
    structure_names=STRUCTURE_NAMES,
)

test_gen = DataGen(
    test_paths,
    context_paths,
    label_paths,
    context=CONTEXT,
    batch_size=BATCH_SIZE,
    structure_names=STRUCTURE_NAMES,
)

model = Model(INPUT_SHAPE, OUTPUT_CHANNELS)

model.compile(optimizer=OPTIMIZER, loss=LOSS)

model.fit_generator(
    generator=train_gen,
    validation_data=valid_gen,
    steps_per_epoch=len(train_paths) // BATCH_SIZE,
    epochs=1,
)

# To test
batch_index = 0
test_inputs, test_labels = test_gen.__getitem__(batch_index=batch_index)

predicts = model.predict(test_inputs)

index = 7


fig = plt.imshow(predicts[index, 0, :, :, 0])
