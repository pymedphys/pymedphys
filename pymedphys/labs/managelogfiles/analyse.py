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


"""Analyse logfiles.
"""

import json
import os
import traceback

from pymedphys._imports import numpy as np
from pymedphys._imports import plt

import pymedphys
from pymedphys._utilities.config import (
    get_cache_filepaths,
    get_centre,
    get_filepath,
    get_index,
    get_mu_density_parameters,
    get_sql_servers,
    get_sql_servers_list,
)


def analyse_single_hash(index, config, filehash, cursors):
    field_id_key_map = get_field_id_key_map(index)
    logfile_filepath = get_filepath(index, config, filehash)
    print(logfile_filepath)

    results = get_logfile_mosaiq_results(
        index, config, field_id_key_map, filehash, cursors, grid_resolution=5 / 3
    )

    comparison = calc_comparison(results[2], results[3])
    print("Comparison result = {}".format(comparison))
    plot_results(*results)

    return comparison


def load_comparisons_from_cache(config):
    (comparison_storage_filepath, _) = get_cache_filepaths(config)

    with open(comparison_storage_filepath, "r") as comparisons_file:
        comparison_storage = json.load(comparisons_file)

    file_hashes = np.array(list(comparison_storage.keys()))

    comparisons = np.array([comparison_storage[file_hash] for file_hash in file_hashes])

    index = get_index(config)
    file_paths_worst_first = np.array(
        [get_filepath_from_hash(config, index, file_hash) for file_hash in file_hashes]
    )

    sort_ref = np.argsort(comparisons)[::-1]

    file_hashes = file_hashes[sort_ref]
    # comparisons = comparisons[sort_ref]
    file_paths_worst_first = file_paths_worst_first[sort_ref]

    return file_hashes, comparison_storage, file_paths_worst_first


def get_field_id_key_map(index):
    field_id_key_map = dict()

    for key, value in index.items():
        if not value["delivery_details"]["qa_mode"]:
            field_id = value["delivery_details"]["field_id"]
            if field_id not in field_id_key_map:
                field_id_key_map[field_id] = []

            field_id_key_map[field_id].append(key)

    return field_id_key_map


def random_uncompared_logfiles(index, config, compared_hashes):
    index_set = set(index.keys())
    comparison_set = set(compared_hashes)

    not_yet_compared = np.array(list(index_set.difference(comparison_set)))
    field_types = np.array(
        [
            index[file_hash]["delivery_details"]["field_type"]
            for file_hash in not_yet_compared
        ]
    )

    file_hashes_vmat = not_yet_compared[field_types == "VMAT"]

    vmat_filepaths = np.array(
        [
            os.path.join(
                config["linac_logfile_data_directory"],
                "indexed",
                index[file_hash]["filepath"],
            )
            for file_hash in file_hashes_vmat
        ]
    )

    shuffle_index = np.arange(len(vmat_filepaths))
    np.random.shuffle(shuffle_index)

    return file_hashes_vmat[shuffle_index], vmat_filepaths[shuffle_index]


def mudensity_comparisons(config, plot=True, new_logfiles=False):
    (comparison_storage_filepath, comparison_storage_scratch) = get_cache_filepaths(
        config
    )

    grid_resolution, _ = get_mu_density_parameters(config)

    index = get_index(config)
    field_id_key_map = get_field_id_key_map(index)

    (file_hashes, comparisons, _) = load_comparisons_from_cache(config)

    if new_logfiles:
        file_hashes, _ = random_uncompared_logfiles(index, config, file_hashes)

    sql_servers_list = get_sql_servers_list(config)

    with pymedphys.mosaiq.connect(sql_servers_list) as cursors:
        for file_hash in file_hashes:

            try:
                logfile_filepath = get_filepath(index, config, file_hash)
                print("\n{}".format(logfile_filepath))

                if (new_logfiles) and (file_hash in comparisons):
                    raise AssertionError(
                        "A new logfile shouldn't have already been compared"
                    )

                if index[file_hash]["delivery_details"]["qa_mode"]:
                    print("Skipping QA field")
                else:
                    if file_hash in comparisons:
                        print(
                            "Cached comparison value = {}".format(
                                comparisons[file_hash]
                            )
                        )

                    results = get_logfile_mosaiq_results(
                        index,
                        config,
                        field_id_key_map,
                        file_hash,
                        cursors,
                        grid_resolution=grid_resolution,
                    )
                    new_comparison = calc_comparison(results[2], results[3])

                    if file_hash not in comparisons:
                        update_comparison_file(
                            file_hash,
                            new_comparison,
                            comparison_storage_filepath,
                            comparison_storage_scratch,
                        )
                        print(
                            "Newly calculated comparison value = {}".format(
                                new_comparison
                            )
                        )
                    elif np.abs(comparisons[file_hash] - new_comparison) > 0.00001:
                        print(
                            "Calculated comparison value does not agree with the "
                            "cached value."
                        )
                        print(
                            "Newly calculated comparison value = {}".format(
                                new_comparison
                            )
                        )
                        update_comparison_file(
                            file_hash,
                            new_comparison,
                            comparison_storage_filepath,
                            comparison_storage_scratch,
                        )
                        print("Overwrote the cache with the new result.")
                    else:
                        print(
                            "Calculated comparison value agrees with the cached value"
                        )
                    if plot:
                        plot_results(*results)
            except KeyboardInterrupt:
                raise
            except AssertionError:
                raise
            except Exception:  # pylint: disable = broad-except
                print(traceback.format_exc())


def mu_density_from_delivery_data(delivery_data: pymedphys.Delivery, grid_resolution=1):
    grid_xx, grid_yy = pymedphys.mudensity.grid(grid_resolution=grid_resolution)
    mu_density = delivery_data.mudensity(grid_resolution=grid_resolution)

    return grid_xx, grid_yy, mu_density


def find_consecutive_logfiles(field_id_key_map, field_id, filehash, index):
    keys = np.array(field_id_key_map[field_id])

    times = np.array([index[key]["local_time"] for key in keys]).astype(np.datetime64)

    sort_reference = np.argsort(times)
    keys = keys[sort_reference]
    times = times[sort_reference]

    hours_4 = np.array(60 * 60 * 4).astype(np.timedelta64)

    delivery_time = np.array(index[filehash]["local_time"]).astype(np.datetime64)
    within_4_hours_reference = np.abs(delivery_time - times) < hours_4
    within_4_hours = keys[within_4_hours_reference].tolist()

    return within_4_hours


def calc_and_merge_logfile_mudensity(filepaths, grid_resolution=1):
    logfile_results = []
    for filepath in filepaths:
        logfile_delivery_data = pymedphys.Delivery.from_logfile(filepath)
        mu_density_results = mu_density_from_delivery_data(
            logfile_delivery_data, grid_resolution=grid_resolution
        )

        logfile_results.append(mu_density_results)

    grid_xx_list = [result[0] for result in logfile_results]
    grid_yy_list = [result[1] for result in logfile_results]

    # assert np.array_equal(*grid_xx_list)
    # assert np.array_equal(*grid_yy_list)

    grid_xx = grid_xx_list[0]
    grid_yy = grid_yy_list[0]

    mu_densities = [result[2] for result in logfile_results]

    logfile_mu_density = np.sum(mu_densities, axis=0)

    return grid_xx, grid_yy, logfile_mu_density


def get_logfile_mosaiq_results(
    index, config, field_id_key_map, filehash, cursors, grid_resolution=1
):
    file_info = index[filehash]
    delivery_details = file_info["delivery_details"]
    field_id = delivery_details["field_id"]

    centre = get_centre(config, file_info)
    server = get_sql_servers(config)[centre]

    mosaiq_delivery_data = pymedphys.Delivery.from_mosaiq(cursors[server], field_id)

    mosaiq_results = mu_density_from_delivery_data(
        mosaiq_delivery_data, grid_resolution=grid_resolution
    )

    consecutive_keys = find_consecutive_logfiles(
        field_id_key_map, field_id, filehash, index
    )

    logfilepaths = [get_filepath(index, config, key) for key in consecutive_keys]

    logfile_results = calc_and_merge_logfile_mudensity(
        logfilepaths, grid_resolution=grid_resolution
    )

    try:
        assert np.all(logfile_results[0] == mosaiq_results[0])
        assert np.all(logfile_results[1] == mosaiq_results[1])
    except AssertionError:
        print(np.shape(logfile_results[0]))
        print(np.shape(mosaiq_results[0]))
        raise

    grid_xx = logfile_results[0]
    grid_yy = logfile_results[1]

    logfile_mu_density = logfile_results[2]
    mosaiq_mu_density = mosaiq_results[2]

    return grid_xx, grid_yy, logfile_mu_density, mosaiq_mu_density


def calc_comparison(logfile_mu_density, mosaiq_mu_density, normalisation=None):
    if normalisation is None:
        normalisation = np.sum(mosaiq_mu_density)

    comparison = np.sum(np.abs(logfile_mu_density - mosaiq_mu_density)) / normalisation

    return comparison


def get_filepath_from_hash(config, index, file_hash):
    return os.path.join(
        config["linac_logfile_data_directory"], "indexed", index[file_hash]["filepath"]
    )


def plot_results(
    grid_xx, grid_yy, logfile_mu_density, mosaiq_mu_density, diff_colour_scale=0.1
):
    min_val = np.min([logfile_mu_density, mosaiq_mu_density])
    max_val = np.max([logfile_mu_density, mosaiq_mu_density])

    plt.figure()
    plt.pcolormesh(grid_xx, grid_yy, logfile_mu_density, vmin=min_val, vmax=max_val)
    plt.colorbar()
    plt.title("Logfile MU density")
    plt.xlabel("MLC direction (mm)")
    plt.ylabel("Jaw direction (mm)")
    plt.gca().invert_yaxis()

    plt.figure()
    plt.pcolormesh(grid_xx, grid_yy, mosaiq_mu_density, vmin=min_val, vmax=max_val)
    plt.colorbar()
    plt.title("Mosaiq MU density")
    plt.xlabel("MLC direction (mm)")
    plt.ylabel("Jaw direction (mm)")
    plt.gca().invert_yaxis()

    scaled_diff = (logfile_mu_density - mosaiq_mu_density) / max_val

    plt.figure()
    plt.pcolormesh(
        grid_xx,
        grid_yy,
        scaled_diff,
        vmin=-diff_colour_scale / 2,
        vmax=diff_colour_scale / 2,
    )
    plt.colorbar(label="Limited colour range = {}".format(diff_colour_scale / 2))
    plt.title("(Logfile - Mosaiq MU density) / Maximum MU Density")
    plt.xlabel("MLC direction (mm)")
    plt.ylabel("Jaw direction (mm)")
    plt.gca().invert_yaxis()

    plt.show()

    plt.figure()
    plt.pcolormesh(
        grid_xx, grid_yy, scaled_diff, vmin=-diff_colour_scale, vmax=diff_colour_scale
    )
    plt.colorbar(label="Limited colour range = {}".format(diff_colour_scale))
    plt.title("(Logfile - Mosaiq MU density) / Maximum MU Density")
    plt.xlabel("MLC direction (mm)")
    plt.ylabel("Jaw direction (mm)")
    plt.gca().invert_yaxis()

    plt.show()

    absolute_range = np.max([-np.min(scaled_diff), np.max(scaled_diff)])

    plt.figure()
    plt.pcolormesh(
        grid_xx, grid_yy, scaled_diff, vmin=-absolute_range, vmax=absolute_range
    )
    plt.colorbar(label="No limited colour range")
    plt.title("(Logfile - Mosaiq MU density) / Maximum MU Density")
    plt.xlabel("MLC direction (mm)")
    plt.ylabel("Jaw direction (mm)")
    plt.gca().invert_yaxis()

    plt.show()


def update_comparison_file(
    file_hash, comparison, comparison_storage_filepath, comparison_storage_scratch
):
    with open(comparison_storage_filepath, "r") as comparisons_file:
        comparison_storage = json.load(comparisons_file)

    comparison_storage[file_hash] = comparison

    with open(comparison_storage_scratch, "w") as comparisons_file:
        json.dump(comparison_storage, comparisons_file)

    os.replace(comparison_storage_scratch, comparison_storage_filepath)
