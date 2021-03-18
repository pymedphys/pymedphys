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

PatientOrientation = Literal["FFDL", "FFDR", "FFP", "FFS", "HFDL", "HFDR", "HFP", "HFS"]
OrientionInt = Literal[-1, 0, 1]

IMAGE_ORIENTATION_MAP: Dict[PatientOrientation, List[OrientionInt]] = {
    "FFDL": [0, 1, 0, 1, 0, 0],
    "FFDR": [0, -1, 0, -1, 0, 0],
    "FFP": [1, 0, 0, 0, -1, 0],
    "FFS": [-1, 0, 0, 0, 1, 0],
    "HFDL": [0, -1, 0, 1, 0, 0],
    "HFDR": [0, 1, 0, -1, 0, 0],
    "HFP": [-1, 0, 0, 0, -1, 0],
    "HFS": [1, 0, 0, 0, 1, 0],
}


def require_patient_orientation(ds: "pydicom.Dataset", patient_orientation):

    if not np.array_equal(
        ds.ImageOrientationPatient, np.array(IMAGE_ORIENTATION_MAP[patient_orientation])
    ):
        raise ValueError(
            "The supplied dataset has a patient "
            f"orientation other than {patient_orientation}."
        )
