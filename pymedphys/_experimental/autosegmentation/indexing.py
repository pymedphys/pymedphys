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


def resolve_paths(root, paths_dict):
    root = pathlib.Path(root)
    resolved_paths_dict = {key: root.joinpath(item) for key, item in paths_dict.items()}

    return resolved_paths_dict


def read_uid_cache(data_path_root, uid_cache):
    ct_uid_to_structure_uid = uid_cache["ct_uid_to_structure_uid"]

    structure_uid_to_ct_uids = {}
    for ct_uid, structure_uid in ct_uid_to_structure_uid.items():
        try:
            structure_uid_to_ct_uids[structure_uid].append(ct_uid)
        except KeyError:
            structure_uid_to_ct_uids[structure_uid] = [ct_uid]

    return (
        resolve_paths(data_path_root, uid_cache["ct_image_paths"]),
        resolve_paths(data_path_root, uid_cache["structure_set_paths"]),
        ct_uid_to_structure_uid,
        structure_uid_to_ct_uids,
    )


def get_uid_cache(data_path_root, validate_cache=True):
    """Get inter-relationship maps between dicom files.

    Dicom files are to be placed within ``data_path_root/dicom``.
    A cache will be created at ``data_path_root/mappings/uid-cache.json``.

    Any change of the file structure within data_path_root/dicom will
    cause the cache to be flushed.
    """

    data_path_root = pathlib.Path(data_path_root)
    uid_cache_path = data_path_root.joinpath("mappings", "uid-cache.json")
    dcm_paths = list(data_path_root.rglob("dicom/**/*.dcm"))

    relative_paths = [str(path.relative_to(data_path_root)) for path in dcm_paths]

    try:
        with open(uid_cache_path) as f:
            uid_cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        uid_cache = {
            "ct_image_paths": {},
            "structure_set_paths": {},
            "ct_uid_to_structure_uid": {},
            "paths_when_run": [],
        }

    if validate_cache and set(uid_cache["paths_when_run"]) != set(relative_paths):
        dcm_headers = []
        for dcm_path in dcm_paths:
            dcm_headers.append(
                pydicom.read_file(
                    dcm_path,
                    force=True,
                    specific_tags=["SOPInstanceUID", "SOPClassUID", "StudyInstanceUID"],
                )
            )

        ct_image_paths = {
            str(header.SOPInstanceUID): str(path)
            for header, path in zip(dcm_headers, relative_paths)
            if header.SOPClassUID.name == "CT Image Storage"
        }

        structure_set_paths = {
            str(header.SOPInstanceUID): str(path)
            for header, path in zip(dcm_headers, relative_paths)
            if header.SOPClassUID.name == "RT Structure Set Storage"
        }

        ct_uid_to_study_instance_uid = {
            str(header.SOPInstanceUID): str(header.StudyInstanceUID)
            for header in dcm_headers
            if header.SOPClassUID.name == "CT Image Storage"
        }

        study_instance_uid_to_structure_uid = {
            str(header.StudyInstanceUID): str(header.SOPInstanceUID)
            for header in dcm_headers
            if header.SOPClassUID.name == "RT Structure Set Storage"
        }

        ct_uid_to_structure_uid = {
            ct_uid: study_instance_uid_to_structure_uid[study_uid]
            for ct_uid, study_uid in ct_uid_to_study_instance_uid.items()
        }

        uid_cache["ct_image_paths"] = ct_image_paths
        uid_cache["structure_set_paths"] = structure_set_paths
        uid_cache["ct_uid_to_structure_uid"] = ct_uid_to_structure_uid
        uid_cache["paths_when_run"] = relative_paths

        with open(uid_cache_path, "w") as f:
            json.dump(uid_cache, f)

    return read_uid_cache(data_path_root, uid_cache)


def get_structure_names_by_uids(structure_set_paths, names_map):
    structure_names_by_ct_uid = {}
    structure_names_by_structure_set_uid = {}

    for structure_set_uid, structure_set_path in structure_set_paths.items():
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

        structure_names_by_structure_set_uid[structure_set_uid] = [
            item for _, item in number_to_name_map.items()
        ]

        for roi_contour_sequence_item in structure_set.ROIContourSequence:
            try:
                structure_name = number_to_name_map[
                    roi_contour_sequence_item.ReferencedROINumber
                ]
            except KeyError:
                continue

            for contour_sequence_item in roi_contour_sequence_item.ContourSequence:
                contour_imaging_sequence = contour_sequence_item.ContourImageSequence
                ct_uid = contour_imaging_sequence[0].ReferencedSOPInstanceUID

                try:
                    structure_names_by_ct_uid[ct_uid].add(structure_name)
                except KeyError:
                    structure_names_by_ct_uid[ct_uid] = set([structure_name])

    structure_names_by_ct_uid = {
        key: list(item) for key, item in structure_names_by_ct_uid.items()
    }

    return structure_names_by_ct_uid, structure_names_by_structure_set_uid


def get_cached_structure_names_by_uids(data_path_root, structure_set_paths, names_map):
    data_path_root = pathlib.Path(data_path_root)
    structure_names_mapping_cache_path = data_path_root.joinpath(
        "mappings", "structure-names-mapping-cache.json"
    )

    relative_structure_set_paths = {
        key: str(pathlib.Path(path).relative_to(data_path_root))
        for key, path in structure_set_paths.items()
    }

    try:
        with open(structure_names_mapping_cache_path) as f:
            structure_names_cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        structure_names_cache = {
            "structure_names_by_ct_uid": {},
            "structure_names_by_structure_set_uid": {},
            "structure_set_paths_when_run": {},
            "names_map_when_run": {},
        }

    cache_valid = (
        structure_names_cache["structure_set_paths_when_run"].keys()
        == relative_structure_set_paths.keys()
        and structure_names_cache["names_map_when_run"] == names_map
    )

    if not cache_valid:
        (
            structure_names_by_ct_uid,
            structure_names_by_structure_set_uid,
        ) = get_structure_names_by_uids(structure_set_paths, names_map)

        structure_names_cache["structure_names_by_ct_uid"] = structure_names_by_ct_uid
        structure_names_cache[
            "structure_names_by_structure_set_uid"
        ] = structure_names_by_structure_set_uid
        structure_names_cache[
            "structure_set_paths_when_run"
        ] = relative_structure_set_paths
        structure_names_cache["names_map_when_run"] = names_map

        with open(structure_names_mapping_cache_path, "w") as f:
            json.dump(structure_names_cache, f)

    structure_names_by_ct_uid = structure_names_cache["structure_names_by_ct_uid"]
    structure_names_by_structure_set_uid = structure_names_cache[
        "structure_names_by_structure_set_uid"
    ]

    return structure_names_by_ct_uid, structure_names_by_structure_set_uid
