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

"""The readiness of a ``public-release`` run in the command line's and the library's runs.

A ``public-release`` run is given, with ``--readiness-review`` and
``--readiness-report``, or the library's ``readiness_review`` and
``readiness_report``, the QC pack of an earlier run of the same files, which
a reviewer attested and beside which an assessment was recorded, and that
run's release report, and its release report then says whether it is ready
for release (D-017, D-053). Every name, path, and data set here is invented
or synthetic.
"""

# The command line's and the library's runs share the collection's reviewed
# runs below, which are slow to make, so they stay in one module.
# pylint: disable = too-many-lines

import contextlib
import dataclasses
import io
import json
import os
import shutil
import tempfile
from pathlib import Path

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    api,
    command,
    instance_transform,
    pilot_command,
    policy,
    qc_attestation,
    qc_store,
    release_report,
    risk_assessment,
    run,
    run_report,
)
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.qc_attestation import Face, Outcome
from pymedphys._dicom.deidentify.readiness import ReadinessReview
from pymedphys._dicom.deidentify.reasons import ReviewReason, StatisticalReason
from pymedphys._dicom.deidentify.reviewed_roi_names import (
    Review,
    ReviewedName,
    ReviewedNames,
)

from . import _corpus_run
from . import _synthetic_references as synthetic
from .test_deidentify_readiness import COMPLETE, REVIEWER, WHEN, _assessment
from .test_deidentify_run import SENTINEL, _write

pytestmark = pytest.mark.pydicom

PUBLIC_RELEASE = "public-release"
# A second ROI of the corpus's structure set, whose name echoes no identifier,
# so that a reviewer can keep it, and what the collection's list maps it to.
BOOST = "Boost region"
BOOST_MAPPED = "PTV_Boost"
_RADIOTHERAPY = frozenset({"CT Image", "RT Structure Set", "RT Dose", "RT Plan"})
# The gates in the order that the release report and the summary give them.
_GATES = ("statistical", "pixel_and_face", "attestation")
_NOT_READY = {
    "ready": False,
    "review": None,
    "assessment": None,
    "statistical": "no-assessment",
    "pixel_and_face": "no-review",
    "attestation": "no-review",
}


@contextlib.contextmanager
def _enabling():
    """Enable the Basic Profile and ``public-release``, which no release
    enables yet, and serve the invented TG-263 edition as published, so that
    nothing is downloaded."""
    with _corpus_run.published_vocabulary(), pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            policy,
            "ENABLED_PRESETS",
            frozenset({policy.DEFAULT_PRESET, PUBLIC_RELEASE}),
        )
        patch.setattr(
            command.tg263_published, "load", lambda *_, **__: _corpus_run.VOCABULARY
        )
        yield


@pytest.fixture(name="enabled")
def _enabled():
    with _enabling():
        yield


# The collection and its reviewed runs.


@dataclasses.dataclass(frozen=True)
class _Collection:
    """A collection of two subjects, run once under the Basic Profile and once
    under ``public-release``, and copies of the second run's QC pack, each
    attested and assessed in its own way.

    Attributes
    ----------
    source : Path
        The collection: the synthetic corpus's radiotherapy files, of one
        subject, its structure set with a second ROI named :data:`BOOST`,
        and a CT series, structure set, plan, and dose of another.
    subset : Path
        The same files but the second subject's RT Plan.
    names : Path
        The reviewed-names list that maps the corpus's planted ROI Name and
        :data:`BOOST`.
    face_pack : Path
        The Basic Profile run's QC pack, attested with no face verdicts, as
        the first ``public-release`` run of a collection is given.
    face_report : Path
        That run's release report.
    reviewed : Path
        The ``public-release`` run's QC pack, as it wrote it.
    report : Path
        Its release report.
    first : tuple
        Its exit status, standard output, and standard error.
    subjects : int
        The distinct subjects of the instances that a run of the collection
        releases.
    packs : dict of str to Path
        Copies of ``reviewed``, by name: ``ready``, attested with every
        series marked absent and the residual risk accepted, and assessed;
        ``unassessed``, attested so, without an assessment; ``unaccepted``,
        with the residual risk not accepted; ``above-threshold``,
        ``fewer-subjects``, and ``more-subjects``, whose assessments give
        the maximum risk above the threshold, or a subject fewer or more;
        ``not-attested``, as written; and ``rejected``.
    """

    source: Path
    subset: Path
    names: Path
    face_pack: Path
    face_report: Path
    reviewed: Path
    report: Path
    first: tuple
    subjects: int
    packs: dict


@pytest.fixture(name="collection", scope="module")
def fixture_collection():
    # A short directory, since a run refuses output paths that could exceed
    # Windows' 259 characters.
    directory = Path(tempfile.mkdtemp(prefix="d"))
    try:
        with _enabling():
            yield _collection(directory)
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _collection(directory):
    corpus = corpus_module.build_corpus()
    corpus = dataclasses.replace(
        corpus,
        files=tuple(f for f in corpus.files if f.manifest.iod in _RADIOTHERAPY),
    )
    corpus = _corpus_run.with_a_second_roi(corpus, BOOST)
    (directory / "corpus").mkdir()
    corpus_module.write_corpus(corpus, directory / "corpus")
    source = directory / "source"
    shutil.copytree(directory / "corpus" / corpus_module.INSTANCES_DIRECTORY, source)
    other = synthetic.collection()
    _write(source / "other", other)
    subset = directory / "subset"
    shutil.copytree(source, subset)
    (subset / "other" / "004.dcm").unlink()  # the second subject's RT Plan
    planted = _corpus_run.planted_roi_name(corpus)
    names = directory / "custodian" / "reviewed.json"
    names.parent.mkdir()
    listed = ReviewedNames.open(names)
    listed.record(planted, ReviewedName(Review.MAP, _corpus_run.MAPPED_NAME))
    listed.record(BOOST, ReviewedName(Review.MAP, BOOST_MAPPED))
    listed.save()

    status, _, err = _command(source, directory / "r0", "--preset", "basic")
    assert status in (command.EXIT_RELEASED, command.EXIT_WITHHELD), err
    face_pack = directory / "r0" / "qc"
    _attest(face_pack, {})
    first = _command(
        source,
        directory / "r1",
        "--preset",
        PUBLIC_RELEASE,
        "--reviewed-names",
        str(names),
        "--face-review",
        str(face_pack),
    )
    assert first[0] == command.EXIT_WITHHELD, first[2]
    reviewed = directory / "r1" / "qc"
    report = directory / "r1" / "release" / run_report.RELEASE_REPORT
    subjects = 2
    packs = {}
    for name in (
        "ready",
        "unassessed",
        "unaccepted",
        "above-threshold",
        "fewer-subjects",
        "more-subjects",
        "not-attested",
        "rejected",
    ):
        pack = directory / "packs" / name
        shutil.copytree(reviewed, pack)
        packs[name] = pack
    every_series = {
        entry["positions"][0]: Face.ABSENT
        for entry in _pack_document(reviewed)["series"]
    }
    for name in (
        "ready",
        "unassessed",
        "above-threshold",
        "fewer-subjects",
        "more-subjects",
    ):
        _attest(packs[name], every_series)
    _attest(packs["unaccepted"], every_series, accepted=False)
    _attest(packs["rejected"], None, outcome=Outcome.REJECTED)
    assessments = {
        "ready": _assessment(subjects=subjects),
        "unaccepted": _assessment(subjects=subjects),
        "above-threshold": _assessment(subjects=subjects, maximum_risk=0.5),
        "fewer-subjects": _assessment(subjects=subjects - 1),
        "more-subjects": _assessment(subjects=subjects + 1),
    }
    for name, assessment in assessments.items():
        risk_assessment.record_assessment(packs[name], report, assessment)
    return _Collection(
        source=source,
        subset=subset,
        names=names,
        face_pack=face_pack,
        face_report=directory / "r0" / "release" / run_report.RELEASE_REPORT,
        reviewed=reviewed,
        report=report,
        first=first,
        subjects=subjects,
        packs=packs,
    )


def _attest(pack, faces, *, outcome=Outcome.ATTESTED, accepted=True):
    return qc_attestation.attest(
        pack,
        reviewer=REVIEWER,
        outcome=outcome,
        coverage=COMPLETE,
        attested_at=WHEN,
        residual_risk_accepted=None if outcome is Outcome.REJECTED else accepted,
        faces=faces,
    )


def _pack_document(pack):
    return json.loads((pack / qc_store.PACK_FILE).read_text("utf-8"))


def _command(source, directory, *options):
    stdout, stderr = io.StringIO(), io.StringIO()
    directory.mkdir(parents=True)
    status = command.main(
        [
            str(source),
            str(directory / "release"),
            "--qc-pack",
            str(directory / "qc"),
            *options,
        ],
        stdout=stdout,
        stderr=stderr,
    )
    return status, stdout.getvalue(), stderr.getvalue()


def _readiness(release):
    report = json.loads((release / run_report.RELEASE_REPORT).read_text("utf-8"))
    return report["readiness"]


# Second runs of the collection, through the command line or the library,
# each given one of the reviewed packs as its face and readiness reviews.


@dataclasses.dataclass(frozen=True)
class _Second:
    readiness: dict
    summary: list
    status: int
    err: str
    released: frozenset


def _second(collection, directory, pack, *, entry, source=None, **changes):
    """Run the collection again under ``public-release``, given ``pack`` as its
    face and readiness reviews and the reviewed run's release report, through
    ``entry``, the command line or the library, with ``changes`` to its
    arguments: ``safe_private_list`` or ``reviewed_names``."""
    arguments = {"reviewed_names": collection.names, **changes}
    source = collection.source if source is None else source
    release = directory / "release"
    if entry == "command":
        options = [
            "--preset",
            PUBLIC_RELEASE,
            "--face-review",
            str(pack),
            "--readiness-review",
            str(pack),
            "--readiness-report",
            str(collection.report),
        ]
        for name, value in arguments.items():
            options += [f"--{name.replace('_', '-')}", str(value)]
        status, out, err = _command(source, directory, *options)
        assert status != command.EXIT_NOT_RUN, err
        return _Second(
            _readiness(release), out.splitlines(), status, err, _released(directory)
        )
    directory.mkdir(parents=True)
    done = api.deidentify(
        source,
        release,
        qc_pack=directory / "qc",
        preset=PUBLIC_RELEASE,
        face_review=pack,
        readiness_review=pack,
        readiness_report=collection.report,
        **arguments,
    )
    readiness = _readiness(release)
    assert done.readiness == _from_section(readiness)
    return _Second(
        readiness, done.summary(), done.exit_status, "", _released(directory)
    )


def _released(directory):
    """The names of the source files that a run released."""
    return frozenset(
        Path(entry["source"]).name
        for entry in _pack_document(directory / "qc")["instances"]
        if entry["disposition"] == "released"
    )


def _from_section(section):
    return release_report.Readiness(
        review=section["review"],
        assessment=section["assessment"],
        statistical=None
        if section["statistical"] is None
        else StatisticalReason(section["statistical"]),
        pixel_and_face=None
        if section["pixel_and_face"] is None
        else ReviewReason(section["pixel_and_face"]),
        attestation=None
        if section["attestation"] is None
        else ReviewReason(section["attestation"]),
    )


def _gates(readiness):
    return tuple(readiness[gate] for gate in _GATES)


def _keeping_the_boost(collection, directory):
    """The collection's reviewed-names list, but keeping :data:`BOOST` as
    received rather than mapping it, so that the structure set retains a
    string that the reviewed run's did not."""
    path = directory / "custodian" / "keeping.json"
    path.parent.mkdir(parents=True)
    shutil.copyfile(collection.names, path)
    listed = ReviewedNames.open(path)
    listed.record(BOOST, ReviewedName(Review.KEEP), replace=True)
    listed.save()
    return path


def _with_an_unused_decision(collection, directory):
    """The collection's reviewed-names list, with one more decision, on a name
    that no instance holds."""
    path = directory / "custodian" / "added.json"
    path.parent.mkdir(parents=True)
    shutil.copyfile(collection.names, path)
    listed = ReviewedNames.open(path)
    listed.record("Invented unused", ReviewedName(Review.KEEP))
    listed.save()
    return path


_ENTRIES = ("command", "library")


@pytest.fixture(name="entry", params=_ENTRIES)
def fixture_entry(request):
    return request.param


# The first public-release run, given no readiness review.


def test_the_first_runs_report_and_summary_say_it_is_not_ready(collection):
    status, out, err = collection.first

    assert status == command.EXIT_WITHHELD, err
    assert _readiness(collection.report.parent) == _NOT_READY
    lines = out.splitlines()
    assert lines[-4:] == [
        "readiness for release: not ready",
        "  statistical: no-assessment",
        "  pixel and face review: no-review",
        "  attestation: no-review",
    ]


# A second run that passes every gate.


@pytest.mark.deid_requirement(
    "MIDI-BP-01", "MIDI-BP-07", "MIDI-BP-10", "MIDI-BP-11", "MIDI-BP-15"
)
def test_a_second_run_given_its_reviewed_and_assessed_pack_is_ready(
    collection, tmp_path, entry
):
    pack = collection.packs["ready"]
    record = risk_assessment.read_assessment(pack)

    second = _second(collection, tmp_path / "r2", pack, entry=entry)

    assert second.readiness == {
        "ready": True,
        "review": _pack_document(pack)["reference"],
        "assessment": record.reference,
        "statistical": None,
        "pixel_and_face": None,
        "attestation": None,
    }
    assert second.summary[-4:] == [
        "readiness for release: ready",
        "  statistical: passed",
        "  pixel and face review: passed",
        "  attestation: passed",
    ]
    assert str(pack) not in "\n".join(second.summary) + second.err
    # Readiness is of what a run releases: an instance that it holds is not
    # released, so it neither passes nor fails a gate.
    assert second.status == command.EXIT_WITHHELD
    assert "  held-for-review: " in "\n".join(second.summary)
    # Both subjects' images and plans, and the structure set's contours,
    # were released, so the gates checked pixel data, contours, and an
    # instance with neither.
    assert {"01-ct-1.dcm", "04-rtstruct.dcm", "05-rtplan.dcm", "000.dcm"} <= (
        second.released
    )


# Each gate's reasons that a second run can reach.


@pytest.mark.deid_requirement("MIDI-BP-01", "MIDI-BP-15")
@pytest.mark.parametrize(
    "name, gates",
    [
        ("unassessed", ("no-assessment", None, None)),
        ("above-threshold", ("above-threshold", None, None)),
        ("fewer-subjects", ("fewer-subjects", None, None)),
        ("more-subjects", ("more-subjects", None, None)),
        ("unaccepted", (None, None, "residual-risk-not-accepted")),
    ],
)
def test_a_pack_attested_or_assessed_otherwise_fails_its_gate_alone(
    collection, tmp_path, entry, name, gates
):
    second = _second(collection, tmp_path / "r2", collection.packs[name], entry=entry)

    assert _gates(second.readiness) == gates
    assert second.readiness["ready"] is False
    assert second.summary[0 - len(_GATES) - 1] == "readiness for release: not ready"


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_run_of_other_files_fails_every_gate(collection, tmp_path, entry):
    second = _second(
        collection,
        tmp_path / "r2",
        collection.packs["ready"],
        entry=entry,
        source=collection.subset,
    )

    assert _gates(second.readiness) == ("other-collection",) * 3


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_run_under_another_list_of_safe_private_rules_fails_every_gate(
    collection, tmp_path, entry
):
    second = _second(
        collection,
        tmp_path / "r2",
        collection.packs["ready"],
        entry=entry,
        safe_private_list="tcia",
    )

    assert _gates(second.readiness) == ("other-policy",) * 3


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_run_with_another_reviewed_names_list_fails_the_statistical_gate(
    collection, tmp_path, entry
):
    names = _with_an_unused_decision(collection, tmp_path)

    second = _second(
        collection,
        tmp_path / "r2",
        collection.packs["ready"],
        entry=entry,
        reviewed_names=names,
    )

    assert _gates(second.readiness) == ("other-lists", None, None)


@pytest.mark.deid_requirement("MIDI-BP-01", "MIDI-BP-15")
def test_a_string_that_an_edited_list_now_keeps_fails_the_attestation_gate(
    collection, tmp_path, entry
):
    names = _keeping_the_boost(collection, tmp_path)

    second = _second(
        collection,
        tmp_path / "r2",
        collection.packs["ready"],
        entry=entry,
        reviewed_names=names,
    )

    assert _gates(second.readiness) == (
        "other-lists",
        None,
        "unreviewed-retained-string",
    )


# The reviewed pack's own reasons, which a run through the command line or the
# library never reaches, since its readiness review is its face review's pack,
# which must be attested and not rejected.


@pytest.mark.parametrize(
    "name, says",
    [("not-attested", "has not been attested"), ("rejected", "rejected it")],
)
def test_a_pack_not_attested_or_rejected_stops_the_run_as_its_face_review(
    collection, tmp_path, entry, name, says
):
    pack = collection.packs[name]

    message = _refused(
        collection, tmp_path, entry, face_review=pack, readiness_review=pack
    )

    assert message.startswith("the face review could not be read: ")
    assert says in message


# What the run refuses before it starts.


def _refused(collection, tmp_path, entry, **changes):
    """Return the message with which a ``public-release`` run of the
    collection was refused, having checked that it created nothing."""
    arguments = {
        "face_review": collection.packs["ready"],
        "readiness_review": collection.packs["ready"],
        "readiness_report": collection.report,
        "reviewed_names": collection.names,
        **changes,
    }
    before = sorted(tmp_path.rglob("*"))
    directory = tmp_path / "refused"
    if entry == "command":
        options = ["--preset", PUBLIC_RELEASE]
        for name, value in arguments.items():
            if value is not None:
                options += [f"--{name.replace('_', '-')}", str(value)]
        stdout, stderr = io.StringIO(), io.StringIO()
        status = command.main(
            [
                str(collection.source),
                str(directory / "release"),
                "--qc-pack",
                str(directory / "qc"),
                *options,
            ],
            stdout=stdout,
            stderr=stderr,
        )
        assert (status, stdout.getvalue()) == (command.EXIT_NOT_RUN, "")
        err = stderr.getvalue()
        assert err.startswith("error: ") and err.endswith("\n")
        message = err[len("error: ") : -1]
    else:
        with pytest.raises(api.DeidentifyError) as raised:
            api.deidentify(
                collection.source,
                directory / "release",
                qc_pack=directory / "qc",
                preset=PUBLIC_RELEASE,
                **arguments,
            )
        assert raised.value.__cause__ is None and raised.value.__suppress_context__
        message = str(raised.value)
    assert sorted(tmp_path.rglob("*")) == before
    assert SENTINEL not in message and str(tmp_path) not in message
    assert str(collection.source.parent) not in message
    return message


def test_a_readiness_review_of_another_pack_than_the_face_review_is_refused(
    collection, tmp_path, entry
):
    # The Basic Profile run's pack is attested, and its report names it, so
    # it is read as a review; but its verdicts are not those that release
    # this run's instances.
    message = _refused(
        collection,
        tmp_path,
        entry,
        readiness_review=collection.face_pack,
        readiness_report=collection.face_report,
    )

    assert message == command._READINESS_OTHER_PACK  # pylint: disable = protected-access


def _not_json(tmp_path):
    path = tmp_path / SENTINEL / "release-report.json"
    path.parent.mkdir()
    path.write_text(f"{SENTINEL} is not JSON", "utf-8")
    return path


@pytest.mark.parametrize(
    "problem, says",
    [
        ("missing pack", "the directory holds no QC pack"),
        ("empty pack", "the directory holds no QC pack"),
        ("missing report", "the release report could not be read: "),
        ("report not JSON", "the release report is not of its format"),
        ("report of another run", "the release report names another QC pack"),
    ],
)
def test_a_readiness_review_that_cannot_be_read_is_refused_naming_no_path(
    collection, tmp_path, entry, problem, says
):
    holder = tmp_path / SENTINEL
    changes = {
        "missing pack": lambda: {"readiness_review": holder / "absent"},
        "empty pack": lambda: {"readiness_review": holder},
        "missing report": lambda: {"readiness_report": holder / "absent.json"},
        "report not JSON": lambda: {"readiness_report": _not_json(tmp_path)},
        "report of another run": lambda: {"readiness_report": collection.face_report},
    }[problem]
    if problem in ("empty pack", "missing pack", "missing report"):
        holder.mkdir()

    message = _refused(collection, tmp_path, entry, **changes())

    assert message.startswith("the readiness review could not be read: ")
    assert says in message


def test_a_readiness_review_whose_assessment_cannot_be_read_is_refused(
    collection, tmp_path, entry
):
    pack = tmp_path / "pack"
    shutil.copytree(collection.packs["ready"], pack)
    record = pack / risk_assessment.ASSESSMENT_FILE
    record.chmod(0o600)
    record.write_text(json.dumps({"format": SENTINEL}), "utf-8")

    message = _refused(
        collection, tmp_path, entry, face_review=pack, readiness_review=pack
    )

    assert message.startswith("the readiness review could not be read: ")
    assert "risk assessment" in message


@pytest.mark.parametrize("entry_", _ENTRIES)
def test_the_preset_not_enabled_is_refused_before_the_readiness_review_is_read(
    tmp_path, monkeypatch, entry_
):
    monkeypatch.setattr(policy, "ENABLED_PRESETS", frozenset({"basic"}))
    absent = tmp_path / SENTINEL
    arguments = {
        "face_review": absent,
        "readiness_review": absent,
        "readiness_report": absent / "release-report.json",
    }
    if entry_ == "command":
        stderr = io.StringIO()
        options = []
        for name, value in arguments.items():
            options += [f"--{name.replace('_', '-')}", str(value)]
        status = command.main(
            [
                str(tmp_path / "source"),
                str(tmp_path / "release"),
                "--qc-pack",
                str(tmp_path / "qc"),
                "--preset",
                PUBLIC_RELEASE,
                *options,
            ],
            stdout=io.StringIO(),
            stderr=stderr,
        )
        assert status == command.EXIT_NOT_RUN
        message = stderr.getvalue()
    else:
        with pytest.raises(api.DeidentifyError) as raised:
            api.deidentify(
                tmp_path / "source",
                tmp_path / "release",
                qc_pack=tmp_path / "qc",
                preset=PUBLIC_RELEASE,
                **arguments,
            )
        message = str(raised.value)

    assert "not enabled" in message and "review" not in message
    assert not any(tmp_path.iterdir())


# The arguments, which go together and need the preset.


_ELSEWHERE = [
    ((), {}),
    (("--preset", "basic"), {"preset": "basic"}),
    (("--preset", "tps-import"), {"preset": "tps-import"}),
    # A custom option set, even one with the preset's options, is not the
    # preset, whose release report alone says whether a run is ready.
    (
        tuple(
            part
            for option in policy.PRESETS[PUBLIC_RELEASE]
            for part in ("--option", option)
        ),
        {"options": list(policy.PRESETS[PUBLIC_RELEASE])},
    ),
]
_ELSEWHERE_IDS = ["default", "basic", "tps-import", "public-release-options"]


@pytest.mark.parametrize("arguments, keywords", _ELSEWHERE, ids=_ELSEWHERE_IDS)
def test_a_readiness_review_without_the_preset_is_a_usage_error(
    tmp_path, arguments, keywords
):
    del keywords
    absent = str(tmp_path / SENTINEL)
    stdout, stderr = io.StringIO(), io.StringIO()
    status = command.main(
        [
            str(tmp_path / "source"),
            str(tmp_path / "release"),
            "--qc-pack",
            str(tmp_path / "qc"),
            *arguments,
            "--readiness-review",
            absent,
            "--readiness-report",
            absent,
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert status == command.EXIT_USAGE
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == (
        "error: --readiness-review and --readiness-report apply only under the "
        "public-release preset: with --preset public-release\n"
    )
    assert not any(tmp_path.iterdir())


@pytest.mark.parametrize("arguments, keywords", _ELSEWHERE, ids=_ELSEWHERE_IDS)
def test_a_readiness_review_without_the_preset_is_refused_by_the_library(
    tmp_path, arguments, keywords
):
    del arguments
    absent = tmp_path / SENTINEL

    with pytest.raises(ValueError, match="only under the public-release preset"):
        api.deidentify(
            tmp_path / "source",
            tmp_path / "release",
            qc_pack=tmp_path / "qc",
            readiness_review=absent,
            readiness_report=absent,
            **keywords,
        )

    assert not any(tmp_path.iterdir())


@pytest.mark.parametrize("given", ["--readiness-review", "--readiness-report"])
def test_a_readiness_review_or_report_alone_is_a_usage_error(tmp_path, given):
    stdout, stderr = io.StringIO(), io.StringIO()
    status = command.main(
        [
            str(tmp_path / "source"),
            str(tmp_path / "release"),
            "--qc-pack",
            str(tmp_path / "qc"),
            "--preset",
            PUBLIC_RELEASE,
            given,
            str(tmp_path / SENTINEL),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert status == command.EXIT_USAGE
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == (
        "error: a readiness review and its release report are given together, "
        "or neither\n"
    )
    assert not any(tmp_path.iterdir())


@pytest.mark.parametrize("given", ["readiness_review", "readiness_report"])
def test_a_readiness_review_or_report_alone_is_refused_by_the_library(tmp_path, given):
    with pytest.raises(ValueError, match="together"):
        api.deidentify(
            tmp_path / "source",
            tmp_path / "release",
            qc_pack=tmp_path / "qc",
            preset=PUBLIC_RELEASE,
            **{given: tmp_path / SENTINEL},
        )

    assert not any(tmp_path.iterdir())


@pytest.mark.parametrize(
    "keywords, says",
    [
        ({"readiness_review": "pack"}, "together"),
        ({"readiness_report": "report"}, "together"),
        (
            {
                "readiness_review": "pack",
                "readiness_report": "report",
                "preset": "basic",
            },
            "only under the public-release preset",
        ),
        (
            {
                "readiness_review": "pack",
                "readiness_report": "report",
                "preset": None,
                "options": list(policy.PRESETS[PUBLIC_RELEASE]),
            },
            "only under the public-release preset",
        ),
    ],
)
def test_transform_for_refuses_a_readiness_review_before_reading_anything(
    tmp_path, monkeypatch, keywords, says
):
    monkeypatch.setattr(
        policy, "ENABLED_PRESETS", frozenset({policy.DEFAULT_PRESET, PUBLIC_RELEASE})
    )
    monkeypatch.setattr(
        policy, "ENABLED_OPTIONS", frozenset(policy.PRESETS[PUBLIC_RELEASE])
    )
    keywords = {
        name: tmp_path / SENTINEL / value if name.startswith("readiness") else value
        for name, value in keywords.items()
    }
    preset = keywords.pop("preset", PUBLIC_RELEASE)

    with pytest.raises(command.TransformNotBuilt, match=says) as raised:
        command.transform_for(
            preset,
            _corpus_run.KEY,
            source=tmp_path / "source",
            release=tmp_path / "release",
            qc_pack=tmp_path / "qc",
            **keywords,
        )

    assert raised.value.__cause__ is None
    assert not any(tmp_path.iterdir())


@pytest.mark.parametrize(
    "preset, options, applies",
    [
        (PUBLIC_RELEASE, None, True),
        (None, None, False),
        ("basic", None, False),
        ("basic-clean-descriptors", None, False),
        ("tps-import", None, False),
        (None, policy.PRESETS[PUBLIC_RELEASE], False),
        (None, (), False),
    ],
)
def test_a_readiness_review_applies_under_the_public_release_preset_alone(
    preset, options, applies
):
    assert command.readiness_review_applies(preset, options) is applies


def test_the_help_names_the_readiness_arguments(capsys):
    with pytest.raises(SystemExit):
        command.main(["--help"])

    text = " ".join(capsys.readouterr().out.split())
    assert "--readiness-review DIRECTORY" in text
    assert "--readiness-report FILE" in text
    assert "under the public-release preset, the QC pack given as --face-review" in text


@pytest.mark.usefixtures("enabled")
def test_the_transform_is_given_the_review_of_the_face_reviews_pack(
    collection, tmp_path, monkeypatch
):
    built = []
    real = instance_transform.InstanceTransform

    def recording(selected, key, *args, **kwargs):
        built.append(kwargs)
        return real(selected, key, *args, **kwargs)

    monkeypatch.setattr(instance_transform, "InstanceTransform", recording)
    pack = collection.packs["ready"]

    transform = command.transform_for(
        PUBLIC_RELEASE,
        _corpus_run.KEY,
        source=collection.source,
        release=tmp_path / "release",
        qc_pack=tmp_path / "qc",
        reviewed_names=collection.names,
        face_review=pack,
        readiness_review=pack,
        readiness_report=collection.report,
    )

    (kwargs,) = built
    review = kwargs["readiness_review"]
    assert isinstance(review, ReadinessReview)
    assert review.reference == kwargs["face_review"].reference
    assert review.reference == _pack_document(pack)["reference"]
    assert review.assessment == risk_assessment.read_assessment(pack)
    assert transform.reporter is not None


# Reading a published release's readiness.


def _published(tmp_path, document):
    release = tmp_path / "release"
    release.mkdir()
    (release / run_report.RELEASE_REPORT).write_text(
        document if isinstance(document, str) else json.dumps(document), "utf-8"
    )
    return release


def _result(release):
    return run.RunResult(release, (), ())


def test_a_release_without_a_report_has_no_readiness(tmp_path):
    assert command.release_readiness(tmp_path) is None
    assert command.summary_lines(_result(tmp_path), _no_redactions()) == [
        f"release directory: {tmp_path}",
        "inputs: 0",
    ]


def _no_redactions():
    return api.RedactionCounts(0, 0)


def _report(readiness):
    return {"format": release_report.FORMAT, "readiness": readiness}


def test_a_report_of_another_policy_has_no_readiness(tmp_path):
    release = _published(tmp_path, _report(None))

    assert command.release_readiness(release) is None
    assert len(command.summary_lines(_result(release), _no_redactions())) == 2


def test_a_published_readiness_is_read_by_its_codes(tmp_path):
    section = {
        "ready": False,
        "review": "A-" + "0" * 32,
        "assessment": "R-" + "1" * 32,
        "statistical": "above-threshold",
        "pixel_and_face": None,
        "attestation": "unreviewed-retained-string",
    }
    release = _published(tmp_path, _report(section))

    assert command.release_readiness(release) == release_report.Readiness(
        review="A-" + "0" * 32,
        assessment="R-" + "1" * 32,
        statistical=StatisticalReason.ABOVE_THRESHOLD,
        pixel_and_face=None,
        attestation=ReviewReason.UNREVIEWED_RETAINED_STRING,
    )
    assert command.summary_lines(_result(release), _no_redactions())[-4:] == [
        "readiness for release: not ready",
        "  statistical: above-threshold",
        "  pixel and face review: passed",
        "  attestation: unreviewed-retained-string",
    ]


@pytest.mark.parametrize(
    "document",
    [
        f"{SENTINEL} is not JSON",
        [],
        _report(SENTINEL),
        _report([]),
        _report({**_NOT_READY, "statistical": SENTINEL}),
        _report({**_NOT_READY, "attestation": 1}),
        _report({**_NOT_READY, "review": 1}),
        _report({**_NOT_READY, "ready": True}),
        _report({**_NOT_READY, "ready": None}),
        _report(
            {key: value for key, value in _NOT_READY.items() if key != "attestation"}
        ),
    ],
    ids=[
        "not-json",
        "not-an-object",
        "string",
        "list",
        "unknown-code",
        "code-not-text",
        "reference-not-text",
        "ready-disagrees",
        "ready-not-boolean",
        "gate-missing",
    ],
)
def test_a_published_readiness_that_cannot_be_read_says_so_naming_nothing(
    tmp_path, document
):
    release = _published(tmp_path, document)

    with pytest.raises(release_report.ReleaseReportError) as raised:
        command.release_readiness(release)

    assert str(raised.value) == "the release report's readiness could not be read"
    assert raised.value.__cause__ is None
    lines = command.summary_lines(_result(release), _no_redactions())
    assert lines[-1] == (
        "readiness for release: unknown, since the release report's readiness "
        "could not be read"
    )
    assert SENTINEL not in "\n".join(lines)


def test_a_published_readiness_that_cannot_be_opened_says_so(tmp_path):
    if os.name == "nt":
        pytest.skip("a directory in the report's place is opened otherwise on Windows")
    release = tmp_path / "release"
    (release / run_report.RELEASE_REPORT).mkdir(parents=True)

    with pytest.raises(release_report.ReleaseReportError):
        command.release_readiness(release)


# The pilot command, which runs a preset that is not enabled, for validation.


def _pilot(*options):
    stdout, stderr = io.StringIO(), io.StringIO()
    status = pilot_command.main(list(options), stdout=stdout, stderr=stderr)
    return status, stdout.getvalue().splitlines(), stderr.getvalue()


@pytest.mark.usefixtures("enabled")
def test_a_pilot_of_the_preset_given_its_readiness_review_says_it_is_ready(
    collection, monkeypatch
):
    # The pilot runs the preset whether or not it is enabled.
    monkeypatch.setattr(policy, "ENABLED_PRESETS", frozenset())
    pack = collection.packs["ready"]

    status, lines, err = _pilot(
        str(collection.source),
        "--preset",
        PUBLIC_RELEASE,
        "--reviewed-names",
        str(collection.names),
        "--face-review",
        str(pack),
        "--readiness-review",
        str(pack),
        "--readiness-report",
        str(collection.report),
    )

    assert status == command.EXIT_WITHHELD, err
    start = lines.index("readiness for release: ready")
    assert lines[start + 1 : start + 4] == [
        "  statistical: passed",
        "  pixel and face review: passed",
        "  attestation: passed",
    ]
    assert str(pack) not in "\n".join(lines) + err


@pytest.mark.parametrize(
    "arguments, says",
    [
        (
            ("--preset", "basic", "--readiness-review", "x", "--readiness-report", "x"),
            "apply only under the public-release preset",
        ),
        (
            ("--option", policy.CLEAN_RECOGNIZABLE_VISUAL_FEATURES)
            + ("--readiness-review", "x", "--readiness-report", "x"),
            "apply only under the public-release preset",
        ),
        (("--preset", PUBLIC_RELEASE, "--readiness-review", "x"), "together"),
        (("--preset", PUBLIC_RELEASE, "--readiness-report", "x"), "together"),
    ],
    ids=["basic", "options", "review-alone", "report-alone"],
)
def test_the_pilots_readiness_arguments_are_checked_before_it_runs(
    tmp_path, arguments, says
):
    status, lines, err = _pilot(str(tmp_path / "source"), *arguments)

    assert status == command.EXIT_USAGE
    assert lines == []
    assert err.startswith("error: --readiness-review and --readiness-report ")
    assert says in err
    assert not any(tmp_path.iterdir())


def test_the_pilots_help_names_the_readiness_arguments(capsys):
    with pytest.raises(SystemExit):
        pilot_command.main(["--help"])

    text = " ".join(capsys.readouterr().out.split())
    assert "--readiness-review DIRECTORY" in text
    assert "--readiness-report FILE" in text
