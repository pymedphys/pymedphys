# -*- coding: utf-8 -*-
"""

Document:
This is just a bunch of hacky functions i have been using to examine the data while processing

Example:

Attributes:

Todo:
"""

import numpy as np

import matplotlib.pyplot as plt


def plot_pixel_array(pixel_array, index=None):
    """
    Quick hack to view a slice from either a 3D or 2D array
    """
    # TODO
    # Scale pixel intensity for CT
    if index is not None:
        pixel_array = pixel_array[index]
    plt.imshow(pixel_array, cmap=plt.cm.bone)
    plt.show()


def plot_model_data(images, masks, index=90, slices=9, corners=False):
    plt.figure(figsize=(15, 15))
    for i in range(slices):
        plt.subplot(3, 3, i + 1)
        # plt.imshow(images[..., i + 90], cmap="gray") # side
        # plt.imshow(images[i + 90], cmap="gray") # side
        plt.imshow(images[i + index], cmap="gray")  # side
        # plt.contour(masks[ i + 90], levels=[0.5, 1.5, 2.5, 3.5, 4.5], colors=colors)
        # plt.contour(masks[ i + 90])#, colors=colors)
        plt.contour(masks[i + index], corner_mask=corners)
    plt.axis("off")


def print_structures(structures):
    for index, con in enumerate(structures):
        num = int(con["number"])
        name = con["name"]
        color = con["color"]
        print(f"structures[{index}]: structure numer {num} - {name} - color {color}")


def print_range(images):
    try:
        print(np.iinfo(type(images[0][0][0])))
    except ValueError:
        print(np.finfo(type(images[0][0][0])))
    # print(f"min:{np.min(images)}\nmax:{np.max(images)}")


def print_dicom_slice_data(dicom_slice, index=None):
    if index is not None:
        dicom_slice = dicom_slice[index]
    try:
        print(f"AnatomicalOrientationType:{dicom_slice.AnatomicalOrientationType}")
    except AttributeError:
        print(f"AnatomicalOrientationType: None - Assume BIPED not QUADRUPED")
    print(f"PatientPosition: {dicom_slice.PatientPosition}")
    print(" ")
    print(f"ImageOrientationPatient: {dicom_slice.ImageOrientationPatient}")
    print(f"PixelSpacing [x,y] - Scaling factors: {dicom_slice.PixelSpacing}")
    print(f"PixelSpacing [z] - Scaling factors: {dicom_slice.SliceThickness}")
    print(
        f"ImagePositionPatient [x,y,z] (patient space) - Translation factors: {dicom_slice.ImagePositionPatient}"
    )
    print(" ")
    # print(f"Slice index (z pixel space): {index}")
    print(f"SliceLocation (z patient space): {dicom_slice.SliceLocation}")
    print(f"SliceThickness: {dicom_slice.SliceThickness}")
    print(" ")
    print(f"type in pixel_array: {type(dicom_slice.pixel_array[0][0])}")


def print_data_split(train_images, test_images):
    total_train_images = len(train_images)
    total_test_images = len(test_images)
    total_instances = total_train_images + total_test_images
    perc_train = total_train_images / total_instances
    perc_test = total_test_images / total_instances

    print("Total instances:", total_instances)
    print("-------------")
    print("Total training instance:", total_train_images)
    print("Total validation instances:", total_test_images)
    print("=============")
    print("Data split:")
    print("Train:", perc_train)
    print("Test:", perc_test)


# def plot_training_instance(input_instance):
#     plt.figure(figsize=(15, 15))
#     for i in range(input_instance):
#         plt.subplot(3, 3, i + 1)
#         # plt.imshow(images[..., i + 90], cmap="gray") # side
#         #plt.imshow(images[i + 90], cmap="gray") # side
#         plt.imshow(images[i + index], cmap="gray")  # side
#         #plt.contour(masks[ i + 90], levels=[0.5, 1.5, 2.5, 3.5, 4.5], colors=colors)
#         #plt.contour(masks[ i + 90])#, colors=colors)
#         plt.contour(masks[i + index])
#     plt.axis('off')
