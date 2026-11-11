# Copyright (C) 2026 Marchant Van der Walt

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Writing a delivery into small synthetic RT Plan templates.

Each template has two step-and-shoot beams, at gantry 0 and 90 degrees,
with Beam Metersets of 100 and 50 MU. Their four control points have
Cumulative Meterset Weights of 0, 0.5, 0.5 and 1 times the beam's Final
Cumulative Meterset Weight, and the leaves move between the second and
third control points.
"""

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

import pymedphys

JAW = [-50.0, 60.0]
MLC_A = [-5.0, -6.0, -7.0, -8.0, 5.0, 6.0, 7.0, 8.0]
MLC_B = [-15.0, -16.0, -17.0, -18.0, 15.0, 16.0, 17.0, 18.0]

# (fraction of the beam's meterset, MLCX positions) at each control point
CONTROL_POINTS = [(0.0, MLC_A), (0.5, MLC_A), (0.5, MLC_B), (1.0, MLC_B)]
# (Beam Number, Gantry Angle, Beam Meterset)
BEAMS = [(1, 0.0, 100.0), (2, 90.0, 50.0)]

# PS3.3 C.8.8.14.1: meterset = Beam Meterset * Cumulative Meterset Weight
# / Final Cumulative Meterset Weight, so 0, 50, 50, 100 MU and then
# 0, 25, 25, 50 MU, which a Delivery accumulates across the beams.
EXPECTED_MU = [0.0, 50.0, 50.0, 100.0, 100.0, 125.0, 125.0, 150.0]


def _item(**elements):
    item = pydicom.Dataset()
    for keyword, value in elements.items():
        setattr(item, keyword, value)

    return item


def _template(final_weight=1.0, device_order=("ASYMY", "MLCX"), later_devices=None):
    """Return a two-beam RT Plan template.

    ``device_order`` orders the beam limiting devices in each beam and in
    its first control point. ``later_devices`` lists the devices that
    control points after the first include, by default all of them.
    Each control point also has a Cumulative Dose Reference Coefficient,
    rising from 0 to 1 with the meterset.
    """
    if later_devices is None:
        later_devices = device_order

    beams = []
    for number, gantry_angle, _ in BEAMS:
        control_points = []
        for index, (fraction, mlc) in enumerate(CONTROL_POINTS):
            positions = {"ASYMY": JAW, "MLCX": mlc}
            devices = device_order if index == 0 else later_devices

            control_point = _item(
                ControlPointIndex=index,
                CumulativeMetersetWeight=fraction * final_weight,
                ReferencedDoseReferenceSequence=[
                    _item(
                        ReferencedDoseReferenceNumber=1,
                        CumulativeDoseReferenceCoefficient=fraction,
                    )
                ],
            )
            if devices:
                control_point.BeamLimitingDevicePositionSequence = [
                    _item(
                        RTBeamLimitingDeviceType=device,
                        LeafJawPositions=positions[device],
                    )
                    for device in devices
                ]
            if index == 0:
                control_point.GantryAngle = gantry_angle
                control_point.BeamLimitingDeviceAngle = 0.0

            control_points.append(control_point)

        device_definitions = {
            "ASYMY": _item(RTBeamLimitingDeviceType="ASYMY", NumberOfLeafJawPairs=1),
            "MLCX": _item(
                RTBeamLimitingDeviceType="MLCX",
                NumberOfLeafJawPairs=4,
                LeafPositionBoundaries=[-20.0, -10.0, 0.0, 10.0, 20.0],
            ),
        }
        beams.append(
            _item(
                BeamNumber=number,
                FinalCumulativeMetersetWeight=final_weight,
                NumberOfControlPoints=len(control_points),
                ControlPointSequence=control_points,
                BeamLimitingDeviceSequence=[
                    device_definitions[device] for device in device_order
                ],
            )
        )

    referenced_beams = [
        _item(ReferencedBeamNumber=number, BeamMeterset=meterset)
        for number, _, meterset in BEAMS
    ]

    return _item(
        BeamSequence=beams,
        FractionGroupSequence=[
            _item(
                FractionGroupNumber=1,
                NumberOfBeams=len(BEAMS),
                ReferencedBeamSequence=referenced_beams,
            )
        ],
    )


def _positions_by_device(control_point):
    return {
        item.RTBeamLimitingDeviceType: [float(value) for value in item.LeafJawPositions]
        for item in control_point.BeamLimitingDevicePositionSequence
    }


def _assert_positions_match_the_template(written):
    for beam in written.BeamSequence:
        for control_point, (_, mlc) in zip(
            beam.ControlPointSequence, CONTROL_POINTS, strict=True
        ):
            assert len(control_point.BeamLimitingDevicePositionSequence) == 2
            assert _positions_by_device(control_point) == {"ASYMY": JAW, "MLCX": mlc}


def _assert_reads_back_as(written, delivery):
    read_back = pymedphys.Delivery.from_dicom(written)

    np.testing.assert_allclose(read_back.mu, EXPECTED_MU)
    np.testing.assert_allclose(read_back.jaw, delivery.jaw)
    np.testing.assert_allclose(read_back.mlc, delivery.mlc)


@pytest.mark.parametrize("final_weight", [1.0, 100.0])
def test_weights_are_written_on_the_template_beams_scale(final_weight):
    template = _template(final_weight=final_weight)
    delivery = pymedphys.Delivery.from_dicom(template)
    np.testing.assert_allclose(delivery.mu, EXPECTED_MU)

    written = delivery.to_dicom(template)

    for beam in written.BeamSequence:
        weights = [
            float(control_point.CumulativeMetersetWeight)
            for control_point in beam.ControlPointSequence
        ]
        assert weights == [fraction * final_weight for fraction, _ in CONTROL_POINTS]
        # PS3.3 C.8.8.14: the final control point's weight equals the
        # beam's Final Cumulative Meterset Weight.
        assert weights[-1] == float(beam.FinalCumulativeMetersetWeight)

    _assert_reads_back_as(written, delivery)


def test_a_template_beam_without_a_final_weight_is_given_one():
    delivery = pymedphys.Delivery.from_dicom(_template())

    # As exported before the plan's dose was calculated.
    template = _template()
    for beam in template.BeamSequence:
        del beam.FinalCumulativeMetersetWeight
        for control_point in beam.ControlPointSequence:
            control_point.CumulativeMetersetWeight = None

    written = delivery.to_dicom(template)

    for beam in written.BeamSequence:
        assert float(beam.FinalCumulativeMetersetWeight) == 1.0
        assert float(beam.ControlPointSequence[-1].CumulativeMetersetWeight) == 1.0

    _assert_reads_back_as(written, delivery)


def test_dose_reference_coefficients_are_not_copied_between_control_points():
    template = _template()

    written = pymedphys.Delivery.from_dicom(template).to_dicom(template)

    for beam in written.BeamSequence:
        references = [
            [
                (
                    int(reference.ReferencedDoseReferenceNumber),
                    reference.CumulativeDoseReferenceCoefficient,
                )
                for reference in control_point.ReferencedDoseReferenceSequence
            ]
            for control_point in beam.ControlPointSequence
        ]
        # The coefficients come from the dose the planning system
        # calculated for the template, which a Delivery does not record,
        # so they are left empty. PS3.3 C.8.8.14.7 defines the first
        # control point's coefficient as zero.
        assert references == [[(1, 0.0)], [(1, None)], [(1, None)], [(1, None)]]


def test_positions_are_written_to_the_item_of_their_device_type():
    template = _template(device_order=("MLCX", "ASYMY"))
    delivery = pymedphys.Delivery.from_dicom(template)

    written = delivery.to_dicom(template)

    _assert_positions_match_the_template(written)
    _assert_reads_back_as(written, delivery)


@pytest.mark.parametrize(
    "later_devices", [("MLCX",), ()], ids=["only-mlc-after-first", "none-after-first"]
)
def test_devices_left_out_of_later_template_control_points_are_written(
    later_devices,
):
    delivery = pymedphys.Delivery.from_dicom(_template())

    # After the first control point, PS3.3 C.8.8.14 lists only the
    # devices that move during the beam, and no device when none moves.
    template = _template(later_devices=later_devices)

    written = delivery.to_dicom(template)

    _assert_positions_match_the_template(written)
    _assert_reads_back_as(written, delivery)


def test_template_beams_must_define_the_jaws_and_mlc_that_are_written():
    delivery = pymedphys.Delivery.from_dicom(_template())

    template = _template()
    for beam in template.BeamSequence:
        beam.BeamLimitingDeviceSequence = [
            device
            for device in beam.BeamLimitingDeviceSequence
            if device.RTBeamLimitingDeviceType == "MLCX"
        ]

    with pytest.raises(ValueError, match="one ASYMY and one MLCX"):
        delivery.to_dicom(template)
