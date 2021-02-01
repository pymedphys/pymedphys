# Copyright (C) 2020 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


# pylint: disable = redefined-outer-name

from pymedphys._imports import pydicom, pytest

import pymedphys


@pytest.fixture
def dataset():
    path = pymedphys.zip_data_paths("dicom-to-delivery-issue-#1047.zip")[0]

    return pydicom.dcmread(path)


def test_converting_dicom_to_delivery(dataset):
    with pytest.raises(ValueError, match=r".*not yet supported.*"):
        pymedphys.Delivery.from_dicom(dataset)
