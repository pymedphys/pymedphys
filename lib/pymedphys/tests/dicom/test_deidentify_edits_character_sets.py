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

"""How text is read under a Specific Character Set that is not supported (D-010).

Every file is synthetic and encoded by hand. Values that must never appear in
a result's ``repr`` carry the text ``SENTINEL``.
"""

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import walker

from .test_deidentify_edits import _collected, _edits
from .test_deidentify_file_layout import _explicit
from .test_deidentify_walker import _path, _rules

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]


def test_text_in_iso_646_is_read_under_an_unsupported_character_set():
    # Text with no byte from 0x80 and no escape reads the same in every
    # character set, so it is read in the Default Character Repertoire.
    _, result = _edits(
        _explicit(0x00080005, "CS", b"ISO_IR 999")
        + _explicit(0x00100010, "PN", b"SENTINEL^NAME ")
    )

    assert not result.sequestrations
    assert not result.not_collected
    assert _collected(result)[_path("(0010,0010)")] == ("PN", "SENTINEL^NAME")
    assert not result.read_as_latin_1


def test_text_outside_iso_646_under_an_unsupported_character_set_is_not_guessed():
    # As where no Specific Character Set is given: removed text is read as
    # ISO 8859-1 and listed as such, and cleaned text sequesters the instance.
    character_set = _explicit(0x00080005, "CS", b"ISO-IR 100")
    _, removed = _edits(character_set + _explicit(0x00081030, "LO", b"SENTINEL \xe9"))
    _, cleaned = _edits(
        character_set + _explicit(0x300A0003, "LO", b"SENTINEL \xe9"),
        _rules("basic-clean-descriptors"),
    )

    assert not removed.sequestrations
    assert removed.read_as_latin_1 == (_path("(0008,1030)"),)
    assert cleaned.sequestrations == (
        walker.Sequestration(
            _path("(300A,0003)"), "C", "LO", walker.SequesterReason.UNDECODABLE
        ),
    )
    assert not cleaned.edits
