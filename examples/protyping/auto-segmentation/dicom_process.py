# -*- coding: utf-8 -*-
"""

Document:
This script aims to take dicom files and prepare them for:
a) Training / Test data for the model (includes label processing)
b) Prediction input for the model (model returns the labels)

Example:

Attributes:

Todo:
"""

from __future__ import print_function

from glob import glob

import numpy as np

import pydicom

import skimage.transform

import skimage.draw


def list_files(data_path, ext=None):
    """Returns a sorted list of all files names in data_path with (optional) ext.

    Parameters
    ----------
    data_path : str
        Path to list files
    ext : str
        Option to list only files with extension .ext

    Returns
    -------
    file_names : list
        Sorted list of file names
    """

    if ext is None:
        file_names = glob(data_path + "/*")
    else:
        file_names = glob(data_path + "/*" + ext)
    file_names.sort()
    return file_names


def read_dicom_files(file_names):
    """
    Returns a list of DICOM files read in from each file_name
    in list file_names.
    """
    return [pydicom.dcmread(file_name, force=True) for file_name in file_names]


def filter_dicom_files(dicom_files):
    """
    Filters a list of DICOM files into 4 lists depending on file attributes:

    dicom_series: DICOM imaging series (CT DICOM files).

    dicom_structures: DICOM structure set file (RS DICOM file).

    dicom_plan: DICOM treatment plan file (RP DICOM file).

    dicom_dose: DICOM dose grid file (RD DICOM file).
    """
    dicom_series = []
    dicom_structures = []
    dicom_plan = []
    dicom_dose = []

    for file in dicom_files:
        if hasattr(file, 'ImageType'):
            dicom_series.append(file)
        elif hasattr(file, 'StructureSetName'):
            dicom_structures.append(file)
        elif hasattr(file, 'BeamSequence'):
            dicom_plan.append(file)
        else:
            # TODO Add condition - will it always be DICOM dose file?
            dicom_dose.append(file)
    return dicom_series, dicom_structures, dicom_plan, dicom_dose


def add_transfer_syntax(dicom_series):
    """
    Fill in missing TransferSyntaxUID on DICOM files after reading
    in the DICOM series. Required before pixel_array attribute is called.
    """
    for dicom in dicom_series:
        try:
            dicom.file_meta.TransferSyntaxUID
        except AttributeError:
            dicom.file_meta.TransferSyntaxUID = (
                pydicom.uid.ImplicitVRLittleEndian)
    return dicom_series


def get_pixel_array(dicom_series):
    """
    Return pixel array volume from DICOM imaging series.
    """
    return np.array([dicom.pixel_array for dicom in dicom_series])


def read_structures(dicom_structures):
    structures = []
    """Returns a sorted list of all files names in data_path with (optional) ext.

    Parameters
    ----------
    dicom_structures : RS DICOM file

    Returns
    -------
    structures : list
        List containing a dict for each structure type found in dicom_structure
        Each dict has keys: 'number', 'name', 'contour_points', 'color'

    Note
    -------
    contour_points need to be transformed to pixel space for model
    """
    # loop through each structure type
    for structure_index in range(len(dicom_structures.ROIContourSequence)):

        structure_dict = {}
        structure_dict['number'] = dicom_structures.ROIContourSequence[
            structure_index].ReferencedROINumber
        # Double check number is correct
        assert structure_dict[
            'number'] == dicom_structures.StructureSetROISequence[
                structure_index].ROINumber
        structure_dict['name'] = dicom_structures.StructureSetROISequence[
            structure_index].ROIName
        structure_dict['contour_points'] = [
            z_slice.ContourData for z_slice in dicom_structures.
            ROIContourSequence[structure_index].ContourSequence
        ]
        structure_dict['color'] = dicom_structures.ROIContourSequence[
            structure_index].ROIDisplayColor

        structures.append(structure_dict)
    return structures


def transform_to_array(x, y, dicom_series):
    """
    Transform from patient space to pixel space
    """
    translation = dicom_series[0].ImagePositionPatient
    scale = dicom_series[0].PixelSpacing
    orientation = dicom_series[0].ImageOrientationPatient
    x = np.array(x)
    y = np.array(y)

    # NOTE Only handles +-1 cosines
    # A more robust method that handles intermediate angels
    # was attempted however the affine matrix was singular
    # See: http://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_C.7.6.2.htmlx1
    # See: https://dicomiseasy.blogspot.com/2013/06/getting-oriented-using-image-plane.html
    r = (y - translation[1]) / scale[1] * orientation[4]
    c = (x - translation[0]) / scale[0] * orientation[0]

    return r, c


def get_binary_masks(structures, dicom_series, images):
    # Should z location for each slice in patient space
    z_slice_locations = [(dicom.ImagePositionPatient[2])
                         for dicom in dicom_series]
    # an array full of zeros the same shape as images
    labels = np.zeros_like(images, dtype=np.int16)

    # NOTE: This function only works for a single label volume output
    # See line for structure in structures[0:1] to choose
    for structure in structures[0:1]:
        for z_slice_contour_data in structure['contour_points']:

            # arrance into list([x1,y1,z1], [x2, y2, z2]...)
            xyz_points = np.array(z_slice_contour_data).reshape((-1, 3))

            z_points = xyz_points[0, 2]
            z_index = z_slice_locations.index(z_points)

            x_points_on_z_slice = xyz_points[:, 0]
            y_points_on_z_slice = xyz_points[:, 1]

            r, c = transform_to_array(x_points_on_z_slice, y_points_on_z_slice, dicom_series)
            rr, cc = skimage.draw.polygon(r, c)

            labels[z_index, rr, cc] = True
    return labels





def normalise_pixel_array_volume(pixel_array_volume):
    """
    Return a normalised pixel array volume - and convert to float
    """
    try:
        type_max = np.iinfo(type(pixel_array_volume[0][0][0])).max
    except ValueError:
        type_max = np.finfo(type(pixel_array_volume[0][0][0])).max
    return pixel_array_volume / type_max


def resize_pixel_array(pixel_array, size):
    """
    Resizes axial slices in the pixel_array volume to size (x, y) tuple.
    Assumes volume size (z, x, y) where z indexes axial slices.
    """
    if len(pixel_array.shape) > 2:
        size = len(pixel_array), *size
    return skimage.transform.resize(pixel_array, size)



def get_context(pixel_array_volume, index, context=10):
    """
    # TODO write docstring
    """
    return pixel_array_volume[index - context:index + context + 1]

def clean_structures(structures, structure_names):
    clean_structures = []
    for structure in structures:
        if structure['name'] in structure_names:
            clean_structures.append(structure)
    return clean_structures


def get_input_data(folder, size, context=10):
    """
    # TODO write docstring
    """

    # Get list of DICOM files in directory
    file_names = list_files(folder, ".dcm")
    # Read in DICOM files in file_names
    dicom_files = read_dicom_files(file_names)
    # Filter DICOM files
    dicom_series, dicom_structures, *rest = filter_dicom_files(dicom_files)
    # Add necessary attribute to recover pixel data
    dicom_series = add_transfer_syntax(dicom_series)
    # Sort images in imaging series by image position in axial direction
    dicom_series.sort(key=lambda x: float(x.ImagePositionPatient[2]))
    # Extract pixel data from imaging series
    images = get_pixel_array(dicom_series)
    # Extract structure data for imaging series
    structures = read_structures(dicom_structures[0])
    # Convert structure (x,y,z) tuple to binary mask
    labels = get_binary_masks(structures, dicom_series, images)
    # Get label colors
    colors = np.array(
        [np.array(structure['color']) for structure in structures])
    # Resize data
    images = resize_pixel_array(images, size)
    labels = resize_pixel_array(labels, size)

    # Normalise data
    images = normalise_pixel_array_volume(images)
    labels = normalise_pixel_array_volume(labels)
    return images, labels, colors, structures








# def transform_to_array(x, y, dicom_series):
#     """
#     # TODO write docstring
#     """
#     translation = dicom_series[0].ImagePositionPatient
#     scale = dicom_series[0].PixelSpacing
#     x = np.array(x)
#     y = np.array(y)
#
#     r = (y - translation[1]) / scale[1]
#     c = (x - translation[0]) / scale[0]
#     return -r, c



# def get_binary_masks(structures, dicom_series, images, structure_names):
#     """
#     # TODO write docstring
#     """
#     z = [np.around(dicom.ImagePositionPatient[2], 1) for dicom in dicom_series]
#     labels = np.zeros_like(images, dtype=np.int16)
#     for structure in structures:
#
#         for z_slice_contour_data in structure['contour_points']:
#             nodes = np.array(z_slice_contour_data).reshape((-1, 3))
#             assert np.amax(np.abs(np.diff(nodes[:, 2]))) == 0
#             try:
#                 z_index = z.index(nodes[0, 2])
#             except ValueError:
#                 pass
#             x = nodes[:, 0]
#             y = nodes[:, 1]
#             r, c = transform_to_array(x, y, dicom_series)
#             rr, cc = skimage.draw.polygon(r, c)
#             try:
#                 labels[z_index, rr, cc] = True
#             except IndexError:
#                 pass
#                 # print(
#                 #     f"IndexError: structure {structure['name']} at {z_index}")
#     colors = [np.array(structure['color']) for structure in structures]
#     return labels, colors


# def shape_model_data(pixel_array_volume, size):
#     """
#     # TODO write docstring
#     """
#     images = resize_pixel_array(images, size)
#     images = normalise_pixel_array_volume(images)
#     if labels is not None:
#         # labels = resize_pixel_array(labels, size, is_mask=True)
#         labels = resize_pixel_array(labels, size)
#         labels = normalise_pixel_array_volume(labels)
#         labels = np.round(labels)
#     return images, labels



# def get_binary_masks(structures, dicom_series, images, flip_r):
#     # Should z location for each slice in patient space
#     z_slice_locations = [(dicom.ImagePositionPatient[2])
#                          for dicom in dicom_series]
#     # an array full of zeros the same shape as images
#     labels = np.zeros_like(images, dtype=np.int16)

#     # NOTE: This function only works for a single label volume output
#     # See line for structure in structures[0:1] to choose
#     for structure in structures[0:1]:
#         for z_slice_contour_data in structure['contour_points']:

#             # arrance into list([x1,y1,z1], [x2, y2, z2]...)
#             xyz_points = np.array(z_slice_contour_data).reshape((-1, 3))

#             z_points = xyz_points[0, 2]
#             z_index = z_slice_locations.index(z_points)

#             x_points_on_z_slice = xyz_points[:, 0]
#             y_points_on_z_slice = xyz_points[:, 1]

#             r, c = transform_to_array(x_points_on_z_slice, y_points_on_z_slice,
#                                       dicom_series, flip_r)
#             rr, cc = skimage.draw.polygon(r, c)

#             labels[z_index, rr, cc] = True
#     return labels


# def affine_matrix(dicom_series):
#     # See: http://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_C.7.6.2.htmlx1
#     # i = Column index to the image plane. The first column is index zero
#     # j = Row index to the image plane. The first row index is zero.
#     # Pxyz = The coordinates of the voxel (i,j) in the frame's image plane in units of mm.
#
#     # Also, this is a great reference
#     # https://dicomiseasy.blogspot.com/2013/06/getting-oriented-using-image-plane.html
#
#     # The three values of Image Position (Patient) (0020,0032).
#     # Sxyz It is the location in mm from the origin of the RCS
#     Sxyz = dicom_series[20].ImagePositionPatient
#     # Xxyz: The values from the row (X) direction cosine of Image Orientation (Patient) (0020,0037)
#     Xxyz = dicom_series[20].ImageOrientationPatient[0:3]
#     # Yxyz The values from the column (Y) direction cosine of Image Orientation (Patient) (0020,0037)
#     Yxyz = dicom_series[20].ImageOrientationPatient[3:]
#     # Column pixel resolution of Pixel Spacing (0028,0030) in units of mm
#     Delta_i = np.array(dicom_series[20].ImagePositionPatient[0])
#     # Row pixel resolution of Pixel Spacing (0028,0030) in units of mm
#     Delta_j = np.array(dicom_series[20].ImagePositionPatient[1])

#     return np.array([np.append(Xxyz, 0)*Delta_i, np.append(Yxyz, 0)*Delta_j, np.zeros(4), np.append(Sxyz, 0)]).T
