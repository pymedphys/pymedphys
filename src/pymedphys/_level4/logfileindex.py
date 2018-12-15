# Copyright (C) 2018 Cancer Care Associates

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version (the "AGPL-3.0+").

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License and the additional terms for more
# details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

# ADDITIONAL TERMS are also included as allowed by Section 7 of the GNU
# Affero General Public License. These additional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


# pylint: skip-file

"""Index logfiles.
"""

import os
import json
import pathlib
import traceback
from glob import glob

import attr

from .._level1.filehash import hash_file
from .._level1.utilitiesconfig import get_sql_servers
from .._level1.utilitiesfilesystem import make_a_valid_directory_name
from .._level1.msqconnect import multi_mosaiq_connect

from .._level2.msqdelivery import (
    get_mosaiq_delivery_details, OISDeliveryDetails, NoMosaiqEntries)
from .._level2.trfdecode import Header, decode_header_from_file
from .._level3.trfidentify import date_convert


from .._level0.libutils import get_imports
IMPORTS = get_imports(globals())


def create_logfile_directory_name(centre,
                                  delivery_details: OISDeliveryDetails,
                                  header: Header, path_string_time):
    proposed_patient_directory_name = '{}_{}_{}'.format(
        delivery_details.patient_id, delivery_details.last_name,
        delivery_details.first_name
    )

    patient_directory_name = make_a_valid_directory_name(
        proposed_patient_directory_name)

    if delivery_details.qa_mode:
        clinical_or_qa = 'qa'
    else:
        clinical_or_qa = 'clinical'

    proposed_field_directory_name = '{}_{}_{}_{}'.format(
        delivery_details.field_id, header.field_label, header.field_name,
        delivery_details.field_type
    )

    field_directory_name = make_a_valid_directory_name(
        proposed_field_directory_name)

    proposed_delivery_directory = '{}_{}'.format(
        path_string_time, header.machine
    )

    delivery_directory = make_a_valid_directory_name(
        proposed_delivery_directory)

    return os.path.join(
        centre, patient_directory_name, clinical_or_qa,
        field_directory_name, delivery_directory
    )


def create_index_entry(new_filepath, delivery_details: OISDeliveryDetails,
                       header: Header, mosaiq_string_time):

    index_entry = {
        'filepath': new_filepath,
        'delivery_details': {
            **attr.asdict(delivery_details)
        },
        'logfile_header': {
            **attr.asdict(header)
        },
        'local_time': mosaiq_string_time
    }

    return index_entry


def file_already_in_index(indexed_filepath, to_be_indexed_filepath, filehash):
    try:
        new_hash = hash_file(indexed_filepath)
    except FileNotFoundError:
        raise FileNotFoundError(
            "Indexed logfile can't be found in its declared location.")

    try:
        assert new_hash == filehash
    except AssertionError:
        raise AssertionError(
            "The located file doesn't agree with the index hash.")

    print('Already exists in index')
    os.remove(to_be_indexed_filepath)


def rename_and_handle_fileexists(old_filepath, new_filepath):
    try:
        os.rename(old_filepath, new_filepath)
    except FileExistsError:
        files_hashes_match = (
            hash_file(old_filepath) ==
            hash_file(new_filepath)
        )
        print('    File already exists at {}'.format(new_filepath))
        if files_hashes_match:
            os.remove(old_filepath)
        else:
            raise FileExistsError(
                "File already exists and the hash does not match")


# TODO Split this function up into smaller functions for easier reuse.
def file_ready_to_be_indexed(cursors, filehash_list, to_be_indexed_dict,
                             unknown_error_in_logfile, no_mosaiq_record_found,
                             no_field_label_in_logfile,
                             indexed_directory, index_filepath, index,
                             machine_map, centre_details, config):
    for filehash in filehash_list:
        logfile_basename = os.path.basename(to_be_indexed_dict[filehash])

        try:
            header = decode_header_from_file(to_be_indexed_dict[filehash])
            print("\n{}".format(header))
            if header.field_label == "":
                print('No field label in logfile')
                new_filepath = os.path.join(
                    no_field_label_in_logfile, logfile_basename)
                rename_and_handle_fileexists(
                    to_be_indexed_dict[filehash], new_filepath)
                continue

            centre = machine_map[header.machine]['centre']
            server = get_sql_servers(config)[centre]

            mosaiq_string_time, path_string_time = date_convert(
                header.date, centre_details[centre]['timezone'])
        except Exception as e:
            traceback.print_exc()
            new_filepath = os.path.join(
                unknown_error_in_logfile, logfile_basename)
            rename_and_handle_fileexists(
                to_be_indexed_dict[filehash], new_filepath)
            continue

        try:
            delivery_details = get_mosaiq_delivery_details(
                cursors[server], header.machine, mosaiq_string_time,
                header.field_label, header.field_name)
        except NoMosaiqEntries as e:
            print(e)
            new_filepath = os.path.join(
                no_mosaiq_record_found, logfile_basename)
            rename_and_handle_fileexists(
                to_be_indexed_dict[filehash], new_filepath)
            continue

        logfile_directory_name = create_logfile_directory_name(
            centre, delivery_details, header,
            path_string_time)

        abs_logfile_directory_name = os.path.abspath(
            os.path.join(indexed_directory, logfile_directory_name))

        pathlib.Path(abs_logfile_directory_name).mkdir(
            parents=True, exist_ok=True)

        new_filepath = os.path.join(
            logfile_directory_name,
            logfile_basename)

        index[filehash] = create_index_entry(
            new_filepath, delivery_details, header, mosaiq_string_time)

        abs_new_filepath = os.path.abspath(
            os.path.join(indexed_directory, new_filepath))

        index_extension_split = os.path.splitext(index_filepath)
        temp_index_path = "{}_temp{}".format(
            index_extension_split[0], index_extension_split[1])

        with open(temp_index_path, 'w') as json_data_file:
            json.dump(index, json_data_file, indent=2)

        os.replace(temp_index_path, index_filepath)

        os.rename(to_be_indexed_dict[filehash], abs_new_filepath)

        print('Indexed logfile:\n    {} -->\n    {}'.format(
            to_be_indexed_dict[filehash], abs_new_filepath))


def index_logfiles(config):
    data_directory = config['linac_logfile_data_directory']
    index_filepath = os.path.abspath(
        os.path.join(data_directory, 'index.json'))
    to_be_indexed_directory = os.path.abspath(
        os.path.join(data_directory, 'to_be_indexed'))
    indexed_directory = os.path.abspath(
        os.path.join(data_directory, 'indexed'))
    no_mosaiq_record_found = os.path.abspath(
        os.path.join(data_directory, 'no_mosaiq_record_found'))
    unknown_error_in_logfile = os.path.abspath(
        os.path.join(data_directory, 'unknown_error_in_logfile'))
    no_field_label_in_logfile = os.path.abspath(
        os.path.join(data_directory, 'no_field_label_in_logfile'))
    machine_map = config['machine_map']
    centre_details = config['centres']

    sql_server_and_ports = [
        "{}:{}".format(details['ois_specific_data']['sql_server'],
                       details['ois_specific_data']['port'])
        for _, details in centre_details.items()
    ]

    with open(index_filepath, 'r') as json_data_file:
        index = json.load(json_data_file)

    indexset = set(index.keys())

    print('\nConnecting to Mosaiq SQL servers...')
    with multi_mosaiq_connect(sql_server_and_ports) as cursors:

        print('Globbing index directory...')
        to_be_indexed = glob(
            os.path.join(to_be_indexed_directory, '**/*.trf'), recursive=True)

        chunk_size = 50
        number_to_be_indexed = len(to_be_indexed)
        to_be_indexed_chunked = [
            to_be_indexed[i:i+chunk_size]
            for i in range(0, number_to_be_indexed, chunk_size)]

        for i, a_to_be_indexed_chunk in enumerate(to_be_indexed_chunked):
            print('\nHashing a chunk of logfiles ({}/{})'.format(
                i + 1, len(to_be_indexed_chunked)))
            hashlist = [
                hash_file(filename, dot_feedback=True)
                for filename in a_to_be_indexed_chunk
            ]

            print(' ')

            to_be_indexed_dict = dict(zip(hashlist, a_to_be_indexed_chunk))

            hashset = set(hashlist)

            for filehash in list(hashset.intersection(indexset)):
                file_already_in_index(
                    os.path.join(
                        indexed_directory, index[filehash]['filepath']),
                    to_be_indexed_dict[filehash],
                    filehash
                )

            file_ready_to_be_indexed(
                cursors, list(hashset.difference(indexset)),
                to_be_indexed_dict,
                unknown_error_in_logfile, no_mosaiq_record_found,
                no_field_label_in_logfile,
                indexed_directory, index_filepath, index,
                machine_map, centre_details, config
            )
    print('Complete')
