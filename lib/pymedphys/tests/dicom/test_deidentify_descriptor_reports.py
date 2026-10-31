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

"""What the QC pack and the release report give of free-text descriptors."""

import json
from pathlib import Path

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    conformance,
    conformance_markdown,
    qc_pack,
    release_report,
    run_report,
)
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.qc_pack import (
    DescriptorEntry,
    Disposition,
    InstanceEntry,
    QcPack,
    QcPackError,
)
from pymedphys._dicom.deidentify.release_report_markdown import to_markdown
from pymedphys._dicom.deidentify.reviewed_descriptors import (
    CleanedDescriptor,
    DescriptorCounts,
    DescriptorReviewQueue,
    Held,
    Outcome,
)
from pymedphys._dicom.deidentify.run_qc import DescriptorMaterial, qc_pack_of

SENTINEL = "SENTINEL VALUE"
PATH = ElementPath((), "(0008,103E)")
KEPT = CleanedDescriptor(Outcome.KEPT_BY_VOCABULARY, None, "CHEST CT")
HELD = CleanedDescriptor(Outcome.HELD, Held.UNREVIEWED, None)


def _entry(sources, results, applied, position=0):
    return DescriptorEntry(position, PATH, sources, results, applied)


@pytest.mark.parametrize(
    "source, result",
    [
        ("", CleanedDescriptor(Outcome.EMPTY, None, "")),
        ("CHEST CT ", CleanedDescriptor(Outcome.KEPT, None, "CHEST CT")),
        ("CHEST CT", KEPT),
        (SENTINEL, CleanedDescriptor(Outcome.MAPPED, None, "OTHER")),
        (SENTINEL, CleanedDescriptor(Outcome.EMPTIED, None, "")),
        (SENTINEL, HELD),
        (SENTINEL, CleanedDescriptor(Outcome.HELD, Held.ECHOES_IDENTIFIER, None)),
        (SENTINEL, CleanedDescriptor(Outcome.EMPTIED_UNREVIEWED, Held.UNREVIEWED, "")),
    ],
)
def test_each_descriptor_outcome_is_accepted(source, result):
    applied = result.outcome is not Outcome.HELD

    entry = _entry((source,), (result,), applied)

    assert entry.results == (result,)


@pytest.mark.parametrize(
    "source, result, match",
    [
        (SENTINEL, CleanedDescriptor(Outcome.HELD, None, None), "reason for review"),
        (
            SENTINEL,
            CleanedDescriptor(Outcome.KEPT, Held.UNREVIEWED, SENTINEL),
            "reason",
        ),
        (SENTINEL, CleanedDescriptor(Outcome.HELD, Held.UNREVIEWED, ""), "nothing"),
        (SENTINEL, CleanedDescriptor(Outcome.MAPPED, None, None), "what was written"),
        (SENTINEL, CleanedDescriptor(Outcome.MAPPED, None, ""), "written empty only"),
        (SENTINEL, CleanedDescriptor(Outcome.EMPTIED, None, "x"), "written empty only"),
        (SENTINEL, CleanedDescriptor(Outcome.KEPT, None, "OTHER"), "its source value"),
        (SENTINEL, CleanedDescriptor("kept", None, SENTINEL), "needs an outcome"),
    ],
)
def test_a_descriptor_entry_is_consistent(source, result, match):
    with pytest.raises(QcPackError, match=match) as raised:
        _entry((source,), (result,), False)

    assert SENTINEL not in str(raised.value)


def test_a_descriptor_entry_needs_a_result_for_each_value_and_is_not_held_if_applied():
    with pytest.raises(QcPackError, match="for each value"):
        _entry((SENTINEL, SENTINEL), (HELD,), False)
    with pytest.raises(QcPackError, match="values as text"):
        _entry((), (), False)
    with pytest.raises(QcPackError, match="True or False"):
        _entry((SENTINEL,), (HELD,), 0)
    with pytest.raises(QcPackError, match="not held"):
        _entry(("CHEST CT", SENTINEL), (KEPT, HELD), True)


def _instances(count=1):
    return tuple(
        InstanceEntry(
            position, f"in/{position}.dcm", Disposition.REFUSED, reasons=("stopped",)
        )
        for position in range(count)
    )


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_the_pack_lists_each_descriptor_with_its_values_and_whether_written():
    pack = QcPack(
        qc_pack.new_reference(),
        _instances(2),
        descriptors=(_entry(("CHEST CT", SENTINEL), (KEPT, HELD), False, position=1),),
    )

    document = qc_pack.pack_document(pack)

    assert document["format"] == "pymedphys-deid-qc-pack/20"
    assert document["descriptors"] == [
        {
            "position": 1,
            "element": "(0008,103E)",
            "attribute": "(0008,103E)",
            "applied": False,
            "values": [
                {
                    "source": "CHEST CT",
                    "outcome": "kept by vocabulary",
                    "held_because": None,
                    "written": "CHEST CT",
                },
                {
                    "source": SENTINEL,
                    "outcome": "held",
                    "held_because": "unreviewed",
                    "written": None,
                },
            ],
        }
    ]
    shown = repr(pack) + repr(pack.descriptors)
    assert SENTINEL not in shown and "CHEST" not in shown
    with pytest.raises(QcPackError, match="without an instance"):
        QcPack(
            qc_pack.new_reference(),
            _instances(1),
            descriptors=(_entry((SENTINEL,), (HELD,), False, position=1),),
        )


class _Outcome:  # pylint: disable = too-few-public-methods
    """A run outcome, as qc_pack_of reads it."""

    def __init__(self, position):
        self.position = position
        self.status = Disposition.REFUSED
        self.output = None
        self.label = None
        # Any enum member is a value-free reason.
        self.reasons = (Held.UNREVIEWED,)


def test_the_material_of_each_input_becomes_its_entries():
    material = DescriptorMaterial(PATH, ("CHEST CT",), (KEPT,), True)

    pack = qc_pack_of(
        [Path("in/0.dcm"), Path("in/1.dcm")],
        [_Outcome(0), _Outcome(1)],
        {1: (material,)},
    )

    assert pack.descriptors == (_entry(("CHEST CT",), (KEPT,), True, position=1),)
    assert "CHEST" not in repr(material)


def test_a_run_counts_its_descriptor_values_and_elements_without_values():
    counts = run_report.descriptor_counts(
        {
            0: (
                DescriptorMaterial(PATH, ("CHEST CT",), (KEPT,), True),
                DescriptorMaterial(
                    ElementPath((), "(0008,1030)"), (SENTINEL,), (HELD,), False
                ),
            ),
            1: (
                DescriptorMaterial(
                    ElementPath((), "(0008,1030)"), (SENTINEL,), (HELD,), False
                ),
            ),
        }
    )

    assert counts == DescriptorCounts(
        held={Held.UNREVIEWED: 1},
        outcomes={Outcome.KEPT_BY_VOCABULARY: 1, Outcome.HELD: 2},
        fell_back=2,
    )


def test_the_queue_counts_an_element_that_fell_back_once():
    queue = DescriptorReviewQueue()
    queue.add("(0008,103E)", ["CHEST CT"], [KEPT])
    queue.add("(0008,103E)", [SENTINEL, "x"], [HELD, HELD], applied=False)

    assert queue.report_counts().fell_back == 1


def _report(descriptors):
    return release_report.release_report(
        compose_policy("basic"),
        vocabulary=None,
        reviewed_roi_names=None,
        descriptors=descriptors,
    )


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_the_report_counts_descriptors_by_outcome_and_reason_naming_none():
    report = _report(
        DescriptorCounts(
            held={Held.UNREVIEWED: 3, Held.ECHOES_IDENTIFIER: 1},
            outcomes={Outcome.KEPT_BY_VOCABULARY: 2, Outcome.HELD: 4},
            fell_back=3,
        )
    )

    document = json.loads(release_report.to_json(report))

    assert document["descriptors"] == {
        "outcomes": [
            {"outcome": "held", "count": 4},
            {"outcome": "kept by vocabulary", "count": 2},
        ],
        "held": [
            {"reason": "echoes identifier", "count": 1},
            {"reason": "unreviewed", "count": 3},
        ],
        "fell_back": 3,
    }
    section = (
        to_markdown(release_report.to_json(report))
        .split("## Descriptors", 1)[1]
        .split("\n## ", 1)[0]
    )
    rows = [line for line in section.splitlines() if line.startswith("| ")]
    assert rows == [
        "| Outcome | Values |",
        "| --- | --- |",
        "| `held` | `4` |",
        "| `kept by vocabulary` | `2` |",
        "| Reason | Distinct values |",
        "| --- | --- |",
        "| `echoes identifier` | `1` |",
        "| `unreviewed` | `3` |",
    ]
    assert "without Clean Descriptors: `3`." in section


def test_a_report_without_descriptors_counts_none():
    document = json.loads(release_report.to_json(_report(None)))

    assert document["descriptors"] == {"outcomes": [], "held": [], "fell_back": 0}
    assert "without Clean Descriptors: `0`." in to_markdown(
        release_report.to_json(_report(None))
    )


@pytest.mark.parametrize(
    "counts, field",
    [
        (DescriptorCounts({}, {Held.UNREVIEWED: 1}), "descriptors outcome"),
        (DescriptorCounts({Outcome.HELD: 1}, {}), "descriptors reason"),
        (DescriptorCounts({}, {Outcome.HELD: True}), "descriptors outcome count"),
        (DescriptorCounts({}, {}, fell_back=-1), "descriptors fell_back"),
        (DescriptorCounts({}, {}, fell_back=1.0), "descriptors fell_back"),
        ({"outcomes": {}}, "descriptors"),
    ],
)
def test_the_report_refuses_descriptor_counts_of_another_form(counts, field):
    with pytest.raises(release_report.ReleaseReportError, match=field):
        release_report.to_json(_report(counts))


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d["descriptors"].pop("fell_back"),
        lambda d: d["descriptors"].update(fell_back=-1),
        lambda d: d["descriptors"]["outcomes"].append(
            {"outcome": "`SENTINEL`", "count": 1}
        ),
    ],
)
def test_the_markdown_refuses_a_descriptors_section_of_another_form(change):
    document = json.loads(
        release_report.to_json(
            _report(DescriptorCounts({}, {Outcome.HELD: 1}, fell_back=1))
        )
    )
    change(document)

    with pytest.raises(ValueError, match="descriptors"):
        to_markdown(json.dumps(document))


@pytest.mark.deid_requirement("PS3.15-E.3.5-02")
def test_the_conformance_statement_describes_free_text_cleaning():
    statement = conformance_markdown.render_markdown(
        conformance.conformance_statement(
            compose_policy("basic-clean-descriptors"), vocabulary=None
        )
    )
    basic = conformance_markdown.render_markdown(
        conformance.conformance_statement(compose_policy("basic"), vocabulary=None)
    )

    section = statement.split("## Cleaning free-text descriptors", 1)[1].split(
        "\n## ", 1
    )[0]
    assert "Series Description (0008,103E)" in section
    assert "Scatter Correction Method (0054,1105)" in section
    assert section.count("\n- ") == len(conformance_markdown.TECHNIQUE_RULES)
    assert "Cleaning free-text descriptors" not in basic
