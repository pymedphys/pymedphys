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

from .core import (
    DeliveryData, find_relevant_control_points)


def convert_angle_to_bipolar(angle):
    angle = np.copy(angle)
    if np.all(angle == 180):
        return angle

    angle[angle > 180] = angle[angle > 180] - 360

    is_180 = np.where(angle == 180)[0]
    not_180 = np.where(np.invert(angle == 180))[0]

    where_closest_left_leaning = np.argmin(
        np.abs(is_180[:, None] - not_180[None, :]), axis=1)
    where_closest_right_leaning = len(not_180) - 1 - np.argmin(np.abs(
        is_180[::-1, None] -
        not_180[None, ::-1]), axis=1)[::-1]

    closest_left_leaning = not_180[where_closest_left_leaning]
    closest_right_leaning = not_180[where_closest_right_leaning]

    assert np.all(
        np.sign(angle[closest_left_leaning]) ==
        np.sign(angle[closest_right_leaning])
    ), "Unable to automatically determine whether angle is 180 or -180"

    angle[is_180] = np.sign(angle[closest_left_leaning]) * angle[is_180]

    return angle


def get_gantry_angles_from_dicom(dicom_dataset):
    gantry_angles = [
        set(convert_angle_to_bipolar([
            control_point.GantryAngle
            for control_point in beam_sequence.ControlPointSequence
        ]))
        for beam_sequence in dicom_dataset.BeamSequence
    ]

    for gantry_angle_set in gantry_angles:
        if len(gantry_angle_set) != 1:
            raise ValueError(
                "Only a single gantry angle per beam is currently supported")

    gantry_angle_list = [
        list(item)[0]
        for item in gantry_angles
    ]

    return gantry_angle_list


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
                    [collection[field], getattr(delivery_data, field)], axis=0)
            except KeyError:
                collection[field] = getattr(delivery_data, field)

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


def maintain_order_unique(items):
    result = []
    for item in items:
        if item not in result:
            result.append(item)

    return result


def delivery_data_to_dicom(delivery_data: DeliveryData, dicom_template):
    delivery_data = filter_out_irrelivant_control_points(delivery_data)
    template_gantry_angles = get_gantry_angles_from_dicom(dicom_template)

    min_diff = np.min(np.diff(sorted(template_gantry_angles)))
    gantry_tol = np.min([min_diff / 2 - 0.1, 3])

    masks = [
        gantry_angle_mask(delivery_data, gantry_angle, gantry_tol)
        for gantry_angle in template_gantry_angles
    ]

    assert np.all(np.sum(masks, axis=0) == np.ones_like(delivery_data.gantry))

    single_beam_dicoms = []
    for beam_index, mask in enumerate(masks):
        masked_delivery_data = apply_mask_to_delivery_data(delivery_data, mask)
        single_beam_dicoms.append(delivery_data_to_dicom_single_beam(
            masked_delivery_data, dicom_template, beam_index))

    return merge_beam_sequences(single_beam_dicoms)


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

    beam_meterset = data_converted['monitor_units'][-1]
    replace_fraction_group(created_dicom, beam_meterset, beam_index)
    replace_beam_sequence(created_dicom, all_control_points, beam_index)

    return created_dicom


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


def gantry_dd2dcm(gantry):
    diff = np.append(np.diff(gantry), 0)
    movement = (np.empty_like(gantry)).astype(str)

    movement[diff > 0] = 'CW'
    movement[diff < 0] = 'CC'
    movement[diff == 0] = 'NONE'

    converted_gantry = np.array(gantry, copy=False)
    converted_gantry[converted_gantry < 0] = (
        converted_gantry[converted_gantry < 0] + 360)

    converted_gantry = converted_gantry.astype(str).tolist()

    return converted_gantry, movement


def coordinate_convert_delivery_data(delivery_data):
    monitor_units = delivery_data.monitor_units
    mlc = mlc_dd2dcm(delivery_data.mlc)
    jaw = jaw_dd2dcm(delivery_data.jaw)
    gantry_angle, gantry_movement = gantry_dd2dcm(delivery_data.gantry)
    # TODO: support collimator

    return {
        'monitor_units': monitor_units,
        'mlc': mlc,
        'jaw': jaw,
        'gantry_angle': gantry_angle,
        'gantry_movement': gantry_movement
    }


def replace_fraction_group(created_dicom, beam_meterset, beam_index):
    fraction_group = created_dicom.FractionGroupSequence[0]
    referenced_beam = fraction_group.ReferencedBeamSequence[beam_index]
    referenced_beam.BeamMeterset = str(beam_meterset)
    fraction_group.ReferencedBeamSequence = [referenced_beam]
    created_dicom.FractionGroupSequence = [fraction_group]


def replace_beam_sequence(created_dicom, all_control_points, beam_index):
    beam = created_dicom.BeamSequence[beam_index]
    beam.ControlPointSequence = all_control_points
    beam.NumberOfControlPoints = len(all_control_points)
    created_dicom.BeamSequence = [beam]


def build_control_points(initial_cp_template, subsequent_cp_template,
                         data):
    initial_cp_template = deepcopy(initial_cp_template)
    subsequent_cp_template = deepcopy(subsequent_cp_template)

    initial_cp_template.GantryAngle = data['gantry_angle'][0]
    initial_cp_template.GantryRotationDirection = data['gantry_movement'][0]

    init_cp_collimation = initial_cp_template.BeamLimitingDevicePositionSequence

    init_cp_collimation[0].LeafJawPositions = data['jaw'][0]
    init_cp_collimation[1].LeafJawPositions = data['mlc'][0]

    remaining_cps = []
    for i, (
        mu, mlc_cp, jaw_cp, move_cp, gantry_cp
    ) in enumerate(zip(data['monitor_units'][1::], data['mlc'][1::],
                       data['jaw'][1::], data['gantry_movement'][1::],
                       data['gantry_angle'][1::])):

        current_cp = deepcopy(subsequent_cp_template)
        current_cp.ControlPointIndex = str(i+1)
        current_cp.GantryAngle = gantry_cp
        current_cp.GantryRotationDirection = move_cp
        current_cp.BeamLimitingDevicePositionSequence[0].LeafJawPositions = jaw_cp
        current_cp.BeamLimitingDevicePositionSequence[1].LeafJawPositions = mlc_cp
        current_cp.CumulativeMetersetWeight = np.around(
            mu / data['monitor_units'][-1], decimals=6)

        remaining_cps.append(current_cp)

    all_control_points = [initial_cp_template] + remaining_cps

    return all_control_points


def filter_out_irrelivant_control_points(delivery_data: DeliveryData) -> DeliveryData:

    relvant_control_points = find_relevant_control_points(
        delivery_data.monitor_units)

    new_delivery_data = []
    for item in delivery_data:
        new_delivery_data.append(
            np.array(item)[relvant_control_points].tolist())

    return DeliveryData(*new_delivery_data)


def strip_delivery_data(delivery_data, skip_size):
    new_delivery_data = []
    for item in delivery_data:
        new_delivery_data.append(np.array(item)[::skip_size].tolist())

    return DeliveryData(*new_delivery_data)


def gantry_angle_mask(delivery_data, gantry_angle, gantry_angle_tol):
    near_angle = np.abs(
        np.array(delivery_data.gantry) - gantry_angle) <= gantry_angle_tol
    assert np.all(np.diff(np.where(near_angle)[0]) == 1)

    return near_angle


def apply_mask_to_delivery_data(delivery_data, mask):
    new_delivery_data = []
    for item in delivery_data:
        new_delivery_data.append(np.array(item)[mask].tolist())

    new_delivery_data[0] = np.round(
        np.array(new_delivery_data[0], copy=False)
        - new_delivery_data[0][0], decimals=7
    ).tolist()

    return DeliveryData(*new_delivery_data)


def extract_one_gantry_angle(delivery_data, gantry_angle, gantry_angle_tol=3):
    near_angle = gantry_angle_mask(
        delivery_data, gantry_angle, gantry_angle_tol)

    return apply_mask_to_delivery_data(delivery_data, near_angle)


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
