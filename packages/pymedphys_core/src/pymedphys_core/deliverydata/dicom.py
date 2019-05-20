import os
from copy import deepcopy

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


def dicom_to_delivery_data(dicom_dataset, gantry_angle):
    gantry_angles_of_beam_sequences = [
        set(convert_angle_to_bipolar([
            control_point.GantryAngle
            for control_point in beam_sequence.ControlPointSequence
        ]))
        for beam_sequence in dicom_dataset.BeamSequence
    ]

    try:
        beam_sequence_index = gantry_angles_of_beam_sequences.index(
            set([gantry_angle]))
    except ValueError:
        raise ValueError(
            "Chosen static gantry angle doesn't exist within DICOM file")

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
            mlc[num_leaves::],
            -np.array(mlc[0:num_leaves])  # pylint: disable=invalid-unary-operand-type  # nopep8
        ]).T
        for mlc in mlcs
    ]

    mlcs = np.array(mlcs)

    dicom_jaw = [
        control_point.BeamLimitingDevicePositionSequence[0].LeafJawPositions
        for control_point in control_points
    ]

    jaw = np.array(dicom_jaw)[-1::-1]

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


def delivery_data_to_dicom(delivery_data, dicom_template, gantry_angle):
    delivery_data = filter_out_irrelivant_control_points(delivery_data)

    delivery_data = extract_one_gantry_angle(
        delivery_data, gantry_angle)  # abstract used gantry_angle = -120
    mlc = np.array(delivery_data.mlc)
    converted_mlc = convert_mlc_format(mlc)

    new_jaw = np.array(delivery_data.jaw)
    new_jaw[:, 1] = -new_jaw[:, 1]

    converted_jaw = new_jaw.astype(str)
    converted_jaw[:, 1] = new_jaw.astype(str)[:, 0]
    converted_jaw[:, 0] = new_jaw.astype(str)[:, 1]
    converted_jaw = converted_jaw.tolist()

    diff = np.append(np.diff(delivery_data.gantry), 0)
    movement = (np.empty_like(delivery_data.gantry)).astype(str)

    movement[diff > 0] = 'CW'
    movement[diff < 0] = 'CC'
    movement[diff == 0] = 'NONE'

    converted_gantry = np.array(delivery_data.gantry)
    converted_gantry[converted_gantry <
                     0] = converted_gantry[converted_gantry < 0] + 360

    converted_gantry = converted_gantry.astype(str).tolist()

    monitor_units = delivery_data.monitor_units

    control_point_sequence = dicom_template.BeamSequence[0].ControlPointSequence

    init_cp = deepcopy(control_point_sequence[0])
    subsequent_cp = deepcopy(control_point_sequence[-1])

    init_cp.GantryAngle = converted_gantry[0]
    init_cp.GantryRotationDirection = movement[0]
    init_cp.BeamLimitingDevicePositionSequence[0].LeafJawPositions = converted_jaw[0]

    init_cp.BeamLimitingDevicePositionSequence[1].LeafJawPositions = converted_mlc[0]

    remaining_cps = []
    for i, (mu, mlc_cp, jaw_cp, move_cp, gantry_cp) in enumerate(zip(monitor_units[1::],
                                                                     converted_mlc[1::],
                                                                     converted_jaw[1::],
                                                                     movement[1::],
                                                                     converted_gantry[1::])):
        current_cp = deepcopy(subsequent_cp)
        current_cp.ControlPointIndex = str(i+1)
        current_cp.GantryAngle = gantry_cp
        current_cp.GantryRotationDirection = move_cp
        current_cp.BeamLimitingDevicePositionSequence[0].LeafJawPositions = jaw_cp
        current_cp.BeamLimitingDevicePositionSequence[1].LeafJawPositions = mlc_cp
        current_cp.CumulativeMetersetWeight = np.around(
            mu / delivery_data.monitor_units[-1], decimals=5)

        remaining_cps.append(current_cp)

    all_control_points = [init_cp] + remaining_cps

    edited_dcm = deepcopy(dicom_template)

    edited_dcm.FractionGroupSequence[0].ReferencedBeamSequence[-2].BeamMeterset = (
        str(monitor_units[-1]))

    edited_dcm.FractionGroupSequence[0].ReferencedBeamSequence = [
        edited_dcm.FractionGroupSequence[0].ReferencedBeamSequence[-2]
    ]

    edited_dcm.BeamSequence[-2].ControlPointSequence = all_control_points
    edited_dcm.BeamSequence[-2].NumberOfControlPoints = len(all_control_points)

    edited_dcm.BeamSequence = [
        edited_dcm.BeamSequence[-2]
    ]

    return edited_dcm


def filter_out_irrelivant_control_points(delivery_data):

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


def extract_one_gantry_angle(delivery_data, gantry_angle):
    near_angle = np.abs(np.array(delivery_data.gantry) - gantry_angle) < 3
    assert np.all(np.diff(np.where(near_angle)[0]) == 1)

    new_delivery_data = []
    for item in delivery_data:
        new_delivery_data.append(np.array(item)[near_angle].tolist())

    new_delivery_data[0] = np.round(
        np.array(new_delivery_data[0]) - new_delivery_data[0][0], decimals=7).tolist()

    return DeliveryData(*new_delivery_data)


def convert_mlc_format(mlc):

    dicom_mlc_format = []
    for control_point in mlc:
        concatenated = np.hstack(
            [-control_point[-1::-1, 1], control_point[-1::-1, 0]])
        dicom_mlc_format.append(concatenated.astype(str).tolist())

    return dicom_mlc_format


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
