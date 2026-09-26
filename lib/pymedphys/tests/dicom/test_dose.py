# Copyright (C) 2018, 2021, 2026 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A test suite for the DICOM RT Dose toolbox."""

import copy

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom import collection, create, dose, orientation

from ._synthetic_rtdose import ORIENTATIONS, rtdose


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "transfer_syntax", ["1.2.840.10008.1.2", "1.2.840.10008.1.2.1"]
)
def test_dicom_dose_reads_known_values_and_coordinates(tmp_path, transfer_syntax):
    # Preserve file decoding, dose scaling and DicomDose property coverage
    # without downloading the historical wedge dose and its JSON baseline.
    expected_dose = np.array(
        [
            [[1.0, 2.5, 4.0], [6.5, 9.0, 12.5]],
            [[0.5, 1.5, 3.0], [5.0, 8.0, 10.0]],
        ]
    )
    dataset = rtdose(
        "HFS",
        shape=expected_dose.shape,
        pixel_values=np.round(expected_dose / 0.01),
    )
    dataset.DoseGridScaling = 0.01
    dataset.file_meta.TransferSyntaxUID = transfer_syntax
    path = tmp_path / "dose.dcm"
    collection.DicomDose(dataset).to_file(path)

    actual = collection.DicomDose.from_file(path)

    assert actual.dataset.file_meta.TransferSyntaxUID == transfer_syntax
    np.testing.assert_allclose(actual.values, expected_dose, rtol=0, atol=1e-12)
    assert actual.units == "GY"
    np.testing.assert_array_equal(actual.x, [100, 103, 106])
    np.testing.assert_array_equal(actual.y, [-200, -198])
    np.testing.assert_array_equal(actual.z, [300, 302.5])
    k, i, j = np.indices(expected_dose.shape)
    expected_coords = np.array((100 + 3 * j, -200 + 2 * i, 300 + 2.5 * k))
    np.testing.assert_array_equal(actual.coords, expected_coords)


@pytest.mark.pydicom
@pytest.mark.parametrize("patient_position", sorted(ORIENTATIONS))
@pytest.mark.parametrize("include_patient_position", [False, True])
def test_require_dicom_patient_position(patient_position, include_patient_position):
    dataset = rtdose(patient_position)
    if include_patient_position:
        dataset.PatientPosition = patient_position
    for required_position in ORIENTATIONS:
        if patient_position == required_position:
            orientation.require_dicom_patient_position(dataset, required_position)
        else:
            with pytest.raises(ValueError):
                orientation.require_dicom_patient_position(dataset, required_position)


@pytest.mark.pydicom
def test_require_dicom_patient_position_without_orientation():
    with pytest.raises(AttributeError, match="ImageOrientationPatient"):
        orientation.require_dicom_patient_position(pydicom.Dataset(), "HFS")


@pytest.mark.pydicom
def test_require_dicom_patient_position_with_conflicting_tag():
    dataset = rtdose("HFS")
    dataset.PatientPosition = "HFP"
    with pytest.raises(ValueError, match="patient position is set"):
        orientation.require_dicom_patient_position(dataset, "HFS")


@pytest.mark.pydicom
def test_sum_doses_in_datasets():
    scale1 = 1e-2
    data1 = (
        np.array(
            [
                [[0.90, 0.80, 0.70], [0.60, 0.50, 0.40]],
                [[0.91, 0.81, 0.71], [0.61, 0.51, 0.41]],
                [[0.92, 0.82, 0.72], [0.62, 0.52, 0.42]],
                [[0.93, 0.83, 0.73], [0.63, 0.53, 0.43]],
            ]
        )
        / scale1
    ).astype(np.uint32)

    scale2 = 5e-9
    data2 = (
        np.array(
            [
                [[0.10, 0.20, 0.30], [0.40, 0.50, 0.60]],
                [[0.09, 0.19, 0.29], [0.39, 0.49, 0.59]],
                [[0.08, 0.18, 0.28], [0.38, 0.48, 0.58]],
                [[0.07, 0.17, 0.27], [0.37, 0.47, 0.57]],
            ]
        )
        / scale2
    ).astype(np.uint32)

    expected_sum = np.ones((4, 2, 3))

    bits_allocated = 32

    test_dicom_dict = {
        "PatientID": "PMP",
        "Modality": "RTDOSE",
        "ImagePositionPatient": [-1.0, -1.0, -1.0],
        "ImageOrientationPatient": [1, 0, 0, 0, 1, 0],
        "BitsAllocated": bits_allocated,
        "BitsStored": bits_allocated,
        "Rows": 2,
        "Columns": 3,
        "PixelRepresentation": 0,
        "SamplesPerPixel": 1,
        "PhotometricInterpretation": "MONOCHROME2",
        "PixelSpacing": [1.0, 1.0],
        "GridFrameOffsetVector": [0, 1, 2, 3],
        "PixelData": data1.tobytes(),
        "DoseGridScaling": scale1,
        "DoseSummationType": "PLAN",
        "DoseType": "PHYSICAL",
        "DoseUnits": "GY",
    }

    ds1 = create.dicom_dataset_from_dict(test_dicom_dict)

    ds2 = copy.deepcopy(ds1)
    ds2.PixelData = data2.tobytes()
    ds2.DoseGridScaling = scale2

    ds_summed = dose.sum_doses_in_datasets([ds1, ds2])
    assert np.allclose(dose.dose_from_dataset(ds_summed), expected_sum)
    assert ds_summed.DoseType == "PHYSICAL"

    # Effective dose type:
    ds2.DoseType = "EFFECTIVE"
    ds_summed = dose.sum_doses_in_datasets([ds1, ds2])
    assert ds_summed.DoseType == "EFFECTIVE"

    # Single dataset
    ds_summed = dose.sum_doses_in_datasets([ds1])
    assert np.allclose(dose.dose_from_dataset(ds_summed), dose.dose_from_dataset(ds1))

    # More than two doses:
    ds_summed = dose.sum_doses_in_datasets([ds1, ds1, ds2, ds2])
    assert np.allclose(dose.dose_from_dataset(ds_summed), 2 * expected_sum)

    # Unmatched patient IDs
    with pytest.raises(ValueError):
        ds2.PatientID = "PMX"
        dose.sum_doses_in_datasets([ds1, ds2])
    ds2.PatientID = "PMP"

    # Bad modality
    with pytest.raises(ValueError):
        ds2.Modality = "CT"
        dose.sum_doses_in_datasets([ds1, ds2])
    ds2.Modality = "RTDOSE"

    # Nothing supplied:
    with pytest.raises(IndexError):
        dose.sum_doses_in_datasets([])

    # BEAM dose present:
    with pytest.raises(ValueError):
        ds2.DoseSummationType = "BEAM"
        dose.sum_doses_in_datasets([ds1, ds2])
    ds2.DoseSummationType = "PLAN"

    # Bad dose units
    with pytest.raises(ValueError):
        ds2.DoseUnits = "RELATIVE"
        dose.sum_doses_in_datasets([ds1, ds2])
    ds2.Modality = "GY"

    # Unmatched coords
    with pytest.raises(ValueError):
        ds2.ImagePositionPatient = [-1, -1.1, -1]
        dose.sum_doses_in_datasets([ds1, ds2])
    ds2.ImagePositionPatient = [-1, -1, -1]
