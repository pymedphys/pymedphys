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
