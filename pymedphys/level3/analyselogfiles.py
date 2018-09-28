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
# Affrero General Public License. These aditional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


"""Analyse logfiles.
"""

import os
import traceback
import json

import numpy as np
import matplotlib.pyplot as plt

from ..level1.configutilities import (
    get_cache_filepaths, get_mu_density_parameters,
    get_index, get_centre, get_sql_servers, get_sql_servers_list
)
from ..level1.msqconnect import multi_mosaiq_connect
from ..level1.filehash import hash_file
from ..level1.deliverydata import get_delivery_parameters
from ..level1.mudensity import calc_mu_density
from ..level2.msqdelivery import multi_fetch_and_verify_mosaiq

# from ..level1.trfdecode import delivery_data_from_logfile
from decode_trf import delivery_data_from_logfile  # remove this when ready


def update_cache(config):
    (
        comparison_storage_filepath, comparison_storage_scratch
    ) = get_cache_filepaths(config)

    index = get_index(config)
    grid_resolution, ram_fraction = get_mu_density_parameters(config)

    with open(comparison_storage_filepath, 'r') as comparisons_file:
        comparison_storage = json.load(comparisons_file)

    index_set = set(index.keys())
    comparison_set = set(comparison_storage.keys())

    not_yet_compared = np.array(list(index_set.difference(comparison_set)))
    field_types = np.array([
        index[file_hash]['delivery_details']['field_type']
        for file_hash in not_yet_compared
    ])

    vmat_not_yet_compared = not_yet_compared[field_types == 'VMAT']

    vmat_filepaths = np.array([
        os.path.join(
            config['linac_logfile_data_directory'],
            'indexed',
            index[file_hash]['filepath'])
        for file_hash in vmat_not_yet_compared
    ])

    np.random.shuffle(vmat_filepaths)

    sql_servers_list = get_sql_servers_list(config)

    with multi_mosaiq_connect(sql_servers_list) as cursors:
        for file_hash, logfile_filepath in zip(
            vmat_not_yet_compared, vmat_filepaths
        ):
            try:
                print("\n{}".format(logfile_filepath))
                with open(
                    comparison_storage_filepath, 'r'
                ) as comparisons_file:
                    comparison_storage = json.load(comparisons_file)

                file_hash = hash_file(logfile_filepath)
                if file_hash in comparison_storage:
                    print('This file has already been compared.')
                else:
                    comparison = get_logfile_mosaiq_comparison(
                        index, config, logfile_filepath, cursors,
                        grid_resolution=grid_resolution,
                        ram_fraction=ram_fraction)
                    update_comparison_file(
                        file_hash, comparison,
                        comparison_storage_filepath,
                        comparison_storage_scratch)

                    print("Comparison result = {}".format(comparison))
            except KeyboardInterrupt:
                raise
            except Exception:
                print(traceback.format_exc())

    print('Done!')


def load_comparisons_from_cache(config):
    (
        comparison_storage_filepath, _
    ) = get_cache_filepaths(config)

    with open(comparison_storage_filepath, 'r') as comparisons_file:
        comparison_storage = json.load(comparisons_file)

    file_hashes = np.array(list(comparison_storage.keys()))

    comparisons = np.array([
        comparison_storage[file_hash]
        for file_hash in file_hashes
    ])

    index = get_index(config)
    file_paths_worst_first = np.array([
        get_filepath_from_hash(config, index, file_hash)
        for file_hash in file_hashes
    ])

    sort_ref = np.argsort(comparisons)[::-1]

    file_hashes = file_hashes[sort_ref]
    comparisons = comparisons[sort_ref]
    file_paths_worst_first = file_paths_worst_first[sort_ref]

    return file_hashes, comparisons, file_paths_worst_first


def plot_comparisons_from_cache(config, skip_larger_than=np.inf):
    (
        comparison_storage_filepath, comparison_storage_scratch
    ) = get_cache_filepaths(config)

    grid_resolution, ram_fraction = get_mu_density_parameters(config)

    index = get_index(config)

    (
        file_hashes, comparisons, file_paths_worst_first
    ) = load_comparisons_from_cache(config)

    sql_servers_list = get_sql_servers_list(config)

    with multi_mosaiq_connect(sql_servers_list) as cursors:

        for i, logfile_filepath in enumerate(file_paths_worst_first):
            print("\n{}".format(logfile_filepath))

            if index[file_hashes[i]]['delivery_details']['qa_mode']:
                print('Skipping QA field')
            elif comparisons[i] > skip_larger_than:
                print(
                    'Cached comparison value too large ({})\n'
                    'Skipping...'.format(comparisons[i]))
            else:
                print("Cached comparison value = {}".format(comparisons[i]))

                results = get_logfile_mosaiq_results(
                    index, config, logfile_filepath, cursors,
                    ram_fraction=ram_fraction, grid_resolution=grid_resolution)
                new_comparison = calc_comparison(results[2], results[3])

                if np.abs(comparisons[i] - new_comparison) > 0.00001:
                    print(
                        "Calced comparison value does not agree with the "
                        "cached value.")
                    print("Newly calculated comparison value = {}".format(
                        new_comparison))
                    update_comparison_file(
                        file_hashes[i], new_comparison,
                        comparison_storage_filepath,
                        comparison_storage_scratch)
                    print("Overwrote the cache with the new result.")
                else:
                    print(
                        "Calced comparison value agrees with the cached value")
                plot_results(*results)


def get_file_info(index, filepath):
    return index[hash_file(filepath)]


def mu_density_from_delivery_data(delivery_data, grid_resolution=1,
                                  ram_fraction=0.8):
    mu, mlc, jaw = get_delivery_parameters(delivery_data)

    grid_xx, grid_yy, mu_density = calc_mu_density(
        mu, mlc, jaw, ram_fraction=ram_fraction,
        grid_resolution=grid_resolution)

    return grid_xx, grid_yy, mu_density


def get_logfile_mosaiq_results(index, config, filepath, cursors,
                               ram_fraction=0.8, grid_resolution=1):
    logfile_delivery_data = delivery_data_from_logfile(filepath)

    file_info = get_file_info(index, filepath)
    delivery_details = file_info['delivery_details']
    field_id = delivery_details['field_id']

    centre = get_centre(config, file_info)
    server = get_sql_servers(config)[centre]
    mosaiq_delivery_data = multi_fetch_and_verify_mosaiq(
        cursors[server], field_id)

    mosaiq_results = mu_density_from_delivery_data(
        mosaiq_delivery_data, ram_fraction=ram_fraction,
        grid_resolution=grid_resolution)
    logile_results = mu_density_from_delivery_data(
        logfile_delivery_data, ram_fraction=ram_fraction,
        grid_resolution=grid_resolution)

    assert np.all(logile_results[0] == mosaiq_results[0])
    assert np.all(logile_results[1] == mosaiq_results[1])

    grid_xx = logile_results[0]
    grid_yy = logile_results[1]

    logfile_mu_density = logile_results[2]
    mosaiq_mu_density = mosaiq_results[2]

    return grid_xx, grid_yy, logfile_mu_density, mosaiq_mu_density


def calc_comparison(logfile_mu_density, mosaiq_mu_density):
    comparison = (
        np.sum(np.abs(logfile_mu_density - mosaiq_mu_density)) /
        np.sum(mosaiq_mu_density))

    return comparison


def get_logfile_mosaiq_comparison(index, config, filepath, cursors,
                                  grid_resolution=1, ram_fraction=0.8):
    _, _, logfile_mu_density, mosaiq_mu_density = get_logfile_mosaiq_results(
        index, config, filepath, cursors, grid_resolution=grid_resolution,
        ram_fraction=ram_fraction)

    return calc_comparison(logfile_mu_density, mosaiq_mu_density)


def get_filepath_from_hash(config, index, file_hash):
    return os.path.join(
        config['linac_logfile_data_directory'],
        'indexed',
        index[file_hash]['filepath'])


def plot_results(grid_xx, grid_yy, logfile_mu_density, mosaiq_mu_density,
                 diff_colour_scale=0.1):
    min_val = np.min([logfile_mu_density, mosaiq_mu_density])
    max_val = np.max([logfile_mu_density, mosaiq_mu_density])

    plt.figure()
    plt.pcolormesh(
        grid_xx,
        grid_yy,
        logfile_mu_density,
        vmin=min_val, vmax=max_val)
    plt.colorbar()
    plt.title('Logfile MU density')
    plt.xlabel('MLC direction (mm)')
    plt.ylabel('Jaw direction (mm)')
    plt.gca().invert_yaxis()

    plt.figure()
    plt.pcolormesh(
        grid_xx,
        grid_yy,
        mosaiq_mu_density,
        vmin=min_val, vmax=max_val)
    plt.colorbar()
    plt.title('Mosaiq MU density')
    plt.xlabel('MLC direction (mm)')
    plt.ylabel('Jaw direction (mm)')
    plt.gca().invert_yaxis()

    scaled_diff = (logfile_mu_density - mosaiq_mu_density) / max_val

    plt.figure()
    plt.pcolormesh(
        grid_xx,
        grid_yy,
        scaled_diff,
        vmin=-diff_colour_scale/2, vmax=diff_colour_scale/2)
    plt.colorbar(label='Limited colour range = {}'.format(diff_colour_scale/2))
    plt.title('(Logfile - Mosaiq MU density) / Maximum MU Density')
    plt.xlabel('MLC direction (mm)')
    plt.ylabel('Jaw direction (mm)')
    plt.gca().invert_yaxis()

    plt.show()

    plt.figure()
    plt.pcolormesh(
        grid_xx,
        grid_yy,
        scaled_diff,
        vmin=-diff_colour_scale, vmax=diff_colour_scale)
    plt.colorbar(label='Limited colour range = {}'.format(diff_colour_scale))
    plt.title('(Logfile - Mosaiq MU density) / Maximum MU Density')
    plt.xlabel('MLC direction (mm)')
    plt.ylabel('Jaw direction (mm)')
    plt.gca().invert_yaxis()

    plt.show()

    absolute_range = np.max([-np.min(scaled_diff), np.max(scaled_diff)])

    plt.figure()
    plt.pcolormesh(
        grid_xx,
        grid_yy,
        scaled_diff,
        vmin=-absolute_range, vmax=absolute_range)
    plt.colorbar(label='No limited colour range')
    plt.title('(Logfile - Mosaiq MU density) / Maximum MU Density')
    plt.xlabel('MLC direction (mm)')
    plt.ylabel('Jaw direction (mm)')
    plt.gca().invert_yaxis()

    plt.show()


def update_comparison_file(file_hash, comparison, comparison_storage_filepath,
                           comparison_storage_scratch):
    with open(comparison_storage_filepath, 'r') as comparisons_file:
        comparison_storage = json.load(comparisons_file)

    comparison_storage[file_hash] = comparison

    with open(comparison_storage_scratch, 'w') as comparisons_file:
        json.dump(comparison_storage, comparisons_file)

    os.replace(comparison_storage_scratch, comparison_storage_filepath)
