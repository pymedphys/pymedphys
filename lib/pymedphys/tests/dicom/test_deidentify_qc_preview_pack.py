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

"""Tests of how the QC pack, its store, its attestation, and a run carry previews.

Every image is synthetic.
"""

import datetime
import json
import os
from pathlib import Path, PurePosixPath

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    pixel_risk,
    qc_attestation,
    qc_pack,
    qc_previews,
    qc_store,
    residuals,
    run,
    run_qc,
)
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import ReleaseGate
from pymedphys._dicom.deidentify.qc_pack import (
    Disposition,
    InstanceEntry,
    NotPreviewedEntry,
    NotPreviewedReason,
    PixelRiskEntry,
    Preview,
    PreviewKind,
    QcPack,
    QcPackError,
)

from . import _synthetic_references as synthetic
from .test_deidentify_instance_transform import _source, _transform, _transformed
from .test_deidentify_qc_previews import SECONDARY_CAPTURE, _image, _slices


# The pack's entries.


def _png():
    return qc_previews.png(np.zeros((2, 2), np.uint8))


def _instances(*dispositions):
    entries = []
    labels = iter(f"S-{n:04d}" for n in range(1, 10))
    for position, disposition in enumerate(dispositions):
        if disposition is Disposition.RELEASED:
            entries.append(
                InstanceEntry(
                    position,
                    f"in/{position}.dcm",
                    disposition,
                    PurePosixPath(f"{position}.dcm"),
                )
            )
        elif disposition is Disposition.SEQUESTERED:
            entries.append(
                InstanceEntry(
                    position,
                    f"in/{position}.dcm",
                    disposition,
                    label=next(labels),
                    reasons=("r",),
                )
            )
        else:
            entries.append(
                InstanceEntry(
                    position, f"in/{position}.dcm", disposition, reasons=("r",)
                )
            )
    return tuple(entries)


def _finding():
    return pixel_risk.Finding(
        pixel_risk.Indicator.BURNED_IN_ANNOTATION, ElementPath((), "(0028,0301)")
    )


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "fields",
    [
        {"name": "preview.png"},
        {"name": "P-1.png"},
        {"kind": "series-cine"},
        {"frames": ()},
        {"frames": ((0, 0), (0, 0))},
        {"frames": ((-1, 0),)},
        {"frames": ((True, 0),)},
        {"total_frames": 0},
        {"png": b"GIF89a"},
    ],
)
def test_a_preview_is_checked(fields):
    preview = {
        "name": "P-0001.png",
        "kind": PreviewKind.SERIES_CINE,
        "frames": ((0, 0),),
        "total_frames": 1,
        "png": _png(),
        **fields,
    }

    with pytest.raises(QcPackError) as raised:
        Preview(**preview)

    assert "GIF" not in str(raised.value)


@pytest.mark.pydicom
def test_the_pack_lists_previews_and_high_risk_instances():
    preview = Preview("P-0001.png", PreviewKind.INSTANCE, ((1, 0),), 1, _png())
    pack = QcPack(
        qc_pack.new_reference(),
        _instances(Disposition.SEQUESTERED, Disposition.HELD_FOR_REVIEW),
        pixel_risks=(PixelRiskEntry(1, (_finding(),)),),
        previews=(preview,),
        not_previewed=(NotPreviewedEntry(0, NotPreviewedReason.COMPRESSED),),
    )

    document = qc_pack.pack_document(pack)

    assert document["previews"] == [
        {
            "file": "previews/P-0001.png",
            "kind": "instance",
            "frames": [{"position": 1, "frame": 0}],
            "total_frames": 1,
            "sha256": preview.sha256,
        }
    ]
    assert document["pixel_risks"] == [
        {
            "position": 1,
            "findings": [
                {
                    "indicator": "burned-in-annotation",
                    "risk": "burned-in-text",
                    "element": "(0028,0301)",
                }
            ],
        }
    ]
    assert document["not_previewed"] == [
        {"position": 0, "reason": "compressed-pixel-data"}
    ]
    assert "previews=1" in repr(pack) and "PNG" not in repr(pack.previews)


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "fields",
    [
        # A sequestered instance is not released, so is not reviewed here.
        {
            "previews": (
                Preview("P-0001.png", PreviewKind.INSTANCE, ((0, 0),), 1, _png()),
            )
        },
        {
            "previews": (
                Preview("P-0002.png", PreviewKind.INSTANCE, ((1, 0),), 1, _png()),
            )
        },
        {
            "previews": (
                Preview("P-0001.png", PreviewKind.INSTANCE, ((7, 0),), 1, _png()),
            )
        },
        {
            "pixel_risks": (
                PixelRiskEntry(1, (_finding(),)),
                PixelRiskEntry(1, (_finding(),)),
            )
        },
        {"pixel_risks": (PixelRiskEntry(7, (_finding(),)),)},
        {
            "not_previewed": (
                NotPreviewedEntry(1, NotPreviewedReason.COMPRESSED),
                NotPreviewedEntry(0, NotPreviewedReason.COMPRESSED),
            )
        },
        {
            "previews": [
                Preview("P-0001.png", PreviewKind.INSTANCE, ((1, 0),), 1, _png())
            ]
        },
    ],
)
def test_the_pack_checks_its_previews(fields):
    with pytest.raises(QcPackError):
        QcPack(
            qc_pack.new_reference(),
            _instances(Disposition.SEQUESTERED, Disposition.RELEASED),
            **fields,
        )


@pytest.mark.pydicom
def test_entries_need_their_types():
    with pytest.raises(QcPackError):
        PixelRiskEntry(0, ())
    with pytest.raises(QcPackError):
        PixelRiskEntry(0, ("burned-in-annotation",))
    with pytest.raises(QcPackError):
        NotPreviewedEntry(0, "compressed-pixel-data")
    with pytest.raises(QcPackError):
        NotPreviewedEntry(-1, NotPreviewedReason.COMPRESSED)


def _pack_with_previews():
    previews = tuple(
        Preview(
            f"P-000{n}.png",
            PreviewKind.SERIES_CINE,
            ((0, 0),),
            1,
            qc_previews.png(np.full((2, 2), n, np.uint8)),
        )
        for n in (1, 2)
    )
    return QcPack(
        qc_pack.new_reference(), _instances(Disposition.RELEASED), previews=previews
    )


def _write_pack(tmp_path, pack):
    return qc_store.write_qc_pack(
        pack, tmp_path / "qc", release_directory=tmp_path / "release"
    ).parent


@pytest.mark.pydicom
def test_previews_are_written_beside_the_pack_and_only_for_its_owner(tmp_path):
    pack = _pack_with_previews()

    directory = _write_pack(tmp_path, pack)

    previews = directory / qc_pack.PREVIEW_DIRECTORY
    assert sorted(path.name for path in previews.iterdir()) == [
        qc_store.MARKER_FILE,
        "P-0001.png",
        "P-0002.png",
    ]
    # Copied away on its own, the directory is still recognised.
    copy = tmp_path / "copied"
    copy.mkdir()
    for path in previews.iterdir():
        (copy / path.name).write_bytes(path.read_bytes())
    assert qc_store.is_qc_material(copy)
    for preview in pack.previews:
        assert (previews / preview.name).read_bytes() == preview.png
    document = json.loads((directory / qc_store.PACK_FILE).read_text("ascii"))
    assert [entry["file"] for entry in document["previews"]] == [
        "previews/P-0001.png",
        "previews/P-0002.png",
    ]
    assert qc_store.is_qc_material(previews / "P-0001.png")
    if os.name == "posix":
        assert previews.stat().st_mode & 0o777 == 0o700
        assert (previews / "P-0001.png").stat().st_mode & 0o777 == 0o600


@pytest.mark.pydicom
def test_a_pack_without_previews_has_no_previews_directory(tmp_path):
    pack = QcPack(qc_pack.new_reference(), _instances(Disposition.RELEASED))

    directory = _write_pack(tmp_path, pack)

    assert not (directory / qc_pack.PREVIEW_DIRECTORY).exists()


@pytest.mark.pydicom
def test_withdrawing_a_pack_removes_its_previews(tmp_path):
    directory = _write_pack(tmp_path, _pack_with_previews())

    assert qc_store.withdraw_qc_pack(directory)

    assert not list(directory.iterdir())


@pytest.mark.pydicom
def test_previews_that_cannot_all_be_withdrawn_keep_both_markers(tmp_path, monkeypatch):
    directory = _write_pack(tmp_path, _pack_with_previews())
    unlink = Path.unlink

    def refusing(path, missing_ok=False):
        if path.name == "P-0002.png":
            raise PermissionError("refused")
        return unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", refusing)

    assert not qc_store.withdraw_qc_pack(directory)

    previews = directory / qc_pack.PREVIEW_DIRECTORY
    assert sorted(path.name for path in previews.iterdir()) == [
        qc_store.MARKER_FILE,
        "P-0002.png",
    ]
    assert (directory / qc_store.MARKER_FILE).exists()


_COMPLETE = qc_attestation.Coverage(True, True, True)
_WHEN = datetime.datetime(2026, 10, 6, tzinfo=datetime.timezone.utc)


def _attest(directory):
    return qc_attestation.attest(
        directory,
        reviewer="Reviewer",
        outcome=qc_attestation.Outcome.ATTESTED,
        coverage=_COMPLETE,
        attested_at=_WHEN,
    )


@pytest.mark.pydicom
@pytest.mark.parametrize("change", ["altered", "missing"])
def test_a_preview_changed_after_attestation_is_detected(tmp_path, change):
    directory = _write_pack(tmp_path, _pack_with_previews())
    _attest(directory)
    assert qc_attestation.attestation_record(directory).outcome is (
        qc_attestation.Outcome.ATTESTED
    )
    preview = directory / qc_pack.PREVIEW_DIRECTORY / "P-0002.png"
    os.chmod(preview, 0o600)
    if change == "altered":
        preview.write_bytes(_png())
    else:
        preview.unlink()

    with pytest.raises(QcPackError, match="changed after it was attested"):
        qc_attestation.attestation_record(directory)


@pytest.mark.pydicom
def test_a_pack_whose_preview_changed_cannot_be_attested(tmp_path):
    directory = _write_pack(tmp_path, _pack_with_previews())
    (directory / qc_pack.PREVIEW_DIRECTORY / "P-0001.png").write_bytes(_png())

    with pytest.raises(QcPackError, match="preview of the QC pack"):
        _attest(directory)

    assert not (directory / qc_attestation.ATTESTATION_FILE).exists()


@pytest.mark.pydicom
@pytest.mark.skipif(os.name != "posix", reason="needs a FIFO and symbolic links")
@pytest.mark.parametrize("kind", ["fifo", "link"])
def test_a_preview_that_is_not_a_regular_file_is_not_read(tmp_path, kind):
    directory = _write_pack(tmp_path, _pack_with_previews())
    preview = directory / qc_pack.PREVIEW_DIRECTORY / "P-0001.png"
    original = preview.read_bytes()
    preview.unlink()
    if kind == "fifo":
        os.mkfifo(preview)  # pylint: disable = no-member
    else:
        target = tmp_path / "elsewhere.png"
        target.write_bytes(original)
        preview.symlink_to(target)

    with pytest.raises(QcPackError, match="preview of the QC pack"):
        _attest(directory)


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "listed",
    [
        {"file": "../P-0001.png", "sha256": "0" * 64},
        {"file": "previews/P-0001.png"},
        "previews/P-0001.png",
    ],
)
def test_a_pack_listing_previews_out_of_format_cannot_be_attested(tmp_path, listed):
    directory = _write_pack(tmp_path, _pack_with_previews())
    pack_file = directory / qc_store.PACK_FILE
    document = json.loads(pack_file.read_text("ascii"))
    document["previews"] = [listed]
    os.chmod(pack_file, 0o600)
    pack_file.write_text(json.dumps(document), "ascii")

    with pytest.raises(QcPackError, match="preview of the QC pack"):
        _attest(directory)


# The run's pack.


def _outcome(position, status, output=None, label=None, reasons=()):
    return run.Outcome(position, status, reasons, output, None, label)


def _search(written):
    empty = residuals.ResidualSearch(findings=(), not_searched=(), readable=True)
    return run_qc.SearchMaterial(empty, written)


@pytest.mark.pydicom
def test_the_run_pack_previews_released_and_held_files_and_lists_high_risk():
    slices = _slices(3)
    capture = _image(
        np.ones((4, 4)), number=9, series="2.25.3", sop_class=SECONDARY_CAPTURE
    )
    outcomes = (
        _outcome(0, run.Status.RELEASED, PurePosixPath("a/0.dcm")),
        _outcome(1, run.Status.RELEASED, PurePosixPath("a/1.dcm")),
        _outcome(2, run.Status.HELD_FOR_REVIEW, reasons=(run.RunReason.DICOMDIR,)),
        _outcome(
            3, run.Status.SEQUESTERED, label="S-0001", reasons=(run.RunReason.DICOMDIR,)
        ),
        _outcome(4, run.Status.RELEASED, PurePosixPath("a/4.dcm")),
    )
    risky = run_qc.PixelRiskMaterial(
        pixel_risk.PixelRiskAssessment(True, (_finding(),))
    )
    calm = run_qc.PixelRiskMaterial(pixel_risk.PixelRiskAssessment(True, ()))
    material = {
        0: (calm, _search(slices[0])),
        1: (_search(slices[1]),),
        2: (_search(slices[2]),),
        # A sequestered file is not previewed, though high-risk.
        3: (risky, _search(capture)),
        4: (risky, _search(capture)),
    }
    sources = [Path(f"in/{n}.dcm") for n in range(5)]

    pack = run_qc.qc_pack_of(sources, outcomes, material)

    assert [(preview.kind, preview.frames) for preview in pack.previews] == [
        (PreviewKind.SERIES_CINE, ((0, 0), (1, 0), (2, 0))),
        (PreviewKind.SERIES_MIP, ((0, 0), (1, 0), (2, 0))),
        (PreviewKind.SERIES_CINE, ((4, 0),)),
        (PreviewKind.INSTANCE, ((4, 0),)),
    ]
    assert pack.pixel_risks == (
        PixelRiskEntry(3, (_finding(),)),
        PixelRiskEntry(4, (_finding(),)),
    )
    assert not pack.not_previewed


@pytest.mark.pydicom
def test_a_reviewed_file_that_no_gate_handed_over_is_listed():
    outcomes = (
        _outcome(0, run.Status.RELEASED, PurePosixPath("a/0.dcm")),
        _outcome(1, run.Status.HELD_FOR_REVIEW, reasons=(run.RunReason.DICOMDIR,)),
        _outcome(
            2, run.Status.SEQUESTERED, label="S-0001", reasons=(run.RunReason.DICOMDIR,)
        ),
    )
    sources = [Path(f"in/{n}.dcm") for n in range(3)]

    pack = run_qc.qc_pack_of(sources, outcomes, {})

    assert pack.not_previewed == (
        NotPreviewedEntry(0, NotPreviewedReason.NOT_AVAILABLE),
        NotPreviewedEntry(1, NotPreviewedReason.NOT_AVAILABLE),
    )


# The transform's material, and a run with the real transform and gate.


def test_the_transform_gives_the_sources_pixel_risk_as_qc_material():
    dose = synthetic.rt_dose()
    dose.BurnedInAnnotation = "YES"

    with_risk = _transformed(dose)
    without = _transformed(synthetic.rt_plan())

    (material,) = [
        item for item in with_risk.qc if isinstance(item, run_qc.PixelRiskMaterial)
    ]
    assert [finding.indicator.value for finding in material.assessment.findings] == [
        "burned-in-annotation"
    ]
    assert not [
        item for item in without.qc if isinstance(item, run_qc.PixelRiskMaterial)
    ]


def test_a_run_previews_its_images_in_the_qc_pack(tmp_path):
    plan = synthetic.rt_plan()
    dose = synthetic.rt_dose()
    dose.BurnedInAnnotation = "YES"
    dose.SamplesPerPixel = 1
    dose.PhotometricInterpretation = "MONOCHROME2"
    dose.Rows = dose.Columns = 4
    dose.BitsAllocated = dose.BitsStored = 16
    dose.HighBit = 15
    dose.PixelRepresentation = 0
    dose.PixelData = bytes(range(32))

    result = run.run(
        _source(tmp_path, [plan, dose]),
        tmp_path / "release",
        _transform(),
        ReleaseGate(),
        qc_destination=tmp_path / "qc",
    )

    pack = json.loads(result.qc_pack.read_text(encoding="utf-8"))
    dose_position = next(
        entry["position"]
        for entry in pack["instances"]
        if entry["source"].endswith("1.dcm")
    )
    assert [entry["position"] for entry in pack["pixel_risks"]] == [dose_position]
    kinds = [preview["kind"] for preview in pack["previews"]]
    assert kinds == ["series-cine", "instance"]
    for preview in pack["previews"]:
        assert (result.qc_pack.parent / preview["file"]).is_file()
    assert not pack["not_previewed"]
