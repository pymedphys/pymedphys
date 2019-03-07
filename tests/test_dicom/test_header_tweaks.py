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
import subprocess

import numpy as np

import pydicom

from pymedphys.dicom import (
    ds_from_dict, adjust_machine_name, adjust_rel_elec_density)


HERE = os.path.dirname(__file__)
ORIGINAL_DICOM_FILENAME = os.path.join(HERE, 'original.dcm')
ADJUSTED_DICOM_FILENAME = os.path.join(HERE, 'adjusted.dcm')


def test_adjust_machine_name():
    new_name = 'new_name'

    original_dicom_file = ds_from_dict({
        'BeamSequence': [
            {
                'TreatmentMachineName': 'hello'
            },
            {
                'TreatmentMachineName': 'george'
            }
        ]
    })

    expected_dicom_file = ds_from_dict({
        'BeamSequence': [
            {
                'TreatmentMachineName': new_name
            },
            {
                'TreatmentMachineName': new_name
            }
        ]
    })

    adjusted_dicom_file = adjust_machine_name(original_dicom_file, new_name)

    assert adjusted_dicom_file != original_dicom_file
    assert adjusted_dicom_file == expected_dicom_file

    pydicom.write_file(ORIGINAL_DICOM_FILENAME, original_dicom_file)
    subprocess.check_call(
        'pymedphys dicom adjust-machine-name'.split() +
        [ORIGINAL_DICOM_FILENAME, ADJUSTED_DICOM_FILENAME, new_name]
    )

    cli_adjusted_dicom_file = pydicom.read_file(
        ADJUSTED_DICOM_FILENAME, force=True)

    assert str(cli_adjusted_dicom_file) == str(expected_dicom_file)

    os.remove(ORIGINAL_DICOM_FILENAME)
    os.remove(ADJUSTED_DICOM_FILENAME)


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

    original_dicom_file = ds_from_dict({
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

    expected_dicom_file = ds_from_dict({
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
    }, template_ds=original_dicom_file)

    adjusted_dicom_file = adjust_rel_elec_density(
        original_dicom_file, adjustment_map)

    assert adjusted_dicom_file != original_dicom_file
    assert str(expected_dicom_file) == str(adjusted_dicom_file)

    adjusted_with_excess_dicom_file = adjust_rel_elec_density(
        original_dicom_file, excess_adjustment_map, ignore_missing_structure=True)

    assert adjusted_with_excess_dicom_file != original_dicom_file
    assert str(expected_dicom_file) == str(adjusted_with_excess_dicom_file)

    pydicom.write_file(ORIGINAL_DICOM_FILENAME, original_dicom_file)
    excess_adjustment_map_as_list = [
        ['{}'.format(key), item] for key, item in excess_adjustment_map.items()
    ]
    excess_adjustment_map_flat = np.concatenate(
        excess_adjustment_map_as_list).tolist()

    command = (
        'pymedphys dicom adjust-rel-elec-density -i '.split()
        + [ORIGINAL_DICOM_FILENAME, ADJUSTED_DICOM_FILENAME]
        + excess_adjustment_map_flat)

    subprocess.check_call(command)

    cli_adjusted_dicom_file = pydicom.read_file(
        ADJUSTED_DICOM_FILENAME, force=True)

    assert str(expected_dicom_file) == str(cli_adjusted_dicom_file)

    os.remove(ORIGINAL_DICOM_FILENAME)
    os.remove(ADJUSTED_DICOM_FILENAME)
