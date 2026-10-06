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

"""Tests of the release report's human-readable form.

Every input is synthetic.
"""

import collections
import json
import re
import uuid

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    output_names,
    qc_attestation,
    reference_graph,
    release_gate,
    release_report,
    walker,
)
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.release_report_markdown import (
    ReleaseReportMarkdownError,
    to_markdown,
)

_REFERENCE = "A-" + "0" * 32


def _uid(name):
    return f"2.25.{uuid.uuid5(uuid.NAMESPACE_OID, name).int}"


def _output_name(instance):
    return output_names.instance_path(
        patient_id="DEID-AAAAAAAAAAAAAAAA",
        study_instance_uid=_uid("study"),
        series_instance_uid=_uid("series"),
        sop_instance_uid=_uid(instance),
    )


def _report(**run):
    return release_report.release_report(
        compose_policy("basic"), vocabulary=None, reviewed_roi_names=None, **run
    )


def _full_report():
    walked = walker.Sequestration(
        ElementPath((("(0010,1002)", 3),), "(0010,0020)"),
        "D",
        "SQ",
        walker.SequesterReason.NO_DUMMY_VALUE,
    )
    gate = release_gate.ReleaseReason(
        release_gate.Decision.WITHHOLD,
        release_gate.ReasonCode.RESIDUAL_PERSON_NAME,
        ElementPath((), "(0008,103E)"),
    )
    return _report(
        qc_review=qc_attestation.AttestationRecord(
            _REFERENCE, qc_attestation.Outcome.NOT_ATTESTED
        ),
        released=(_output_name("one"), _output_name("two")),
        sequestered=(
            release_report.SequesteredInstance(
                "S-0001",
                (
                    release_report.sequestration_reason(
                        reference_graph.FindingKind.CONFLICTING_INSTANCE
                    ),
                    release_report.sequestration_reason(walked),
                ),
            ),
            release_report.SequesteredInstance(
                "S-0002", (release_report.sequestration_reason(gate),)
            ),
        ),
        held=(release_report.HeldForReview("release", "read-as-latin-1", 2),),
        coverage=(release_report.SearchCoverage("(0010,0010)", "too-short", 3),),
        gaps=(
            release_report.SourceGapCount("(0008,0060)", "1", 2),
            release_report.SourceGapCount("(3006,0010) > (0020,0052)", "2", 1),
        ),
    )


def _document(report):
    return json.loads(release_report.to_json(report))


def _leaves(document):
    """Every value of the document, with the file names that key digests."""
    found = []

    def visit(value, digests=False):
        if isinstance(value, dict):
            for key, member in value.items():
                if digests:
                    found.append(key)
                visit(member, key in ("table_digests", "engine_files"))
        elif isinstance(value, list):
            for member in value:
                visit(member)
        elif value is not None:
            found.append(json.dumps(value) if not isinstance(value, str) else value)

    visit(document)
    return found


_CODE_SPAN = re.compile(r"`([^`]*)`")


def _spans(markdown):
    return _CODE_SPAN.findall(markdown)


@pytest.mark.deid_requirement("MIDI-BP-18")
def test_every_value_of_the_report_is_shown_and_nothing_else():
    report = _full_report()
    document = _document(report)

    markdown = to_markdown(release_report.to_json(report))

    # Each value appears as a code span exactly as often as in the document,
    # and no code span holds anything the document does not.
    assert collections.Counter(_spans(markdown)) == collections.Counter(
        _leaves(document)
    )


@pytest.mark.deid_requirement("MIDI-BP-18")
def test_the_text_around_the_values_does_not_depend_on_them():
    # Two reports of the same shape differ only inside their code spans, so
    # nothing outside them is drawn from the report.
    first = to_markdown(release_report.to_json(_full_report()))
    document = _document(_full_report())
    document["qc_review"]["reference"] = "A-" + "1" * 32
    document["released"] = sorted(str(_output_name(name)) for name in ("three", "four"))
    document["held_for_review"][0]["count"] = 5
    second = to_markdown(json.dumps(document))

    assert first != second
    assert _CODE_SPAN.sub("``", first) == _CODE_SPAN.sub("``", second)


@pytest.mark.deid_requirement("MIDI-BP-18")
def test_the_form_cites_no_decision_number():
    # Decision numbers belong to the design document and may be renumbered,
    # so an archived report describes each guarantee instead.
    for report in (_full_report(), _report()):
        markdown = to_markdown(release_report.to_json(report))
        assert not re.search(r"\bD-\d", _CODE_SPAN.sub("``", markdown))


@pytest.mark.deid_requirement("MIDI-BP-18")
def test_the_form_is_the_same_every_time_it_is_generated():
    text = release_report.to_json(_full_report())
    assert to_markdown(text) == to_markdown(text)


def test_the_sections_follow_the_documents_order():
    markdown = to_markdown(release_report.to_json(_full_report()))
    headings = [line for line in markdown.splitlines() if line.startswith("## ")]
    assert headings == [
        "## Policy",
        "## Method",
        "## Runtime environment",
        "## QC review",
        "## Released instances",
        "## Sequestered instances",
        "## Instances held for review",
        "## Values not searched",
        "## Required attributes missing from the source",
    ]
    assert markdown.splitlines()[0] == "# De-identification release report"


def test_each_sequestered_reason_is_a_row_under_its_label():
    markdown = to_markdown(release_report.to_json(_full_report()))
    section = markdown.split("## Sequestered instances", 1)[1].split("\n## ", 1)[0]
    rows = [line for line in section.splitlines() if line.startswith("| ")]
    assert rows[2:] == [
        "| `S-0001` | `references` | `conflicting-instance` | | | |",
        "| | `walker` | `no-dummy-value` | `(0010,1002) > (0010,0020)` | `D` | `SQ` |",
        "| `S-0002` | `release` | `residual-person-name` | `(0008,103E)` | | |",
    ]


def test_an_empty_run_says_so_in_each_run_section():
    markdown = to_markdown(release_report.to_json(_report()))
    assert "No QC pack was written for this run." in markdown
    assert markdown.count("None.") == 5
    assert "|" not in markdown.split("## QC review", 1)[1]


def test_a_custom_option_set_and_absent_digests_are_named_in_words():
    markdown = to_markdown(release_report.to_json(_report()))
    assert "| L3 rules | none |" in markdown
    assert "| Vocabulary digest | none |" in markdown
    document = _document(_report())
    document["policy"]["preset"] = None
    assert "| Preset | none (a custom option set) |" in to_markdown(
        json.dumps(document)
    )


def test_the_markdown_is_well_formed_commonmark():
    markdown = to_markdown(release_report.to_json(_full_report()))
    lines = markdown.split("\n")
    assert markdown.endswith("\n") and not markdown.endswith("\n\n")
    assert all(line == line.rstrip() for line in lines)
    assert sum(line.startswith("# ") for line in lines) == 1
    for index, line in enumerate(lines):
        # Headings and tables are set apart by blank lines (markdownlint
        # MD022 and MD058).
        if line.startswith("#") and index:
            assert lines[index - 1] == "" and lines[index + 1] == ""
        if line.startswith("|") and not lines[index - 1].startswith("|"):
            assert lines[index - 1] == ""
            assert re.fullmatch(r"\|( --- \|)+", lines[index + 1])
        if line.startswith("|") and not lines[index + 1].startswith("|"):
            assert lines[index + 1] == ""


def _changed(change):
    document = _document(_full_report())
    change(document)
    return json.dumps(document)


@pytest.mark.deid_requirement("MIDI-BP-18")
@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(format="pymedphys-deid-release-report/3"),
        lambda d: d.update(extra=1),
        lambda d: d.pop("runtime"),
        lambda d: d["policy"].update(extra="x"),
        lambda d: d["runtime"].update(rust_version="1.0"),
        lambda d: d["sequestered"][0]["reasons"][0].update(note="x"),
        lambda d: d["held_for_review"][0].update(count="2"),
        lambda d: d["released"].append("`SENTINEL`"),
        lambda d: d["released"].append("a\nb"),
        lambda d: d["search_coverage"][0].update(attribute="a | b"),
        lambda d: d["source_gaps"][0].update(note="x"),
        lambda d: d["source_gaps"][0].update(count=0),
        lambda d: d.pop("source_gaps"),
        lambda d: d["method"]["table_digests"].update({"x`y": "0"}),
        lambda d: d.update(sequestered={}),
        lambda d: d["sequestered"][0].update(reasons=[]),
        # Each stage's reason has exactly the fields the report gives it.
        lambda d: d["sequestered"][0]["reasons"][0].update(action="K"),
        lambda d: d["sequestered"][0]["reasons"][1].pop("vr"),
        lambda d: d["sequestered"][1]["reasons"][0].update(vr="SQ"),
        lambda d: d["method"].update(method_digest=None),
        lambda d: d["released"].append(""),
        lambda d: d["released"].append(" SENTINEL "),
        lambda d: d["policy"].update({"SENTINEL|": 1}),
    ],
)
def test_a_document_not_in_the_reports_form_is_refused(change):
    with pytest.raises(ReleaseReportMarkdownError) as raised:
        to_markdown(_changed(change))
    assert "SENTINEL" not in str(raised.value)


def test_a_member_named_twice_is_refused():
    # JSON keeps the last of two members of the same name, which would hide
    # the first from the form.
    text = release_report.to_json(_full_report())
    twice = text.replace('"released": [', '"released": ["SENTINEL"], "released": [', 1)
    with pytest.raises(ReleaseReportMarkdownError) as raised:
        to_markdown(twice)
    assert "SENTINEL" not in str(raised.value)


def test_reasons_with_and_without_optional_fields_leave_their_cells_empty():
    walked = walker.Sequestration(
        ElementPath((), "(0010,0020)"),
        "X",
        None,
        walker.SequesterReason.NO_DUMMY_VALUE,
    )
    gate = release_gate.ReleaseReason(
        release_gate.Decision.WITHHOLD, release_gate.ReasonCode.UNCOLLECTED
    )
    report = _report(
        sequestered=(
            release_report.SequesteredInstance(
                "S-0001",
                (
                    release_report.sequestration_reason(walked),
                    release_report.sequestration_reason(gate),
                ),
            ),
        ),
        held=(release_report.HeldForReview("roi-names", "unmatched", 1),),
    )
    markdown = to_markdown(release_report.to_json(report))
    assert "| `S-0001` | `walker` | `no-dummy-value` | `(0010,0020)` | `X` | |" in (
        markdown
    )
    assert "| | `release` | `uncollected` | | | |" in markdown
    assert "| `roi-names` | `unmatched` | `1` |" in markdown


def test_text_that_is_not_json_is_refused():
    with pytest.raises(ReleaseReportMarkdownError):
        to_markdown("SENTINEL")


def test_each_source_gap_is_a_row_with_its_type_and_count():
    markdown = to_markdown(release_report.to_json(_full_report()))
    section = markdown.split("## Required attributes missing from the source", 1)[1]
    rows = [line for line in section.splitlines() if line.startswith("| ")]
    assert rows == [
        "| Attribute | Type | Instances |",
        "| --- | --- | --- |",
        "| `(0008,0060)` | `1` | `2` |",
        "| `(3006,0010) > (0020,0052)` | `2` | `1` |",
    ]
