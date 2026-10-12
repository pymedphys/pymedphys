# Copyright (C) 2026 Matthew Jennings
# Copyright (C) 2025 Stuart Swerdloff

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

DICOM PS3.5 Table 6.2-1 allows at most 64 characters per PN component group,
which is the whole of ``family^given^middle^prefix^suffix``, delimiters
included. The components within a group have no limit of their own.
"""

# pylint: disable = protected-access

import warnings

from pymedphys._imports import pydicom, pytest

from pymedphys._experimental.pseudonymisation import strategy
from pymedphys.experimental import pseudonymisation

PN_COMPONENT_GROUP_MAX_LENGTH = 64

LONG = "A" * 100
NAMES = [
    "",
    "SMITH",
    "SMITH^JANE",
    "SMITH^JANE^QUINN",
    "SMITH^JANE^QUINN^DR^JR",
    "Smith^^John",
    f"{LONG}^{LONG}^{LONG}^{LONG}^{LONG}",
]


def _full_hash(name_part):
    """The whole hash that a name part's pseudonym is the start of."""
    return strategy._strip_plus_slash_from_base64(
        strategy._pseudonymise_plaintext(name_part)
    )


@pytest.mark.pydicom
@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("strip", [True, False])
def test_pseudonymised_names_are_valid_person_names(name, strip):
    pseudonym = strategy._pseudonymise_PN(
        name, strip_name_prefix=strip, strip_name_suffix=strip
    )

    assert len(pseudonym) <= PN_COMPONENT_GROUP_MAX_LENGTH
    assert pydicom.valuerep.validate_pn("PN", pseudonym) == (True, "")
    assert len(pseudonym.split("^")) == 5


@pytest.mark.pydicom
def test_empty_name_parts_stay_empty():
    components = strategy._pseudonymise_PN("Smith^^John").split("^")

    assert components[0] == _full_hash("Smith")[:20]
    assert components[1] == ""
    assert components[2] == _full_hash("John")[:20]
    assert components[3:] == ["", ""]


@pytest.mark.pydicom
def test_an_empty_name_stays_empty():
    assert strategy._pseudonymise_PN("").split("^") == ["", "", "", "", ""]


@pytest.mark.pydicom
@pytest.mark.parametrize("name", NAMES)
def test_name_parts_are_the_start_of_their_former_pseudonyms(name):
    # Earlier versions wrote each name part as its whole hash, so earlier
    # output can be linked by truncating its non-empty parts to 20 characters.
    person = pydicom.valuerep.PersonName(name)
    parts = [person.family_name, person.given_name, person.middle_name]
    components = strategy._pseudonymise_PN(name).split("^")

    assert components[:3] == [_full_hash(part)[:20] if part else "" for part in parts]


@pytest.mark.pydicom
def test_a_shorter_component_length_is_honoured():
    components = strategy._pseudonymise_PN(
        "FAMILYNAME^GIVENNAME^MIDDLENAME", max_component_length=8
    ).split("^")

    assert [len(component) for component in components[:3]] == [8, 8, 8]


@pytest.mark.pydicom
@pytest.mark.parametrize("max_component_length", [0, -1, 21, 64])
def test_component_lengths_that_cannot_fit_the_limit_are_rejected(
    max_component_length,
):
    with pytest.raises(ValueError, match="between 1 and 20"):
        strategy._pseudonymise_PN(
            "SMITH^JANE", max_component_length=max_component_length
        )


@pytest.mark.pydicom
def test_a_retained_prefix_and_suffix_fill_only_the_room_left():
    kept = strategy._pseudonymise_PN(
        "SMITH^^^DR^JR", strip_name_prefix=False, strip_name_suffix=False
    )
    assert kept.split("^")[3:] == ["DR", "JR"]

    # Two 20-character name parts and four delimiters leave 20 characters,
    # which the prefix takes before the suffix.
    cut = strategy._pseudonymise_PN(
        f"SMITH^JANE^^{'P' * 30}^{'S' * 30}",
        strip_name_prefix=False,
        strip_name_suffix=False,
    )
    assert cut.split("^")[3:] == ["P" * 20, ""]
    assert len(cut) == PN_COMPONENT_GROUP_MAX_LENGTH


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
