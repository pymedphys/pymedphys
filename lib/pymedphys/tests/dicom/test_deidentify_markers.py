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

# The tests share the hand-written expected markers and synthetic data sets
# below, so they stay in one module.
# pylint: disable = too-many-lines

import copy
import dataclasses
import importlib
import io
import itertools
import platform
import struct
import warnings

from pymedphys._imports import pydicom, pytest, tomlkit

from pymedphys import _version
from pymedphys._dicom.deidentify import (
    codes,
    iods,
    markers,
    method_digest,
    policy,
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


def _software_versions(version):
    """PyMedPhys's version, then the running Python, pydicom, and tomlkit.

    Taken from the interpreter and the libraries themselves, independently
    of the code under test.
    """
    return [
        version,
        f"{platform.python_implementation()} {platform.python_version()}",
        f"pydicom {pydicom.__version__}",
        f"tomlkit {tomlkit.__version__}",
    ]


def _expected(readable, digest, code_values, temporal, version):
    """The markers' data set, built from pydicom's own dictionary."""
    expected = pydicom.Dataset()
    expected.PatientIdentityRemoved = "YES"
    expected.DeidentificationMethod = [digest, readable]
    if code_values:
        expected.DeidentificationMethodCodeSequence = [
            _code_item(value, CID_7050[value]) for value in code_values
        ]
    expected.LongitudinalTemporalInformationModified = temporal
    equipment = pydicom.Dataset()
    equipment.Manufacturer = "PyMedPhys"
    equipment.SoftwareVersions = _software_versions(version)
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
    yield from found.software_versions


@pytest.mark.parametrize("preset", list(policy.PRESETS))
def test_each_preset_adds_exactly_its_markers(preset):
    composed = policy.compose_policy(preset)
    digest = method_digest.method_digest(composed, vocabulary=None)
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
    assert unclaimed.method[1].endswith("; PS3.15 2026d; basic-clean-descriptors")


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

    readable = found.method[1]
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


def test_the_first_method_value_is_exactly_the_method_digest():
    composed = policy.compose_policy("basic")
    digest = method_digest.method_digest(composed, vocabulary=None)

    found = markers.markers_for(composed, digest, satisfied=())

    assert found.method[0] == digest
    assert found.method[1] == f"PyMedPhys {_version.__version__}; PS3.15 2026d; basic"
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

    assert found.software_versions[0] == version
    assert found.method[1] == f"PyMedPhys {version}; PS3.15 2026d; basic"
    assert found.manufacturer == "PyMedPhys"


# A synthetic value for each source of Software Versions after PyMedPhys's
# version, by module and attribute.
SYNTHETIC_RUNTIME = {
    "platform.python_implementation": "PyPy",
    "platform.python_version": "3.11.9",
    "pydicom.__version__": "3.1.0.dev0",
    "tomlkit.__version__": "0.13.2",
}
# With "tomlkit ", 64 characters, as many as LO allows.
LONGEST_LIBRARY_VERSION = "1." + "0" * 54
# Software Versions that end in a value as long as LO allows, with 7, 11, 18,
# and 64 characters and three backslashes: 103 in all, odd, so that the
# padding space follows the last value.
ODD_SOFTWARE_VERSIONS = (
    "0.42.10",
    "PyPy 3.11.9",
    "pydicom 3.1.0.dev0",
    f"tomlkit {LONGEST_LIBRARY_VERSION}",
)


def _with_runtime(monkeypatch, runtime):
    """Make the interpreter and the libraries give other versions.

    Each name is a module and one of its attributes, such as
    ``"platform.python_version"``, and the function or value it names is
    replaced by one that gives the value, as an upgrade would change it.
    """
    for name, value in runtime.items():
        module_name, attribute = name.rsplit(".", 1)
        module = importlib.import_module(module_name)
        if callable(getattr(module, attribute)):
            monkeypatch.setattr(module, attribute, lambda value=value: value)
        else:
            monkeypatch.setattr(module, attribute, value)


def test_software_versions_give_pymedphys_then_python_pydicom_and_tomlkit(
    monkeypatch,
):
    monkeypatch.setattr(_version, "__version__", "0.42.0")
    _with_runtime(monkeypatch, SYNTHETIC_RUNTIME)
    expected = ["0.42.0", "PyPy 3.11.9", "pydicom 3.1.0.dev0", "tomlkit 0.13.2"]

    found = markers.markers_for(policy.compose_policy("basic"), DIGEST, satisfied=())
    (equipment,) = markers.apply_markers(
        pydicom.Dataset(), found
    ).ContributingEquipmentSequence

    assert list(found.software_versions) == expected
    element = equipment["SoftwareVersions"]
    assert (element.VR, element.VM, list(element.value)) == ("LO", 4, expected)
    assert values.values_problem("LO", "1-n", expected) is None
    assert found.method[1] == "PyMedPhys 0.42.0; PS3.15 2026d; basic"


def test_software_versions_give_the_running_python_pydicom_and_tomlkit():
    found = markers.markers_for(policy.compose_policy("basic"), DIGEST, satisfied=())
    (equipment,) = markers.apply_markers(
        pydicom.Dataset(), found
    ).ContributingEquipmentSequence

    expected = _software_versions(_version.__version__)
    assert list(found.software_versions) == expected
    assert list(equipment.SoftwareVersions) == expected
    assert expected[1].split(" ") == [
        platform.python_implementation(),
        platform.python_version(),
    ]


@pytest.mark.parametrize(
    ("source", "value", "position", "expected"),
    [
        (
            "platform.python_implementation",
            "SyntheticPython",
            1,
            "SyntheticPython {python_version}",
        ),
        ("platform.python_version", "3.99.0", 1, "{python_implementation} 3.99.0"),
        ("pydicom.__version__", "9.9.9.dev9", 2, "pydicom 9.9.9.dev9"),
        ("tomlkit.__version__", "9.9.9.dev9", 3, "tomlkit 9.9.9.dev9"),
    ],
    ids=["python-implementation", "python-version", "pydicom", "tomlkit"],
)
def test_each_source_of_software_versions_changes_its_own_value(
    monkeypatch, source, value, position, expected
):
    composed = policy.compose_policy("basic")
    running = list(
        markers.markers_for(composed, DIGEST, satisfied=()).software_versions
    )
    expected = expected.format(
        python_implementation=platform.python_implementation(),
        python_version=platform.python_version(),
    )
    _with_runtime(monkeypatch, {source: value})

    found = markers.markers_for(composed, DIGEST, satisfied=())

    assert running[position] != expected
    assert list(found.software_versions) == [
        *running[:position],
        expected,
        *running[position + 1 :],
    ]


def test_python_and_library_versions_change_software_versions_not_the_digest(
    monkeypatch,
):
    composed = policy.compose_policy("basic")

    def mark(dataset):
        # The engine's files and tables are read once per process, so they
        # are read again, as in another process.
        # pylint: disable = protected-access
        method_digest._file_digests.cache_clear()
        method_digest._table_digests.cache_clear()
        digest = method_digest.method_digest(composed, vocabulary=None)
        found = markers.markers_for(composed, digest, satisfied=())
        return markers.apply_markers(dataset, found)

    first = mark(pydicom.Dataset())
    _with_runtime(
        monkeypatch,
        {
            "platform.python_implementation": "SyntheticPython",
            "platform.python_version": "3.99.0",
            "pydicom.__version__": "9.9.9.dev9",
            "tomlkit.__version__": "9.9.9.dev9",
        },
    )
    second = mark(pydicom.Dataset())
    again = mark(first)

    assert list(second.DeidentificationMethod) == list(first.DeidentificationMethod)
    (first_equipment,) = first.ContributingEquipmentSequence
    (second_equipment,) = second.ContributingEquipmentSequence
    assert list(second_equipment.SoftwareVersions) == [
        _version.__version__,
        "SyntheticPython 3.99.0",
        "pydicom 9.9.9.dev9",
        "tomlkit 9.9.9.dev9",
    ]
    assert list(first_equipment.SoftwareVersions) == _software_versions(
        _version.__version__
    )
    # Output marked again in another runtime keeps one pair, and gains that
    # runtime's equipment item.
    assert list(again.DeidentificationMethod) == list(first.DeidentificationMethod)
    assert list(again.ContributingEquipmentSequence) == [
        first_equipment,
        second_equipment,
    ]


def test_a_library_version_too_long_for_lo_is_refused_not_shortened(monkeypatch):
    composed = policy.compose_policy("basic")
    # With "pydicom ", 64 characters, as many as LO allows.
    longest = "1." + "0" * 54
    too_long = longest + "0"

    _with_runtime(monkeypatch, {**SYNTHETIC_RUNTIME, "pydicom.__version__": longest})
    found = markers.markers_for(composed, DIGEST, satisfied=())
    _with_runtime(monkeypatch, {**SYNTHETIC_RUNTIME, "pydicom.__version__": too_long})
    with pytest.raises(markers.MarkerError, match=r"\(0018,1020\)") as raised:
        markers.markers_for(composed, DIGEST, satisfied=())

    assert found.software_versions[2] == f"pydicom {longest}"
    assert len(found.software_versions[2]) == 64
    assert too_long not in str(raised.value)


# With "PyMedPhys ", "; PS3.15 2026d; ", and "basic-clean-descriptors", 63
# characters: one fewer than LO allows, so that the padding that can follow
# the readable value still fits.
LONGEST_VERSION = "10.100.10.dev1"  # 14 characters


def _policies():
    yield from (policy.compose_policy(preset) for preset in policy.PRESETS)
    yield policy.compose_custom_policy(CUSTOM_OPTIONS)


def test_every_version_of_up_to_14_characters_fits_every_readable_value(monkeypatch):
    monkeypatch.setattr(_version, "__version__", LONGEST_VERSION)
    assert len(LONGEST_VERSION) == 14

    lengths = {}
    for composed in _policies():
        readable = markers.markers_for(
            composed, DIGEST, satisfied=composed.options
        ).method[1]
        assert values.value_problem("LO", readable) is None
        lengths[composed.preset] = len(readable)

    # Counted by hand: "PyMedPhys ", the version, then "; PS3.15 2026d; " and
    # the preset, "custom option set" for a custom option set, or
    # "; no PS3.15 claim; tps-import".
    assert lengths == {
        "basic": 45,
        "basic-clean-descriptors": 63,
        "tps-import": 53,
        "public-release": 54,
        None: 57,
    }


def test_a_readable_value_that_would_not_fit_is_refused_not_shortened(monkeypatch):
    version = LONGEST_VERSION + "0"
    monkeypatch.setattr(_version, "__version__", version)
    composed = policy.compose_policy("basic-clean-descriptors")

    with pytest.raises(markers.MarkerError, match=r"\(0012,0063\)") as raised:
        markers.markers_for(composed, DIGEST, satisfied=())

    assert version not in str(raised.value)
    assert "readable value longer than 63 characters" in str(raised.value)
    # As many characters as LO allows, one more than a readable value may have.
    assert len(f"PyMedPhys {version}; PS3.15 2026d; basic-clean-descriptors") == 64
    # The other presets' readable values are shorter, so they still fit.
    found = markers.markers_for(policy.compose_policy("basic"), DIGEST, satisfied=())
    assert found.method[1] == f"PyMedPhys {version}; PS3.15 2026d; basic"


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
    # A code from another de-identifier that this run does not add.
    earlier_code = _code_item("113108", CID_7050["113108"])
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


def _found(preset="basic", digest=DIGEST):
    composed = policy.compose_policy(preset)
    return markers.markers_for(composed, digest, satisfied=composed.options)


@pytest.mark.parametrize("preset", list(policy.PRESETS))
def test_the_same_release_and_policy_applied_twice_gives_the_markers_of_one_run(
    preset,
):
    found = _found(preset)
    once = markers.apply_markers(_identifying_dataset(), found)
    once.PatientIdentityRemoved = "NO"

    twice = markers.apply_markers(once, found)

    once.PatientIdentityRemoved = "YES"
    assert twice == once


def test_a_different_digest_adds_its_pair_but_not_the_equal_codes_and_item():
    other_digest = "fedcba9876543210" * 4
    found, other = _found(), _found(digest=other_digest)
    once = markers.apply_markers(_identifying_dataset(), found)

    twice = markers.apply_markers(once, other)

    assert list(twice.DeidentificationMethod) == [*found.method, *other.method]
    for keyword in (
        "DeidentificationMethodCodeSequence",
        "ContributingEquipmentSequence",
    ):
        assert twice.data_element(keyword) == once.data_element(keyword)


@pytest.mark.parametrize(
    ("existing", "added"),
    [
        # Present as two consecutive values, in any place.
        (["{digest}", "{readable}"], False),
        (["SYNTHETIC TOOL 1", "{digest}", "{readable}", "SYNTHETIC TOOL 2"], False),
        # Present, but not as the pair.
        (["{readable}"], True),
        (["{digest}"], True),
        (["{readable}", "{digest}"], True),
        (["{digest}", "SYNTHETIC TOOL 1", "{readable}"], True),
        (["{digest}", "{digest}"], True),
    ],
)
def test_the_method_pair_is_added_unless_present_as_two_consecutive_values(
    existing, added
):
    found = _found()
    digest, readable = found.method
    present = [value.format(readable=readable, digest=digest) for value in existing]
    source = _identifying_dataset()
    source.DeidentificationMethod = present

    marked = markers.apply_markers(source, found)

    expected = [*present, digest, readable] if added else present
    assert list(marked.DeidentificationMethod) == expected


def _coded(value, designator="DCM", meaning=None, version=None):
    item = pydicom.Dataset()
    item.CodeValue = value
    item.CodingSchemeDesignator = designator
    if version is not None:
        item.CodingSchemeVersion = version
    item.CodeMeaning = meaning or CID_7050.get(value, "Synthetic Local Code")
    return item


@pytest.mark.parametrize(
    ("existing", "expected_values"),
    [
        # Another de-identifier's codes, one with its own wording, are kept in
        # their order, and only the run's other codes follow, in its order.
        (
            [
                _coded("113105"),
                _coded("113100", meaning="Basic Application Confidentiality"),
            ],
            ["113105", "113100", "113111", "113107"],
        ),
        # A code of another scheme, or of a stated scheme version, differs.
        (
            [_coded("113100", designator="99SYN")],
            ["113100", "113100", "113111", "113107", "113105"],
        ),
        (
            [_coded("113100", version="01")],
            ["113100", "113100", "113111", "113107", "113105"],
        ),
    ],
    ids=["same-codes", "other-scheme", "scheme-version"],
)
def test_a_code_already_present_is_not_added_again_and_new_codes_follow(
    existing, expected_values
):
    source = _identifying_dataset()
    source.DeidentificationMethodCodeSequence = existing
    found = _found("public-release")

    marked = markers.apply_markers(source, found)

    items = list(marked.DeidentificationMethodCodeSequence)
    assert items[: len(existing)] == existing
    assert [item.CodeValue for item in items] == expected_values
    for item in items[len(existing) :]:
        assert "CodingSchemeVersion" not in item


def _equipment(manufacturer, versions, purpose="109104"):
    item = pydicom.Dataset()
    item.Manufacturer = manufacturer
    item.SoftwareVersions = list(versions)
    item.PurposeOfReferenceCodeSequence = [_coded(purpose, meaning="Synthetic Purpose")]
    return item


@pytest.mark.parametrize(
    ("change", "added"),
    [
        ({}, False),
        # Other attributes of an item do not make it differ.
        ({"ContributionDescription": "SYNTHETIC DESCRIPTION"}, False),
        ({"Manufacturer": "Synthetic Vendor"}, True),
        ({"SoftwareVersions": ["0.41.0", "CPython 3.11.9"]}, True),
        ({"reversed": True}, True),
        ({"purpose": "109103"}, True),
    ],
    ids=[
        "equal",
        "equal-with-description",
        "other-manufacturer",
        "other-versions",
        "versions-in-another-order",
        "other-purpose",
    ],
)
def test_an_equal_equipment_item_is_not_added_again(change, added):
    found = _found()
    versions = list(found.software_versions)
    if change.get("reversed"):
        versions.reverse()
    existing = _equipment(
        change.get("Manufacturer", "PyMedPhys"),
        change.get("SoftwareVersions", versions),
        change.get("purpose", "109104"),
    )
    if "ContributionDescription" in change:
        existing.ContributionDescription = change["ContributionDescription"]
    source = _identifying_dataset()
    source.ContributingEquipmentSequence = [existing]
    alone = markers.apply_markers(pydicom.Dataset(), found)

    marked = markers.apply_markers(source, found)

    expected = [existing, *alone.ContributingEquipmentSequence] if added else [existing]
    assert list(marked.ContributingEquipmentSequence) == expected


# The stricter of the value already present and this run's, written out by
# hand in the order UNMODIFIED, MODIFIED, REMOVED.
STRICTER = {
    ("UNMODIFIED", "UNMODIFIED"): "UNMODIFIED",
    ("UNMODIFIED", "MODIFIED"): "MODIFIED",
    ("UNMODIFIED", "REMOVED"): "REMOVED",
    ("MODIFIED", "UNMODIFIED"): "MODIFIED",
    ("MODIFIED", "MODIFIED"): "MODIFIED",
    ("MODIFIED", "REMOVED"): "REMOVED",
    ("REMOVED", "UNMODIFIED"): "REMOVED",
    ("REMOVED", "MODIFIED"): "REMOVED",
    ("REMOVED", "REMOVED"): "REMOVED",
}


@pytest.mark.parametrize(("present", "new"), list(STRICTER))
def test_temporal_information_modified_keeps_the_stricter_value(present, new):
    source = _identifying_dataset()
    source.LongitudinalTemporalInformationModified = present
    found = dataclasses.replace(_found(), temporal_information_modified=new)

    marked = markers.apply_markers(source, found)

    assert marked.LongitudinalTemporalInformationModified == STRICTER[present, new]


@pytest.mark.parametrize("present", [None, ""])
def test_temporal_information_modified_without_a_value_takes_this_runs(present):
    source = _identifying_dataset()
    if present is not None:
        source.LongitudinalTemporalInformationModified = present
    found = _found("public-release")

    marked = markers.apply_markers(source, found)

    assert marked.LongitudinalTemporalInformationModified == "MODIFIED"


@pytest.mark.parametrize(
    "present",
    ["SYNTHETIC", "SYNTHETIC_MOD", ["SYNTHETIC", "REMOVED"]],
)
def test_an_unknown_temporal_information_modified_is_refused_without_quoting_it(
    monkeypatch, present
):
    source = _identifying_dataset()
    source.LongitudinalTemporalInformationModified = present

    def never(*args):
        raise AssertionError("an attribute was written")

    monkeypatch.setattr(markers, "_set", never)

    with pytest.raises(markers.MarkerError, match=r"\(0028,0303\)") as raised:
        markers.apply_markers(source, _found())

    assert "SYNTHETIC" not in str(raised.value)


@pytest.mark.parametrize("temporal", ["UNMODIFIED", "MODIFIED", "REMOVED"])
def test_the_markers_may_give_any_enumerated_temporal_value(temporal):
    found = dataclasses.replace(_found(), temporal_information_modified=temporal)

    marked = markers.apply_markers(pydicom.Dataset(), found)

    assert marked.LongitudinalTemporalInformationModified == temporal
    assert marked.PatientIdentityRemoved == "YES"


@pytest.mark.parametrize(
    ("keyword", "vr", "value", "replace_un"),
    [
        # pydicom gives the element its dictionary VR but leaves the bytes.
        ("DeidentificationMethod", "UN", b"SYNTHETIC IDENTIFIER", True),
        ("DeidentificationMethod", "UN", b"SYNTHETIC IDENTIFIER", False),
        ("DeidentificationMethod", "UN", "SYNTHETIC IDENTIFIER", False),
        ("DeidentificationMethod", "UT", "SYNTHETIC IDENTIFIER", True),
        ("ContributingEquipmentSequence", "UN", b"SYNTHETIC IDENTIFIER", False),
        ("LongitudinalTemporalInformationModified", "UN", b"SYNTHETIC", True),
        ("LongitudinalTemporalInformationModified", "UN", b"SYNTHETIC", False),
    ],
    ids=[
        "LO-bytes",
        "UN-bytes",
        "UN-text",
        "UT-text",
        "UN-sequence",
        "CS-bytes-temporal",
        "UN-bytes-temporal",
    ],
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


@pytest.fixture(name="un_kept")
def fixture_un_kept(monkeypatch):
    """Keep the VR UN of an attribute that pydicom's dictionary knows.

    pydicom otherwise gives such an element its dictionary VR when it is
    added or read, and decodes its value. The setting is restored afterwards.
    """
    monkeypatch.setattr(pydicom.config, "replace_un_with_known_vr", False)


ITEM_TAG = 0xFFFEE000


def _implicit(tag, value):
    """Return an element or item of defined length in Implicit VR Little Endian.

    Its tag's group and element, then the length of ``value``, each little
    endian, then ``value`` (PS3.5 Sections 7.1.3 and 7.5).
    """
    return struct.pack("<HHI", tag >> 16, tag & 0xFFFF, len(value)) + value


# A Purpose of Reference Code Sequence of one synthetic item, as an element of
# VR UN holds it: in Implicit VR Little Endian (PS3.5 Section 6.2.2), with
# each text value padded with a space to an even length.
UNDECODED_PURPOSE = _implicit(
    ITEM_TAG,
    _implicit(0x00080100, b"109104")
    + _implicit(0x00080102, b"DCM ")
    + _implicit(0x00080104, b"SYNTHETIC PURPOSE "),
)
# Each attribute that the markers compare in an item already present, after
# the sequences that hold it, outermost first.
COMPARED_IN_ITEMS = {
    "equipment-manufacturer": ("ContributingEquipmentSequence", "Manufacturer"),
    "equipment-software-versions": (
        "ContributingEquipmentSequence",
        "SoftwareVersions",
    ),
    "equipment-purpose": (
        "ContributingEquipmentSequence",
        "PurposeOfReferenceCodeSequence",
    ),
    "purpose-code-value": (
        "ContributingEquipmentSequence",
        "PurposeOfReferenceCodeSequence",
        "CodeValue",
    ),
    "purpose-coding-scheme": (
        "ContributingEquipmentSequence",
        "PurposeOfReferenceCodeSequence",
        "CodingSchemeDesignator",
    ),
    "method-code-value": ("DeidentificationMethodCodeSequence", "CodeValue"),
    "method-coding-scheme": (
        "DeidentificationMethodCodeSequence",
        "CodingSchemeDesignator",
    ),
    "method-coding-scheme-version": (
        "DeidentificationMethodCodeSequence",
        "CodingSchemeVersion",
    ),
}


def _holder(dataset, sequences):
    """Return the first item of the innermost of nested sequences.

    Each sequence, named by its keyword, is taken from the first item of the
    one before it, and the data set itself where there are none.
    """
    for sequence in sequences:
        dataset = dataset[sequence].value[0]
    return dataset


def _nested(dataset, path):
    """Return the element at a path of keywords, in each sequence's first item."""
    *sequences, keyword = path
    return _holder(dataset, sequences)[keyword]


@pytest.mark.usefixtures("pydicom_behaviour", "un_kept")
@pytest.mark.parametrize("read_back", [False, True], ids=["in-memory", "read-back"])
@pytest.mark.parametrize(
    "path", list(COMPARED_IN_ITEMS.values()), ids=list(COMPARED_IN_ITEMS)
)
def test_an_attribute_compared_in_an_existing_item_not_read_as_its_vr_is_refused(
    monkeypatch, path, read_back
):
    source = _identifying_dataset()
    source.DeidentificationMethodCodeSequence = [_coded("113100", version="01")]
    source.ContributingEquipmentSequence = [
        _equipment("Synthetic Vendor", ["SYNTHETIC 9.9"])
    ]
    *sequences, keyword = path
    undecoded, decoded_value = (
        (UNDECODED_PURPOSE, [_coded("109104", meaning="SYNTHETIC PURPOSE")])
        if keyword == "PurposeOfReferenceCodeSequence"
        else (b"SYNTHETIC ID", "SYNTHETIC ID")
    )
    _holder(source, sequences).add_new(pydicom.tag.Tag(keyword), "UN", undecoded)
    found = _found()
    if read_back:
        # Written as UN in Explicit VR. Where pydicom replaces UN with the
        # dictionary VR, as it does by default, it decodes the attribute and
        # the markers are added.
        with monkeypatch.context() as patch:
            patch.setattr(pydicom.config, "replace_un_with_known_vr", True)
            decoded = _nested(_written_and_read(source), path)
            assert decoded.VR == pydicom.datadict.dictionary_VR(keyword)
            assert decoded.value == decoded_value
            markers.apply_markers(_written_and_read(source), found)
        source = _written_and_read(source)
    assert _nested(source, path).VR == "UN"

    def never(*args):
        raise AssertionError("an attribute was written")

    monkeypatch.setattr(markers, "_set", never)

    with pytest.raises(markers.MarkerError) as raised:
        markers.apply_markers(source, found)

    # The message names the attribute, then each sequence that holds it, from
    # the innermost out.
    message = str(raised.value)
    tags = [str(pydicom.tag.Tag(each)) for each in reversed(path)]
    assert all(tag in message for tag in tags)
    assert sorted(tags, key=message.index) == tags
    assert "synthetic" not in message.lower()


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


@pytest.fixture(name="strict_reading")
def fixture_strict_reading():
    """Read with pydicom's strict validation, and fail on any warning.

    pydicom's reading validation mode and the warning filters are restored
    afterwards, so other tests are unaffected.
    """
    with pydicom.config.strict_reading(), warnings.catch_warnings():
        warnings.simplefilter("error")
        assert pydicom.config.settings.reading_validation_mode == pydicom.config.RAISE
        yield


TRANSFER_SYNTAXES = [
    pydicom.uid.ImplicitVRLittleEndian,
    pydicom.uid.ExplicitVRLittleEndian,
]


def _written_and_read(dataset, transfer_syntax=pydicom.uid.ExplicitVRLittleEndian):
    """Write a data set to a file in memory, and read the file back."""
    written = copy.deepcopy(dataset)
    written.file_meta = pydicom.dataset.FileMetaDataset()
    written.file_meta.TransferSyntaxUID = transfer_syntax
    buffer = io.BytesIO()
    pydicom.dcmwrite(buffer, written, enforce_file_format=True)
    buffer.seek(0)
    return pydicom.dcmread(buffer)


def _marker_elements(dataset):
    return {
        keyword: dataset.data_element(keyword)
        for keyword in MARKER_KEYWORDS
        if keyword in dataset
    }


# Each policy whose markers are written and read back, and its satisfied
# options.
ROUND_TRIP_POLICIES = {
    "basic": ("basic", ()),
    "basic-clean-descriptors": ("basic-clean-descriptors", ("clean_descriptors",)),
    "basic-clean-descriptors-unsatisfied": ("basic-clean-descriptors", ()),
    "public-release": ("public-release", policy.PRESETS["public-release"]),
    "tps-import": ("tps-import", ()),
    "custom-option-set": (CUSTOM_OPTIONS, CUSTOM_OPTIONS),
}
# Versions of 11 and 14 characters, whose lengths differ by an odd number,
# so that under each policy the De-identification Method values have an odd
# length in all with one version and an even length with the other.
ROUND_TRIP_VERSIONS = ("0.42.0.dev1", LONGEST_VERSION)
DEIDENTIFICATION_METHOD_TAG = 0x00120063


@pytest.mark.usefixtures("pydicom_behaviour", "strict_reading")
@pytest.mark.parametrize(
    "transfer_syntax", TRANSFER_SYNTAXES, ids=["implicit", "explicit"]
)
@pytest.mark.parametrize("name", list(ROUND_TRIP_POLICIES))
def test_marked_output_reads_back_strictly_and_gains_nothing_when_marked_again(
    monkeypatch, name, transfer_syntax
):
    selected, satisfied = ROUND_TRIP_POLICIES[name]
    padded = set()

    for version in ROUND_TRIP_VERSIONS:
        monkeypatch.setattr(_version, "__version__", version)
        found = markers.markers_for(_compose(selected), DIGEST, satisfied=satisfied)
        marked = markers.apply_markers(_identifying_dataset(), found)

        read = _written_and_read(marked, transfer_syntax)
        # The bytes as written, before pydicom reads them and removes any
        # padding: an odd length in all is padded with a trailing space.
        encoded = read.get_item(DEIDENTIFICATION_METHOD_TAG).value
        padded.add(encoded.endswith(b" "))
        again = markers.apply_markers(read, found)

        assert _marker_elements(read) == _marker_elements(marked)
        assert _marker_elements(again) == _marker_elements(read)
        assert list(read.DeidentificationMethod) == list(found.method)

    assert padded == {True, False}


@pytest.mark.usefixtures("strict_reading")
def test_the_markers_follow_a_value_as_long_as_lo_allows(monkeypatch):
    monkeypatch.setattr(_version, "__version__", "0.42.0.dev1")
    # Another tool's value, as many characters as LO allows. With "SYNTHETIC
    # AB" and a backslash before it, 77 characters, odd, so it would be read
    # as too long if it stayed last. Reading such input is not this module's
    # concern, so it is made in memory.
    other = "SYNTHETIC TOOL " + "X" * 49
    source = _identifying_dataset()
    source.DeidentificationMethod = ["SYNTHETIC AB", other]
    found = _found()

    read = _written_and_read(markers.apply_markers(source, found))

    assert len(other) == 64
    assert list(read.DeidentificationMethod) == ["SYNTHETIC AB", other, *found.method]


@pytest.mark.parametrize(
    ("earlier", "refused"),
    # The digest, basic's readable value of 37 characters under version
    # 0.42.0, the other tool's value, and two backslashes make 167
    # characters, odd; "SYNTHETIC TOOL" and one more backslash before them
    # make 182, even.
    [((), True), (("SYNTHETIC TOOL",), False)],
    ids=["odd", "even"],
)
@pytest.mark.usefixtures("strict_reading")
def test_a_present_pair_followed_by_a_value_that_padding_makes_too_long_is_refused(
    monkeypatch, earlier, refused
):
    monkeypatch.setattr(_version, "__version__", "0.42.0")
    found = _found()
    digest, readable = found.method
    # Another tool's value, as many characters as LO allows, after the pair
    # from an earlier run, so that marking again adds nothing after it.
    # Reading such input is not this module's concern, so it is made in
    # memory.
    other = "SYNTHETIC TOOL " + "X" * 49
    present = [*earlier, digest, readable, other]
    source = _identifying_dataset()
    source.DeidentificationMethod = present
    assert (len(readable), len(other)) == (37, 64)

    if refused:

        def never(*args):
            raise AssertionError("an attribute was written")

        monkeypatch.setattr(markers, "_set", never)
        with pytest.raises(markers.MarkerError, match=r"\(0012,0063\)") as raised:
            markers.apply_markers(source, found)
        assert "SYNTHETIC" not in str(raised.value)
        assert "X" * 49 not in str(raised.value)
    else:
        read = _written_and_read(markers.apply_markers(source, found))
        assert list(read.DeidentificationMethod) == present


@pytest.mark.parametrize(
    ("version", "refused"),
    # With "PyPy 3.11.9", "pydicom 3.1.0.dev0", the last value, and three
    # backslashes, 102 characters, even, with a version of 6 characters, and
    # 103, odd, with one of 7.
    [("0.42.0", False), ("0.42.10", True)],
)
@pytest.mark.usefixtures("strict_reading")
def test_software_versions_that_padding_would_make_too_long_are_refused(
    monkeypatch, version, refused
):
    monkeypatch.setattr(_version, "__version__", version)
    _with_runtime(
        monkeypatch,
        {**SYNTHETIC_RUNTIME, "tomlkit.__version__": LONGEST_LIBRARY_VERSION},
    )
    expected = [
        version,
        "PyPy 3.11.9",
        "pydicom 3.1.0.dev0",
        f"tomlkit {LONGEST_LIBRARY_VERSION}",
    ]
    assert refused == (expected == list(ODD_SOFTWARE_VERSIONS))
    # pydicom itself reads the padded last value as too long.
    alone = _identifying_dataset()
    alone.SoftwareVersions = expected
    read_alone = _written_and_read(alone)
    composed = policy.compose_policy("basic")

    if refused:
        with pytest.raises(ValueError, match="exceeds the maximum length of 64"):
            _ = read_alone.SoftwareVersions
        with pytest.raises(markers.MarkerError, match=r"\(0018,1020\)") as raised:
            markers.markers_for(composed, DIGEST, satisfied=())
        assert LONGEST_LIBRARY_VERSION not in str(raised.value)
    else:
        assert list(read_alone.SoftwareVersions) == expected
        found = markers.markers_for(composed, DIGEST, satisfied=())
        marked = markers.apply_markers(_identifying_dataset(), found)
        (equipment,) = _written_and_read(marked).ContributingEquipmentSequence
        assert list(equipment.SoftwareVersions) == expected


@pytest.mark.usefixtures("strict_reading")
def test_a_single_value_as_long_as_its_vr_allows_is_written():
    # A single value as long as its VR allows has an even length, so no
    # padding follows it.
    purpose = codes.CodedConcept("DCM", "109104", "Synthetic Purpose " + "X" * 46)
    found = dataclasses.replace(_found(), purpose_of_reference=purpose)

    marked = markers.apply_markers(_identifying_dataset(), found)
    (equipment,) = _written_and_read(marked).ContributingEquipmentSequence

    (code,) = equipment.PurposeOfReferenceCodeSequence
    assert code.CodeMeaning == purpose.code_meaning
    assert len(code.CodeMeaning) == 64


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
        ({"method": (DIGEST, LONG_TEXT)}, markers.MarkerError, r"\(0012,0063\)"),
        ({"method": (DIGEST, "x" * 64)}, markers.MarkerError, r"\(0012,0063\)"),
        (
            {"patient_identity_removed": "NO", "method": (DIGEST, LONG_TEXT)},
            markers.MarkerError,
            r"\(0012,0062\).*\(0012,0063\)",
        ),
        ({"method": (DIGEST,)}, markers.MarkerError, r"\(0012,0063\)"),
        (
            {"method": (DIGEST, DIGEST, "SYNTHETIC")},
            markers.MarkerError,
            r"\(0012,0063\)",
        ),
        # The readable value first, as the digest's place.
        ({"method": ("SYNTHETIC", DIGEST)}, ValueError, "64 lowercase hexadecimal"),
        (
            {"method": ("A" * 64, "SYNTHETIC")},
            ValueError,
            "64 lowercase hexadecimal digits",
        ),
        ({"method": (DIGEST.encode(), "SYNTHETIC")}, TypeError, "digest must be text"),
        (
            {"temporal_information_modified": "modified"},
            markers.MarkerError,
            r"\(0028,0303\)",
        ),
        (
            {"temporal_information_modified": "PARTIAL"},
            markers.MarkerError,
            r"\(0028,0303\)",
        ),
        ({"manufacturer": "Py\\MedPhys"}, markers.MarkerError, r"\(0008,0070\)"),
        (
            {"software_versions": ("SYNTHETIC", LONG_TEXT)},
            markers.MarkerError,
            r"\(0018,1020\)",
        ),
        (
            {"software_versions": ODD_SOFTWARE_VERSIONS},
            markers.MarkerError,
            r"\(0018,1020\)",
        ),
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
        "readable-value-as-long-as-LO-allows",
        "NO-and-long-readable-value",
        "one-method-value",
        "three-method-values",
        "readable-value-first",
        "upper-case-digest",
        "bytes-digest",
        "lower-case-temporal",
        "unenumerated-temporal",
        "backslash-manufacturer",
        "long-software-versions",
        "software-versions-padded-too-long",
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
    assert "x" * 64 not in str(raised.value)
    assert LONGEST_LIBRARY_VERSION not in str(raised.value)


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
