# Copyright (C) 2018 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import os
import shutil
from glob import glob

ARCHIVE_DIRECTORY = r"\\UTILSVR\PhysBack\MONACO_ARCHIVE_1"
HOLDING_DIRECTORY = r"\\monacoda\FocalData\CurrentlyDeArchiving"
CLINICAL_DIRECTORY = r"\\monacoda\FocalData\RCCC\1~Clinical"

# ARCHIVE_DIRECTORY = r'C:\Users\sbiggs\Desktop\TEST'
# HOLDING_DIRECTORY = r'S:\Temp\TEST\holding'
# CLINICAL_DIRECTORY = r'S:\Temp\TEST\clinical'


def find_archived_folder(patient_id):
    string_id = str(patient_id).zfill(6)
    search_string = r"{}\*{}*".format(ARCHIVE_DIRECTORY, string_id)
    patient_folders_found = glob(search_string)

    assert not (len(patient_folders_found) == 0), "No patients found with that ID."
    assert not (
        len(patient_folders_found) > 1
    ), "There appears to be more than one archived patient with that ID."

    patient_folder_to_move = patient_folders_found[0]

    return patient_folder_to_move


def display_patient_name(patient_id):
    patient_folder_to_move = find_archived_folder(patient_id)

    demographic_search_string = os.path.join(patient_folder_to_move, "demographic*")
    demographic_file_list = glob(demographic_search_string)

    assert not (
        len(demographic_file_list) == 0
    ), "No demographic record for patient found."
    assert not (
        len(demographic_file_list) > 1
    ), "Multiple demographic records found. Don't know what to do with that."

    with open(demographic_file_list[0], "r") as file:
        lines = file.readlines()

    return lines[2].strip("\n")


def get_folder_names(patient_id):
    patient_folder_to_move = find_archived_folder(patient_id)
    patient_folder_name = os.path.basename(patient_folder_to_move)

    holding_location = os.path.join(HOLDING_DIRECTORY, patient_folder_name)
    location_to_move_to = os.path.join(CLINICAL_DIRECTORY, patient_folder_name)

    return patient_folder_to_move, holding_location, location_to_move_to


def folder_size(path):
    total = 0
    for entry in os.scandir(path):
        if entry.is_file():
            total += entry.stat().st_size
        elif entry.is_dir():
            total += folder_size(entry.path)
    return total


def get_origin_folder_size(patient_id):
    patient_folder_to_move, _, _ = get_folder_names(patient_id)
    return folder_size(patient_folder_to_move)


def get_proportion_moved(patient_id, origin_size):
    _, holding_location, location_to_move_to = get_folder_names(patient_id)
    if os.path.exists(location_to_move_to):
        return 1
    elif not os.path.exists(holding_location):
        return 0
    else:
        return folder_size(holding_location) / origin_size


def check_patient_name(patient_id, input_patient_name):
    demographic_patient_name = display_patient_name(patient_id)
    assert (
        input_patient_name == demographic_patient_name
    ), "Patient name given doesn't match the name on record."


def check_folders(patient_id):
    patient_folder_to_move, holding_location, location_to_move_to = get_folder_names(
        patient_id
    )

    assert os.path.exists(
        patient_folder_to_move
    ), "Tried to de-archive the patient but the archived file is gone!"
    assert not (
        os.path.exists(location_to_move_to)
    ), "Tried to de-archive the patient but there is already another patient record by the same ID."
    assert not (
        os.path.exists(holding_location)
    ), "The patient file exists within the holding directory! Was there a previous failed transfer?"


def dearchive_patient(patient_id, input_patient_name):
    check_patient_name(patient_id, input_patient_name)
    check_folders(patient_id)
    patient_folder_to_move, holding_location, location_to_move_to = get_folder_names(
        patient_id
    )

    shutil.move(patient_folder_to_move, holding_location)
    os.rename(holding_location, location_to_move_to)

    assert not (
        os.path.exists(patient_folder_to_move)
    ), "The move failed to delete the archived file!"
    assert os.path.exists(location_to_move_to), "Failed to de-archive!"
    assert not (
        os.path.exists(holding_location)
    ), "The patient file exists within the holding directory!"

    print("Patient folder moved successfully.")
