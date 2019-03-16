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


from pymedphys.dicom import DicomBase, dicom_dataset_from_dict


def test_copy():
    dont_change_string = "don't change me"
    to_be_changed_string = 'do change me'

    new_manufactuer = 'george'

    dataset_to_be_copied = dicom_dataset_from_dict({
        'Manufacturer': dont_change_string
    })

    dataset_to_be_viewed = dicom_dataset_from_dict({
        'Manufacturer': to_be_changed_string
    })

    dicom_base_copy = DicomBase(dataset_to_be_copied)
    dicom_base_view = DicomBase(dataset_to_be_viewed, copy=False)

    dicom_base_copy.dataset.Manufacturer = new_manufactuer
    dicom_base_view.dataset.Manufacturer = new_manufactuer

    assert dataset_to_be_copied.Manufacturer == dont_change_string
    assert dataset_to_be_viewed.Manufacturer == new_manufactuer


def test_anonymise():
    expected_dataset = dicom_dataset_from_dict({
        'Manufacturer': 'PyMedPhys',
        'PatientName': 'Anonymous'
    })

    dicom = DicomBase.from_dict({
        'Manufacturer': 'PyMedPhys',
        'PatientName': 'Python^Monte'
    })

    dicom.anonymise(inplace=True)

    assert dicom.dataset == expected_dataset
