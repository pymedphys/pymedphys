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

Each plan has two step-and-shoot beams, at gantry 0 and 90 degrees, with
four control points each. The leaves move between the second and third.

The delivery is read from one plan and written into another, the
template. The two differ in their Beam Metersets, in the meterset
reached at the middle control points and in every jaw and leaf position,
so that what is written can only have come from the delivery.
"""

from decimal import Decimal

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

import pymedphys
from pymedphys._dicom.rtplan import build

# (Beam Number, Gantry Angle)
BEAMS = [(1, 0.0), (2, 90.0)]

# For each plan: the Beam Meterset of each beam, the ASYMY positions, and
# the fraction of a beam's meterset reached at each of its control points
# with the MLCX positions there. Positions are Leaf/Jaw Positions in mm.
TEMPLATE = {
    "metersets": [100.0, 50.0],
    "jaw": [-50.0, 60.0],
    "control_points": [
        (0.0, [-5.0, -6.0, -7.0, -8.0, 5.0, 6.0, 7.0, 8.0]),
        (0.5, [-5.0, -6.0, -7.0, -8.0, 5.0, 6.0, 7.0, 8.0]),
        (0.5, [-15.0, -16.0, -17.0, -18.0, 15.0, 16.0, 17.0, 18.0]),
        (1.0, [-15.0, -16.0, -17.0, -18.0, 15.0, 16.0, 17.0, 18.0]),
    ],
}
DELIVERED = {
    "metersets": [80.0, 30.0],
    "jaw": [-42.5, 68.75],
    "control_points": [
        (0.0, [-9.0, -4.25, -1.5, -0.5, 12.5, 17.75, 28.0, 3.25]),
        (0.2468, [-9.0, -4.25, -1.5, -0.5, 12.5, 17.75, 28.0, 3.25]),
        (0.2468, [-19.0, -14.25, -11.5, -10.5, 2.5, 7.75, 8.0, 13.25]),
        (1.0, [-19.0, -14.25, -11.5, -10.5, 2.5, 7.75, 8.0, 13.25]),
    ],
}

# The delivery's meterset at each control point of each beam, worked out
# by hand: 0.2468 of 80 MU and of 30 MU at the middle control points.
DELIVERED_METERSETS = [[0.0, 19.744, 19.744, 80.0], [0.0, 7.404, 7.404, 30.0]]
# A Delivery accumulates the monitor units across the beams.
DELIVERED_MONITOR_UNITS = [0.0, 19.744, 19.744, 80.0, 80.0, 87.404, 87.404, 110.0]

# A weight is written to within a millionth of the beam's Final Cumulative
# Meterset Weight, and so a control point's meterset to within a millionth
# of the Beam Meterset.
A_MILLIONTH = 1e-6


def _item(**elements):
    item = pydicom.Dataset()
    for keyword, value in elements.items():
        setattr(item, keyword, value)

    return item


def _plan(values, final_weight=1.0, device_order=("ASYMY", "MLCX"), later_devices=None):
    """Return a two-beam RT Plan holding ``values``.

    ``final_weight`` is each beam's Final Cumulative Meterset Weight,
    the scale of its Cumulative Meterset Weights. ``device_order``
    orders the beam limiting devices in each beam and in its first
    control point. ``later_devices`` lists the devices that control
    points after the first include, by default all of them. Each control
    point also has a Cumulative Dose Reference Coefficient, rising from
    0 to 1 with the meterset.
    """
    if later_devices is None:
        later_devices = device_order

    beams = []
    for number, gantry_angle in BEAMS:
        control_points = []
        for index, (fraction, mlc) in enumerate(values["control_points"]):
            positions = {"ASYMY": values["jaw"], "MLCX": mlc}
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
        for (number, _), meterset in zip(BEAMS, values["metersets"], strict=True)
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


def _delivery():
    delivery = pymedphys.Delivery.from_dicom(_plan(DELIVERED))
    np.testing.assert_allclose(delivery.mu, DELIVERED_MONITOR_UNITS)

    return delivery


def _metersets(written):
    """Return the meterset at each control point of each beam.

    PS3.3 C.8.8.14.1: the Beam Meterset times the Cumulative Meterset
    Weight over the Final Cumulative Meterset Weight, here in decimal
    arithmetic from the values as they are written.
    """
    referenced_beams = written.FractionGroupSequence[0].ReferencedBeamSequence

    return [
        [
            float(
                Decimal(str(referenced_beam.BeamMeterset))
                * Decimal(str(control_point.CumulativeMetersetWeight))
                / Decimal(str(beam.FinalCumulativeMetersetWeight))
            )
            for control_point in beam.ControlPointSequence
        ]
        for beam, referenced_beam in zip(
            written.BeamSequence, referenced_beams, strict=True
        )
    ]


def _assert_metersets_are_the_deliverys(written):
    referenced_beams = written.FractionGroupSequence[0].ReferencedBeamSequence
    assert [float(beam.BeamMeterset) for beam in referenced_beams] == [80.0, 30.0]

    for metersets, expected in zip(
        _metersets(written), DELIVERED_METERSETS, strict=True
    ):
        np.testing.assert_allclose(
            metersets, expected, rtol=0, atol=A_MILLIONTH * expected[-1]
        )


def _positions_by_device(control_point):
    return {
        item.RTBeamLimitingDeviceType: [float(value) for value in item.LeafJawPositions]
        for item in control_point.BeamLimitingDevicePositionSequence
    }


def _assert_positions_are_the_deliverys(written):
    for beam in written.BeamSequence:
        for control_point, (_, mlc) in zip(
            beam.ControlPointSequence, DELIVERED["control_points"], strict=True
        ):
            assert len(control_point.BeamLimitingDevicePositionSequence) == 2
            assert _positions_by_device(control_point) == {
                "ASYMY": DELIVERED["jaw"],
                "MLCX": mlc,
            }


def _assert_reads_back_as(written, delivery):
    read_back = pymedphys.Delivery.from_dicom(written)

    np.testing.assert_allclose(
        read_back.mu, DELIVERED_MONITOR_UNITS, rtol=0, atol=A_MILLIONTH * 80.0
    )
    np.testing.assert_array_equal(read_back.jaw, delivery.jaw)
    np.testing.assert_array_equal(read_back.mlc, delivery.mlc)


@pytest.mark.parametrize(
    "final_weight, weights",
    [
        # Six decimal places, as for every template before.
        (1.0, ["0.000000", "0.246800", "0.246800", "1.000000"]),
        (100.0, ["0.000000", "24.680000", "24.680000", "100.000000"]),
        # One more decimal place for each power of ten below 1.
        (0.0001, ["0.0000000000", "0.0000246800", "0.0000246800", "0.0001000000"]),
        (
            1e-7,
            [
                "0.0000000000000",
                "0.0000000246800",
                "0.0000000246800",
                "0.0000001000000",
            ],
        ),
        # A final weight that seven decimal places cannot hold is itself
        # the weight at the end of the beam.
        (0.123456789, ["0.0000000", "0.0304691", "0.0304691", "0.123456789"]),
        # Where the decimal places do not fit the 16 characters of a
        # Decimal String, the weight has seven significant figures.
        (1e-10, ["0.000000E+00", "2.468000E-11", "2.468000E-11", "1.000000E-10"]),
        (2.5e9, ["0.000000", "617000000.000000", "617000000.000000", "2.500000E+09"]),
        # Towards the ends of what a float holds. At 1E308 the meterset
        # read back overflowed where it multiplied before it divided.
        (1e-307, ["0.000000E+00", "2.468000E-308", "2.468000E-308", "1.000000E-307"]),
        (1e303, ["0.000000", "2.468000E+302", "2.468000E+302", "1.000000E+303"]),
        (1e308, ["0.000000", "2.468000E+307", "2.468000E+307", "1.000000E+308"]),
    ],
)
def test_metersets_are_the_deliverys_on_any_template_weight_scale(
    final_weight, weights
):
    template = _plan(TEMPLATE, final_weight=final_weight)
    delivery = _delivery()

    written = delivery.to_dicom(template)

    _assert_metersets_are_the_deliverys(written)
    for beam in written.BeamSequence:
        control_points = beam.ControlPointSequence
        assert [
            str(control_point.CumulativeMetersetWeight)
            for control_point in control_points
        ] == weights
        # PS3.3 C.8.8.14: the final control point's weight equals the
        # beam's Final Cumulative Meterset Weight, which stays the
        # template's.
        assert float(beam.FinalCumulativeMetersetWeight) == final_weight
        assert float(control_points[-1].CumulativeMetersetWeight) == final_weight

    _assert_reads_back_as(written, delivery)


@pytest.mark.parametrize(
    "final_weight, weight",
    [
        (1.0, "0.666667"),
        (100.0, "66.666667"),
        (0.0001, "0.0000666667"),
        (1e-10, "6.666667E-11"),
        (2.5e9, "1.666667E+09"),
        (1e-307, "6.666667E-308"),
        (1e303, "6.666667E+302"),
    ],
)
def test_weights_are_rounded_to_within_a_millionth_of_the_final_weight(
    final_weight, weight
):
    # Two thirds of the beam's meterset, which no number of decimal places
    # holds exactly.
    written = build._cumulative_meterset_weight(  # pylint: disable = protected-access
        [0.0, 200.0, 300.0], 1, final_weight
    )

    assert written == weight
    exact = 2 * Decimal(repr(final_weight)) / 3
    assert abs(Decimal(written) - exact) <= Decimal(repr(final_weight)) * Decimal(
        repr(A_MILLIONTH)
    )


def test_the_last_weight_is_the_final_weight_as_a_decimal():
    # A valid 16-character Decimal String that a float does not hold: as
    # a float it is 9999990000000000, which 9.999990E+15 also is.
    final_weight = "9999990000000001"
    template = _plan(TEMPLATE, final_weight=float(final_weight))
    for beam in template.BeamSequence:
        beam.FinalCumulativeMetersetWeight = final_weight
    delivery = _delivery()

    written = delivery.to_dicom(template)

    for beam in written.BeamSequence:
        assert str(beam.FinalCumulativeMetersetWeight) == final_weight
        last_weight = beam.ControlPointSequence[-1].CumulativeMetersetWeight
        assert Decimal(str(last_weight)) == Decimal(final_weight)

    _assert_metersets_are_the_deliverys(written)
    _assert_reads_back_as(written, delivery)


def test_rounding_does_not_carry_a_weight_past_the_final_weight():
    # 99.999999 of 100 MU on a scale of 0.123456789 is 0.12345678777,
    # which seven decimal places round up to 0.1234568, more than the
    # final weight.
    weight = build._cumulative_meterset_weight(  # pylint: disable = protected-access
        [0.0, 99.999999, 100.0], 1, 0.123456789
    )

    assert float(weight) == 0.123456789


def test_a_template_beam_without_a_final_weight_is_given_one():
    delivery = _delivery()

    # As exported before the plan's dose was calculated.
    template = _plan(TEMPLATE)
    for beam in template.BeamSequence:
        del beam.FinalCumulativeMetersetWeight
        for control_point in beam.ControlPointSequence:
            control_point.CumulativeMetersetWeight = None

    written = delivery.to_dicom(template)

    for beam in written.BeamSequence:
        assert float(beam.FinalCumulativeMetersetWeight) == 1.0
        assert float(beam.ControlPointSequence[-1].CumulativeMetersetWeight) == 1.0

    _assert_metersets_are_the_deliverys(written)
    _assert_reads_back_as(written, delivery)


@pytest.mark.parametrize(
    "final_weight", [0.0, -100.0, float("inf"), float("nan"), 1e-320]
)
def test_template_beams_need_a_positive_finite_final_weight(final_weight):
    # A control point's meterset is its weight over the final weight, so
    # no weights on these scales give the delivery's metersets. The last
    # is below the smallest float with full precision.
    template = _plan(TEMPLATE, final_weight=final_weight)

    with pytest.raises(ValueError, match="positive, finite number"):
        _delivery().to_dicom(template)


def test_dose_reference_coefficients_are_not_copied_between_control_points():
    template = _plan(TEMPLATE)

    written = _delivery().to_dicom(template)

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


@pytest.mark.parametrize(
    "device_order, later_devices",
    [
        pytest.param(("ASYMY", "MLCX"), None, id="jaws-listed-first"),
        pytest.param(("MLCX", "ASYMY"), None, id="leaves-listed-first"),
        # After the first control point, PS3.3 C.8.8.14 lists only the
        # devices that move during the beam, and no device when none
        # moves.
        pytest.param(("ASYMY", "MLCX"), ("MLCX",), id="only-leaves-after-first"),
        pytest.param(("ASYMY", "MLCX"), (), id="no-device-after-first"),
    ],
)
def test_positions_are_written_to_the_item_of_their_device_type(
    device_order, later_devices
):
    template = _plan(TEMPLATE, device_order=device_order, later_devices=later_devices)
    delivery = _delivery()

    written = delivery.to_dicom(template)

    _assert_positions_are_the_deliverys(written)
    _assert_metersets_are_the_deliverys(written)
    _assert_reads_back_as(written, delivery)


@pytest.mark.parametrize("defined_devices", [("MLCX",), ()], ids=["no-jaws", "none"])
def test_template_beams_must_define_the_jaws_and_mlc_that_are_written(
    defined_devices,
):
    template = _plan(TEMPLATE)
    for beam in template.BeamSequence:
        beam.BeamLimitingDeviceSequence = [
            device
            for device in beam.BeamLimitingDeviceSequence
            if device.RTBeamLimitingDeviceType in defined_devices
        ]

    with pytest.raises(ValueError, match="one ASYMY and one MLCX"):
        _delivery().to_dicom(template)


def test_template_beams_without_device_definitions_raise_the_same_error():
    template = _plan(TEMPLATE)
    for beam in template.BeamSequence:
        del beam.BeamLimitingDeviceSequence

    with pytest.raises(ValueError, match="one ASYMY and one MLCX"):
        _delivery().to_dicom(template)
