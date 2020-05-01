# INPUT GENERATOR
DATA_PATH = "/home/matthew/priv/PROSTATE_TEST/"
STRUCTURE_NAMES = ["patient"]

CONTEXT = 10
BATCH_SIZE = 2

# Train/Valid/Test
SPLIT_RATIO = (0.7, 0.2, 0.1)

# DATA SHAPES
INPUT_SHAPE = (2 * CONTEXT + 1, 512, 512, 1)
OUTPUT_SHAPE = (1, 512, 512, len(STRUCTURE_NAMES))
OUTPUT_CHANNELS = OUTPUT_SHAPE[-1]

# MODEL COMPILING
EPOCHS = 1
OPTIMIZER = "adam"

import tensorflow as tf

LOSS = tf.nn.sigmoid_cross_entropy_with_logits

METRICS = ["accuracy"]
