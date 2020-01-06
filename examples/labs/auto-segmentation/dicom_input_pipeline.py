# -*- coding: utf-8 -*-
# TODO Write module docstring
"""

Document:

Example:

Attributes:

Todo:
"""

from __future__ import print_function

from glob import glob

import numpy as np

import matplotlib.pyplot as plt

from skimage.transform import resize

import pydicom


def get_file_names(data_path):
    """
    Returns a sorted list of all files in data_path with ext dcm.
    """
    file_names = glob(data_path + "/*.dcm")
    file_names.sort()
    return file_names


def read_dicom_volume(file_names):
    """
    Returns a volume stack of DICOM files from names in list file_names.
    """
    return [pydicom.dcmread(name, force=True) for name in file_names]


def filter_dicom_volume(dicom_volume):
    """
    Filters a DICOM volume into 4 sections:

    dicom_imaging_volume: DICOM CT series files (CT DICOM files).

    dicom_rs: DICOM structure set file (RS DICOM file).

    dicom_rp: DICOM treatment plan file (RP DICOM file).

    dicom_rd: DICOM dose grid file (RD DICOM file).
    """
    dicom_imaging_volume = []
    dicom_rs = []
    dicom_rp = []
    dicom_rd = []
    for file in dicom_volume:
        if hasattr(file, 'ImageType'):
            dicom_imaging_volume.append(file)
        elif hasattr(file, 'StructureSetName'):
            dicom_rs.append(file)
        elif hasattr(file, 'BeamSequence'):
            dicom_rp.append(file)
        else:
            dicom_rd.append(file)
    return dicom_imaging_volume, dicom_rs, dicom_rp, dicom_rd

def clean_data_by_label():
    # TODO
    # If no label in structures for slice then pop slice
    # This might need to be done by hand as we want to slices
    # containing vac bag that has not been labelled
    return 0


def add_transfer_syntax(dicom_imaging_volume):
    """
    Fill in missing TransferSyntaxUID on DICOM files after reading
    in the volume. Required before pixel_array attribute is called.
    """
    for file in dicom_imaging_volume:
        # TODO
        # Decide which logic handles errors better below
        try:
            file.file_meta.TransferSyntaxUID
        except AttributeError:
            file.file_meta.TransferSyntaxUID = (
                pydicom.uid.ImplicitVRLittleEndian)
        # if hasattr(file, 'file_meta.TransferSyntaxUID') is not True:
        #     file.file_meta.TransferSyntaxUID = (pydicom
        #                                         .uid.ImplicitVRLittleEndian)
    return dicom_imaging_volume


def extract_pixel_array(dicom_imaging_volume):
    """
    Return pixel array volume from DICOM imaging volume.
    """
    # TODO
    # Can make this faster by defining array size
    # Probably break the return statement down for readability.
    return np.array(
        [ax_slice.pixel_array for ax_slice in dicom_imaging_volume])


def scale_pixel_array(pixel_array_volume, scale):
    """
    Resizes axial slices in the pixel_array volume to tuple (x,y) scale.
    Assumes volume shape (z, x, y) where z indexes axial slices.
    """
    # TODO
    # Holding 2 * volume in memeory - look at generators if this is an issue
    # Can make this faster by defining array size.
    # Probably break the return statement down for readability.
    # TODO
    # This should probably be done at a volume level rather
    # than looping through each slice - to speed things up.
    return np.array([(transform.resize(ax_slice, scale))
                     for ax_slice in pixel_array_volume])


def plot_pixel_array(pixel_array, index=0):
    """
    Quick hack to view a slice
    """
    # TODO
    # Scale pixel intensity for CT
    plt.imshow(pixel_array[index], cmap=plt.cm.bone)
    plt.show()


def normalise_pixel_array_volume(pixel_array_volume):
    """
    Return a normalised pixel array volume
    """
    # TODO
    # Have changed from max of slice to max of array
    # But have not put much thought into effect different
    # maximum values from different patient cases may have (yet)!
    # This should probably be /max for type
    return pixel_array_volume / np.max(pixel_array_volume)


def get_padding(pixel_array_volume, index, padding=5):
    # TODO
    # Get padding ala deep-mind: index of volume +- padding 
    # Can make this faster by defining array size
    # TODO
    # At some point in the pipeline we need to handle
    # that the outer margin slices are only to be used
    # as padding
    return  

def strip_margin(pixel_array_volume, padding=5):
    """
    Return inner pixel array volume by subtracting margins as defined by padding.
    """
    return pixel_array_volume[padding:-padding]


def get_scaled_pixel_array_volume(data_path, scale):
    """
    Return a scaled pixel array volume from a patient file data_path
    and structures if available.
    """
    file_names = get_file_names(data_path)
    dicom_volume = read_dicom_volume(file_names)
    dicom_imaging_volume, dicom_structures, *rest = filter_dicom_volume(
        dicom_volume)

    # Handling of dicom_imaging_volume
    dicom_imaging_volume = add_transfer_syntax(dicom_imaging_volume)
    pixel_array_volume = extract_pixel_array(dicom_imaging_volume)
    pixel_array_volume = normalise_pixel_array_volume(pixel_array_volume)
    scaled_pixel_array_volume = scale_pixel_array(pixel_array_volume, scale)

    # TODO
    # Handling of structures
    return scaled_pixel_array_volume, dicom_structures

def construct_input_data(data_path, scale, output_path):

    scaled_pixel_array_volume, dicom_structures = get_scaled_pixel_array_volume(data_path, scale)

    # r
    return 0


DATA_PATH = "/home/matthew/proj/masters-project/DATASET/13950"
SCALE = 64, 64
