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
import dicom_helpers
import tensorflow as tf
import unet

import numpy as np

from pymedphys._experimental.autosegmentation import mask

# Assign GPU or CPU based on config.DEVICE
if config.DEVICE == "GPU":
    try:
        physical_devices = tf.config.experimental.list_physical_devices("GPU")
        tf.config.experimental.set_memory_growth(physical_devices[0], True)
        assert len(physical_devices) > 0
    except AssertionError:
        # Default to CPU
        tf.config.set_visible_devices([], "GPU")
else:
    tf.config.set_visible_devices([], "GPU")


def standardise_array(data_array, mean, standard_deviation):
    return (data_array - mean) / standard_deviation


def predict_to_contour(dicom, prediction):
    # TODO This can be written better
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

    # shape (n, x, y) to (n, x, y, 1) for TensorFlow input
    pixel_arrays = pixel_arrays[..., np.newaxis]

    pixel_arrays = standardise_array(
        pixel_arrays, config.TRAINING_DATA_MEAN, config.TRAINING_DATA_STD
    )

    predictions = model.predict(pixel_arrays, batch_size=config.BATCH_SIZE, verbose=0)

    predictions = np.round(predictions)

    return predictions
