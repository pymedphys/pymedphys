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

"""The de-identification markers that every de-identified instance carries.

The expected markers are written out by hand from PS3.15 E.1.1, E.2, and
E.3.6, the codes of PS3.16 CID 7050 and CID 7005, and the SOP Common Module
of PS3.3, independently of the code under test. All data are synthetic.
"""

import copy
import dataclasses
import io
import itertools

from pymedphys._imports import pydicom, pytest

from pymedphys import _version
from pymedphys._dicom.deidentify import (
    codes,
    iods,
    markers,
    policy,
    policy_digest,
    standard,
    values,
)

# A digest of the right form, for tests in which its value does not matter.
DIGEST = "0123456789abcdef" * 4
CUSTOM_OPTIONS = ("retain_patient_characteristics", "retain_device_identity")

# PS3.16 CID 7050, written out by hand: each code's meaning, and the option
# each one names.
CID_7050 = {
    "113100": "Basic Application Confidentiality Profile",
    "113105": "Clean Descriptors Option",
    "113107": "Retain Longitudinal Temporal Information Modified Dates Option",
    "113108": "Retain Patient Characteristics Option",
    "113109": "Retain Device Identity Option",
    "113111": "Retain Safe Private Option",
}
OPTION_CODES = {
    "retain_safe_private": "113111",
    "retain_device_identity": "113109",
    "retain_patient_characteristics": "113108",
    "retain_longitudinal_modified_dates": "113107",
    "clean_descriptors": "113105",
}

# Each preset's claim in its readable value, its codes when every option is
# satisfied, and its Longitudinal Temporal Information Modified.
EXPECTED = {
    "basic": ("PS3.15 2026d", ["113100"], "REMOVED"),
    "basic-clean-descriptors": ("PS3.15 2026d", ["113100", "113105"], "REMOVED"),
    "tps-import": ("no PS3.15 claim", [], "MODIFIED"),
    "public-release": (
        "PS3.15 2026d",
        ["113100", "113111", "113107", "113105"],
        "MODIFIED",
    ),
}

MARKER_KEYWORDS = (
    "PatientIdentityRemoved",
    "DeidentificationMethod",
    "DeidentificationMethodCodeSequence",
    "LongitudinalTemporalInformationModified",
    "ContributingEquipmentSequence",
)
FIRST_RELEASE_IODS = ("CT Image", "RT Dose", "RT Structure Set", "RT Plan")
CONTRIBUTING_EQUIPMENT = "(0018,A001)"
PURPOSE_OF_REFERENCE = "(0040,A170)"


def _code_item(value, meaning):
    item = pydicom.Dataset()
    item.CodeValue = value
    item.CodingSchemeDesignator = "DCM"
    item.CodeMeaning = meaning
    return item


def _expected(readable, digest, code_values, temporal, version):
    """The markers' data set, built from pydicom's own dictionary."""
    expected = pydicom.Dataset()
    expected.PatientIdentityRemoved = "YES"
    expected.DeidentificationMethod = [readable, digest]
    if code_values:
        expected.DeidentificationMethodCodeSequence = [
            _code_item(value, CID_7050[value]) for value in code_values
        ]
    expected.LongitudinalTemporalInformationModified = temporal
    equipment = pydicom.Dataset()
    equipment.Manufacturer = "PyMedPhys"
    equipment.SoftwareVersions = version
    equipment.PurposeOfReferenceCodeSequence = [
        _code_item("109104", "De-identifying Equipment")
    ]
    expected.ContributingEquipmentSequence = [equipment]
    return expected


def _all_markers():
    """Every preset's markers, and a custom option set's, with every option satisfied."""
    found = {}
    for preset, options in policy.PRESETS.items():
        found[preset] = markers.markers_for(
            policy.compose_policy(preset), DIGEST, satisfied=options
        )
    found["custom"] = markers.markers_for(
        policy.compose_custom_policy(CUSTOM_OPTIONS), DIGEST, satisfied=CUSTOM_OPTIONS
    )
    return found


def _identifying_dataset():
    """A synthetic data set whose values stand for identifying source values."""
    dataset = pydicom.Dataset()
    dataset.PatientName = "Synthetic^Testpatient"
    dataset.PatientID = "SYN-0001"
    dataset.PatientBirthDate = "19700101"
    dataset.StudyDate = "20240229"
    dataset.InstitutionName = "Synthetic General Hospital"
    dataset.StudyDescription = "SYNTHETIC THORAX STUDY"
    dataset.Manufacturer = "Synthetic Linac Company"
    dataset.SoftwareVersions = "SYNTHETIC 9.9"
    dataset.SOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
    dataset.SOPInstanceUID = "2.25.1234567890"
    return dataset


def _strings(dataset):
    """Every text value in a data set, at any depth."""
    for element in dataset:
        if element.VR == "SQ":
            for item in element.value:
                yield from _strings(item)
        elif element.VM == 1:
            yield str(element.value)
        elif element.VM > 1:
            yield from (str(value) for value in element.value)


def _marker_strings(found):
    yield found.patient_identity_removed
    yield from found.method
    for code in (*found.method_codes, found.purpose_of_reference):
        yield from (code.code_value, code.scheme_designator, code.code_meaning)
    yield found.temporal_information_modified
    yield found.manufacturer
    yield found.software_versions


@pytest.mark.parametrize("preset", list(policy.PRESETS))
def test_each_preset_adds_exactly_its_markers(preset):
    composed = policy.compose_policy(preset)
    digest = policy_digest.policy_digest(composed)
    claim, code_values, temporal = EXPECTED[preset]
    version = _version.__version__

    marked = markers.apply_markers(
        pydicom.Dataset(),
        markers.markers_for(composed, digest, satisfied=policy.PRESETS[preset]),
    )

    readable = f"PyMedPhys {version}; {claim}; {preset}"
    assert marked == _expected(readable, digest, code_values, temporal, version)


def test_basic_clean_descriptors_claims_clean_descriptors_only_where_satisfied():
    composed = policy.compose_policy("basic-clean-descriptors")

    claimed = markers.markers_for(composed, DIGEST, satisfied=["clean_descriptors"])
    unclaimed = markers.markers_for(composed, DIGEST, satisfied=[])

    assert [code.code_value for code in claimed.method_codes] == ["113100", "113105"]
    assert [code.code_value for code in unclaimed.method_codes] == ["113100"]
    assert claimed.method == unclaimed.method
    assert unclaimed.method[0].endswith("; PS3.15 2026d; basic-clean-descriptors")


def test_a_custom_option_set_is_named_as_one_and_claims_its_satisfied_options():
    composed = policy.compose_custom_policy(CUSTOM_OPTIONS)
    version = _version.__version__

    marked = markers.apply_markers(
        pydicom.Dataset(),
        markers.markers_for(composed, DIGEST, satisfied=CUSTOM_OPTIONS),
    )

    readable = f"PyMedPhys {version}; PS3.15 2026d; custom option set"
    expected = _expected(
        readable, DIGEST, ["113100", "113109", "113108"], "REMOVED", version
    )
    assert marked == expected
    assert "custom option set" not in policy.PRESETS
    assert not any(" " in name for name in policy.PRESETS)


def test_a_custom_option_set_with_modified_dates_marks_dates_as_modified():
    options = ["retain_longitudinal_modified_dates"]
    found = markers.markers_for(
        policy.compose_custom_policy(options), DIGEST, satisfied=options
    )

    assert found.temporal_information_modified == "MODIFIED"
    assert [code.code_value for code in found.method_codes] == ["113100", "113107"]


def test_codes_follow_the_profile_in_table_e1_1s_order_of_options():
    composed = policy.compose_policy("public-release")

    found = markers.markers_for(
        composed, DIGEST, satisfied=list(reversed(policy.PRESETS["public-release"]))
    )

    assert [code.code_value for code in found.method_codes] == [
        "113100",
        "113111",
        "113107",
        "113105",
    ]


def test_tps_import_claims_no_ps3_15_conformance_and_adds_no_codes():
    composed = policy.compose_policy("tps-import")
    version = _version.__version__

    found = markers.markers_for(
        composed, DIGEST, satisfied=policy.PRESETS["tps-import"]
    )

    readable = found.method[0]
    assert readable == f"PyMedPhys {version}; no PS3.15 claim; tps-import"
    assert "2026d" not in readable
    assert not found.method_codes
    assert found.patient_identity_removed == "YES"
    assert found.temporal_information_modified == "MODIFIED"


@pytest.mark.parametrize("earlier", [None, [], ["113100"]])
def test_tps_import_keeps_earlier_codes_and_writes_no_empty_code_sequence(earlier):
    source = _identifying_dataset()
    if earlier is not None:
        source.DeidentificationMethodCodeSequence = [
            _code_item(value, CID_7050[value]) for value in earlier
        ]
    found = markers.markers_for(
        policy.compose_policy("tps-import"), DIGEST, satisfied=()
    )

    marked = markers.apply_markers(source, found)

    if earlier:
        assert marked.DeidentificationMethodCodeSequence == (
            source.DeidentificationMethodCodeSequence
        )
    else:
        assert "DeidentificationMethodCodeSequence" not in marked


def _legitimate_satisfied(preset):
    """Each list of satisfied options that a preset's instance can have.

    ``tps-import`` adds no codes, so any of its options can be satisfied.
    Under every other preset, each selected option is satisfied, except that
    Clean Descriptors can go unsatisfied.
    """
    options = policy.PRESETS[preset]
    subsets = itertools.chain.from_iterable(
        itertools.combinations(options, size) for size in range(len(options) + 1)
    )
    return [
        satisfied
        for satisfied in subsets
        if preset == "tps-import"
        or set(options) - {"clean_descriptors"} <= set(satisfied)
    ]


@pytest.mark.parametrize("preset", list(policy.PRESETS))
def test_patient_identity_removed_is_never_no(preset):
    composed = policy.compose_policy(preset)

    for satisfied in _legitimate_satisfied(preset):
        found = markers.markers_for(composed, DIGEST, satisfied=satisfied)
        assert found.patient_identity_removed == "YES"


def test_the_second_method_value_is_exactly_the_policy_digest():
    composed = policy.compose_policy("basic")
    digest = policy_digest.policy_digest(composed)

    found = markers.markers_for(composed, digest, satisfied=())

    assert found.method[1] == digest
    assert len(found.method) == 2


def test_every_code_is_a_row_of_the_pinned_context_groups():
    cid_7050 = codes.load_context_group(7050).rows
    cid_7005 = codes.load_context_group(7005).rows

    for found in _all_markers().values():
        for code in found.method_codes:
            assert code in cid_7050
        assert found.purpose_of_reference in cid_7005
        assert found.purpose_of_reference == codes.CodedConcept(
            "DCM", "109104", "De-identifying Equipment"
        )


def test_each_target_option_has_the_cid_7050_code_that_names_it():
    pinned = {
        row.code_value: row.code_meaning
        for row in codes.load_context_group(7050).rows
        if row.scheme_designator == "DCM"
    }

    assert set(markers.OPTION_CODES) == set(policy.TARGET_OPTIONS)
    assert dict(markers.OPTION_CODES) == OPTION_CODES
    assert markers.PROFILE_CODE == "113100"
    for value, meaning in CID_7050.items():
        assert pinned[value] == meaning
    # Clean Pixel Data and Clean Recognizable Visual Features are never claimed.
    assert {"113101", "113102"}.isdisjoint(markers.OPTION_CODES.values())


def _elements(dataset, path=()):
    for element in dataset:
        yield path, element
        if element.VR == "SQ":
            for item in element.value:
                yield from _elements(item, (*path, element.tag))


def test_every_marker_value_is_valid_for_its_vr_and_vm():
    dictionary = {
        attribute.tag: attribute
        for attribute in standard.load_data_dictionary().attributes
    }

    for found in _all_markers().values():
        marked = markers.apply_markers(pydicom.Dataset(), found)
        for _, element in _elements(marked):
            tag = f"({element.tag.group:04X},{element.tag.element:04X})"
            attribute = dictionary[tag]
            assert element.VR == attribute.vr
            if element.VR != "SQ":
                given = (
                    [element.value]
                    if isinstance(element.value, str)
                    else list(element.value)
                )
                assert values.values_problem(attribute.vr, attribute.vm, given) is None


@pytest.mark.parametrize("iod_name", FIRST_RELEASE_IODS)
def test_the_markers_are_defined_by_the_iod_and_the_equipment_item_is_complete(
    iod_name,
):
    iod = iods.load_iod_tables().iods[iod_name]
    found = markers.markers_for(policy.compose_policy("basic"), DIGEST, satisfied=())
    marked = markers.apply_markers(pydicom.Dataset(), found)
    (equipment,) = marked.ContributingEquipmentSequence
    (purpose,) = equipment.PurposeOfReferenceCodeSequence

    for keyword in MARKER_KEYWORDS:
        tag = marked.data_element(keyword).tag
        assert iod.lookup(f"({tag.group:04X},{tag.element:04X})")
    for path, item in (
        ((CONTRIBUTING_EQUIPMENT,), equipment),
        ((CONTRIBUTING_EQUIPMENT, PURPOSE_OF_REFERENCE), purpose),
    ):
        required = {
            definition.tag
            for definition in iod.definitions
            if definition.path == path and definition.type == "1"
        }
        present = {
            f"({element.tag.group:04X},{element.tag.element:04X})" for element in item
        }
        assert required
        assert required <= present
    # Code Value and Coding Scheme Designator are Type 1C, required where the
    # code has neither a Long Code Value nor a URN Code Value.
    assert {"CodeValue", "CodingSchemeDesignator", "CodeMeaning"} == set(purpose.dir())
    assert {
        "Manufacturer",
        "SoftwareVersions",
        "PurposeOfReferenceCodeSequence",
    } == set(equipment.dir())


def test_software_versions_and_the_readable_value_give_the_full_version(monkeypatch):
    version = "0.42.0.dev1+g1a2b"
    monkeypatch.setattr(_version, "__version__", version)

    found = markers.markers_for(policy.compose_policy("basic"), DIGEST, satisfied=())

    assert found.software_versions == version
    assert found.method[0] == f"PyMedPhys {version}; PS3.15 2026d; basic"
    assert found.manufacturer == "PyMedPhys"


LONGEST_VERSION = "10.100.10.dev10"  # 15 characters


def _policies():
    yield from (policy.compose_policy(preset) for preset in policy.PRESETS)
    yield policy.compose_custom_policy(CUSTOM_OPTIONS)


def test_every_version_of_up_to_15_characters_fits_every_readable_value(monkeypatch):
    monkeypatch.setattr(_version, "__version__", LONGEST_VERSION)
    assert len(LONGEST_VERSION) == 15

    lengths = {}
    for composed in _policies():
        readable = markers.markers_for(
            composed, DIGEST, satisfied=composed.options
        ).method[0]
        assert values.value_problem("LO", readable) is None
        lengths[composed.preset] = len(readable)

    assert max(lengths.values()) == 64
    assert lengths["basic-clean-descriptors"] == 64


def test_a_readable_value_that_would_not_fit_is_refused_not_shortened(monkeypatch):
    version = LONGEST_VERSION + "0"
    monkeypatch.setattr(_version, "__version__", version)
    composed = policy.compose_policy("basic-clean-descriptors")

    with pytest.raises(markers.MarkerError, match=r"\(0012,0063\)") as raised:
        markers.markers_for(composed, DIGEST, satisfied=())

    assert version not in str(raised.value)
    # The other presets' readable values are shorter, so they still fit.
    found = markers.markers_for(policy.compose_policy("basic"), DIGEST, satisfied=())
    assert found.method[0] == f"PyMedPhys {version}; PS3.15 2026d; basic"


def test_every_value_that_would_not_fit_is_reported(monkeypatch):
    monkeypatch.setattr(_version, "__version__", "1." + "0" * 63)

    with pytest.raises(markers.MarkerError) as raised:
        markers.markers_for(policy.compose_policy("basic"), DIGEST, satisfied=())

    assert "(0012,0063)" in str(raised.value)
    assert "(0018,1020)" in str(raised.value)


def test_a_marker_value_invalid_for_its_vr_is_refused(monkeypatch):
    monkeypatch.setattr(markers, "MANUFACTURER", "Py\\MedPhys")

    with pytest.raises(markers.MarkerError, match=r"\(0008,0070\)"):
        markers.markers_for(policy.compose_policy("basic"), DIGEST, satisfied=())


def _altered_context_group(code_value, **changes):
    def load(cid, path=None):
        table = codes.load_context_group(cid, path)
        rows = tuple(
            dataclasses.replace(row, **changes) if row.code_value == code_value else row
            for row in table.rows
            if changes or row.code_value != code_value
        )
        return dataclasses.replace(table, rows=rows)

    return load


@pytest.mark.parametrize("code_value", ["113100", "109104"])
def test_a_code_invalid_for_its_vr_is_refused(monkeypatch, code_value):
    monkeypatch.setattr(
        markers,
        "load_context_group",
        _altered_context_group(code_value, code_meaning="De\\identified"),
    )

    with pytest.raises(markers.MarkerError, match=r"\(0008,0104\)"):
        markers.markers_for(policy.compose_policy("basic"), DIGEST, satisfied=())


@pytest.mark.parametrize(
    "existing_method",
    [None, "", "SYNTHETIC TOOL 1", ["SYNTHETIC TOOL 1", "SYNTHETIC METHOD 2"]],
)
def test_existing_markers_and_contributing_equipment_items_are_kept(existing_method):
    source = _identifying_dataset()
    if existing_method is not None:
        source.DeidentificationMethod = existing_method
    earlier_code = _code_item("113100", CID_7050["113100"])
    source.DeidentificationMethodCodeSequence = [earlier_code]
    earlier_equipment = pydicom.Dataset()
    earlier_equipment.Manufacturer = "Synthetic Vendor"
    earlier_equipment.PurposeOfReferenceCodeSequence = [
        _code_item("109103", "Modifying Equipment")
    ]
    source.ContributingEquipmentSequence = [earlier_equipment]
    source.PatientIdentityRemoved = "NO"
    source.LongitudinalTemporalInformationModified = "MODIFIED"
    found = markers.markers_for(
        policy.compose_policy("basic-clean-descriptors"),
        DIGEST,
        satisfied=["clean_descriptors"],
    )
    alone = markers.apply_markers(pydicom.Dataset(), found)

    marked = markers.apply_markers(source, found)

    earlier = (
        []
        if not existing_method
        else [existing_method]
        if isinstance(existing_method, str)
        else existing_method
    )
    assert list(marked.DeidentificationMethod) == [*earlier, *found.method]
    assert list(marked.DeidentificationMethodCodeSequence) == [
        earlier_code,
        *alone.DeidentificationMethodCodeSequence,
    ]
    assert list(marked.ContributingEquipmentSequence) == [
        earlier_equipment,
        *alone.ContributingEquipmentSequence,
    ]
    assert marked.PatientIdentityRemoved == "YES"
    assert marked.LongitudinalTemporalInformationModified == "REMOVED"


def test_markers_added_to_marked_output_keep_the_earlier_markers():
    found = markers.markers_for(
        policy.compose_policy("public-release"),
        DIGEST,
        satisfied=policy.PRESETS["public-release"],
    )
    once = markers.apply_markers(_identifying_dataset(), found)

    twice = markers.apply_markers(once, found)

    assert list(twice.DeidentificationMethod)[:2] == list(once.DeidentificationMethod)
    for keyword in (
        "DeidentificationMethodCodeSequence",
        "ContributingEquipmentSequence",
    ):
        earlier = list(once.data_element(keyword).value)
        assert list(twice.data_element(keyword).value)[: len(earlier)] == earlier


@pytest.mark.parametrize(
    ("keyword", "vr", "value", "replace_un"),
    [
        # pydicom gives the element its dictionary VR but leaves the bytes.
        ("DeidentificationMethod", "UN", b"SYNTHETIC IDENTIFIER", True),
        ("DeidentificationMethod", "UN", b"SYNTHETIC IDENTIFIER", False),
        ("DeidentificationMethod", "UN", "SYNTHETIC IDENTIFIER", False),
        ("DeidentificationMethod", "UT", "SYNTHETIC IDENTIFIER", True),
        ("ContributingEquipmentSequence", "UN", b"SYNTHETIC IDENTIFIER", False),
    ],
    ids=["LO-bytes", "UN-bytes", "UN-text", "UT-text", "UN-sequence"],
)
def test_an_existing_marker_that_is_not_read_as_its_vr_is_refused_not_dropped(
    monkeypatch, keyword, vr, value, replace_un
):
    monkeypatch.setattr(pydicom.config, "replace_un_with_known_vr", replace_un)
    source = _identifying_dataset()
    tag = pydicom.datadict.tag_for_keyword(keyword)
    source.add_new(tag, vr, value)
    found = markers.markers_for(policy.compose_policy("basic"), DIGEST, satisfied=())

    with pytest.raises(markers.MarkerError) as raised:
        markers.apply_markers(source, found)

    assert "SYNTHETIC" not in str(raised.value)


def test_an_empty_existing_marker_of_another_vr_is_replaced():
    source = _identifying_dataset()
    source.add_new(
        pydicom.datadict.tag_for_keyword("DeidentificationMethod"), "UN", b""
    )
    found = markers.markers_for(policy.compose_policy("basic"), DIGEST, satisfied=())

    marked = markers.apply_markers(source, found)

    assert marked["DeidentificationMethod"].VR == "LO"
    assert list(marked.DeidentificationMethod) == list(found.method)


def test_the_markers_never_quote_a_source_value():
    source = _identifying_dataset()
    source.DeidentificationMethod = "SYNTHETIC TOOL 1"
    source_strings = set(_strings(source))
    found_markers = _all_markers()
    found = found_markers["public-release"]

    marked = markers.apply_markers(source, found)

    for each in found_markers.values():
        for text in _marker_strings(each):
            assert not any(value in text for value in source_strings)
    added = list(marked.DeidentificationMethod)[1:]
    assert added == list(found.method)
    alone = markers.apply_markers(pydicom.Dataset(), found)
    for keyword in MARKER_KEYWORDS:
        if keyword != "DeidentificationMethod":
            assert marked.data_element(keyword) == alone.data_element(keyword)


def test_nothing_but_the_markers_changes_and_the_source_is_untouched():
    source = _identifying_dataset()
    before = copy.deepcopy(source)
    found = markers.markers_for(policy.compose_policy("basic"), DIGEST, satisfied=())

    marked = markers.apply_markers(source, found)

    assert source == before
    assert marked is not source
    for keyword in MARKER_KEYWORDS:
        delattr(marked, keyword)
    assert marked == before


@pytest.mark.parametrize(
    "transfer_syntax",
    [pydicom.uid.ImplicitVRLittleEndian, pydicom.uid.ExplicitVRLittleEndian],
)
def test_the_marked_data_set_is_written_and_read_back_unchanged(
    pydicom_behaviour, transfer_syntax
):
    del pydicom_behaviour
    source = _identifying_dataset()
    source.file_meta = pydicom.dataset.FileMetaDataset()
    source.file_meta.TransferSyntaxUID = transfer_syntax
    found = markers.markers_for(
        policy.compose_policy("public-release"),
        DIGEST,
        satisfied=policy.PRESETS["public-release"],
    )
    marked = markers.apply_markers(source, found)
    buffer = io.BytesIO()

    pydicom.dcmwrite(buffer, marked, enforce_file_format=True)
    buffer.seek(0)
    read = pydicom.dcmread(buffer)

    for keyword in MARKER_KEYWORDS:
        assert read.data_element(keyword) == marked.data_element(keyword)


@pytest.mark.parametrize(
    "digest", ["A" * 64, "0" * 63, "0" * 65, "g" * 64, " " + "0" * 63, ""]
)
def test_a_malformed_digest_is_refused_without_quoting_it(digest):
    with pytest.raises(ValueError, match="64 lowercase hexadecimal digits") as raised:
        markers.markers_for(policy.compose_policy("basic"), digest, satisfied=())

    assert not digest or digest not in str(raised.value)


LONG_TEXT = "x" * 80


@pytest.mark.parametrize(
    ("changes", "error", "match"),
    [
        ({"patient_identity_removed": "NO"}, markers.MarkerError, r"\(0012,0062\)"),
        ({"patient_identity_removed": ""}, markers.MarkerError, r"\(0012,0062\)"),
        ({"method": (LONG_TEXT, DIGEST)}, markers.MarkerError, r"\(0012,0063\)"),
        (
            {"patient_identity_removed": "NO", "method": (LONG_TEXT, DIGEST)},
            markers.MarkerError,
            r"\(0012,0062\).*\(0012,0063\)",
        ),
        ({"method": ("SYNTHETIC",)}, markers.MarkerError, r"\(0012,0063\)"),
        (
            {"method": ("SYNTHETIC", DIGEST, DIGEST)},
            markers.MarkerError,
            r"\(0012,0063\)",
        ),
        (
            {"method": ("SYNTHETIC", "A" * 64)},
            ValueError,
            "64 lowercase hexadecimal digits",
        ),
        ({"method": ("SYNTHETIC", DIGEST.encode())}, TypeError, "digest must be text"),
        (
            {"temporal_information_modified": "modified"},
            markers.MarkerError,
            r"\(0028,0303\)",
        ),
        ({"manufacturer": "Py\\MedPhys"}, markers.MarkerError, r"\(0008,0070\)"),
        ({"software_versions": LONG_TEXT}, markers.MarkerError, r"\(0018,1020\)"),
        (
            {"method_codes": (codes.CodedConcept("DCM", "113100", LONG_TEXT),)},
            markers.MarkerError,
            r"\(0008,0104\)",
        ),
        (
            {"purpose_of_reference": codes.CodedConcept("DCM", "1\\09104", "Synth")},
            markers.MarkerError,
            r"\(0008,0100\)",
        ),
    ],
    ids=[
        "NO",
        "empty-identity-removed",
        "long-readable-value",
        "NO-and-long-readable-value",
        "one-method-value",
        "three-method-values",
        "upper-case-digest",
        "bytes-digest",
        "lower-case-temporal",
        "backslash-manufacturer",
        "long-software-versions",
        "long-code-meaning",
        "backslash-code-value",
    ],
)
def test_markers_changed_after_markers_for_are_refused_before_they_are_written(
    monkeypatch, changes, error, match
):
    found = markers.markers_for(
        policy.compose_policy("public-release"),
        DIGEST,
        satisfied=policy.PRESETS["public-release"],
    )
    changed = dataclasses.replace(found, **changes)

    def never(*args):
        raise AssertionError("an attribute was written")

    monkeypatch.setattr(markers, "_set", never)

    with pytest.raises(error, match=match) as raised:
        markers.apply_markers(_identifying_dataset(), changed)

    assert LONG_TEXT not in str(raised.value)
    assert "A" * 64 not in str(raised.value)


def test_arguments_of_the_wrong_type_are_refused():
    basic = policy.compose_policy("basic")
    found = markers.markers_for(basic, DIGEST, satisfied=())

    with pytest.raises(TypeError, match="Policy"):
        markers.markers_for(object(), DIGEST, satisfied=())
    with pytest.raises(TypeError, match="digest"):
        markers.markers_for(basic, DIGEST.encode(), satisfied=())
    with pytest.raises(TypeError, match="single string"):
        markers.markers_for(
            policy.compose_policy("basic-clean-descriptors"),
            DIGEST,
            satisfied="clean_descriptors",
        )
    with pytest.raises(TypeError, match="Dataset"):
        markers.apply_markers({}, found)
    with pytest.raises(TypeError, match="Markers"):
        markers.apply_markers(pydicom.Dataset(), object())


def test_an_option_that_the_policy_does_not_select_cannot_be_satisfied():
    with pytest.raises(ValueError, match="retain_safe_private"):
        markers.markers_for(
            policy.compose_policy("basic-clean-descriptors"),
            DIGEST,
            satisfied=["clean_descriptors", "retain_safe_private"],
        )


def _compose(selected):
    """A preset's policy, or a custom option set's."""
    if isinstance(selected, str):
        return policy.compose_policy(selected)
    return policy.compose_custom_policy(selected)


@pytest.mark.parametrize(
    ("selected", "satisfied", "missing"),
    [
        # The codes would claim that the Basic Profile removed the dates that
        # Modified Dates shifted, and contradict MODIFIED.
        (
            "public-release",
            ["retain_safe_private", "clean_descriptors"],
            ["retain_longitudinal_modified_dates"],
        ),
        (
            "public-release",
            [],
            ["retain_safe_private", "retain_longitudinal_modified_dates"],
        ),
        # The codes would claim the Basic Profile alone, which removes the
        # Device Serial Number that Retain Device Identity keeps.
        (("retain_device_identity",), [], ["retain_device_identity"]),
        (
            CUSTOM_OPTIONS,
            ["retain_device_identity"],
            ["retain_patient_characteristics"],
        ),
    ],
)
def test_a_satisfied_list_that_leaves_out_a_selected_option_is_refused(
    selected, satisfied, missing
):
    with pytest.raises(ValueError, match="leaves out") as raised:
        markers.markers_for(_compose(selected), DIGEST, satisfied=satisfied)

    message = str(raised.value)
    for option in missing:
        assert option in message
    for option in set(satisfied) - {"clean_descriptors"}:
        assert option not in message
    assert not isinstance(raised.value, markers.MarkerError)


@pytest.mark.parametrize(
    ("preset", "satisfied", "code_values", "temporal"),
    [
        ("basic-clean-descriptors", [], ["113100"], "REMOVED"),
        (
            "public-release",
            ["retain_safe_private", "retain_longitudinal_modified_dates"],
            ["113100", "113111", "113107"],
            "MODIFIED",
        ),
    ],
)
def test_clean_descriptors_is_the_one_selected_option_that_can_go_unsatisfied(
    preset, satisfied, code_values, temporal
):
    found = markers.markers_for(
        policy.compose_policy(preset), DIGEST, satisfied=satisfied
    )

    assert [code.code_value for code in found.method_codes] == code_values
    assert found.temporal_information_modified == temporal


def test_tps_import_needs_no_option_satisfied_and_least_of_all_its_unmet_one():
    composed = policy.compose_policy("tps-import")
    unmet = {option for resolved in composed.resolved for option in resolved.unmet}
    assert unmet == {"retain_device_identity"}
    met = [option for option in composed.options if option not in unmet]

    for satisfied in ([], ["retain_patient_characteristics"], met):
        found = markers.markers_for(composed, DIGEST, satisfied=satisfied)
        assert not found.method_codes
        assert found.temporal_information_modified == "MODIFIED"


def test_an_option_that_the_policy_records_as_unmet_is_never_required(monkeypatch):
    # Only tps-import records an unmet option, and it claims no conformance,
    # so a policy that claims conformance is simulated to check that the
    # unmet option is left out of the required ones in its own right.
    monkeypatch.setattr(
        policy.Policy, "claims_conformance", property(lambda self: True)
    )
    composed = policy.compose_policy("tps-import")

    found = markers.markers_for(
        composed,
        DIGEST,
        satisfied=[
            "retain_patient_characteristics",
            "retain_longitudinal_modified_dates",
        ],
    )
    with pytest.raises(ValueError, match="leaves out") as raised:
        markers.markers_for(composed, DIGEST, satisfied=[])

    assert [code.code_value for code in found.method_codes] == [
        "113100",
        "113108",
        "113107",
    ]
    assert "retain_patient_characteristics" in str(raised.value)
    assert "retain_device_identity" not in str(raised.value)


def test_a_policy_with_an_option_that_has_no_code_is_refused():
    outside = dataclasses.replace(
        policy.compose_policy("basic"), options=("retain_uids",)
    )

    with pytest.raises(ValueError, match="retain_uids have no code"):
        markers.markers_for(outside, DIGEST, satisfied=())


def test_a_policy_that_resolves_a_conflict_by_keeping_the_value_gets_no_markers():
    tps_import = policy.compose_policy("tps-import")
    keeping = dataclasses.replace(
        tps_import,
        resolved=tuple(
            dataclasses.replace(conflict, action="K")
            for conflict in tps_import.resolved
        ),
    )

    with pytest.raises(markers.MarkerError, match="Patient Identity Removed"):
        markers.markers_for(keeping, DIGEST, satisfied=())


@pytest.mark.parametrize(("cid", "code_value"), [(7050, "113100"), (7005, "109104")])
def test_codes_are_taken_from_the_dcm_coding_scheme_only(monkeypatch, cid, code_value):
    def with_a_local_code_first(group, path=None):
        table = codes.load_context_group(group, path)
        local = codes.CodedConcept("99SYN", code_value, "Synthetic Local Code")
        return dataclasses.replace(table, rows=(local, *table.rows))

    monkeypatch.setattr(markers, "load_context_group", with_a_local_code_first)

    found = markers.markers_for(policy.compose_policy("basic"), DIGEST, satisfied=())

    chosen = found.method_codes[0] if cid == 7050 else found.purpose_of_reference
    assert chosen == codes.CodedConcept("DCM", code_value, chosen.code_meaning)
    assert chosen.code_meaning != "Synthetic Local Code"


@pytest.mark.parametrize(("cid", "code_value"), [(7050, "113100"), (7005, "109104")])
def test_a_code_missing_from_the_pinned_context_group_is_refused(
    monkeypatch, cid, code_value
):
    monkeypatch.setattr(
        markers, "load_context_group", _altered_context_group(code_value)
    )

    with pytest.raises(
        standard.StandardTableError, match=f"CID {cid} has no code DCM {code_value}"
    ):
        markers.markers_for(policy.compose_policy("basic"), DIGEST, satisfied=())
