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

"""The pinned archives of the text detector's evaluation, read from
invented archives on disk. No file of Zenodo or of the Sydney store is
read."""

import hashlib
import json
import zipfile

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import text_evaluation_cases as cases_module
from pymedphys._dicom.deidentify import text_evaluation_idc as idc
from pymedphys._dicom.deidentify import text_evaluation_archives as archives
from pymedphys._dicom.deidentify.text_evaluation_frames import EvaluationRefused

from . import _synthetic_references as synthetic
from ._text_evaluation_stand_ins import SHAPE, _ct_dataset

from .test_deidentify_text_evaluation_idc import _evaluated

SECRET = "INVENTED-PATIENT-NAME"
BRAVEHEART = "sydney_braveheart_rt_image"
SYDNEY_PATH = "32833_Byrne_2/P01-P05 (Anonymised).zip"


def _dicom(series, instance, patient="INVENTED-1", **attributes):
    dataset = _ct_dataset(
        np.full((1, *SHAPE), 1024),
        SeriesInstanceUID=series,
        SOPInstanceUID=f"{series}.{instance}",
        InstanceNumber=instance,
        PixelSpacing=[1.0, 1.0],
        PatientID=patient,
        **attributes,
    )
    return synthetic.written(dataset)


def _rt_image(series, instance):
    return _dicom(series, instance, SOPClassUID=archives.RT_IMAGE, Modality="RTIMAGE")


def _archive(path, members, record=15697196):
    """An invented archive of ``members``, a mapping of name to bytes,
    pinned as the module pins Zenodo's."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    data = path.read_bytes()
    with zipfile.ZipFile(path) as archive:
        start = archive.start_dir
    return archives.ZenodoArchive(
        record,
        len(data),
        hashlib.md5(data, usedforsecurity=False).hexdigest(),
        hashlib.sha256(data[start:]).hexdigest(),
    )


def _members(folders=2, per_folder=2):
    found = {}
    for folder in range(1, folders + 1):
        for instance in range(1, per_folder + 1):
            name = f"{SECRET}/scan{folder}/{instance}.dcm"
            found[name] = _dicom(f"2.25.{folder}", instance, f"INVENTED-{folder}")
        found[f"{SECRET}/scan{folder}/model.stl"] = b"solid"
    found["labels.csv"] = b"name\n"
    return found


def _hosted(path, members, folders=frozenset()):
    """An invented archive of ``members``, pinned as the module pins the
    Sydney store's."""
    pinned = _archive(path, members)
    return archives.HostedArchive(
        BRAVEHEART,
        SYDNEY_PATH,
        pinned.size,
        pinned.central_directory_sha256,
        frozenset(folders),
    )


def _opener(path):
    return lambda archive: open(path, "rb")


def test_an_archive_is_read_only_as_pinned(tmp_path):
    path = tmp_path / "a.zip"
    archive = _archive(path, _members())
    with open(path, "rb") as opened:
        folders = archives.archive_index(archive, opened)
    assert len(folders) == 2
    assert {len(each.members) for each in folders} == {2}
    # Another central directory, size, or file is refused.
    for changed in (
        {"central_directory_sha256": "0" * 64},
        {"size": archive.size + 1},
    ):
        wrong = archives.ZenodoArchive(**{**archive.__dict__, **changed})
        with open(path, "rb") as opened, pytest.raises(EvaluationRefused):
            archives.archive_index(wrong, opened)
    other = tmp_path / "b.zip"
    other.write_bytes(b"x" * archive.size)
    with open(other, "rb") as opened, pytest.raises(EvaluationRefused):
        archives.archive_index(archive, opened)


def test_an_archive_must_be_of_a_vetted_record():
    pins = (15697196, 10, "0" * 32, "0" * 64)
    archives.ZenodoArchive(*pins)
    for changed in (
        (1,) + pins[1:],
        pins[:1] + (0,) + pins[2:],
        pins[:2] + ("md5",) + pins[3:],
        pins[:3] + ("sha",),
    ):
        with pytest.raises(EvaluationRefused):
            archives.ZenodoArchive(*changed)


def test_an_archive_is_found_in_its_record_by_its_digest():
    archive = archives.ZenodoArchive(15697196, 10, "a" * 32, "0" * 64)
    files = {"a" * 32: ("Data set.zip", 10), "b" * 32: ("other.zip", 10)}
    assert archives.archive_url(archive, files) == (
        "https://zenodo.org/records/15697196/files/Data%20set.zip?download=1"
    )
    for wrong in (
        {"b" * 32: ("other.zip", 10)},
        {"a" * 32: ("Data set.zip", 11)},
        {"a" * 32: ("Data set.tar", 10)},
    ):
        with pytest.raises(EvaluationRefused):
            archives.archive_url(archive, wrong)


def test_a_hosted_archive_is_pinned_by_its_path():
    pins = (BRAVEHEART, SYDNEY_PATH, 10, "0" * 64, frozenset({"1" * 64}))
    archive = archives.HostedArchive(*pins)
    assert archive.url() == (
        "https://ses-data.library.sydney.edu.au/public/"
        "32833_Byrne_2/P01-P05%20%28Anonymised%29.zip"
    )
    assert archive.collection.host == "University of Sydney"
    for changed in (
        ("zenodo_head_cta",) + pins[1:],
        ("sydney_other",) + pins[1:],
        pins[:1] + ("P01.zip",) + pins[2:],
        pins[:1] + ("32833_Byrne_2/../x.zip",) + pins[2:],
        pins[:1] + ("32833_Byrne_2/x.tar",) + pins[2:],
        pins[:2] + (0,) + pins[3:],
        pins[:3] + ("sha",) + pins[4:],
        pins[:4] + (frozenset({"folder"}),),
    ):
        with pytest.raises(EvaluationRefused):
            archives.HostedArchive(*changed)


def test_a_collection_is_named_for_its_host_and_limited_sensibly():
    fields = dict(
        licence="CC BY 4.0",
        doi="10.25910/7by0-vf89",
        title="A title",
        known_text="unknown",
        subjects="patients",
        classic=False,
    )
    archives.ArchiveCollection("sydney_x", host="University of Sydney", **fields)
    archives.ArchiveCollection("zenodo_x", **fields)
    for refused in (
        {"name": "zenodo_x", "host": "University of Sydney"},
        {"name": "sydney_x"},
        {"name": "x_y", "host": "Elsewhere"},
        {"name": "zenodo_x", "per_collection": 0},
        {"name": "zenodo_x", "licence": "CC BY-ND 4.0"},
    ):
        with pytest.raises(EvaluationRefused):
            archives.ArchiveCollection(**{**fields, **refused})


def test_the_pinned_archives_cover_each_vetted_record():
    archives.check_pins()
    assert {each.collection.name for each in archives.ARCHIVES} == set(
        archives.COLLECTIONS
    )
    for collection in archives.COLLECTIONS.values():
        assert collection.licence in idc.OPEN_LICENCES
    braveheart = archives.COLLECTIONS[BRAVEHEART]
    assert braveheart.sop_classes == {archives.RT_IMAGE}
    assert (braveheart.known_text, braveheart.classic) == ("unknown", False)
    hosted = [
        each for each in archives.ARCHIVES if isinstance(each, archives.HostedArchive)
    ]
    assert hosted and all(each.folders for each in hosted)
    head = archives.COLLECTIONS["zenodo_head_cta"]
    assert (head.known_text, head.subjects, head.classic) == ("none", "patients", True)
    assert archives.COLLECTIONS["zenodo_dental_cbct"].known_text == "unknown"
    assert archives.COLLECTIONS["zenodo_knee_mr_0p55t"].subjects == "volunteers"
    head_archives = [
        each
        for each in archives.ARCHIVES
        if isinstance(each, archives.ZenodoArchive) and each.record == 15697196
    ]
    assert len(head_archives) == 1


def _folders(path, collections=("zenodo_head_cta",), folders=2):
    records = {"zenodo_head_cta": 15697196, "zenodo_cardiac_mr_0p55t": 23089164}
    found = []
    for name in collections:
        archive_path = path / f"{name}.zip"
        archive = _archive(archive_path, _members(folders), records[name])
        with open(archive_path, "rb") as opened:
            found += archives.archive_index(archive, opened)
    return found


def test_a_selection_is_fixed_limited_and_shared(tmp_path):
    folders = _folders(
        tmp_path, ("zenodo_head_cta", "zenodo_cardiac_mr_0p55t"), folders=3
    )
    first = archives.select_folders(folders, per_collection=2)
    again = archives.select_folders(list(reversed(folders)), per_collection=2)
    assert first == again
    assert [each.collection for each in first.folders] == [
        "zenodo_cardiac_mr_0p55t",
        "zenodo_head_cta",
    ] * 2
    assert dict(first.refused) == {"over-collection-limit": 2}
    size = folders[0].size_mb
    limited = archives.select_folders(folders, max_mb=size * 1.5)
    assert len(limited.folders) == 1
    assert dict(limited.refused) == {
        "over-size-limit": 3,
        "over-collection-limit": 2,
    }
    small = archives.select_folders(folders, max_folder_mb=size / 2)
    assert not small.folders
    assert dict(small.refused) == {
        "over-folder-size-limit": 4,
        "over-collection-limit": 2,
    }
    with pytest.raises(EvaluationRefused):
        archives.select_folders(folders, per_collection=0)


def test_a_selection_is_described_without_a_name(tmp_path):
    selection = archives.select_folders(_folders(tmp_path))
    described = json.dumps(selection.described())
    assert SECRET not in described and "scan" not in described
    collection = selection.described()["collections"]["zenodo_head_cta"]
    assert (collection["folders"], collection["files"]) == (2, 4)
    assert collection["doi"] == "10.5281/zenodo.15697196"
    assert collection["host"] == "Zenodo"


def test_fetched_members_are_named_by_digests_alone(tmp_path):
    path = tmp_path / "a.zip"
    archive = _archive(path, _members())
    with open(path, "rb") as opened:
        selection = archives.select_folders(archives.archive_index(archive, opened))
    out = tmp_path / "out"
    written = archives.fetch(selection, out, _opener(path))
    assert written == {"zenodo_head_cta": 4}
    files = sorted(each for each in out.rglob("*") if each.is_file())
    assert len(files) == 4
    for each in files:
        relative = each.relative_to(out).as_posix()
        assert SECRET not in relative and "scan" not in relative
        assert each.suffix == ".dcm"


def test_a_member_changed_after_pinning_is_refused(tmp_path):
    path = tmp_path / "a.zip"
    archive = _archive(path, _members(folders=1))
    with open(path, "rb") as opened:
        selection = archives.select_folders(archives.archive_index(archive, opened))
    # A byte of a member's data changes; the central directory, and so its
    # digest, does not, but the member's CRC-32 no longer holds.
    data = bytearray(path.read_bytes())
    member = selection.folders[0].members[0]
    offset = member.header_offset + 30 + len(member.filename.encode()) + 200
    data[offset] ^= 0xFF
    path.write_bytes(bytes(data))
    with pytest.raises(EvaluationRefused):
        archives.fetch(selection, tmp_path / "out", _opener(path))


def test_fetched_folders_are_read_as_counted_t3_cases(tmp_path):
    path = tmp_path / "a.zip"
    archive = _archive(path, _members())
    with open(path, "rb") as opened:
        selection = archives.select_folders(archives.archive_index(archive, opened))
    out = tmp_path / "out"
    archives.fetch(selection, out, _opener(path))
    cases = archives.archive_cases(out)
    assert len(cases) == 2
    assert {each.collection for each in cases} == {"zenodo_head_cta"}
    assert len({each.subject for each in cases}) == 2
    frames = [frame for case in cases for frame in case.read()]
    assert {frame.tier for frame in frames} == {"T3"}
    assert {frame.known_text for frame in frames} == {"none"}
    run = _evaluated(cases)
    report = cases_module.cases_report(run)
    assert report["withheld"] == 2 and not report["cases"]
    assert SECRET not in json.dumps(report)
    converted = archives.archive_cases(out, converted=True)
    assert len(converted) == 2
    assert all(isinstance(each, archives.ConvertedCase) for each in converted)


def test_collections_without_classic_images_are_not_converted(tmp_path):
    (tmp_path / "zenodo_knee_mr_0p55t" / "x").mkdir(parents=True)
    (tmp_path / "zenodo_knee_mr_0p55t" / "x" / "a.dcm").write_bytes(_dicom("2.25.9", 1))
    assert len(archives.archive_cases(tmp_path)) == 1
    assert not archives.archive_cases(tmp_path, converted=True)


def _mixed_members():
    """Two folders: one of an RT Image and a CT, one of a CT alone."""
    return {
        f"{SECRET}/kv/1.dcm": _rt_image("2.25.1", 1),
        f"{SECRET}/kv/2.dcm": _dicom("2.25.1", 2),
        f"{SECRET}/kv/notes.txt": b"x",
        f"{SECRET}/ct/1.dcm": _dicom("2.25.2", 1),
    }


def test_only_the_pinned_folders_of_a_hosted_archive_are_taken(tmp_path):
    path = tmp_path / "a.zip"
    every = _hosted(path, _mixed_members())
    with open(path, "rb") as opened:
        indexed = archives.archive_index(every, opened)
    assert len(indexed) == 2
    kv = next(each for each in indexed if len(each.members) == 2)
    pinned = _hosted(path, _mixed_members(), {kv.digest})
    with open(path, "rb") as opened:
        (taken,) = archives.archive_index(pinned, opened)
    assert (taken.archive, taken.digest) == (pinned, kv.digest)
    assert [each.filename for each in taken.members] == [
        each.filename for each in kv.members
    ]
    missing = _hosted(path, _mixed_members(), {kv.digest, "f" * 64})
    with open(path, "rb") as opened, pytest.raises(EvaluationRefused):
        archives.archive_index(missing, opened)


def test_a_limited_collection_writes_its_classes_alone(tmp_path):
    path = tmp_path / "a.zip"
    archive = _hosted(path, _mixed_members())
    with open(path, "rb") as opened:
        selection = archives.select_folders(archives.archive_index(archive, opened))
    assert len(selection.folders) == 2
    out = tmp_path / "out"
    assert archives.fetch(selection, out, _opener(path)) == {BRAVEHEART: 1}
    (written,) = [each for each in out.rglob("*") if each.is_file()]
    assert archives.sop_class(written.read_bytes()) == archives.RT_IMAGE
    assert archives.sop_class(b"not DICOM") is None
    cases = archives.archive_cases(out)
    assert len(cases) == 1
    assert {frame.known_text for frame in cases[0].read()} == {"unknown"}


def test_a_collection_may_take_more_folders_than_the_selection(tmp_path):
    members = {
        f"{SECRET}/drr{each}/1.dcm": _rt_image(f"2.25.{each}", 1)
        for each in range(1, 13)
    }
    path = tmp_path / "a.zip"
    archive = _hosted(path, members)
    with open(path, "rb") as opened:
        folders = archives.archive_index(archive, opened)
    selection = archives.select_folders(folders, per_collection=1)
    limit = archives.COLLECTIONS[BRAVEHEART].per_collection
    assert limit and len(selection.folders) == min(limit, 12) > 1


class _Served:
    """An HTTP response of a range of ``data``, as urllib gives one."""

    def __init__(self, data, status=206):
        self.data, self.status = data, status

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_a_range_reader_reads_by_cached_blocks(monkeypatch, tmp_path):
    path = tmp_path / "a.zip"
    archive = _archive(path, _members())
    data = path.read_bytes()
    asked = []

    def served(request, **_):
        start, end = map(int, request.get_header("Range")[6:].split("-"))
        asked.append(start)
        return _Served(data[start : end + 1])

    monkeypatch.setattr(archives.urllib.request, "urlopen", served)
    reader = archives.RangeReader(
        "https://zenodo.org/x", len(data), block=256, blocks=4
    )
    folders = archives.archive_index(archive, reader)
    assert len(folders) == 2
    # A read spanning blocks is read whole, and a block is asked for once
    # however many reads fall in it while it is kept.
    reader.seek(100)
    assert reader.read(1000) == data[100:1100]
    count = len(asked)
    reader.seek(1050)
    assert reader.read(10) == data[1050:1060]
    assert len(asked) == count
    reader.seek(0)
    assert reader.read() == data
    monkeypatch.setattr(
        archives.urllib.request, "urlopen", lambda request, **_: _Served(b"", 200)
    )
    with pytest.raises(EvaluationRefused):
        archives.RangeReader("https://zenodo.org/x", 10).read(4)
