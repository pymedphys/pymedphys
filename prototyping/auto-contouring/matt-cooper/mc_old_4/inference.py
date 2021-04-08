import glob

import numpy as np

import pydicom

import config
import tensorflow as tf
import unet
from pymedphys._experimental.autosegmentation import mask

physical_devices = tf.config.experimental.list_physical_devices("GPU")
assert len(physical_devices) > 0, "Not enough GPU hardware devices available"
config = tf.config.experimental.set_memory_growth(physical_devices[0], True)


def get_pixel_array(dcm):
    try:
        dcm.file_meta.TransferSyntaxUID
    except AttributeError:
        dcm.file_meta.TransferSyntaxUID = pydicom.uid.ImplicitVRLittleEndian
    return dcm.pixel_array


dcm_paths = glob.glob(config.DATA_PATH + "/*")

dcms = [pydicom.dcmread(path, force=True) for path in dcm_paths]

dcms = sorted(dcms, key=lambda dcm: dcm.SliceLocation)

imgs = np.array([get_pixel_array(dcm) for dcm in dcms])

imgs = imgs[..., np.newaxis]

imgs = (imgs - config.DATA_MEAN) / config.DATA_STD

model = unet.model(output_channels=config.OUTPUT_CHANNELS)

model.compile()

model.load_weights(config.WEIGHTS)

predicts = model.predict(x=imgs, batch_size=1, verbose=1)

predicts = np.round(predicts)
