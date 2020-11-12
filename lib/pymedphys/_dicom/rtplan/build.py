# Copyright (C) 2019 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from copy import deepcopy

from pymedphys._imports import numpy as np


def add_data_to_control_point(template, data, i):
    cp = deepcopy(template)
    cp.ControlPointIndex = str(i)

    cp.GantryAngle = data["gantry_angle"][i]
    cp.GantryRotationDirection = data["gantry_movement"][i]

    cp.BeamLimitingDeviceAngle = data["collimator_angle"][i]
    cp.BeamLimitingDeviceRotationDirection = data["collimator_movement"][i]

    collimation = cp.BeamLimitingDevicePositionSequence
    collimation[0].LeafJawPositions = data["jaw"][i]
    collimation[1].LeafJawPositions = data["mlc"][i]

    cp.CumulativeMetersetWeight = np.around(
        data["monitor_units"][i] / data["monitor_units"][-1], decimals=6
    )

    return cp


def build_control_points(initial_cp_template, subsequent_cp_template, data):
    number_of_control_points = len(data["monitor_units"])

    cps = []
    for i in range(number_of_control_points):
        if i == 0:
            template = initial_cp_template
        else:
            template = subsequent_cp_template

        cps.append(add_data_to_control_point(template, data, i))

    return cps


def replace_fraction_group(
    created_dicom, beam_meterset, beam_index, fraction_group_index
):
    fraction_group = created_dicom.FractionGroupSequence[fraction_group_index]
    referenced_beam = fraction_group.ReferencedBeamSequence[beam_index]
    referenced_beam.BeamMeterset = str(beam_meterset)
    fraction_group.ReferencedBeamSequence = [referenced_beam]
    created_dicom.FractionGroupSequence = [fraction_group]


def replace_beam_sequence(created_dicom, all_control_points, beam_index):
    beam = created_dicom.BeamSequence[beam_index]
    beam.ControlPointSequence = all_control_points
    beam.NumberOfControlPoints = len(all_control_points)
    created_dicom.BeamSequence = [beam]


def restore_trailing_zeros(created_dicom):
    for beam_sequence in created_dicom.BeamSequence:
        for control_point in beam_sequence.ControlPointSequence:
            current_value = float(control_point.CumulativeMetersetWeight)
            new_value = "{0:.6f}".format(current_value)

            control_point.CumulativeMetersetWeight = new_value


def merge_beam_sequences(dicoms_by_gantry_angle):
    merged = dicoms_by_gantry_angle[0]

    for dicom in dicoms_by_gantry_angle[1::]:
        merged.BeamSequence.append(dicom.BeamSequence[0])
        merged.FractionGroupSequence[0].ReferencedBeamSequence.append(
            dicom.FractionGroupSequence[0].ReferencedBeamSequence[0]
        )

    return merged
