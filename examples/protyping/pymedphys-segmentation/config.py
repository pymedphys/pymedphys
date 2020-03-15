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
