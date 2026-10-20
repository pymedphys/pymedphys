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

"""A reviewer's face verdict on each series of a QC pack, bound to its source files.

Every name, path, and data set here is invented or synthetic.
"""

import dataclasses
import datetime
import hashlib
import io
import json
import shutil
import tempfile
from pathlib import Path, PurePosixPath

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import attestation_command as command
from pymedphys._dicom.deidentify import qc_attestation, qc_store, run, run_qc
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.face_review import (
    contour_data_sha256,
    pixel_data_sha256,
)
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.qc_attestation import (
    Attestation,
    AttestationRecord,
    Coverage,
    Face,
    FaceVerdict,
    Outcome,
)
from pymedphys._dicom.deidentify.qc_pack import (
    Disposition,
    InstanceEntry,
    QcPack,
    QcPackError,
    SeriesEntry,
)

from .test_deidentify_pixel_risk import _slice
from .test_deidentify_qc_preview_pack import _outcome
from .test_deidentify_qc_series_risks import _evidence

REFERENCE = "A-" + "0123456789abcdef" * 2
REVIEWER = "Quokka Wombatson"
WHEN = datetime.datetime(2026, 10, 12, 20, 30, tzinfo=datetime.timezone.utc)
COMPLETE = Coverage(retained_strings=True, series=True, high_risk_instances=True)
EVERY_REVIEW = (
    "--reviewed-retained-strings",
    "--reviewed-series",
    "--reviewed-high-risk-instances",
)


def _digest(n):
    return hashlib.sha256(bytes([n])).hexdigest()


def _released(position, digest=True):
    return InstanceEntry(
        position,
        f"/imports/{position}.dcm",
        Disposition.RELEASED,
        output=PurePosixPath(f"ZQ0001/2.25.1/2.25.2/2.25.{position + 3}.dcm"),
        source_sha256=_digest(position) if digest else None,
    )


def _sequestered(position, label="S-0001"):
    return InstanceEntry(
        position,
        f"/imports/{position}.dcm",
        Disposition.SEQUESTERED,
        label=label,
        reasons=("conflicting instance",),
        source_sha256=_digest(position),
    )


# Five released instances in two series, (0, 2, 3) and (1, 4).
SERIES = (SeriesEntry((0, 2, 3)), SeriesEntry((1, 4)))


@pytest.fixture(name="pack")
def fixture_pack(tmp_path):
    release = tmp_path / "release"
    release.mkdir()
    pack = QcPack(REFERENCE, tuple(_released(n) for n in range(5)), series=SERIES)
    return qc_store.write_qc_pack(
        pack, tmp_path / "secretdir-qc", release_directory=release
    ).parent


def _attest(directory, faces, outcome=Outcome.ATTESTED):
    return qc_attestation.attest(
        directory,
        reviewer=REVIEWER,
        outcome=outcome,
        coverage=COMPLETE,
        attested_at=WHEN,
        faces=faces,
    )


def _written(directory):
    path = directory / qc_attestation.ATTESTATION_FILE
    return json.loads(path.read_text("ascii"))


# The pack's series and source digests.


@pytest.mark.parametrize(
    "digest", ["", "0" * 63, "A" * 64, "g" * 64, b"0" * 64, 0], ids=repr
)
def test_a_source_digest_is_64_lower_case_hexadecimal_digits(digest):
    with pytest.raises(QcPackError, match="SHA-256"):
        dataclasses.replace(_released(0), source_sha256=digest)


@pytest.mark.parametrize(
    "positions, message",
    [
        ((), "run positions"),
        ([0, 1], "run positions"),
        ((1, 0), "once, in order"),
        ((0, 0), "once, in order"),
        ((-1,), "run position from 0"),
        ((True,), "run position from 0"),
    ],
)
def test_a_series_lists_its_instances_once_in_order(positions, message):
    with pytest.raises(QcPackError, match=message):
        SeriesEntry(positions)


@pytest.mark.parametrize(
    "series, message",
    [
        ((SeriesEntry((1, 4)), SeriesEntry((0, 2, 3))), "in order"),
        ((SeriesEntry((0, 2)), SeriesEntry((1, 2))), "in two series"),
        ((SeriesEntry((0, 5)),), "neither released nor held"),
        ((SeriesEntry((0, 9)),), "neither released nor held"),
        ((SeriesEntry((0, 3)),), "without its source's SHA-256"),
    ],
)
def test_a_pack_lists_each_released_or_held_instance_in_one_series(series, message):
    instances = (
        *(_released(n) for n in range(3)),
        _released(3, digest=False),
        _released(4),
        _sequestered(5),
    )
    with pytest.raises(QcPackError, match=message):
        QcPack(REFERENCE, instances, series=series)


def test_the_run_pack_records_source_digests_and_every_series():
    outcomes = (
        _outcome(0, run.Status.RELEASED, PurePosixPath("a/0.dcm")),
        _outcome(1, run.Status.RELEASED, PurePosixPath("a/1.dcm")),
        _outcome(2, run.Status.HELD_FOR_REVIEW, reasons=(run.RunReason.DICOMDIR,)),
        _outcome(
            3, run.Status.SEQUESTERED, label="S-0001", reasons=(run.RunReason.DICOMDIR,)
        ),
        _outcome(4, run.Status.RELEASED, PurePosixPath("a/4.dcm")),
    )
    material = {
        0: (_evidence("2.25.1", _slice(0)),),
        1: (_evidence("2.25.2", _slice(1)),),
        2: (_evidence("2.25.1", _slice(2)),),
        3: (_evidence("2.25.1", _slice(3)),),
        4: (_evidence(None, _slice(4)),),
    }
    sources = [Path(f"in/{n}.dcm") for n in range(5)]
    digests = {n: hashlib.sha256(bytes([n])).digest() for n in range(5)}

    pack = run_qc.qc_pack_of(sources, outcomes, material, digests=digests)

    assert [entry.source_sha256 for entry in pack.instances] == [
        _digest(n) for n in range(5)
    ]
    # Only released and held instances are in a series, the sequestered one
    # is not, and an instance without a series is a series of its own.
    assert pack.series == (
        SeriesEntry((0, 2)),
        SeriesEntry((1,)),
        SeriesEntry((4,)),
    )


def test_a_series_with_an_instance_without_a_digest_is_not_listed():
    outcomes = tuple(
        _outcome(n, run.Status.RELEASED, PurePosixPath(f"a/{n}.dcm")) for n in range(3)
    )
    material = {n: (_evidence(f"2.25.{n // 2}", _slice(n)),) for n in range(3)}
    sources = [Path(f"in/{n}.dcm") for n in range(3)]

    pack = run_qc.qc_pack_of(
        sources, outcomes, material, digests={1: b"\x01" * 32, 2: b"\x02" * 32}
    )

    assert pack.instances[0].source_sha256 is None
    assert pack.series == (SeriesEntry((2,)),)


@pytest.mark.deid_requirement("MIDI-BP-17")
def test_a_run_binds_each_series_to_the_digests_of_its_source_files(tmp_path):
    corpus = corpus_module.build_corpus()
    # A short directory, since a run refuses output paths that could exceed
    # Windows' 259 characters.
    directory = Path(tempfile.mkdtemp(prefix="d"))
    try:
        corpus_module.write_corpus(corpus, directory)
        instances = directory / corpus_module.INSTANCES_DIRECTORY
        transform = InstanceTransform(
            compose_policy("basic"), DeidKey(bytes(range(32))), unvalidated_policy=True
        )
        result = run.run(
            run.discover(instances),
            directory / "release",
            transform,
            ReleaseGate(),
            qc_destination=tmp_path / "qc",
        )
        digests = {
            file.manifest.name: hashlib.sha256(
                (instances / file.manifest.name).read_bytes()
            ).hexdigest()
            for file in corpus.files
        }
        # The Basic Profile writes each file's pixel data and contours as
        # received.
        pixels = {
            file.manifest.name: pixel_data_sha256(
                pydicom.dcmread(instances / file.manifest.name)
            ).hex()
            for file in corpus.files
        }
        contours = {
            file.manifest.name: contour_data_sha256(
                pydicom.dcmread(instances / file.manifest.name)
            ).hex()
            for file in corpus.files
        }
        # No preview shows an RT Dose as it could show a face.
        doses = {
            file.manifest.name
            for file in corpus.files
            if (dataset := pydicom.dcmread(instances / file.manifest.name)).get(
                "Modality"
            )
            == "RTDOSE"
            and "PixelData" in dataset
        }
    finally:
        shutil.rmtree(directory, ignore_errors=True)

    pack = json.loads(result.qc_pack.read_text(encoding="utf-8"))
    entries = pack["instances"]
    assert all(
        entry["source_sha256"] == digests[Path(entry["source"]).name]
        for entry in entries
    )
    reviewed = [
        entry["position"]
        for entry in entries
        if entry["disposition"] in ("released", "held-for-review")
    ]
    for entry in entries:
        name = Path(entry["source"]).name
        reviewable = entry["position"] in reviewed
        assert entry["pixel_sha256"] == (
            pixels[name] if reviewable and name not in doses else None
        ), entry["position"]
        assert entry["contour_sha256"] == (contours[name] if reviewable else None), (
            entry["position"]
        )
    # The structure set's contours are digested, and differ from the
    # digest of none that every other instance has.
    assert len(set(contours.values())) == 2
    listed = [position for series in pack["series"] for position in series["positions"]]
    assert sorted(listed) == reviewed
    # Every series with risks is one of the series a verdict can name.
    assert {tuple(risk["positions"]) for risk in pack["series_risks"]} <= {
        tuple(series["positions"]) for series in pack["series"]
    }

    # A verdict names a series by its first instance, and no other.
    volume = pack["series_risks"][0]["positions"]
    with pytest.raises(QcPackError, match="begins none of the QC pack's series"):
        _attest(result.qc_pack.parent, {volume[1]: Face.ABSENT})
    attestation = _attest(result.qc_pack.parent, {volume[0]: Face.ABSENT})
    assert attestation.faces == (FaceVerdict(volume[0], Face.ABSENT),)


@pytest.mark.parametrize("digester", ["pixel_data_sha256", "contour_data_sha256"])
def test_a_written_file_that_cannot_be_read_has_no_digests(monkeypatch, digester):
    def fails(dataset):
        raise RuntimeError("anything")

    data = next(
        file.data
        for file in corpus_module.build_corpus().files
        if "PixelData" in pydicom.dcmread(io.BytesIO(file.data))
    )
    dataset = pydicom.dcmread(io.BytesIO(data))
    expected = {
        "pixel_sha256": pixel_data_sha256(dataset).hex(),
        "contour_sha256": contour_data_sha256(dataset).hex(),
    }
    digests = run_qc._written_sha256  # pylint: disable = protected-access
    # A file without contours has the digest of none, shown or not.
    assert digests(data, False, True) == expected
    monkeypatch.setattr(run_qc, digester, fails)
    # Whatever taking a digest raises, the pack is still built, and no
    # verdict can clear the instance, which lacks that digest; nor one that
    # cannot be read.
    field = "pixel_sha256" if digester == "pixel_data_sha256" else "contour_sha256"
    assert digests(data, False, True) == {**expected, field: None}
    assert digests(b"not DICOM", True, True) == {
        "pixel_sha256": None,
        "contour_sha256": None,
    }


# The attestation's verdicts.


@pytest.mark.deid_requirement("MIDI-BP-17")
def test_verdicts_are_written_by_series_in_order(pack):
    attestation = _attest(pack, {1: Face.PRESENT, 0: Face.ABSENT})

    assert attestation.faces == (
        FaceVerdict(0, Face.ABSENT),
        FaceVerdict(1, Face.PRESENT),
    )
    assert _written(pack)["faces"] == [
        {"series": 0, "face": "absent"},
        {"series": 1, "face": "present"},
    ]


def test_the_record_is_unchanged_by_verdicts(pack):
    _attest(pack, {0: Face.PRESENT}, Outcome.ATTESTED)
    assert qc_attestation.attestation_record(pack) == AttestationRecord(
        REFERENCE, Outcome.ATTESTED
    )


def test_an_outcome_of_rejected_takes_no_verdict(pack):
    with pytest.raises(QcPackError, match="would release nothing"):
        _attest(pack, {0: Face.ABSENT}, Outcome.REJECTED)
    assert not (pack / qc_attestation.ATTESTATION_FILE).exists()


def test_a_reviewer_need_give_no_verdict(pack):
    attestation = _attest(pack, None)
    assert not attestation.faces
    assert _written(pack)["faces"] == []


@pytest.mark.parametrize("series", [2, 3, 4, 5, 99])
def test_a_verdict_names_the_first_instance_of_a_series(pack, series):
    with pytest.raises(QcPackError, match=f"run position {series}, which begins"):
        _attest(pack, {0: Face.ABSENT, series: Face.ABSENT})
    assert not (pack / qc_attestation.ATTESTATION_FILE).exists()


@pytest.mark.parametrize(
    "faces, message",
    [
        ({0: "absent"}, "needs a Face"),
        ({0: True}, "needs a Face"),
        ({-1: Face.ABSENT}, "first run position"),
        ({True: Face.ABSENT}, "first run position"),
        ({"0": Face.ABSENT}, "first run position"),
        ([(0, Face.ABSENT)], "map a series"),
    ],
)
def test_a_verdict_is_a_face_on_a_run_position(pack, faces, message):
    with pytest.raises(QcPackError, match=message):
        _attest(pack, faces)


@pytest.mark.parametrize(
    "faces",
    [
        (FaceVerdict(1, Face.ABSENT), FaceVerdict(0, Face.ABSENT)),
        (FaceVerdict(0, Face.ABSENT), FaceVerdict(0, Face.PRESENT)),
        [FaceVerdict(0, Face.ABSENT)],
        ((0, Face.ABSENT),),
    ],
)
def test_an_attestation_gives_each_series_one_verdict_in_order(faces):
    with pytest.raises(QcPackError, match="face verdict"):
        Attestation(
            reference=REFERENCE,
            pack_digest="0" * 64,
            outcome=Outcome.ATTESTED,
            coverage=COMPLETE,
            reviewer=REVIEWER,
            attested_at=WHEN,
            faces=faces,
        )


@pytest.mark.parametrize(
    "faces",
    [
        None,
        {},
        [{"series": 0, "face": "maybe"}],
        [{"series": 0}],
        [{"series": "0", "face": "absent"}],
        [{"series": 2, "face": "absent"}, {"series": 0, "face": "absent"}],
        [["series", 0]],
    ],
    ids=repr,
)
def test_a_written_attestation_with_malformed_verdicts_is_refused(pack, faces):
    _attest(pack, {0: Face.ABSENT})
    path = pack / qc_attestation.ATTESTATION_FILE
    document = json.loads(path.read_text("ascii"))
    if faces is None:
        del document["faces"]
    else:
        document["faces"] = faces
    path.write_text(json.dumps(document), "ascii")
    with pytest.raises(QcPackError, match="not of its format"):
        qc_attestation.attestation_record(pack)


def test_a_pack_without_its_series_cannot_be_given_verdicts(pack):
    path = pack / qc_store.PACK_FILE
    document = json.loads(path.read_text("ascii"))
    del document["series"]
    path.write_text(json.dumps(document), "ascii")
    with pytest.raises(QcPackError, match="not of its format"):
        _attest(pack, {0: Face.ABSENT})


# The command.


def _run(*argv):
    stdout, stderr = io.StringIO(), io.StringIO()
    status = command.main(list(argv), stdout=stdout, stderr=stderr)
    return status, stdout.getvalue(), stderr.getvalue()


def _assert_quotes_nothing(*texts):
    for text in texts:
        for sentinel in ("Quokka", "Wombatson", "secretdir"):
            assert sentinel not in text


@pytest.mark.deid_requirement("MIDI-BP-17")
def test_the_command_records_each_verdict(pack):
    status, stdout, stderr = _run(
        str(pack),
        "--reviewer",
        REVIEWER,
        "--outcome",
        "attested",
        *EVERY_REVIEW,
        "--face-present",
        "1",
        "--face-absent",
        "0",
        "--face-absent",
        "0",
    )

    assert status == command.EXIT_RECORDED, stderr
    assert _written(pack)["faces"] == [
        {"series": 0, "face": "absent"},
        {"series": 1, "face": "present"},
    ]
    assert stdout.splitlines()[-6:] == [
        "  series without a recognisable face: 1",
        "  series with a recognisable face: 1",
        "  cleaned instances with their regions accepted: 0",
        "  cleaned instances with the reviewer's regions added: 0",
        "  cleaned instances rejected: 0",
        "the release report published with the run is unchanged",
    ]
    _assert_quotes_nothing(stdout, stderr)


@pytest.mark.parametrize(
    "verdicts, message",
    [
        (("--face-absent", "0", "--face-present", "0"), "both face verdicts"),
        (("--face-absent", "2"), "begins none of the QC pack's series"),
        (("--face-present", "-1"), "first run position"),
    ],
)
def test_the_command_refuses_a_verdict_it_cannot_record(pack, verdicts, message):
    status, stdout, stderr = _run(
        str(pack),
        "--reviewer",
        REVIEWER,
        "--outcome",
        "attested",
        *EVERY_REVIEW,
        *verdicts,
    )

    assert status == command.EXIT_NOT_RECORDED
    assert message in stderr and "nothing was recorded" in stderr
    assert not stdout
    assert not (pack / qc_attestation.ATTESTATION_FILE).exists()
    _assert_quotes_nothing(stdout, stderr)


def test_the_command_refuses_a_verdict_with_an_outcome_of_rejected(pack):
    status, stdout, stderr = _run(
        str(pack), "--reviewer", REVIEWER, "--outcome", "rejected", "--face-absent", "0"
    )

    assert status == command.EXIT_NOT_RECORDED
    assert "would release nothing; nothing was recorded" in stderr
    assert not stdout
    assert not (pack / qc_attestation.ATTESTATION_FILE).exists()


def test_a_position_that_is_not_a_number_is_a_usage_error(pack):
    with pytest.raises(SystemExit) as raised:
        _run(
            str(pack),
            "--reviewer",
            REVIEWER,
            "--outcome",
            "rejected",
            "--face-absent",
            "Wombatson",
        )
    assert raised.value.code == command.EXIT_USAGE
    assert not (pack / qc_attestation.ATTESTATION_FILE).exists()
