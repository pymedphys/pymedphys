import numpy as np
import pydicom
import tensorflow as tf

import config
import dicom_helpers

from pymedphys.__experimental.autosegmentation import mask
import unet

# Assign GPU or CPU
if config.DEVICE == "GPU":
    try:
        physical_devices = tf.config.experimental.list_physical_devices("GPU")
        tf.config.experimental.set_memory_growth(physical_devices[0], True)
        assert len(physical_devices) > 0
    except AssertionError:
        print("Defaulting to CPU")
        tf.config.set_visible_devices([], "GPU")
else:
    tf.config.set_visible_devices([], "GPU")


def standardise_array(data_array, mean, standard_deviation):
    return (data_array - mean) / standard_deviation


def predict_to_contour(dicom, prediction):
    x_grid, y_grid, ct_size = mask.get_grid(dicom)
    z_position = float(dicom.SliceLocation)
    slice_contours = mask.get_contours_from_mask(x_grid, y_grid, prediction[..., 0])

    # [x1 y1 x2 y2 ... ] to [x1 y1 z x2 y2 z ...] for DICOM input
    slice_contours_xyz = []
    for roi in slice_contours:
        roi_xyz = []
        for xy_point in roi:
            xyz_point = [*xy_point, z_position]
            roi_xyz = roi_xyz + xyz_point
        slice_contours_xyz.append(roi_xyz)

    return slice_contours_xyz


def get_predictions(dicom_series):
    model = unet.Network(output_channels=config.MODEL_OUTPUT_CHANNELS)

    model.compile()

    model.load_weights(config.MODEL_WEIGHTS)

    pixel_arrays = dicom_helpers.get_pixel_arrays(dicom_series)

    # shape (x, y) to (1, x, y) for TensorFlow input
    pixel_arrays = pixel_arrays[..., np.newaxis]

    pixel_arrays = standardise_array(
        pixel_arrays, config.TRAINING_DATA_MEAN, config.TRAINING_DATA_STD
    )

    predictions = model.predict(pixel_arrays, batch_size=config.BATCH_SIZE, verbose=1)

    predictions = np.round(predictions)

    return predictions
