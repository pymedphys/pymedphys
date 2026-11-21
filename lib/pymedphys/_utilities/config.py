# Copyright (C) 2026 Jeffrey D. Cooney
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


import json
import os
import stat
from pathlib import Path


def get_gantry_tolerance(index, file_hash, config):
    machine_name = index[file_hash]["logfile_header"]["machine"]
    machine_type = config["machine_map"][machine_name]["type"]
    gantry_tolerance = config["machine_types"][machine_type]["gantry_tolerance"]

    return gantry_tolerance


def get_data_directory(config):
    return config["linac_logfile_data_directory"]


def get_cache_filepaths(config):
    metersetmap_config = config["metersetmap"]

    comparison_storage_filepath = os.path.join(
        get_data_directory(config), metersetmap_config["comparisons_cache"]["primary"]
    )
    comparison_storage_scratch = os.path.join(
        get_data_directory(config), metersetmap_config["comparisons_cache"]["scratch"]
    )

    return comparison_storage_filepath, comparison_storage_scratch


def get_metersetmap_parameters(config):
    metersetmap_config = config["metersetmap"]
    grid_resolution = metersetmap_config["grid_resolution"]
    ram_fraction = metersetmap_config["ram_fraction"]

    return grid_resolution, ram_fraction


def get_index(config):
    index_filepath = os.path.join(get_data_directory(config), "index.json")
    with open(index_filepath) as json_data_file:
        index = json.load(json_data_file)

    return index


def get_centre(config, file_info):
    machine = file_info["logfile_header"]["machine"]
    centre = config["machine_map"][machine]["centre"]
    return centre


def get_sql_servers(config):
    centres = list(config["centres"].keys())

    sql_servers = {
        centre: config["centres"][centre]["ois_specific_data"]["sql_server"]
        for centre in centres
    }

    return sql_servers


def get_sql_servers_list(config):
    sql_servers = get_sql_servers(config)

    sql_servers_list = [value for _, value in sql_servers.items()]

    return sql_servers_list


def _resolve_indexed_logfile_path(indexed_root, relative_path):
    """Resolve a logfile index entry to a file within its indexed root.

    Existing ancestors are compared by filesystem identity when differing
    path casing prevents a lexical match on a case-insensitive filesystem.
    """
    try:
        relative_path = Path(relative_path)
        if relative_path.is_absolute():
            raise ValueError

        root = Path(indexed_root).resolve()
        candidate = (root / relative_path).resolve()

        contained = candidate.is_relative_to(root)
        if not contained:
            for ancestor in candidate.parents:
                try:
                    if ancestor.samefile(root):
                        contained = True
                        break
                except (FileNotFoundError, NotADirectoryError):
                    continue

        if not contained:
            raise ValueError

        # Do not hash or return a FIFO, device, directory, or unresolved
        # symlink loop. A missing logfile is handled by its eventual reader.
        try:
            mode = candidate.stat().st_mode
        except FileNotFoundError:
            pass
        else:
            if not stat.S_ISREG(mode):
                raise ValueError

        return str(candidate)
    except (OSError, RuntimeError, TypeError, ValueError):
        raise ValueError("Indexed logfile path escapes the indexed directory.") from None


def get_filepath(index, config, filehash):
    return _resolve_indexed_logfile_path(
        os.path.join(get_data_directory(config), "indexed"),
        index[filehash]["filepath"],
    )
