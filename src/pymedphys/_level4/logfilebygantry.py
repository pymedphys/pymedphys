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

import numpy as np

from .._level1.utilitiesconfig import get_filepath, get_gantry_tolerance

from .._level2.mudensity import (
    find_relevant_control_points, calc_mu_density_return_grid)
from .._level2.msqdelivery import multi_fetch_and_verify_mosaiq
from .._level2.trfdecode import delivery_data_from_logfile

from .._level3.logfileanalyse import calc_comparison, plot_results


from .._level0.libutils import get_imports
IMPORTS = get_imports(globals())


def get_mappings(index, file_hashes):
    patient_grouped_fields = dict()
    field_id_grouped_hashes = dict()

    for file_hash in file_hashes:
        delivery_details = index[file_hash]['delivery_details']
        patient_id = delivery_details['patient_id']
        field_id = delivery_details['field_id']

        if patient_id not in patient_grouped_fields:
            patient_grouped_fields[patient_id] = set()

        patient_grouped_fields[patient_id].add(field_id)

        if field_id not in field_id_grouped_hashes:
            field_id_grouped_hashes[field_id] = []

        field_id_grouped_hashes[field_id].append(file_hash)

    return patient_grouped_fields, field_id_grouped_hashes


def group_consecutive_logfiles(file_hashes, index):
    times = np.array([
        index[key]['local_time']
        for key in file_hashes
    ]).astype(np.datetime64)

    sort_reference = np.argsort(times)
    file_hashes = file_hashes[sort_reference]
    times = times[sort_reference]

    hours_4 = np.array(60 * 60 * 4).astype(np.timedelta64)
    split_locations = np.where(np.diff(times) >= hours_4)[0] + 1

    return np.split(file_hashes, split_locations)


def assert_array_agreement(unique_logfile_gantry_angles, mosaiq_gantry_angles,
                           allowed_deviation):
    difference_matrix = np.abs(
        unique_logfile_gantry_angles[:, None] - mosaiq_gantry_angles[None, :])
    agreement_matrix = difference_matrix <= allowed_deviation
    row_agreement = np.any(agreement_matrix, axis=1)
    at_least_one_agreement = np.all(row_agreement)

    assert at_least_one_agreement, (
        'There is a logfile gantry angle that deviates by more than {} degrees'
        ' from the Mosaiq control points. Unsure how to handle this.\n\n'
        'Logfile: {}\nMosaiq: {}\nDifference Matrix:\n{}\n'
        'Agreement Matrix:\n{}'.format(
            allowed_deviation, unique_logfile_gantry_angles,
            mosaiq_gantry_angles, difference_matrix, agreement_matrix))


def extract_angle_from_delivery_data(delivery_data, gantry_angle,
                                     gantry_tolerance=0):
    moniter_units = np.array(delivery_data.monitor_units)
    relevant_control_points = find_relevant_control_points(moniter_units)

    mu = moniter_units[relevant_control_points]
    mlc = np.array(delivery_data.mlc)[relevant_control_points]
    jaw = np.array(delivery_data.jaw)[relevant_control_points]
    gantry_angles = np.array(delivery_data.gantry)[relevant_control_points]

    gantry_angle_within_tolerance = (
        np.abs(gantry_angles - gantry_angle) <= gantry_tolerance)
    diff_mu = np.concatenate([[0], np.diff(mu)])[gantry_angle_within_tolerance]
    mu = np.cumsum(diff_mu)

    mlc = mlc[gantry_angle_within_tolerance]
    jaw = jaw[gantry_angle_within_tolerance]

    return mu, mlc, jaw


def get_field_id_from_logfile_group(index, logfile_group):
    field_ids = []

    for logfile_hash in logfile_group:
        field_ids.append(index[logfile_hash]['delivery_details']['field_id'])

    assert len(np.unique(field_ids)) == 1

    field_id = field_ids[0]

    return field_id


def calc_normalisation(mosaiq_delivery_data):
    all_gantry_angles = calc_mu_density_return_grid(
        mosaiq_delivery_data.monitor_units, mosaiq_delivery_data.mlc,
        mosaiq_delivery_data.jaw
    )
    mosaiq_gantry_angles = np.unique(mosaiq_delivery_data.gantry)
    number_of_gantry_angles = len(mosaiq_gantry_angles)

    normalisation = np.sum(all_gantry_angles[2]) / number_of_gantry_angles

    return normalisation


def calc_mu_density_bygantry(delivery_data, gantry_angle, grid_resolution=1):
    mu_density = calc_mu_density_return_grid(
        grid_resolution=grid_resolution,
        *extract_angle_from_delivery_data(delivery_data, gantry_angle)
    )

    return mu_density


def calc_logfile_mu_density_bygantry(index, config, logfile_group,
                                     gantry_angle, grid_resolution=1):
    logfile_mu_density = None

    for filehash in logfile_group:
        filepath = get_filepath(index, config, filehash)
        logfile_delivery_data = delivery_data_from_logfile(filepath)

        gantry_tolerance = get_gantry_tolerance(index, filehash, config)

        a_logfile_mu_density = calc_mu_density_return_grid(
            grid_resolution=grid_resolution,
            *extract_angle_from_delivery_data(
                logfile_delivery_data, gantry_angle, gantry_tolerance)
        )

        if logfile_mu_density is None:
            logfile_mu_density = a_logfile_mu_density
        else:
            assert np.all(logfile_mu_density[0] == a_logfile_mu_density[0])
            assert np.all(logfile_mu_density[1] == a_logfile_mu_density[1])
            logfile_mu_density[2] += a_logfile_mu_density[2]

    return logfile_mu_density


def compare_logfile_group_bygantry(index, config, cursor, logfile_group,
                                   gantry_angle):
    field_id = get_field_id_from_logfile_group(index, logfile_group)

    mosaiq_delivery_data = multi_fetch_and_verify_mosaiq(cursor, field_id)

    mosaiq_mu_density = calc_mu_density_bygantry(
        mosaiq_delivery_data, gantry_angle)
    normalisation = calc_normalisation(mosaiq_delivery_data)

    logfile_mu_density = calc_logfile_mu_density_bygantry(
        index, config, logfile_group, gantry_angle)

    grid_xx = logfile_mu_density[0]
    grid_yy = logfile_mu_density[1]
    assert np.all(grid_xx == mosaiq_mu_density[0])
    assert np.all(grid_yy == mosaiq_mu_density[1])

    comparison = calc_comparison(
        logfile_mu_density[2], mosaiq_mu_density[2], normalisation)

    print(comparison)
    plot_results(
        grid_xx, grid_yy, logfile_mu_density[2], mosaiq_mu_density[2])

    return comparison


# -----------------------------------------------------------------------------
# TODO Refactor the following functions to be in terms of the above.
# -----------------------------------------------------------------------------


def get_logfile_delivery_data_bygantry(index, config, logfile_groups,
                                       mosaiq_gantry_angles):
    logfile_delivery_data_bygantry = dict()

    for logfile_group in logfile_groups:
        logfile_delivery_data_bygantry[logfile_group] = dict()

        for file_hash in logfile_group:
            filepath = get_filepath(index, config, file_hash)
            logfile_delivery_data = delivery_data_from_logfile(filepath)
            mu = np.array(logfile_delivery_data.monitor_units)

            relevant_control_points = find_relevant_control_points(mu)

            mu = mu[relevant_control_points]
            mlc = np.array(logfile_delivery_data.mlc)[relevant_control_points]
            jaw = np.array(logfile_delivery_data.jaw)[relevant_control_points]
            logfile_gantry_angles = np.array(
                logfile_delivery_data.gantry)[relevant_control_points]

            gantry_tolerance = get_gantry_tolerance(index, file_hash, config)
            unique_logfile_gantry_angles = np.unique(logfile_gantry_angles)

            assert_array_agreement(
                unique_logfile_gantry_angles, mosaiq_gantry_angles,
                gantry_tolerance)

            logfile_delivery_data_bygantry[logfile_group][file_hash] = dict()

            for mosaiq_gantry_angle in mosaiq_gantry_angles:
                logfile_delivery_data_bygantry[logfile_group][file_hash][mosaiq_gantry_angle] = dict(
                )
                agrees_within_tolerance = (
                    np.abs(logfile_gantry_angles - mosaiq_gantry_angle) <= gantry_tolerance)

                logfile_delivery_data_bygantry[logfile_group][file_hash][
                    mosaiq_gantry_angle]['mu'] = mu[agrees_within_tolerance]
                logfile_delivery_data_bygantry[logfile_group][file_hash][
                    mosaiq_gantry_angle]['mlc'] = mlc[agrees_within_tolerance]
                logfile_delivery_data_bygantry[logfile_group][file_hash][
                    mosaiq_gantry_angle]['jaw'] = jaw[agrees_within_tolerance]

    return logfile_delivery_data_bygantry


def get_logfile_mu_density_bygantry(logfile_groups, mosaiq_gantry_angles,
                                    logfile_delivery_data_bygantry):
    logfile_mu_density_bygantry = dict()

    for logfile_group in logfile_groups:
        delivery_data = logfile_delivery_data_bygantry[logfile_group]
        logfile_mu_density_bygantry[logfile_group] = dict()

        for file_hash in logfile_group:
            for mosaiq_gantry_angle in mosaiq_gantry_angles:
                num_control_points = len(
                    delivery_data[file_hash][mosaiq_gantry_angle]['mu'])
                if num_control_points > 0:
                    mu_density = calc_mu_density_return_grid(
                        **delivery_data[file_hash][mosaiq_gantry_angle])
                    if mosaiq_gantry_angle not in logfile_mu_density_bygantry[logfile_group]:
                        logfile_mu_density_bygantry[logfile_group][mosaiq_gantry_angle] = list(
                            mu_density)
                    else:
                        assert np.all(
                            logfile_mu_density_bygantry[logfile_group][mosaiq_gantry_angle][0] == mu_density[0])
                        assert np.all(
                            logfile_mu_density_bygantry[logfile_group][mosaiq_gantry_angle][1] == mu_density[1])
                        logfile_mu_density_bygantry[logfile_group][mosaiq_gantry_angle][2] += mu_density[2]

    return logfile_mu_density_bygantry


def get_mosaiq_delivery_data_bygantry(mosaiq_delivery_data):
    mu = np.array(mosaiq_delivery_data.monitor_units)
    mlc = np.array(mosaiq_delivery_data.mlc)
    jaw = np.array(mosaiq_delivery_data.jaw)
    gantry_angles = np.array(mosaiq_delivery_data.gantry)
    unique_mosaiq_gantry_angles = np.unique(gantry_angles)

    mosaiq_delivery_data_bygantry = dict()

    for mosaiq_gantry_angle in unique_mosaiq_gantry_angles:
        gantry_angle_matches = gantry_angles == mosaiq_gantry_angle

        diff_mu = np.concatenate([[0], np.diff(mu)])[gantry_angle_matches]
        gantry_angle_specific_mu = np.cumsum(diff_mu)

        mosaiq_delivery_data_bygantry[mosaiq_gantry_angle] = dict()
        mosaiq_delivery_data_bygantry[mosaiq_gantry_angle]['mu'] = gantry_angle_specific_mu
        mosaiq_delivery_data_bygantry[mosaiq_gantry_angle]['mlc'] = mlc[gantry_angle_matches]
        mosaiq_delivery_data_bygantry[mosaiq_gantry_angle]['jaw'] = jaw[gantry_angle_matches]

    return mosaiq_delivery_data_bygantry


def get_mosaiq_mu_density_bygantry(mosaiq_delivery_data_bygantry):
    mosaiq_mu_density_bygantry = dict()
    mosaiq_gantry_angles = mosaiq_delivery_data_bygantry.keys()

    for mosaiq_gantry_angle in mosaiq_gantry_angles:
        mu_density = calc_mu_density_return_grid(
            **mosaiq_delivery_data_bygantry[mosaiq_gantry_angle])
        mosaiq_mu_density_bygantry[mosaiq_gantry_angle] = mu_density

    return mosaiq_mu_density_bygantry


def get_comparison_results(mosaiq_mu_density_bygantry,
                           logfile_mu_density_bygantry, normalisation):
    comparison_results = dict()
    mosaiq_gantry_angles = mosaiq_mu_density_bygantry.keys()
    logfile_groups = list(logfile_mu_density_bygantry.keys())

    for mosaiq_gantry_angle in mosaiq_gantry_angles:
        comparison_results[mosaiq_gantry_angle] = dict()
        comparison_results[mosaiq_gantry_angle]['comparisons'] = {}

        grid_xx = mosaiq_mu_density_bygantry[mosaiq_gantry_angle][0]
        grid_yy = mosaiq_mu_density_bygantry[mosaiq_gantry_angle][1]
        mosaiq_mu_density = mosaiq_mu_density_bygantry[mosaiq_gantry_angle][2]

        for logfile_group in logfile_groups:
            assert np.all(
                grid_xx == logfile_mu_density_bygantry[logfile_group][mosaiq_gantry_angle][0])
            assert np.all(
                grid_yy == logfile_mu_density_bygantry[logfile_group][mosaiq_gantry_angle][1])

            logfile_mu_density = logfile_mu_density_bygantry[logfile_group][mosaiq_gantry_angle][2]

            comparison = calc_comparison(
                logfile_mu_density, mosaiq_mu_density, normalisation)
            comparison_results[mosaiq_gantry_angle]['comparisons'][logfile_group] = comparison

        comparisons = np.array([
            comparison_results[mosaiq_gantry_angle]['comparisons'][logfile_group]
            for logfile_group in logfile_groups
        ])

        comparison_results[mosaiq_gantry_angle]['median'] = np.median(
            comparisons)
        ref = np.argmin(np.abs(
            comparisons -
            comparison_results[mosaiq_gantry_angle]['median']
        ))
        comparison_results[mosaiq_gantry_angle]['median_filehash_group'] = logfile_groups[ref]
        comparison_results[mosaiq_gantry_angle]['filehash_groups'] = logfile_groups

    return comparison_results


def get_comparisons_byfield(index, config, cursor, field_ids,
                            field_id_grouped_hashes):
    mosaiq_delivery_data_byfield = dict()

    for field_id in field_ids:
        mosaiq_delivery_data_byfield[field_id] = multi_fetch_and_verify_mosaiq(
            cursor, field_id)

    comparisons_byfield = dict()

    for field_id in field_ids:
        keys = np.array(field_id_grouped_hashes[field_id])
        logfile_groups = group_consecutive_logfiles(keys, index)
        logfile_groups = [
            tuple(group)
            for group in logfile_groups
        ]

        mosaiq_delivery_data = mosaiq_delivery_data_byfield[field_id]
        mosaiq_gantry_angles = np.unique(mosaiq_delivery_data.gantry)

        logfile_delivery_data_bygantry = get_logfile_delivery_data_bygantry(
            index, config, logfile_groups, mosaiq_gantry_angles)
        logfile_mu_density_bygantry = get_logfile_mu_density_bygantry(
            logfile_groups, mosaiq_gantry_angles, logfile_delivery_data_bygantry)
        mosaiq_delivery_data_bygantry = get_mosaiq_delivery_data_bygantry(
            mosaiq_delivery_data)
        mosaiq_mu_density_bygantry = get_mosaiq_mu_density_bygantry(
            mosaiq_delivery_data_bygantry)

        normalisation = calc_normalisation(mosaiq_delivery_data)
        comparison_results = get_comparison_results(
            mosaiq_mu_density_bygantry, logfile_mu_density_bygantry,
            normalisation)

        comparisons_byfield[field_id] = comparison_results

    return comparisons_byfield
