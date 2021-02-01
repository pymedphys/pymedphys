# Copyright (C) 2019 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import io
from copy import deepcopy

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.collection import DicomBase
from pymedphys._dicom.create import dicom_dataset_from_dict


@pytest.mark.pydicom
def test_copy():
    dont_change_string = "don't change me"
    to_be_changed_string = "do change me"

    new_manufacturer = "george"

    dataset_to_be_copied = dicom_dataset_from_dict({"Manufacturer": dont_change_string})

    dataset_to_be_viewed = dicom_dataset_from_dict(
        {"Manufacturer": to_be_changed_string}
    )

    dicom_base_copy = DicomBase(dataset_to_be_copied)
    dicom_base_view = DicomBase(dataset_to_be_viewed, copy=False)

    dicom_base_copy.dataset.Manufacturer = new_manufacturer
    dicom_base_view.dataset.Manufacturer = new_manufacturer

    assert dataset_to_be_copied.Manufacturer == dont_change_string
    assert dataset_to_be_viewed.Manufacturer == new_manufacturer


@pytest.mark.pydicom
def test_anonymise():
    expected_dataset = dicom_dataset_from_dict(
        {"Manufacturer": "PyMedPhys", "PatientName": "Anonymous"}
    )

    dicom = DicomBase.from_dict(
        {"Manufacturer": "PyMedPhys", "PatientName": "Python^Monte"}
    )

    dicom.anonymise(inplace=True)

    assert dicom.dataset == expected_dataset


@pytest.mark.pydicom
def test_to_and_from_file():
    temp_file = io.BytesIO()

    dicom = DicomBase.from_dict(
        {"Manufacturer": "PyMedPhys", "PatientName": "Python^Monte"}
    )

    dicom.to_file(temp_file)

    new_dicom = DicomBase.from_file(temp_file)

    # TODO: Without the str this was passing locally but not on CI. Further
    # investigation needed.
    assert new_dicom == dicom


@pytest.mark.pydicom
def test_equal():
    dicom1 = DicomBase.from_dict(
        {"Manufacturer": "PyMedPhys", "PatientName": "Python^Monte"}
    )
    dicom2 = DicomBase.from_dict(
        {"Manufacturer": "PyMedPhys", "PatientName": "Python^Monte"}
    )
    assert dicom1 == dicom2  # Equality from dict

    try:
        fp1 = pydicom.filebase.DicomBytesIO()
        dicom1.to_file(fp1)
        fp2 = pydicom.filebase.DicomBytesIO()
        dicom2.to_file(fp2)

        dicom1_from_file = DicomBase.from_file(fp1)
        dicom2_from_file = DicomBase.from_file(fp2)
        # Equality from file (implicitly also from dataset)
        assert dicom1_from_file == dicom2_from_file

        dicom1_from_file.dataset.PatientName = "test^PatientName change"
        assert dicom1_from_file != dicom2_from_file  # Negative case

        dicom1_from_file.dataset.PatientName = "Python^Monte"
        assert dicom1_from_file == dicom2_from_file  # Equality post re-assignment

        dicom1_from_file_copied = deepcopy(dicom1_from_file)
        assert dicom1_from_file == dicom1_from_file_copied  # Equality from deepcopy
    finally:
        fp1.close()
        fp2.close()
