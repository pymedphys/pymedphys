# Copyright (C) 2020 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import functools
import pathlib

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom
from pymedphys._imports import tensorflow as tf

from pymedphys._data import download

from . import mask


def create_numpy_generator_dataset(
    data_path_root,
    structure_set_paths,
    ct_image_paths,
    ct_uid_to_structure_uid,
    names_map,
    ct_uids,
    structures_to_learn,
    uid_to_url,
    hash_path,
):
    def predownload_generator():
        for ct_uid in ct_uids:
            download_uid(data_path_root, ct_uid, uid_to_url, hash_path)

            structure_uid = ct_uid_to_structure_uid[ct_uid]
            download_uid(data_path_root, structure_uid, uid_to_url, hash_path)

            yield ct_uid

    pre_download_parameters = ((tf.string), (tf.TensorShape(())))
    pre_download_dataset = tf.data.Dataset.from_generator(
        predownload_generator, *pre_download_parameters
    )

    def generator():
        for ct_uid in pre_download_dataset.prefetch(30):
            ct_uid = ct_uid.numpy().decode()
            x_grid, y_grid, input_array, output_array = numpy_input_output_from_cache(
                data_path_root,
                structure_set_paths,
                ct_image_paths,
                ct_uid_to_structure_uid,
                names_map,
                ct_uid,
                structures_to_learn,
                uid_to_url,
                hash_path,
            )
            input_array = input_array[:, :, None]

            yield ct_uid, x_grid, y_grid, input_array, output_array

    parameters = (
        (tf.string, tf.float64, tf.float64, tf.int32, tf.float64),
        (
            tf.TensorShape(()),
            tf.TensorShape([512]),
            tf.TensorShape([512]),
            tf.TensorShape([512, 512, 1]),
            tf.TensorShape([512, 512, len(structures_to_learn)]),
        ),
    )

    dataset = tf.data.Dataset.from_generator(generator, *parameters)

    return dataset


def get_contours_by_ct_uid(structure_set, number_to_name_map):
    contours_by_ct_uid = {}

    for roi_contour_sequence_item in structure_set.ROIContourSequence:
        try:
            structure_name = number_to_name_map[
                roi_contour_sequence_item.ReferencedROINumber
            ]
        except KeyError:
            continue

        for contour_sequence_item in roi_contour_sequence_item.ContourSequence:
            ct_uid = contour_sequence_item.ContourImageSequence[
                0
            ].ReferencedSOPInstanceUID

            try:
                _ = contours_by_ct_uid[ct_uid]
            except KeyError:
                contours_by_ct_uid[ct_uid] = dict()

            try:
                contours_by_ct_uid[ct_uid][structure_name].append(
                    contour_sequence_item.ContourData
                )
            except KeyError:
                contours_by_ct_uid[ct_uid][structure_name] = [
                    contour_sequence_item.ContourData
                ]

    return contours_by_ct_uid


def get_filename_from_url(url):
    filename = url.split("/")[-1]

    return filename


def download_uid(data_path_root, uid, uid_to_url, hash_path):
    download_directory_name = data_path_root.name

    url = uid_to_url[uid]
    filename = get_filename_from_url(url)
    save_filepath = pathlib.Path(download_directory_name).joinpath("dicom", filename)

    download.zip_data_paths(
        save_filepath,
        check_hash=True,
        redownload_on_hash_mismatch=True,
        delete_when_no_hash_found=True,
        url=url,
        hash_filepath=hash_path,
    )


def create_input_ct_image(dcm_ct):
    x_grid, y_grid, _ = mask.get_grid(dcm_ct)

    return x_grid, y_grid, dcm_ct.pixel_array


def create_output_mask(dcm_ct, contours_by_ct_uid, structure, ct_uid):
    _, _, ct_size = mask.get_grid(dcm_ct)

    contours_on_this_slice = contours_by_ct_uid[ct_uid].keys()
    if structure in contours_on_this_slice:
        original_contours = contours_by_ct_uid[ct_uid][structure]
        _, _, calculated_mask = mask.calculate_anti_aliased_mask(
            original_contours, dcm_ct
        )
    else:
        calculated_mask = np.zeros(ct_size) - 1

    return calculated_mask


def numpy_input_output_from_cache(
    data_path_root,
    structure_set_paths,
    ct_image_paths,
    ct_uid_to_structure_uid,
    names_map,
    ct_uid,
    structures_to_learn,
    uid_to_url,
    hash_path,
):
    data_path_root = pathlib.Path(data_path_root)

    @functools.lru_cache()
    def get_dcm_ct_from_uid(ct_uid):
        ct_path = ct_image_paths[ct_uid]
        try:
            dcm_ct = pydicom.read_file(ct_path, force=True)
        except FileNotFoundError:
            download_uid(data_path_root, ct_uid, uid_to_url, hash_path)
            dcm_ct = pydicom.read_file(ct_path, force=True)

        dcm_ct.file_meta.TransferSyntaxUID = pydicom.uid.ImplicitVRLittleEndian

        return dcm_ct

    @functools.lru_cache()
    def get_dcm_structure_from_uid(structure_set_uid):
        structure_set_path = structure_set_paths[structure_set_uid]

        def load_structure():
            return pydicom.read_file(
                structure_set_path,
                force=True,
                specific_tags=["ROIContourSequence", "StructureSetROISequence"],
            )

        try:
            dcm_structure = load_structure()
        except FileNotFoundError:
            download_uid(data_path_root, structure_set_uid, uid_to_url, hash_path)
            dcm_structure = load_structure()

        return dcm_structure

    @functools.lru_cache()
    def get_contours_by_ct_uid_from_structure_uid(structure_set_uid):
        dcm_structure = get_dcm_structure_from_uid(structure_set_uid)

        number_to_name_map = {
            roi_sequence_item.ROINumber: names_map[roi_sequence_item.ROIName]
            for roi_sequence_item in dcm_structure.StructureSetROISequence
            if names_map[roi_sequence_item.ROIName] is not None
        }

        contours_by_ct_uid = get_contours_by_ct_uid(dcm_structure, number_to_name_map)

        return contours_by_ct_uid

    npz_directory = data_path_root.joinpath("npz_cache")
    npz_directory.mkdir(parents=True, exist_ok=True)

    npz_input_path = npz_directory.joinpath(f"{ct_uid}_input.npz")
    npz_output_paths = {
        structure: npz_directory.joinpath(f"{ct_uid}_output_{structure}.npz")
        for structure in structures_to_learn
    }

    try:
        input_data = np.load(npz_input_path)
    except FileNotFoundError:
        dcm_ct = get_dcm_ct_from_uid(ct_uid)
        x_grid, y_grid, input_array = create_input_ct_image(dcm_ct)

        np.savez(npz_input_path, x_grid=x_grid, y_grid=y_grid, input_array=input_array)
    else:
        x_grid = input_data["x_grid"]
        y_grid = input_data["y_grid"]
        input_array = input_data["input_array"]

    output_array = np.ones((*np.shape(input_array), len(structures_to_learn)))
    for i, structure in enumerate(structures_to_learn):
        npz_path = npz_output_paths[structure]

        try:
            output_data = np.load(npz_path)
        except FileNotFoundError:
            structure_set_uid = ct_uid_to_structure_uid[ct_uid]
            contours_by_ct_uid = get_contours_by_ct_uid_from_structure_uid(
                structure_set_uid
            )

            dcm_ct = get_dcm_ct_from_uid(ct_uid)
            calculated_mask = create_output_mask(
                dcm_ct, contours_by_ct_uid, structure, ct_uid
            )

            np.savez(npz_path, mask=calculated_mask)
        else:
            calculated_mask = output_data["mask"]

        output_array[:, :, i] = calculated_mask

    return x_grid, y_grid, input_array, output_array
