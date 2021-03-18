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


from typing import Dict, List, Union, cast

from pymedphys._imports import pydicom  # pylint: disable = unused-import
from typing_extensions import Literal

PatientOrientationString = Literal[
    "FFDL", "FFDR", "FFP", "FFS", "HFDL", "HFDR", "HFP", "HFS"
]
OrientationInt = Literal[-1, 0, 1]

IMAGE_ORIENTATION_MAP: Dict[PatientOrientationString, List[OrientationInt]] = {
    "FFDL": [0, 1, 0, 1, 0, 0],
    "FFDR": [0, -1, 0, -1, 0, 0],
    "FFP": [1, 0, 0, 0, -1, 0],
    "FFS": [-1, 0, 0, 0, 1, 0],
    "HFDL": [0, -1, 0, 1, 0, 0],
    "HFDR": [0, 1, 0, -1, 0, 0],
    "HFP": [-1, 0, 0, 0, -1, 0],
    "HFS": [1, 0, 0, 0, 1, 0],
}


def require_patient_orientation(
    datasets: Union["pydicom.Dataset", List["pydicom.Dataset"]],
    patient_orientation: PatientOrientationString,
):
    """Require a specific patient orientation.

    Parameters
    ----------
    datasets : pydicom.Dataset or List[pydicom.Dataset]
    patient_orientation : PatientOrientationString
        The string representation of the patient orientation, eg. "HFS".

    Raises
    ------
    ValueError
        If the patient orientation of any of the provided datasets does
        not match the provided orientation.
    """

    if isinstance(datasets, pydicom.Dataset):
        datasets = list(datasets)

    required_image_orientation_patient = IMAGE_ORIENTATION_MAP[patient_orientation]

    for dataset in datasets:
        image_orientation_patient = dataset.ImageOrientationPatient

        if image_orientation_patient != required_image_orientation_patient:
            raise ValueError(
                f"Patient orientation is not {patient_orientation}. "
                "For this to be the case the ImageOrientationPatient tag "
                f"would need to equal {required_image_orientation_patient}. "
                "Instead, however, the provided dataset has this set to "
                f"{image_orientation_patient}."
            )
