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


import os
import json

from .._level0.libutils import get_imports
IMPORTS = get_imports(globals())


def get_gantry_tolerance(index, file_hash, config):
    machine_name = index[file_hash]['logfile_header']['machine']
    machine_type = config['machine_map'][machine_name]['type']
    gantry_tolerance = (
        config['machine_types'][machine_type]['gantry_tolerance'])

    return gantry_tolerance


def get_data_directory(config):
    return config['linac_logfile_data_directory']


def get_cache_filepaths(config):
    mu_density_config = config['mu_density']

    comparison_storage_filepath = os.path.join(
        get_data_directory(config),
        mu_density_config['comparisons_cache']['primary'])
    comparison_storage_scratch = os.path.join(
        get_data_directory(config),
        mu_density_config['comparisons_cache']['scratch'])

    return comparison_storage_filepath, comparison_storage_scratch


def get_mu_density_parameters(config):
    mu_density_config = config['mu_density']
    grid_resolution = mu_density_config['grid_resolution']
    ram_fraction = mu_density_config['ram_fraction']

    return grid_resolution, ram_fraction


def get_index(config):
    index_filepath = os.path.join(
        get_data_directory(config), 'index.json')
    with open(index_filepath) as json_data_file:
        index = json.load(json_data_file)

    return index


def get_centre(config, file_info):
    machine = file_info['logfile_header']['machine']
    centre = config['machine_map'][machine]['centre']
    return centre


def get_sql_servers(config):
    centres = list(config['centres'].keys())

    sql_servers = {
        centre: config['centres'][centre]['ois_specific_data']['sql_server']
        for centre in centres
    }

    return sql_servers


def get_sql_servers_list(config):
    sql_servers = get_sql_servers(config)

    sql_servers_list = [
        value
        for _, value in sql_servers.items()
    ]

    return sql_servers_list


def get_filepath(index, config, filehash):
    data_directory = get_data_directory(config)
    relative_path = index[filehash]['filepath']
    filepath = os.path.abspath(
        os.path.join(data_directory, 'indexed', relative_path))

    return filepath
