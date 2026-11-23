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


# pylint: disable = redefined-outer-name

from pymedphys._imports import pydicom, pytest

import pymedphys
from pymedphys._dicom import create

# Leaf/Jaw Positions (mm) at each of three control points: Y1 then Y2 for
# the ASYMY jaws, and bank 1 then bank 2 of two leaf pairs for the MLCX.
POSITIONS = {
    "ASYMY": ([-50.0, 60.0], [-40.0, 70.0], [-30.0, 80.0]),
    "MLCX": (
        [-1.0, -2.0, 11.0, 12.0],
        [-3.0, -4.0, 13.0, 14.0],
        [-5.0, -6.0, 15.0, 16.0],
    ),
}


@pytest.fixture
def dataset():
    path = pymedphys.zip_data_paths("dicom-to-delivery-issue-#1047.zip")[0]

    return pydicom.dcmread(path)


def test_converting_dicom_to_delivery(dataset):
    with pytest.raises(ValueError, match=r".*not yet supported.*"):
        pymedphys.Delivery.from_dicom(dataset)


@pytest.mark.parametrize(
    "static_device, moving_device, field, expected",
    [
        # Delivery gives the jaws as (Y2, -Y1).
        pytest.param("ASYMY", "MLCX", "jaw", (60.0, 50.0), id="static-jaws"),
        # Delivery gives the leaf pairs in reverse order, each as
        # (bank 2, -bank 1).
        pytest.param(
            "MLCX", "ASYMY", "mlc", ((12.0, 2.0), (11.0, 1.0)), id="static-leaves"
        ),
    ],
)
def test_static_device_listed_only_at_first_control_point(
    static_device, moving_device, field, expected
):
    # PS3.3 C.8.8.14: the first control point lists every beam limiting
    # device, and later control points list only those whose positions
    # change during the beam. Repeating a static device at every control
    # point describes the same beam.
    static_positions = POSITIONS[static_device][0]
    listed_at_every_control_point = [
        {static_device: static_positions, moving_device: moving_positions}
        for moving_positions in POSITIONS[moving_device]
    ]
    listed_at_first_control_point_only = listed_at_every_control_point[:1] + [
        {moving_device: moving_positions}
        for moving_positions in POSITIONS[moving_device][1:]
    ]

    sparse = pymedphys.Delivery.from_dicom(_plan(listed_at_first_control_point_only))
    repeated = pymedphys.Delivery.from_dicom(_plan(listed_at_every_control_point))

    assert sparse == repeated
    assert getattr(sparse, field) == (expected,) * 3


@pytest.mark.parametrize(
    "later_control_point, message",
    [
        pytest.param({}, "control point 1, counting from 0, is empty", id="empty-list"),
        pytest.param(
            {"ASYMX": [-30.0, 30.0]},
            "Control point 1, counting from 0, leaves out .* does not define",
            id="only-an-undefined-device",
        ),
        pytest.param(
            {"MLCX": POSITIONS["MLCX"][1], "ASYMX": [-30.0, 30.0]},
            "Control point 1, counting from 0, leaves out .* does not define",
            id="leaves-and-an-undefined-device",
        ),
    ],
)
def test_control_point_that_does_not_list_the_beams_devices_raises(
    later_control_point, message
):
    # Leaving a device out of a later control point says that it does not
    # move (PS3.3 C.8.8.14). An empty list, or a list with a device that
    # the beam does not define, does not say that, so it is not read as
    # "nothing moved". The message names the control point, the second of
    # the three.
    every_device = {device: positions[0] for device, positions in POSITIONS.items()}
    plan = _plan([every_device, later_control_point, every_device])

    with pytest.raises(ValueError, match=message):
        pymedphys.Delivery.from_dicom(plan)


def test_other_device_beside_both_of_the_beams_devices_is_ignored():
    # A control point that lists both of the beam's devices is read as it
    # always was, whatever else it lists.
    every_device = [
        {device: positions[index] for device, positions in POSITIONS.items()}
        for index in range(3)
    ]
    with_another_device = [
        {**positions_by_device, "ASYMX": [-30.0, 30.0]}
        for positions_by_device in every_device
    ]

    assert pymedphys.Delivery.from_dicom(
        _plan(with_another_device)
    ) == pymedphys.Delivery.from_dicom(_plan(every_device))


def _plan(positions_by_control_point):
    """Return a one-beam RT Plan collimated by ASYMY jaws and MLCX leaves.

    Each control point lists the devices in its dictionary, which maps
    RT Beam Limiting Device Type to Leaf/Jaw Positions.
    """
    control_points = [
        {
            "ControlPointIndex": index,
            "CumulativeMetersetWeight": float(index),
            "BeamLimitingDevicePositionSequence": [
                {"RTBeamLimitingDeviceType": device, "LeafJawPositions": positions}
                for device, positions in positions_by_device.items()
            ],
        }
        for index, positions_by_device in enumerate(positions_by_control_point)
    ]
    control_points[0]["GantryAngle"] = 0.0
    control_points[0]["BeamLimitingDeviceAngle"] = 0.0

    return create.dicom_dataset_from_dict(
        {
            "BeamSequence": [
                {
                    "BeamNumber": 1,
                    "FinalCumulativeMetersetWeight": float(len(control_points) - 1),
                    "NumberOfControlPoints": len(control_points),
                    "BeamLimitingDeviceSequence": [
                        {
                            "RTBeamLimitingDeviceType": "ASYMY",
                            "NumberOfLeafJawPairs": 1,
                        },
                        {
                            "RTBeamLimitingDeviceType": "MLCX",
                            "NumberOfLeafJawPairs": 2,
                            "LeafPositionBoundaries": [-10.0, 0.0, 10.0],
                        },
                    ],
                    "ControlPointSequence": control_points,
                }
            ],
            "FractionGroupSequence": [
                {
                    "FractionGroupNumber": 1,
                    "NumberOfBeams": 1,
                    "ReferencedBeamSequence": [
                        {"ReferencedBeamNumber": 1, "BeamMeterset": 100.0}
                    ],
                }
            ],
        }
    )
