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


import json
import logging
import pathlib
import random

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom
from pymedphys._imports import tensorflow as tf

from . import filtering, indexing, mask


def create_datasets(data_path_root, names_map, structures_to_learn, filters):

    data_path_root = pathlib.Path(data_path_root)
    dicom_directory = data_path_root.joinpath("dicom")

    structure_value_error = ValueError(
        "Expected DICOM files to be organised into directories "
        "testing, training and validation under data_path_root/dicom."
    )

    if not dicom_directory.exists():
        raise structure_value_error

    (
        ct_image_paths,
        structure_set_paths,
        ct_uid_to_structure_uid,
        structure_uid_to_ct_uids,
    ) = indexing.get_uid_cache(data_path_root)

    uid_to_dataset_type = {}
    for structure_uid, ct_uids in structure_uid_to_ct_uids.items():
        structure_set_path = pathlib.Path(structure_set_paths[structure_uid])
        structure_set_type = structure_set_path.relative_to(dicom_directory).parts[0]

        uid_to_dataset_type[structure_uid] = structure_set_type

        if not structure_set_type in ["testing", "training", "validation"]:
            raise structure_value_error

        for ct_uid in ct_uids:
            ct_path = pathlib.Path(ct_image_paths[ct_uid])
            ct_type = structure_set_path.relative_to(dicom_directory).parts[0]

            if ct_type != structure_set_type:
                raise ValueError(
                    f"{str(ct_path)} uses the structure set at "
                    f"{str(structure_set_path)}, yet their top level directory "
                    "within data_path_root/dicom does not have the same "
                    "value of 'testing', 'training', or 'validation'."
                )

            uid_to_dataset_type[ct_uid] = ct_type

    verification = filtering.verify_all_names_have_mapping(
        data_path_root, structure_set_paths, names_map
    )
    false_mapping = verification["Names mapped that don't exist in DICOM files"]
    to_be_mapped = verification[
        "Names within DICOM files that have not been mapped yet"
    ]

    if false_mapping != set([]):
        raise ValueError(
            "Name mapping has structures within it that don't exist within "
            f"your dataset. {false_mapping}"
        )

    if to_be_mapped != set([]):
        raise ValueError(
            "Name mapping is not complete. The following structures have not yet "
            f"been mapped: {to_be_mapped}"
        )

    (
        structure_names_by_ct_uid,
        structure_names_by_structure_set_uid,
    ) = indexing.get_cached_structure_names_by_uids(
        data_path_root, structure_set_paths, names_map
    )

    filtered_ct_uids = filtering.filter_ct_uids(
        structure_uid_to_ct_uids,
        structure_names_by_structure_set_uid,
        structure_names_by_ct_uid,
        **filters,
    )

    filtered_uids_by_type = {"training": [], "validation": [], "testing": []}
    for uid in filtered_ct_uids:
        uid_dataset_type = uid_to_dataset_type[uid]
        filtered_uids_by_type[uid_dataset_type].append(uid)

    datasets = {}
    for dataset_type in ["training", "validation", "testing"]:
        uids = filtered_uids_by_type[dataset_type]
        random.shuffle(uids)

        datasets[dataset_type] = create_numpy_generator_dataset(
            data_path_root,
            structure_set_paths,
            ct_image_paths,
            ct_uid_to_structure_uid,
            names_map,
            uids,
            structures_to_learn,
        )

    return datasets


def create_numpy_generator_dataset(
    data_path_root,
    structure_set_paths,
    ct_image_paths,
    ct_uid_to_structure_uid,
    names_map,
    ct_uids,
    structures_to_learn,
):
    def generator():
        for ct_uid in ct_uids:
            x_grid, y_grid, input_array, output_array = numpy_input_output_from_cache(
                data_path_root,
                structure_set_paths,
                ct_image_paths,
                ct_uid_to_structure_uid,
                names_map,
                ct_uid,
                structures_to_learn,
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


def create_numpy_input_output(
    structure_set_paths,
    ct_image_paths,
    ct_uid_to_structure_uid,
    names_map,
    structures_to_learn,
    ct_uid,
):
    structure_uid = ct_uid_to_structure_uid[ct_uid]

    structure_set_path = structure_set_paths[structure_uid]

    structure_set = pydicom.read_file(
        structure_set_path,
        force=True,
        specific_tags=["ROIContourSequence", "StructureSetROISequence"],
    )

    number_to_name_map = {
        roi_sequence_item.ROINumber: names_map[roi_sequence_item.ROIName]
        for roi_sequence_item in structure_set.StructureSetROISequence
        if names_map[roi_sequence_item.ROIName] is not None
    }

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

    ct_path = ct_image_paths[ct_uid]
    dcm_ct = pydicom.read_file(ct_path, force=True)
    dcm_ct.file_meta.TransferSyntaxUID = pydicom.uid.ImplicitVRLittleEndian

    contours_on_this_slice = contours_by_ct_uid[ct_uid].keys()

    x_grid, y_grid, ct_size = mask.get_grid(dcm_ct)
    masks = np.nan * np.ones((*ct_size, len(structures_to_learn)))

    for i, structure in enumerate(structures_to_learn):
        if not structure in contours_on_this_slice:
            masks[:, :, i] = np.zeros(ct_size) - 1

            continue

        original_contours = contours_by_ct_uid[ct_uid][structure]
        _, _, masks[:, :, i] = mask.calculate_anti_aliased_mask(
            original_contours, dcm_ct
        )

    assert np.sum(np.isnan(masks)) == 0

    return x_grid, y_grid, dcm_ct.pixel_array, masks


def numpy_input_output_from_cache(
    data_path_root,
    structure_set_paths,
    ct_image_paths,
    ct_uid_to_structure_uid,
    names_map,
    ct_uid,
    structures_to_learn,
):
    data_path_root = pathlib.Path(data_path_root)
    npz_directory = data_path_root.joinpath("npz_cache")
    npz_directory.mkdir(parents=True, exist_ok=True)

    npz_path = npz_directory.joinpath(f"{ct_uid}.npz")
    structures_to_learn_cache_path = npz_directory.joinpath("structures_to_learn.json")

    try:
        with open(structures_to_learn_cache_path) as f:
            structures_to_learn_cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        structures_to_learn_cache = []

    if structures_to_learn_cache != structures_to_learn:
        logging.warning("Structures to learn has changed. Dumping npz cache.")
        for path in npz_directory.glob("*.npz"):
            path.unlink()
        with open(structures_to_learn_cache_path, "w") as f:
            json.dump(structures_to_learn, f)

    try:
        data = np.load(npz_path)
        x_grid = data["x_grid"]
        y_grid = data["y_grid"]
        input_array = data["input_array"]
        output_array = data["output_array"]
    except FileNotFoundError:
        x_grid, y_grid, input_array, output_array = create_numpy_input_output(
            structure_set_paths,
            ct_image_paths,
            ct_uid_to_structure_uid,
            names_map,
            structures_to_learn,
            ct_uid,
        )
        np.savez(
            npz_path,
            x_grid=x_grid,
            y_grid=y_grid,
            input_array=input_array,
            output_array=output_array,
        )

    return x_grid, y_grid, input_array, output_array
