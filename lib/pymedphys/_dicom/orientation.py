# Copyright (C) 2021 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from typing import Dict, List

from pymedphys._imports import pydicom  # pylint: disable = unused-import
from typing_extensions import Literal

DicomPatientPosition = Literal[  # DICOM Patient Position Attribute (0x0018,5100)
    "HFP",
    "HFS",
    "HFDR",
    "HFDL",
    "FFDR",
    "FFDL",
    "FFP",
    "FFS",
    "LFP",
    "LFS",
    "RFP",
    "RFS",
    "AFDR",
    "AFDL",
    "PFDR",
    "PFDL",
    "SITTING",
]
OrientationInt = Literal[-1, 0, 1]

# https://dicom.innolitics.com/ciods/ct-image/general-series/00185100
# SITTING was added to the standard within the RT Image specification
# https://dicom.innolitics.com/ciods/rt-image/rt-image/00185100
PATIENT_POSITION_DEFINITION: Dict[DicomPatientPosition, str] = {
    "HFP": "Head First-Prone",
    "HFS": "Head First-Supine",
    "HFDR": "Head First-Decubitus Right",
    "HFDL": "Head First-Decubitus Left",
    "FFDR": "Feet First-Decubitus Right",
    "FFDL": "Feet First-Decubitus Left",
    "FFP": "Feet First-Prone",
    "FFS": "Feet First-Supine",
    "LFP": "Left First-Prone",
    "LFS": "Left First-Supine",
    "RFP": "Right First-Prone",
    "RFS": "Right First-Supine",
    "AFDR": "Anterior First-Decubitus Right",
    "AFDL": "Anterior First-Decubitus Left",
    "PFDR": "Posterior First-Decubitus Right",
    "PFDL": "Posterior First-Decubitus Left",
    "SITTING": "In the sitting position, the patient's face is towards the front of the chair",
}

IMAGE_ORIENTATION_MAP: Dict[DicomPatientPosition, List[OrientationInt]] = {
    "FFDL": [0, 1, 0, 1, 0, 0],
    "FFDR": [0, -1, 0, -1, 0, 0],
    "FFP": [1, 0, 0, 0, -1, 0],
    "FFS": [-1, 0, 0, 0, 1, 0],
    "HFDL": [0, -1, 0, 1, 0, 0],
    "HFDR": [0, 1, 0, -1, 0, 0],
    "HFP": [-1, 0, 0, 0, -1, 0],
    "HFS": [1, 0, 0, 0, 1, 0],
}


def require_dicom_patient_position(
    dataset: "pydicom.Dataset",
    patient_position: DicomPatientPosition,
):
    """Require a specific patient position.

    Parameters
    ----------
    datasets : pydicom.Dataset
    patient_position : DicomPatientPosition
        The required DICOM Patient Position Attribute string
        representation of the patient orientation, eg. "HFS".

    Raises
    ------
    ValueError
        If the patient orientation of the provided dataset does
        not match the provided DICOM Patient Position Attribute.
    """
    required_image_orientation_patient = IMAGE_ORIENTATION_MAP[patient_position]
    image_orientation_patient = dataset.ImageOrientationPatient

    try:
        if dataset.PatientPosition != patient_position:
            raise ValueError(
                f'The patient position is set to "{dataset.PatientPosition}", '
                f'however, if it is set, it is required to be "{patient_position}".'
            )
    except AttributeError:
        pass

    if image_orientation_patient != required_image_orientation_patient:
        raise ValueError(
            f"Patient position is not {patient_position}. "
            "For this to be the case the ImageOrientationPatient tag "
            f"would need to equal {required_image_orientation_patient}. "
            "Instead, however, the provided dataset has this set to "
            f"{image_orientation_patient}."
        )
