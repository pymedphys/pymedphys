import random
from pathlib import Path

import numpy as np
from scipy.ndimage.filters import gaussian_filter
from scipy.ndimage.interpolation import map_coordinates

import skimage.draw
import skimage.transform

import pydicom

import cv2
import tensorflow as tf


class make_gen(tf.keras.utils.Sequence):
    def __init__(
        self,
        input_paths,
        label_paths,
        batch_size,
        grid_size,
        structure_names,
        train_mean,
        train_std,
        shuffle_on_end=True,
        augment=True,
    ):
        self.input_paths = input_paths
        self.label_paths = label_paths
        self.batch_size = batch_size
        self.batch_size_recall = batch_size
        self.structure_names = structure_names
        self.train_mean = train_mean
        self.train_std = train_std
        self.grid_size = grid_size
        self.shuffle_on_end = shuffle_on_end
        self.augment = augment
        random.shuffle(self.input_paths)

    def __len__(self):
        # number of batches per epoch
        return int(np.ceil(len(self.input_paths) / float(self.batch_size)))

    def on_epoch_end(self):
        """Updates indexes after each epoch
        """
        if self.shuffle_on_end == True:
            random.shuffle(self.input_paths)

        self.batch_size = self.batch_size_recall

    def standardise(self, data):
        return (data - self.train_mean) / self.train_std

    def gaussian_noise(self, img, mean=0, sigma=0.001):
        img = img.copy()
        noise = np.random.normal(mean, sigma, img.shape)
        mask_overflow_upper = img + noise >= 1.0
        mask_overflow_lower = img + noise < 0
        noise[mask_overflow_upper] = 1.0
        noise[mask_overflow_lower] = 0
        img = np.add(img, noise, out=img, casting="unsafe")
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

    def data_augment(self, img, label):

        chance = 2.0
        # flip l/r
        if random.uniform(0, 1) < chance:
            img = cv2.flip(img, 1)
            label = cv2.flip(label, 1)
            img = img[..., np.newaxis]
            if len(label.shape) == 2:
                label = label[..., np.newaxis]

        # random crop and resize
        if random.uniform(0, 1) < chance:
            img, label = self.random_crop_resize(img, label)
            if len(label.shape) == 2:
                label = label[..., np.newaxis]

        # random elastic deformation
        # if random.uniform(0,1) < chance:
        #     img, label = self.elastic_transform(img, label, alpha=2, sigma=0.5)
        #     if len(label.shape) == 2:
        #         label = label[...,np.newaxis]

        # random affine transformation
        if random.uniform(0, 1) < chance:
            img, label = self.affine_transform(img, label, alpha_affine=20)
            if len(label.shape) == 2:
                label = label[..., np.newaxis]

        # random gaussian noise
        if random.uniform(0, 1) < chance:
            img = self.gaussian_noise(img)

        return img, label

    def get_parent_dir(self, path):
        return str(Path(path).parent.name)

    def get_image_instance(self, dcm):
        try:
            dcm.file_meta.TransferSyntaxUID
        except AttributeError:
            dcm.file_meta.TransferSyntaxUID = pydicom.uid.ImplicitVRLittleEndian
        return dcm.pixel_array

    def get_label_instance(
        self,
        dicom_structures,
        structure_indexes,
        img_position,
        img_spacing,
        img_orientation,
    ):
        mask = np.zeros(
            shape=(self.grid_size, self.grid_size, len(structure_indexes)),
            dtype=np.float32,
        )
        dx, dy, *rest = img_spacing
        Cx, Cy, *rest = img_position
        Ox, Oy = img_orientation[0], img_orientation[4]

        # Mask loop
        for mask_index, structure_index in enumerate(structure_indexes):
            # all z positions from contour defined by structure_index
            contours = [
                contour.ContourData[2::3][0]
                for contour in dicom_structures.ROIContourSequence[
                    structure_index
                ].ContourSequence
            ]
            try:
                # get indices from contours that
                indices = [i for i, z in enumerate(contours) if z == img_position[2]]
            except:
                continue
            try:
                # is it a list
                len(indices)
            except:
                # make a list to iterate
                indices = [indices]

            for index in indices:
                xyz = (
                    dicom_structures.ROIContourSequence[structure_index]
                    .ContourSequence[index]
                    .ContourData
                )
                x = np.array(xyz[0::3])
                y = np.array(xyz[1::3])
                r = (y - Cy) / dy * Oy
                c = (x - Cx) / dx * Ox
                rr, cc = skimage.draw.polygon(r, c)
                mask[rr, cc, mask_index] = 1.0

        return mask

    def __getitem__(self, batch_index):
        # Get batch at index: batch_index

        # Handle case when not enough inputs for a full batch
        # NOTE this changes the values for the generator
        # Need to initialise again if triggered
        if (batch_index + 1) * self.batch_size > len(self.input_paths):
            self.batch_size = len(self.input_paths) - batch_index * self.batch_size

        # Extract input paths for one batch at index: batch_index
        batch_paths = self.input_paths[
            batch_index * self.batch_size : (batch_index + 1) * self.batch_size
        ]

        # Empy lists to store inputs and labels
        # Convert to array after
        batch_inputs = []
        batch_labels = []

        for img_path in batch_paths:

            # Get the image file
            dcm = pydicom.dcmread(img_path, force=True)
            # z position of central slice
            img_position = dcm.ImagePositionPatient
            # [x, y, z] spacing
            img_spacing = [float(x) for x in dcm.PixelSpacing] + [
                float(dcm.SliceThickness)
            ]
            # orientation of patient
            img_orientation = dcm.ImageOrientationPatient

            # Image Loop
            img = self.get_image_instance(dcm)
            # standardise
            img = self.standardise(img)
            # convert to (x, y, 1)
            img = img[..., np.newaxis]
            # check conversion
            assert len(img.shape) == 3

            # Get the structure file
            parent_dir = self.get_parent_dir(img_path)
            label_path = [s for s in self.label_paths if parent_dir in s][0]
            dcm_strs = pydicom.dcmread(label_path, force=True)

            # Get structure names from structure file
            dcm_rs_struct_names = [
                structure.ROIName for structure in dcm_strs.StructureSetROISequence
            ]
            names_to_pull = [
                name for name in dcm_rs_struct_names if name in self.structure_names
            ]

            try:
                # Check structure file has all names defined otherwise we have missing labels
                assert len(names_to_pull) == len(self.structure_names)

                structure_indexes = [
                    dcm_rs_struct_names.index(name) for name in names_to_pull
                ]
                label = self.get_label_instance(
                    dcm_strs,
                    structure_indexes,
                    img_position,
                    img_spacing,
                    img_orientation,
                )

                if self.augment:
                    img, label = self.data_augment(img, label)
                batch_inputs.append(img)
                batch_labels.append(label)

            except:
                # continue without appending above case to batch
                continue

        ###################### BATCH AUGMENTING ######################
        batch_inputs = np.array(
            batch_inputs, dtype=np.float32
        )  # list to np array (b,  x, y)

        # batch_inputs = batch_inputs[..., np.newaxis] # add channel (b,  x, y, ch=1)
        batch_inputs = skimage.transform.resize(
            batch_inputs, (self.batch_size, self.grid_size, self.grid_size, 1)
        )

        batch_labels = np.array(
            batch_labels, dtype=np.float32
        )  # list to np array (b, x, y, ch=#labels)
        batch_labels = skimage.transform.resize(
            batch_labels,
            (
                self.batch_size,
                self.grid_size,
                self.grid_size,
                len(self.structure_names),
            ),
        )
        batch_labels = np.round(
            batch_labels
        )  # round to binary mask after converting to float32

        return batch_inputs, batch_labels
