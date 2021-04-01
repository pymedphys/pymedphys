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

from pymedphys._imports import pydicom

# Many thanks to the Medical Connections for offering free
# valid UIDs (http://www.medicalconnections.co.uk/FreeUID.html)
# Their service was used to obtain the following root UID for PyMedPhys:
PYMEDPHYS_ROOT_UID = "1.2.826.0.1.3680043.10.188"

DICOM_PLAN_UID = "1.2.840.10008.5.1.4.1.1.481.5"


def generate_uid():
    return pydicom.uid.generate_uid(prefix=f"{PYMEDPHYS_ROOT_UID}.")
