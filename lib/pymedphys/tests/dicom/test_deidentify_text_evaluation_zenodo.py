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

"""Zenodo archives of the text detector's evaluation, read from invented
archives on disk. No Zenodo file is read."""

import hashlib
import json
import zipfile

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import text_evaluation_cases as cases_module
from pymedphys._dicom.deidentify import text_evaluation_idc as idc
from pymedphys._dicom.deidentify import text_evaluation_zenodo as zenodo
from pymedphys._dicom.deidentify.text_evaluation_frames import EvaluationRefused

from . import _synthetic_references as synthetic
from ._text_evaluation_stand_ins import SHAPE, _ct_dataset

from .test_deidentify_text_evaluation_idc import _evaluated

SECRET = "INVENTED-PATIENT-NAME"


def _dicom(series, instance, patient="INVENTED-1"):
    dataset = _ct_dataset(
        np.full((1, *SHAPE), 1024),
        SeriesInstanceUID=series,
        SOPInstanceUID=f"{series}.{instance}",
        InstanceNumber=instance,
        PixelSpacing=[1.0, 1.0],
        PatientID=patient,
    )
    return synthetic.written(dataset)


def _archive(path, members, record=15697196):
    """An invented archive of ``members``, a mapping of name to bytes,
    pinned as the module pins Zenodo's."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    data = path.read_bytes()
    with zipfile.ZipFile(path) as archive:
        start = archive.start_dir
    return zenodo.ZenodoArchive(
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


def _opener(path):
    return lambda archive: open(path, "rb")


def test_an_archive_is_read_only_as_pinned(tmp_path):
    path = tmp_path / "a.zip"
    archive = _archive(path, _members())
    with open(path, "rb") as opened:
        folders = zenodo.archive_index(archive, opened)
    assert len(folders) == 2
    assert {len(each.members) for each in folders} == {2}
    # Another central directory, size, or file is refused.
    for changed in (
        {"central_directory_sha256": "0" * 64},
        {"size": archive.size + 1},
    ):
        wrong = zenodo.ZenodoArchive(**{**archive.__dict__, **changed})
        with open(path, "rb") as opened, pytest.raises(EvaluationRefused):
            zenodo.archive_index(wrong, opened)
    other = tmp_path / "b.zip"
    other.write_bytes(b"x" * archive.size)
    with open(other, "rb") as opened, pytest.raises(EvaluationRefused):
        zenodo.archive_index(archive, opened)


def test_an_archive_must_be_of_a_vetted_record():
    pins = (15697196, 10, "0" * 32, "0" * 64)
    zenodo.ZenodoArchive(*pins)
    for changed in (
        (1,) + pins[1:],
        pins[:1] + (0,) + pins[2:],
        pins[:2] + ("md5",) + pins[3:],
        pins[:3] + ("sha",),
    ):
        with pytest.raises(EvaluationRefused):
            zenodo.ZenodoArchive(*changed)


def test_an_archive_is_found_in_its_record_by_its_digest():
    archive = zenodo.ZenodoArchive(15697196, 10, "a" * 32, "0" * 64)
    files = {"a" * 32: ("Data set.zip", 10), "b" * 32: ("other.zip", 10)}
    assert zenodo.archive_url(archive, files) == (
        "https://zenodo.org/records/15697196/files/Data%20set.zip?download=1"
    )
    for wrong in (
        {"b" * 32: ("other.zip", 10)},
        {"a" * 32: ("Data set.zip", 11)},
        {"a" * 32: ("Data set.tar", 10)},
    ):
        with pytest.raises(EvaluationRefused):
            zenodo.archive_url(archive, wrong)


def test_the_pinned_archives_cover_each_vetted_record():
    zenodo.check_pins()
    assert {each.collection.name for each in zenodo.ARCHIVES} == set(zenodo.COLLECTIONS)
    for collection in zenodo.COLLECTIONS.values():
        assert collection.licence in idc.OPEN_LICENCES
    head = zenodo.COLLECTIONS["zenodo_head_cta"]
    assert (head.known_text, head.subjects, head.classic) == ("none", "patients", True)
    assert zenodo.COLLECTIONS["zenodo_dental_cbct"].known_text == "unknown"
    assert zenodo.COLLECTIONS["zenodo_knee_mr_0p55t"].subjects == "volunteers"
    assert len([each for each in zenodo.ARCHIVES if each.record == 15697196]) == 1


def _folders(path, collections=("zenodo_head_cta",), folders=2):
    records = {"zenodo_head_cta": 15697196, "zenodo_cardiac_mr_0p55t": 23089164}
    found = []
    for name in collections:
        archive_path = path / f"{name}.zip"
        archive = _archive(archive_path, _members(folders), records[name])
        with open(archive_path, "rb") as opened:
            found += zenodo.archive_index(archive, opened)
    return found


def test_a_selection_is_fixed_limited_and_shared(tmp_path):
    folders = _folders(
        tmp_path, ("zenodo_head_cta", "zenodo_cardiac_mr_0p55t"), folders=3
    )
    first = zenodo.select_folders(folders, per_collection=2)
    again = zenodo.select_folders(list(reversed(folders)), per_collection=2)
    assert first == again
    assert [each.collection for each in first.folders] == [
        "zenodo_cardiac_mr_0p55t",
        "zenodo_head_cta",
    ] * 2
    assert dict(first.refused) == {"over-collection-limit": 2}
    size = folders[0].size_mb
    limited = zenodo.select_folders(folders, max_mb=size * 1.5)
    assert len(limited.folders) == 1
    assert dict(limited.refused) == {
        "over-size-limit": 3,
        "over-collection-limit": 2,
    }
    small = zenodo.select_folders(folders, max_folder_mb=size / 2)
    assert not small.folders
    assert dict(small.refused) == {
        "over-folder-size-limit": 4,
        "over-collection-limit": 2,
    }
    with pytest.raises(EvaluationRefused):
        zenodo.select_folders(folders, per_collection=0)


def test_a_selection_is_described_without_a_name(tmp_path):
    selection = zenodo.select_folders(_folders(tmp_path))
    described = json.dumps(selection.described())
    assert SECRET not in described and "scan" not in described
    collection = selection.described()["collections"]["zenodo_head_cta"]
    assert (collection["folders"], collection["files"]) == (2, 4)
    assert collection["doi"] == "10.5281/zenodo.15697196"


def test_fetched_members_are_named_by_digests_alone(tmp_path):
    path = tmp_path / "a.zip"
    archive = _archive(path, _members())
    with open(path, "rb") as opened:
        selection = zenodo.select_folders(zenodo.archive_index(archive, opened))
    out = tmp_path / "out"
    written = zenodo.fetch(selection, out, _opener(path))
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
        selection = zenodo.select_folders(zenodo.archive_index(archive, opened))
    # A byte of a member's data changes; the central directory, and so its
    # digest, does not, but the member's CRC-32 no longer holds.
    data = bytearray(path.read_bytes())
    member = selection.folders[0].members[0]
    offset = member.header_offset + 30 + len(member.filename.encode()) + 200
    data[offset] ^= 0xFF
    path.write_bytes(bytes(data))
    with pytest.raises(EvaluationRefused):
        zenodo.fetch(selection, tmp_path / "out", _opener(path))


def test_fetched_folders_are_read_as_counted_t3_cases(tmp_path):
    path = tmp_path / "a.zip"
    archive = _archive(path, _members())
    with open(path, "rb") as opened:
        selection = zenodo.select_folders(zenodo.archive_index(archive, opened))
    out = tmp_path / "out"
    zenodo.fetch(selection, out, _opener(path))
    cases = zenodo.zenodo_cases(out)
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
    converted = zenodo.zenodo_cases(out, converted=True)
    assert len(converted) == 2
    assert all(isinstance(each, zenodo.ConvertedCase) for each in converted)


def test_collections_without_classic_images_are_not_converted(tmp_path):
    (tmp_path / "zenodo_knee_mr_0p55t" / "x").mkdir(parents=True)
    (tmp_path / "zenodo_knee_mr_0p55t" / "x" / "a.dcm").write_bytes(_dicom("2.25.9", 1))
    assert len(zenodo.zenodo_cases(tmp_path)) == 1
    assert not zenodo.zenodo_cases(tmp_path, converted=True)


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

    monkeypatch.setattr(zenodo.urllib.request, "urlopen", served)
    reader = zenodo.RangeReader("https://zenodo.org/x", len(data), block=256, blocks=4)
    folders = zenodo.archive_index(archive, reader)
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
        zenodo.urllib.request, "urlopen", lambda request, **_: _Served(b"", 200)
    )
    with pytest.raises(EvaluationRefused):
        zenodo.RangeReader("https://zenodo.org/x", 10).read(4)
