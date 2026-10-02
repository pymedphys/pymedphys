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

import json
import re
import logging
import os
import stat
from pathlib import Path, PurePosixPath

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import qc_pack
from pymedphys._dicom.deidentify.file_layout import ElementPath, Location, Region
from pymedphys._dicom.deidentify.qc_pack import (
    Disposition,
    DropEntry,
    DropReason,
    Excerpt,
    InstanceEntry,
    QcPack,
    QcPackError,
    ResidualEntry,
    RetainedString,
    RoiNameEntry,
    RoiNameStatus,
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
    return InstanceEntry(position, source, Disposition.WRITTEN, output=output)


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
                RoiNameStatus.RENAMED,
                "Lung_L",
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
        ({"output": "ZQ0001/x.dcm"}, "needs a relative output path"),
        ({"label": "S-0001"}, "has no label or reasons"),
        ({"reasons": ("conflicting instance",)}, "has no label or reasons"),
    ],
)
def test_a_written_instance_is_checked(fields, match):
    fields = {"output": OUTPUT, **fields}
    with pytest.raises(QcPackError, match=match):
        InstanceEntry(0, SOURCE_PATH, Disposition.WRITTEN, **fields)


@pytest.mark.parametrize(
    "fields, match",
    [
        ({"output": OUTPUT}, "has no output path"),
        ({"label": None}, "needs a label"),
        ({"label": "s-0001"}, "needs a label"),
        ({"label": "S-01"}, "needs a label"),
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
        InstanceEntry(position, SOURCE_PATH, Disposition.WRITTEN, output=OUTPUT)
    with pytest.raises(QcPackError, match="run position"):
        DropEntry(position, NAME_PATH, DropReason.RETAINED)


def test_instances_are_one_for_each_run_position_from_0():
    with pytest.raises(QcPackError, match="one for each run position"):
        _pack(instances=(_written(1),))
    with pytest.raises(QcPackError, match="one for each run position"):
        _pack(instances=(_written(0), _written(0, PurePosixPath("b.dcm"))))
    assert len(_pack(instances=()).instances) == 0


def test_labels_and_output_paths_are_not_shared():
    with pytest.raises(QcPackError, match="share a label"):
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
        ("drops", DropEntry(1, NAME_PATH, DropReason.ENGINE_CONSTANT)),
        ("roi_names", RoiNameEntry(1, NAME_PATH, "x", RoiNameStatus.AWAITING_REVIEW)),
        ("retained_strings", RetainedString(RETAINED, ((1, NAME_PATH),))),
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


def test_a_roi_name_has_a_vocabulary_name_only_when_renamed():
    with pytest.raises(QcPackError, match="only when it was renamed"):
        RoiNameEntry(0, NAME_PATH, "lung l", RoiNameStatus.RENAMED)
    with pytest.raises(QcPackError, match="only when it was renamed"):
        RoiNameEntry(0, NAME_PATH, "x", RoiNameStatus.AWAITING_REVIEW, "Lung_L")


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


def test_the_document_holds_every_section():
    document = json.loads(qc_pack.to_json(_full_pack()))
    assert document["format"] == qc_pack.FORMAT == "pymedphys-deid-qc-pack/1"
    assert document["reference"] == REFERENCE
    assert document["instances"] == [
        {
            "position": 0,
            "source": SOURCE_PATH,
            "disposition": "written",
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
            "name": "lung l",
            "status": "renamed",
            "vocabulary_name": "Lung_L",
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
        lambda: InstanceEntry(0, SOURCE_PATH, Disposition.WRITTEN),
        lambda: RetainedString(RETAINED, ()),
        lambda: qc_pack.check_confidential_destination(
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


@pytest.mark.parametrize(
    "where",
    ["release", "release/qc", "release/a/b/qc", "staging/qc", "", "."],
)
def test_the_destination_is_neither_in_nor_around_releases(places, where):
    root, release, staging = places
    with pytest.raises(QcPackError, match="neither inside the"):
        qc_pack.check_confidential_destination(
            root / where, release_directory=release, staging_directory=staging
        )


def test_the_destination_is_compared_once_resolved(places, monkeypatch):
    root, release, _ = places
    monkeypatch.chdir(release)
    with pytest.raises(QcPackError, match="inside the release directory"):
        qc_pack.check_confidential_destination("qc", release_directory=release)
    with pytest.raises(QcPackError, match="inside the release directory"):
        qc_pack.check_confidential_destination(
            root / "elsewhere" / ".." / "release" / "qc", release_directory=release
        )


@POSIX_ONLY
def test_a_link_into_the_release_directory_is_refused(places):
    root, release, _ = places
    (root / "link").symlink_to(release, target_is_directory=True)
    with pytest.raises(QcPackError, match="inside the release directory"):
        qc_pack.check_confidential_destination(
            root / "link" / "qc", release_directory=release
        )


def test_the_destination_has_no_default(places):
    root, release, _ = places
    with pytest.raises(TypeError):
        qc_pack.check_confidential_destination(root / "qc")  # pylint: disable = missing-kwoa
    with pytest.raises(QcPackError, match="must be given as a path"):
        qc_pack.check_confidential_destination("", release_directory=release)
    with pytest.raises(QcPackError, match="must be given as a path"):
        qc_pack.check_confidential_destination(None, release_directory=release)


def test_the_destination_is_new_or_empty(places):
    root, release, _ = places
    (root / "file").write_text("x")
    with pytest.raises(QcPackError, match="not a directory"):
        qc_pack.check_confidential_destination(root / "file", release_directory=release)
    full = root / "full"
    full.mkdir(mode=0o700)
    (full / "x").write_text("x")
    with pytest.raises(QcPackError, match="new or an empty directory"):
        qc_pack.check_confidential_destination(full, release_directory=release)
    new = root / "new" / "qc"
    assert qc_pack.check_confidential_destination(new, release_directory=release) == (
        new.resolve()
    )


@POSIX_ONLY
def test_an_existing_destination_is_restricted_to_its_owner(places):
    root, release, _ = places
    shared = root / "shared"
    shared.mkdir()
    shared.chmod(0o750)
    with pytest.raises(QcPackError, match="chmod 700"):
        qc_pack.check_confidential_destination(shared, release_directory=release)
    shared.chmod(0o700)
    assert qc_pack.check_confidential_destination(shared, release_directory=release)


def test_a_pack_is_written_with_its_marker_and_notice(places):
    root, release, staging = places
    written = qc_pack.write_qc_pack(
        _full_pack(),
        root / "qc" / "run-1",
        release_directory=release,
        staging_directory=staging,
    )
    directory = written.parent
    assert written == (root / "qc" / "run-1" / qc_pack.PACK_FILE).resolve()
    assert sorted(path.name for path in directory.iterdir()) == sorted(
        [qc_pack.MARKER_FILE, qc_pack.PACK_FILE, qc_pack.NOTICE_FILE]
    )
    assert json.loads(written.read_text("ascii")) == qc_pack.pack_document(_full_pack())
    assert (directory / qc_pack.MARKER_FILE).read_text() == qc_pack.FORMAT + "\n"
    notice = (directory / qc_pack.NOTICE_FILE).read_text()
    assert notice == qc_pack.NOTICE and "CONFIDENTIAL" in notice
    assert "delete the whole directory" in notice


@POSIX_ONLY
def test_a_written_pack_is_readable_only_by_its_owner(places):
    root, release, _ = places
    old = os.umask(0)
    try:
        written = qc_pack.write_qc_pack(_pack(), root / "qc", release_directory=release)
    finally:
        os.umask(old)
    assert stat.S_IMODE(written.parent.stat().st_mode) == 0o700
    for path in written.parent.iterdir():
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_a_pack_never_overwrites(places):
    root, release, _ = places
    qc_pack.write_qc_pack(_pack(), root / "qc", release_directory=release)
    with pytest.raises(QcPackError, match="new or an empty directory"):
        qc_pack.write_qc_pack(_pack(), root / "qc", release_directory=release)


def test_nothing_is_written_for_a_bad_pack_or_destination(places):
    root, release, _ = places
    with pytest.raises(TypeError, match="QcPack"):
        qc_pack.write_qc_pack("pack", root / "qc", release_directory=release)
    with pytest.raises(QcPackError):
        qc_pack.write_qc_pack(_pack(), release / "qc", release_directory=release)
    assert not (root / "qc").exists() and not any(release.iterdir())


def test_qc_material_is_recognised_wherever_it_is(places):
    root, release, _ = places
    written = qc_pack.write_qc_pack(
        _pack(), root / "store" / "qc", release_directory=release
    )
    assert qc_pack.is_qc_material(written.parent)
    assert qc_pack.is_qc_material(written)
    assert qc_pack.is_qc_material(written.parent / "later" / "file.png")
    assert qc_pack.is_qc_material(root / "store")
    assert qc_pack.is_qc_material(root)
    assert not qc_pack.is_qc_material(release)
    assert not qc_pack.is_qc_material(root / "missing")


def test_a_release_that_gained_qc_material_is_recognised(places):
    _, release, _ = places
    (release / "ZQ0001").mkdir()
    assert not qc_pack.is_qc_material(release)
    (release / "ZQ0001" / qc_pack.MARKER_FILE).write_text(qc_pack.FORMAT)
    assert qc_pack.is_qc_material(release)


def test_nothing_is_logged(places, caplog):
    root, release, _ = places
    with caplog.at_level(logging.DEBUG):
        qc_pack.write_qc_pack(_full_pack(), root / "qc", release_directory=release)
    assert not caplog.records


def test_the_destination_may_be_given_as_text(places):
    root, release, _ = places
    written = qc_pack.write_qc_pack(
        _pack(), str(root / "qc"), release_directory=str(release)
    )
    assert isinstance(written, Path) and written.is_file()
