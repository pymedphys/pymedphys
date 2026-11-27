# Copyright (C) 2026 Chen-Yang Su

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Gantry-angle masking across the +/-180 degree wraparound boundary."""

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

import pymedphys
from pymedphys._dicom.delivery import utilities


def _simple_beam_delivery(gantry_angles, mu):
    """Build a delivery with a fixed rectangular MLC opening."""
    n_cp = len(gantry_angles)
    collimator = np.zeros(n_cp)
    mlc = np.zeros((n_cp, 80, 2))
    mlc[:, 35:45, 0] = 20.0
    mlc[:, 35:45, 1] = 20.0
    jaw = np.full((n_cp, 2), 50.0)
    return pymedphys.Delivery(mu, gantry_angles, collimator, mlc, jaw)


def _item(**elements):
    item = pydicom.Dataset()
    for keyword, value in elements.items():
        setattr(item, keyword, value)
    return item


def _two_beam_plan(metersets, gantry_angles=(0.0, 180.0)):
    """Return a two-beam step-and-shoot RT Plan, by default at gantry 0 and 180 degrees."""
    jaw = [-50.0, 60.0]
    control_point_specs = [
        (0.0, [-5.0, -6.0, -7.0, -8.0, 5.0, 6.0, 7.0, 8.0]),
        (0.5, [-5.0, -6.0, -7.0, -8.0, 5.0, 6.0, 7.0, 8.0]),
        (0.5, [-15.0, -16.0, -17.0, -18.0, 15.0, 16.0, 17.0, 18.0]),
        (1.0, [-15.0, -16.0, -17.0, -18.0, 15.0, 16.0, 17.0, 18.0]),
    ]
    beams = []
    for beam_number, gantry_angle in zip([1, 2], gantry_angles, strict=True):
        control_points = []
        for index, (weight, mlc) in enumerate(control_point_specs):
            cp = _item(
                ControlPointIndex=index,
                CumulativeMetersetWeight=weight,
                BeamLimitingDevicePositionSequence=[
                    _item(RTBeamLimitingDeviceType="ASYMY", LeafJawPositions=jaw),
                    _item(RTBeamLimitingDeviceType="MLCX", LeafJawPositions=mlc),
                ],
            )
            if index == 0:
                cp.GantryAngle = gantry_angle
                cp.BeamLimitingDeviceAngle = 0.0
            control_points.append(cp)

        beams.append(
            _item(
                BeamNumber=beam_number,
                FinalCumulativeMetersetWeight=1.0,
                NumberOfControlPoints=len(control_points),
                ControlPointSequence=control_points,
                BeamLimitingDeviceSequence=[
                    _item(RTBeamLimitingDeviceType="ASYMY", NumberOfLeafJawPairs=1),
                    _item(
                        RTBeamLimitingDeviceType="MLCX",
                        NumberOfLeafJawPairs=4,
                        LeafPositionBoundaries=[-20.0, -10.0, 0.0, 10.0, 20.0],
                    ),
                ],
            )
        )

    referenced_beams = [
        _item(ReferencedBeamNumber=beam_number, BeamMeterset=meterset)
        for beam_number, meterset in zip([1, 2], metersets, strict=True)
    ]

    return _item(
        BeamSequence=beams,
        FractionGroupSequence=[
            _item(
                FractionGroupNumber=1,
                NumberOfBeams=2,
                ReferencedBeamSequence=referenced_beams,
            )
        ],
    )


@pytest.mark.parametrize("pa_target", [180.0, -180.0])
@pytest.mark.parametrize(
    "pa_measured",
    [
        [179.9, -179.9],
        [-179.9, 179.9],
        [179.9, -179.9, 179.9],
    ],
)
def test_metersetmap_handles_gantry_crossing_180_boundary(pa_target, pa_measured):
    n_pa = len(pa_measured)
    mu = np.concatenate(([0.0, 10.0], np.linspace(10.0, 25.0, n_pa)))
    gantry = np.concatenate(([0.0, 0.1], pa_measured))

    delivery = _simple_beam_delivery(gantry, mu)
    reference_pa = _simple_beam_delivery(np.zeros(n_pa), np.linspace(0.0, 15.0, n_pa))

    ap_map, pa_map = delivery.metersetmap(gantry_angles=[0.0, pa_target])
    expected_pa_map = reference_pa.metersetmap(gantry_angles=[0.0])

    np.testing.assert_allclose(pa_map, expected_pa_map)
    assert np.max(ap_map) > 0


def test_to_dicom_handles_pa_beam_crossing_180_boundary():
    template = _two_beam_plan(metersets=[100.0, 50.0])
    delivered = pymedphys.Delivery.from_dicom(_two_beam_plan(metersets=[80.0, 40.0]))

    # Simulate linac gantry drift across the +/-180 degree boundary during the PA beam.
    drifted_gantry = np.array([0.0, 0.0, 0.1, 0.1, 179.9, 179.9, -179.9, -179.9])
    drifted_delivery = pymedphys.Delivery(
        delivered.monitor_units,
        drifted_gantry,
        delivered.collimator,
        delivered.mlc,
        delivered.jaw,
    )

    written = drifted_delivery.to_dicom(template)

    referenced = written.FractionGroupSequence[0].ReferencedBeamSequence
    assert [float(beam.BeamMeterset) for beam in referenced] == [80.0, 40.0]

    pa_beam = written.BeamSequence[1]
    assert len(pa_beam.ControlPointSequence) == 4
    pa_angles = [float(cp.GantryAngle) for cp in pa_beam.ControlPointSequence]
    np.testing.assert_allclose(pa_angles, [179.9, 179.9, 180.1, 180.1])


@pytest.mark.parametrize(
    ("pa_gantry", "expected_directions"),
    [
        # Clockwise drift (DICOM 179.9 to 180.1 degrees) between control
        # points with the same meterset, then while 20 MU are delivered.
        ([179.9, 179.9, -179.9, -179.9], ["NONE", "CW", "NONE", "NONE"]),
        ([179.9, -179.9, -179.9, -179.9], ["CW", "NONE", "NONE", "NONE"]),
        # Counter-clockwise drift (DICOM 180.1 to 179.9 degrees), likewise.
        ([-179.9, -179.9, 179.9, 179.9], ["NONE", "CC", "NONE", "NONE"]),
        ([-179.9, -179.9, -179.9, 179.9], ["NONE", "NONE", "CC", "NONE"]),
    ],
)
def test_to_dicom_writes_short_way_rotation_across_180_boundary(
    pa_gantry, expected_directions
):
    template = _two_beam_plan(metersets=[100.0, 50.0])
    delivered = pymedphys.Delivery.from_dicom(_two_beam_plan(metersets=[80.0, 40.0]))
    drifted_delivery = pymedphys.Delivery(
        delivered.monitor_units,
        np.concatenate(([0.0, 0.0, 0.1, 0.1], pa_gantry)),
        delivered.collimator,
        delivered.mlc,
        delivered.jaw,
    )

    written = drifted_delivery.to_dicom(template)

    ap_beam, pa_beam = written.BeamSequence
    ap_directions = [cp.GantryRotationDirection for cp in ap_beam.ControlPointSequence]
    pa_directions = [cp.GantryRotationDirection for cp in pa_beam.ControlPointSequence]
    assert ap_directions == ["NONE", "CW", "NONE", "NONE"]
    assert pa_directions == expected_directions


def test_to_dicom_keeps_neighbouring_beams_across_180_boundary_separate():
    template = _two_beam_plan(metersets=[100.0, 50.0], gantry_angles=(179.0, 181.0))
    delivered = pymedphys.Delivery.from_dicom(
        _two_beam_plan(metersets=[80.0, 40.0], gantry_angles=(179.0, 181.0))
    )

    written = delivered.to_dicom(template)

    referenced = written.FractionGroupSequence[0].ReferencedBeamSequence
    assert [float(beam.BeamMeterset) for beam in referenced] == [80.0, 40.0]
    for beam, gantry_angle in zip(written.BeamSequence, [179.0, 181.0], strict=True):
        control_points = beam.ControlPointSequence
        assert [float(cp.GantryAngle) for cp in control_points] == [gantry_angle] * 4
        assert [float(cp.CumulativeMetersetWeight) for cp in control_points] == [
            0.0,
            0.5,
            0.5,
            1.0,
        ]


@pytest.mark.parametrize(
    ("gantry_angles", "expected"),
    [
        # Half the spacing on the circle, less 0.1 degrees, capped at 3.
        ((179.0, -179.0), 0.9),
        ((-179.0, 180.0), 0.4),
        ((0.0, 2.0), 0.9),
        ((0.0, 180.0), 3.0),
    ],
)
def test_gantry_tolerance_uses_circular_beam_spacing(gantry_angles, expected):
    tolerance = utilities.gantry_tol_from_gantry_angles(gantry_angles)

    assert tolerance == pytest.approx(expected)


@pytest.mark.parametrize(
    ("target", "measured", "tol", "expected"),
    [
        (180.0, -177.0, 3.0, True),
        (180.0, -176.9, 3.0, False),
        (-180.0, 177.0, 3.0, True),
        (-180.0, 176.9, 3.0, False),
        (0.3, 0.0, 0.3, True),
    ],
)
def test_gantry_angle_mask_exact_tolerance_boundaries(target, measured, tol, expected):
    delivery = _simple_beam_delivery(
        np.array([measured, measured]), np.array([0.0, 5.0])
    )
    mask = delivery._gantry_angle_mask(target, tol)  # pylint: disable=protected-access
    assert bool(np.all(mask)) is expected
