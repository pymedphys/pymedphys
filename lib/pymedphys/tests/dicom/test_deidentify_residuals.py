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

"""The search of written DICOM files for source values left in them."""

# The tests share the file builders and invented values below, so they stay
# in one module.
# pylint: disable = too-many-lines

import dataclasses
import io
import json
import logging
import struct
import unicodedata
import warnings
from unittest import mock

from pymedphys._imports import hypothesis, pydicom, pytest
from pymedphys._imports import numpy as np

from pymedphys._dicom.deidentify import dates, dummy_values, pseudonyms, residuals, uids
from pymedphys._dicom.deidentify.file_layout import ElementPath, Location, Region
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.residuals import (
    Finding,
    Form,
    NotSearched,
    Omission,
    SourceValue,
    Unsearched,
    UnsearchedReason,
    ValueKind,
    find_residuals,
)
from pymedphys._dicom.deidentify.values import CHECKED_VRS

st = hypothesis.strategies

EXPLICIT = "1.2.840.10008.1.2.1"
IMPLICIT = "1.2.840.10008.1.2"
UNDEFINED = 0xFFFFFFFF
# The VRs whose explicit VR header is 12 bytes (PS3.5 Table 7.1-1).
LONG_HEADER = frozenset("OB OD OF OL OV OW SQ SV UC UN UR UT UV".split())

# Invented values, distinctive enough that nothing else in a file matches them.
NAME = "ZEBEDEE^QUILLON"
PATIENT_ID = "ZQ7741093"
BIRTH_DATE = "19710203"
STUDY_DATE = "20240517"
ACCESSION = "44170917"
ROOT = "1.2.999.4417"  # an invented UID root
STUDY_UID = f"{ROOT}.1.20240517.1"


def _path(tag, *items):
    return ElementPath(tuple(items), tag)


def _source(tag, vr, value, codecs=()):
    return SourceValue(_path(tag), vr, value, codecs)


NAME_SOURCE = _source("(0010,0010)", "PN", NAME)
ID_SOURCE = _source("(0010,0020)", "LO", PATIENT_ID)
BIRTH_SOURCE = _source("(0010,0030)", "DA", BIRTH_DATE)
STUDY_SOURCE = _source("(0020,000D)", "UI", STUDY_UID)
SOURCES = (NAME_SOURCE, ID_SOURCE, BIRTH_SOURCE, STUDY_SOURCE)


def _element(tag, vr, value):
    """An explicit VR element with the header of PS3.5 Table 7.1-1 or 7.1-2."""
    group, element = divmod(tag, 0x10000)
    if vr in LONG_HEADER:
        return (
            struct.pack("<HH2sHI", group, element, vr.encode(), 0, len(value)) + value
        )
    return struct.pack("<HH2sH", group, element, vr.encode(), len(value)) + value


def _file(data_set=b"", transfer_syntax=EXPLICIT):
    """A zeroed preamble, the prefix, a Transfer Syntax UID, and ``data_set``."""
    uid = transfer_syntax.encode()
    uid += b"\x00" * (len(uid) % 2)  # PS3.5 Section 9.1
    return bytes(128) + b"DICM" + _element(0x00020010, "UI", uid) + data_set


def _private(*values):
    """A file with each ``(vr, value)`` in its own private element, (0019,1000) on.

    Text is encoded as UTF-8 and padded to an even length.
    """
    data_set = _element(0x00190010, "LO", b"PRIVATE ")
    for number, (vr, value) in enumerate(values):
        value = value.encode() if isinstance(value, str) else value
        value += b" " * (len(value) % 2)
        data_set += _element(0x00191000 + number, vr, value)
    return _file(data_set)


def _texts(*texts):
    return _private(*(("LT", text) for text in texts))


def _summary(result):
    """Each finding's source, form, encoding, and private element or region."""
    return [
        (
            finding.source.tag,
            finding.form,
            finding.encoding,
            finding.location.element.tag
            if finding.location.element
            else finding.location.region,
        )
        for finding in result.findings
    ]


def _write(dataset, transfer_syntax=EXPLICIT, **file_meta):
    if "SOPClassUID" not in dataset:
        dataset.SOPClassUID = pydicom.uid.RTPlanStorage
    if "SOPInstanceUID" not in dataset:
        dataset.SOPInstanceUID = "2.25.1"
    dataset.file_meta = pydicom.dataset.FileMetaDataset()
    dataset.file_meta.TransferSyntaxUID = transfer_syntax
    for keyword, value in file_meta.items():
        setattr(dataset.file_meta, keyword, value)
    written = io.BytesIO()
    pydicom.dcmwrite(written, dataset, enforce_file_format=True)
    return written.getvalue()


# Where de-identification can leave a source value behind.


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_a_value_hidden_in_the_preamble_is_found():
    dataset = pydicom.Dataset()
    dataset.preamble = b"II*\x00" + NAME.encode().ljust(124, b"\x00")
    data = _write(dataset)

    result = find_residuals(data, SOURCES)

    assert result.findings == (
        Finding(
            _path("(0010,0010)"),
            ValueKind.PERSON_NAME,
            Form.VALUE,
            "utf-8",
            Location(Region.PREAMBLE),
            4,
        ),
    )
    assert str(result.findings[0]) == (
        "person name from (0010,0010) found as value, utf-8, in the preamble at byte 4"
    )
    assert result.readable


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_a_value_in_the_file_meta_information_is_found():
    data = _write(
        pydicom.Dataset(),
        SourceApplicationEntityTitle=PATIENT_ID,
        PrivateInformationCreatorUID="2.25.2",
        PrivateInformation=b"born 1971-02-03.",
    )

    result = find_residuals(data, SOURCES)

    assert [str(finding) for finding in result.findings] == [
        "text from (0010,0020) found as value, utf-8, in File Meta Information "
        f"element (0002,0016) (AE) at byte {data.index(PATIENT_ID.encode())}",
        "date from (0010,0030) found as date iso, utf-8, in File Meta Information "
        f"element (0002,0102) (OB) at byte {data.index(b'1971-02-03')}",
    ]


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_a_value_in_data_set_trailing_padding_is_found():
    dataset = pydicom.Dataset()
    dataset.DataSetTrailingPadding = b"\x00" + NAME.encode()
    data = _write(dataset)

    result = find_residuals(data, SOURCES)

    assert _summary(result) == [
        ("(0010,0010)", Form.VALUE, "utf-8", "(FFFC,FFFC)"),
    ]
    assert result.findings[0].location.region is Region.TRAILING_PADDING


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_bytes_after_the_data_set_are_searched():
    written = _write(pydicom.Dataset())
    # At the first byte after the data set.
    data = written + PATIENT_ID.encode() + b"\x00"

    result = find_residuals(data, SOURCES)

    assert result.findings == (
        Finding(
            _path("(0010,0020)"),
            ValueKind.TEXT,
            Form.VALUE,
            "utf-8",
            Location(Region.TRAILING),
            len(written),
        ),
    )
    assert not result.readable


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_a_value_in_an_ob_value_is_found():
    dataset = pydicom.Dataset()
    dataset.add_new(0x00190010, "LO", "PRIVATE")
    dataset.add_new(0x00191001, "OB", b"\x01\x02" + PATIENT_ID.encode() + b"\x00")
    data = _write(dataset)

    result = find_residuals(data, SOURCES)

    assert [str(finding.location) for finding in result.findings] == [
        "data set element (0019,1001) (OB)"
    ]


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_a_value_in_a_un_value_is_found_in_utf_16():
    dataset = pydicom.Dataset()
    dataset.add_new(0x00190010, "LO", "PRIVATE")
    dataset.add_new(0x00191002, "UN", NAME.encode("utf-16-le"))
    data = _write(dataset)

    result = find_residuals(data, SOURCES)

    assert _summary(result) == [("(0010,0010)", Form.VALUE, "utf-16-le", "(0019,1002)")]
    assert str(result.findings[0].location) == "data set element (0019,1002) (UN)"


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize("transfer_syntax", [EXPLICIT, IMPLICIT])
def test_a_value_in_a_private_element_is_found(transfer_syntax):
    dataset = pydicom.Dataset()
    dataset.add_new(0x00190010, "LO", "PRIVATE")
    dataset.add_new(0x00191003, "LO", f"MRN {PATIENT_ID}")
    data = _write(dataset, transfer_syntax)

    result = find_residuals(data, SOURCES)

    # Implicit VR gives no VR for a private element.
    vr = " (LO)" if transfer_syntax == EXPLICIT else ""
    assert [str(finding) for finding in result.findings] == [
        f"text from (0010,0020) found as value, utf-8, in data set element "
        f"(0019,1003){vr} at byte {data.index(PATIENT_ID.encode())}"
    ]


ENCODINGS = [
    pytest.param(syntax, undefined, id=f"{name}-{lengths}")
    for syntax, name in ((EXPLICIT, "explicit"), (IMPLICIT, "implicit"))
    for undefined, lengths in ((False, "defined"), (True, "undefined"))
]


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize("transfer_syntax, undefined_lengths", ENCODINGS)
def test_a_value_in_a_nested_sequence_item_is_found(transfer_syntax, undefined_lengths):
    beams = []
    for beam_number in (1, 2):
        wedges = []
        for wedge_id in ("W1", "ZEBEDEE"):
            wedge = pydicom.Dataset()
            wedge.WedgeID = wedge_id if beam_number == 2 else "W0"
            wedges.append(wedge)
        beam = pydicom.Dataset()
        beam.BeamNumber = beam_number
        beam.WedgeSequence = wedges
        beams.append(beam)
    dataset = pydicom.Dataset()
    dataset.BeamSequence = beams
    if undefined_lengths:
        for sequence in (dataset["BeamSequence"], *(b["WedgeSequence"] for b in beams)):
            sequence.is_undefined_length = True
            for item in sequence.value:
                item.is_undefined_length_sequence_item = True
    data = _write(dataset, transfer_syntax)

    result = find_residuals(data, SOURCES)

    # Items are numbered from 0, as pydicom numbers them: the second wedge of
    # the second beam.
    path = "(300A,00B0)[1] > (300A,00D1)[1] > (300A,00D4)"
    assert [str(finding) for finding in result.findings] == [
        f"person name from (0010,0010) found as name component, utf-8, in data "
        f"set element {path} (SH) at byte {data.index(b'ZEBEDEE')}"
    ]
    element = result.findings[0].location.element
    assert element == ElementPath(
        (("(300A,00B0)", 1), ("(300A,00D1)", 1)), "(300A,00D4)"
    )
    read = pydicom.dcmread(io.BytesIO(data))
    (beam, beam_item), (wedge, wedge_item) = element.items
    assert beam == "(300A,00B0)" and wedge == "(300A,00D1)"
    assert read.BeamSequence[beam_item].WedgeSequence[wedge_item].WedgeID == "ZEBEDEE"


# The forms that are searched, and when a match counts.


def test_a_name_is_found_by_its_components_in_free_text():
    data = _texts("Reviewed for Zebedee", "QUILLON, Z.", "no name here")

    result = find_residuals(data, [NAME_SOURCE])

    assert _summary(result) == [
        ("(0010,0010)", Form.NAME_COMPONENT, "utf-8", "(0019,1000)"),
        ("(0010,0010)", Form.NAME_COMPONENT, "utf-8", "(0019,1001)"),
    ]


def test_a_short_name_is_found_joined():
    source = _source("(0010,0010)", "PN", "WU^LI")
    data = _texts("Li Wu", "WU, LI", "seen by wu li.", "Li Wuhan", "LI")

    result = find_residuals(data, [source])

    assert _summary(result) == [
        ("(0010,0010)", Form.NAME_JOINED, "utf-8", f"(0019,100{number})")
        for number in range(3)
    ]
    assert result.not_searched == (
        NotSearched(
            _path("(0010,0010)"), "PN", Form.NAME_COMPONENT, Omission.TOO_SHORT
        ),
    )


YAMADA = "Yamada^Tarou=山田^太郎=やまだ^たろう"
# Each name, its codecs, the codec its copies are written in, the copies,
# and which of them are found as joined names.
WRITTEN_TOGETHER = {
    "japanese-utf-8": (
        YAMADA,
        (),
        "utf-8",
        ["山田太郎", "山田\u3000太郎", "やまだたろう"],
        [0, 1, 2],
    ),
    "japanese-shift-jis": (
        YAMADA,
        ("shift_jis",),
        "shift_jis",
        ["山田太郎", "山田\u3000太郎", "やまだたろう"],
        [0, 1, 2],
    ),
    "japanese-euc-jp": (
        YAMADA,
        ("euc_jp",),
        "euc_jp",
        ["山田太郎", "山田\u3000太郎", "やまだたろう"],
        [0, 1, 2],
    ),
    "japanese-iso-2022": (
        YAMADA,
        ("iso8859", "iso2022_jp"),
        "iso2022_jp",
        ["山田太郎", "やまだたろう"],
        [0, 1],
    ),
    "ideographic-space": ("Tanaka^Makoto=田中^誠", (), "utf-8", ["田中\u3000誠"], [0]),
    "chinese-utf-8": ("Ouyang^Mingyu=欧阳^明宇", (), "utf-8", ["欧阳明宇"], [0]),
    "chinese-gb18030": (
        "Ouyang^Mingyu=欧阳^明宇",
        ("GB18030",),
        "GB18030",
        ["欧阳明宇"],
        [0],
    ),
    # A letter at an outer edge rejects a match, as for any person name form.
    "latin": (
        "QUILLON^ZEBEDEE",
        (),
        "utf-8",
        ["QUILLONZEBEDEE", "ZebedeeQuillon", "XQUILLONZEBEDEE"],
        [0, 1],
    ),
}


@pytest.mark.parametrize(
    "name, codecs, codec, copies, found",
    WRITTEN_TOGETHER.values(),
    ids=WRITTEN_TOGETHER,
)
def test_a_name_is_found_written_together(name, codecs, codec, copies, found):
    source = _source("(0010,0010)", "PN", name, codecs)
    data = _private(*(("LT", copy.encode(codec)) for copy in copies))

    result = find_residuals(data, [source])

    assert _summary(result) == [
        ("(0010,0010)", Form.NAME_JOINED, codec, f"(0019,100{number})")
        for number in found
    ]


def test_a_name_too_short_written_together_is_listed():
    source = _source("(0010,0010)", "PN", "王^小明")

    result = find_residuals(_texts("王小明", "王 小明"), [source])

    assert _summary(result) == [
        ("(0010,0010)", Form.NAME_JOINED, "utf-8", "(0019,1001)")
    ]
    path = _path("(0010,0010)")
    assert result.not_searched == (
        NotSearched(path, "PN", Form.NAME_JOINED, Omission.TOO_SHORT),
        NotSearched(path, "PN", Form.NAME_COMPONENT, Omission.TOO_SHORT),
    )


@pytest.mark.parametrize(
    "apostrophe",
    ["'", "\u2019", "\u2018", "\u02bc"],
    ids=[
        "ascii",
        "right-single-quotation-mark",
        "left-single-quotation-mark",
        "modifier-letter",
    ],
)
def test_a_name_with_an_apostrophe_is_found_with_any_apostrophe_or_none(apostrophe):
    source = _source("(0010,0010)", "PN", f"O{apostrophe}NEILL^SIOBHAN")
    data = _texts("Dr O'Neill", "Dr O\u2019Neill", "Dr ONeill", "Dr Neill")

    result = find_residuals(data, [source])

    assert _summary(result) == [
        ("(0010,0010)", Form.NAME_COMPONENT, "utf-8", f"(0019,100{number})")
        for number in range(3)
    ]
    assert not result.not_searched


# Each name, its codecs, the codec of the copy, the copy, and the form found.
# Each character is written in its other width, half or full, or as NFKC
# gives it.
WIDTHS = {
    "half-width-source": ("ﾔﾏﾀﾞ^ﾀﾛｳ", (), "utf-8", "ヤマダタロウ", Form.NAME_JOINED),
    "half-width-copy": ("ヤマダ^タロウ", (), "utf-8", "ﾔﾏﾀﾞﾀﾛｳ", Form.NAME_JOINED),
    "half-width-copy-in-shift-jis": (
        "ヤマダ^タロウ",
        ("shift_jis",),
        "shift_jis",
        "ﾔﾏﾀﾞﾀﾛｳ",
        Form.NAME_JOINED,
    ),
    "full-width-copy": (
        "YAMADA^TAROU",
        (),
        "utf-8",
        "Dr ＹＡＭＡＤＡ",
        Form.NAME_COMPONENT,
    ),
}


@pytest.mark.parametrize("name, codecs, codec, copy, form", WIDTHS.values(), ids=WIDTHS)
def test_a_name_is_found_in_its_other_width(name, codecs, codec, copy, form):
    source = _source("(0010,0010)", "PN", name, codecs)

    result = find_residuals(_private(("LT", copy.encode(codec))), [source])

    assert _summary(result) == [("(0010,0010)", form, codec, "(0019,1000)")]


def test_a_run_in_one_character_set_is_found_inside_a_longer_run():
    # The codec designates JIS X 0208 before each run and resets after it,
    # so "山田太郎" inside a longer run has no escape sequences around it.
    source = _source("(0010,0010)", "PN", YAMADA, ("iso8859", "iso2022_jp"))
    copies = ["山田太郎様", "患者山田太郎", "山田太郎"]
    data = _private(*(("LT", copy.encode("iso2022_jp")) for copy in copies))

    result = find_residuals(data, [source])

    assert _summary(result) == [
        ("(0010,0010)", Form.NAME_JOINED, "iso2022_jp", f"(0019,100{number})")
        for number in range(3)
    ]
    # Spellings with escape sequences placed otherwise are still not searched.
    assert (Form.NAME_JOINED, Omission.CODE_EXTENSIONS) in {
        (omission.form, omission.reason) for omission in result.not_searched
    }


def test_a_name_with_one_short_part_is_found_joined_and_by_the_other():
    source = _source("(0010,0010)", "PN", "QUILLON^LI")
    data = _texts("Li Quillon", "Dr Quillon")

    result = find_residuals(data, [source])

    assert _summary(result) == [
        ("(0010,0010)", Form.NAME_JOINED, "utf-8", "(0019,1000)"),
        ("(0010,0010)", Form.NAME_COMPONENT, "utf-8", "(0019,1001)"),
    ]


def test_middle_names_are_searched_but_not_prefixes_or_suffixes():
    source = _source("(0010,0010)", "PN", "QUILLON^ZEBEDEE^ARCHIBALD^DOCTOR^JUNIOR")
    data = _texts("Archibald", "Doctor", "Junior")

    result = find_residuals(data, [source])

    assert _summary(result) == [
        ("(0010,0010)", Form.NAME_COMPONENT, "utf-8", "(0019,1000)")
    ]


def test_each_word_of_a_compound_name_is_searched():
    source = _source("(0010,0010)", "PN", "DE LA CRUZ^ANNE-MARIE")
    data = _texts("Seen by Dr Cruz", "Marie", "Cruzado", "ANNE-MARIE", "Annette")

    result = find_residuals(data, [source])

    assert _summary(result) == [
        ("(0010,0010)", Form.NAME_WORD, "utf-8", "(0019,1000)"),
        ("(0010,0010)", Form.NAME_WORD, "utf-8", "(0019,1001)"),
        ("(0010,0010)", Form.NAME_COMPONENT, "utf-8", "(0019,1003)"),
    ]
    assert result.not_searched == (
        NotSearched(_path("(0010,0010)"), "PN", Form.NAME_WORD, Omission.TOO_SHORT),
    )
    assert str(result.findings[0]).startswith(
        "person name from (0010,0010) found as name word, utf-8"
    )


def test_a_component_inside_a_longer_word_is_not_a_finding():
    source = _source("(0010,0010)", "PN", "MARY^QUILLON")
    data = _private(
        ("LT", "PRIMARY"),
        ("LT", "Summary"),
        ("LT", "zebedeequillon"),
        ("UN", "PRIMARY".encode("utf-16-le")),
        ("LT", "Dr Mary."),
        ("UN", " Mary ".encode("utf-16-le")),
        ("LT", "mary2"),
        # U+0141 is not an ASCII letter, although its low byte is "A".
        ("UN", "ŁMary".encode("utf-16-le")),
    )

    result = find_residuals(data, [source])

    assert _summary(result) == [
        ("(0010,0010)", Form.NAME_COMPONENT, "utf-8", "(0019,1004)"),
        ("(0010,0010)", Form.NAME_COMPONENT, "utf-16-le", "(0019,1005)"),
        ("(0010,0010)", Form.NAME_COMPONENT, "utf-8", "(0019,1006)"),
        ("(0010,0010)", Form.NAME_COMPONENT, "utf-16-le", "(0019,1007)"),
    ]


def test_a_date_is_found_in_dicom_and_iso_forms():
    invalid = _source("(0010,0030)", "DA", "19710230")
    data = _texts("born 19710203", "born 1971-02-03", "1971-02-30", "19710230")

    result = find_residuals(data, [BIRTH_SOURCE, invalid])

    assert _summary(result) == [
        ("(0010,0030)", Form.VALUE, "utf-8", "(0019,1000)"),
        ("(0010,0030)", Form.DATE_ISO, "utf-8", "(0019,1001)"),
        ("(0010,0030)", Form.VALUE, "utf-8", "(0019,1003)"),
    ]
    assert {finding.kind for finding in result.findings} == {ValueKind.DATE}


def test_a_date_is_found_in_other_spellings():
    datetime = _source("(0008,002A)", "DT", "20240517101500")
    data = _texts(
        "born 03/02/1971",
        "born 02/03/1971",
        "born 03.02.1971",
        "1971:02:03 08:30:00",  # as EXIF writes a date and time
        "103/02/1971",
        "on 17.05.2024",
    )

    result = find_residuals(data, [BIRTH_SOURCE, datetime])

    assert _summary(result) == [
        ("(0010,0030)", Form.DATE_DMY_SLASH, "utf-8", "(0019,1000)"),
        ("(0010,0030)", Form.DATE_MDY_SLASH, "utf-8", "(0019,1001)"),
        ("(0010,0030)", Form.DATE_DMY_DOT, "utf-8", "(0019,1002)"),
        ("(0010,0030)", Form.DATE_EXIF, "utf-8", "(0019,1003)"),
        ("(0008,002A)", Form.DATE_DMY_DOT, "utf-8", "(0019,1005)"),
    ]
    # Reports name the spelling without quoting the date.
    spellings = ["dd/mm/yyyy", "mm/dd/yyyy", "dd.mm.yyyy", "exif"]
    for finding, spelling in zip(result.findings, spellings):
        assert f" found as date {spelling}, utf-8, " in str(finding)


@pytest.mark.parametrize("value", ["2024", "202405"])
def test_a_datetime_without_a_full_date_is_not_searched(value):
    source = _source("(0008,002A)", "DT", value)
    data = _texts("2024-05-17", "Version 2024.1", "1.2.2024.5", "20240517")

    result = find_residuals(data, [source])

    assert not result.findings
    assert result.not_searched == (
        NotSearched(_path("(0008,002A)"), "DT", Form.VALUE, Omission.NOT_DISTINCTIVE),
    )


def test_an_acr_nema_date_is_found_in_each_spelling():
    # ACR-NEMA wrote dates as YYYY.MM.DD.
    source = _source("(0010,0030)", "DA", "1971.02.03")
    data = _texts("19710203", "1971-02-03", "1971.02.03", "03/02/1971")

    result = find_residuals(data, [source])

    assert _summary(result) == [
        ("(0010,0030)", Form.DATE_DICOM, "utf-8", "(0019,1000)"),
        ("(0010,0030)", Form.DATE_ISO, "utf-8", "(0019,1001)"),
        ("(0010,0030)", Form.VALUE, "utf-8", "(0019,1002)"),
        ("(0010,0030)", Form.DATE_DMY_SLASH, "utf-8", "(0019,1003)"),
    ]


def test_a_date_is_found_at_the_start_of_a_datetime():
    datetime = _source("(0008,002A)", "DT", "20240517101500.000000+1000")
    data = _texts("19710203120000", "acquired 20240517.", "2024-05-17T10:15")

    result = find_residuals(data, [BIRTH_SOURCE, datetime])

    assert _summary(result) == [
        ("(0010,0030)", Form.VALUE, "utf-8", "(0019,1000)"),
        ("(0008,002A)", Form.DATE_DICOM, "utf-8", "(0019,1001)"),
        ("(0008,002A)", Form.DATE_ISO, "utf-8", "(0019,1002)"),
    ]
    assert result.findings[1].kind is ValueKind.DATETIME


def test_a_datetime_that_is_only_a_date_is_found_before_a_time():
    datetime = _source("(0008,002A)", "DT", BIRTH_DATE)

    result = find_residuals(_texts("19710203120000"), [datetime])

    assert _summary(result) == [("(0008,002A)", Form.VALUE, "utf-8", "(0019,1000)")]


def test_each_of_several_values_is_searched_without_its_padding():
    other_ids = _source("(0010,1002)", "LO", " ZQ7741093 \\QX5512093\x00")
    comments = _source("(0010,4000)", "LT", "Seen\\ZEBEDEE again")
    data = _texts("QX5512093", "ZQ7741093", "ZEBEDEE again", "Seen\\ZEBEDEE again")

    result = find_residuals(data, [other_ids, comments])

    # LT, ST, UR, and UT values are not split at backslashes.
    assert _summary(result) == [
        ("(0010,1002)", Form.VALUE, "utf-8", "(0019,1000)"),
        ("(0010,1002)", Form.VALUE, "utf-8", "(0019,1001)"),
        ("(0010,4000)", Form.VALUE, "utf-8", "(0019,1003)"),
    ]


def _nfc(text):
    return unicodedata.normalize("NFC", text)


def _nfd(text):
    return unicodedata.normalize("NFD", text)


# Each source value, its codecs, the copy written in the file, and the
# encoding of the copy. In NFD, each accented letter is a base letter and a
# combining character, and each Hangul syllable is conjoining jamo.
NORMALISATIONS = {
    "nfd-source-nfc-copy": (_nfd("MÜLLER^JÖRG"), (), _nfc("MÜLLER^JÖRG"), "utf-8"),
    "nfd-source-nfd-copy": (_nfd("MÜLLER^JÖRG"), (), _nfd("MÜLLER^JÖRG"), "utf-8"),
    "nfc-source-nfd-copy": (_nfc("MÜLLER^JÖRG"), (), _nfd("MÜLLER^JÖRG"), "utf-8"),
    "nfd-copy-in-utf-16": ("MÜLLER^JÖRG", (), _nfd("MÜLLER^JÖRG"), "utf-16-le"),
    "nfd-copy-in-gb18030": (
        "MÜLLER^JÖRG",
        ("GB18030",),
        _nfd("MÜLLER^JÖRG"),
        "GB18030",
    ),
    "vietnamese-tone-marks": ("NGUYỄN^THỊ", (), _nfd("NGUYỄN^THỊ"), "utf-8"),
    "hangul-jamo": ("서울병원", (), _nfd("서울병원"), "utf-8"),
    # NFC replaces a CJK compatibility ideograph, U+F900, with U+8C48.
    "compatibility-ideograph": (
        "\uf900\u5c71\u75c5\u9662",
        (),
        "\uf900\u5c71\u75c5\u9662",
        "utf-8",
    ),
    # A compatibility character, such as "№", which NFKC replaces with "No",
    # kept in a copy that is composed or decomposed otherwise.
    "nfc-copy-keeping-a-compatibility-character": (
        _nfd("ZIMMER № 12, MÜLLER"),
        (),
        _nfc("ZIMMER № 12, MÜLLER"),
        "utf-8",
    ),
    "nfd-copy-keeping-a-compatibility-character": (
        _nfc("ZIMMER № 12, MÜLLER"),
        (),
        _nfd("ZIMMER № 12, MÜLLER"),
        "utf-8",
    ),
}


@pytest.mark.parametrize(
    "value, codecs, copy, encoding", NORMALISATIONS.values(), ids=NORMALISATIONS
)
def test_a_value_is_found_composed_decomposed_or_as_written(
    value, codecs, copy, encoding
):
    source = _source("(0008,0080)", "LO", value, codecs)
    data = _private(("UN" if encoding == "utf-16-le" else "LT", copy.encode(encoding)))

    result = find_residuals(data, [source])

    assert _summary(result) == [("(0008,0080)", Form.VALUE, encoding, "(0019,1000)")]
    assert not result.not_searched


def test_a_number_inside_a_longer_number_is_not_a_finding():
    source = _source("(0008,0050)", "SH", ACCESSION)
    data = _texts(
        "A144170917", "441709170", "2.25.1441709175", "acc 44170917.", "x44170917y"
    )

    result = find_residuals(data, [source])

    assert _summary(result) == [
        ("(0008,0050)", Form.VALUE, "utf-8", "(0019,1003)"),
        ("(0008,0050)", Form.VALUE, "utf-8", "(0019,1004)"),
    ]


def test_an_identifier_that_ends_with_a_digit_is_not_found_before_one():
    data = _texts("ZQ77410935", "MRN ZQ7741093.")

    result = find_residuals(data, [ID_SOURCE])

    assert _summary(result) == [("(0010,0020)", Form.VALUE, "utf-8", "(0019,1001)")]


def test_text_that_is_not_a_person_name_is_found_inside_words():
    institution = _source("(0008,0080)", "LO", "ARBORVALE")

    result = find_residuals(
        _texts(f"MRN{PATIENT_ID}", "XARBORVALES"), [ID_SOURCE, institution]
    )

    assert _summary(result) == [
        ("(0010,0020)", Form.VALUE, "utf-8", "(0019,1000)"),
        ("(0008,0080)", Form.VALUE, "utf-8", "(0019,1001)"),
    ]


@pytest.mark.parametrize(
    "data",
    [b"1" + ACCESSION.encode(), ACCESSION.encode() + b"5"],
    ids=["first-byte", "last-byte"],
)
def test_the_first_and_last_bytes_of_a_file_are_neighbours(data):
    source = _source("(0008,0050)", "SH", ACCESSION)

    assert not find_residuals(data, [source]).findings


def test_numbers_in_decimal_strings_are_not_findings():
    source = _source("(0008,0050)", "SH", ACCESSION)
    letters = _source("(0010,0020)", "LO", "ZQ774109")
    data = _private(
        ("DS", "-12.5\\44170917\\3"),
        ("IS", "44170917\\44170917"),
        ("DS", "ZQ774109"),
        ("LO", "44170917"),
    )

    result = find_residuals(data, [source, letters])

    assert _summary(result) == [
        ("(0010,0020)", Form.VALUE, "utf-8", "(0019,1002)"),
        ("(0008,0050)", Form.VALUE, "utf-8", "(0019,1003)"),
    ]


def test_a_uid_is_found_but_not_inside_a_longer_component():
    data = _texts(
        STUDY_UID,
        f"{STUDY_UID}5",
        f"1{STUDY_UID}",
        f"{STUDY_UID}.7",
        f"uid={STUDY_UID}",
    )

    result = find_residuals(data, [STUDY_SOURCE])

    assert _summary(result) == [
        ("(0020,000D)", Form.VALUE, "utf-8", "(0019,1000)"),
        ("(0020,000D)", Form.VALUE, "utf-8", "(0019,1003)"),
        ("(0020,000D)", Form.VALUE, "utf-8", "(0019,1004)"),
    ]
    assert result.findings[0].kind is ValueKind.UID
    assert str(result.findings[0]).startswith("UID from (0020,000D) found as value")


def test_a_person_name_is_found_without_its_trailing_delimiters():
    source = _source("(0010,0010)", "PN", "ZEBEDEE^QUILLON^^==")

    result = find_residuals(_texts("ZEBEDEE^QUILLON"), [source])

    assert _summary(result) == [("(0010,0010)", Form.VALUE, "utf-8", "(0019,1000)")]


def test_case_does_not_hide_a_value():
    accented = _source("(0008,0090)", "PN", "MÜLLER^JÖRG", ("latin_1",))
    data = _private(
        ("LT", "zebedee^quillon"),
        ("LT", "Zebedee^Quillon"),
        ("LT", "müller^jörg".encode("latin-1")),
        ("LT", "Müller"),
        ("UN", "mÜller".encode("utf-16-le")),
    )

    result = find_residuals(data, [NAME_SOURCE, accented])

    assert _summary(result) == [
        ("(0010,0010)", Form.VALUE, "utf-8", "(0019,1000)"),
        ("(0010,0010)", Form.VALUE, "utf-8", "(0019,1001)"),
        ("(0008,0090)", Form.VALUE, "latin-1", "(0019,1002)"),
        ("(0008,0090)", Form.NAME_COMPONENT, "utf-8", "(0019,1003)"),
        ("(0008,0090)", Form.NAME_COMPONENT, "utf-16-le", "(0019,1004)"),
    ]


# Names in upper case, their source character sets, and copies written in
# title case, whose first letters are not ASCII.
TITLE_CASE = {
    "cyrillic": ("ИВАНОВ^ИВАН", "iso_ir_144", "Пациент Иванов Иван", "iso_ir_144"),
    # Python gives "Παπαδοπουλος" its final sigma.
    "greek": (
        "ΠΑΠΑΔΟΠΟΥΛΟΣ^ΓΙΩΡΓΟΣ",
        "iso_ir_126",
        "Παπαδοπουλος Γιωργος",
        "iso_ir_126",
    ),
    # ISO 8859-9 encodes these letters as ISO 8859-1 does.
    "turkish": ("ÖZTÜRK^AYŞE", "iso_ir_148", "Dr Öztürk", "latin-1"),
    "latin-1": ("ÅSTRÖM^ØYVIND", "latin_1", "Åström", "latin-1"),
}


@pytest.mark.parametrize(
    "name, codec, copy, reported", TITLE_CASE.values(), ids=TITLE_CASE
)
def test_a_name_is_found_in_title_case(name, codec, copy, reported):
    source = _source("(0010,0010)", "PN", name, (codec,))
    data = _private(
        ("LO", copy.encode(codec)),
        ("LO", copy.encode("utf-8")),
        ("UN", copy.encode("utf-16-le")),
    )

    result = find_residuals(data, [source])

    assert _summary(result) == [
        ("(0010,0010)", Form.NAME_COMPONENT, reported, "(0019,1000)"),
        ("(0010,0010)", Form.NAME_COMPONENT, "utf-8", "(0019,1001)"),
        ("(0010,0010)", Form.NAME_COMPONENT, "utf-16-le", "(0019,1002)"),
    ]
    assert not result.not_searched


@pytest.mark.parametrize(
    "name, codec, reported",
    [
        ("MÜLLER^JÖRG", "latin_1", "latin-1"),  # ISO_IR 100, which is ISO 8859-1
        ("DVOŘÁK^ZDENĚK", "iso8859_2", "iso8859_2"),  # ISO_IR 101
    ],
)
def test_a_value_is_found_in_its_character_set_utf_8_and_utf_16(name, codec, reported):
    source = _source("(0010,0010)", "PN", name, (codec,))
    data = _private(
        ("LO", name.encode(codec)),
        ("LO", name.encode("utf-8")),
        ("UN", name.encode("utf-16-le")),
    )

    result = find_residuals(data, [source])

    assert _summary(result) == [
        ("(0010,0010)", Form.VALUE, reported, "(0019,1000)"),
        ("(0010,0010)", Form.VALUE, "utf-8", "(0019,1001)"),
        ("(0010,0010)", Form.VALUE, "utf-16-le", "(0019,1002)"),
    ]


def test_a_form_is_searched_with_the_escape_sequences_its_codec_writes():
    source = _source("(0010,0010)", "PN", "Yamada^Tarou=山田^太郎", ("iso2022_jp",))
    data = _private(
        ("LO", "山田^太郎".encode("iso2022_jp")),
        ("LO", "山田^太郎".encode("utf-8")),
        ("LO", "TAROU"),
    )

    result = find_residuals(data, [source])

    assert _summary(result) == [
        ("(0010,0010)", Form.NAME_GROUP, "iso2022_jp", "(0019,1000)"),
        ("(0010,0010)", Form.NAME_GROUP, "utf-8", "(0019,1001)"),
        ("(0010,0010)", Form.NAME_COMPONENT, "utf-8", "(0019,1002)"),
    ]
    # Spellings with escape sequences that another writer places otherwise
    # are not searched.
    path = _path("(0010,0010)")
    assert result.not_searched == (
        NotSearched(path, "PN", Form.VALUE, Omission.CODE_EXTENSIONS, "iso2022_jp"),
        NotSearched(
            path, "PN", Form.NAME_GROUP, Omission.CODE_EXTENSIONS, "iso2022_jp"
        ),
        NotSearched(
            path, "PN", Form.NAME_JOINED, Omission.CODE_EXTENSIONS, "iso2022_jp"
        ),
        NotSearched(path, "PN", Form.NAME_COMPONENT, Omission.TOO_SHORT),
        # "Ｙａｍａｄａ", in full-width Latin letters.
        NotSearched(
            path, "PN", Form.NAME_COMPONENT, Omission.CODE_EXTENSIONS, "iso2022_jp"
        ),
    )
    assert str(result.not_searched[0]) == (
        "PN from (0010,0010): value with other ISO 2022 escape sequences in "
        "iso2022_jp not searched: code extensions"
    )


# With more than one value in Specific Character Set, each component in
# another character set starts with an ISO 2022 escape sequence (PS3.5
# Section 6.1.2.5.3, and Annexes I and K), although pydicom writes none in
# ISO 2022 IR 58 text. The Korean name has an invented family name of four
# syllables, long enough to search, which is also copied on its own.
CODE_EXTENSIONS = {
    "korean": (
        ["", "ISO 2022 IR 149"],
        "HWANGBOSEOYUN^ARAM==황보서윤^아람",
        "황보서윤",
        [(Form.NAME_GROUP, "utf-8", "(0008,0090)")],
        [(Form.NAME_COMPONENT, "euc_kr", "(0019,1001)")],
        [
            (Form.VALUE, Omission.CODE_EXTENSIONS),
            (Form.NAME_GROUP, Omission.CODE_EXTENSIONS),
            (Form.NAME_JOINED, Omission.CODE_EXTENSIONS),
            (Form.NAME_COMPONENT, Omission.CODE_EXTENSIONS),
            (Form.NAME_COMPONENT, Omission.TOO_SHORT),
        ],
    ),
    "chinese": (
        ["", "ISO 2022 IR 58"],
        "Zhang^XiaoDong=张^小东=",
        None,
        [(Form.VALUE, "iso_ir_58", "(0008,0090)")],
        [],
        [
            (Form.VALUE, Omission.CODE_EXTENSIONS),
            (Form.NAME_GROUP, Omission.CODE_EXTENSIONS),
            # "张小东" and "小东张", run together, are too short to search.
            (Form.NAME_JOINED, Omission.TOO_SHORT),
            (Form.NAME_JOINED, Omission.CODE_EXTENSIONS),
            (Form.NAME_COMPONENT, Omission.TOO_SHORT),
            # "Ｚｈａｎｇ", in full-width Latin letters.
            (Form.NAME_COMPONENT, Omission.CODE_EXTENSIONS),
        ],
    ),
}


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize(
    "character_set, name, copy, in_name, in_copy, listed",
    CODE_EXTENSIONS.values(),
    ids=CODE_EXTENSIONS,
)
def test_forms_with_code_extensions_are_searched_in_their_codec_and_listed(
    character_set, name, copy, in_name, in_copy, listed
):
    dataset = pydicom.Dataset()
    dataset.SpecificCharacterSet = character_set
    dataset.ReferringPhysicianName = name
    if copy:
        dataset.add_new(0x00190010, "LO", "PRIVATE")
        dataset.add_new(0x00191001, "LO", copy)
    data = _write(dataset)
    codecs = tuple(pydicom.charset.convert_encodings(character_set))
    source = _source("(0010,0010)", "PN", name, codecs)

    result = find_residuals(data, [source])

    assert _summary(result) == [
        ("(0010,0010)", form, encoding, tag)
        for form, encoding, tag in in_name + in_copy
    ]
    path = _path("(0010,0010)")
    assert result.not_searched == tuple(
        NotSearched(
            path,
            "PN",
            form,
            reason,
            codecs[1] if reason is Omission.CODE_EXTENSIONS else None,
        )
        for form, reason in listed
    )


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize("character_set", ["GB18030", "GBK"])
def test_character_sets_without_code_extensions_are_searched_in_their_codec(
    character_set,
):
    name = "Zhang^XiaoDong=张^小东="
    dataset = pydicom.Dataset()
    dataset.SpecificCharacterSet = character_set
    dataset.ReferringPhysicianName = name
    data = _write(dataset)
    (codec,) = pydicom.charset.convert_encodings(character_set)

    result = find_residuals(data, [_source("(0010,0010)", "PN", name, (codec,))])

    # They use no escape sequences, so the whole name is found.
    assert _summary(result) == [("(0010,0010)", Form.VALUE, codec, "(0008,0090)")]
    path = _path("(0010,0010)")
    # "张小东" and "小东张", run together, are too short to search.
    assert result.not_searched == (
        NotSearched(path, "PN", Form.NAME_JOINED, Omission.TOO_SHORT),
        NotSearched(path, "PN", Form.NAME_COMPONENT, Omission.TOO_SHORT),
    )


def test_forms_already_searched_in_iso_8859_1_are_not_listed():
    # Code extensions, with ISO 8859-1 as the extension, whose forms are
    # searched as ISO 8859-1 whatever the escape sequences around them.
    source = _source("(0010,0010)", "PN", "MÜLLER^JÖRG", ("iso8859", "latin_1"))
    data = _private(("LO", "Dr MÜLLER".encode("latin-1")))

    result = find_residuals(data, [source])

    assert _summary(result) == [
        ("(0010,0010)", Form.NAME_COMPONENT, "latin-1", "(0019,1000)")
    ]
    assert not result.not_searched


def test_half_width_characters_are_counted_once_composed():
    # "ﾔﾏﾀﾞ" is four characters, but "ヤマダ", three, once composed (NFKC).
    source = _source("(0010,0010)", "PN", "ﾔﾏﾀﾞ^TAROU")

    result = find_residuals(_texts("Dr ﾔﾏﾀﾞ"), [source])

    assert not result.findings
    assert result.not_searched == (
        NotSearched(
            _path("(0010,0010)"), "PN", Form.NAME_COMPONENT, Omission.TOO_SHORT
        ),
    )


def test_lengths_are_counted_once_composed():
    # "ZOË" has three characters composed (NFC) and four decomposed (NFD).
    source = _source("(0010,0010)", "PN", "ZOË^QUILLON")
    data = _texts(_nfd("Dr Zoë."), _nfd("QUILLON ZOË"))

    result = find_residuals(data, [source])

    assert _summary(result) == [
        ("(0010,0010)", Form.NAME_JOINED, "utf-8", "(0019,1001)")
    ]
    assert result.not_searched == (
        NotSearched(
            _path("(0010,0010)"), "PN", Form.NAME_COMPONENT, Omission.TOO_SHORT
        ),
    )


def test_a_long_value_is_searched_by_its_first_256_characters():
    comment = "Clinic " + " ".join(f"note {number}" for number in range(100, 160))
    # The first 256 characters end inside "note 127", so a digit follows them.
    assert comment[250:258] == "note 127"
    source = _source("(0032,4000)", "LT", comment)
    data = _texts(comment[:257] + " and then something else", comment[100:])

    result = find_residuals(data, [source])

    assert residuals.MAX_CHARACTERS == 256
    assert _summary(result) == [("(0032,4000)", Form.VALUE, "utf-8", "(0019,1000)")]


NUMERIC = {
    "private-ow": (0x00191001, "OW"),
    "private-of": (0x00191001, "OF"),
    "pixel-data-ow": (0x7FE00010, "OW"),
    "pixel-data-ob": (0x7FE00010, "OB"),  # native, with 8-bit samples
    "float-pixel-data": (0x7FE00008, "OF"),
}
# A form shorter than 8 bytes at the first byte, one in UTF-16LE, and two of
# at least 8 bytes.
IN_NUMBERS = (
    b"MARY\x00\x02"
    + PATIENT_ID.encode("utf-16-le")
    + b"\x00\x02"
    + PATIENT_ID.encode()
    + b"\x00\x02"
    + BIRTH_DATE.encode()
    + b"\x00\x02"
)


@pytest.mark.parametrize("tag, vr", NUMERIC.values(), ids=NUMERIC)
def test_values_in_numeric_values_need_long_single_byte_forms(tag, vr):
    name = _source("(0010,0010)", "PN", "MARY^QUILLON")
    numeric = _file(_element(tag, vr, IN_NUMBERS))
    ob = _file(_element(0x00191001, "OB", IN_NUMBERS))

    in_numbers = find_residuals(numeric, [name, ID_SOURCE, BIRTH_SOURCE])
    in_ob = find_residuals(ob, [name, ID_SOURCE, BIRTH_SOURCE])

    assert residuals.MIN_BYTES_IN_NUMBERS == 8
    assert [(f.source.tag, f.encoding, f.offset) for f in in_numbers.findings] == [
        ("(0010,0020)", "utf-8", numeric.index(PATIENT_ID.encode())),
        ("(0010,0030)", "utf-8", numeric.index(BIRTH_DATE.encode())),
    ]
    # Each source once, by the first match of its widest form.
    assert [(f.source.tag, f.encoding, f.offset) for f in in_ob.findings] == [
        ("(0010,0010)", "utf-8", ob.index(b"MARY")),
        ("(0010,0020)", "utf-16-le", ob.index(PATIENT_ID.encode("utf-16-le"))),
        ("(0010,0030)", "utf-8", ob.index(BIRTH_DATE.encode())),
    ]


def test_in_an_item_only_values_of_numeric_vrs_hold_numbers():
    # Pixel Data in an item, such as an icon's, is searched for every form.
    item = _element(0x00191001, "OW", IN_NUMBERS) + _element(0x7FE00010, "OB", b"MARY")
    sequence = _element(0x00191002, "SQ", _element_item(item))
    data = _file(_element(0x00190010, "LO", b"PRIVATE ") + sequence)

    result = find_residuals(data, [_source("(0010,0010)", "PN", "MARY^Q"), ID_SOURCE])

    assert [(f.source.tag, str(f.location.element)) for f in result.findings] == [
        ("(0010,0020)", "(0019,1002)[0] > (0019,1001)"),
        ("(0010,0010)", "(0019,1002)[0] > (7FE0,0010)"),
    ]


def _element_item(content=b"", length=None):
    """An Item (FFFE,E000) of PS3.5 Section 7.5.1."""
    length = len(content) if length is None else length
    return struct.pack("<HHI", 0xFFFE, 0xE000, length) + content


SEQUENCE_END = struct.pack("<HHI", 0xFFFE, 0xE0DD, 0)


def test_encapsulated_fragments_are_searched_for_every_form():
    # A JPEG comment (COM) segment in the first fragment.
    fragment = b"\xff\xd8\xff\xfe\x00\x12MARY\x00\x00" + PATIENT_ID.encode("utf-16-le")
    data = _file(
        _element(0x7FE00010, "OB", b"")[:-4]
        + struct.pack("<I", UNDEFINED)
        + _element_item()
        + _element_item(fragment)
        + SEQUENCE_END,
        "1.2.840.10008.1.2.4.50",
    )

    result = find_residuals(data, [_source("(0010,0010)", "PN", "MARY^Q"), ID_SOURCE])

    assert [(str(f.location), f.encoding) for f in result.findings] == [
        ("item 1 of data set element (7FE0,0010) (OB)", "utf-8"),
        ("item 1 of data set element (7FE0,0010) (OB)", "utf-16-le"),
    ]
    assert result.readable


def test_each_location_is_reported_once_by_its_widest_form():
    text = "QUILLON saw ZEBEDEE^QUILLON; ZEBEDEE^QUILLON again"
    data = _texts(text, "ZEBEDEE")

    result = find_residuals(data, [NAME_SOURCE])

    assert [(f.form, f.offset) for f in result.findings] == [
        (Form.VALUE, data.index(b"ZEBEDEE^QUILLON")),
        (Form.NAME_COMPONENT, data.rindex(b"ZEBEDEE")),
    ]


def test_the_same_value_from_two_instances_is_reported_once_per_place():
    # The subject's Patient's Name, from this instance and from another.
    data = _texts("ZEBEDEE^QUILLON")

    result = find_residuals(data, [NAME_SOURCE, NAME_SOURCE, ID_SOURCE])

    assert len(result.findings) == 1


# What is not searched, and robustness.


def test_short_and_non_distinctive_values_are_reported_not_searched():
    values = [
        _source("(0010,0040)", "CS", "F"),
        _source("(0010,1010)", "AS", "054Y"),
        _source("(0020,0010)", "SH", "123"),
        _source("(0008,0030)", "TM", "101500"),
        _source("(0010,1030)", "DS", "72.5"),
        _source("(0019,1001)", "OB", b"\x01\x02\x03\x04"),
        _source("(0010,0010)", "PN", "WU^LI"),
        _source("(0010,0010)", "PN", "LI^WU"),
        _source("(0010,0040)", "CS", "F"),
    ]

    result = find_residuals(_file(), values)

    assert [str(omission) for omission in result.not_searched] == [
        "CS from (0010,0040): value not searched: not distinctive",
        "AS from (0010,1010): value not searched: not distinctive",
        "SH from (0020,0010): value not searched: too short",
        "TM from (0008,0030): value not searched: not distinctive",
        "DS from (0010,1030): value not searched: not distinctive",
        "OB from (0019,1001): value not searched: binary",
        "PN from (0010,0010): name component not searched: too short",
    ]
    assert not result.findings
    assert residuals.MIN_CHARACTERS == 4


def test_every_vr_is_searched_or_reported():
    searched = {"AE", "DA", "DT", "LO", "LT", "PN", "SH", "ST", "UC", "UI", "UR", "UT"}
    binary = {"OB", "OD", "OF", "OL", "OV", "OW", "UN"}

    for vr in CHECKED_VRS:
        value = b"\x01\x02\x03\x04" if vr in binary else "ABCDEFGH"
        value = "20240517" if vr == "DT" else value  # a datetime needs a full date
        result = find_residuals(_file(), [_source("(0019,1001)", vr, value)])
        reasons = {omission.reason for omission in result.not_searched}
        if vr in searched:
            assert not reasons, vr
        else:
            assert reasons == {
                Omission.BINARY if vr in binary else Omission.NOT_DISTINCTIVE
            }


def test_a_match_across_a_chunk_boundary_is_found_once():
    data = _texts("prefix ZEBEDEE^QUILLON suffix")
    start = data.index(b"ZEBEDEE")
    expected = find_residuals(data, [NAME_SOURCE])

    for chunk in (start + 1, start + 7, start + 8, start + 14, 5, 1):
        with mock.patch.object(residuals, "CHUNK_BYTES", chunk):
            result = find_residuals(data, [NAME_SOURCE])
        assert result == expected, chunk
    assert [(f.form, f.offset) for f in expected.findings] == [(Form.VALUE, start)]


PIECES = [
    b"ZEBEDEE",
    b"^QUILLON",
    b"zq7741093",
    b"19710203",
    b"1971-02-03",
    b"7",
    b"x",
    b"\x00",
    b"\\",
    "ZEBEDEE".encode("utf-16-le"),
    STUDY_UID.encode(),
]


@hypothesis.settings(deadline=None)
@hypothesis.given(
    pieces=st.lists(st.sampled_from(PIECES), max_size=24),
    chunk=st.integers(1, 96),
)
def test_chunking_never_changes_the_result(pieces, chunk):
    value = b"".join(pieces)
    value += b"\x00" * (len(value) % 2)
    data = (
        _private(("LT", value), ("OB", value), ("OW", value), ("DS", value))
        + value[:-1]
    )
    expected = find_residuals(data, SOURCES)

    with mock.patch.object(residuals, "CHUNK_BYTES", chunk):
        result = find_residuals(data, SOURCES)

    assert result == expected


def test_unreadable_bytes_are_still_searched():
    # The element claims more bytes than the file holds, so reading stops.
    data = _file(struct.pack("<HH2sH", 0x0010, 0x0010, b"PN", 200) + NAME.encode())

    result = find_residuals(data, SOURCES)

    assert _summary(result) == [("(0010,0010)", Form.VALUE, "utf-8", Region.TRAILING)]
    assert str(result.findings[0].location) == "bytes after the last readable element"
    assert not result.readable


def test_a_file_without_the_dicm_prefix_is_searched_as_trailing_bytes():
    result = find_residuals(b"ZEBEDEE^QUILLON", SOURCES)

    assert _summary(result) == [("(0010,0010)", Form.VALUE, "utf-8", Region.TRAILING)]
    assert result.findings[0].offset == 0
    assert not result.readable


def test_a_deflated_data_set_is_refused():
    with pytest.raises(ValueError, match="deflated"):
        find_residuals(_file(bytes(8), "1.2.840.10008.1.2.1.99"), SOURCES)


def test_nothing_to_search_finds_nothing():
    data = _texts(NAME)

    result = find_residuals(data, [])

    assert result == residuals.ResidualSearch((), (), True)


INVALID = {
    "a source that is not a path": (("(0010,0010)", "PN", NAME), {}),
    "an unknown VR": ((_path("(0010,0010)"), "ZZ", NAME), {}),
    "VR SQ": ((_path("(0010,0010)"), "SQ", NAME), {}),
    "a VR that is not text": ((_path("(0010,0010)"), ["PN"], NAME), {}),
    "bytes for a searched VR": ((_path("(0010,0010)"), "PN", NAME.encode()), {}),
    "a number": ((_path("(0010,0010)"), "PN", 42), {}),
    "a lone surrogate": ((_path("(0010,0010)"), "PN", NAME + "\ud800"), {}),
    "codecs in a list": ((_path("(0010,0010)"), "PN", NAME), {"codecs": ["latin_1"]}),
    "an unknown codec": ((_path("(0010,0010)"), "PN", NAME), {"codecs": ("zz",)}),
    "a codec that is not ASCII": (
        (_path("(0010,0010)"), "PN", NAME),
        {"codecs": ("utf-16",)},
    ),
    "a codec that is not for text": (
        (_path("(0010,0010)"), "PN", NAME),
        {"codecs": ("base64",)},
    ),
}


@pytest.mark.parametrize("args, kwargs", INVALID.values(), ids=INVALID)
def test_invalid_source_values_are_rejected(args, kwargs):
    with pytest.raises(ValueError) as raised:
        SourceValue(*args, **kwargs)

    message = str(raised.value)
    assert "ZEBEDEE" not in message.upper()
    assert "QUILLON" not in message.upper()


def test_anything_but_source_values_is_rejected():
    with pytest.raises(TypeError, match="SourceValue"):
        find_residuals(_file(), [NAME])


# Constants that the engine writes whatever the source held.


def _written_constants():
    """A file holding each constant that the engine writes, in a private LT."""
    return _texts(*(value for _, value in residuals.written_constants()))


@pytest.mark.parametrize(
    "vr, value",
    [
        ("PN", "DEIDENTIFIED"),
        ("PN", "Deidentified^^"),
        ("PN", "DEIDENTIFIED^DEIDENTIFIED"),
        ("PN", "DE-IDENTIFIED^DE-IDENTIFIED"),
        ("LO", "DEIDENTIFIED"),
        ("LO", " deidentified\x00"),
        ("SH", "DE-IDENTIFIED"),
        ("LT", "DEIDENTIFIED"),
        ("UT", "DE-IDENTIFIED "),
        ("DA", "19000101"),
        ("DA", "1900.01.02"),
        ("DT", "19000101000000"),
        ("DT", "19000101000001+1000"),
        ("DT", "1900"),
        ("LO", "19000101"),
        ("SH", "99PYMEDPHYS"),
        ("LO", "PyMedPhys"),
        ("SH", "113100"),
        ("SH", "109104"),
        ("LO", "Basic Application Confidentiality Profile"),
        ("LO", "De-identifying Equipment"),
    ],
)
def test_a_source_value_equal_to_a_written_constant_is_skipped_and_recorded(vr, value):
    source = _source("(0010,1001)", vr, value)

    result = find_residuals(_written_constants(), [source])

    assert result.unsearched == (
        Unsearched(_path("(0010,1001)"), UnsearchedReason.WRITTEN_CONSTANT),
    )
    assert not result.findings
    assert not result.not_searched


@pytest.mark.parametrize(
    "vr, value",
    [
        ("PN", "DEIDENTIFIED^ZEBEDEE"),
        ("LO", "DEIDENTIFIED 2"),
        ("LO", "PyMedPhys DEIDENTIFIED"),
        ("DA", "19000103"),
        ("DT", "19000101000002"),
        ("SH", "1131000"),
    ],
)
def test_a_source_value_that_differs_from_every_constant_is_searched(vr, value):
    data = _texts(value, *(text for _, text in residuals.written_constants()))

    result = find_residuals(data, [_source("(0010,1001)", vr, value)])

    assert result.findings
    assert not result.unsearched


def test_a_constant_among_several_values_is_skipped_alone():
    values = [
        _source("(0010,1001)", "PN", "DEIDENTIFIED\\ZEBEDEE^QUILLON"),
        _source("(0010,1002)", "LO", "QUILLON\\DE-IDENTIFIED"),
    ]
    data = _texts("Mr Zebedee", "QUILLON", "DEIDENTIFIED", "DE-IDENTIFIED")

    result = find_residuals(data, values)

    # Only the elements of the name, (0019,1000), and of QUILLON, (0019,1001).
    assert {(str(f.source), f.location.element.tag) for f in result.findings} == {
        ("(0010,1001)", "(0019,1000)"),
        ("(0010,1001)", "(0019,1001)"),
        ("(0010,1002)", "(0019,1001)"),
    }
    assert [str(skip) for skip in result.unsearched] == [
        "(0010,1001): not searched: written constant",
        "(0010,1002): not searched: written constant",
    ]


def test_a_single_valued_text_is_not_split_into_constants():
    value = _source("(0008,4000)", "LT", "DEIDENTIFIED\\ZEBEDEE")

    result = find_residuals(_texts("DEIDENTIFIED\\ZEBEDEE"), [value])

    assert len(result.findings) == 1
    assert not result.unsearched


def test_a_value_of_constants_alone_is_dropped_and_recorded_once():
    values = [
        _source("(0010,1001)", "PN", "DEIDENTIFIED\\DE-IDENTIFIED"),
        _source("(0010,1001)", "PN", "DEIDENTIFIED"),
        NAME_SOURCE,
    ]

    result = find_residuals(_written_constants(), values)

    assert result.unsearched == (
        Unsearched(_path("(0010,1001)"), UnsearchedReason.WRITTEN_CONSTANT),
    )
    assert not result.findings


def test_values_that_are_not_searched_are_listed_even_when_equal_to_a_constant():
    values = [
        _source("(0012,0062)", "CS", "YES"),
        _source("(0010,1030)", "DS", "0"),
        _source("(0008,0030)", "TM", "000000"),
    ]

    result = find_residuals(_file(), values)

    assert [omission.reason for omission in result.not_searched] == [
        Omission.NOT_DISTINCTIVE
    ] * 3
    assert not result.unsearched


@pytest.mark.parametrize("vr", ["DA", "DT", "LO", "LT", "PN", "SH", "ST", "UC", "UT"])
def test_every_constant_that_d_writes_is_skipped(vr):
    key = DeidKey(bytes(32))
    vm = "1"
    for source in ([], [str(dummy_values.CONSTANTS[vr][0])]):
        (written,) = dummy_values.values_for_d(vr, vm, source, key)
        value = _source("(0010,1001)", vr, str(written))

        result = find_residuals(_file(), [value])

        assert [skip.reason for skip in result.unsearched] == [
            UnsearchedReason.WRITTEN_CONSTANT
        ]


def test_every_value_of_the_dummy_code_item_is_skipped():
    for source in ([], [{"(0008,0100)": "DEIDENTIFIED"}]):
        (item,) = dummy_values.items_for_d("(0040,1101)", source)
        values = [_source(element.tag, element.vr, element.value) for element in item]

        result = find_residuals(_file(), values)

        assert len(result.unsearched) == len(item)


# Privacy.


def _hidden():
    """A file with source values in every place the search covers."""
    dataset = pydicom.Dataset()
    dataset.preamble = NAME.encode().ljust(128, b"\x00")
    dataset.SpecificCharacterSet = "ISO_IR 100"
    dataset.add_new(0x00190010, "LO", "PRIVATE")
    dataset.add_new(0x00191001, "UN", "QUILLON Zebedee".encode("utf-16-le"))
    dataset.add_new(0x00191002, "LO", "MÜLLER, Jörg, 1971-02-03")
    dataset.add_new(0x00191003, "LO", f"{STUDY_UID} {ACCESSION}")
    dataset.DataSetTrailingPadding = PATIENT_ID.encode() + b"\x00"
    written = _write(dataset, SourceApplicationEntityTitle=PATIENT_ID)
    return written + "Li Wu".encode("utf-16-le")


PRIVATE_VALUES = (
    *SOURCES,
    _source("(0008,0090)", "PN", "MÜLLER^JÖRG", ("latin_1",)),
    _source("(0008,0050)", "SH", ACCESSION),
    _source("(0008,1070)", "PN", "WU^LI"),
    _source("(0010,0040)", "CS", "F"),
)


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_results_and_errors_never_contain_a_source_value(caplog):
    data = _hidden()
    secrets = [
        "ZEBEDEE",
        "QUILLON",
        PATIENT_ID,
        "19710203",
        "1971-02-03",
        STUDY_UID,
        "4417",
        ACCESSION,
        "MÜLLER",
        "JÖRG",
        "LI WU",
        "WU^LI",
    ]

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with caplog.at_level(logging.DEBUG):
            result = find_residuals(data, PRIVATE_VALUES)
            errors = []
            for args, kwargs in INVALID.values():
                try:
                    SourceValue(*args, **kwargs)
                except ValueError as error:
                    errors.append(str(error))

    assert len(result.findings) >= 9
    assert len(errors) == len(INVALID)
    text = "\n".join(
        [
            repr(result),
            *map(str, result.findings),
            *map(str, result.not_searched),
            *map(repr, PRIVATE_VALUES),
            json.dumps(dataclasses.asdict(result), default=lambda member: member.value),
            *errors,
        ]
    )
    for secret in secrets:
        for case in (secret, secret.lower(), secret.title()):
            assert case not in text
            for codec in ("utf-8", "latin-1", "utf-16-le"):
                assert case.encode(codec) not in text.encode("utf-8")
    assert not caught
    assert not caplog.records


# Clean, realistic de-identified files.


KEY = DeidKey(bytes(range(32)))
SOURCE_IMAGES = [f"{ROOT}.3.{number}" for number in range(1, 21)]
CLEAN_SOURCES = [
    NAME_SOURCE,
    ID_SOURCE,
    BIRTH_SOURCE,
    _source("(0008,0020)", "DA", STUDY_DATE),
    _source("(0008,0030)", "TM", "101500"),
    _source("(0008,0050)", "SH", ACCESSION),
    _source("(0008,0080)", "LO", "ARBORVALE INFIRMARY"),
    _source("(0008,0090)", "PN", "MORDRED^ALBERICH"),
    _source("(0010,0040)", "CS", "F"),
    STUDY_SOURCE,
    _source("(0020,000E)", "UI", f"{ROOT}.2.1"),
    _source("(0020,0052)", "UI", f"{ROOT}.4.1"),
    _source("(0008,0018)", "UI", SOURCE_IMAGES[0]),
    *(
        SourceValue(
            ElementPath(
                (
                    ("(3006,0010)", 0),
                    ("(3006,0012)", 0),
                    ("(3006,0014)", 0),
                    ("(3006,0016)", number),
                ),
                "(0008,1155)",
            ),
            "UI",
            uid,
        )
        for number, uid in enumerate(SOURCE_IMAGES)
    ),
]


def _patient_and_study(dataset):
    """Set the replacement values of the subject, study, and series."""
    identity = pseudonyms.SubjectIdentity.from_patient_id(PATIENT_ID)
    pseudonym = pseudonyms.patient_pseudonym(KEY, identity)
    dataset.PatientName = pseudonym.patients_name
    dataset.PatientID = pseudonym.patient_id
    dataset.PatientBirthDate = ""
    dataset.PatientSex = ""
    dataset.StudyDate = dates.shift_date(
        STUDY_DATE, dates.date_offset_weeks(KEY, identity)
    )
    dataset.StudyTime = ""
    dataset.AccessionNumber = ""
    dataset.ReferringPhysicianName = ""
    dataset.StudyInstanceUID = uids.replacement_uid(KEY, STUDY_UID)
    dataset.SeriesInstanceUID = uids.replacement_uid(KEY, f"{ROOT}.2.1")
    dataset.FrameOfReferenceUID = uids.replacement_uid(KEY, f"{ROOT}.4.1")


def _clean_ct(rng):
    dataset = pydicom.Dataset()
    dataset.SOPClassUID = pydicom.uid.CTImageStorage
    dataset.SOPInstanceUID = uids.replacement_uid(KEY, SOURCE_IMAGES[0])
    dataset.Modality = "CT"
    _patient_and_study(dataset)
    dataset.ImagePositionPatient = ["-250", "-250", "-112.5"]
    dataset.PixelSpacing = ["0.9765625", "0.9765625"]
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.Rows = dataset.Columns = 256
    dataset.BitsAllocated = 16
    dataset.BitsStored = 12
    dataset.HighBit = 11
    dataset.PixelRepresentation = 0
    dataset.RescaleIntercept = "-1024"
    dataset.RescaleSlope = "1"
    # Air, lung, and soft tissue, stored with an intercept of -1024.
    pixels = rng.choice([24, 200, 1064], size=(256, 256), p=[0.3, 0.3, 0.4])
    pixels = pixels + rng.normal(0, 40, size=pixels.shape)
    dataset.PixelData = np.clip(pixels, 0, 4095).astype("<u2").tobytes()
    return dataset


def _clean_structure_set(rng):
    dataset = pydicom.Dataset()
    dataset.SOPClassUID = pydicom.uid.RTStructureSetStorage
    dataset.SOPInstanceUID = uids.replacement_uid(KEY, f"{ROOT}.5.1")
    dataset.Modality = "RTSTRUCT"
    _patient_and_study(dataset)
    images = []
    for uid in SOURCE_IMAGES:
        image = pydicom.Dataset()
        image.ReferencedSOPClassUID = pydicom.uid.CTImageStorage
        image.ReferencedSOPInstanceUID = uids.replacement_uid(KEY, uid)
        images.append(image)
    series = pydicom.Dataset()
    series.SeriesInstanceUID = dataset.SeriesInstanceUID
    series.ContourImageSequence = images
    study = pydicom.Dataset()
    study.ReferencedSOPClassUID = "1.2.840.10008.3.1.2.3.1"
    study.ReferencedSOPInstanceUID = dataset.StudyInstanceUID
    study.RTReferencedSeriesSequence = [series]
    frame = pydicom.Dataset()
    frame.FrameOfReferenceUID = dataset.FrameOfReferenceUID
    frame.RTReferencedStudySequence = [study]
    dataset.ReferencedFrameOfReferenceSequence = [frame]
    contours = []
    for image in images:
        contour = pydicom.Dataset()
        contour.ContourImageSequence = [image]
        contour.ContourGeometricType = "CLOSED_PLANAR"
        points = rng.uniform(-250, 250, size=600)
        contour.NumberOfContourPoints = len(points) // 3
        contour.ContourData = [f"{point:.4f}" for point in points]
        contours.append(contour)
    roi = pydicom.Dataset()
    roi.ReferencedROINumber = 1
    roi.ContourSequence = contours
    dataset.ROIContourSequence = [roi]
    return dataset


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize("build", [_clean_ct, _clean_structure_set])
def test_a_clean_file_has_no_findings(build):
    dataset = build(np.random.default_rng(4417))
    data = _write(dataset, IMPLICIT)

    result = find_residuals(data, CLEAN_SOURCES)

    assert not result.findings
    assert result.readable
    assert [str(omission) for omission in result.not_searched] == [
        "TM from (0008,0030): value not searched: not distinctive",
        "CS from (0010,0040): value not searched: not distinctive",
    ]
    # The same file with the source Patient ID left in has a finding.
    dataset.PatientID = PATIENT_ID
    leaked = find_residuals(_write(dataset, IMPLICIT), CLEAN_SOURCES)
    assert [str(finding.location) for finding in leaked.findings] == [
        "data set element (0010,0020) (LO)"
    ]


# pydicom's test files, from several writers, which dcmwrite writes again
# with File Meta Information of its own.
PYDICOM_FILES = [
    "CT_small.dcm",
    "MR_small.dcm",
    "JPEG-lossy.dcm",
    "SC_rgb_jpeg_dcmtk.dcm",
    "rtplan.dcm",
    "rtdose.dcm",
]


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize("name", PYDICOM_FILES)
def test_files_from_other_writers_give_no_false_findings(name):
    source = pydicom.dcmread(pydicom.data.get_testdata_file(name))
    written = io.BytesIO()
    pydicom.dcmwrite(written, source, enforce_file_format=True)
    data = written.getvalue()
    own = _source("(0008,0018)", "UI", source.SOPInstanceUID)

    result = find_residuals(data, [*PRIVATE_VALUES, *CLEAN_SOURCES, own])

    assert result.readable
    # Only the instance's own UID, where the instance and its File Meta
    # Information hold it.
    assert [(str(f.source), str(f.location)) for f in result.findings] == [
        ("(0008,0018)", "File Meta Information element (0002,0003) (UI)"),
        ("(0008,0018)", "data set element (0008,0018) (UI)"),
    ]
