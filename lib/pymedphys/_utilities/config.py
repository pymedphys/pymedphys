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


def get_gantry_tolerance(index, file_hash, config):
    machine_name = index[file_hash]["logfile_header"]["machine"]
    machine_type = config["machine_map"][machine_name]["type"]
    gantry_tolerance = config["machine_types"][machine_type]["gantry_tolerance"]

    return gantry_tolerance


def get_data_directory(config):
    return config["linac_logfile_data_directory"]


def get_cache_filepaths(config):
    mu_density_config = config["mu_density"]

    comparison_storage_filepath = os.path.join(
        get_data_directory(config), mu_density_config["comparisons_cache"]["primary"]
    )
    comparison_storage_scratch = os.path.join(
        get_data_directory(config), mu_density_config["comparisons_cache"]["scratch"]
    )

    return comparison_storage_filepath, comparison_storage_scratch


def get_mu_density_parameters(config):
    mu_density_config = config["mu_density"]
    grid_resolution = mu_density_config["grid_resolution"]
    ram_fraction = mu_density_config["ram_fraction"]

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


def get_filepath(index, config, filehash):
    data_directory = get_data_directory(config)
    relative_path = index[filehash]["filepath"]
    filepath = os.path.abspath(os.path.join(data_directory, "indexed", relative_path))

    return filepath
