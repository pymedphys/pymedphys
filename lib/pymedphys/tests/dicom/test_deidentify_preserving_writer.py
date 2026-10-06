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

"""Write a de-identified data set from its source's bytes, and verify it.

Every source is synthetic and encoded by hand. Values that must never
appear in a message carry the text ``SENTINEL``.
"""

import io
import logging
import struct
import warnings

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import file_meta
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.preservation import (
    Expectations,
    PreservationFailed,
    PreservationReason,
    verify_preservation,
)
from pymedphys._dicom.deidentify.preserving_writer import (
    WriteReason,
    WriteRefused,
    write_data_set,
    write_file_bytes,
)
from pymedphys._dicom.deidentify.source import read_source

from .test_deidentify_file_layout import (
    EXPLICIT,
    IMPLICIT,
    ITEM_END,
    SEQUENCE_END,
    UNDEFINED,
    _explicit,
    _file,
    _implicit,
    _item,
)

pytestmark = pytest.mark.pydicom

RT_PLAN = b"1.2.840.10008.5.1.4.1.1.481.5\x00"
CT_IMAGE = b"1.2.840.10008.5.1.4.1.1.2\x00"
INSTANCE = b"2.25.100"
NAME = b"SENTINEL^NAME "
BEAM_TEXT = "SENTINEL BEAM Ü"
REPLACED_TEXT = "BEAM Ü"
# 4096 entries, the first mapped to -1024 HU, of 12 bits: SS (PS3.3
# C.11.2.1.1).
DESCRIPTOR = struct.pack("<HhH", 4096, -1024, 12)
CODECS = {"ISO_IR 192": "utf-8", "GB18030": "gb18030"}


def _path(*steps):
    return ElementPath(tuple(steps[:-1]), steps[-1])


def _encoder(explicit):
    def element(tag, vr, value=b"", length=None):
        if explicit:
            return _explicit(tag, vr, value, length)
        return _implicit(tag, value, length)

    return element


def _even(text, codec):
    value = text.encode(codec)
    return value + b" " * (len(value) % 2)


def _plan(explicit=True, character_set="ISO_IR 192"):
    """An RT Plan-like data set, with nested sequences of both length forms.

    The second beam's name inherits the top level's character set.
    """
    element = _encoder(explicit)
    beam_name = _even(BEAM_TEXT, CODECS[character_set])
    control_point = _item(element(0x300A0112, "IS", b"0 "))
    first_beam = (
        element(0x300A00C0, "IS", b"1 ")
        + element(0x300A00C2, "LO", b"SENTINEL")
        + element(0x300A0111, "SQ", control_point)  # defined lengths
    )
    beams = (
        element(0x300A00B0, "SQ", length=UNDEFINED)
        + _item(length=UNDEFINED)
        + first_beam
        + ITEM_END
        + _item(element(0x300A00C0, "IS", b"2 ") + element(0x300A00C2, "LO", beam_name))
        + SEQUENCE_END
    )
    referenced = _item(
        element(0x00081150, "UI", RT_PLAN) + element(0x00081155, "UI", INSTANCE)
    )
    data_set = (
        element(0x00080005, "CS", _even(character_set, "ascii"))
        + element(0x00080016, "UI", RT_PLAN)
        + element(0x00080018, "UI", INSTANCE)
        + element(0x00081140, "SQ", referenced)
        + element(0x00100010, "PN", NAME)
        + element(0x00100020, "LO", b"SENTINEL ID ")
        + element(0x00290010, "LO", b"SENTINEL CREATOR")
        + element(0x00291001, "UN", b"SENTINEL")
        + beams
    )
    return _file(EXPLICIT if explicit else IMPLICIT, data_set)


def _ct(voi_lut_vr="SQ"):
    """A CT image in Hounsfield Units, whose VOI LUT Descriptor is SS.

    With ``voi_lut_vr`` UN, VOI LUT Sequence is as a system without its
    dictionary entry sends it, with its items in implicit VR (PS3.5 6.2.2).
    """
    if voi_lut_vr == "UN":
        lut = _implicit(0x00283002, DESCRIPTOR)
    else:
        lut = _explicit(0x00283002, "SS", DESCRIPTOR)
    return _file(
        EXPLICIT,
        _explicit(0x00080016, "UI", CT_IMAGE)
        + _explicit(0x00080018, "UI", INSTANCE)
        + _explicit(0x00100010, "PN", NAME)
        + _explicit(0x00280103, "US", struct.pack("<H", 0))
        + _explicit(0x00281052, "DS", b"-1024 ")
        + _explicit(0x00281053, "DS", b"1 ")
        + _explicit(0x00283010, voi_lut_vr, _item(lut)),
    )


NAME_PATH = _path("(0010,0010)")
REMOVED_IDENTITY = _path("(0012,0062)")
FIRST_BEAM = ("(300A,00B0)", 0)
SECOND_BEAM = ("(300A,00B0)", 1)
CONTROL_POINT = (FIRST_BEAM, ("(300A,0111)", 0))


def _element(keyword, value):
    tag = pydicom.datadict.tag_for_keyword(keyword)
    # Unchecked, so that a value the writer must refuse can be built.
    return pydicom.DataElement(
        tag,
        pydicom.datadict.dictionary_VR(tag),
        value,
        validation_mode=pydicom.config.IGNORE,
    )


def _plan_edit(source):
    """Replace, remove, introduce, and keep, at the top level and in items."""
    replacements = {
        NAME_PATH: _element("PatientName", "PSEUDONYM"),
        REMOVED_IDENTITY: _element("PatientIdentityRemoved", "YES"),
        _path(SECOND_BEAM, "(300A,00C2)"): _element("BeamName", REPLACED_TEXT),
        _path(FIRST_BEAM, "(300A,00C3)"): _element("BeamDescription", "PLANNED"),
    }
    removed = {
        path
        for path in source.paths()
        if path.tag in ("(0010,0020)", "(0029,0010)", "(0029,1001)", "(0008,1140)")
        or path.items[:1] == (("(0008,1140)", 0),)
        or path.items == CONTROL_POINT  # leaves an empty item
    }
    kept = set(source.paths()) - removed - set(replacements)
    return frozenset(kept), frozenset(removed), replacements


def _with_source_meta(data, source, written):
    """The source's preamble and File Meta Information, then ``written``."""
    return data[: source.element(next(iter(source.paths()))).start] + written


def _written_and_verified(data, edit):
    source = read_source(data)
    kept, removed, replacements = edit(source)

    written = write_data_set(
        source, kept=kept, removed=removed, replacements=replacements
    )
    output = read_source(_with_source_meta(data, source, written))
    verify_preservation(
        source,
        output,
        Expectations(kept=kept, changed=frozenset(replacements), removed=removed),
    )
    return output, _with_source_meta(data, source, written)


@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize(
    "explicit, character_set",
    [(True, "ISO_IR 192"), (True, "GB18030"), (False, "ISO_IR 192")],
    ids=["explicit-utf-8", "explicit-gb18030", "implicit-utf-8"],
)
def test_a_written_plan_preserves_what_it_keeps(explicit, character_set):
    output, data = _written_and_verified(_plan(explicit, character_set), _plan_edit)

    dataset = pydicom.dcmread(io.BytesIO(data))
    assert dataset.PatientName == "PSEUDONYM"
    assert dataset.PatientIdentityRemoved == "YES"
    assert "PatientID" not in dataset
    assert "ReferencedImageSequence" not in dataset
    first, second = dataset.BeamSequence
    assert second.BeamName == REPLACED_TEXT
    assert first.BeamDescription == "PLANNED"
    assert [len(item) for item in first.ControlPointSequence] == [0]
    # Every kept sequence and item is written with an undefined length.
    for path in output.paths():
        if output.element(path).items is not None:
            assert output.element(path).undefined_length


def test_kept_text_keeps_its_inherited_bytes_and_new_text_takes_them():
    output, data = _written_and_verified(_plan(True, "GB18030"), _plan_edit)

    beam_name = output.value_field(_path(SECOND_BEAM, "(300A,00C2)"))
    assert beam_name == _even(REPLACED_TEXT, "gb18030")
    assert pydicom.dcmread(io.BytesIO(data)).BeamSequence[1].BeamName == REPLACED_TEXT


def _ct_edit(source):
    replacements = {NAME_PATH: _element("PatientName", "PSEUDONYM")}
    return frozenset(source.paths()) - {NAME_PATH}, frozenset(), replacements


@pytest.mark.parametrize("voi_lut_vr", ["SQ", "UN"])
def test_a_ct_voi_lut_descriptor_keeps_its_vr_and_bytes(voi_lut_vr):
    output, _ = _written_and_verified(_ct(voi_lut_vr), _ct_edit)

    descriptor = _path(("(0028,3010)", 0), "(0028,3002)")
    assert output.value_field(descriptor) == DESCRIPTOR
    assert output.element(_path("(0028,3010)")).vr == voi_lut_vr


@pytest.mark.usefixtures("pydicom_behaviour")
def test_pydicom_resolves_the_descriptor_again_where_this_writer_does_not():
    # The same edit through pydicom: once the data set has been walked, as
    # any walk of its elements does, pydicom writes VOI LUT Sequence as SQ,
    # and resolves the descriptor's VR from Pixel Representation as US,
    # although the input to the VOI LUT is in Hounsfield Units, so SS.
    data = _ct("UN")
    dataset = pydicom.dcmread(io.BytesIO(data))
    dataset.PatientName = "PSEUDONYM"
    list(dataset.iterall())
    written = io.BytesIO()
    file_meta.write_file(written, dataset, transfer_syntax_uid=EXPLICIT)
    source, output = read_source(data), read_source(written.getvalue())
    kept, removed, replacements = _ct_edit(source)

    descriptor = _path(("(0028,3010)", 0), "(0028,3002)")
    assert output.element(descriptor).vr == "US"
    with pytest.raises(PreservationFailed) as raised:
        verify_preservation(
            source,
            output,
            Expectations(kept=kept, changed=frozenset(replacements), removed=removed),
        )
    assert raised.value.reason is PreservationReason.VR

    _written_and_verified(data, _ct_edit)


@pytest.mark.usefixtures("pydicom_behaviour")
def test_the_file_has_new_file_meta_information():
    source = read_source(_ct())
    kept, removed, replacements = _ct_edit(source)
    data_set = write_data_set(
        source, kept=kept, removed=removed, replacements=replacements
    )

    data = write_file_bytes(
        data_set,
        sop_class_uid=CT_IMAGE.rstrip(b"\x00").decode(),
        sop_instance_uid="2.25.200",
        transfer_syntax_uid=EXPLICIT,
    )

    assert data[:128] == file_meta.PREAMBLE
    assert data.endswith(data_set)
    assert read_source(data).transfer_syntax == EXPLICIT
    dataset = pydicom.dcmread(io.BytesIO(data))
    assert dataset.file_meta.MediaStorageSOPInstanceUID == "2.25.200"
    assert (
        dataset.file_meta.ImplementationClassUID == file_meta.IMPLEMENTATION_CLASS_UID
    )
    assert dataset.PatientName == "PSEUDONYM"


def _tag(keyword):
    tag = pydicom.tag.Tag(pydicom.datadict.tag_for_keyword(keyword))
    return f"({tag.group:04X},{tag.elem:04X})"


@pytest.mark.usefixtures("pydicom_behaviour")
def test_an_introduced_sequence_is_written_with_its_items():
    data = _ct()
    source = read_source(data)
    item = pydicom.Dataset()
    item.CodeValue = "113100"
    item.CodingSchemeDesignator = "DCM"
    item.CodeMeaning = "Basic Application Confidentiality Profile"
    method = _path("(0012,0064)")
    sequence = pydicom.DataElement(0x00120064, "SQ", pydicom.Sequence([item]))
    kept = frozenset(source.paths())

    written = write_data_set(
        source, kept=kept, removed=frozenset(), replacements={method: sequence}
    )
    output = read_source(_with_source_meta(data, source, written))

    introduced = {method} | {
        _path(("(0012,0064)", 0), _tag(keyword))
        for keyword in ("CodeValue", "CodingSchemeDesignator", "CodeMeaning")
    }
    verify_preservation(
        source, output, Expectations(kept=kept, changed=frozenset(introduced))
    )
    dataset = pydicom.dcmread(io.BytesIO(_with_source_meta(data, source, written)))
    assert dataset[0x00120064].value[0].CodeValue == "113100"


def _refused(source, **plan):
    with pytest.raises(WriteRefused) as raised:
        write_data_set(source, **plan)
    assert "SENTINEL" not in str(raised.value)
    assert "SENTINEL" not in repr(raised.value)
    # Neither carries an exception from pydicom, whose message can quote a
    # value.
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    return raised.value.reason, raised.value.path


def test_an_element_without_a_plan_is_refused():
    source = read_source(_ct())

    assert _refused(
        source,
        kept=frozenset(source.paths()) - {NAME_PATH},
        removed=frozenset(),
        replacements={},
    ) == (WriteReason.UNPLANNED, NAME_PATH)


def test_an_element_introduced_where_nothing_is_written_is_refused():
    source = read_source(_plan())
    # Inside Referenced Image Sequence, which is removed.
    stray = _path(("(0008,1140)", 0), "(0008,1150)")
    removed = frozenset(
        path
        for path in source.paths()
        if path.tag == "(0008,1140)" or path.items[:1] == (("(0008,1140)", 0),)
    ) - {stray}

    assert _refused(
        source,
        kept=frozenset(source.paths()) - removed - {stray},
        removed=removed,
        replacements={stray: _element("ReferencedSOPClassUID", "1.2.3")},
    ) == (WriteReason.UNPLACED, stray)


@pytest.mark.parametrize(
    "element",
    [
        pydicom.DataElement(0x00100010, "US or SS", 1),
        pydicom.DataElement(0x00100020, "LO", "SENTINEL"),
    ],
    ids=["ambiguous-vr", "another-tag"],
)
def test_a_replacement_that_does_not_fit_its_place_is_refused(element):
    source = read_source(_ct())

    assert _refused(
        source,
        kept=frozenset(source.paths()) - {NAME_PATH},
        removed=frozenset(),
        replacements={NAME_PATH: element},
    ) == (WriteReason.ELEMENT, NAME_PATH)


def test_a_value_that_cannot_be_encoded_is_refused_without_quoting_it():
    source = read_source(_ct())

    assert _refused(
        source,
        kept=frozenset(source.paths()) - {NAME_PATH},
        removed=frozenset(),
        replacements={
            # Text where a number belongs, which pydicom's writer cannot pack.
            NAME_PATH: pydicom.DataElement(
                0x00100010, "FD", "SENTINEL", validation_mode=pydicom.config.IGNORE
            )
        },
    ) == (WriteReason.ENCODING, NAME_PATH)


def test_an_element_planned_twice_is_rejected():
    source = read_source(_ct())

    with pytest.raises(ValueError, match=r"\(0010,0010\)"):
        write_data_set(
            source,
            kept=frozenset(source.paths()),
            removed=frozenset({NAME_PATH}),
            replacements={},
        )


def test_a_kept_value_of_fragments_is_refused():
    # Encapsulated Document as fragments, which verification cannot show
    # preserved.
    fragments = (
        _explicit(0x00420011, "OB", length=UNDEFINED)
        + _item(b"SENTINEL")
        + SEQUENCE_END
    )
    source = read_source(_file(EXPLICIT, _explicit(0x00100010, "PN", NAME) + fragments))

    assert _refused(
        source, kept=frozenset(source.paths()), removed=frozenset(), replacements={}
    ) == (WriteReason.FRAGMENTS, _path("(0042,0011)"))


VOI_LUT_ITEM = ("(0028,3010)", 0)
EXPLANATION = _path(VOI_LUT_ITEM, "(0028,3003)")


def _ct_with_un_voi_lut():
    """A CT whose VOI LUT Sequence is UN, with its items in implicit VR."""
    lut = (
        _implicit(0x00283002, DESCRIPTOR)
        + _implicit(0x00283003, b"SENTINEL WINDOW ")
        + _implicit(0x00283006, struct.pack("<4H", 0, 1, 2, 3))
    )
    return _ct("UN").replace(
        _explicit(0x00283010, "UN", _item(_implicit(0x00283002, DESCRIPTOR))),
        _explicit(0x00283010, "UN", _item(lut)),
    )


def _pydicom_vrs(data):
    """Each element's VR as pydicom resolves it, once the data set is walked."""
    return {
        element.tag: element.VR
        for element in pydicom.dcmread(io.BytesIO(data)).iterall()
    }


@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize("explanation", ["WINDOW", ""], ids=["replaced", "emptied"])
def test_an_edit_inside_a_un_sequence_keeps_it_un_with_implicit_items(explanation):
    def edit(source):
        replacements = {EXPLANATION: _element("LUTExplanation", explanation)}
        return frozenset(source.paths()) - {EXPLANATION}, frozenset(), replacements

    data = _ct_with_un_voi_lut()
    output, written = _written_and_verified(data, edit)

    assert output.element(_path("(0028,3010)")).vr == "UN"
    assert output.element(EXPLANATION).vr is None
    assert output.value_field(_path(VOI_LUT_ITEM, "(0028,3002)")) == DESCRIPTOR
    dataset = pydicom.dcmread(io.BytesIO(written))
    list(dataset.iterall())
    assert dataset.VOILUTSequence[0].LUTExplanation == explanation
    # pydicom takes every VR in the items from its dictionary, for the output
    # as for the source, so it reads the descriptor as US from both.
    assert _pydicom_vrs(written) == _pydicom_vrs(data)
    assert _pydicom_vrs(written)[0x00283002] == "US"


@pytest.mark.parametrize(
    "path, element",
    [
        # US or SS, which a reader resolves itself where no VR is written.
        (
            _path(VOI_LUT_ITEM, "(0028,3002)"),
            pydicom.DataElement(0x00283002, "SS", [4096, -1024, 12]),
        ),
        # Not the VR that the dictionary gives, which a reader would use.
        (EXPLANATION, pydicom.DataElement(0x00283003, "SH", "WINDOW")),
    ],
    ids=["ambiguous", "another-vr"],
)
def test_a_replacement_whose_vr_a_reader_cannot_tell_is_refused(path, element):
    source = read_source(_ct_with_un_voi_lut())

    assert _refused(
        source,
        kept=frozenset(source.paths()) - {path},
        removed=frozenset(),
        replacements={path: element},
    ) == (WriteReason.IMPLICIT_VR, path)


def _all_but(source, replacements, removed=frozenset()):
    return {
        "kept": frozenset(source.paths()) - set(replacements) - removed,
        "removed": removed,
        "replacements": replacements,
    }


def _inside(source):
    return frozenset(each for each in source.paths() if each.items)


def test_items_from_pydicom_are_never_resolved_again():
    # A replaced VOI LUT Sequence taken from a view of the source, whose
    # items pydicom holds raw, with the descriptor's VR still to resolve.
    source = read_source(_ct("UN"))
    sequence = source.dataset()[0x00283010]
    voi_lut = _path("(0028,3010)")
    descriptor = _path(("(0028,3010)", 0), "(0028,3002)")
    plan = _all_but(source, {voi_lut: sequence}, _inside(source))

    assert _refused(source, **plan) == (WriteReason.ELEMENT, descriptor)
    # Held raw in explicit VR too, with its VR as written.
    explicit = read_source(_ct("SQ"))
    raw = {voi_lut: explicit.dataset()[0x00283010]}
    assert _refused(explicit, **_all_but(explicit, raw, _inside(explicit))) == (
        WriteReason.ELEMENT,
        descriptor,
    )

    item = pydicom.Dataset()
    item.add(pydicom.DataElement(0x00283002, "US or SS", [4096, 0, 12]))
    plan["replacements"] = {voi_lut: pydicom.DataElement(0x00283010, "SQ", [item])}
    assert _refused(source, **plan) == (WriteReason.ELEMENT, descriptor)


def _with_character_set(term):
    return _file(
        EXPLICIT,
        (_explicit(0x00080005, "CS", term) if term else b"")
        + _explicit(0x00100010, "PN", NAME),
    )


@pytest.mark.parametrize(
    "data, element",
    [
        (_with_character_set(b"ISO_IR 100"), _element("PatientName", "山田^太郎")),
        (_with_character_set(b""), _element("PatientName", "MÜLLER")),
        (_with_character_set(b"ISO_IR 999"), _element("PatientName", "MULLER")),
    ],
    ids=["cjk-in-latin-1", "non-ascii-in-the-default", "unknown-term"],
)
def test_text_that_cannot_be_written_in_its_character_set_is_refused(data, element):
    source = read_source(data)

    assert _refused(source, **_all_but(source, {NAME_PATH: element})) == (
        WriteReason.ENCODING,
        NAME_PATH,
    )


def test_a_default_repertoire_value_outside_iso_646_is_refused():
    source = read_source(_with_character_set(b"ISO_IR 192"))
    identity = _path("(0012,0062)")
    replacements = {
        NAME_PATH: _element("PatientName", "X"),
        identity: _element("PatientIdentityRemoved", "YÉS"),
    }

    assert _refused(source, **_all_but(source, replacements)) == (
        WriteReason.ENCODING,
        identity,
    )


@pytest.mark.parametrize(
    "path, element",
    [
        (_path("(0002,0016)"), pydicom.DataElement(0x00020016, "AE", "SENTINEL")),
        (_path("(0010,0000)"), pydicom.DataElement(0x00100000, "UL", 4)),
        (_path("(FFFE,E0DD)"), pydicom.DataElement(0xFFFEE0DD, "UN", b"")),
    ],
    ids=["file-meta", "group-length", "delimiter"],
)
def test_an_element_that_does_not_belong_in_a_data_set_is_refused(path, element):
    source = read_source(_ct())

    assert _refused(source, **_all_but(source, {path: element})) == (
        WriteReason.ELEMENT,
        path,
    )


def test_a_kept_group_length_is_refused():
    group_length = _explicit(0x00100000, "UL", struct.pack("<I", 16))
    source = read_source(
        _file(EXPLICIT, group_length + _explicit(0x00100010, "PN", NAME))
    )

    assert _refused(source, **_all_but(source, {})) == (
        WriteReason.ELEMENT,
        _path("(0010,0000)"),
    )


def test_a_value_that_pydicom_would_write_with_another_vr_is_refused():
    # pydicom writes an LT longer than its 16-bit length allows as UN.
    source = read_source(_ct())
    comments = _path("(0010,4000)")
    element = _element("PatientComments", "y" * 70000)

    assert _refused(source, **_all_but(source, {comments: element})) == (
        WriteReason.ELEMENT,
        comments,
    )


def test_a_replacement_of_undefined_length_without_items_is_refused():
    source = read_source(_ct())
    document = _path("(0042,0011)")
    element = pydicom.DataElement(0x00420011, "OB", b"\x00\x01")
    element.is_undefined_length = True

    assert _refused(source, **_all_but(source, {document: element})) == (
        WriteReason.ELEMENT,
        document,
    )


def test_a_kept_element_inside_a_removed_or_replaced_sequence_is_refused():
    source = read_source(_ct())
    voi_lut = _path("(0028,3010)")
    descriptor = _path(("(0028,3010)", 0), "(0028,3002)")

    removed = _all_but(source, {}, frozenset({voi_lut}))
    assert _refused(source, **removed) == (WriteReason.UNPLACED, descriptor)
    sequence = pydicom.DataElement(0x00283010, "SQ", [])
    replaced = _all_but(source, {voi_lut: sequence})
    assert _refused(source, **replaced) == (WriteReason.UNPLACED, descriptor)


def test_a_replaced_character_set_under_kept_text_is_refused():
    source = read_source(_with_character_set(b"ISO_IR 100"))
    character_set = pydicom.DataElement(0x00080005, "CS", "ISO_IR 192")

    assert _refused(
        source, **_all_but(source, {_path("(0008,0005)"): character_set})
    ) == (WriteReason.CHARACTER_SET, NAME_PATH)


@pytest.mark.parametrize("value", [None, ""], ids=["none", "empty"])
def test_a_replaced_character_set_without_a_value_is_the_default(value):
    data = _with_character_set(b"ISO_IR 192")
    source = read_source(data)
    replacements = {
        _path("(0008,0005)"): pydicom.DataElement(0x00080005, "CS", value),
        NAME_PATH: _element("PatientName", "PSEUDONYM"),
    }

    written = write_data_set(source, **_all_but(source, replacements))

    dataset = pydicom.dcmread(io.BytesIO(_with_source_meta(data, source, written)))
    assert dataset.PatientName == "PSEUDONYM"


def _private_items():
    """A private UN value of defined length that happens to read as items."""
    return _explicit(0x00090010, "LO", b"SENTINEL CREATOR") + _explicit(
        0x00091001, "UN", _item(_implicit(0x00091002, b"AB"))
    )


@pytest.mark.parametrize(
    "data",
    [
        _plan(True),
        _plan(False),
        _file(EXPLICIT, _private_items() + _explicit(0x00100010, "PN", NAME)),
        _file(
            EXPLICIT,
            _explicit(0x00100010, "PN", NAME) + _explicit(0xFFFCFFFC, "OB", bytes(6)),
        ),
    ],
    ids=["explicit", "implicit", "private-items", "trailing-padding"],
)
def test_a_data_set_kept_whole_is_copied_byte_for_byte(data):
    source = read_source(data)

    written = write_data_set(source, **_all_but(source, {}))

    assert _with_source_meta(data, source, written) == data


def test_an_introduced_sequence_in_implicit_vr_takes_a_replaced_character_set():
    data = _plan(False)
    source = read_source(data)
    item = pydicom.Dataset()
    item.CodeValue = "113100"
    item.CodingSchemeDesignator = "DCM"
    item.CodeMeaning = "Profile Ü"
    method = _path("(0012,0064)")
    texts = {
        path: _element("BeamName", "BEAM")
        for path in source.paths()
        if path.tag == "(300A,00C2)"
    }
    replacements = {
        _path("(0008,0005)"): pydicom.DataElement(0x00080005, "CS", "GB18030"),
        NAME_PATH: _element("PatientName", "PSEUDONYM"),
        method: pydicom.DataElement(0x00120064, "SQ", [item]),
        **texts,
    }
    removed = frozenset(
        path
        for path in source.paths()
        if path.tag in ("(0010,0020)", "(0029,0010)", "(0029,1001)")
    )

    written = write_data_set(source, **_all_but(source, replacements, removed))

    output = read_source(_with_source_meta(data, source, written))
    meaning = _path(("(0012,0064)", 0), "(0008,0104)")
    assert output.value_field(meaning) == _even("Profile Ü", "gb18030")
    assert output.element(method).vr is None


@pytest.mark.parametrize("step", ["data-set", "file-meta"])
def test_pydicom_diagnostics_while_writing_are_redacted(step, monkeypatch, caplog):
    # A replacement or a File Meta value can be quoted in a warning about its
    # encoding, and no caller need redact.
    sentinel = "ZZSENTINELZZ"
    name = "write_data_element" if step == "data-set" else "write_file_meta_info"
    write = getattr(pydicom.filewriter, name)

    def warn_and_write(*args, **kwargs):
        pydicom.misc.warn_and_log(f"bad value {sentinel}")
        return write(*args, **kwargs)

    monkeypatch.setattr(pydicom.filewriter, name, warn_and_write)
    caplog.set_level(logging.DEBUG, logger="pydicom")
    source = read_source(_ct())
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        data_set = write_data_set(
            source, **dict(zip(("kept", "removed", "replacements"), _ct_edit(source)))
        )
        write_file_bytes(
            data_set,
            sop_class_uid=CT_IMAGE.rstrip(b"\x00").decode(),
            sop_instance_uid="2.25.200",
            transfer_syntax_uid=EXPLICIT,
        )

    assert caught and caplog.records
    assert sentinel not in " ".join(str(each.message) for each in caught)
    assert sentinel not in caplog.text
