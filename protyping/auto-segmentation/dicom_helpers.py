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


import glob

import os_helpers

import numpy as np

import pydicom


def read_dicom_paths(dicom_paths, force=False):
    return [pydicom.dcmread(dicom_path, force=force) for dicom_path in dicom_paths]


def sort_slice_location(dicom_series):
    return sorted(dicom_series, key=lambda dicom: dicom.SliceLocation)


def get_pixel_arrays(dicom_series):
    return np.array([dicom.pixel_array for dicom in dicom_series])


def filter_dicom_files(dicom_files):
    dicom_series = []
    dicom_structures = []
    dicom_plan = []
    other = []

    for file in dicom_files:
        if hasattr(file, "ImageType"):
            dicom_series.append(file)
        elif hasattr(file, "StructureSetName"):
            dicom_structures.append(file)
        elif hasattr(file, "BeamSequence"):
            dicom_plan.append(file)
        else:
            other.append(file)

    return dicom_series, dicom_structures, dicom_plan, other


def add_transfer_syntax(dicom_files):
    for dicom in dicom_files:
        try:
            dicom.file_meta.TransferSyntaxUID
        except AttributeError:
            dicom.file_meta.TransferSyntaxUID = pydicom.uid.ImplicitVRLittleEndian
            dicom.fix_meta_info(enforce_standard=True)
    return dicom_files


def write_transfer_syntax_to_path(data_path, test=False):
    save_parent = data_path + "/with_transfer_syntax"
    os_helpers.make_directory(save_parent)

    dicom_paths = glob.glob(data_path + "/*.dcm")
    dicom_files = read_dicom_paths(dicom_paths, force=True)

    for dicom in dicom_files:
        save_path = save_parent + "/" + dicom.SOPInstanceUID + ".dcm"
        print(save_path)
        if not test:
            dicom.save_as(save_path, write_like_original=False)


def print_dicom_file(dicom_file):
    print("\nFile meta")
    print(dicom_file.file_meta)
    print("\nFile main")
    for data in dicom_file:
        print(data)
