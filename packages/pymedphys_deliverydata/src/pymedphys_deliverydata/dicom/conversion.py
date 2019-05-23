# Copyright (C) 2019 Cancer Care Associates and Simon Biggs

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


from copy import deepcopy
from typing import List

import numpy as np

from pymedphys_utilities.transforms import convert_angle_to_bipolar
from pymedphys_utilities.algorithms import maintain_order_unique

from pymedphys_dicom.rtplan import (
    get_gantry_angles_from_dicom,
    build_control_points,
    replace_fraction_group,
    replace_beam_sequence,
    restore_trailing_zeros)


from ..base import DeliveryData
from ..utilities import (
    find_relevant_control_points,
    filter_out_irrelevant_control_points,
    get_all_masked_delivery_data)


def delivery_data_to_dicom(delivery_data: DeliveryData, dicom_template):
    delivery_data = filter_out_irrelevant_control_points(delivery_data)
    template_gantry_angles = get_gantry_angles_from_dicom(dicom_template)

    min_diff = np.min(np.diff(sorted(template_gantry_angles)))
    gantry_tol = np.min([min_diff / 2 - 0.1, 3])

    all_masked_delivery_data = get_all_masked_delivery_data(
        delivery_data, template_gantry_angles, gantry_tol)

    single_beam_dicoms = []
    for beam_index, masked_delivery_data in enumerate(all_masked_delivery_data):
        single_beam_dicoms.append(delivery_data_to_dicom_single_beam(
            masked_delivery_data, dicom_template, beam_index))

    return merge_beam_sequences(single_beam_dicoms)


def get_metersets_from_delivery_data(all_masked_delivery_data):
    metersets = []
    for delivery_data in all_masked_delivery_data:
        try:
            metersets.append(delivery_data.monitor_units[-1])
        except IndexError:
            continue

    return metersets


def dicom_to_delivery_data(dicom_dataset) -> DeliveryData:
    gantry_angles_of_beam_sequences = get_gantry_angles_from_dicom(
        dicom_dataset)

    delivery_data_by_beam_sequence = []
    for beam_sequence_index, _ in enumerate(dicom_dataset.BeamSequence):
        delivery_data_by_beam_sequence.append(
            dicom_to_delivery_data_single_beam(
                dicom_dataset, beam_sequence_index))

    return merge_delivery_data(delivery_data_by_beam_sequence)


def merge_delivery_data(separate: List[DeliveryData]) -> DeliveryData:
    collection = {}  # type: ignore

    for delivery_data in separate:
        for field in delivery_data._fields:
            try:
                collection[field] = np.concatenate(
                    [collection[field], getattr(delivery_data, field)],
                    axis=0
                )
            except KeyError:
                collection[field] = getattr(delivery_data, field)

    mu = np.concatenate([[0], np.diff(collection['monitor_units'])])
    mu[mu < 0] = 0
    collection['monitor_units'] = np.cumsum(mu)

    for key, item in collection.items():
        collection[key] = item.tolist()

    merged = DeliveryData(**collection)

    return merged


def dicom_to_delivery_data_single_beam(dicom_dataset, beam_sequence_index):
    beam_sequence = dicom_dataset.BeamSequence[beam_sequence_index]
    leaf_boundaries = beam_sequence.BeamLimitingDeviceSequence[-1].LeafPositionBoundaries
    leaf_widths = np.diff(leaf_boundaries)

    assert beam_sequence.BeamLimitingDeviceSequence[-1].NumberOfLeafJawPairs == len(
        leaf_widths)
    num_leaves = len(leaf_widths)

    control_points = beam_sequence.ControlPointSequence

    mlcs = [
        control_point.BeamLimitingDevicePositionSequence[-1].LeafJawPositions
        for control_point in control_points
    ]

    mlcs = [
        np.array([
            -np.array(mlc[0:num_leaves][::-1]),  # pylint: disable=invalid-unary-operand-type  # nopep8
            np.array(mlc[num_leaves::][::-1])
        ][::-1]).T
        for mlc in mlcs
    ]

    mlcs = np.array(mlcs)

    dicom_jaw = [
        control_point.BeamLimitingDevicePositionSequence[0].LeafJawPositions
        for control_point in control_points
    ]

    jaw = np.array(dicom_jaw)

    second_col = deepcopy(jaw[:, 1])
    jaw[:, 1] = jaw[:, 0]
    jaw[:, 0] = second_col

    jaw[:, 1] = -jaw[:, 1]

    total_mu = np.array(
        dicom_dataset.FractionGroupSequence[0].ReferencedBeamSequence[  # TODO: Make this more generalised
            beam_sequence_index].BeamMeterset)
    final_mu_weight = np.array(beam_sequence.FinalCumulativeMetersetWeight)

    mu = [
        total_mu *
        np.array(control_point.CumulativeMetersetWeight) / final_mu_weight
        for control_point in control_points
    ]
    mu = np.array(mu)

    gantry_angles = convert_angle_to_bipolar([
        control_point.GantryAngle
        for control_point in control_points
    ])

    collimator_angles = convert_angle_to_bipolar([
        control_point.BeamLimitingDeviceAngle
        for control_point in control_points
    ])

    return DeliveryData(mu, gantry_angles, collimator_angles, mlcs, jaw)


def merge_beam_sequences(dicoms_by_gantry_angle):
    merged = dicoms_by_gantry_angle[0]

    for dicom in dicoms_by_gantry_angle[1::]:
        merged.BeamSequence.append(
            dicom.BeamSequence[0]
        )
        merged.FractionGroupSequence[0].ReferencedBeamSequence.append(
            dicom.FractionGroupSequence[0].ReferencedBeamSequence[0]
        )

    return merged


def delivery_data_to_dicom_single_beam(delivery_data, dicom_template,
                                       beam_index):

    created_dicom = deepcopy(dicom_template)
    data_converted = coordinate_convert_delivery_data(delivery_data)

    beam = created_dicom.BeamSequence[beam_index]
    cp_sequence = beam.ControlPointSequence
    initial_cp = cp_sequence[0]
    subsequent_cp = cp_sequence[-1]

    all_control_points = build_control_points(
        initial_cp, subsequent_cp, data_converted)

    beam_meterset = '{0:.6f}'.format(data_converted['monitor_units'][-1])
    replace_fraction_group(created_dicom, beam_meterset, beam_index)
    replace_beam_sequence(created_dicom, all_control_points, beam_index)

    restore_trailing_zeros(created_dicom)

    return created_dicom


def coordinate_convert_delivery_data(delivery_data):
    monitor_units = delivery_data.monitor_units
    mlc = mlc_dd2dcm(delivery_data.mlc)
    jaw = jaw_dd2dcm(delivery_data.jaw)
    gantry_angle, gantry_movement = angle_dd2dcm(delivery_data.gantry)
    collimator_angle, collimator_movement = angle_dd2dcm(
        delivery_data.collimator)

    return {
        'monitor_units': monitor_units,
        'mlc': mlc,
        'jaw': jaw,
        'gantry_angle': gantry_angle,
        'gantry_movement': gantry_movement,
        'collimator_angle': collimator_angle,
        'collimator_movement': collimator_movement
    }


def jaw_dd2dcm(jaw):
    jaw = np.array(jaw, copy=False)

    new_jaw = np.array(jaw)
    new_jaw[:, 1] = -new_jaw[:, 1]

    converted_jaw = new_jaw.astype(str)
    converted_jaw[:, 1] = new_jaw.astype(str)[:, 0]
    converted_jaw[:, 0] = new_jaw.astype(str)[:, 1]
    converted_jaw = converted_jaw.tolist()

    return converted_jaw


def mlc_dd2dcm(mlc):
    mlc = np.array(mlc, copy=False)

    dicom_mlc_format = []
    for control_point in mlc:
        concatenated = np.hstack(
            [-control_point[-1::-1, 1], control_point[-1::-1, 0]])
        dicom_mlc_format.append(concatenated.astype(str).tolist())

    return dicom_mlc_format


def angle_dd2dcm(angle):
    diff = np.append(np.diff(angle), 0)
    movement = (np.empty_like(angle)).astype(str)

    movement[diff > 0] = 'CW'
    movement[diff < 0] = 'CC'
    movement[diff == 0] = 'NONE'

    converted_angle = np.array(angle, copy=False)
    converted_angle[converted_angle < 0] = (
        converted_angle[converted_angle < 0] + 360)

    converted_angle = converted_angle.astype(str).tolist()

    return converted_angle, movement


def convert_jaw_format(jaw):
    dicom_jaw_format = []
    for control_point in jaw:
        control_point[0]


def movement_check(angles):
    float_angles = angles.astype(np.float64)
    float_angles[float_angles >= 180] = float_angles[float_angles >= 180] - 360
    diff = np.append(np.diff(float_angles), 0)

    movement = (np.empty_like(angles)).astype(str)
    movement[diff > 0] = 'CW'
    movement[diff < 0] = 'CC'
    movement[diff == 0] = 'NONE'

    return movement
