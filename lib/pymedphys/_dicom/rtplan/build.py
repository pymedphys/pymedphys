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

from collections.abc import Mapping, Sequence
from copy import deepcopy
from decimal import Decimal
from typing import Any

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

# A Decimal String holds at most 16 characters (PS3.5 6.2).
_DECIMAL_STRING_MAX_LENGTH = 16


def _device_position(
    control_point: "pydicom.Dataset", device_type: str
) -> "pydicom.Dataset":
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


def _cumulative_meterset_weight(
    monitor_units: Sequence[float], i: int, final_cumulative_meterset_weight: float
) -> str | float:
    """Return the Cumulative Meterset Weight to write at control point
    ``i`` of a beam.

    The weight is the control point's share of the beam's monitor units,
    on the scale of the beam's Final Cumulative Meterset Weight. A
    control point's meterset is the Beam Meterset times its weight over
    the final weight (PS3.3 C.8.8.14.1), so the weight is written to
    within a millionth of the final weight, whatever that scale is: to
    six decimal places, to more where the final weight is below 1, and
    to seven significant figures where those decimal places do not fit
    a Decimal String. That holds for a final weight of at least
    ``sys.float_info.min``, below which a float no longer has full
    precision and ``Delivery.to_dicom`` refuses the template.

    The weight at the end of the beam equals the final weight (PS3.3
    C.8.8.14), compared as the decimal numbers that are written, not as
    floats. Where the rounded weight would differ from it there, or
    would pass it just before, the final weight itself is returned, as
    the template gives it.
    """
    final_weight = float(final_cumulative_meterset_weight)
    fraction = monitor_units[i] / monitor_units[-1]
    weight = final_weight * fraction

    # Six decimal places, as have always been written, give a millionth
    # of a final weight of 1 or more. A final weight below 1 needs as
    # many more as its first significant figure lies behind the decimal
    # point: 0.0001 needs four more.
    decimals = 6 - min(Decimal(repr(final_weight)).adjusted(), 0)

    # The digits before the decimal point that a Decimal String has room
    # for beside those decimal places. A weight that needs more is given
    # seven significant figures instead.
    whole_digits = _DECIMAL_STRING_MAX_LENGTH - len(".") - decimals
    text = f"{weight:.6E}"
    if whole_digits >= 1 and not abs(weight) >= 10**whole_digits:
        fixed_point = f"{np.around(weight, decimals):.{decimals}f}"
        if len(fixed_point) <= _DECIMAL_STRING_MAX_LENGTH:
            text = fixed_point

    # As decimals: two Decimal Strings that a float holds as the same
    # number, such as 9999990000000001 and 9.999990E+15, are not equal.
    written = Decimal(text)
    exact_final_weight = Decimal(str(final_cumulative_meterset_weight))
    if (fraction == 1 and written != exact_final_weight) or (
        fraction < 1 and written > exact_final_weight
    ):
        return final_cumulative_meterset_weight

    return text


def add_data_to_control_point(
    template: "pydicom.Dataset",
    data: Mapping[str, Any],
    i: int,
    final_cumulative_meterset_weight: float,
) -> "pydicom.Dataset":
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

    cp.CumulativeMetersetWeight = _cumulative_meterset_weight(
        data["monitor_units"], i, final_cumulative_meterset_weight
    )

    return cp


def build_control_points(
    initial_cp_template: "pydicom.Dataset",
    subsequent_cp_template: "pydicom.Dataset",
    data: Mapping[str, Any],
    final_cumulative_meterset_weight: float,
) -> "list[pydicom.Dataset]":
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


def merge_beam_sequences(dicoms_by_gantry_angle):
    merged = dicoms_by_gantry_angle[0]

    for dicom in dicoms_by_gantry_angle[1::]:
        merged.BeamSequence.append(dicom.BeamSequence[0])
        merged.FractionGroupSequence[0].ReferencedBeamSequence.append(
            dicom.FractionGroupSequence[0].ReferencedBeamSequence[0]
        )

    return merged
