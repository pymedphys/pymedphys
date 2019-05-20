import os
from copy import deepcopy

import numpy as np

import pydicom

from pymedphys_coordsandscales.deliverydata import (
    DeliveryData, find_relevant_control_points)
from pymedphys_fileformats.trf import delivery_data_from_logfile


def trf2dcm(dcm_template_filepath, trf_filepath, gantry_angle, output_dir):
    trf_filename = os.path.basename(trf_filepath)
    filepath_out = os.path.join(output_dir, "{}.dcm".format(trf_filename))

    dicom_template = pydicom.read_file(dcm_template_filepath, force=True)
    delivery_data = delivery_data_from_logfile(trf_filepath)

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

    edited_dcm.save_as(filepath_out)


def strip_delivery_data(delivery_data, skip_size):
    new_delivery_data = []
    for item in delivery_data:
        new_delivery_data.append(np.array(item)[::skip_size].tolist())

    return DeliveryData(*new_delivery_data)


def filter_out_irrelivant_control_points(delivery_data):

    relvant_control_points = find_relevant_control_points(
        delivery_data.monitor_units)

    new_delivery_data = []
    for item in delivery_data:
        new_delivery_data.append(
            np.array(item)[relvant_control_points].tolist())

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
