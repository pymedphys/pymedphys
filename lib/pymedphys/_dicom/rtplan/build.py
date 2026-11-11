# Copyright (C) 2026 Marchant Van der Walt
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
from pymedphys._imports import pydicom


def _device_position(control_point, device_type):
    """Return the control point's position item for a beam limiting
    device type, adding the item if the control point lacks it.

    After the first control point, PS3.3 C.8.8.14 lists only the
    devices that move during the beam, so a template's later control
    points can leave out the jaws, or every device.
    """
    if "BeamLimitingDevicePositionSequence" not in control_point:
        control_point.BeamLimitingDevicePositionSequence = []

    positions = control_point.BeamLimitingDevicePositionSequence
    for item in positions:
        if item.RTBeamLimitingDeviceType == device_type:
            return item

    item = pydicom.Dataset()
    item.RTBeamLimitingDeviceType = device_type
    positions.append(item)

    return item


def add_data_to_control_point(template, data, i, final_cumulative_meterset_weight):
    cp = deepcopy(template)
    cp.ControlPointIndex = str(i)

    # Multiplied by the Beam Dose, a Cumulative Dose Reference Coefficient
    # gives the beam's dose to the reference up to this control point
    # (PS3.3 C.8.8.14.7). It comes from the dose calculated for the
    # template's own control points, and a delivery records no dose, so
    # after the first control point, where it is zero by definition, it
    # is left empty (Type 2). The rest of each item is kept.
    if i > 0:
        for reference in cp.get("ReferencedDoseReferenceSequence", []):
            if "CumulativeDoseReferenceCoefficient" in reference:
                reference.CumulativeDoseReferenceCoefficient = None

    cp.GantryAngle = data["gantry_angle"][i]
    cp.GantryRotationDirection = data["gantry_movement"][i]

    cp.BeamLimitingDeviceAngle = data["collimator_angle"][i]
    cp.BeamLimitingDeviceRotationDirection = data["collimator_movement"][i]

    _device_position(cp, "ASYMY").LeafJawPositions = data["jaw"][i]
    _device_position(cp, "MLCX").LeafJawPositions = data["mlc"][i]

    # On the beam's Final Cumulative Meterset Weight scale, which the
    # final control point's weight equals (PS3.3 C.8.8.14).
    cp.CumulativeMetersetWeight = np.around(
        final_cumulative_meterset_weight
        * (data["monitor_units"][i] / data["monitor_units"][-1]),
        decimals=6,
    )

    return cp


def build_control_points(
    initial_cp_template,
    subsequent_cp_template,
    data,
    final_cumulative_meterset_weight,
):
    number_of_control_points = len(data["monitor_units"])

    cps = []
    for i in range(number_of_control_points):
        if i == 0:
            template = initial_cp_template
        else:
            template = subsequent_cp_template

        cps.append(
            add_data_to_control_point(
                template, data, i, final_cumulative_meterset_weight
            )
        )

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
            new_value = "{:.6f}".format(current_value)

            control_point.CumulativeMetersetWeight = new_value


def merge_beam_sequences(dicoms_by_gantry_angle):
    merged = dicoms_by_gantry_angle[0]

    for dicom in dicoms_by_gantry_angle[1::]:
        merged.BeamSequence.append(dicom.BeamSequence[0])
        merged.FractionGroupSequence[0].ReferencedBeamSequence.append(
            dicom.FractionGroupSequence[0].ReferencedBeamSequence[0]
        )

    return merged
