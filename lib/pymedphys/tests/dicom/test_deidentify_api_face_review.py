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

"""The Clean Recognizable Visual Features Option in the library's runs.

A run under the option is given the QC pack of an earlier run of the same
files, attested with face verdicts (D-033, D-046). Every name, path, and data
set here is invented or synthetic.
"""

import contextlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    api,
    command,
    instance_transform,
    markers,
    policy,
    qc_store,
)
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.face_review import FaceReview
from pymedphys._dicom.deidentify.qc_attestation import Face, Outcome

from .test_deidentify_qc_face_verdicts import _released
from .test_deidentify_run import SENTINEL
from .test_deidentify_visual_features_option import (
    _attest,
    _codes,
    _sheeted,
    _with_written,
)

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

OPTION = policy.CLEAN_RECOGNIZABLE_VISUAL_FEATURES
CODE = "113102"
_CT = ("01-ct-1.dcm", "02-ct-2.dcm")
_DOSE = ("06-rtdose.dcm", "07-rtdose-review.dcm")
_STRUCTURE_SET = "04-rtstruct.dcm"
_PLAN = "05-rtplan.dcm"


@pytest.fixture(name="tmp_path")
def _short_tmp_path(tmp_path):
    """Give a base directory short enough for Windows' path limit.

    On Windows, a run refuses a release directory whose files' paths could
    exceed 259 characters, which pytest's own temporary directories do.
    """
    if os.name != "nt":
        yield tmp_path
        return
    short = Path(tempfile.mkdtemp(prefix="d"))
    yield short
    shutil.rmtree(short, ignore_errors=True)


@contextlib.contextmanager
def _enabling():
    """Enable the Basic Profile and the option, which no release enables yet."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(policy, "ENABLED_PRESETS", frozenset({"basic"}))
        patch.setattr(policy, "ENABLED_OPTIONS", frozenset({OPTION}))
        yield


@pytest.fixture(name="enabled")
def _enabled():
    with _enabling():
        yield


@pytest.fixture(name="built")
def _built(monkeypatch):
    """Record the face review that each transform that is built is given."""
    built = []
    real = instance_transform.InstanceTransform

    def recording(selected, key, *args, **kwargs):
        built.append(kwargs.get("face_review"))
        return real(selected, key, *args, **kwargs)

    monkeypatch.setattr(instance_transform, "InstanceTransform", recording)
    return built


def _deidentify(directory, **options):
    return api.deidentify(
        directory / "source",
        directory / "release",
        qc_pack=directory / "qc",
        **options,
    )


def _pack(directory, outcome=None):
    """A QC pack of five released instances in two series, attested with
    ``outcome`` where it is given, and if attested, its first series marked
    absent."""
    release = directory / "pack-release"
    release.mkdir(parents=True)
    instances = tuple(_with_written(_released(n), n) for n in range(5))
    pack = qc_store.write_qc_pack(
        _sheeted(instances), directory / "pack", release_directory=release
    ).parent
    if outcome is not None:
        faces = {0: Face.ABSENT} if outcome is Outcome.ATTESTED else {}
        _attest(pack, faces, outcome=outcome)
    return pack


# What the run is given.


@pytest.mark.usefixtures("enabled")
def test_a_run_under_the_option_needs_a_face_review(tmp_path, built):
    (tmp_path / "source").mkdir()

    with pytest.raises(api.DeidentifyError, match="needs a face review") as raised:
        _deidentify(tmp_path, options=[OPTION])

    assert raised.value.__cause__ is None
    assert built == []
    assert sorted(p.name for p in tmp_path.iterdir()) == ["source"]


@pytest.mark.usefixtures("enabled")
@pytest.mark.parametrize("options", [{}, {"options": []}, {"preset": "basic"}])
def test_a_face_review_without_the_option_is_refused_before_it_is_read(
    tmp_path, built, options
):
    # A path that names nothing, so that reading it would fail.
    with pytest.raises(ValueError, match=OPTION):
        _deidentify(tmp_path, face_review=tmp_path / SENTINEL, **options)

    assert built == []
    assert not any(tmp_path.iterdir())


def test_the_policy_is_checked_before_the_face_review(tmp_path, built):
    # No release enables the option yet, so the run is refused as not
    # enabled, whether or not it is given a face review.
    for options in ({}, {"face_review": tmp_path / SENTINEL}):
        with pytest.raises(api.DeidentifyError, match="not enabled"):
            _deidentify(tmp_path, options=[OPTION], **options)

    assert built == []
    assert not any(tmp_path.iterdir())


@pytest.mark.usefixtures("enabled")
@pytest.mark.parametrize(
    "problem, says",
    [
        ("missing", "holds no QC pack"),
        ("empty", "holds no QC pack"),
        ("not attested", "has not been attested"),
        ("rejected", "rejected it"),
    ],
)
def test_a_face_review_that_cannot_be_used_raises_naming_no_path(
    tmp_path, built, problem, says
):
    (tmp_path / "source").mkdir()
    holder = tmp_path / SENTINEL
    holder.mkdir()
    if problem == "missing":
        review = holder / "absent"
    elif problem == "empty":
        review = holder
    else:
        review = _pack(
            holder, None if problem == "not attested" else Outcome.REJECTED
        )
    before = sorted(tmp_path.rglob("*"))

    with pytest.raises(api.DeidentifyError) as raised:
        _deidentify(tmp_path, options=[OPTION], face_review=review)

    message = str(raised.value)
    assert message.startswith("the face review could not be read: ")
    assert says in message
    assert SENTINEL not in message and str(tmp_path) not in message
    assert raised.value.__cause__ is None and raised.value.__suppress_context__
    assert built == []
    assert sorted(tmp_path.rglob("*")) == before


@pytest.mark.usefixtures("enabled")
def test_the_transform_is_given_the_attested_packs_verdicts(
    tmp_path, monkeypatch, built
):
    calls = []
    monkeypatch.setattr(
        api.run, "run", lambda *args, **kwargs: calls.append((args, kwargs))
    )
    monkeypatch.setattr(api, "Deidentified", lambda result, counts: result)
    (tmp_path / "source").mkdir()
    pack = _pack(tmp_path / "reviewed")
    attestation = _attest(pack, {0: Face.ABSENT})

    _deidentify(tmp_path, options=[OPTION], face_review=pack)

    (review,) = built
    assert isinstance(review, FaceReview)
    assert review.reference == attestation.reference
    assert len(review.absent) == 3 and review.present == frozenset()
    ((args, kwargs),) = calls
    transform = args[2]
    assert kwargs["reporter"] is transform.reporter


# Two runs of the synthetic collection through the library: the first under
# the Basic Profile, whose pack a reviewer attests, and the second under the
# option, given that pack.


@pytest.fixture(name="second_run", scope="module")
def fixture_second_run():
    directory = Path(tempfile.mkdtemp(prefix="d"))
    try:
        with _enabling():
            yield _second_run(directory)
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _second_run(directory):
    corpus_module.write_corpus(corpus_module.build_corpus(), directory)
    source = directory / corpus_module.INSTANCES_DIRECTORY
    first = api.deidentify(
        source, directory / "r1", qc_pack=directory / "qc1", preset="basic"
    )
    pack = first.result.qc_pack.parent
    entries = json.loads(first.result.qc_pack.read_text("utf-8"))
    names = {e["position"]: Path(e["source"]).name for e in entries["instances"]}
    by_first = {names[s["positions"][0]]: s for s in entries["series"]}
    attestation = _attest(
        pack,
        {
            by_first[_CT[0]]["positions"][0]: Face.ABSENT,
            by_first[_STRUCTURE_SET]["positions"][0]: Face.ABSENT,
            by_first[_DOSE[0]]["positions"][0]: Face.PRESENT,
        },
    )
    second = api.deidentify(
        source,
        directory / "r2",
        qc_pack=directory / "qc2",
        options=[OPTION],
        face_review=pack,
    )
    outcomes = {
        Path(entry["source"]).name: (
            entry["disposition"],
            None
            if entry.get("output") is None
            else pydicom.dcmread(directory / "r2" / entry["output"]),
        )
        for entry in json.loads(second.result.qc_pack.read_text("utf-8"))[
            "instances"
        ]
    }
    report = json.loads((directory / "r2" / "release-report.json").read_text())
    return attestation, outcomes, report, second


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_the_library_releases_a_series_marked_absent_with_the_option(second_run):
    _, outcomes, _, _ = second_run

    for name in (*_CT, _STRUCTURE_SET, _PLAN):
        disposition, dataset = outcomes[name]
        assert disposition == "released", name
        assert dataset.RecognizableVisualFeatures == "NO"
        assert _codes(dataset)[-2:] == [markers.PROFILE_CODE, CODE]


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_the_library_holds_a_series_marked_present(second_run):
    _, outcomes, report, done = second_run

    for name in _DOSE:
        assert outcomes[name] == ("held-for-review", None), name
    held = {
        entry["code"]: entry["count"]
        for entry in report["held_for_review"]
        if entry["stage"] == "visual-features"
    }
    assert held["face-present"] == 2
    assert not done.released
    assert done.exit_status == command.EXIT_WITHHELD


def test_the_librarys_report_names_the_attested_pack(second_run):
    attestation, _, report, _ = second_run

    assert report["face_review"]["reference"] == attestation.reference
    assert report["policy"]["preset"] is None
    assert report["policy"]["options"] == [OPTION]
