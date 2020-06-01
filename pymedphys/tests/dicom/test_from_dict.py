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


import pytest

import pydicom

from pymedphys._dicom.create import dicom_dataset_from_dict


@pytest.mark.pydicom
def test_dicom_from_dict():
    baseline_dataset = pydicom.Dataset()
    baseline_dataset.Manufacturer = "PyMedPhys"
    beam_sequence = pydicom.Dataset()
    beam_sequence.Manufacturer = "PyMedPhys"
    baseline_dataset.BeamSequence = [beam_sequence]

    created_dataset = dicom_dataset_from_dict(
        {"Manufacturer": "PyMedPhys", "BeamSequence": [{"Manufacturer": "PyMedPhys"}]}
    )

    assert created_dataset == baseline_dataset
