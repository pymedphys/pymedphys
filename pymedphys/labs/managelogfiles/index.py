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


"""Index logfiles.
"""

import json
import os
import pathlib
import traceback
from glob import glob

from pymedphys._imports import attr

from pymedphys._mosaiq.connect import multi_mosaiq_connect
from pymedphys._mosaiq.delivery import NoMosaiqEntries, get_mosaiq_delivery_details
from pymedphys._trf.header import Header, decode_header_from_file
from pymedphys._utilities.filehash import hash_file
from pymedphys._utilities.filesystem import make_a_valid_directory_name

from .identify import date_convert


def create_logfile_directory_name(
    centre, delivery_details, header: Header, path_string_time
):
    proposed_patient_directory_name = "{}_{}_{}".format(
        delivery_details.patient_id,
        delivery_details.last_name,
        delivery_details.first_name,
    )

    patient_directory_name = make_a_valid_directory_name(
        proposed_patient_directory_name
    )

    if delivery_details.qa_mode:
        clinical_or_qa = "qa"
    else:
        clinical_or_qa = "clinical"

    proposed_field_directory_name = "{}_{}_{}_{}".format(
        delivery_details.field_id,
        header.field_label,
        header.field_name,
        delivery_details.field_type,
    )

    field_directory_name = make_a_valid_directory_name(proposed_field_directory_name)

    proposed_delivery_directory = "{}_{}".format(path_string_time, header.machine)

    delivery_directory = make_a_valid_directory_name(proposed_delivery_directory)

    return os.path.join(
        centre,
        patient_directory_name,
        clinical_or_qa,
        field_directory_name,
        delivery_directory,
    )


def create_index_entry(
    new_filepath, delivery_details, header: Header, mosaiq_string_time
):

    index_entry = {
        "filepath": new_filepath,
        "delivery_details": {**attr.asdict(delivery_details)},
        "logfile_header": {**header._asdict()},
        "local_time": mosaiq_string_time,
    }

    return index_entry


# CODE SMELL: The logic within `file_already_in_index` is actually
# already handled by `rename_and_handle_fileexists`. This is
# unnecessarily duplicated.


def file_already_in_index(indexed_filepath, to_be_indexed_filepath, filehash):
    try:
        new_hash = hash_file(indexed_filepath)
    except FileNotFoundError:
        raise FileNotFoundError(
            "Indexed logfile can't be found in its declared location."
        )

    try:
        assert new_hash == filehash
    except AssertionError:
        raise AssertionError("The located file doesn't agree with the index hash.")

    print("Already exists in index")
    os.remove(to_be_indexed_filepath)


def rename_and_handle_fileexists(old_filepath, new_filepath):
    pathlib.Path(new_filepath).parent.mkdir(parents=True, exist_ok=True)

    try:
        os.rename(old_filepath, new_filepath)
    except FileExistsError:
        files_hashes_match = hash_file(old_filepath) == hash_file(new_filepath)
        print("    File already exists at {}".format(new_filepath))
        if files_hashes_match:
            os.remove(old_filepath)
        else:
            raise FileExistsError("File already exists and the hash does not match")


def get_logfile_mosaiq_info(
    cursor, machine_id, utc_date, mosaiq_timezone, field_label, field_name, buffer=240
):
    mosaiq_string_time, _ = date_convert(utc_date, mosaiq_timezone)
    delivery_details = get_mosaiq_delivery_details(
        cursor, machine_id, mosaiq_string_time, field_label, field_name, buffer=buffer
    )

    return attr.asdict(delivery_details)


# TODO Split this function up into smaller functions for easier reuse.
def file_ready_to_be_indexed(
    cursors,
    filehash_list,
    to_be_indexed_dict,
    unknown_error_in_logfile,
    no_mosaiq_record_found,
    no_field_label_in_logfile,
    indexed_directory,
    index_filepath,
    index,
    machine_map,
    centre_details,
    centre_server_map,
):
    for filehash in filehash_list:
        logfile_basename = os.path.basename(to_be_indexed_dict[filehash])

        try:
            header = decode_header_from_file(to_be_indexed_dict[filehash])
            print("\n{}".format(header))
            if header.field_label == "":
                print("No field label in logfile")
                new_filepath = os.path.join(no_field_label_in_logfile, logfile_basename)
                rename_and_handle_fileexists(to_be_indexed_dict[filehash], new_filepath)
                continue

            centre = machine_map[header.machine]["centre"]
            server = centre_server_map[centre]

            mosaiq_string_time, path_string_time = date_convert(
                header.date, centre_details[centre]["timezone"]
            )
        except Exception as e:  # pylint: disable = broad-except
            traceback.print_exc()
            new_filepath = os.path.join(unknown_error_in_logfile, logfile_basename)
            rename_and_handle_fileexists(to_be_indexed_dict[filehash], new_filepath)
            continue

        try:
            delivery_details = get_mosaiq_delivery_details(
                cursors[server],
                header.machine,
                mosaiq_string_time,
                header.field_label,
                header.field_name,
                buffer=240,
            )
        except NoMosaiqEntries as e:
            print(e)
            new_filepath = os.path.join(no_mosaiq_record_found, logfile_basename)
            rename_and_handle_fileexists(to_be_indexed_dict[filehash], new_filepath)
            continue

        logfile_directory_name = create_logfile_directory_name(
            centre, delivery_details, header, path_string_time
        )

        abs_logfile_directory_name = os.path.abspath(
            os.path.join(indexed_directory, logfile_directory_name)
        )

        pathlib.Path(abs_logfile_directory_name).mkdir(parents=True, exist_ok=True)

        new_filepath = os.path.join(logfile_directory_name, logfile_basename)

        index[filehash] = create_index_entry(
            new_filepath, delivery_details, header, mosaiq_string_time
        )

        abs_new_filepath = os.path.abspath(
            os.path.join(indexed_directory, new_filepath)
        )

        index_extension_split = os.path.splitext(index_filepath)
        temp_index_path = "{}_temp{}".format(
            index_extension_split[0], index_extension_split[1]
        )

        with open(temp_index_path, "w") as json_data_file:
            json.dump(index, json_data_file, indent=2)

        os.replace(temp_index_path, index_filepath)

        os.rename(to_be_indexed_dict[filehash], abs_new_filepath)

        print(
            "Indexed logfile:\n    {} -->\n    {}".format(
                to_be_indexed_dict[filehash], abs_new_filepath
            )
        )


def index_logfiles(centre_map, machine_map, logfile_data_directory):
    data_directory = logfile_data_directory
    index_filepath = os.path.abspath(os.path.join(data_directory, "index.json"))
    to_be_indexed_directory = os.path.abspath(
        os.path.join(data_directory, "to_be_indexed")
    )
    indexed_directory = os.path.abspath(os.path.join(data_directory, "indexed"))
    no_mosaiq_record_found = os.path.abspath(
        os.path.join(data_directory, "no_mosaiq_record_found")
    )
    unknown_error_in_logfile = os.path.abspath(
        os.path.join(data_directory, "unknown_error_in_logfile")
    )
    no_field_label_in_logfile = os.path.abspath(
        os.path.join(data_directory, "no_field_label_in_logfile")
    )
    # machine_map = config['machine_map']
    centre_details = centre_map

    centre_server_map = {
        centre: centre_lookup["mosaiq_sql_server"]
        for centre, centre_lookup in centre_map.items()
    }

    sql_server_and_ports = [
        "{}".format(details["mosaiq_sql_server"])
        for _, details in centre_details.items()
    ]

    try:
        with open(index_filepath, "r") as json_data_file:
            index = json.load(json_data_file)
    except FileNotFoundError:
        index = {}

    indexset = set(index.keys())

    print("\nConnecting to Mosaiq SQL servers...")
    with multi_mosaiq_connect(sql_server_and_ports) as cursors:

        print("Globbing index directory...")
        to_be_indexed = glob(
            os.path.join(to_be_indexed_directory, "**/*.trf"), recursive=True
        )

        chunk_size = 50
        number_to_be_indexed = len(to_be_indexed)
        to_be_indexed_chunked = [
            to_be_indexed[i : i + chunk_size]
            for i in range(0, number_to_be_indexed, chunk_size)
        ]

        for i, a_to_be_indexed_chunk in enumerate(to_be_indexed_chunked):
            print(
                "\nHashing a chunk of logfiles ({}/{})".format(
                    i + 1, len(to_be_indexed_chunked)
                )
            )
            hashlist = [
                hash_file(filename, dot_feedback=True)
                for filename in a_to_be_indexed_chunk
            ]

            print(" ")

            to_be_indexed_dict = dict(zip(hashlist, a_to_be_indexed_chunk))

            hashset = set(hashlist)

            for filehash in list(hashset.intersection(indexset)):
                file_already_in_index(
                    os.path.join(indexed_directory, index[filehash]["filepath"]),
                    to_be_indexed_dict[filehash],
                    filehash,
                )

            file_ready_to_be_indexed(
                cursors,
                list(hashset.difference(indexset)),
                to_be_indexed_dict,
                unknown_error_in_logfile,
                no_mosaiq_record_found,
                no_field_label_in_logfile,
                indexed_directory,
                index_filepath,
                index,
                machine_map,
                centre_details,
                centre_server_map,
            )
    print("Complete")
