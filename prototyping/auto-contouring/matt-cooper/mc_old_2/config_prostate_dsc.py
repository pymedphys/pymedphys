import loss as loss
import tensorflow as tf

# DATA
DATA_PATH = "./dataset_prostate_cleaned/"
MODEL_SAVE = "./prostate_dsc/dsc"
BATCH_SIZE = 1
OUTPUT_CHANNELS = 3

# COMPILING MODEL
LOSS = loss.dsc_loss
INITIAL_LR = 1e-5
OPTIMIZER = tf.keras.optimizers.Adam(lr=INITIAL_LR)
METRICS = [loss.dice_metric, tf.keras.metrics.Precision(), tf.keras.metrics.Recall()]
INITIAL_WEIGHTS = None

# TRAINING MODEL
EPOCHS = 150
LR_SCALE = 0.5
LR_PATIENCE = 3
STOP_PATIENCE = 30
