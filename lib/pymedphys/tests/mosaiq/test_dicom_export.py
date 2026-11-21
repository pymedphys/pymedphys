# Copyright (C) 2026 Derek Lane

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from pymedphys._imports import pytest

from pymedphys._mosaiq import dicom_export

STUDY = "1.2.3"
SERIES = "1.2.3.4"


def instance(instance_id, sop="1.2.3.4.5", scheme=0, n_bytes=3, series=SERIES):
    return (instance_id, STUDY, series, sop, scheme, n_bytes)


@pytest.fixture(name="mosaiq")
def fixture_mosaiq(monkeypatch):
    """Answer the two queries in dicom_export.py from in-memory rows"""

    def install(instances, blobs):
        def execute(_connection, query, parameters=None):
            if "FROM DCMInstance" in query:
                assert parameters
                return instances
            if "FROM vw_LegacyDCMInstance" in query:
                return [(blobs.get(parameters["instance_id"]),)]
            raise AssertionError(f"unexpected query: {query}")

        monkeypatch.setattr(dicom_export.api, "execute", execute)

    return install


def test_writes_each_instance_under_its_uids(mosaiq, tmp_path):
    mosaiq([instance(1), instance(2, sop="1.2.3.4.6")], {1: b"abc", 2: b"def"})

    exported = dicom_export.export_instances(None, tmp_path, patient_ids=["P1"])

    assert (tmp_path / STUDY / SERIES / "1.2.3.4.5.dcm").read_bytes() == b"abc"
    assert (tmp_path / STUDY / SERIES / "1.2.3.4.6.dcm").read_bytes() == b"def"
    assert len(exported.written) == 2
    assert not exported.missing


def test_reports_an_instance_whose_bytes_are_not_in_the_store(mosaiq, tmp_path):
    mosaiq([instance(1), instance(2, sop="1.2.3.4.6")], {1: b"abc"})

    exported = dicom_export.export_instances(None, tmp_path, patient_ids=["P1"])

    assert [i.instance_id for i in exported.missing] == [2]
    assert len(exported.written) == 1


def test_refuses_a_compressed_instance_before_writing_anything(mosaiq, tmp_path):
    mosaiq([instance(1), instance(2, sop="1.2.3.4.6", scheme=1)], {1: b"abc"})

    with pytest.raises(dicom_export.ExportError, match="compression"):
        dicom_export.export_instances(None, tmp_path, patient_ids=["P1"])

    assert not list(tmp_path.iterdir())


def test_refuses_bytes_of_a_different_size(mosaiq, tmp_path):
    mosaiq([instance(1, n_bytes=4)], {1: b"abc"})

    with pytest.raises(dicom_export.ExportError, match="recorded"):
        dicom_export.export_instances(None, tmp_path, patient_ids=["P1"])


def test_refuses_to_overwrite(mosaiq, tmp_path):
    mosaiq([instance(1)], {1: b"abc"})
    dicom_export.export_instances(None, tmp_path, patient_ids=["P1"])

    with pytest.raises(dicom_export.ExportError, match="already exists"):
        dicom_export.export_instances(None, tmp_path, patient_ids=["P1"])


def test_refuses_a_uid_that_could_escape_the_directory(mosaiq, tmp_path):
    mosaiq([instance(1, sop="../../evil")], {1: b"abc"})

    with pytest.raises(dicom_export.ExportError, match="not a DICOM UID"):
        dicom_export.export_instances(None, tmp_path, patient_ids=["P1"])


def test_requires_a_selector():
    with pytest.raises(ValueError, match="Select by"):
        dicom_export.find_instances(None)


@pytest.fixture(name="deidentify")
def fixture_deidentify(monkeypatch):
    """Replace the de-identification with a recorder of what it was given"""
    calls = []

    def fake(source, release, **kwargs):
        calls.append(
            {
                "source": source,
                "files": sorted(p.name for p in source.rglob("*.dcm")),
                "release": release,
                "kwargs": kwargs,
            }
        )
        if kwargs.get("fail"):
            raise RuntimeError("stopped")
        return "deidentified"

    monkeypatch.setattr(dicom_export, "deidentify", fake)
    return calls


def test_deidentifies_the_export_then_deletes_the_staging_directory(
    mosaiq, deidentify, tmp_path
):
    mosaiq([instance(1)], {1: b"abc"})

    exported, deidentified = dicom_export.export_deidentified(
        None,
        tmp_path / "release",
        qc_pack=tmp_path / "qc",
        patient_ids=["P1"],
        preset="basic",
    )

    (call,) = deidentify
    assert call["files"] == ["1.2.3.4.5.dcm"]
    assert call["release"] == tmp_path / "release"
    assert call["kwargs"] == {"qc_pack": tmp_path / "qc", "preset": "basic"}
    assert not call["source"].exists()
    assert len(exported.written) == 1
    assert deidentified == "deidentified"


def test_deletes_the_staging_directory_when_deidentification_fails(
    mosaiq, deidentify, tmp_path
):
    mosaiq([instance(1)], {1: b"abc"})

    with pytest.raises(RuntimeError):
        dicom_export.export_deidentified(
            None, tmp_path / "release", qc_pack=tmp_path / "qc",
            patient_ids=["P1"], fail=True,
        )

    assert not deidentify[0]["source"].exists()


def test_refuses_missing_instances_unless_allowed(mosaiq, deidentify, tmp_path):
    mosaiq([instance(1), instance(2, sop="1.2.3.4.6")], {1: b"abc"})
    staging = tmp_path / "staging"

    with pytest.raises(dicom_export.ExportError, match="1 of the 2"):
        dicom_export.export_deidentified(
            None, tmp_path / "release", qc_pack=tmp_path / "qc",
            patient_ids=["P1"], staging=staging,
        )

    assert not deidentify
    assert not staging.exists()

    exported, _ = dicom_export.export_deidentified(
        None, tmp_path / "release", qc_pack=tmp_path / "qc",
        patient_ids=["P1"], staging=staging, allow_missing=True,
    )

    assert [i.instance_id for i in exported.missing] == [2]
    assert len(deidentify) == 1


def test_refuses_a_staging_directory_that_exists(mosaiq, deidentify, tmp_path):
    mosaiq([instance(1)], {1: b"abc"})

    with pytest.raises(dicom_export.ExportError, match="already exists"):
        dicom_export.export_deidentified(
            None, tmp_path / "release", qc_pack=tmp_path / "qc",
            patient_ids=["P1"], staging=tmp_path,
        )

    assert tmp_path.exists()
    assert not deidentify
