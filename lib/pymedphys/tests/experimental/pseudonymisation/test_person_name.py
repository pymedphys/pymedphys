# Copyright (C) 2026 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Pseudonymised Person Name (PN) values fit the VR's length limit.

DICOM PS3.5 Table 6.2-1 allows at most 64 characters per PN component group.
"""

import warnings

from pymedphys._imports import pydicom, pytest

from pymedphys._experimental.pseudonymisation import strategy
from pymedphys.experimental import pseudonymisation

PN_COMPONENT_GROUP_MAX_LENGTH = 64

NAMES = ["", "SMITH", "SMITH^JANE", "SMITH^JANE^QUINN", "SMITH^JANE^QUINN^DR^JR"]


@pytest.mark.pydicom
@pytest.mark.parametrize("name", NAMES)
def test_pseudonymised_name_fits_the_component_group_limit(name):
    pseudonym = strategy._pseudonymise_PN(name)  # pylint: disable = protected-access

    assert len(pseudonym) <= PN_COMPONENT_GROUP_MAX_LENGTH


@pytest.mark.pydicom
@pytest.mark.parametrize("name", NAMES)
def test_pseudonymised_components_are_prefixes_of_untruncated_hashes(name):
    # Before the limit was applied, each component was the whole hash. Each
    # component is now its first 20 characters, so earlier output can be
    # re-linked by truncating it.
    untruncated = strategy._pseudonymise_PN(  # pylint: disable = protected-access
        name, max_component_length=None
    ).split("^")
    truncated = strategy._pseudonymise_PN(name).split("^")  # pylint: disable = protected-access

    assert truncated[:3] == [component[:20] for component in untruncated[:3]]
    assert all(len(component) == 20 for component in truncated[:3])


@pytest.mark.pydicom
def test_pseudonymise_writes_names_without_length_warnings():
    ds = pydicom.Dataset()
    ds.PatientName = "SMITH^JANE^QUINN"
    ds.PatientID = "123456"
    ds.OperatorsName = "JONES^ALEX"

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        pseudonymised = pseudonymisation.pseudonymise(ds)

    assert not [w for w in caught if "PN component length" in str(w.message)]
    for keyword in ("PatientName", "OperatorsName"):
        value = str(pseudonymised[keyword].value)
        assert value != str(ds[keyword].value)
        assert len(value) <= PN_COMPONENT_GROUP_MAX_LENGTH
