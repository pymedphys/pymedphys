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

"""Tests of the QC pack that each run writes, from its outcomes and material.

Every input is synthetic.
"""

import dataclasses
import json
import os
from pathlib import PurePosixPath

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import qc_pack, qc_store, run, run_qc
from pymedphys._dicom.deidentify.file_layout import ElementPath

from . import _synthetic_references as synthetic
from .test_deidentify_run import (
    Finding,
    Gate,
    GateReason,
    Transform,
    _listing,
    _output,
    _run,
    _write,
)

# The run module's fixture, for a base directory short enough for Windows.
from .test_deidentify_run import (  # noqa: F401  # pylint: disable = unused-import
    _short_tmp_path,
)


def _pack(result):
    return json.loads(result.qc_pack.read_text(encoding="utf-8"))


@pytest.mark.pydicom
def test_the_qc_pack_lists_every_input_with_labels_for_the_sequestered(tmp_path):
    datasets = synthetic.collection()
    _write(tmp_path / "source", [*datasets, datasets[1]])
    sequestered = (datasets[0].SOPInstanceUID, datasets[2].SOPInstanceUID)
    held = _output(datasets[3].SOPInstanceUID)
    gate = Gate(
        {
            held: run.HoldForReview(
                (Finding("residual", ElementPath((), "(0010,0010)")),)
            )
        }
    )

    discovery, result = _run(tmp_path, Transform(sequester=sequestered), gate)

    assert result.qc_pack == tmp_path / "qc" / qc_store.PACK_FILE
    labels = [outcome.label for outcome in result.outcomes]
    # Drawn at random, so that a label says nothing of its input's place.
    assert sorted(labels[0:3:2]) == ["S-0001", "S-0002"]
    assert labels[1] is None and labels[3:] == [None] * 4
    instances = _pack(result)["instances"]
    assert [entry["label"] for entry in instances] == labels
    assert [entry["source"] for entry in instances] == [
        str(path) for path in discovery.paths
    ]
    assert [entry["disposition"] for entry in instances] == [
        "sequestered",
        "released",
        "sequestered",
        "held-for-review",
        "released",
        "released",
        "duplicate",
    ]
    assert instances[0]["reasons"] == ["GateReason.TEXT_FINDING"]
    assert instances[3]["reasons"] == ["Finding(code=residual, path=(0010,0010))"]
    assert instances[6]["output"] == instances[1]["output"]
    # The release itself holds none of it.
    assert not any(
        qc_store.is_qc_material(path) for path in (tmp_path / "release").rglob("*")
    )


@pytest.mark.pydicom
def test_the_qc_pack_holds_the_transforms_and_gates_material_by_position(tmp_path):
    datasets = synthetic.collection()[:2]
    _write(tmp_path / "source", datasets)
    place = ElementPath((), "(0008,0018)")

    def transform(data, record):
        written = Transform()(data, record)
        drop = run_qc.Dropped(place, qc_pack.DropReason.REGISTERED_UID)
        return dataclasses.replace(written, qc=(drop,))

    def gate(written, *_):
        if written == _output(datasets[1].SOPInstanceUID):
            return run.Release(
                (run_qc.Dropped(place, qc_pack.DropReason.WRITTEN_CONSTANT),)
            )
        return run.Release()

    _, result = _run(tmp_path, transform, gate)

    assert _pack(result)["drops"] == [
        {"position": 0, "source": "(0008,0018)", "reason": "registered-uid"},
        {"position": 1, "source": "(0008,0018)", "reason": "registered-uid"},
        {"position": 1, "source": "(0008,0018)", "reason": "written-constant"},
    ]


@pytest.mark.pydicom
def test_qc_material_is_kept_for_a_file_withheld_after_staging(tmp_path):
    datasets = synthetic.collection()[:1]
    _write(tmp_path / "source", datasets)
    place = ElementPath((), "(0010,0010)")

    def gate(*_):
        drop = run_qc.Dropped(place, qc_pack.DropReason.RETAINED)
        return run.Sequestered((GateReason.TEXT_FINDING,), qc=(drop,))

    _, result = _run(tmp_path, gate=gate)

    pack = _pack(result)
    assert pack["instances"][0]["label"] == "S-0001"
    assert pack["drops"] == [
        {"position": 0, "source": "(0010,0010)", "reason": "retained"}
    ]


@pytest.mark.pydicom
def test_material_that_is_not_a_tuple_publishes_nothing(tmp_path):
    _write(tmp_path / "source", synthetic.collection()[:1])

    def gate(*_):
        return run.Release(qc=[run_qc.Dropped(ElementPath((), "(0010,0010)"), None)])

    with pytest.raises(TypeError):
        _run(tmp_path, gate=gate)

    assert _listing(tmp_path) == ["source"]


@pytest.mark.pydicom
def test_material_of_an_unknown_type_publishes_nothing(tmp_path):
    _write(tmp_path / "source", synthetic.collection()[:1])

    def gate(*_):
        return run.Release(qc=(object(),))

    with pytest.raises(TypeError):
        _run(tmp_path, gate=gate)

    assert _listing(tmp_path) == ["source"]


@pytest.mark.pydicom
@pytest.mark.parametrize("destination", ["release/qc", ".release.staging/qc"])
def test_a_qc_destination_in_the_release_or_staging_is_refused_first(
    tmp_path, destination
):
    _write(tmp_path / "source", synthetic.collection()[:1])
    transform = Transform()

    with pytest.raises(qc_pack.QcPackError):
        run.run(
            run.discover(tmp_path / "source"),
            tmp_path / "release",
            transform,
            Gate(),
            qc_destination=tmp_path / destination,
        )

    assert not transform.calls
    assert _listing(tmp_path) == ["source"]


@pytest.mark.pydicom
def test_a_qc_destination_that_is_not_empty_is_refused(tmp_path):
    _write(tmp_path / "source", synthetic.collection()[:1])
    (tmp_path / "qc").mkdir()
    (tmp_path / "qc" / "earlier").write_text("not empty")

    with pytest.raises(qc_pack.QcPackError):
        _run(tmp_path)

    assert not os.path.lexists(tmp_path / "release")
    assert not os.path.lexists(tmp_path / ".release.staging")


@pytest.mark.pydicom
def test_a_pack_that_cannot_be_written_publishes_nothing(tmp_path, monkeypatch):
    _write(tmp_path / "source", synthetic.collection()[:1])
    written = []

    def write_qc_pack(*_args, **_kwargs):
        # Fails once the run has staged and gated its files.
        written.append(os.listdir(tmp_path / ".release.staging"))
        raise qc_pack.QcPackError("the QC pack could not be written")

    monkeypatch.setattr(qc_store, "write_qc_pack", write_qc_pack)

    with pytest.raises(qc_pack.QcPackError):
        _run(tmp_path)

    assert written and written[0]
    assert _listing(tmp_path) == ["source"]


@pytest.mark.pydicom
def test_a_release_that_appears_before_the_pack_is_written_gets_no_pack(
    tmp_path, monkeypatch
):
    _write(tmp_path / "source", synthetic.collection()[:1])
    prune = run._remove_empty_directories  # pylint: disable = protected-access

    def remove_empty_directories(root):
        prune(root)
        (tmp_path / "release").mkdir()

    monkeypatch.setattr(run, "_remove_empty_directories", remove_empty_directories)

    with pytest.raises(run.RunError, match="already exists"):
        _run(tmp_path)

    assert _listing(tmp_path) == ["release", "source"]
    assert not os.listdir(tmp_path / "release")


@pytest.mark.pydicom
def test_a_pack_is_withdrawn_when_its_release_is_not_published(tmp_path, monkeypatch):
    _write(tmp_path / "source", synthetic.collection()[:1])

    def rename(*_):
        raise PermissionError("synthetic refusal")

    monkeypatch.setattr(run.os, "rename", rename)

    with pytest.raises(PermissionError):
        _run(tmp_path)

    assert _listing(tmp_path) == ["qc", "source"]
    assert not os.listdir(tmp_path / "qc")


@pytest.mark.pydicom
def test_a_pack_that_cannot_be_withdrawn_is_named(tmp_path, monkeypatch):
    _write(tmp_path / "source", synthetic.collection()[:1])

    def rename(*_):
        raise PermissionError("synthetic refusal")

    def unlink(*_args, **_kwargs):
        raise PermissionError("synthetic refusal")

    monkeypatch.setattr(run.os, "rename", rename)
    with monkeypatch.context() as patched:
        with pytest.raises(run.RunError, match="could not be removed") as raised:
            patched.setattr(run.Path, "unlink", unlink)
            _run(tmp_path)

    assert str(tmp_path / "qc") in str(raised.value)
    assert (tmp_path / "qc" / qc_store.PACK_FILE).is_file()


def test_reasons_are_written_as_text_naming_no_value():
    assert run_qc.reason_text(GateReason.TEXT_FINDING) == "GateReason.TEXT_FINDING"
    assert (
        run_qc.reason_text(Finding("residual", ElementPath((), "(0010,0010)")))
        == "Finding(code=residual, path=(0010,0010))"
    )


def test_qc_material_is_left_out_of_reprs():
    material = (
        run_qc.Dropped(ElementPath((), "(0010,0010)"), qc_pack.DropReason.RETAINED),
    )

    for result in (
        run.Release(material),
        run.HoldForReview((), material),
        run.Sequestered((), qc=material),
        run.Transformed(PurePosixPath("a"), b"", qc=material),
    ):
        assert "Dropped" not in repr(result)


@dataclasses.dataclass(frozen=True)
class _PartlySet:
    code: GateReason
    later: str = dataclasses.field(init=False)


def test_a_reason_field_left_unset_is_left_out():
    assert run_qc.reason_text(_PartlySet(GateReason.TEXT_FINDING)) == (
        f"_PartlySet(code={GateReason.TEXT_FINDING.value})"
    )
