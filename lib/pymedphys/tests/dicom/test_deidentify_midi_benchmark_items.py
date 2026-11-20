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

"""Tests that the MIDI benchmark reads each check in the written file (D-018, D-047).

An answer key names a check's place by the item indexes of the test data
set's file. Under Clean Structured Content, the engine removes a content
item of a kept Content Sequence on its own, and the written file numbers the
items after it one lower, so the benchmark maps each place to the written
file before it reads it. Every DICOM file and answer key is synthetic.
"""

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import midi_benchmark as benchmark
from pymedphys._dicom.deidentify import midi_benchmark_flips as flips
from pymedphys._dicom.deidentify.midi_answer_key import parse_check, parse_path
from pymedphys._dicom.deidentify.midi_benchmark_sources import kept_word_kinds
from pymedphys._dicom.deidentify.midi_benchmark_values import (
    find_element,
    written_path,
)
from pymedphys._dicom.deidentify.policy import CLEAN_STRUCTURED_CONTENT
from pymedphys._dicom.deidentify.removed_items import RemovedItems
from pymedphys._dicom.deidentify.synthetic_content_trees import (
    DEVICE_OBSERVER_UID_CONCEPT,
    IRRADIATION_EVENT_UID_CONCEPT,
    Code,
    item,
)

from . import _synthetic_dose_reports as reports
from ._synthetic_references import written
from .test_deidentify_midi_benchmark import _answer_key, _check, _row

# A run needs a base directory short enough for Windows' output path limit.
from .test_deidentify_run import (  # noqa: F401  # pylint: disable = unused-import
    _short_tmp_path,
)

CONTENT = "(0040,A730)"
# Table E.3.4-1 gives Accession Number as TEXT X, so that Clean Structured
# Content removes such an item on its own and keeps its siblings.
ACCESSION_NUMBER = Code("121022", "DCM", "Accession Number")
ACCESSION = f"{reports.SENTINEL}-ACC"
# An invented section heading, which no table lists.
SECTION = Code("SEC1", "99PMP", "Fixture section")
# A UID of the irradiating device, held in a nested item.
NESTED_UID = "2.25.7499"


def _place(*items, tag):
    """Return a place as the answer key writes it, from source item indexes."""
    return "".join(f"<{sequence}>[<{index:04d}>]" for sequence, index in items) + (
        f"<{tag}>"
    )


def _content_item(value_type, **values):
    dataset = pydicom.Dataset()
    dataset.ValueType = value_type
    for keyword, value in values.items():
        setattr(dataset, keyword, value)
    return dataset


def _written_tree():
    """A written Content Sequence of three items, the second with two of its own."""
    nested = pydicom.Sequence(
        [
            _content_item("TEXT", TextValue="NESTED 0"),
            _content_item("TEXT", TextValue="NESTED 1"),
        ]
    )
    dataset = pydicom.Dataset()
    dataset.ContentSequence = pydicom.Sequence(
        [
            _content_item("TEXT", TextValue="ITEM 0"),
            _content_item("CONTAINER", ContentSequence=nested),
            _content_item("TEXT", TextValue="ITEM 2"),
        ]
    )
    return dataset


def _text_at(dataset, place, removed):
    element = find_element(dataset, parse_path(place), removed=removed)
    return None if element is None else element.value


def test_a_later_sibling_of_a_removed_item_is_read_where_the_file_holds_it():
    # The source's items 0 and 2 were removed: its item 3 is written as 1.
    removed = RemovedItems({((CONTENT, 0),), ((CONTENT, 2),)})
    dataset = _written_tree()

    assert _text_at(dataset, _place((CONTENT, 3), tag="(0040,A040)"), removed) == (
        "CONTAINER"
    )
    assert _text_at(dataset, _place((CONTENT, 1), tag="(0040,A160)"), removed) == (
        "ITEM 0"
    )


def test_a_removed_item_and_everything_in_it_read_nothing():
    removed = RemovedItems({((CONTENT, 1),)})
    dataset = _written_tree()

    for place in (
        _place((CONTENT, 1), tag="(0040,A040)"),
        _place((CONTENT, 1), tag=CONTENT),
        _place((CONTENT, 1), (CONTENT, 0), tag="(0040,A160)"),
    ):
        assert find_element(dataset, parse_path(place), removed=removed) is None
        assert written_path(parse_path(place), removed) is None


@pytest.mark.parametrize(
    "removed, place, expected",
    [
        # A removal at depth two moves only the items of its own sequence.
        (
            {((CONTENT, 1), (CONTENT, 0))},
            _place((CONTENT, 1), (CONTENT, 1), tag="(0040,A160)"),
            "NESTED 0",
        ),
        (
            {((CONTENT, 1), (CONTENT, 0))},
            _place((CONTENT, 2), tag="(0040,A160)"),
            "ITEM 2",
        ),
        # A removal at depth one moves the outer index alone.
        (
            {((CONTENT, 0),)},
            _place((CONTENT, 2), (CONTENT, 1), tag="(0040,A160)"),
            "NESTED 1",
        ),
        # A removal in another item's Content Sequence moves nothing here.
        (
            {((CONTENT, 2), (CONTENT, 0))},
            _place((CONTENT, 1), (CONTENT, 1), tag="(0040,A160)"),
            "NESTED 1",
        ),
    ],
)
def test_each_depth_is_mapped_by_the_removals_in_its_own_sequence(
    removed, place, expected
):
    assert _text_at(_written_tree(), place, RemovedItems(removed)) == expected


def test_a_private_attribute_of_a_later_sibling_is_mapped():
    dataset = _written_tree()
    item_1 = dataset.ContentSequence[1]
    block = item_1.private_block(0x0019, "SYNTHETIC CREATOR", create=True)
    block.add_new(0x10, "LO", "PRIVATE")
    removed = RemovedItems({((CONTENT, 0),)})

    place = f'<{CONTENT}>[<0002>]<(0019,"SYNTHETIC CREATOR",10)>'

    assert _text_at(dataset, place, removed) == "PRIVATE"
    assert _text_at(dataset, place, None) is None


def test_without_removed_items_a_place_is_read_as_the_key_gives_it():
    place = parse_path(_place((CONTENT, 2), tag="(0040,A160)"))

    assert written_path(place, RemovedItems()) == place
    assert find_element(_written_tree(), place).value == "ITEM 2"


def _report():
    """Return an X-Ray Radiation Dose SR from which the option removes items.

    Its root's Content Sequence holds, by source index:

    0. Procedure reported;
    1. Observer Type, given an Accession Number of its own, which is removed,
       so that it loses its Content Sequence;
    2. an Accession Number, which is removed;
    3. the Device Observer UID;
    4. an Irradiation Event UID;
    5. a section that holds only an Accession Number, which is removed with
       it;
    6. Scope of Accumulation, with the Study Instance UID as item 0;
    7. Accumulated X-Ray Dose Data, whose item 1 is an Accession Number,
       which is removed, before a Device Observer UID as item 2;
    8. Irradiation Event X-Ray Data; and
    9. Source of Dose Information.
    """
    dataset = reports.x_ray_dose_report(())
    root = dataset.ContentSequence
    assert [each.ConceptNameCodeSequence[0].CodeValue for each in root] == [
        "121058",
        "121005",
        "121012",
        "113705",
        "113702",
        "113706",
        "113854",
    ]
    root[1].ContentSequence = pydicom.Sequence(
        [item("HAS PROPERTIES", "TEXT", ACCESSION_NUMBER, text=ACCESSION)]
    )
    root.insert(2, item("HAS OBS CONTEXT", "TEXT", ACCESSION_NUMBER, text=ACCESSION))
    root.insert(
        4,
        item(
            "HAS OBS CONTEXT",
            "UIDREF",
            IRRADIATION_EVENT_UID_CONCEPT,
            text=reports.IRRADIATION_EVENT_UID,
        ),
    )
    root.insert(
        5,
        item(
            "CONTAINS",
            "CONTAINER",
            SECTION,
            item("CONTAINS", "TEXT", ACCESSION_NUMBER, text=ACCESSION),
        ),
    )
    accumulated = root[7].ContentSequence
    accumulated.append(item("CONTAINS", "TEXT", ACCESSION_NUMBER, text=ACCESSION))
    accumulated.append(
        item("CONTAINS", "UIDREF", DEVICE_OBSERVER_UID_CONCEPT, text=NESTED_UID)
    )
    return dataset


# Each check of the report, by its place in the source, and the outcome that
# reading it in the written file gives.
_CHECKS = [
    # A removed item reads nothing: its text is removed, and a check that
    # asks to keep it is a deliberate difference.
    (
        _check("text_removed", _place((CONTENT, 2), tag="(0040,A160)"), text=ACCESSION),
        "passed",
    ),
    (
        _check(
            "text_retained",
            _place((CONTENT, 2), tag="(0040,A160)"),
            text=ACCESSION,
            tcia_p15="TEST-RETAIN",
        ),
        "deliberate",
    ),
    # The two UIDREF items after it are read as themselves.
    (
        _check(
            "uid_consistent",
            _place((CONTENT, 3), tag="(0040,A124)"),
            value=reports.DEVICE_OBSERVER_UID,
        ),
        "passed",
    ),
    (
        _check(
            "uid_changed",
            _place((CONTENT, 3), tag="(0040,A124)"),
            value=reports.DEVICE_OBSERVER_UID,
        ),
        "passed",
    ),
    (
        _check(
            "uid_consistent",
            _place((CONTENT, 4), tag="(0040,A124)"),
            value=reports.IRRADIATION_EVENT_UID,
        ),
        "passed",
    ),
    (
        _check("tag_retained", _place((CONTENT, 4), tag="(0040,A124)"), dicom_iod="T"),
        "passed",
    ),
    # Inside the removed section: nothing.
    (
        _check(
            "text_removed",
            _place((CONTENT, 5), (CONTENT, 0), tag="(0040,A160)"),
            text=ACCESSION,
        ),
        "passed",
    ),
    (
        _check("tag_retained", _place((CONTENT, 5), tag="(0040,A040)"), dicom_iod="T"),
        "deliberate",
    ),
    # A later sibling's own item, at depth two.
    (
        _check(
            "uid_consistent",
            _place((CONTENT, 6), (CONTENT, 0), tag="(0040,A124)"),
            value=reports.STUDY,
        ),
        "passed",
    ),
    # A nested removal moves the nested sibling after it.
    (
        _check(
            "uid_consistent",
            _place((CONTENT, 7), (CONTENT, 2), tag="(0040,A124)"),
            value=NESTED_UID,
        ),
        "passed",
    ),
    (
        _check(
            "tag_retained",
            _place((CONTENT, 7), (CONTENT, 2), tag="(0040,A124)"),
            dicom_iod="T",
        ),
        "passed",
    ),
    # The item emptied of its Content Sequence keeps its own concept name.
    (
        _check("tag_retained", _place((CONTENT, 1), tag="(0040,A043)"), dicom_iod="T"),
        "passed",
    ),
    (
        _check("tag_retained", _place((CONTENT, 1), tag=CONTENT), dicom_iod="T"),
        "deliberate",
    ),
    (
        _check(
            "text_removed",
            _place((CONTENT, 1), (CONTENT, 0), tag="(0040,A160)"),
            text=ACCESSION,
        ),
        "passed",
    ),
    # The last item, three places up in the written file.
    (
        _check("tag_retained", _place((CONTENT, 9), tag="(0040,A043)"), dicom_iod="T"),
        "passed",
    ),
    # Outside Content Sequence, nothing moves.
    (
        _check("uid_changed", "<(0020,000D)>", value=reports.STUDY),
        "passed",
    ),
]


def _run_report(tmp_path, options, report=None, checks=None):
    source = tmp_path / "source"
    source.mkdir()
    (source / "0.dcm").write_bytes(written(_report() if report is None else report))
    key = _answer_key(
        tmp_path / "key.db",
        [
            _row(
                reports.X_RAY_REPORT,
                [check for check, _ in _CHECKS] if checks is None else checks,
                patient=reports.PATIENT_ID,
                study=reports.STUDY,
                series=reports.X_RAY_SERIES,
                sop_class=reports.X_RAY_RADIATION_DOSE_SR,
                modality="SR",
            )
        ],
    )
    return benchmark.run_benchmark(source, key, tmp_path / "work", options=options)


def test_each_check_of_a_report_reads_its_own_item_after_removals(tmp_path):
    result = _run_report(tmp_path, [CLEAN_STRUCTURED_CONTENT])

    assert result.document["coverage"]["instances"]["released"] == 1
    assert result.check_outcomes.decode("ascii") == "".join(
        flips.outcome_code(outcome).decode("ascii") for _, outcome in _CHECKS
    )
    assert result.document["findings"] == []


def test_each_check_that_a_removed_item_moved_is_counted(tmp_path):
    result = _run_report(tmp_path, [CLEAN_STRUCTURED_CONTENT])

    rows = result.document["moved_checks"]
    totals = {}
    for row in rows:
        place = (row["place"], row["outcome"])
        totals[place] = totals.get(place, 0) + row["checks"]
    # Eight checks are read one or more items up, and four lie in removed
    # items; the three in Observer Type, and the one outside Content
    # Sequence, are where the key gives them.
    assert totals == {
        ("moved", "passed"): 8,
        ("removed", "passed"): 2,
        ("removed", "deliberate"): 2,
    }
    assert {
        (row["action"], row["attribute"], row["place"])
        for row in rows
        if row["outcome"] == "deliberate"
    } == {
        ("text_retained", "(0040,A730)/(0040,A160)", "removed"),
        ("tag_retained", "(0040,A730)/(0040,A040)", "removed"),
    }
    markdown = result.markdown()
    assert "## Checks moved by removed items" in markdown
    assert "| dicom T | tag_retained | (0040,A730)/(0040,A040) | removed |" in markdown


def test_without_removed_items_no_check_is_counted_as_moved(tmp_path):
    # The fixture's own report holds no item that the option removes.
    result = _run_report(
        tmp_path,
        [CLEAN_STRUCTURED_CONTENT],
        reports.x_ray_dose_report(()),
        [
            _check(
                "uid_consistent",
                _place((CONTENT, 2), tag="(0040,A124)"),
                value=reports.DEVICE_OBSERVER_UID,
            )
        ],
    )

    assert result.check_outcomes == b"P"
    assert result.document["moved_checks"] == []


def test_a_check_whose_place_cannot_be_mapped_is_not_evaluated(tmp_path, monkeypatch):
    # Where the source cannot be read again, which items the engine removed
    # is not known, so no check in a Content Sequence is read.
    monkeypatch.setattr(benchmark, "removed_items", lambda *_: None)

    result = _run_report(tmp_path, [CLEAN_STRUCTURED_CONTENT])

    outcomes = result.check_outcomes.decode("ascii")
    assert outcomes[:-1] == "N" * (len(_CHECKS) - 1)
    assert outcomes[-1] == "P"
    assert {row["reason"] for row in result.document["not_evaluated"]} == {
        "items removed from it unknown"
    }


def test_the_removed_items_are_the_engines_own(tmp_path):
    source = tmp_path / "0.dcm"
    source.write_bytes(written(_report()))
    iod = benchmark.load_iod_tables().iods[reports.X_RAY_IOD]
    policy = benchmark.compose_custom_policy([CLEAN_STRUCTURED_CONTENT])

    removed = benchmark.removed_items(source, policy, iod)

    # The section is removed with what it holds, and Observer Type's
    # Content Sequence is emptied, rather than its item removed on its own.
    assert removed.items == {
        ((CONTENT, 2),),
        ((CONTENT, 5),),
        ((CONTENT, 7), (CONTENT, 1)),
    }


def test_removed_items_are_unknown_without_a_readable_source_or_an_iod(tmp_path):
    policy = benchmark.compose_custom_policy([CLEAN_STRUCTURED_CONTENT])
    iod = benchmark.load_iod_tables().iods[reports.X_RAY_IOD]
    unreadable = tmp_path / "unreadable.dcm"
    unreadable.write_bytes(b"not DICOM")

    assert benchmark.removed_items(unreadable, policy, iod) is None
    assert benchmark.removed_items(tmp_path / "missing.dcm", policy, iod) is None
    assert benchmark.removed_items(None, policy, iod) is None
    source = tmp_path / "0.dcm"
    source.write_bytes(written(_report()))
    assert benchmark.removed_items(source, policy, None) is None


def test_a_finding_is_described_by_the_item_that_the_written_file_holds():
    removed = RemovedItems({((CONTENT, 0),)})
    check = parse_check(
        {
            "action": "<text_removed>",
            "tag_ds": _place((CONTENT, 3), tag="(0040,A160)"),
            "action_text": "<ITEM 2>",
        }
    )

    assert kept_word_kinds(_written_tree(), check, removed) == ("bare number, other")
    assert kept_word_kinds(_written_tree(), check) == "unknown"
