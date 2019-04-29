# Copyright (C) 2019 Cancer Care Associates

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version (the "AGPL-3.0+").

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License and the additional terms for more
# details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

# ADDITIONAL TERMS are also included as allowed by Section 7 of the GNU
# Affero General Public License. These additional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


import os
import uuid
import subprocess

import numpy as np

import pydicom

from pymedphys_dicom.dicom import (
    dicom_dataset_from_dict, adjust_machine_name, adjust_rel_elec_density,
    adjust_RED_by_structure_name, RED_adjustment_map_from_structure_names)
from pymedphys_utilities.utilities import remove_file


HERE = os.path.dirname(__file__)
ORIGINAL_DICOM_FILENAME = os.path.join(
    HERE, 'scratch', 'original-{}.dcm'.format(str(uuid.uuid4())))
ADJUSTED_DICOM_FILENAME = os.path.join(
    HERE, 'scratch', 'adjusted-{}.dcm'.format(str(uuid.uuid4())))


def compare_dicom_cli(command, original, expected):
    pydicom.write_file(ORIGINAL_DICOM_FILENAME, original)

    try:
        subprocess.check_call(command)
        cli_adjusted_ds = pydicom.read_file(
            ADJUSTED_DICOM_FILENAME, force=True)

        assert str(cli_adjusted_ds) == str(expected)
    finally:
        remove_file(ORIGINAL_DICOM_FILENAME)
        remove_file(ADJUSTED_DICOM_FILENAME)


def test_adjust_machine_name():
    new_name = 'new_name'

    original_ds = dicom_dataset_from_dict({
        'BeamSequence': [
            {
                'TreatmentMachineName': 'hello'
            },
            {
                'TreatmentMachineName': 'george'
            }
        ]
    })

    expected_ds = dicom_dataset_from_dict({
        'BeamSequence': [
            {
                'TreatmentMachineName': new_name
            },
            {
                'TreatmentMachineName': new_name
            }
        ]
    })

    adjusted_ds = adjust_machine_name(original_ds, new_name)

    assert adjusted_ds != original_ds
    assert adjusted_ds == expected_ds

    command = (
        'pymedphys dicom adjust-machine-name'.split() +
        [ORIGINAL_DICOM_FILENAME, ADJUSTED_DICOM_FILENAME, new_name])

    compare_dicom_cli(command, original_ds, expected_ds)


def test_electron_density_append():
    adjustment_map = {
        'to_be_changed 1': 1.0,
        'to_be_changed 2': 0.5,
        'to_be_changed 3': 1.5
    }

    excess_adjustment_map = {
        **adjustment_map,
        **{
            'this_structure_doesnt_exist': 1.0
        }
    }

    original_ds = dicom_dataset_from_dict({
        'StructureSetROISequence': [
            {
                'ROINumber': 1,
                'ROIName': 'to_be_changed 1'
            },
            {
                'ROINumber': 2,
                'ROIName': 'dont_change_me'
            },
            {
                'ROINumber': 10,
                'ROIName': 'to_be_changed 2'
            },
            {
                'ROINumber': 99,
                'ROIName': 'to_be_changed 3'
            },
        ],
        'RTROIObservationsSequence': [
            {
                'ReferencedROINumber': 1,
                'ROIPhysicalPropertiesSequence': [
                    {
                        'ROIPhysicalProperty': 'EFFECTIVE_Z',
                        'ROIPhysicalPropertyValue': 6
                    }
                ]
            },
            {
                'ReferencedROINumber': 2,
            },
            {
                'ReferencedROINumber': 10,
            },
            {
                'ReferencedROINumber': 99,
                'ROIPhysicalPropertiesSequence': [
                    {
                        'ROIPhysicalProperty': 'REL_ELEC_DENSITY',
                        'ROIPhysicalPropertyValue': 0
                    }
                ]
            }
        ]
    })

    expected_ds = dicom_dataset_from_dict({
        'RTROIObservationsSequence': [
            {
                'ReferencedROINumber': 1,
                'ROIPhysicalPropertiesSequence': [
                    {
                        'ROIPhysicalProperty': 'EFFECTIVE_Z',
                        'ROIPhysicalPropertyValue': 6
                    },
                    {
                        'ROIPhysicalProperty': 'REL_ELEC_DENSITY',
                        'ROIPhysicalPropertyValue': adjustment_map['to_be_changed 1']
                    }
                ]
            },
            {
                'ReferencedROINumber': 2
            },
            {
                'ReferencedROINumber': 10,
                'ROIPhysicalPropertiesSequence': [
                    {
                        'ROIPhysicalProperty': 'REL_ELEC_DENSITY',
                        'ROIPhysicalPropertyValue': adjustment_map['to_be_changed 2']
                    }
                ]
            },
            {
                'ReferencedROINumber': 99,
                'ROIPhysicalPropertiesSequence': [
                    {
                        'ROIPhysicalProperty': 'REL_ELEC_DENSITY',
                        'ROIPhysicalPropertyValue': adjustment_map['to_be_changed 3']
                    }
                ]
            }
        ]
    }, template_ds=original_ds)

    adjusted_ds = adjust_rel_elec_density(
        original_ds, adjustment_map)

    assert adjusted_ds != original_ds
    assert str(expected_ds) == str(adjusted_ds)

    adjusted_with_excess_ds = adjust_rel_elec_density(
        original_ds, excess_adjustment_map, ignore_missing_structure=True)

    assert adjusted_with_excess_ds != original_ds
    assert str(expected_ds) == str(adjusted_with_excess_ds)

    excess_adjustment_map_as_list = [
        ['{}'.format(key), item] for key, item in excess_adjustment_map.items()
    ]
    excess_adjustment_map_flat = np.concatenate(
        excess_adjustment_map_as_list).tolist()

    command = (
        'pymedphys dicom adjust-RED -i '.split()
        + [ORIGINAL_DICOM_FILENAME, ADJUSTED_DICOM_FILENAME]
        + excess_adjustment_map_flat)

    compare_dicom_cli(command, original_ds, expected_ds)


def test_structure_name_parse():
    structure_names = [
        'a RED=1', 'b', 'c', 'd RED=2.2', 'e red = 3', 'f', 'g Red: 4.7',
        'h  RED=0.5  '
    ]
    expected_adjustment_map = {
        'a RED=1': 1,
        'd RED=2.2': 2.2,
        'e red = 3': 3,
        'g Red: 4.7': 4.7,
        'h  RED=0.5  ': 0.5
    }

    adjustment_map = RED_adjustment_map_from_structure_names(structure_names)

    assert expected_adjustment_map == adjustment_map


def test_structure_name_based_RED_append():
    electron_density_to_use = 0.5

    original_ds = dicom_dataset_from_dict({
        'StructureSetROISequence': [
            {
                'ROINumber': 1,
                'ROIName': 'a_structure RED={}'.format(electron_density_to_use)
            },
            {
                'ROINumber': 2,
                'ROIName': 'dont_change_me'
            }
        ],
        'RTROIObservationsSequence': [
            {
                'ReferencedROINumber': 1,
            },
            {
                'ReferencedROINumber': 2,
            }
        ]
    })

    expected_ds = dicom_dataset_from_dict({
        'RTROIObservationsSequence': [
            {
                'ReferencedROINumber': 1,
                'ROIPhysicalPropertiesSequence': [
                    {
                        'ROIPhysicalProperty': 'REL_ELEC_DENSITY',
                        'ROIPhysicalPropertyValue': electron_density_to_use
                    }
                ]
            },
            {
                'ReferencedROINumber': 2
            },
        ]
    }, template_ds=original_ds)

    adjusted_ds = adjust_RED_by_structure_name(original_ds)

    assert adjusted_ds != original_ds
    assert str(expected_ds) == str(adjusted_ds)

    command = (
        'pymedphys dicom adjust-RED-by-structure-name'.split()
        + [ORIGINAL_DICOM_FILENAME, ADJUSTED_DICOM_FILENAME])

    compare_dicom_cli(command, original_ds, expected_ds)
