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

"""The validators' output reduced to findings, and the comparison of findings.

None of these tests runs a validator: each reads output written here in the
form that dciodvfy and dcentvfy print, or validations made here. The corpus
tests (``test_deidentify_dicom_validation_corpus.py``) run the validators.
"""

import collections
import json
import logging
import sys
import textwrap
import types
import warnings
from pathlib import Path

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import dicom_validation, dicom_validation_command
from pymedphys._dicom.deidentify import dicom_validators as validators
from pymedphys._dicom.deidentify.dicom_validation import (
    Category,
    KnownDifference,
    KnownDifferencesError,
    Outcome,
    Pair,
)
from pymedphys._dicom.deidentify.dicom_validation_markdown import render_markdown
from pymedphys._dicom.deidentify.dicom_validators import (
    DCENTVFY,
    DCIODVFY,
    DICOM_VALIDATOR,
    Finding,
    Status,
    Validation,
)

pytestmark = pytest.mark.pydicom

# A value that each test plants in a validator's output, and that no
# finding may hold.
PLANTED = "PLANTEDVALUE"
PN_DUBIOUS = "Value dubious for this VR [PN] = <value> - Retired Person Name form"
EVEN_GROUP = validators._UNPARSED_IN_IMPLICIT_VR[0]  # pylint: disable = protected-access
EXPLICIT_UN = validators._UNPARSED[0]  # pylint: disable = protected-access
ORIENTATION = "PatientOrientation row and column directions cannot be identical"
# Strings compiled into a dicom3tools executable, as dciodvfy's are.
STRINGS = frozenset(
    {
        "CTImage",
        "Value dubious for this VR",
        "Retired Person Name form",
        "Missing attribute",
        "Type 1 Required",
        "Unrecognized enumerated value",
        "String attribute has different value",
        "GeneralStudy",
        "NotAKeyword",
        # An entity's name, stored as the end of a longer string.
        "InformationEntityPatient",
        "Study",
        ORIENTATION,
        EVEN_GROUP,
        EXPLICIT_UN,
    }
)
NO_VERSIONS = validators.Versions(None, None, None, {})


def _dciodvfy(text):
    return textwrap.dedent(text).lstrip("\n")


def test_a_dciodvfy_message_keeps_its_type_and_not_its_value():
    output = _dciodvfy(
        f"""
        CTImage
        Warning - </PersonName(0040,a123)[1]> - Value dubious for this VR [PN] = <{PLANTED}> - Retired Person Name form
        Error - </StudyDate(0008,0020)> - Missing attribute for Type 1 Required - Module=<GeneralStudy>
        """
    )

    validation = validators.parse_dciodvfy(output, STRINGS)

    assert validation.status is Status.VALIDATED
    assert validation.iod == "CTImage"
    assert validation.findings == {
        Finding(DCIODVFY, "warning", "(0040,A123)", PN_DUBIOUS): 1,
        Finding(
            DCIODVFY,
            "error",
            "(0008,0020)",
            "Missing attribute for Type 1 Required",
            "GeneralStudy",
        ): 1,
    }


@pytest.mark.parametrize(
    "value",
    [
        f"{PLANTED}> - Retired Person Name form",
        f"<{PLANTED}",
        f'"{PLANTED}"',
        f"{PLANTED} - Module=<{PLANTED}>",
    ],
)
def test_no_part_of_a_value_passes(value):
    output = f"Warning - </PersonName(0040,a123)[1]> - Value dubious for this VR [PN] = <{value}> - {PLANTED}\n"

    validation = validators.parse_dciodvfy(output, STRINGS)

    assert PLANTED not in repr(validation)


@pytest.mark.parametrize(
    "message",
    [
        f'{ORIENTATION} = "{PLANTED}" and "{PLANTED}"',
        f"{ORIENTATION} = '{PLANTED}' and '{PLANTED}'",
        f"{ORIENTATION} = <{PLANTED}> and <{PLANTED}>",
        f"{ORIENTATION} = {PLANTED}",
        f'{ORIENTATION} "{PLANTED}"',
        f"{ORIENTATION} = <{PLANTED}",
    ],
)
def test_a_value_outside_angle_brackets_is_redacted(message):
    output = f"Error - </PatientOrientation(0020,0020)> - {message}\n{PLANTED}>\n"

    validation = validators.parse_dciodvfy(output, STRINGS)

    assert PLANTED not in repr(validation)
    assert {finding.message for finding in validation.findings} == {
        ORIENTATION + (" = <value>" if "= " in message else " <value>"),
        "line not recognised",
    }


@pytest.mark.parametrize(
    "message",
    [
        f"Missing attribute {PLANTED}",
        f"{PLANTED} Missing attribute",
        f"Missing attribute for {PLANTED} Type 1 Required",
        f"Missing attribute [{PLANTED}]",
        f"Missing attribute - {PLANTED}",
    ],
)
def test_a_message_that_is_not_the_validators_own_text_is_not_shown(message):
    message_type, module = validators.message_type(message, STRINGS)

    assert (message_type, module) == (validators.UNPROVEN_MESSAGE, "")


def test_a_message_is_made_of_the_validators_strings_and_counts():
    assert validators.composed("Missing attribute for Type 1 Required", STRINGS) == (
        "Missing attribute for Type 1 Required"
    )
    assert validators.composed("Missing attribute [PN] 12", STRINGS) == (
        "Missing attribute [PN] <n>"
    )
    assert validators.composed("Missing attribute [ZZ]", STRINGS) is None


def test_an_iod_name_must_be_the_validators_own():
    validation = validators.parse_dciodvfy(f"{PLANTED}\n", STRINGS)

    assert validation.iod == ""
    assert PLANTED not in repr(validation)


def test_a_dcentvfy_message_that_is_not_its_own_text_is_not_shown():
    output = f"Error - Different {PLANTED} value - Element=<PatientName> IE=<Patient>\n"

    (finding,) = validators.parse_dcentvfy(output, STRINGS).findings

    assert finding.message == validators.UNPROVEN_MESSAGE


def test_a_report_holds_no_value_quoted_outside_angle_brackets(monkeypatch):
    output = validators.parse_dciodvfy(
        f'Error - </PatientOrientation(0020,0020)> - {ORIENTATION} = "{PLANTED}"'
        f' and "{PLANTED}"\n',
        STRINGS,
    )

    comparison = _comparison(monkeypatch, _validation(DCIODVFY, {}), output)

    assert not comparison.passed
    for text in (comparison.json(), comparison.markdown()):
        assert PLANTED not in text
        assert (
            f"{ORIENTATION} = &lt;value&gt;" in text
            or f"{ORIENTATION} = <value>" in text
        )


# A value that spans lines: dciodvfy prints its line breaks, so its later
# lines can have a message's form, with the value in the structural fields.
SPANNING = (
    f'Error - </PatientName(0010,0010)> - Value invalid for this VR [PN] = "{PLANTED}\n'
    f"Error - </(0010,0010)> - Missing attribute - Module=<{PLANTED}>\n"
    f'{PLANTED}"\n'
)


def test_a_value_that_spans_lines_leaves_no_structural_field():
    validation = validators.parse_dciodvfy(SPANNING, STRINGS)

    assert PLANTED not in repr(validation)
    assert Finding(DCIODVFY, "error", "(0010,0010)", "Missing attribute") in (
        validation.findings
    )
    assert validation.iod == ""


def test_a_dcentvfy_line_keeps_only_names_the_validator_holds():
    output = (
        f"Error - String attribute has different value - Element=<{PLANTED}> "
        f"IE=<{PLANTED}>\n"
        "Error - String attribute has different value - Element=<PatientName> "
        "IE=<Patient>\n"
    )

    validation = validators.parse_dcentvfy(output, STRINGS)

    assert PLANTED not in repr(validation)
    assert set(validation.findings) == {
        Finding(DCENTVFY, "error", "", "String attribute has different value"),
        Finding(
            DCENTVFY,
            "error",
            "(0010,0010)",
            "String attribute has different value",
            "Patient",
        ),
    }


def test_reports_hold_no_value_from_a_line_spanning_value(monkeypatch):
    baseline = validators.parse_dciodvfy(
        "Error - </StudyDate(0008,0020)> - Missing attribute for Type 1 Required"
        " - Module=<GeneralStudy>\n",
        STRINGS,
    )
    output = validators.parse_dciodvfy(
        "Error - </StudyDate(0008,0020)> - Missing attribute for Type 1 Required"
        " - Module=<GeneralStudy>\n" + SPANNING,
        STRINGS,
    )
    spanned = validators.parse_dciodvfy(SPANNING, STRINGS)

    introduced = _comparison(monkeypatch, baseline, output)
    # The same lines in the input cancel.
    control = _comparison(monkeypatch, spanned, spanned)

    assert not introduced.passed
    assert control.passed and not control.introduced
    for comparison in (introduced, control):
        for text in (comparison.json(), comparison.markdown()):
            assert PLANTED not in text


def test_a_reason_that_is_not_the_validators_own_is_dropped():
    message, module = validators.message_type(
        f"Unrecognized enumerated value = <A> - {PLANTED}", STRINGS
    )

    assert (message, module) == ("Unrecognized enumerated value = <value>", "")


def test_a_module_that_is_not_a_name_is_dropped():
    message, module = validators.message_type(
        f"Missing attribute - Module=<{PLANTED} x>", STRINGS
    )

    assert PLANTED not in message + module


def test_a_path_keeps_its_tags_and_not_its_private_creators_or_items():
    output = (
        f'Error - </(0019,1010,"{PLANTED}> - x")[2]/StudyDate(0008,0020)> - '
        "Missing attribute for Type 1 Required\n"
    )

    (finding,) = validators.parse_dciodvfy(output, STRINGS).findings

    assert finding.path == "(0019,1010)/(0008,0020)"
    assert finding.message == "Missing attribute for Type 1 Required"


def test_a_line_without_a_messages_form_is_counted_without_its_text():
    output = f"CTImage\n = <{PLANTED}> - expected 1\n{PLANTED}\n"

    validation = validators.parse_dciodvfy(output, STRINGS)

    assert validation.findings == {
        Finding(DCIODVFY, "unrecognised", "", "line not recognised"): 2
    }
    assert PLANTED not in repr(validation)


def test_an_unknown_attribute_is_unparsed_in_implicit_vr_alone():
    output = (
        f"Error - </(0008,001d)> - {EVEN_GROUP}\n"
        f"Warning - </(300a,07a0)> - {EXPLICIT_UN}\n"
    )

    implicit = validators.parse_dciodvfy(output, STRINGS, implicit_vr=True)
    explicit = validators.parse_dciodvfy(output, STRINGS)

    assert implicit.unparsed == {"(0008,001D)", "(300A,07A0)"}
    # In Explicit VR dciodvfy reads an unknown attribute's contents by the VR
    # the file gives, unless that is UN.
    assert explicit.unparsed == {"(300A,07A0)"}


def test_dcentvfy_keeps_the_attribute_and_entity_and_not_the_files_or_values():
    output = (
        "Error - String attribute has different value - Element=<PatientName> "
        f"IE=<Patient> for file <{PLANTED}.dcm> versus <b.dcm> Value 1 "
        f"<{PLANTED}> versus <{PLANTED}>\n"
        "Error - String attribute has different value - Element=<NotAKeyword> "
        "IE=<Study> for file <a> versus <b>\n"
        f"{PLANTED}\n"
    )

    validation = validators.parse_dcentvfy(output, STRINGS)

    assert validation.findings == {
        Finding(
            DCENTVFY,
            "error",
            "(0010,0010)",
            "String attribute has different value",
            "Patient",
        ): 1,
        Finding(
            DCENTVFY,
            "error",
            "NotAKeyword",
            "String attribute has different value",
            "Study",
        ): 1,
        Finding(DCENTVFY, "unrecognised", "", "line not recognised"): 1,
    }


def test_a_dicom_validator_finding_has_no_context():
    # The shape of dicom-validator's tag and error objects, without the
    # package.
    tag = types.SimpleNamespace(parents=[0x00081115], tag=0x00081150)
    error = types.SimpleNamespace(
        code=types.SimpleNamespace(name="TagMissing"),
        type="1C",
        scope=types.SimpleNamespace(name="General"),
        context={"value": PLANTED},
    )

    finding = validators._dicom_validator_finding(  # pylint: disable = protected-access
        "SOP Common", tag, error
    )

    assert finding == Finding(
        DICOM_VALIDATOR,
        "error",
        "(0008,1115)/(0008,1150)",
        "TagMissing (Type 1C)",
        "SOP Common",
    )


def _known_file(tmp_path, body):
    path = tmp_path / "known.toml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


ENTRY = """
    [[difference]]
    validator = "dciodvfy"
    severity = "warning"
    message = "Attribute is not present in standard DICOM IOD"
    paths = ["(0044,0110)/*"]
    category = "validator"
    reason = '''
    A reason
    over two lines.
    '''
"""


def test_a_known_difference_matches_by_its_patterns(tmp_path):
    (difference,) = dicom_validation.read_known_differences(
        _known_file(tmp_path, ENTRY)
    )
    finding = Finding(
        DCIODVFY,
        "warning",
        "(0044,0110)/(0040,1101)",
        "Attribute is not present in standard DICOM IOD",
    )

    assert difference.category is Category.VALIDATOR
    assert difference.reason == "A reason over two lines."
    assert difference.matches(finding)
    assert not difference.matches(
        Finding(DCIODVFY, "warning", "(0044,0110)", finding.message)
    )
    assert not difference.matches(
        Finding(DCIODVFY, "error", finding.path, finding.message)
    )


@pytest.mark.parametrize(
    "change",
    [
        ('category = "validator"', 'category = "other"'),
        ('severity = "warning"', 'severity = "unrecognised"'),
        ('validator = "dciodvfy"', 'validator = "dcmtk"'),
        ('paths = ["(0044,0110)/*"]', "paths = []"),
        ('paths = ["(0044,0110)/*"]', 'paths = ["*"]\nextra = 1'),
    ],
)
def test_a_known_difference_must_be_well_formed(tmp_path, change):
    with pytest.raises(KnownDifferencesError):
        dicom_validation.read_known_differences(
            _known_file(tmp_path, ENTRY.replace(*change))
        )


def test_the_known_differences_are_well_formed():
    differences = dicom_validation.read_known_differences()

    assert differences
    assert all(difference.reason for difference in differences)


def _validation(validator, findings, *, status=Status.VALIDATED, unparsed=()):
    return Validation(validator, status, dict(findings), frozenset(unparsed))


def _introduced(source, output, known=()):
    tallies = collections.defaultdict(
        dicom_validation._Tally  # pylint: disable = protected-access
    )
    found = {
        (finding, outcome): count
        for (finding, outcome, _), count in dicom_validation._introduced(  # pylint: disable = protected-access
            source, output, tallies, known
        )
    }
    return found, tallies[source.validator]


MISSING = Finding(DCIODVFY, "error", "(0008,0020)", "Missing attribute")
BELOW = Finding(DCIODVFY, "warning", "(0008,001D)/(0008,0106)", "Not in IOD")


def test_only_what_the_output_gives_more_often_is_introduced():
    source = _validation(DCIODVFY, {MISSING: 2, BELOW: 1})
    output = _validation(DCIODVFY, {MISSING: 3})

    found, tally = _introduced(source, output)

    assert found == {(MISSING, Outcome.UNEXPLAINED): 1}
    assert tally.resolved == 1


def test_a_finding_below_an_attribute_the_input_hid_is_not_comparable():
    source = _validation(DCIODVFY, {}, unparsed={"(0008,001D)"})
    output = _validation(DCIODVFY, {BELOW: 1, MISSING: 1})

    found, _ = _introduced(source, output)

    assert found == {
        (BELOW, Outcome.NOT_COMPARABLE): 1,
        (MISSING, Outcome.UNEXPLAINED): 1,
    }


def test_a_known_difference_explains_a_finding():
    known = (
        KnownDifference(
            DCIODVFY,
            "error",
            "Missing attribute",
            ("(0008,0020)",),
            Category.ENGINE,
            "",
        ),
    )

    found, _ = _introduced(
        _validation(DCIODVFY, {}), _validation(DCIODVFY, {MISSING: 1}), known
    )

    assert found == {(MISSING, Outcome.EXPLAINED): 1}


def test_an_output_the_validator_could_not_check_is_unexplained():
    found, tally = _introduced(
        _validation(DCIODVFY, {MISSING: 1}),
        _validation(DCIODVFY, {}, status=Status.FAILED),
    )

    ((finding, outcome),) = found
    assert finding.message == dicom_validation.OUTPUT_FAILED
    assert outcome is Outcome.UNEXPLAINED
    assert tally.statuses == {"input validated, output failed": 1}


def test_nothing_is_compared_with_an_input_the_validator_could_not_check():
    found, tally = _introduced(
        _validation(DCIODVFY, {}, status=Status.FAILED),
        _validation(DCIODVFY, {MISSING: 1}),
    )

    assert not found
    assert tally.statuses == {"input failed, output validated": 1}


def _comparison(monkeypatch, source, output, known=()):
    toolset = dicom_validation.Toolset(DCIODVFY, None, None, "2026d")
    monkeypatch.setattr(
        dicom_validation, "_validate_files", lambda paths, *_: [(source,), (output,)]
    )
    monkeypatch.setattr(dicom_validation, "_header", lambda path: {})
    monkeypatch.setattr(dicom_validation.Toolset, "versions", lambda self: NO_VERSIONS)
    return dicom_validation.compare(
        [Pair(Path("a"), Path("b"))], toolset, unpaired=1, known=known
    )


def test_a_comparison_passes_when_nothing_introduced_is_unexplained(monkeypatch):
    known = (
        KnownDifference(
            DCIODVFY, "error", "Missing attribute", ("*",), Category.PROFILE, "Why."
        ),
    )

    comparison = _comparison(
        monkeypatch,
        _validation(DCIODVFY, {}),
        _validation(DCIODVFY, {MISSING: 1}),
        known,
    )
    document = json.loads(comparison.json())

    assert comparison.passed
    assert document["schema"] == dicom_validation.SCHEMA
    assert document["pairs"] == 1 and document["unpaired"] == 1
    assert document["introduced"][0]["difference"] == 1
    assert document["known_differences"][0]["category"] == "profile"


def test_a_comparison_fails_on_an_unexplained_finding(monkeypatch):
    comparison = _comparison(
        monkeypatch, _validation(DCIODVFY, {}), _validation(DCIODVFY, {MISSING: 1})
    )

    assert not comparison.passed
    assert "**Failed**" in comparison.markdown()


def test_the_markdown_escapes_what_could_break_a_table(monkeypatch):
    odd = Finding(DCIODVFY, "error", "(0008,0020)", "a | b <value>")
    comparison = _comparison(
        monkeypatch, _validation(DCIODVFY, {}), _validation(DCIODVFY, {odd: 1})
    )

    text = render_markdown(json.loads(comparison.json()))

    assert "a \\| b &lt;value&gt;" in text
    assert "(0008,0020) StudyDate" in text


def _instance(path, instance_uid):
    dataset = pydicom.Dataset()
    dataset.SOPClassUID = pydicom.uid.CTImageStorage
    dataset.SOPInstanceUID = instance_uid
    dataset.PatientID = "a"
    dataset.file_meta = pydicom.dataset.FileMetaDataset()
    dataset.file_meta.MediaStorageSOPClassUID = dataset.SOPClassUID
    dataset.file_meta.MediaStorageSOPInstanceUID = instance_uid
    dataset.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
    path.parent.mkdir(parents=True, exist_ok=True)
    dataset.save_as(path, enforce_file_format=True)


def test_pairs_follow_the_uid_mapping(tmp_path):
    _instance(tmp_path / "source" / "a.dcm", "1.2.3.1")
    _instance(tmp_path / "source" / "b.dcm", "1.2.3.2")
    (tmp_path / "source" / "c.txt").write_text("not DICOM", encoding="utf-8")
    _instance(tmp_path / "release" / "x" / "2.25.1.dcm", "2.25.1")
    mapping = tmp_path / "uid_mapping.csv"
    mapping.write_text(
        "id_old,id_new\n1.2.3.1,2.25.1\n1.2.3.2,2.25.2\n", encoding="utf-8"
    )

    pairs, unpaired = dicom_validation.pairs_from_uid_mapping(
        tmp_path / "source", tmp_path / "release", mapping
    )

    assert pairs == (
        Pair(
            (tmp_path / "source" / "a.dcm").resolve(),
            tmp_path / "release" / "x" / "2.25.1.dcm",
        ),
    )
    assert unpaired == 2


def test_the_command_refuses_an_out_directory_that_exists(tmp_path, capsys):
    status = dicom_validation_command.main(
        [
            "compare",
            "--source",
            str(tmp_path),
            "--release",
            str(tmp_path),
            "--uid-mapping",
            str(tmp_path / "missing.csv"),
            "--out",
            str(tmp_path),
        ]
    )

    assert status == dicom_validation_command.USAGE_ERROR
    assert str(tmp_path) not in capsys.readouterr().err


def test_the_command_refuses_a_missing_mapping(tmp_path, capsys):
    status = dicom_validation_command.main(
        [
            "midi",
            "--source",
            str(tmp_path),
            "--work",
            str(tmp_path / "work"),
            "--out",
            str(tmp_path / "out"),
        ]
    )

    assert status == dicom_validation_command.USAGE_ERROR
    assert str(tmp_path) not in capsys.readouterr().err


def test_a_comparison_of_no_pair_fails():
    comparison = dicom_validation.Comparison(NO_VERSIONS, (), 0, 3, {}, {}, ())

    assert not comparison.passed
    assert "no released instance was compared" in comparison.markdown()


def _release(tmp_path, mapping_text):
    _instance(tmp_path / "source" / "a.dcm", "1.2.3.1")
    _instance(tmp_path / "release" / "2.25.1.dcm", "2.25.1")
    mapping = tmp_path / "uid_mapping.csv"
    mapping.write_text(mapping_text, encoding="utf-8")
    return tmp_path / "source", tmp_path / "release", mapping


@pytest.mark.parametrize(
    "mapping_text",
    [
        "old,new\n1.2.3.1,2.25.1\n",
        "id_old,id_new\n1.2.3.1,2.25.1\n1.2.3.1,2.25.2\n",
    ],
)
def test_an_ambiguous_mapping_is_refused(tmp_path, mapping_text):
    with pytest.raises(dicom_validation.PairingError):
        dicom_validation.pairs_from_uid_mapping(*_release(tmp_path, mapping_text))


def test_outputs_that_share_a_name_are_refused(tmp_path):
    source, release, mapping = _release(tmp_path, "id_old,id_new\n1.2.3.1,2.25.1\n")
    _instance(release / "x" / "2.25.1.dcm", "2.25.1")

    with pytest.raises(dicom_validation.PairingError):
        dicom_validation.pairs_from_uid_mapping(source, release, mapping)


def test_an_output_without_an_input_is_refused(tmp_path):
    source, release, mapping = _release(tmp_path, "id_old,id_new\n1.2.3.1,2.25.1\n")
    _instance(release / "2.25.9.dcm", "2.25.9")

    with pytest.raises(dicom_validation.PairingError):
        dicom_validation.pairs_from_uid_mapping(source, release, mapping)


def test_patients_are_grouped_by_patient_id_and_issuer():
    headers = [
        {"patient": "a\\x"},
        {"patient": "a\\x"},
        {"patient": "a\\y"},
        {"patient": ""},
        {"patient": ""},
        {"patient": "a\\x"},
    ]

    groups = dicom_validation._patients(  # pylint: disable = protected-access
        headers, left_out={5}
    )

    assert groups == [[0, 1]]


def _item(**elements):
    item = pydicom.Dataset()
    for keyword, value in elements.items():
        setattr(item, keyword, value)
    return item


def _referencing(path, *, listed, elsewhere=(), other_study=()):
    """Write an instance whose Common Instance Reference Module lists UIDs."""

    def items(uids):
        return [_item(ReferencedSOPInstanceUID=uid) for uid in uids]

    dataset = pydicom.Dataset()
    dataset.ReferencedSeriesSequence = [_item(ReferencedSOPSequence=items(listed))]
    if other_study:
        dataset.StudiesContainingOtherReferencedInstancesSequence = [
            _item(
                ReferencedSeriesSequence=[
                    _item(ReferencedSOPSequence=items(other_study))
                ]
            )
        ]
    dataset.SharedFunctionalGroupsSequence = [
        _item(DerivationImageSequence=[_item(SourceImageSequence=items(elsewhere))])
    ]
    dataset.file_meta = pydicom.dataset.FileMetaDataset()
    dataset.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
    dataset.save_as(path, enforce_file_format=False)
    return path


def test_a_premise_holds_where_a_listed_instance_is_referenced_elsewhere(tmp_path):
    kept = _referencing(
        tmp_path / "kept.dcm",
        listed=["1.2.3.1"],
        elsewhere=["1.2.3.1", "1.2.9.1"],
        other_study=["1.2.9.1"],
    )
    lost = _referencing(tmp_path / "lost.dcm", listed=["1.2.3.1"], elsewhere=[])
    other = _referencing(
        tmp_path / "other.dcm",
        listed=["1.2.3.1"],
        elsewhere=["1.2.9.1"],
        other_study=["1.2.9.1"],
    )

    assert dicom_validation.output_premises(kept) == {
        dicom_validation.THIS_STUDY_REFERENCED,
        dicom_validation.OTHER_STUDIES_REFERENCED,
    }
    assert dicom_validation.output_premises(lost) == set()
    # Only the reference to another study survives.
    assert dicom_validation.output_premises(other) == {
        dicom_validation.OTHER_STUDIES_REFERENCED
    }
    assert dicom_validation.output_premises(tmp_path / "missing.dcm") == set()


INVALID_UID = "1.02.3"


def test_reading_a_file_reports_no_invalid_value(tmp_path, caplog):
    # pydicom validates a value as it converts it, on first reading, and
    # reports an invalid one with the value.
    dataset = pydicom.Dataset()
    dataset.SOPClassUID = pydicom.uid.CTImageStorage
    dataset.SOPInstanceUID = INVALID_UID
    dataset.PatientID = "PATIENT"
    dataset.file_meta = pydicom.dataset.FileMetaDataset()
    dataset.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
    header = tmp_path / "header.dcm"
    dataset.save_as(header, enforce_file_format=True)
    premises = _referencing(
        tmp_path / "premises.dcm", listed=[INVALID_UID], elsewhere=[INVALID_UID]
    )
    # Writing the files reports the value too.
    caplog.clear()
    caplog.set_level(logging.DEBUG)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        header_read = dicom_validation._header(header)  # pylint: disable = protected-access
        assert header_read["instance"] == INVALID_UID
        assert dicom_validation.output_premises(premises) == {
            dicom_validation.THIS_STUDY_REFERENCED
        }

    assert caplog.records
    assert INVALID_UID not in caplog.text
    assert not [each for each in caught if INVALID_UID in str(each.message)]


def test_loading_dicom_validator_leaves_the_root_logger_as_it_was(
    tmp_path, monkeypatch
):
    class Reader:
        # As dicom-validator's EditionReader does.
        def __init__(self, _path):
            root = logging.getLogger()
            root.addHandler(logging.StreamHandler(sys.stdout))
            root.setLevel(logging.INFO)

        def get_edition_path(self, _edition):
            return tmp_path

        def load_dicom_info(self, _edition):
            return object()

    monkeypatch.setattr(validators.dicom_validator_editions, "EditionReader", Reader)
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level

    validators.DicomValidator.load(tmp_path, "2026d")

    assert root.handlers == handlers
    assert root.level == level


def _requiring(tmp_path):
    body = ENTRY.replace(
        'category = "validator"',
        f'category = "validator"\nrequires = "{dicom_validation.THIS_STUDY_REFERENCED}"',
    )
    (difference,) = dicom_validation.read_known_differences(_known_file(tmp_path, body))
    return difference


def test_a_known_difference_with_a_premise_needs_it(tmp_path):
    difference = _requiring(tmp_path)
    finding = Finding(
        DCIODVFY, "warning", "(0044,0110)/(0040,1101)", difference.message
    )

    assert difference.requires == dicom_validation.THIS_STUDY_REFERENCED
    assert difference.matches(finding, {dicom_validation.THIS_STUDY_REFERENCED})
    assert not difference.matches(finding)
    assert not difference.matches(finding, {dicom_validation.OTHER_STUDIES_REFERENCED})


def test_an_unknown_premise_is_refused(tmp_path):
    body = ENTRY.replace(
        'category = "validator"', 'category = "validator"\nrequires = "anything"'
    )

    with pytest.raises(KnownDifferencesError):
        dicom_validation.read_known_differences(_known_file(tmp_path, body))


def test_lost_references_are_unexplained(monkeypatch, tmp_path):
    # The output's last references outside the Common Instance Reference
    # Module are gone, so the sequences it keeps are not allowed.
    difference = _requiring(tmp_path)
    lost = Finding(DCIODVFY, "warning", "(0044,0110)/(0040,1101)", difference.message)
    source, output = _validation(DCIODVFY, {}), _validation(DCIODVFY, {lost: 1})

    monkeypatch.setattr(dicom_validation, "output_premises", lambda path: frozenset())
    failed = _comparison(monkeypatch, source, output, (difference,))
    monkeypatch.setattr(
        dicom_validation,
        "output_premises",
        lambda path: frozenset({dicom_validation.THIS_STUDY_REFERENCED}),
    )
    passed = _comparison(monkeypatch, source, output, (difference,))

    assert not failed.passed
    assert [i.outcome for i in failed.introduced] == [Outcome.UNEXPLAINED]
    assert passed.passed
    assert [(i.outcome, i.difference) for i in passed.introduced] == [
        (Outcome.EXPLAINED, 1)
    ]
    assert "Only where an instance that Referenced Series Sequence" in passed.markdown()


def test_the_common_instance_reference_entries_require_their_premises():
    entries = {
        difference.paths: difference.requires
        for difference in dicom_validation.read_known_differences()
    }

    assert entries[("(0008,1115)",)] == dicom_validation.THIS_STUDY_REFERENCED
    assert entries[("(0008,1200)",)] == dicom_validation.OTHER_STUDIES_REFERENCED
