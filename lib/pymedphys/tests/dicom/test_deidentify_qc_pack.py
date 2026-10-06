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

"""The confidential QC pack and where it may be written."""

# The tests share the pack and entry builders below, so they stay in one
# module.
# pylint: disable = too-many-lines

import json
import re
import logging
import mmap
import os
import stat
import tracemalloc
import traceback
from pathlib import Path, PurePosixPath

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import qc_pack, qc_store, residuals, reviewed_roi_names
from pymedphys._dicom.deidentify.reference_graph import FindingKind
from pymedphys._dicom.deidentify.roi_names import Reason
from pymedphys._dicom.deidentify.file_layout import ElementPath, Location, Region
from pymedphys._dicom.deidentify.qc_pack import (
    Disposition,
    DropEntry,
    DropReason,
    Excerpt,
    InstanceEntry,
    QcPack,
    QcPackError,
    ReferenceFindingEntry,
    ResidualEntry,
    RetainedString,
    RoiNameEntry,
    RoiNameOutcome,
)
from pymedphys._dicom.deidentify.residuals import (
    Finding,
    Form,
    SourceValue,
    ValueKind,
    find_residuals,
)

# Invented values, distinctive enough that nothing else in a file matches them.
NAME = "ZEBEDEE^QUILLON"
SOURCE_PATH = "/imports/ZEBEDEE QUILLON/CT.1.dcm"
RETAINED = "QUILLON CLINIC CT"
REFERENCE = "A-" + "0123456789abcdef" * 2
OUTPUT = PurePosixPath("ZQ0001/2.25.1/2.25.2/2.25.3.dcm")

POSIX_ONLY = pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")


def _path(tag, *items):
    return ElementPath(tuple(items), tag)


NAME_PATH = _path("(0010,0010)")


def _written(position=0, output=OUTPUT, source=SOURCE_PATH):
    return InstanceEntry(position, source, Disposition.RELEASED, output=output)


def _sequestered(position=0, label="S-0001"):
    return InstanceEntry(
        position,
        SOURCE_PATH,
        Disposition.SEQUESTERED,
        label=label,
        reasons=("conflicting instance",),
    )


def _finding(offset=3, encoding="utf-8"):
    return Finding(
        NAME_PATH,
        ValueKind.PERSON_NAME,
        Form.NAME_COMPONENT,
        encoding,
        Location(Region.TRAILING),
        offset,
    )


def _pack(**sections):
    sections.setdefault("instances", (_written(),))
    return QcPack(REFERENCE, **sections)


def _full_pack():
    data = b"Seen by Dr Zebedee today"
    search = find_residuals(data, [SourceValue(NAME_PATH, "PN", NAME)])
    findings, omissions = qc_pack.entries_for_search(0, search, data)
    return _pack(
        instances=(_written(), _sequestered(1)),
        residual_findings=findings,
        drops=(DropEntry(0, _path("(0008,1030)"), DropReason.RETAINED),),
        not_searched=omissions,
        retained_strings=qc_pack.retained_strings(
            [(RETAINED, 1, _path("(0008,1090)")), (RETAINED, 0, _path("(0008,1090)"))]
        ),
        roi_names=(
            RoiNameEntry(
                0,
                _path("(3006,0026)", ("(3006,0020)", 2)),
                "lung l",
                RoiNameOutcome.RENAMED,
                written="Lung_L",
            ),
        ),
        reference_findings=(
            ReferenceFindingEntry(
                0, FindingKind.DANGLING_REFERENCE, ("(300C,0080)", "(0008,1155)"), 2
            ),
        ),
    )


def test_references_are_random_and_opaque():
    references = {qc_pack.new_reference() for _ in range(100)}
    assert len(references) == 100
    assert all(re.fullmatch(r"A-[0-9a-f]{32}", reference) for reference in references)


@pytest.mark.parametrize("reference", ["", "A-0123", "B-" + "0" * 32, "A-" + "G" * 32])
def test_a_pack_needs_a_reference_of_its_form(reference):
    with pytest.raises(QcPackError, match="reference"):
        QcPack(reference, (_written(),))


def test_labels_grow_beyond_four_digits():
    assert _sequestered(label="S-12345").label == "S-12345"


@pytest.mark.parametrize(
    "labels",
    [("S-0001", "S-0001"), ("S-0002",), ("S-0001", "S-00002"), ("S-00001",)],
)
def test_a_runs_labels_are_s_0001_onwards_at_one_width(labels):
    instances = tuple(
        _sequestered(position, label) for position, label in enumerate(labels)
    )
    with pytest.raises(QcPackError, match="S-0001 onwards"):
        _pack(instances=instances)


def test_labels_widen_with_the_number_of_sequestered_instances():
    labels = [f"S-{n:05d}" for n in range(1, 10001)]
    instances = tuple(
        _sequestered(position, label) for position, label in enumerate(reversed(labels))
    )
    assert len(_pack(instances=instances).instances) == 10000
    shuffled = (_sequestered(0, "S-0002"), _sequestered(1, "S-0001"))
    assert _pack(instances=shuffled).instances == shuffled


@pytest.mark.parametrize(
    "disposition", [Disposition.HELD_FOR_REVIEW, Disposition.REFUSED]
)
def test_held_and_refused_instances_have_reasons_and_no_label_or_output(disposition):
    entry = InstanceEntry(0, SOURCE_PATH, disposition, reasons=("roi name held",))
    assert entry.output is None and entry.label is None
    with pytest.raises(QcPackError, match="needs the reasons"):
        InstanceEntry(0, SOURCE_PATH, disposition)
    with pytest.raises(QcPackError, match="has no label"):
        InstanceEntry(0, SOURCE_PATH, disposition, label="S-0001", reasons=("x",))
    with pytest.raises(QcPackError, match="has no output path"):
        InstanceEntry(0, SOURCE_PATH, disposition, output=OUTPUT, reasons=("x",))


def test_a_written_instance_has_an_output_path_and_no_label():
    entry = _written()
    assert entry.output == OUTPUT and entry.label is None and not entry.reasons
    duplicate = InstanceEntry(1, SOURCE_PATH, Disposition.DUPLICATE, output=OUTPUT)
    assert duplicate.output == OUTPUT


@pytest.mark.parametrize(
    "fields, match",
    [
        ({"output": None}, "needs a relative output path"),
        ({"output": PurePosixPath("/abs/x.dcm")}, "needs a relative output path"),
        ({"output": PurePosixPath("../x.dcm")}, "needs a relative output path"),
        ({"output": PurePosixPath("a\\b.dcm")}, "needs a relative output path"),
        ({"output": PurePosixPath("C:/x.dcm")}, "needs a relative output path"),
        ({"output": "ZQ0001/x.dcm"}, "needs a relative output path"),
        ({"label": "S-0001"}, "has no label or reasons"),
        ({"reasons": ("conflicting instance",)}, "has no label or reasons"),
    ],
)
def test_a_written_instance_is_checked(fields, match):
    fields = {"output": OUTPUT, **fields}
    with pytest.raises(QcPackError, match=match):
        InstanceEntry(0, SOURCE_PATH, Disposition.RELEASED, **fields)


@pytest.mark.parametrize(
    "fields, match",
    [
        ({"output": OUTPUT}, "has no output path"),
        ({"label": None}, "needs a label"),
        ({"label": "s-0001"}, "needs a label"),
        ({"label": "S-01"}, "needs a label"),
        ({"label": "T-0001"}, "needs a label"),
        ({"reasons": ()}, "needs the reasons"),
        ({"reasons": ("",)}, "needs reasons as text"),
    ],
)
def test_a_sequestered_instance_is_checked(fields, match):
    fields = {"label": "S-0001", "reasons": ("conflicting instance",), **fields}
    with pytest.raises(QcPackError, match=match):
        InstanceEntry(0, SOURCE_PATH, Disposition.SEQUESTERED, **fields)


@pytest.mark.parametrize("position", [-1, True, 1.0, None])
def test_entries_need_a_run_position(position):
    with pytest.raises(QcPackError, match="run position"):
        InstanceEntry(position, SOURCE_PATH, Disposition.RELEASED, output=OUTPUT)
    with pytest.raises(QcPackError, match="run position"):
        DropEntry(position, NAME_PATH, DropReason.RETAINED)


def test_instances_are_one_for_each_run_position_from_0():
    with pytest.raises(QcPackError, match="one for each run position"):
        _pack(instances=(_written(1),))
    with pytest.raises(QcPackError, match="one for each run position"):
        _pack(instances=(_written(0), _written(0, PurePosixPath("b.dcm"))))
    assert len(_pack(instances=()).instances) == 0


def test_labels_and_output_paths_are_not_shared():
    with pytest.raises(QcPackError, match="S-0001 onwards"):
        _pack(instances=(_sequestered(0), _sequestered(1)))
    with pytest.raises(QcPackError, match="share an output path"):
        _pack(instances=(_written(0), _written(1)))


def test_a_duplicate_names_a_written_instance_output():
    duplicate = InstanceEntry(
        1, SOURCE_PATH, Disposition.DUPLICATE, output=PurePosixPath("other.dcm")
    )
    with pytest.raises(QcPackError, match="duplicate's output path"):
        _pack(instances=(_written(0), duplicate))
    same = InstanceEntry(1, SOURCE_PATH, Disposition.DUPLICATE, output=OUTPUT)
    assert _pack(instances=(_written(0), same)).instances[1] is same


@pytest.mark.parametrize(
    "section, entry",
    [
        ("residual_findings", ResidualEntry(1, _finding())),
        ("drops", DropEntry(1, NAME_PATH, DropReason.WRITTEN_CONSTANT)),
        (
            "roi_names",
            RoiNameEntry(1, NAME_PATH, "x", RoiNameOutcome.HELD, Reason.UNMATCHED),
        ),
        ("retained_strings", RetainedString(RETAINED, ((1, NAME_PATH),))),
        (
            "reference_findings",
            ReferenceFindingEntry(1, FindingKind.DANGLING_REFERENCE, ("(0008,1155)",)),
        ),
    ],
)
def test_entries_name_an_instance(section, entry):
    with pytest.raises(QcPackError, match="without an instance"):
        _pack(**{section: (entry,)})


def test_sections_hold_their_own_entries():
    with pytest.raises(QcPackError, match="drops must be a tuple of DropEntry"):
        _pack(drops=[DropEntry(0, NAME_PATH, DropReason.RETAINED)])
    with pytest.raises(QcPackError, match="instances must be a tuple"):
        _pack(instances=(_written(), "x"))


@pytest.mark.deid_requirement("MIDI-BP-17")
def test_retained_strings_are_grouped_by_value():
    title, other = _path("(0008,1090)"), _path("(0008,1010)")
    grouped = qc_pack.retained_strings(
        [
            (RETAINED, 2, title),
            ("Other", 1, other),
            (RETAINED, 0, title),
            (RETAINED, 2, title),
            (RETAINED.lower(), 0, other),
        ]
    )
    assert [(entry.value, entry.places) for entry in grouped] == [
        (RETAINED.lower(), ((0, other),)),
        (RETAINED, ((0, title), (2, title))),
        ("Other", ((1, other),)),
    ]
    with pytest.raises(QcPackError, match="each value once"):
        _pack(
            instances=(_written(),),
            retained_strings=(
                RetainedString(RETAINED, ((0, title),)),
                RetainedString(RETAINED, ((0, other),)),
            ),
        )


def test_a_retained_string_keeps_its_places_distinct_and_in_order():
    first, second = (0, _path("(0008,1090)")), (1, _path("(0008,1090)"))
    with pytest.raises(QcPackError, match="distinct and in order"):
        RetainedString(RETAINED, (second, first))
    with pytest.raises(QcPackError, match="distinct and in order"):
        RetainedString(RETAINED, (first, first))
    with pytest.raises(QcPackError, match="places"):
        RetainedString(RETAINED, ())
    with pytest.raises(QcPackError, match="text, a run position"):
        qc_pack.retained_strings([(RETAINED, 0, "(0008,1090)")])


@pytest.mark.parametrize(
    "outcome, held_because, written",
    [
        (RoiNameOutcome.RENAMED, None, "Lung_L"),
        (RoiNameOutcome.EMPTY, None, ""),
        (RoiNameOutcome.KEPT, None, "lung l"),
        (RoiNameOutcome.MAPPED, None, "Lung_Left"),
        (RoiNameOutcome.EMPTIED, None, ""),
        (RoiNameOutcome.HELD, Reason.UNMATCHED, None),
        (RoiNameOutcome.HELD, Reason.WOULD_DUPLICATE, None),
        (RoiNameOutcome.EMPTIED_UNREVIEWED, Reason.ECHOES_IDENTIFIER, ""),
        (RoiNameOutcome.EMPTIED_UNREVIEWED, Reason.AMBIGUOUS, ""),
    ],
)
def test_each_roi_name_outcome_is_accepted(outcome, held_because, written):
    entry = RoiNameEntry(0, NAME_PATH, "lung l", outcome, held_because, written)
    assert entry.written == written


@pytest.mark.parametrize(
    "outcome, held_because, written, match",
    [
        (RoiNameOutcome.HELD, None, None, "reason for review"),
        (RoiNameOutcome.HELD, Reason.MATCHED, None, "reason for review"),
        (RoiNameOutcome.RENAMED, Reason.UNMATCHED, "Lung_L", "reason for review"),
        (RoiNameOutcome.HELD, Reason.UNMATCHED, "", "has nothing written"),
        (RoiNameOutcome.RENAMED, None, None, "needs what was written"),
        (RoiNameOutcome.RENAMED, None, "", "written empty only"),
        (RoiNameOutcome.MAPPED, None, "", "written empty only"),
        (RoiNameOutcome.EMPTIED, None, "x", "written empty only"),
        (RoiNameOutcome.EMPTIED_UNREVIEWED, Reason.UNMATCHED, "x", "written empty"),
        (RoiNameOutcome.KEPT, None, "Lung_L", "written as its source name"),
    ],
)
def test_a_roi_name_entry_is_consistent(outcome, held_because, written, match):
    with pytest.raises(QcPackError, match=match):
        RoiNameEntry(0, NAME_PATH, "lung l", outcome, held_because, written)


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_a_held_roi_name_lists_the_institutional_names_it_matched():
    held = RoiNameEntry(
        0,
        NAME_PATH,
        "clinicx lung",
        RoiNameOutcome.HELD,
        Reason.UNMATCHED,
        institutional_matches=("CLINICX_LUNG", "ClinicX_Lung"),
    )
    emptied = RoiNameEntry(
        0,
        NAME_PATH,
        "clinicx lung",
        RoiNameOutcome.EMPTIED_UNREVIEWED,
        Reason.UNMATCHED,
        "",
        institutional_matches=("ClinicX_Lung",),
    )

    assert held.institutional_matches == ("CLINICX_LUNG", "ClinicX_Lung")
    assert emptied.institutional_matches == ("ClinicX_Lung",)
    assert "ClinicX" not in repr(held)


@pytest.mark.parametrize(
    "outcome, held_because, written, matches, match",
    [
        (RoiNameOutcome.RENAMED, None, "Lung_L", ("Lung_L",), "only when it was held"),
        (RoiNameOutcome.KEPT, None, "lung l", ("Lung_L",), "only when it was held"),
        (RoiNameOutcome.HELD, Reason.UNMATCHED, None, ["Lung_L"], "names as text"),
        (RoiNameOutcome.HELD, Reason.UNMATCHED, None, (1,), "names as text"),
        (RoiNameOutcome.HELD, Reason.UNMATCHED, None, ("",), "names as text"),
    ],
)
def test_institutional_matches_are_names_of_a_held_roi_name_only(
    outcome, held_because, written, matches, match
):
    with pytest.raises(QcPackError, match=match):
        RoiNameEntry(
            0,
            NAME_PATH,
            "lung l",
            outcome,
            held_because,
            written,
            institutional_matches=matches,
        )


def test_roi_name_outcomes_are_named_as_descriptor_cleaning_names_them():
    assert [outcome.value for outcome in RoiNameOutcome] == [
        "renamed",
        "empty",
        "kept",
        "mapped",
        "emptied",
        "held",
        "emptied unreviewed",
    ]


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.parametrize(
    "fields",
    [
        ("dangling-reference", ("(0008,1155)",), 1),
        (FindingKind.DANGLING_REFERENCE, (), 1),
        (FindingKind.DANGLING_REFERENCE, "(0008,1155)", 1),
        (FindingKind.DANGLING_REFERENCE, ("SENTINEL",), 1),
        (FindingKind.DANGLING_REFERENCE, ("(0008,1155)",), -1),
        (FindingKind.DANGLING_REFERENCE, ("(0008,1155)",), True),
    ],
    ids=["kind", "no-tags", "tags-as-text", "not-a-tag", "negative", "boolean"],
)
def test_a_reference_finding_entry_is_checked(fields):
    with pytest.raises(QcPackError, match="reference finding") as raised:
        ReferenceFindingEntry(0, *fields)
    assert "SENTINEL" not in str(raised.value)


@pytest.mark.deid_requirement("MIDI-BP-17")
def test_an_excerpt_shows_the_bytes_around_a_residual():
    data = b"Seen by Dr Zebedee today"
    search = find_residuals(data, [SourceValue(NAME_PATH, "PN", NAME)])
    (finding,) = search.findings
    assert qc_pack.excerpt(data, finding) == Excerpt(
        "Seen by Dr ", "Zebedee today", "utf-8"
    )


def test_an_excerpt_is_bounded():
    data = b"." * 200 + b"Zebedee" + b"," * 200
    (finding,) = find_residuals(data, [SourceValue(NAME_PATH, "PN", NAME)]).findings
    cut = qc_pack.excerpt(data, finding)
    assert cut.before == "." * qc_pack.EXCERPT_BYTES
    assert cut.after == "Zebedee" + "," * (2 * qc_pack.EXCERPT_BYTES - 7)


def test_an_excerpt_of_utf_16_keeps_to_whole_characters():
    data = b"\x00" + (" " * 30 + "Zebedee").encode("utf-16-le")
    (finding,) = find_residuals(data, [SourceValue(NAME_PATH, "PN", NAME)]).findings
    assert finding.encoding == "utf-16-le" and finding.offset % 2 == 1
    cut = qc_pack.excerpt(data, finding)
    assert cut.before == " " * (qc_pack.EXCERPT_BYTES // 2)
    assert cut.after == "Zebedee"


def test_an_excerpt_escapes_bytes_its_codec_cannot_decode():
    data = b"\xff\xfeZebedee\x80"
    (finding,) = find_residuals(data, [SourceValue(NAME_PATH, "PN", NAME)]).findings
    cut = qc_pack.excerpt(data, finding)
    assert (cut.before, cut.after) == ("\\xff\\xfe", "Zebedee\\x80")


def test_an_excerpt_needs_the_residual_offset_in_the_file():
    with pytest.raises(QcPackError, match="not in the file"):
        qc_pack.excerpt(b"abc", _finding(offset=3))


@pytest.mark.deid_requirement("MIDI-BP-17")
def test_a_search_gives_entries_with_excerpts_and_omissions():
    data = b"Seen by Dr Zebedee today"
    values = [
        SourceValue(NAME_PATH, "PN", NAME),
        SourceValue(_path("(0010,1010)"), "AS", "041Y"),
    ]
    search = find_residuals(data, values)
    findings, omissions = qc_pack.entries_for_search(3, search, data)
    assert [entry.finding for entry in findings] == list(search.findings)
    assert all(entry.position == 3 and entry.excerpt for entry in findings)
    assert [entry.omission for entry in omissions] == list(search.not_searched)
    assert omissions and all(entry.position == 3 for entry in omissions)


@pytest.mark.deid_requirement("MIDI-BP-17")
def test_the_document_holds_every_section():
    document = json.loads(qc_pack.to_json(_full_pack()))
    assert document["format"] == qc_pack.FORMAT == "pymedphys-deid-qc-pack/1"
    assert document["reference"] == REFERENCE
    assert document["instances"] == [
        {
            "position": 0,
            "source": SOURCE_PATH,
            "disposition": "released",
            "output": OUTPUT.as_posix(),
            "label": None,
            "reasons": [],
        },
        {
            "position": 1,
            "source": SOURCE_PATH,
            "disposition": "sequestered",
            "output": None,
            "label": "S-0001",
            "reasons": ["conflicting instance"],
        },
    ]
    (residual,) = document["residual_findings"]
    assert residual == {
        "position": 0,
        "source": "(0010,0010)",
        "kind": "person-name",
        "form": "name-component",
        "encoding": "utf-8",
        "location": {
            "region": "trailing-bytes",
            "element": None,
            "vr": None,
            "item": None,
            "description": "bytes after the last readable element",
        },
        "offset": 11,
        "excerpt": {
            "before": "Seen by Dr ",
            "after": "Zebedee today",
            "encoding": "utf-8",
        },
    }
    assert document["drops"] == [
        {"position": 0, "source": "(0008,1030)", "reason": "retained"}
    ]
    assert document["retained_strings"] == [
        {
            "value": RETAINED,
            "places": [
                {"position": 0, "element": "(0008,1090)"},
                {"position": 1, "element": "(0008,1090)"},
            ],
        }
    ]
    assert document["roi_names"] == [
        {
            "position": 0,
            "element": "(3006,0020)[2] > (3006,0026)",
            "source": "lung l",
            "outcome": "renamed",
            "held_because": None,
            "written": "Lung_L",
            "institutional_matches": [],
        }
    ]
    assert document["reference_findings"] == [
        {
            "position": 0,
            "kind": "dangling-reference",
            "attribute": "(300C,0080) > (0008,1155)",
            "count": 2,
        }
    ]
    assert list(document) == [
        "format",
        "reference",
        "instances",
        "residual_findings",
        "drops",
        "not_searched",
        "retained_strings",
        "roi_names",
        "reference_findings",
        "pixel_risks",
        "series_risks",
        "previews",
        "not_previewed",
    ]


def test_the_document_is_ascii_and_keeps_undecodable_paths():
    undecodable = os.fsdecode(b"/imports/\xff\xfe.dcm") if os.name == "posix" else "x"
    pack = _pack(instances=(_written(source=undecodable + "é"),))
    text = qc_pack.to_json(pack)
    assert text.isascii() and text.endswith("\n")
    assert json.loads(text)["instances"][0]["source"] == undecodable + "é"


def test_the_document_is_deterministic():
    pack = _full_pack()
    assert qc_pack.to_json(pack) == qc_pack.to_json(pack)


def test_reprs_hold_no_paths_or_values():
    pack = _full_pack()
    shown = repr(pack) + repr(pack.instances) + repr(pack.retained_strings)
    shown += repr(pack.roi_names)
    for secret in (SOURCE_PATH, RETAINED, "lung l", "Lung_L"):
        assert secret not in shown


def test_errors_hold_no_paths_or_values(tmp_path):
    release = tmp_path / "ZEBEDEE release"
    messages = []
    for attempt in (
        lambda: InstanceEntry(0, SOURCE_PATH, Disposition.RELEASED),
        lambda: RetainedString(RETAINED, ()),
        lambda: qc_store.check_confidential_destination(
            release / "qc", release_directory=release
        ),
    ):
        with pytest.raises(QcPackError) as raised:
            attempt()
        messages.append(str(raised.value))
    for secret in (SOURCE_PATH, RETAINED, "ZEBEDEE", str(tmp_path)):
        assert all(secret not in message for message in messages)


@pytest.fixture(name="places")
def fixture_places(tmp_path):
    release, staging = tmp_path / "release", tmp_path / "staging"
    release.mkdir()
    staging.mkdir()
    return tmp_path, release, staging


@pytest.mark.deid_requirement("MIDI-BP-17")
@pytest.mark.parametrize(
    "where",
    ["release", "release/qc", "release/a/b/qc", "staging/qc", "", "."],
)
def test_the_destination_is_neither_in_nor_around_releases(places, where):
    root, release, staging = places
    with pytest.raises(QcPackError, match="neither inside the"):
        qc_store.check_confidential_destination(
            root / where, release_directory=release, staging_directory=staging
        )


def test_the_destination_is_compared_once_resolved(places, monkeypatch):
    root, release, _ = places
    monkeypatch.chdir(release)
    with pytest.raises(QcPackError, match="inside the release directory"):
        qc_store.check_confidential_destination("qc", release_directory=release)
    with pytest.raises(QcPackError, match="inside the release directory"):
        qc_store.check_confidential_destination(
            root / "elsewhere" / ".." / "release" / "qc", release_directory=release
        )


@pytest.mark.deid_requirement("MIDI-BP-17")
@pytest.mark.parametrize("where", ["source/qc", "source/a/qc"])
def test_the_destination_is_outside_the_source_directory(places, where):
    root, release, staging = places
    (root / "source").mkdir()
    with pytest.raises(QcPackError, match="inside the source directory"):
        qc_store.check_confidential_destination(
            root / where,
            release_directory=release,
            staging_directory=staging,
            source_directory=root / "source",
        )
    with pytest.raises(QcPackError, match="inside the source directory"):
        qc_store.write_qc_pack(
            _full_pack(),
            root / where,
            release_directory=release,
            source_directory=root / "source",
        )
    assert os.listdir(root / "source") == []


@POSIX_ONLY
def test_a_link_into_the_release_directory_is_refused(places):
    root, release, _ = places
    (root / "link").symlink_to(release, target_is_directory=True)
    with pytest.raises(QcPackError, match="inside the release directory"):
        qc_store.check_confidential_destination(
            root / "link" / "qc", release_directory=release
        )


def test_the_destination_has_no_default(places):
    root, release, _ = places
    with pytest.raises(TypeError):
        qc_store.check_confidential_destination(root / "qc")  # pylint: disable = missing-kwoa
    with pytest.raises(QcPackError, match="must be given as a path"):
        qc_store.check_confidential_destination("", release_directory=release)
    with pytest.raises(QcPackError, match="must be given as a path"):
        qc_store.check_confidential_destination(None, release_directory=release)


def test_the_destination_is_new_or_empty(places):
    root, release, _ = places
    (root / "file").write_text("x")
    with pytest.raises(QcPackError, match="not a directory"):
        qc_store.check_confidential_destination(
            root / "file", release_directory=release
        )
    full = root / "full"
    full.mkdir(mode=0o700)
    (full / "x").write_text("x")
    with pytest.raises(QcPackError, match="new or an empty directory"):
        qc_store.check_confidential_destination(full, release_directory=release)
    new = root / "new" / "qc"
    assert qc_store.check_confidential_destination(new, release_directory=release) == (
        new.resolve()
    )


@POSIX_ONLY
def test_an_existing_destination_is_restricted_to_its_owner(places):
    root, release, _ = places
    shared = root / "shared"
    shared.mkdir()
    shared.chmod(0o750)
    with pytest.raises(QcPackError, match="chmod 700"):
        qc_store.check_confidential_destination(shared, release_directory=release)
    shared.chmod(0o700)
    assert qc_store.check_confidential_destination(shared, release_directory=release)


def test_a_pack_is_written_with_its_marker_and_notice(places):
    root, release, staging = places
    written = qc_store.write_qc_pack(
        _full_pack(),
        root / "qc" / "run-1",
        release_directory=release,
        staging_directory=staging,
    )
    directory = written.parent
    assert written == (root / "qc" / "run-1" / qc_store.PACK_FILE).resolve()
    assert sorted(path.name for path in directory.iterdir()) == sorted(
        [qc_store.MARKER_FILE, qc_store.PACK_FILE, qc_store.NOTICE_FILE]
    )
    assert json.loads(written.read_text("ascii")) == qc_pack.pack_document(_full_pack())
    assert (directory / qc_store.MARKER_FILE).read_text() == qc_pack.FORMAT + "\n"
    notice = (directory / qc_store.NOTICE_FILE).read_text()
    assert notice == qc_store.NOTICE and "CONFIDENTIAL" in notice
    assert "delete the whole directory" in notice


@pytest.mark.deid_requirement("MIDI-BP-17")
@POSIX_ONLY
def test_a_written_pack_is_readable_only_by_its_owner(places):
    root, release, _ = places
    old = os.umask(0)
    try:
        written = qc_store.write_qc_pack(
            _pack(), root / "qc", release_directory=release
        )
    finally:
        os.umask(old)
    assert stat.S_IMODE(written.parent.stat().st_mode) == 0o700
    for path in written.parent.iterdir():
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_a_pack_never_overwrites(places):
    root, release, _ = places
    qc_store.write_qc_pack(_pack(), root / "qc", release_directory=release)
    with pytest.raises(QcPackError, match="new or an empty directory"):
        qc_store.write_qc_pack(_pack(), root / "qc", release_directory=release)


def test_nothing_is_written_for_a_bad_pack_or_destination(places):
    root, release, _ = places
    with pytest.raises(TypeError, match="QcPack"):
        qc_store.write_qc_pack("pack", root / "qc", release_directory=release)
    with pytest.raises(QcPackError):
        qc_store.write_qc_pack(_pack(), release / "qc", release_directory=release)
    assert not (root / "qc").exists() and not any(release.iterdir())


@pytest.mark.deid_requirement("MIDI-BP-17")
def test_qc_material_is_recognised_wherever_it_is(places):
    root, release, _ = places
    written = qc_store.write_qc_pack(
        _pack(), root / "store" / "qc", release_directory=release
    )
    assert qc_store.is_qc_material(written.parent)
    assert qc_store.is_qc_material(written)
    assert qc_store.is_qc_material(written.parent / "later" / "file.png")
    assert qc_store.is_qc_material(root / "store")
    assert qc_store.is_qc_material(root)
    assert not qc_store.is_qc_material(release)
    assert not qc_store.is_qc_material(root / "missing")


def test_a_release_that_gained_qc_material_is_recognised(places):
    _, release, _ = places
    (release / "ZQ0001").mkdir()
    assert not qc_store.is_qc_material(release)
    (release / "ZQ0001" / qc_store.MARKER_FILE).write_text(qc_pack.FORMAT)
    assert qc_store.is_qc_material(release)


def test_nothing_is_logged(places, caplog):
    root, release, _ = places
    with caplog.at_level(logging.DEBUG):
        qc_store.write_qc_pack(_full_pack(), root / "qc", release_directory=release)
    assert not caplog.records


def test_the_destination_may_be_given_as_text(places):
    root, release, _ = places
    written = qc_store.write_qc_pack(
        _pack(), str(root / "qc"), release_directory=str(release)
    )
    assert isinstance(written, Path) and written.is_file()


def test_residual_reprs_hold_no_text():
    shown = repr(_full_pack().residual_findings)
    assert "Zebedee" not in shown and "Seen by" not in shown
    assert "Excerpt(before=11 characters, after=13 characters" in shown


def test_an_excerpt_in_iso_2022_keeps_its_shift_state():
    data = ("前" * 30 + "山田太郎").encode("iso2022_jp") + b"tail"
    offset = 3 + 60  # after the escape sequence and thirty characters
    cut = qc_pack.excerpt(data, _finding(offset, "iso2022_jp"))
    assert cut.before == "前" * (qc_pack.EXCERPT_BYTES // 2)
    assert cut.after.startswith("山田太郎") and cut.after.endswith("tail")


def _peak_allocation(function):
    tracemalloc.start()
    try:
        function()
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


@pytest.mark.parametrize(
    "prefix, encoding",
    [
        (b"." * (16 * 2**20), "utf-8"),
        # The escape sequence that sets the state is 4 MiB before the excerpt.
        (b"\x1b$B" + b"0!" * (2 * 2**20), "iso2022_jp"),
    ],
    # Pytest puts the case id in PYTEST_CURRENT_TEST; the multi-MiB input
    # exceeds Windows' 32,767-character environment variable limit.
    ids=["large-utf8", "large-iso2022-jp"],
)
def test_an_excerpt_of_a_late_residual_needs_little_memory(tmp_path, prefix, encoding):
    path = tmp_path / "large.dcm"
    path.write_bytes(prefix + b"\x1b(BZebedee today")
    offset = len(prefix) + 3
    with (
        path.open("rb") as file,
        mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as mapped,
    ):
        cuts = []
        peak = _peak_allocation(
            lambda: cuts.append(qc_pack.excerpt(mapped, _finding(offset, encoding)))
        )
    assert peak < 2**20
    assert cuts[0].after == "Zebedee today"
    if encoding == "iso2022_jp":  # decoded in the state the escape set
        assert set(cuts[0].before) == {"亜"}


def test_an_excerpt_tells_backslashes_from_undecoded_bytes():
    data = b"a\\x41 Zebedee\xff"
    (finding,) = find_residuals(data, [SourceValue(NAME_PATH, "PN", NAME)]).findings
    cut = qc_pack.excerpt(data, finding)
    assert (cut.before, cut.after) == ("a\\x5cx41 ", "Zebedee\\xff")


def test_an_excerpt_falls_back_to_latin_1_and_says_so():
    cut = qc_pack.excerpt(b"Dr Zebedee\xe9", _finding(3, "no-such-codec"))
    assert cut == Excerpt("Dr ", "Zebedeeé", "latin-1")


def _shows_no_path(error, *paths):
    """Check that no exception that a traceback of ``error`` shows names a path.

    The traceback's source lines are left out, since a test's own source
    names the paths it uses.
    """
    shown = []
    while error is not None:
        shown.extend(traceback.format_exception_only(error))
        error = error.__cause__ or (
            None if error.__suppress_context__ else error.__context__
        )
    return not any(str(path) in "".join(shown) for path in ("ZEBEDEE", *paths))


def test_os_errors_name_no_path(places):
    root, release, _ = places
    (root / "ZEBEDEE").write_text("x")
    with pytest.raises(QcPackError, match="could not be created") as raised:
        qc_store.write_qc_pack(
            _pack(), root / "ZEBEDEE" / "qc", release_directory=release
        )
    assert _shows_no_path(raised.value, root)


def test_a_directory_that_cannot_be_read_leaves_the_answer_unknown(places, monkeypatch):
    root, _, _ = places

    def walk(top, onerror):
        # os.walk reports an error from within its exception handler, so
        # the error becomes the context of whatever the callback raises.
        try:
            raise PermissionError(13, "Permission denied", str(top / "ZEBEDEE"))
        except PermissionError as error:
            onerror(error)
        yield from ()

    monkeypatch.setattr(qc_store.os, "walk", walk)
    with pytest.raises(QcPackError, match="could not be read") as raised:
        qc_store.is_qc_material(root)
    assert _shows_no_path(raised.value, root)


def _refuse_stat(monkeypatch, refused):
    """Make ``os.stat`` fail with a permission error for paths ``refused`` picks."""
    real = os.stat

    def fake(path, *args, **kwargs):
        if refused(os.fspath(path)):
            raise PermissionError(13, "Permission denied", os.fspath(path))
        return real(path, *args, **kwargs)

    monkeypatch.setattr(qc_store.os, "stat", fake)


def test_a_marker_that_cannot_be_checked_leaves_the_answer_unknown(places, monkeypatch):
    root, _, _ = places
    (root / "ZEBEDEE").mkdir()
    _refuse_stat(monkeypatch, lambda path: path.endswith(qc_store.MARKER_FILE))
    with pytest.raises(QcPackError, match="could not be read") as raised:
        qc_store.is_qc_material(root / "ZEBEDEE")
    assert _shows_no_path(raised.value, root)


def test_a_path_that_cannot_be_checked_leaves_the_answer_unknown(places, monkeypatch):
    root, _, _ = places
    (root / "ZEBEDEE").mkdir()
    _refuse_stat(monkeypatch, lambda path: path == str(root / "ZEBEDEE"))
    with pytest.raises(QcPackError, match="could not be read") as raised:
        qc_store.is_qc_material(root / "ZEBEDEE")
    assert _shows_no_path(raised.value, root)


def test_a_destination_that_cannot_be_checked_is_refused(places, monkeypatch):
    root, release, _ = places
    _refuse_stat(monkeypatch, lambda path: "ZEBEDEE" in path)
    with pytest.raises(QcPackError, match="could not be checked") as raised:
        qc_store.write_qc_pack(
            _pack(), root / "ZEBEDEE" / "qc", release_directory=release
        )
    assert _shows_no_path(raised.value, root)
    monkeypatch.undo()  # before Python 3.12, Path.exists raises for EACCES
    assert not (root / "ZEBEDEE").exists()


def test_a_path_that_cannot_be_resolved_shows_no_path(monkeypatch):
    def resolve(self, strict=False):
        raise PermissionError(13, "Permission denied", str(self))

    monkeypatch.setattr(qc_store.Path, "resolve", resolve)
    with pytest.raises(QcPackError, match="could not be resolved") as raised:
        qc_store.check_confidential_destination(
            "/srv/ZEBEDEE/qc", release_directory="/srv/release"
        )
    assert _shows_no_path(raised.value)


@POSIX_ONLY
def test_links_to_qc_material_are_qc_material(places):
    root, release, _ = places
    written = qc_store.write_qc_pack(
        _pack(), root / "secure" / "qc", release_directory=release
    )
    (release / "ZQ0001").mkdir()
    assert not qc_store.is_qc_material(release)
    (release / "ZQ0001" / "notes.json").symlink_to(written)
    assert qc_store.is_qc_material(release)
    (release / "ZQ0001" / "notes.json").unlink()
    (release / "ZQ0001" / "more").symlink_to(root / "secure", target_is_directory=True)
    assert qc_store.is_qc_material(release)


@POSIX_ONLY
def test_a_link_loop_is_not_qc_material(places):
    _, release, _ = places
    (release / "loop").symlink_to(release, target_is_directory=True)
    assert not qc_store.is_qc_material(release)


@POSIX_ONLY
def test_the_same_directory_by_another_path_is_found_by_its_inode(places):
    root, release, _ = places
    (root / "alias").symlink_to(release, target_is_directory=True)
    # Unresolved, the alias is not below the release directory by its name.
    assert qc_store._within(root / "alias" / "qc", release)  # pylint: disable = protected-access
    assert not qc_store._within(root / "qc", release)  # pylint: disable = protected-access


@POSIX_ONLY
def test_a_destination_replaced_while_it_is_checked_is_refused(places, monkeypatch):
    root, release, _ = places
    check = qc_store.check_confidential_destination
    calls = []

    def racing(destination, **kwargs):
        checked = check(destination, **kwargs)
        if not calls:
            Path(destination).symlink_to(release, target_is_directory=True)
        calls.append(destination)
        return checked

    monkeypatch.setattr(qc_store, "check_confidential_destination", racing)
    with pytest.raises(QcPackError):
        qc_store.write_qc_pack(_pack(), root / "qc", release_directory=release)
    assert not any(release.iterdir())


def test_a_new_file_is_not_created_for_text_that_is_not_ascii(tmp_path):
    with pytest.raises(UnicodeEncodeError):
        qc_store.write_new(tmp_path / "x.json", "é")
    assert not (tmp_path / "x.json").exists()


def test_a_kept_roi_name_is_written_without_its_padding():
    entry = RoiNameEntry(
        0, NAME_PATH, " lung l\x00", RoiNameOutcome.KEPT, written="lung l"
    )
    assert entry.written == "lung l"
    with pytest.raises(QcPackError, match="without padding"):
        RoiNameEntry(
            0, NAME_PATH, " lung l\x00", RoiNameOutcome.KEPT, written=" lung l"
        )


def test_drop_reasons_are_named_as_the_residual_search_names_them():
    assert [reason.value for reason in DropReason] == [
        "retained",
        "written-constant",
        "undecodable",
        "registered-uid",
    ]


def test_the_pack_uses_the_release_report_and_search_names():
    assert qc_pack.DropReason is residuals.UnsearchedReason
    assert qc_pack.RoiNameOutcome is reviewed_roi_names.Outcome
    with pytest.raises(QcPackError, match="label"):
        _sequestered(label="S-001")
