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
import pathlib

from pymedphys._imports import pydicom


def filter_ct_uids(
    structure_uids,
    structure_uid_to_ct_uids,
    structure_names_by_structure_set_uid,
    structure_names_by_ct_uid,
    study_set_must_have_all_of,
    slice_at_least_one_of,
    slice_must_have,
    slice_cannot_have,
):

    if structure_uids is None:
        structure_uids = structure_uid_to_ct_uids.keys()

    filtered_ct_uids = []

    for structure_uid in structure_uids:
        ct_uids = structure_uid_to_ct_uids[structure_uid]

        structure_names_in_study_set = set(
            structure_names_by_structure_set_uid[structure_uid]
        )

        if not structure_names_in_study_set.issuperset(study_set_must_have_all_of):
            continue

        for ct_uid in ct_uids:
            try:
                structure_names_on_slice = set(structure_names_by_ct_uid[ct_uid])
            except KeyError:
                structure_names_on_slice = set([])

            if slice_at_least_one_of is not None:
                if (
                    len(structure_names_on_slice.intersection(slice_at_least_one_of))
                    == 0
                ):
                    continue

            if not structure_names_on_slice.issuperset(slice_must_have):
                continue

            if len(structure_names_on_slice.intersection(slice_cannot_have)) != 0:
                continue

            filtered_ct_uids.append(ct_uid)

    return filtered_ct_uids


def load_names_mapping(path):
    with open(path) as f:
        name_mappings_config = json.load(f)
        names_map = name_mappings_config["names_map"]
        ignore_list = name_mappings_config["ignore_list"]

        for key in ignore_list:
            names_map[key] = None

    return names_map


def verify_all_names_have_mapping(data_path_root, structure_set_paths, names_map):
    data_path_root = pathlib.Path(data_path_root)
    raw_structure_names_cache_path = data_path_root.joinpath(
        "raw-structure-names-cache.json"
    )

    relative_structure_set_paths = {
        key: str(pathlib.Path(path).relative_to(data_path_root))
        for key, path in structure_set_paths.items()
    }

    try:
        with open(raw_structure_names_cache_path) as f:
            raw_structure_names_cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        raw_structure_names_cache = {
            "names_in_dicom_files": [],
            "structure_set_paths_when_run": {},
        }

    cache_valid = (
        raw_structure_names_cache["structure_set_paths_when_run"]
        == relative_structure_set_paths
    )

    if not cache_valid:
        names_in_dicom_files = set()

        for _, path in structure_set_paths.items():
            dcm = pydicom.read_file(
                path, force=True, specific_tags=["StructureSetROISequence"]
            )
            for item in dcm.StructureSetROISequence:
                names_in_dicom_files.add(item.ROIName)

        raw_structure_names_cache = {
            "names_in_dicom_files": list(names_in_dicom_files),
            "structure_set_paths_when_run": relative_structure_set_paths,
        }

        with open(raw_structure_names_cache_path, "w") as f:
            json.dump(raw_structure_names_cache, f)

    names_in_dicom_files = set(raw_structure_names_cache["names_in_dicom_files"])
    mapped_names = set(names_map.keys())

    false_mapping = mapped_names.difference(names_in_dicom_files)
    to_be_mapped = names_in_dicom_files.difference(mapped_names)

    result = {
        "Names mapped that don't exist in DICOM files": false_mapping,
        "Names within DICOM files that have not been mapped yet": to_be_mapped,
    }

    return result
