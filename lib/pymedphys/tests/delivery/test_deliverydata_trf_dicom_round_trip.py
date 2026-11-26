# Copyright (C) 2026 Marchant Van der Walt
# Copyright (C) 2019 Simon Biggs and Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from pymedphys._imports import numpy as np
from pymedphys._imports import plt, pydicom, pytest

import pymedphys
from pymedphys import Delivery
from pymedphys._dicom.create import dicom_dataset_from_dict
from pymedphys._dicom.rtplan import (
    convert_to_one_fraction_group,
    get_gantry_angles_from_dicom,
    get_metersets_from_dicom,
)
from pymedphys._utilities.algorithms import maintain_order_unique

# pylint: disable = redefined-outer-name, protected-access

DIR_TO_TEST_MAP = {
    "original": {"fraction_group": 1},
    "multi_fraction_groups": {"fraction_group": 2},
}

DIR_TO_TEST = "multi_fraction_groups"
FRACTION_GROUP = DIR_TO_TEST_MAP[DIR_TO_TEST]["fraction_group"]


def get_file_in_dir(directory, filename):
    all_paths = pymedphys.zip_data_paths("delivery_test_data.zip")
    filtered = [
        path
        for path in all_paths
        if path.parent.name == directory and path.name == filename
    ]

    assert len(filtered) == 1

    return str(filtered[0])


@pytest.fixture
def loaded_dicom_dataset():
    path = get_file_in_dir(DIR_TO_TEST, "rtplan.dcm")

    return pydicom.dcmread(path, force=True)


@pytest.fixture
def logfile_delivery_data():
    path = get_file_in_dir(DIR_TO_TEST, "imrt.trf")

    return Delivery.from_logfile(path)


@pytest.fixture
def loaded_dicom_gantry_angles(loaded_dicom_dataset):
    return get_gantry_angles_from_dicom(loaded_dicom_dataset)


@pytest.mark.slow
@pytest.mark.pydicom
def test_fraction_group_number(loaded_dicom_dataset, logfile_delivery_data: Delivery):
    expected = FRACTION_GROUP

    result = logfile_delivery_data._fraction_group_number(loaded_dicom_dataset)

    assert result == expected


@pytest.mark.slow
@pytest.mark.pydicom
def test_get_metersets_from_delivery_data(
    logfile_delivery_data, loaded_dicom_dataset, loaded_dicom_gantry_angles
):
    gantry_tol = 3
    expected = get_metersets_from_dicom(loaded_dicom_dataset, FRACTION_GROUP)

    filtered = logfile_delivery_data._filter_cps()
    metersets = filtered._metersets(loaded_dicom_gantry_angles, gantry_tol)

    try:
        assert np.all(np.abs(np.array(expected) - np.array(metersets)) <= 0.2)
    except AssertionError:
        print("\nIn DICOM file:\n   {}".format(expected))
        print("\nIn log file:\n   {}".format(metersets))
        raise


@pytest.mark.slow
@pytest.mark.pydicom
def test_filter_cps(logfile_delivery_data):
    logfile_delivery_data._filter_cps()

    for field in logfile_delivery_data._fields:
        assert len(getattr(logfile_delivery_data, field)) != 0


@pytest.mark.slow
@pytest.mark.pydicom
def test_round_trip_dd2dcm2dd(loaded_dicom_dataset, logfile_delivery_data: Delivery):
    original = logfile_delivery_data._filter_cps()
    template = loaded_dicom_dataset

    dicom = original.to_dicom(template)
    processed = Delivery.from_dicom(dicom, FRACTION_GROUP)

    assert np.all(
        np.around(original.monitor_units, 2) == np.around(processed.monitor_units, 2)
    )

    assert np.all(np.around(original.gantry, 2) == np.around(processed.gantry, 2))

    assert np.all(np.around(original.mlc, 2) == np.around(processed.mlc, 2))

    assert np.all(np.around(original.jaw, 2) == np.around(processed.jaw, 2))

    # Collimator not currently handled appropriately
    assert np.all(
        np.around(original.collimator, 2) == np.around(processed.collimator, 2)
    )


@pytest.mark.slow
@pytest.mark.pydicom
def test_round_trip_dcm2dd2dcm(loaded_dicom_dataset):
    original = loaded_dicom_dataset
    delivery_data = Delivery.from_dicom(original, FRACTION_GROUP)
    processed = delivery_data.to_dicom(original)

    single_fraction_group = convert_to_one_fraction_group(original, FRACTION_GROUP)

    original_gantry_angles = get_gantry_angles_from_dicom(single_fraction_group)

    assert num_of_control_points(single_fraction_group) == num_of_control_points(
        processed
    )

    assert maintain_order_unique(delivery_data.gantry) == original_gantry_angles

    processed_gantry_angles = get_gantry_angles_from_dicom(processed)

    assert original_gantry_angles == processed_gantry_angles

    assert source_to_surface_distances(
        single_fraction_group
    ) == source_to_surface_distances(processed)

    assert first_mlc_positions(single_fraction_group) == first_mlc_positions(processed)

    assert str(single_fraction_group) == str(processed)


@pytest.mark.pydicom
def test_to_dicom_with_single_beam_template():
    # The delivery differs from the template in meterset, and by half a
    # degree in gantry angle, so the beam written must be the delivery's.
    template = single_beam_plan(meterset=100.0, gantry_angle=90.0)
    delivered = Delivery.from_dicom(single_beam_plan(meterset=60.0, gantry_angle=90.5))

    dicom = delivered.to_dicom(template)

    (beam,) = dicom.BeamSequence
    (fraction_group,) = dicom.FractionGroupSequence
    (referenced_beam,) = fraction_group.ReferencedBeamSequence
    assert referenced_beam.ReferencedBeamNumber == beam.BeamNumber
    assert float(referenced_beam.BeamMeterset) == 60.0
    assert float(beam.ControlPointSequence[0].GantryAngle) == 90.5

    processed = Delivery.from_dicom(dicom)
    np.testing.assert_allclose(processed.monitor_units, [0.0, 30.0, 30.0, 60.0])
    for field in ("gantry", "collimator", "mlc", "jaw"):
        np.testing.assert_array_equal(
            getattr(processed, field), getattr(delivered, field)
        )


@pytest.mark.pydicom
@pytest.mark.parametrize("final_weight", [1.0, 100.0])
@pytest.mark.parametrize(
    "first_segment, expected_monitor_units",
    [
        # Two halves of 60 MU, as the template's segments are.
        (0.5, [0.0, 30.0, 30.0, 60.0]),
        # A quarter and three quarters, so that weights copied from the
        # template would give the wrong monitor units.
        (0.25, [0.0, 15.0, 15.0, 60.0]),
    ],
)
def test_single_beam_template_keeps_its_weight_scale(
    final_weight, first_segment, expected_monitor_units
):
    # A template that gives its weights as percentages has a Final
    # Cumulative Meterset Weight of 100. DICOM PS3.3 C.8.8.14.1 gives a
    # control point's meterset as the Beam Meterset times its Cumulative
    # Meterset Weight divided by the Final Cumulative Meterset Weight, and
    # the weight at the end of the beam equals that final weight.
    template = single_beam_plan(
        meterset=100.0, gantry_angle=90.0, final_weight=final_weight
    )
    delivered = Delivery.from_dicom(
        single_beam_plan(meterset=60.0, gantry_angle=90.5, first_segment=first_segment)
    )

    dicom = delivered.to_dicom(template)

    (beam,) = dicom.BeamSequence
    (referenced_beam,) = dicom.FractionGroupSequence[0].ReferencedBeamSequence
    beam_meterset = float(referenced_beam.BeamMeterset)
    final = float(beam.FinalCumulativeMetersetWeight)
    weights = [
        float(control_point.CumulativeMetersetWeight)
        for control_point in beam.ControlPointSequence
    ]
    assert final == final_weight
    assert weights[-1] == final
    np.testing.assert_allclose(
        [beam_meterset * weight / final for weight in weights],
        expected_monitor_units,
    )
    np.testing.assert_allclose(
        Delivery.from_dicom(dicom).monitor_units, expected_monitor_units
    )


@pytest.mark.slow
@pytest.mark.pydicom
def test_metersetmap_agreement(loaded_dicom_dataset, logfile_delivery_data):
    dicom_delivery_data = Delivery.from_dicom(loaded_dicom_dataset, FRACTION_GROUP)

    dicom_metersetmap = dicom_delivery_data.metersetmap(grid_resolution=5)
    logfile_metersetmap = logfile_delivery_data.metersetmap(grid_resolution=5)

    diff = logfile_metersetmap - dicom_metersetmap
    max_diff = np.max(np.abs(diff))
    std_diff = np.std(diff)
    try:
        assert max_diff < 4.1
        assert std_diff < 0.4
    except AssertionError:
        max_val = np.max([np.max(logfile_metersetmap), np.max(dicom_metersetmap)])

        plt.figure()
        plt.pcolormesh(dicom_metersetmap, vmin=0, vmax=max_val)
        plt.colorbar()

        plt.figure()
        plt.pcolormesh(logfile_metersetmap, vmin=0, vmax=max_val)
        plt.colorbar()

        plt.figure()
        plt.pcolormesh(
            logfile_metersetmap - dicom_metersetmap,
            vmin=-max_diff,
            vmax=max_diff,
            cmap="bwr",
        )
        plt.colorbar()
        plt.show()
        raise


def num_of_control_points(dicom_dataset):
    return [len(beam.ControlPointSequence) for beam in dicom_dataset.BeamSequence]


def source_to_surface_distances(dicom_dataset):
    SSDs = [
        {
            control_point.SourceToSurfaceDistance
            for control_point in beam_sequence.ControlPointSequence
        }
        for beam_sequence in dicom_dataset.BeamSequence
    ]

    return SSDs


def first_mlc_positions(dicom_dataset):
    result = [
        beam_sequence.ControlPointSequence[0]
        .BeamLimitingDevicePositionSequence[1]
        .LeafJawPositions
        for beam_sequence in dicom_dataset.BeamSequence
    ]

    return result


def single_beam_plan(meterset, gantry_angle, final_weight=1.0, first_segment=0.5):
    """An RT Plan with one static-gantry beam of two step-and-shoot
    segments, the first delivering the fraction ``first_segment`` of
    ``meterset`` and the second the rest, with Cumulative Meterset Weights
    on the scale of ``final_weight``."""
    jaw = [-50.0, 60.0]
    first_segment_mlc = [-5.0, -6.0, -7.0, -8.0, 15.0, 16.0, 17.0, 18.0]
    second_segment_mlc = [-25.0, -26.0, -27.0, -28.0, 5.0, 6.0, 7.0, 8.0]

    control_points = []
    for index, (fraction, mlc) in enumerate(
        [
            (0.0, first_segment_mlc),
            (first_segment, first_segment_mlc),
            (first_segment, second_segment_mlc),
            (1.0, second_segment_mlc),
        ]
    ):
        control_point = {
            "ControlPointIndex": index,
            "CumulativeMetersetWeight": fraction * final_weight,
            "BeamLimitingDevicePositionSequence": [
                {"RTBeamLimitingDeviceType": "ASYMY", "LeafJawPositions": jaw},
                {"RTBeamLimitingDeviceType": "MLCX", "LeafJawPositions": mlc},
            ],
        }
        if index == 0:
            control_point["GantryAngle"] = gantry_angle
            control_point["BeamLimitingDeviceAngle"] = 0.0
        control_points.append(control_point)

    return dicom_dataset_from_dict(
        {
            "BeamSequence": [
                {
                    "BeamNumber": 1,
                    "FinalCumulativeMetersetWeight": final_weight,
                    "NumberOfControlPoints": len(control_points),
                    "BeamLimitingDeviceSequence": [
                        {
                            "RTBeamLimitingDeviceType": "ASYMY",
                            "NumberOfLeafJawPairs": 1,
                        },
                        {
                            "RTBeamLimitingDeviceType": "MLCX",
                            "NumberOfLeafJawPairs": 4,
                            "LeafPositionBoundaries": [-20.0, -10.0, 0.0, 10.0, 20.0],
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
                        {"ReferencedBeamNumber": 1, "BeamMeterset": meterset}
                    ],
                }
            ],
        }
    )
