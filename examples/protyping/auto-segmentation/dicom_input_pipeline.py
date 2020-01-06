from __future__ import print_function

from glob import glob

import numpy as np

import matplotlib.pyplot as plt

from skimage.transform import resize

import pydicom


def get_file_names(data_path):
    """
    Returns a sorted list of all files in data_path with ext .dcm
    """
    file_names = glob(data_path + "/*.dcm")
    file_names.sort()
    return file_names


def read_volume(file_names):
    """
    Returns a dicom volume from slices in file_names
    """
    return [pydicom.dcmread(file, force=True) for file in file_names]


def add_transfer_syntax(dicom_volume):
    """
    Set the TransferSyntaxUID after reading the file before
    pixel_array attribute is called
    """
    for file in dicom_volume:
        try:
            file.file_meta.TransferSyntaxUID
        except AttributeError:
            file.file_meta.TransferSyntaxUID = pydicom.uid.ImplicitVRLittleEndian
    return dicom_volume


def extract_pixel_array(dicom_volume):
    """
    Pull pixel_array imaging data from dicom volume
    """
    return np.array([ax_slice.pixel_array for ax_slice in dicom_volume])


def scale_volume(volume, scale):
    """
    Get a list of sets of virtual ancestors for the given types
    """
    # TODO
    # we are holding 2*volume in memeory - maybe look at generators
    return np.array([(resize(image, scale)) for image in volume])


def plot_slice(pixel_array, index):
    """
    Quick hack to view a slice
    """
    # TODO Scale pixel values for CT
    plt.imshow(pixel_array[index], cmap=plt.cm.bone)
    plt.show()


def normalise_pixel_array(pixel_array):
    """
    Return a normalise pixel array
    """
    # TODO
    return pixel_array / np.max(pixel_array)
