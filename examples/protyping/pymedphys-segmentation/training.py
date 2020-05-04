import glob
import random
from datetime import datetime

import numpy as np
from scipy.ndimage.filters import gaussian_filter
from scipy.ndimage.interpolation import map_coordinates

from matplotlib import pyplot as plt

import skimage.transform

# CONFIG FILE
import config_vacbag_tversky as config
import cv2
import loss as loss
import paths as paths
import tensorflow as tf
import unet as unet

physical_devices = tf.config.experimental.list_physical_devices("GPU")
assert len(physical_devices) > 0, "Not enough GPU hardware devices available"
config = tf.config.experimental.set_memory_growth(physical_devices[0], True)


# The meaning of life
random.seed(42)
np.random.seed(42)


class make_gen(tf.keras.utils.Sequence):
    def __init__(
        self,
        input_paths,
        label_paths,
        batch_size,
        training_mean,
        training_std,
        shuffle_on_end=True,
        augment=True,
    ):
        self.input_paths = input_paths
        self.label_paths = label_paths
        self.batch_size = batch_size
        self.training_mean = training_mean
        self.training_std = training_std
        self.shuffle_on_end = shuffle_on_end
        self.augment = augment

    def __len__(self):
        # number of batches per epoch
        return int(np.ceil(len(self.input_paths) / float(self.batch_size)))

    def on_epoch_end(self):
        """Updates indexes after each epoch
        """
        if self.shuffle_on_end == True:
            self.inputs, self.truths = self.suffle_together(self.inputs, self.truths)

    def shuffle_together(self, inputs, truths):
        shuffle_together = list(zip(inputs, truths))
        random.shuffle(shuffle_together)
        inputs, truths = zip(*shuffle_together)
        return inputs, truths

    def gaussian_noise(self, img, mean=0, sigma=0.003):
        img = img.copy()
        noise = np.random.normal(mean, sigma, img.shape)
        mask_overflow_upper = img + noise >= 1.0
        mask_overflow_lower = img + noise < 0
        noise[mask_overflow_upper] = 1.0
        noise[mask_overflow_lower] = 0
        img = img + noise
        return img

    def random_crop_resize(self, img, label, crop_size=500):
        size_img = img.shape
        size_label = label.shape
        crop_size = random.randint(crop_size, img.shape[0] - 1)
        crop_size = (crop_size, crop_size)

        # "Crop size should be less than image size"
        assert crop_size[0] <= img.shape[0] and crop_size[1] <= img.shape[1]

        w, h = img.shape[:2]
        x, y = np.random.randint(h - crop_size[0]), np.random.randint(w - crop_size[1])

        img = img[y : y + crop_size[0], x : x + crop_size[1], :]
        img = skimage.transform.resize(img, size_img)

        label = label[y : y + crop_size[0], x : x + crop_size[1], :]
        label = skimage.transform.resize(label, size_label)
        return img, label

    def affine_transform(self, image, label, alpha_affine=0.5, random_state=None):

        if random_state is None:
            random_state = np.random.RandomState(None)

        shape = image.shape
        shape_size = shape[:2]
        center_square = np.float32(shape_size) // 2
        square_size = min(shape_size) // 3
        pts1 = np.float32(
            [
                center_square + square_size,
                [center_square[0] + square_size, center_square[1] - square_size],
                center_square - square_size,
            ]
        )
        pts2 = pts1 + random_state.uniform(
            -alpha_affine, alpha_affine, size=pts1.shape
        ).astype(np.float32)
        M = cv2.getAffineTransform(pts1, pts2)

        image = cv2.warpAffine(
            image, M, shape_size[::-1], borderMode=cv2.BORDER_REFLECT_101
        )
        image = image[..., np.newaxis]
        label = cv2.warpAffine(
            label, M, shape_size[::-1], borderMode=cv2.BORDER_REFLECT_101
        )
        return image, label

    def elastic_transform(self, image, label, alpha, sigma, random_state=None):

        if random_state is None:
            random_state = np.random.RandomState(None)

        shape = image.shape
        shape_label = label.shape

        dx = (
            gaussian_filter(
                (random_state.rand(*shape) * 2 - 1), sigma, mode="constant", cval=0
            )
            * alpha
        )
        dy = (
            gaussian_filter(
                (random_state.rand(*shape) * 2 - 1), sigma, mode="constant", cval=0
            )
            * alpha
        )
        dz = np.zeros_like(dx)

        # image
        x, y, z = np.meshgrid(
            np.arange(shape[0]), np.arange(shape[1]), np.arange(shape[2])
        )
        indices = (
            np.reshape(y + dy, (-1, 1)),
            np.reshape(x + dx, (-1, 1)),
            np.reshape(z, (-1, 1)),
        )
        image = map_coordinates(image, indices, order=1, mode="reflect").reshape(shape)

        # label
        x, y, z = np.meshgrid(
            np.arange(shape_label[0]),
            np.arange(shape_label[1]),
            np.arange(shape_label[2]),
        )
        indices = (
            np.reshape(y + dy, (-1, 1)),
            np.reshape(x + dx, (-1, 1)),
            np.reshape(z, (-1, 1)),
        )
        label = map_coordinates(label, indices, order=1, mode="reflect").reshape(
            shape_label
        )

        return image, label

    def data_augment(self, img, mask, chance=0.5):
        # flip l/r
        if random.uniform(0, 1) < 0.5:
            img = cv2.flip(img, 1)
            mask = cv2.flip(mask, 1)
            if len(img.shape) == 2:
                img = img[..., np.newaxis]
            if len(mask.shape) == 2:
                mask = mask[..., np.newaxis]

        # random crop and resize
        if random.uniform(0, 1) < chance:
            img, mask = self.random_crop_resize(img, mask)
            if len(img.shape) == 2:
                img = img[..., np.newaxis]
            if len(mask.shape) == 2:
                label = label[..., np.newaxis]

        # random affine transformation
        if random.uniform(0, 1) < chance:
            img, mask = self.affine_transform(img, mask, alpha_affine=20)
            if len(img.shape) == 2:
                img = img[..., np.newaxis]
            if len(mask.shape) == 2:
                mask = mask[..., np.newaxis]

        if random.uniform(0, 1) < chance:
            args = random.choice(((1201, 10), (1501, 12), (991, 8)))
            img, mask = self.elastic_transform(img, mask, *args)

        # random Gaussian noise
        if random.uniform(0, 1) < chance:
            sigma = random.choice(np.arange(0.1, 0.3, 0.02))
            img = self.gaussian_noise(img, mean=0, sigma=sigma)

        return img, mask

    def normalise(self, x, mean, std):
        return (x - mean) / std

    def read_array_list(self, arr_path_list):
        return np.array([np.load(arr_path) for arr_path in arr_path_list])

    def __getitem__(self, batch_index):
        # Get batch at index: batch_index

        # Handle case when not enough inputs for a full batch
        if (batch_index + 1) * self.batch_size > len(self.input_paths):
            batch_size = len(self.input_paths) - batch_index * self.batch_size
        else:
            batch_size = self.batch_size

        # Extract input paths for one batch at index: batch_index
        batch_input_paths = self.input_paths[
            batch_index * batch_size : (batch_index + 1) * batch_size
        ]
        batch_label_paths = self.label_paths[
            batch_index * batch_size : (batch_index + 1) * batch_size
        ]

        batch_imgs = []
        batch_masks = []

        for x, y in zip(batch_input_paths, batch_label_paths):
            x = np.load(x)
            y = np.load(y)
            x = self.normalise(x, self.training_mean, self.training_std)

            if self.augment is True:
                x, y = self.data_augment(x, y, chance=0.33)

            batch_imgs.append(x)
            batch_masks.append(y)

        return (
            np.array(batch_imgs, dtype=np.float32),
            np.array(batch_masks, dtype=np.float32),
        )


def get_data_statistics(train_inputs, valid_inputs):
    data = train_inputs + valid_inputs
    arr = np.array([np.load(x) for x in data])
    mean = np.mean(arr)
    std = np.std(arr)
    del arr
    return mean, std


patient_paths = paths.get_patient_paths(config.DATA_PATH)
patient_paths.sort()

img_paths = [glob.glob(path + "/img/*") for path in patient_paths]
mask_paths = [glob.glob(path + "/mask/*") for path in patient_paths]

valid = int(len(img_paths) * 0.15 // 1)
test = int(len(img_paths) * 0.1 // 1)
train = int(len(img_paths) - valid - test)

train_inputs = paths.flatten_list(img_paths[0:train])
train_truths = paths.flatten_list(mask_paths[0:train])

train_inputs.sort()
train_truths.sort()

valid_inputs = paths.flatten_list(img_paths[train : train + valid])
valid_truths = paths.flatten_list(mask_paths[train : train + valid])

valid_inputs.sort()
valid_truths.sort()

test_inputs = paths.flatten_list(img_paths[train + valid :])
test_truths = paths.flatten_list(mask_paths[train + valid :])

test_inputs.sort()
test_truths.sort()


data_mean, data_std = get_data_statistics(train_inputs, valid_inputs)


train_gen = make_gen(
    train_inputs,
    train_truths,
    config.BATCH_SIZE,
    data_mean,
    data_std,
    shuffle_on_end=True,
    augment=True,
)


valid_gen = make_gen(
    valid_inputs,
    valid_truths,
    config.BATCH_SIZE,
    data_mean,
    data_std,
    shuffle_on_end=False,
    augment=False,
)


# test_gen = make_gen(test_inputs,
#                      test_truths,
#                      config.BATCH_SIZE,
#                      data_mean,
#                      data_std,
#                      shuffle_on_end=False,
#                      augment=False)


model = unet.model(output_channels=config.OUTPUT_CHANNELS)

model.compile(config.OPTIMIZER, config.LOSS, config.METRICS)

if config.INITIAL_WEIGHTS is not None:
    model.load_weights(config.INITIAL_WEIGHTS)


checkpoint_name = config.MODEL_SAVE + "_epoch_{epoch:02d}" + ".hdf5"

early_stopping = tf.keras.callbacks.EarlyStopping(
    patience=config.STOP_PATIENCE, verbose=1, restore_best_weights=True
)
reduce_lr = tf.keras.callbacks.ReduceLROnPlateau(
    factor=config.LR_SCALE, patience=config.LR_PATIENCE, verbose=1
)
model_checkpoint = tf.keras.callbacks.ModelCheckpoint(
    checkpoint_name, save_weights_only=True, verbose=1
)
csv_logger = tf.keras.callbacks.CSVLogger(
    config.MODEL_SAVE + "_csv_log", separator=",", append=False
)
tensor_board = tf.keras.callbacks.TensorBoard(
    log_dir=config.MODEL_SAVE + "_log_dir",
    histogram_freq=5,
    write_graph=True,
    write_images=True,
    embeddings_freq=5,
    update_freq="epoch",
)

callbacks = [early_stopping, model_checkpoint, reduce_lr, csv_logger, tensor_board]


steps_per_epoch = train_gen.__len__()
valid_steps = valid_gen.__len__()

train_history = model.fit(
    train_gen,
    epochs=config.EPOCHS,
    steps_per_epoch=steps_per_epoch,
    validation_steps=valid_steps,
    validation_data=valid_gen,
    callbacks=callbacks,
    verbose=1,
)
