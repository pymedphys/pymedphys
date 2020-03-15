# %load generator
import functools
from pathlib import Path
from random import randint

import numpy as np

import matplotlib.pyplot as plt

import skimage.draw
import skimage.transform

# Perhaps use tf.io instead
import pydicom

import tensorflow as tf

# TODO - Modulate get_item


class data_gen(tf.keras.utils.Sequence):
    def __init__(
        self,
        input_paths,
        context_paths,
        label_paths,
        context,
        batch_size,
        structure_names,
        resize,
    ):
        self.input_paths = input_paths
        self.context_paths = context_paths
        self.label_paths = label_paths
        self.context = context
        self.batch_size = batch_size
        self.structure_names = structure_names
        self.resize = resize

        for path in self.label_paths:
            _ = self.pre_cached_structures(path)

        self.on_epoch_end()

    @functools.lru_cache()
    def pre_cached_structures(self, path):
        return pydicom.dcmread(path, force=True)

    def get_parent_dir(self, path):
        return Path(path).parent.name

    # TODO
    # def resize_vol(volume, shape):
    #     for s in volume:
    #         skimage.transform.resize(s, shape)
    #     return volume

    # TODO
    # def normal:

    def __getitem__(self, batch_index):

        if (batch_index + 1) * self.batch_size > len(self.input_paths):
            self.batch_size = len(self.input_paths) - batch_index * self.batch_size

        batch_paths = self.input_paths[
            batch_index * self.batch_size : (batch_index + 1) * self.batch_size
        ]

        batch_inputs = []
        batch_labels = []

        for image_path in batch_paths:
            # Get parent dir
            parent_dir = self.get_parent_dir(image_path)
            # Get mask path
            mask_path = [s for s in self.label_paths if parent_dir in s][0]
            # Get index
            image_index = self.context_paths.index(image_path)
            # Get context
            input_paths = self.context_paths[
                image_index - self.context : image_index + self.context + 1
            ]

            try:
                assert len(input_paths) == 2 * self.context + 1
            except:
                continue

            ###################### IMAGE LOOP ###################################

            images = []
            for dcm_path in input_paths:
                dicom_ct = pydicom.dcmread(dcm_path, force=True)
                try:
                    dicom_ct.file_meta.TransferSyntaxUID
                except AttributeError:
                    dicom_ct.file_meta.TransferSyntaxUID = (
                        pydicom.uid.ImplicitVRLittleEndian
                    )
                image = dicom_ct.pixel_array
                image = skimage.transform.resize(image, (self.resize, self.resize))
                images = images + [image]

            batch_inputs.append(images)

            ####################### MASK LOOP ####################################

            img = pydicom.dcmread(image_path, force=True)
            img_position = img.ImagePositionPatient
            img_spacing = [x for x in img.PixelSpacing] + [img.SliceThickness]
            img_orientation = img.ImageOrientationPatient

            dicom_structures = self.pre_cached_structures(mask_path)

            assert (
                img.FrameOfReferenceUID
                == dicom_structures.StructureSetROISequence[
                    0
                ].ReferencedFrameOfReferenceUID
            )

            dcm_rs_struct_names = [
                structure.ROIName
                for structure in dicom_structures.StructureSetROISequence
            ]

            structure_names = self.structure_names

            names_to_pull = [
                name for name in dcm_rs_struct_names if name in structure_names
            ]
            try:
                assert len(names_to_pull) == len(structure_names)
            except:
                batch_inputs.pop()
                continue

            structure_indexes = [
                dcm_rs_struct_names.index(name) for name in names_to_pull
            ]

            mask = np.zeros(shape=(1, 512, 512, len(structure_indexes)))

            dx, dy, *rest = img_spacing
            Cx, Cy, *rest = img_position
            Ox, Oy = img_orientation[0], img_orientation[4]

            for mask_index, structure_index in enumerate(structure_indexes):
                z = [
                    z_slice.ContourData[2::3][0]
                    for z_slice in dicom_structures.ROIContourSequence[
                        structure_index
                    ].ContourSequence
                ]

                try:
                    indexes = z.index(img_position[2])
                except:
                    continue

                try:
                    len(indexes)
                except:
                    indexes = [indexes]

                for index in indexes:
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

                    mask[:, rr, cc, mask_index] = True

            mask = skimage.transform.resize(
                mask, (1, self.resize, self.resize, len(structure_indexes))
            )

            batch_labels.append(mask)

        ###################### RETURNS ###################################
        batch_inputs = np.array(batch_inputs)
        batch_inputs = batch_inputs[..., np.newaxis]

        # batch_input = np.array(batch_inputs)
        batch_labels = np.array(batch_labels)

        batch_inputs = np.swapaxes(batch_inputs, 1, 3)
        batch_inputs = np.swapaxes(batch_inputs, 2, 1)

        batch_labels = np.swapaxes(batch_labels, 1, 3)
        batch_labels = np.swapaxes(batch_labels, 2, 1)

        return batch_inputs, batch_labels

    def __len__(self):
        # number of batches per epoch
        return int(np.ceil(len(self.input_paths) / float(self.batch_size)))

    def on_epoch_end(self):
        """Updates indexes after each epoch
        """
        None

    def random_batch(self, batch_index=False):
        if batch_index is False:
            batch_index = randint(0, round(len(self.input_paths) / self.batch_size) - 1)

        print(
            "Batch index:",
            batch_index,
            "/",
            round(len(self.input_paths) / self.batch_size) - 1,
        )

        batch_inputs, batch_labels = self.__getitem__(batch_index=batch_index)

        print("Batch inputs shape:", batch_inputs.shape)
        print("Batch labels shape:", batch_labels.shape)

        return batch_inputs, batch_labels

    def plot_instance(self, batch_index=False, input_index=False):
        batch_inputs, batch_labels = self.random_batch(batch_index)

        if input_index is False:
            input_index = randint(0, batch_inputs.shape[0] - 1)

        print("Input index:", input_index, "/", batch_inputs.shape[0] - 1)

        fig, axes = plt.subplots(
            nrows=1, ncols=2, figsize=(10, 5), sharex=True, sharey=True
        )
        axes[0].imshow(batch_inputs[input_index, 0, :, :, 0], cmap="gray")
        axes[0].set_title("Input")
        axes[0].axis("off")
        axes[1].imshow(batch_labels[input_index, 0, :, :, 0])
        axes[1].set_title("Label")
        axes[1].axis("off")
        fig.tight_layout()
