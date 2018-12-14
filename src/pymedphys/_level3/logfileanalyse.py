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

"""Analyse logfiles.
"""

import os
import traceback
import json

import numpy as np
import matplotlib.pyplot as plt

from .._level1.typedeliverydata import get_delivery_parameters
from .._level1.utilitiesconfig import (
    get_cache_filepaths, get_mu_density_parameters,
    get_index, get_centre, get_sql_servers, get_sql_servers_list,
    get_filepath
)
from .._level1.msqconnect import multi_mosaiq_connect

from .._level2.mudensity import calc_mu_density
from .._level2.msqdelivery import multi_fetch_and_verify_mosaiq
from .._level2.trfdecode import delivery_data_from_logfile

from .._level0.libutils import get_imports
IMPORTS = get_imports(globals())


def analyse_single_hash(index, config, filehash, cursors):
    field_id_key_map = get_field_id_key_map(index)
    logfile_filepath = get_filepath(index, config, filehash)
    print(logfile_filepath)

    results = get_logfile_mosaiq_results(
        index, config, logfile_filepath, field_id_key_map,
        filehash, cursors,
        grid_resolution=5/3)

    comparison = calc_comparison(results[2], results[3])
    print("Comparison result = {}".format(comparison))
    plot_results(*results)

    return comparison


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
    # comparisons = comparisons[sort_ref]
    file_paths_worst_first = file_paths_worst_first[sort_ref]

    return file_hashes, comparison_storage, file_paths_worst_first


def get_field_id_key_map(index):
    field_id_key_map = dict()

    for key, value in index.items():
        if not value['delivery_details']['qa_mode']:
            field_id = value['delivery_details']['field_id']
            if field_id not in field_id_key_map:
                field_id_key_map[field_id] = []

            field_id_key_map[field_id].append(key)

    return field_id_key_map


def random_uncompared_logfiles(index, config, compared_hashes):
    index_set = set(index.keys())
    comparison_set = set(compared_hashes)

    not_yet_compared = np.array(list(index_set.difference(comparison_set)))
    field_types = np.array([
        index[file_hash]['delivery_details']['field_type']
        for file_hash in not_yet_compared
    ])

    file_hashes_vmat = not_yet_compared[field_types == 'VMAT']

    vmat_filepaths = np.array([
        os.path.join(
            config['linac_logfile_data_directory'],
            'indexed',
            index[file_hash]['filepath'])
        for file_hash in file_hashes_vmat
    ])

    shuffle_index = np.arange(len(vmat_filepaths))
    np.random.shuffle(shuffle_index)

    return file_hashes_vmat[shuffle_index], vmat_filepaths[shuffle_index]


def mudensity_comparisons(config, plot=True, new_logfiles=False):
    (
        comparison_storage_filepath, comparison_storage_scratch
    ) = get_cache_filepaths(config)

    grid_resolution, ram_fraction = get_mu_density_parameters(config)

    index = get_index(config)
    field_id_key_map = get_field_id_key_map(index)

    (
        file_hashes, comparisons, _
    ) = load_comparisons_from_cache(config)

    if new_logfiles:
        file_hashes, _ = random_uncompared_logfiles(
            index, config, file_hashes)

    sql_servers_list = get_sql_servers_list(config)

    with multi_mosaiq_connect(sql_servers_list) as cursors:
        for file_hash in file_hashes:

            try:
                logfile_filepath = get_filepath(index, config, file_hash)
                print("\n{}".format(logfile_filepath))

                if (new_logfiles) and (file_hash in comparisons):
                    raise AssertionError(
                        "A new logfile shouldn't have already been compared")

                if index[file_hash]['delivery_details']['qa_mode']:
                    print('Skipping QA field')
                else:
                    if file_hash in comparisons:
                        print("Cached comparison value = {}".format(
                            comparisons[file_hash]))

                    results = get_logfile_mosaiq_results(
                        index, config, logfile_filepath, field_id_key_map,
                        file_hash, cursors,
                        grid_resolution=grid_resolution)
                    new_comparison = calc_comparison(results[2], results[3])

                    if file_hash not in comparisons:
                        update_comparison_file(
                            file_hash, new_comparison,
                            comparison_storage_filepath,
                            comparison_storage_scratch)
                        print("Newly calculated comparison value = {}".format(
                            new_comparison))
                    elif np.abs(comparisons[file_hash] - new_comparison) > 0.00001:
                        print(
                            "Calced comparison value does not agree with the "
                            "cached value.")
                        print("Newly calculated comparison value = {}".format(
                            new_comparison))
                        update_comparison_file(
                            file_hash, new_comparison,
                            comparison_storage_filepath,
                            comparison_storage_scratch)
                        print("Overwrote the cache with the new result.")
                    else:
                        print(
                            "Calced comparison value agrees with the cached value")
                    if plot:
                        plot_results(*results)
            except KeyboardInterrupt:
                raise
            except AssertionError:
                raise
            except Exception:
                print(traceback.format_exc())


def mu_density_from_delivery_data(delivery_data, grid_resolution=1):
    mu, mlc, jaw = get_delivery_parameters(delivery_data)

    grid_xx, grid_yy, mu_density = calc_mu_density(
        mu, mlc, jaw,
        grid_resolution=grid_resolution)

    return grid_xx, grid_yy, mu_density


def find_consecutive_logfiles(field_id_key_map, field_id, filehash, index,
                              config):
    keys = np.array(field_id_key_map[field_id])

    times = np.array([
        index[key]['local_time']
        for key in keys
    ]).astype(np.datetime64)

    sort_reference = np.argsort(times)
    keys = keys[sort_reference]
    times = times[sort_reference]

    hours_4 = np.array(60 * 60 * 4).astype(np.timedelta64)

    delivery_time = np.array(
        index[filehash]['local_time']).astype(np.datetime64)
    within_4_hours_reference = np.abs(delivery_time - times) < hours_4
    within_4_hours = keys[within_4_hours_reference].tolist()

    return within_4_hours


def calc_and_merge_logfile_mudensity(filepaths, grid_resolution=1):
    logfile_results = []
    for filepath in filepaths:
        logfile_delivery_data = delivery_data_from_logfile(filepath)
        mu_density_results = mu_density_from_delivery_data(
            logfile_delivery_data, grid_resolution=grid_resolution)

        logfile_results.append(mu_density_results)

    grid_xx_list = [
        result[0] for result in logfile_results
    ]
    grid_yy_list = [
        result[1] for result in logfile_results
    ]

    # assert np.array_equal(*grid_xx_list)
    # assert np.array_equal(*grid_yy_list)

    grid_xx = grid_xx_list[0]
    grid_yy = grid_yy_list[0]

    mu_densities = [
        result[2] for result in logfile_results
    ]

    logfile_mu_density = np.sum(mu_densities, axis=0)

    return grid_xx, grid_yy, logfile_mu_density


def get_logfile_mosaiq_results(index, config, filepath, field_id_key_map,
                               filehash, cursors, grid_resolution=1):
    file_info = index[filehash]
    delivery_details = file_info['delivery_details']
    field_id = delivery_details['field_id']

    centre = get_centre(config, file_info)
    server = get_sql_servers(config)[centre]
    mosaiq_delivery_data = multi_fetch_and_verify_mosaiq(
        cursors[server], field_id)

    mosaiq_results = mu_density_from_delivery_data(
        mosaiq_delivery_data, grid_resolution=grid_resolution)

    consecutive_keys = find_consecutive_logfiles(
        field_id_key_map, field_id, filehash, index, config)

    logfilepaths = [
        get_filepath(index, config, key)
        for key in consecutive_keys
    ]

    logile_results = calc_and_merge_logfile_mudensity(
        logfilepaths, grid_resolution=grid_resolution)

    #     logfile_delivery_data = delivery_data_from_logfile(filepath)
    #     logile_results = mu_density_from_delivery_data(
    #         logfile_delivery_data, ram_fraction=ram_fraction,
    #         grid_resolution=grid_resolution)

    try:
        assert np.all(logile_results[0] == mosaiq_results[0])
        assert np.all(logile_results[1] == mosaiq_results[1])
    except AssertionError:
        print(np.shape(logile_results[0]))
        print(np.shape(mosaiq_results[0]))
        raise

    grid_xx = logile_results[0]
    grid_yy = logile_results[1]

    logfile_mu_density = logile_results[2]
    mosaiq_mu_density = mosaiq_results[2]

    return grid_xx, grid_yy, logfile_mu_density, mosaiq_mu_density


def calc_comparison(logfile_mu_density, mosaiq_mu_density, normalisation=None):
    if normalisation is None:
        normalisation = np.sum(mosaiq_mu_density)

    comparison = (
        np.sum(np.abs(logfile_mu_density - mosaiq_mu_density)) / normalisation)

    return comparison


# def get_logfile_mosaiq_comparison(index, config, filepath, cursors,
#                                   grid_resolution=1, ram_fraction=0.8):
#     _, _, logfile_mu_density, mosaiq_mu_density = get_logfile_mosaiq_results(
#         index, config, filepath, cursors, grid_resolution=grid_resolution,
#         ram_fraction=ram_fraction)

#     return calc_comparison(logfile_mu_density, mosaiq_mu_density)


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
