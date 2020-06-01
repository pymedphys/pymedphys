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


import os
import subprocess
import uuid

import pytest

import numpy as np

import pydicom

from pymedphys._dicom.create import dicom_dataset_from_dict
from pymedphys._dicom.header import (
    RED_adjustment_map_from_structure_names,
    adjust_machine_name,
    adjust_RED_by_structure_name,
    adjust_rel_elec_density,
)
from pymedphys._dicom.utilities import remove_file

HERE = os.path.dirname(__file__)
ORIGINAL_DICOM_FILENAME = os.path.join(
    HERE, "scratch", "original-{}.dcm".format(str(uuid.uuid4()))
)
ADJUSTED_DICOM_FILENAME = os.path.join(
    HERE, "scratch", "adjusted-{}.dcm".format(str(uuid.uuid4()))
)


def compare_dicom_cli(command, original, expected):
    pydicom.write_file(ORIGINAL_DICOM_FILENAME, original)

    try:
        subprocess.check_call(command)
        cli_adjusted_ds = pydicom.read_file(ADJUSTED_DICOM_FILENAME, force=True)

        assert str(cli_adjusted_ds) == str(expected)
    finally:
        remove_file(ORIGINAL_DICOM_FILENAME)
        remove_file(ADJUSTED_DICOM_FILENAME)


@pytest.mark.pydicom
def test_adjust_machine_name():
    new_name = "new_name"

    original_ds = dicom_dataset_from_dict(
        {
            "BeamSequence": [
                {"TreatmentMachineName": "hello"},
                {"TreatmentMachineName": "george"},
            ]
        }
    )

    expected_ds = dicom_dataset_from_dict(
        {
            "BeamSequence": [
                {"TreatmentMachineName": new_name},
                {"TreatmentMachineName": new_name},
            ]
        }
    )

    adjusted_ds = adjust_machine_name(original_ds, new_name)

    assert adjusted_ds != original_ds
    assert adjusted_ds == expected_ds

    command = "pymedphys dicom adjust-machine-name".split() + [
        ORIGINAL_DICOM_FILENAME,
        ADJUSTED_DICOM_FILENAME,
        new_name,
    ]

    compare_dicom_cli(command, original_ds, expected_ds)


@pytest.mark.pydicom
def test_electron_density_append():
    adjustment_map = {
        "to_be_changed 1": 1.0,
        "to_be_changed 2": 0.5,
        "to_be_changed 3": 1.5,
    }

    excess_adjustment_map = {**adjustment_map, **{"this_structure_doesnt_exist": 1.0}}

    original_ds = dicom_dataset_from_dict(
        {
            "StructureSetROISequence": [
                {"ROINumber": 1, "ROIName": "to_be_changed 1"},
                {"ROINumber": 2, "ROIName": "dont_change_me"},
                {"ROINumber": 10, "ROIName": "to_be_changed 2"},
                {"ROINumber": 99, "ROIName": "to_be_changed 3"},
            ],
            "RTROIObservationsSequence": [
                {
                    "ReferencedROINumber": 1,
                    "ROIPhysicalPropertiesSequence": [
                        {
                            "ROIPhysicalProperty": "EFFECTIVE_Z",
                            "ROIPhysicalPropertyValue": 6,
                        }
                    ],
                },
                {"ReferencedROINumber": 2},
                {"ReferencedROINumber": 10},
                {
                    "ReferencedROINumber": 99,
                    "ROIPhysicalPropertiesSequence": [
                        {
                            "ROIPhysicalProperty": "REL_ELEC_DENSITY",
                            "ROIPhysicalPropertyValue": 0,
                        }
                    ],
                },
            ],
        }
    )

    expected_ds = dicom_dataset_from_dict(
        {
            "RTROIObservationsSequence": [
                {
                    "ReferencedROINumber": 1,
                    "ROIPhysicalPropertiesSequence": [
                        {
                            "ROIPhysicalProperty": "EFFECTIVE_Z",
                            "ROIPhysicalPropertyValue": 6,
                        },
                        {
                            "ROIPhysicalProperty": "REL_ELEC_DENSITY",
                            "ROIPhysicalPropertyValue": adjustment_map[
                                "to_be_changed 1"
                            ],
                        },
                    ],
                },
                {"ReferencedROINumber": 2},
                {
                    "ReferencedROINumber": 10,
                    "ROIPhysicalPropertiesSequence": [
                        {
                            "ROIPhysicalProperty": "REL_ELEC_DENSITY",
                            "ROIPhysicalPropertyValue": adjustment_map[
                                "to_be_changed 2"
                            ],
                        }
                    ],
                },
                {
                    "ReferencedROINumber": 99,
                    "ROIPhysicalPropertiesSequence": [
                        {
                            "ROIPhysicalProperty": "REL_ELEC_DENSITY",
                            "ROIPhysicalPropertyValue": adjustment_map[
                                "to_be_changed 3"
                            ],
                        }
                    ],
                },
            ]
        },
        template_ds=original_ds,
    )

    adjusted_ds = adjust_rel_elec_density(original_ds, adjustment_map)

    assert adjusted_ds != original_ds
    assert str(expected_ds) == str(adjusted_ds)

    adjusted_with_excess_ds = adjust_rel_elec_density(
        original_ds, excess_adjustment_map, ignore_missing_structure=True
    )

    assert adjusted_with_excess_ds != original_ds
    assert str(expected_ds) == str(adjusted_with_excess_ds)

    excess_adjustment_map_as_list = [
        ["{}".format(key), item] for key, item in excess_adjustment_map.items()
    ]
    excess_adjustment_map_flat = np.concatenate(excess_adjustment_map_as_list).tolist()

    command = (
        "pymedphys dicom adjust-RED -i ".split()
        + [ORIGINAL_DICOM_FILENAME, ADJUSTED_DICOM_FILENAME]
        + excess_adjustment_map_flat
    )

    compare_dicom_cli(command, original_ds, expected_ds)


@pytest.mark.pydicom
def test_structure_name_parse():
    structure_names = [
        "a RED=1",
        "b",
        "c",
        "d RED=2.2",
        "e red = 3",
        "f",
        "g Red: 4.7",
        "h  RED=0.5  ",
    ]
    expected_adjustment_map = {
        "a RED=1": 1,
        "d RED=2.2": 2.2,
        "e red = 3": 3,
        "g Red: 4.7": 4.7,
        "h  RED=0.5  ": 0.5,
    }

    adjustment_map = RED_adjustment_map_from_structure_names(structure_names)

    assert expected_adjustment_map == adjustment_map


@pytest.mark.pydicom
def test_structure_name_based_RED_append():
    electron_density_to_use = 0.5

    original_ds = dicom_dataset_from_dict(
        {
            "StructureSetROISequence": [
                {
                    "ROINumber": 1,
                    "ROIName": "a_structure RED={}".format(electron_density_to_use),
                },
                {"ROINumber": 2, "ROIName": "dont_change_me"},
            ],
            "RTROIObservationsSequence": [
                {"ReferencedROINumber": 1},
                {"ReferencedROINumber": 2},
            ],
        }
    )

    expected_ds = dicom_dataset_from_dict(
        {
            "RTROIObservationsSequence": [
                {
                    "ReferencedROINumber": 1,
                    "ROIPhysicalPropertiesSequence": [
                        {
                            "ROIPhysicalProperty": "REL_ELEC_DENSITY",
                            "ROIPhysicalPropertyValue": electron_density_to_use,
                        }
                    ],
                },
                {"ReferencedROINumber": 2},
            ]
        },
        template_ds=original_ds,
    )

    adjusted_ds = adjust_RED_by_structure_name(original_ds)

    assert adjusted_ds != original_ds
    assert str(expected_ds) == str(adjusted_ds)

    command = "pymedphys dicom adjust-RED-by-structure-name".split() + [
        ORIGINAL_DICOM_FILENAME,
        ADJUSTED_DICOM_FILENAME,
    ]

    compare_dicom_cli(command, original_ds, expected_ds)
