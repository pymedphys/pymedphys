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

"""The redaction review app's verdicts file (D-059)."""

import json
import os
import stat
from pathlib import PurePosixPath

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import qc_attestation, qc_store, redaction_verdicts
from pymedphys._dicom.deidentify.qc_attestation import Redaction, RedactionVerdict
from pymedphys._dicom.deidentify.qc_pack import (
    Disposition,
    InstanceEntry,
    QcPack,
    QcPackError,
)
from pymedphys._dicom.deidentify.redaction_verdicts import Draft, Verdicts
from pymedphys._dicom.deidentify.text_detection import TextBox

REFERENCE = "A-" + "0123456789abcdef" * 2
DIGEST = "ab" * 32
BOX = TextBox(1, 2, 3, 5)
DRAWN = TextBox(0, 0, 2, 2)


@pytest.fixture(name="pack")
def fixture_pack(tmp_path):
    release = tmp_path / "release"
    release.mkdir()
    pack = QcPack(
        REFERENCE,
        (
            InstanceEntry(
                0,
                "/imports/a.dcm",
                Disposition.RELEASED,
                output=PurePosixPath("ZQ0001/2.25.1/2.25.2/2.25.3.dcm"),
            ),
        ),
    )
    return qc_store.write_qc_pack(
        pack, tmp_path / "qc", release_directory=release
    ).parent


def _verdicts():
    return Verdicts(
        REFERENCE,
        DIGEST,
        (
            Draft(0, Redaction.ACCEPTED, seen=(0, 1)),
            Draft(1, Redaction.REVISED, ((0, (DRAWN,)),), ((1, (BOX,)),), (0, 1)),
            Draft(2, Redaction.REJECTED),
            # Work in progress, which keeps what was drawn.
            Draft(3, None, ((0, (DRAWN,)),), seen=(0,)),
            # Accepted after drawing: the drawn region is kept but not given.
            Draft(4, Redaction.ACCEPTED, ((0, (DRAWN,)),), seen=(0,)),
        ),
    )


def test_drafts_give_only_their_verdicts():
    assert _verdicts().verdicts() == (
        RedactionVerdict(0, Redaction.ACCEPTED, seen=(0, 1)),
        RedactionVerdict(
            1, Redaction.REVISED, ((0, (DRAWN,)),), ((1, (BOX,)),), (0, 1)
        ),
        RedactionVerdict(2, Redaction.REJECTED),
        RedactionVerdict(4, Redaction.ACCEPTED, seen=(0,)),
    )


def test_drafts_are_read_back_as_written():
    document = redaction_verdicts.verdicts_document(_verdicts())

    assert document["format"] == "pymedphys-deid-redaction-verdicts/1"
    assert (
        redaction_verdicts.verdicts_from(json.loads(json.dumps(document)))
        == _verdicts()
    )


def test_a_revised_draft_that_neither_draws_nor_drops_gives_no_verdict():
    with pytest.raises(QcPackError, match="exactly where it revises"):
        Draft(0, Redaction.REVISED, seen=(0,)).verdict()


@pytest.mark.parametrize(
    "fields",
    [
        {"position": -1},
        {"position": 0, "redaction": "accepted"},
        {"position": 0, "seen": (1, 0)},
        {"position": 0, "drawn": ((0, (BOX,)),), "dropped": ((0, (BOX,)),)},
        {"position": 0, "drawn": ((0, ()),)},
    ],
)
def test_a_draft_is_checked(fields):
    with pytest.raises(QcPackError):
        Draft(**fields)


@pytest.mark.parametrize(
    "fields",
    [
        {"reference": "A-1", "pack_digest": DIGEST},
        {"reference": REFERENCE, "pack_digest": "AB" * 32},
        {"reference": REFERENCE, "pack_digest": DIGEST, "drafts": [Draft(0)]},
        {"reference": REFERENCE, "pack_digest": DIGEST, "drafts": (Draft(1), Draft(0))},
        {"reference": REFERENCE, "pack_digest": DIGEST, "drafts": (Draft(0), Draft(0))},
    ],
)
def test_verdicts_are_checked(fields):
    with pytest.raises(QcPackError):
        Verdicts(**fields)


def _document():
    return redaction_verdicts.verdicts_document(_verdicts())


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(format="pymedphys-deid-redaction-verdicts/0"),
        lambda d: d.update(extra=1),
        lambda d: d.pop("drafts"),
        lambda d: d.update(drafts={}),
        lambda d: d["drafts"][0].update(extra=1),
        lambda d: d["drafts"][0].update(seen="0"),
        lambda d: d["drafts"][0].update(redaction="kept"),
        lambda d: d["drafts"][1].update(drawn=[{"frame": 0, "boxes": [[0, 0, 2]]}]),
        lambda d: d["drafts"][1].update(drawn=[{"frame": 0}]),
        lambda d: d["drafts"][1].update(drawn={}),
    ],
)
def test_a_malformed_document_is_refused(change):
    document = _document()
    change(document)

    with pytest.raises(QcPackError, match="not of their format"):
        redaction_verdicts.verdicts_from(document)


@pytest.mark.parametrize("document", [None, [], "x", {"format": 1}])
def test_a_document_that_is_not_one_is_refused(document):
    with pytest.raises(QcPackError, match="not of their format"):
        redaction_verdicts.verdicts_from(document)


def test_drafts_are_saved_in_the_pack_and_read_back_bound_to_it(pack):
    reference, digest = qc_attestation.pack_reference(pack)
    verdicts = Verdicts(reference, digest, _verdicts().drafts)

    redaction_verdicts.save_redaction_verdicts(pack, verdicts)
    # Saved again, replacing the first copy.
    redaction_verdicts.save_redaction_verdicts(pack, verdicts)

    path = pack / redaction_verdicts.VERDICTS_FILE
    assert (
        redaction_verdicts.read_redaction_verdicts(
            path, reference=reference, pack_digest=digest
        )
        == verdicts
    )
    # Inside the pack's directory, so a release refuses it with the pack.
    assert qc_store.is_qc_material(path)
    # No temporary file is left behind.
    assert not [entry for entry in pack.iterdir() if entry.suffix == ".tmp"]
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "binding",
    [
        {"reference": "A-" + "0" * 32},
        {"pack_digest": "0" * 64},
    ],
)
def test_drafts_for_another_pack_are_refused(pack, binding):
    reference, digest = qc_attestation.pack_reference(pack)
    redaction_verdicts.save_redaction_verdicts(
        pack, Verdicts(reference, digest, (Draft(0),))
    )
    expected = {"reference": reference, "pack_digest": digest, **binding}

    with pytest.raises(QcPackError, match="for another QC pack"):
        redaction_verdicts.read_redaction_verdicts(
            pack / redaction_verdicts.VERDICTS_FILE, **expected
        )


def test_a_file_that_cannot_be_read_names_no_path(tmp_path):
    missing = tmp_path / "secret-name" / redaction_verdicts.VERDICTS_FILE

    with pytest.raises(QcPackError) as raised:
        redaction_verdicts.read_redaction_verdicts(
            missing, reference=REFERENCE, pack_digest=DIGEST
        )
    assert "secret-name" not in str(raised.value)


def test_a_file_that_is_not_json_is_refused(tmp_path):
    path = tmp_path / redaction_verdicts.VERDICTS_FILE
    path.write_bytes(b"\xff not json")

    with pytest.raises(QcPackError, match="not of their format"):
        redaction_verdicts.read_redaction_verdicts(
            path, reference=REFERENCE, pack_digest=DIGEST
        )


def test_a_file_that_cannot_be_written_names_no_path(tmp_path):
    missing = tmp_path / "secret-name"

    with pytest.raises(QcPackError) as raised:
        redaction_verdicts.save_redaction_verdicts(missing, _verdicts())
    assert "secret-name" not in str(raised.value)


def test_boxes_are_laid_out_by_frame():
    assert redaction_verdicts.regions_of(
        [(2, BOX), (0, BOX), (0, DRAWN), (0, BOX)]
    ) == ((0, (DRAWN, BOX)), (2, (BOX,)))
