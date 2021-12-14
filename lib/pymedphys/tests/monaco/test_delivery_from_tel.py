# Copyright (C) 2019 Cancer Care Associates and Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import itertools

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

import pymedphys

DIRS_TO_SKIP = (
    "10x10",  #  3DCRT fields not yet implemented within Delivery.from_monaco
)


@pytest.mark.pydicom
def test_delivery_from_monaco():
    data_paths = pymedphys.zip_data_paths("tel-dicom-pairs.zip")
    directories = {path.parent for path in data_paths if path.suffix == ".dcm"}

    assert len(directories) >= 2

    for directory in directories:
        if directory.name in DIRS_TO_SKIP:
            continue

        current_paths = [path for path in data_paths if directory in path.parents]
        tel_paths = [path for path in current_paths if path.name.endswith("tel.1")]
        dcm_paths = [path for path in current_paths if path.suffix == ".dcm"]

        for tel_path, dcm_path in itertools.product(tel_paths, dcm_paths):
            _compare_tel_to_dicom(tel_path, dcm_path)


def _compare_tel_to_dicom(tel_path, dcm_path):
    print(f"tel_path: {tel_path} | dcm_path: {dcm_path}")

    if tel_path.name.startswith("rxB"):
        fraction_group_number = 2
    else:
        fraction_group_number = 1

    delivery_dcm = pymedphys.Delivery.from_dicom(
        pydicom.read_file(str(dcm_path), force=True),
        fraction_group_number=fraction_group_number,
    )
    delivery_monaco = pymedphys.Delivery.from_monaco(tel_path)

    assert np.allclose(delivery_monaco.mu, delivery_dcm.mu, atol=0.01)
    assert np.allclose(delivery_monaco.gantry, delivery_dcm.gantry, atol=0.01)
    assert np.allclose(delivery_monaco.collimator, delivery_dcm.collimator, atol=0.01)
    assert np.allclose(delivery_monaco.mlc, delivery_dcm.mlc, atol=0.1)
    assert np.allclose(delivery_monaco.jaw, delivery_dcm.jaw, atol=0.01)
