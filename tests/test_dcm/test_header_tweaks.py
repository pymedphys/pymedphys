# Copyright (C) 2019 Simon Biggs

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


from pymedphys.dcm import (
    dcm_from_dict, adjust_machine_name, adjust_rel_elec_density)


def test_adjust_machine_name():
    original_dicom_file = dcm_from_dict({
        'BeamSequence': [
            {
                'TreatmentMachineName': 'hello'
            },
            {
                'TreatmentMachineName': 'george'
            }
        ]
    })

    expected_dicom_file = dcm_from_dict({
        'BeamSequence': [
            {
                'TreatmentMachineName': 'new_name'
            },
            {
                'TreatmentMachineName': 'new_name'
            }
        ]
    })

    adjusted_dicom_file = adjust_machine_name(original_dicom_file, 'new_name')

    assert adjusted_dicom_file != original_dicom_file
    assert adjusted_dicom_file == expected_dicom_file


def test_electron_density_append():
    adjustment_map = {
        'to_be_changed 1': 1,
        'to_be_changed 2': 0.5,
        'to_be_changed 3': 1.5
    }

    original_dicom_file = dcm_from_dict({
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

    expected_dicom_file = dcm_from_dict({
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
    }, template_dcm=original_dicom_file)

    adjusted_dicom_file = adjust_rel_elec_density(
        original_dicom_file, adjustment_map)

    assert adjusted_dicom_file != original_dicom_file
    assert str(adjusted_dicom_file) == str(expected_dicom_file)
