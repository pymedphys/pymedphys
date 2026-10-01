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

"""The File Meta Information and preamble written in place of the source's."""

import importlib
import inspect
import io
import re
import struct

from pymedphys._imports import hypothesis, pydicom, pytest

import pymedphys
from pymedphys import _version
from pymedphys._dicom import uid as pymedphys_uid
from pymedphys._dicom.deidentify import file_meta, keys, uid_registry, uids, values

st = hypothesis.strategies

IMPLICIT_LE = "1.2.840.10008.1.2"
EXPLICIT_LE = "1.2.840.10008.1.2.1"
RT_PLAN_STORAGE = "1.2.840.10008.5.1.4.1.1.481.5"
CT_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.2"
# An invented key and source instance under the invented root 1.2.840.99999,
# and the source UID's replacement.
FIXTURE_KEY = keys.DeidKey(bytes(range(32)))
SOURCE_SOP_INSTANCE_UID = "1.2.840.99999.2.55.3.604688119.868.1234567890.1"
REPLACEMENT_UID = uids.replacement_uid(FIXTURE_KEY, SOURCE_SOP_INSTANCE_UID)

# The Implementation Class UID, as documented. It never changes.
DOCUMENTED_IMPLEMENTATION_CLASS_UID = "1.2.826.0.1.3680043.10.188.1.1"
# The seven elements, in order, with their VRs from PS3.6 Table 7-1, where
# each has VM 1.
EXPECTED_ELEMENTS = [
    (0x00020000, "UL"),
    (0x00020001, "OB"),
    (0x00020002, "UI"),
    (0x00020003, "UI"),
    (0x00020010, "UI"),
    (0x00020012, "UI"),
    (0x00020013, "SH"),
]
# The VRs whose explicit VR encoding has two reserved bytes and a 4-byte
# length (PS3.5 Section 7.1.2); every other VR has a 2-byte length.
LONG_LENGTH_VRS = frozenset(
    {"OB", "OD", "OF", "OL", "OV", "OW", "SQ", "SV", "UC", "UN", "UR", "UT", "UV"}
)
# Where the elements after the group length start: after the 128-byte
# preamble, the 4-byte prefix, and the 12-byte group length element (tag, VR,
# 2-byte length, and 4-byte value).
AFTER_GROUP_LENGTH = 128 + 4 + 12

# File Meta elements and a preamble that a source file might hold, all
# invented, none of which may reach the output.
SOURCE_FILE_META = {
    0x00020012: ("UI", "1.2.840.99999.4.1"),
    0x00020013: ("SH", "FIXTURE_WRITER"),
    0x00020016: ("AE", "FIXTURE_SOURCE"),
    0x00020017: ("AE", "FIXTURE_SENDER"),
    0x00020018: ("AE", "FIXTURE_RECEIVER"),
    0x00020026: ("UR", "dicom:fixture-source.invalid:104"),
    0x00020027: ("UR", "dicom:fixture-sender.invalid:11112"),
    0x00020028: ("UR", "http://fixture-receiver.invalid:80/wado-rs/"),
    0x00020100: ("UI", "1.2.840.99999.4.2"),
    0x00020102: ("OB", b"FIXTURE PRIVATE INFORMATION!"),
}
SOURCE_PREAMBLE = b"FIXTURE PREAMBLE".ljust(128, b"#")

valid_uids = st.from_regex(uid_registry.UID_PATTERN, fullmatch=True).filter(
    lambda value: len(value) <= 64
)


def _meta(
    sop_class_uid=RT_PLAN_STORAGE,
    sop_instance_uid=REPLACEMENT_UID,
    transfer_syntax_uid=EXPLICIT_LE,
):
    return file_meta.file_meta_information(
        sop_class_uid=sop_class_uid,
        sop_instance_uid=sop_instance_uid,
        transfer_syntax_uid=transfer_syntax_uid,
    )


def _dataset(sop_class_uid=RT_PLAN_STORAGE, sop_instance_uid=REPLACEMENT_UID):
    dataset = pydicom.dataset.Dataset()
    dataset.SOPClassUID = sop_class_uid
    dataset.SOPInstanceUID = sop_instance_uid
    dataset.Modality = "RTPLAN"
    return dataset


def _written(dataset, transfer_syntax_uid=EXPLICIT_LE):
    buffer = io.BytesIO()
    file_meta.write_file(buffer, dataset, transfer_syntax_uid=transfer_syntax_uid)
    return buffer.getvalue()


def _raw_file_meta(data):
    """Return each File Meta element of a file as (tag, VR, value bytes).

    The elements are read as PS3.10 Section 7.1 lays them out, independently
    of pydicom: after the preamble and prefix, in Explicit VR Little Endian,
    up to the first element of another group. Also return the offset at
    which they end.
    """
    position = 132
    elements = []
    while True:
        group, element = struct.unpack_from("<HH", data, position)
        if group != 0x0002:
            return elements, position
        vr = data[position + 4 : position + 6].decode("ascii")
        if vr in LONG_LENGTH_VRS:
            (length,) = struct.unpack_from("<L", data, position + 8)
            start = position + 12
        else:
            (length,) = struct.unpack_from("<H", data, position + 6)
            start = position + 8
        elements.append((group << 16 | element, vr, data[start : start + length]))
        position = start + length


def _bytes_after_group_length(data):
    _, end = _raw_file_meta(data)
    return end - AFTER_GROUP_LENGTH


def _padded(value, pad):
    encoded = value.encode("ascii")
    return encoded + pad * (len(encoded) % 2)


def test_the_implementation_class_uid_is_the_first_uid_of_the_reserved_arc():
    root = pymedphys_uid.PYMEDPHYS_ROOT_UID
    arc = pymedphys_uid.PYMEDPHYS_FIXED_UID_ARC

    assert root == "1.2.826.0.1.3680043.10.188"
    assert arc == f"{root}.1"
    assert file_meta.IMPLEMENTATION_CLASS_UID == f"{arc}.1"
    assert file_meta.IMPLEMENTATION_CLASS_UID.startswith(f"{root}.")
    assert file_meta.IMPLEMENTATION_CLASS_UID == DOCUMENTED_IMPLEMENTATION_CLASS_UID


def test_the_implementation_class_uid_is_a_valid_ui_value():
    assert uid_registry.is_uid(file_meta.IMPLEMENTATION_CLASS_UID)
    assert len(file_meta.IMPLEMENTATION_CLASS_UID) <= 64
    assert values.value_problem("UI", file_meta.IMPLEMENTATION_CLASS_UID) is None


def test_a_generated_pymedphys_uid_never_falls_under_the_reserved_arc():
    # A generated UID is the root and one component, whereas a UID under the
    # arc has at least two components after the root.
    root = pymedphys_uid.PYMEDPHYS_ROOT_UID
    arc = pymedphys_uid.PYMEDPHYS_FIXED_UID_ARC

    for _ in range(200):
        generated = pymedphys_uid.generate_uid()

        assert generated.startswith(f"{root}.")
        assert re.fullmatch(r"0|[1-9][0-9]*", generated.removeprefix(f"{root}."))
        assert not generated.startswith(f"{arc}.")
        assert values.value_problem("UI", generated) is None


@pytest.mark.parametrize(
    "source_uid",
    [
        "1.2.840.10008.5.1.4.1.1.2",
        "1.2.826.0.1.3680043.10.188.1.1",
        "2.25.34576644949241753017331973314513799820",
        "9" * 64,
    ],
)
def test_a_pseudonymised_pymedphys_uid_never_falls_under_the_reserved_arc(
    source_uid,
):
    # Experimental pseudonymisation also writes UIDs under the root, as the
    # root and one component made from a hash of the source UID.
    from pymedphys._experimental.pseudonymisation import (  # pylint: disable = import-outside-toplevel
        strategy,
    )

    root = pymedphys_uid.PYMEDPHYS_ROOT_UID
    arc = pymedphys_uid.PYMEDPHYS_FIXED_UID_ARC

    # pylint: disable = protected-access
    pseudonymised = strategy._pseudonymise_UI(source_uid)

    assert pseudonymised.startswith(f"{root}.")
    assert re.fullmatch(r"0|[1-9][0-9]*", pseudonymised.removeprefix(f"{root}."))
    assert not pseudonymised.startswith(f"{arc}.")


def test_the_preamble_is_128_zero_bytes():
    assert file_meta.PREAMBLE == bytes(128)
    assert isinstance(file_meta.PREAMBLE, bytes)


@pytest.mark.parametrize(
    "version, name",
    [
        pytest.param("0.4.2", "PYMEDPHYS 0.4.2", id="fits"),
        pytest.param("0.42.0", "PYMEDPHYS 0.42.0", id="exactly-16"),
        pytest.param("1.dev0", "PYMEDPHYS 1.dev0", id="development-that-fits"),
        pytest.param("1!0", "PYMEDPHYS 1!0", id="epoch"),
        # The characters either side of the backslash, and at either end of
        # the visible characters of the default repertoire.
        pytest.param("1[0", "PYMEDPHYS 1[0", id="left-square-bracket"),
        pytest.param("1]0", "PYMEDPHYS 1]0", id="right-square-bracket"),
        pytest.param("1~0", "PYMEDPHYS 1~0", id="tilde"),
        pytest.param("0.42.10", "PYMEDPHYS", id="17-characters"),
        pytest.param("0.42.0.dev1", "PYMEDPHYS", id="development"),
        pytest.param("0.42.0rc1", "PYMEDPHYS", id="pre-release"),
        pytest.param("1.0+abc", "PYMEDPHYS", id="local"),
        pytest.param("2026.10.1234567", "PYMEDPHYS", id="long"),
        pytest.param("", "PYMEDPHYS", id="empty"),
        pytest.param(" 1.0", "PYMEDPHYS", id="leading-space"),
        pytest.param("1.0 ", "PYMEDPHYS", id="trailing-space"),
        pytest.param("1 0", "PYMEDPHYS", id="space"),
        pytest.param("1\\0", "PYMEDPHYS", id="backslash"),
        pytest.param("1.0\n", "PYMEDPHYS", id="line-feed"),
        pytest.param("1.0\x7f", "PYMEDPHYS", id="delete"),
        pytest.param("1.0é", "PYMEDPHYS", id="not-ascii"),
    ],
)
def test_the_implementation_version_name_holds_the_version_where_it_fits(version, name):
    assert file_meta.implementation_version_name(version) == name


def test_a_version_that_fits_exactly_fills_the_16_characters_of_sh():
    assert len(file_meta.implementation_version_name("0.42.0")) == 16


@hypothesis.given(st.text())
def test_the_implementation_version_name_is_always_valid_sh(version):
    name = file_meta.implementation_version_name(version)

    assert values.value_problem("SH", name) is None
    assert len(name) <= 16
    # PS3.10 limits it to the ISO 646 basic G0 set, the default repertoire.
    assert all(" " <= character <= "~" for character in name)
    # SH leading and trailing spaces are not significant, so there are none.
    assert name == name.strip(" ")
    assert name in ("PYMEDPHYS", f"PYMEDPHYS {version}")


@hypothesis.given(st.from_regex(r"[0-9a-z.+!_-]{1,12}", fullmatch=True))
def test_a_version_is_included_exactly_when_it_fits(version):
    included = file_meta.implementation_version_name(version) != "PYMEDPHYS"

    assert included == (len(version) <= 6)


def test_the_installed_version_name_is_derived_from_the_package_version():
    assert file_meta.IMPLEMENTATION_VERSION_NAME == (
        file_meta.implementation_version_name(pymedphys.__version__)
    )


def test_the_installed_version_name_follows_the_package_version(monkeypatch):
    # A development version gives "PYMEDPHYS" alone, so load the module again
    # as a released version would.
    monkeypatch.setattr(_version, "__version__", "0.42.0")
    try:
        reloaded = importlib.reload(file_meta)
        assert reloaded.IMPLEMENTATION_VERSION_NAME == "PYMEDPHYS 0.42.0"
    finally:
        monkeypatch.undo()
        importlib.reload(file_meta)
    assert file_meta.IMPLEMENTATION_VERSION_NAME == (
        file_meta.implementation_version_name(pymedphys.__version__)
    )


def test_the_file_meta_information_holds_exactly_the_seven_elements_in_order():
    meta = _meta()

    assert isinstance(meta, pydicom.dataset.FileMetaDataset)
    assert [(element.tag, element.VR) for element in meta] == EXPECTED_ELEMENTS
    for element in meta:
        assert values.values_problem(element.VR, "1", [element.value]) is None


def test_the_file_meta_information_holds_the_given_and_documented_values():
    meta = _meta()

    assert meta.FileMetaInformationVersion == b"\x00\x01"
    assert meta.MediaStorageSOPClassUID == RT_PLAN_STORAGE
    assert meta.MediaStorageSOPInstanceUID == REPLACEMENT_UID
    assert meta.TransferSyntaxUID == EXPLICIT_LE
    assert meta.ImplementationClassUID == DOCUMENTED_IMPLEMENTATION_CLASS_UID
    assert meta.ImplementationVersionName == file_meta.implementation_version_name(
        pymedphys.__version__
    )


def test_the_file_meta_information_names_the_installed_version(monkeypatch):
    # Every development version gives "PYMEDPHYS" alone, so stand in a
    # released version's name, of another length.
    monkeypatch.setattr(file_meta, "IMPLEMENTATION_VERSION_NAME", "PYMEDPHYS 9.8.7")

    meta = _meta()
    data = _written(_dataset())

    assert meta.ImplementationVersionName == "PYMEDPHYS 9.8.7"
    assert meta.FileMetaInformationGroupLength == _bytes_after_group_length(data)
    assert pydicom.dcmread(io.BytesIO(data)).file_meta == meta


def test_each_call_gives_new_file_meta_information():
    first = _meta()
    first.MediaStorageSOPInstanceUID = "1.2.3"

    assert _meta().MediaStorageSOPInstanceUID == REPLACEMENT_UID


@pytest.mark.parametrize(
    "sop_class_uid, sop_instance_uid, transfer_syntax_uid",
    [
        pytest.param(RT_PLAN_STORAGE, REPLACEMENT_UID, EXPLICIT_LE, id="odd-lengths"),
        pytest.param(CT_IMAGE_STORAGE, "2.25.123", IMPLICIT_LE, id="even-instance"),
        pytest.param("1.2", "1.2.3.4", EXPLICIT_LE, id="short"),
        pytest.param("1." + "2" * 62, "1." + "3" * 61, IMPLICIT_LE, id="longest"),
    ],
)
def test_the_group_length_counts_the_bytes_of_the_elements_after_it(
    sop_class_uid, sop_instance_uid, transfer_syntax_uid
):
    meta = _meta(sop_class_uid, sop_instance_uid, transfer_syntax_uid)
    data = _written(_dataset(sop_class_uid, sop_instance_uid), transfer_syntax_uid)

    elements, _ = _raw_file_meta(data)

    assert elements[0][:2] == (0x00020000, "UL")
    assert meta.FileMetaInformationGroupLength == _bytes_after_group_length(data)
    assert struct.unpack("<L", elements[0][2]) == (_bytes_after_group_length(data),)


@pytest.mark.parametrize("transfer_syntax_uid", [IMPLICIT_LE, EXPLICIT_LE])
def test_a_written_file_has_a_zero_preamble_and_exactly_the_built_elements(
    transfer_syntax_uid,
):
    meta = _meta(transfer_syntax_uid=transfer_syntax_uid)
    data = _written(_dataset(), transfer_syntax_uid)

    elements, _ = _raw_file_meta(data)

    assert data[:128] == bytes(128)
    assert data[128:132] == b"DICM"
    assert [element[:2] for element in elements] == EXPECTED_ELEMENTS
    assert [element[2] for element in elements[1:]] == [
        b"\x00\x01",
        _padded(RT_PLAN_STORAGE, b"\x00"),
        _padded(REPLACEMENT_UID, b"\x00"),
        _padded(transfer_syntax_uid, b"\x00"),
        _padded(file_meta.IMPLEMENTATION_CLASS_UID, b"\x00"),
        _padded(meta.ImplementationVersionName, b" "),
    ]
    # The Implementation Class UID has an even length, so it is written as it
    # is documented, without a padding byte, unlike the odd-length SOP Class
    # UID.
    assert elements[5] == (
        0x00020012,
        "UI",
        DOCUMENTED_IMPLEMENTATION_CLASS_UID.encode("ascii"),
    )
    assert elements[2][2] == RT_PLAN_STORAGE.encode("ascii") + b"\x00"


@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize("transfer_syntax_uid", [IMPLICIT_LE, EXPLICIT_LE])
def test_a_written_file_reads_back_with_the_same_file_meta_information(
    tmp_path, transfer_syntax_uid
):
    dataset = _dataset()
    path = tmp_path / "instance.dcm"

    file_meta.write_file(path, dataset, transfer_syntax_uid=transfer_syntax_uid)
    read = pydicom.dcmread(path)

    assert read.preamble == bytes(128)
    assert read.file_meta == _meta(transfer_syntax_uid=transfer_syntax_uid)
    assert [(element.tag, element.VR) for element in read.file_meta] == (
        EXPECTED_ELEMENTS
    )
    assert read.original_encoding == (transfer_syntax_uid == IMPLICIT_LE, True)
    assert pydicom.dataset.Dataset(read) == dataset


@hypothesis.given(valid_uids, valid_uids, st.sampled_from([IMPLICIT_LE, EXPLICIT_LE]))
def test_any_valid_uids_are_written_and_read_back_unchanged(
    sop_class_uid, sop_instance_uid, transfer_syntax_uid
):
    meta = _meta(sop_class_uid, sop_instance_uid, transfer_syntax_uid)
    data = _written(_dataset(sop_class_uid, sop_instance_uid), transfer_syntax_uid)

    assert meta.FileMetaInformationGroupLength == _bytes_after_group_length(data)
    assert pydicom.dcmread(io.BytesIO(data)).file_meta == meta


def _source_file():
    """Return an invented source file whose File Meta Information is identifying."""
    dataset = _dataset(sop_instance_uid=SOURCE_SOP_INSTANCE_UID)
    dataset.file_meta = pydicom.dataset.FileMetaDataset()
    dataset.file_meta.TransferSyntaxUID = EXPLICIT_LE
    for tag, (vr, value) in SOURCE_FILE_META.items():
        dataset.file_meta.add_new(tag, vr, value)
    dataset.preamble = SOURCE_PREAMBLE
    buffer = io.BytesIO()
    pydicom.dcmwrite(buffer, dataset, enforce_file_format=True)
    return pydicom.dcmread(io.BytesIO(buffer.getvalue()))


def test_the_source_file_holds_every_identifying_element():
    source = _source_file()

    assert source.preamble == SOURCE_PREAMBLE
    for tag, (_, value) in SOURCE_FILE_META.items():
        assert source.file_meta[tag].value == value


@pytest.mark.usefixtures("pydicom_behaviour")
def test_no_source_file_meta_element_or_preamble_is_written():
    source = _source_file()
    source_meta, source_preamble = source.file_meta, source.preamble
    source.SOPInstanceUID = REPLACEMENT_UID

    data = _written(source)
    read = pydicom.dcmread(io.BytesIO(data))

    assert [element.tag for element in read.file_meta] == [
        tag for tag, _ in EXPECTED_ELEMENTS
    ]
    assert read.file_meta == _meta()
    assert read.preamble == bytes(128)
    for _, value in SOURCE_FILE_META.values():
        encoded = value if isinstance(value, bytes) else value.encode("ascii")
        assert encoded not in data
    assert SOURCE_PREAMBLE[:16] not in data
    assert SOURCE_SOP_INSTANCE_UID.encode("ascii") not in data
    # The data set given is not changed.
    assert source.file_meta is source_meta
    assert source.preamble is source_preamble
    assert source.file_meta[0x00020016].value == "FIXTURE_SOURCE"


def test_the_arguments_are_keyword_only():
    parameters = inspect.signature(file_meta.file_meta_information).parameters

    assert list(parameters) == [
        "sop_class_uid",
        "sop_instance_uid",
        "transfer_syntax_uid",
    ]
    for parameter in parameters.values():
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is inspect.Parameter.empty
    with pytest.raises(TypeError):
        # pylint: disable-next = too-many-function-args, missing-kwoa
        file_meta.file_meta_information(RT_PLAN_STORAGE, REPLACEMENT_UID, EXPLICIT_LE)


ATTRIBUTES = {
    "sop_class_uid": "SOP Class UID",
    "sop_instance_uid": "SOP Instance UID",
    "transfer_syntax_uid": "Transfer Syntax UID",
}
MALFORMED_UIDS = {
    "empty": "",
    "none": None,
    "bytes": REPLACEMENT_UID.encode("ascii"),
    "multi-value": [REPLACEMENT_UID, REPLACEMENT_UID],
    "leading-zero": "1.2.840.99999.0123",
    "empty-component": "1.2.840..99999",
    "trailing-period": "1.2.840.99999.",
    "nul-padding": "1.2.840.99999.4\x00",
    "space-padding": "1.2.840.99999.4 ",
    "65-characters": "1.2.840.99999." + "1" * 51,
    "letter": "1.2.840.99999.4a",
    "full-width-digit": "1.2.840.99999.\N{FULLWIDTH DIGIT TWO}",
    "line-feed": "1.2.840.99999.4\n",
}


@pytest.mark.parametrize(
    "attribute, name, value",
    [
        pytest.param(attribute, name, value, id=f"{attribute}-{label}")
        for attribute, name in ATTRIBUTES.items()
        for label, value in MALFORMED_UIDS.items()
    ],
)
def test_a_malformed_uid_is_rejected_without_quoting_it(attribute, name, value):
    arguments = {
        "sop_class_uid": RT_PLAN_STORAGE,
        "sop_instance_uid": REPLACEMENT_UID,
        "transfer_syntax_uid": EXPLICIT_LE,
        attribute: value,
    }

    with pytest.raises(ValueError) as raised:
        file_meta.file_meta_information(**arguments)

    message = str(raised.value)
    assert name in message
    if value:
        assert str(value) not in message
        assert repr(value) not in message


@pytest.mark.parametrize(
    "transfer_syntax_uid",
    [
        pytest.param("1.2.840.10008.1.2.2", id="explicit-big-endian"),
        pytest.param("1.2.840.10008.1.2.1.99", id="deflated"),
        pytest.param("1.2.840.10008.1.2.4.50", id="jpeg-baseline"),
        pytest.param("1.2.840.10008.1.2.4.90", id="jpeg-2000-lossless"),
        pytest.param("1.2.840.10008.1.2.5", id="rle"),
        pytest.param("1.2.840.99999.1.2.1", id="private"),
        pytest.param(RT_PLAN_STORAGE, id="sop-class"),
    ],
)
def test_an_unsupported_transfer_syntax_is_rejected_without_quoting_it(
    transfer_syntax_uid,
):
    with pytest.raises(ValueError) as raised:
        _meta(transfer_syntax_uid=transfer_syntax_uid)

    message = str(raised.value)
    assert "Transfer Syntax UID" in message
    assert transfer_syntax_uid not in message


@pytest.mark.parametrize(
    "keyword, name",
    [
        pytest.param("SOPClassUID", "SOP Class UID", id="sop-class"),
        pytest.param("SOPInstanceUID", "SOP Instance UID", id="sop-instance"),
    ],
)
@pytest.mark.parametrize("problem", ["missing", "malformed", "multi-valued"])
def test_a_data_set_without_a_valid_uid_is_not_written(keyword, name, problem):
    dataset = _dataset()
    if problem == "missing":
        delattr(dataset, keyword)
    elif problem == "malformed":
        with pytest.warns(UserWarning, match="Invalid value for VR UI"):
            setattr(dataset, keyword, "1.2.840.99999.0123")
    else:
        setattr(dataset, keyword, [REPLACEMENT_UID, REPLACEMENT_UID])
    buffer = io.BytesIO()

    with pytest.raises(ValueError) as raised:
        file_meta.write_file(buffer, dataset, transfer_syntax_uid=EXPLICIT_LE)

    assert name in str(raised.value)
    assert "0123" not in str(raised.value)
    assert not buffer.getvalue()


def test_an_unsupported_transfer_syntax_is_not_written():
    buffer = io.BytesIO()

    with pytest.raises(ValueError):
        file_meta.write_file(
            buffer, _dataset(), transfer_syntax_uid="1.2.840.10008.1.2.2"
        )

    assert not buffer.getvalue()
