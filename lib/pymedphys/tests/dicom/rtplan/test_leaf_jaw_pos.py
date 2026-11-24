# Copyright (C) 2026 Marchant Van der Walt
# Copyright (C) 2020 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from pymedphys._imports import pytest

from pymedphys._dicom import create, rtplan


def test_get_leaf_jaw_positions_for_type():
    rt_beam_limiting_device_type = "ASYMY"
    leaf_jaw_positions = [0, 0]

    expected_positions = [leaf_jaw_positions] * 4

    control_point_sequence = create.dicom_dataset_from_dict(
        {
            "ControlPointSequence": [
                {
                    "BeamLimitingDevicePositionSequence": [
                        {
                            "RTBeamLimitingDeviceType": rt_beam_limiting_device_type,
                            "LeafJawPositions": leaf_jaw_positions,
                        },
                        {
                            "RTBeamLimitingDeviceType": "ASYMX",
                            "LeafJawPositions": [1, 1],
                        },
                    ]
                },
                {},
                {},
                {},
            ]
        }
    ).ControlPointSequence

    beam_limiting_device_position_sequences = rtplan.get_cp_attribute_leaning_on_prior(
        control_point_sequence, "BeamLimitingDevicePositionSequence"
    )

    positions = rtplan.get_leaf_jaw_positions_for_type(
        beam_limiting_device_position_sequences, rt_beam_limiting_device_type
    )

    assert positions == expected_positions


def test_device_left_out_of_later_control_points_keeps_its_positions():
    # PS3.3 C.8.8.14: after the first control point, only the devices whose
    # positions change during the beam are listed.
    sequences = _position_sequences(
        [
            {"ASYMY": [-50, 60], "MLCX": [-1, 1]},
            {"MLCX": [-2, 2]},
            {"MLCX": [-3, 3]},
        ]
    )

    jaws = rtplan.get_leaf_jaw_positions_for_type(sequences, "ASYMY")
    leaves = rtplan.get_leaf_jaw_positions_for_type(sequences, "MLCX")

    assert jaws == [[-50, 60]] * 3
    assert leaves == [[-1, 1], [-2, 2], [-3, 3]]


def test_device_missing_from_first_control_point_raises():
    # The first control point must list every device, so there are no
    # positions to carry forward.
    sequences = _position_sequences(
        [
            {"MLCX": [-1, 1]},
            {"ASYMY": [-50, 60], "MLCX": [-2, 2]},
        ]
    )

    with pytest.raises(ValueError, match="exactly one item"):
        rtplan.get_leaf_jaw_positions_for_type(sequences, "ASYMY")


def _position_sequences(positions_by_control_point):
    control_point_sequence = create.dicom_dataset_from_dict(
        {
            "ControlPointSequence": [
                {
                    "BeamLimitingDevicePositionSequence": [
                        {
                            "RTBeamLimitingDeviceType": device,
                            "LeafJawPositions": positions,
                        }
                        for device, positions in positions_by_device.items()
                    ]
                }
                for positions_by_device in positions_by_control_point
            ]
        }
    ).ControlPointSequence

    return rtplan.get_cp_attribute_leaning_on_prior(
        control_point_sequence, "BeamLimitingDevicePositionSequence"
    )
