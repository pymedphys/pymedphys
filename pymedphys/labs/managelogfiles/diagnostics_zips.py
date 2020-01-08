# Copyright (C) 2019 Cancer Care Associates

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
import pathlib
import shutil
import zipfile
from glob import glob


def fetch_system_diagnostics(ip, storage_directory, other_directory=None):
    r"""Fetches and stores locally Linac system diagnostic files.

    For an Elekta Linac the system diagnostic backups are stored at
    \\IP\Backup\TCS\SDD+*.zip. These are copied to a defined local directory.

    Need to have logged in to this directory and ticked "remember credentials".
    You will need to use a login for the Linac NSS supplied by an Elekta
    engineer to access this file share.
    """

    backup_share_path = "\\\\{}\\Backup\\TCS\\".format(ip)
    diagnostic_file_search = "{}\\SDD+*.zip".format(backup_share_path)
    diagnostic_filepaths = glob(diagnostic_file_search)

    print("Found {} diagnostic zip files:".format(len(diagnostic_filepaths)))

    if other_directory is None:
        other_directory = storage_directory

    for nss_filepath in diagnostic_filepaths:
        basename = os.path.basename(nss_filepath)
        storage_filepath = os.path.join(storage_directory, basename)
        other_filepath = os.path.join(other_directory, basename)

        doesnt_exist_in_either_directory = not os.path.exists(
            storage_filepath
        ) and not os.path.exists(other_filepath)

        if doesnt_exist_in_either_directory:
            print("    Copying {}...".format(basename))
            shutil.copyfile(nss_filepath, storage_filepath)
        else:
            print("    {} has already been copied.".format(basename))


def fetch_system_diagnostics_multi_linac(
    machine_ip_map,
    storage_directory,
    to_be_indexed="to_be_indexed",
    already_indexed="already_indexed",
):
    """Run `fetch_system_diagnostics` for a set of machines and corresponding
    IPs.

    Won't redownload the diagnostic files if that diagnostics zip filename
    exists in either to_be_indexed or already_indexed.

    Example
    -------

    machine_ip_map = {
        '2619': '10.0.0.1',
        '2694': '10.0.0.2'
    }

    storage_directory = 'path/to/diagnostics/storage'

    fetch_system_diagnostics_multi_linac(machine_ip_map, storage_directory)
    """

    for machine, ip in machine_ip_map.items():
        print("\nFetching diagnostic zip files from {} @ {}".format(machine, ip))
        machine_storage_directory = os.path.join(
            storage_directory, to_be_indexed, machine
        )
        already_indexed_directory = os.path.join(
            storage_directory, already_indexed, machine
        )

        pathlib.Path(machine_storage_directory).mkdir(parents=True, exist_ok=True)

        fetch_system_diagnostics(
            ip, machine_storage_directory, already_indexed_directory
        )

    print("")


def already_indexed_path(current_location, to_be_indexed, already_indexed):
    machine_and_zip_filepath = os.path.relpath(current_location, to_be_indexed)

    path_to_be_moved_to = os.path.join(already_indexed, machine_and_zip_filepath)

    return os.path.abspath(path_to_be_moved_to)


def extract_diagnostic_zips_and_archive(logfile_data_directory):
    diagnostics_directory = os.path.join(logfile_data_directory, "diagnostics")
    diagnostics_to_be_indexed = os.path.join(diagnostics_directory, "to_be_indexed")
    diagnostics_already_indexed = os.path.join(diagnostics_directory, "already_indexed")

    logfiles_to_be_indexed = os.path.join(logfile_data_directory, "to_be_indexed")

    diagnostics_search_string = os.path.join(diagnostics_to_be_indexed, "*", "*.zip")

    diagnostics_filepaths = glob(diagnostics_search_string)

    print(
        "There are {} diagnostic zips which need to be extracted".format(
            len(diagnostics_filepaths)
        )
    )

    for diagnostic_filepath in diagnostics_filepaths:
        path_to_be_moved_to = already_indexed_path(
            diagnostic_filepath, diagnostics_to_be_indexed, diagnostics_already_indexed
        )

        pathlib.Path(os.path.dirname(path_to_be_moved_to)).mkdir(
            parents=True, exist_ok=True
        )

        print("    Extracting {}".format(diagnostic_filepath))

        with zipfile.ZipFile(diagnostic_filepath, "r") as zip_file:
            for file_name in zip_file.namelist():
                if file_name.endswith(".trf"):
                    zip_file.extract(file_name, logfiles_to_be_indexed)

        shutil.move(diagnostic_filepath, path_to_be_moved_to)
