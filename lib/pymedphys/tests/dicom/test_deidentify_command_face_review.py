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

"""The Clean Recognizable Visual Features Option in the command line's runs.

A run under the option is given, with ``--face-review``, the QC pack of an
earlier run of the same files, attested with face verdicts (D-033, D-046).
Every name, path, and data set here is invented or synthetic.
"""

import contextlib
import io
import json
import os
import shutil
import tempfile
from pathlib import Path

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    command,
    instance_transform,
    markers,
    policy,
    qc_store,
)
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.face_review import FaceReview
from pymedphys._dicom.deidentify.qc_attestation import Face, Outcome

from .test_deidentify_api_face_review import (
    _CT,
    _DOSE,
    _PLAN,
    _STRUCTURE_SET,
    _pack,
)
from .test_deidentify_command import _parsed_call
from .test_deidentify_run import SENTINEL
from .test_deidentify_visual_features_option import _attest, _codes

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

OPTION = policy.CLEAN_RECOGNIZABLE_VISUAL_FEATURES
CODE = "113102"
DEVICE_IDENTITY = "retain_device_identity"
_OPTION = ("--option", OPTION)


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
    """Enable the Basic Profile and two options, which no release enables yet."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(policy, "ENABLED_PRESETS", frozenset({"basic"}))
        patch.setattr(policy, "ENABLED_OPTIONS", frozenset({OPTION, DEVICE_IDENTITY}))
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


def _main(source, directory, *options):
    stdout, stderr = io.StringIO(), io.StringIO()
    directory.mkdir()
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


# What the run is given.


@pytest.mark.usefixtures("enabled")
def test_the_transform_is_given_the_attested_packs_verdicts(
    tmp_path, monkeypatch, built
):
    pack = _pack(tmp_path / "reviewed")
    attestation = _attest(pack, {0: Face.ABSENT})

    status, out, err, calls = _parsed_call(
        tmp_path, monkeypatch, *_OPTION, "--face-review", str(pack)
    )

    assert (status, err) == (command.EXIT_RELEASED, "")
    assert str(pack) not in out
    (review,) = built
    assert isinstance(review, FaceReview)
    assert review.reference == attestation.reference
    assert len(review.absent) == 3 and review.present == frozenset()
    (call,) = calls
    assert call["reporter"] is call["transform"].reporter


@pytest.mark.usefixtures("enabled")
def test_a_run_under_the_option_without_a_face_review_exits_three(
    tmp_path, monkeypatch, built
):
    status, out, err, calls = _parsed_call(tmp_path, monkeypatch, *_OPTION)

    assert status == command.EXIT_NOT_RUN
    assert (out, calls, built) == ("", [], [])
    assert err.startswith("error: a run under Clean Recognizable Visual Features")
    assert "needs a face review" in err
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
def test_a_face_review_that_cannot_be_used_exits_three_naming_no_path(
    tmp_path, monkeypatch, built, problem, says
):
    holder = tmp_path / SENTINEL
    holder.mkdir()
    if problem == "missing":
        review = holder / "absent"
    elif problem == "empty":
        review = holder
    else:
        review = _pack(holder, None if problem == "not attested" else Outcome.REJECTED)
    before = sorted(tmp_path.rglob("*"))

    status, out, err, calls = _parsed_call(
        tmp_path, monkeypatch, *_OPTION, "--face-review", str(review)
    )

    assert status == command.EXIT_NOT_RUN
    assert (out, calls, built) == ("", [], [])
    assert err.startswith("error: the face review could not be read: ")
    assert says in err
    assert SENTINEL not in err and str(tmp_path) not in err
    assert sorted(tmp_path.rglob("*")) == before


def test_the_option_not_enabled_exits_three_before_the_face_review_is_read(
    tmp_path, monkeypatch, built
):
    monkeypatch.setattr(policy, "ENABLED_PRESETS", frozenset({"basic"}))

    # A path that names nothing, so that reading it would fail otherwise.
    status, _, err, calls = _parsed_call(
        tmp_path, monkeypatch, *_OPTION, "--face-review", str(tmp_path / SENTINEL)
    )

    assert status == command.EXIT_NOT_RUN
    assert "not enabled" in err and "face review" not in err
    assert (calls, built) == ([], [])


# The argument, which needs the option.


@pytest.mark.parametrize(
    "policy_arguments",
    [(), ("--preset", "basic-clean-descriptors"), ("--option", DEVICE_IDENTITY)],
    ids=["default", "preset", "options"],
)
def test_a_face_review_without_the_option_is_a_usage_error(
    tmp_path, monkeypatch, policy_arguments
):
    status, out, err, calls = _parsed_call(
        tmp_path,
        monkeypatch,
        *policy_arguments,
        "--face-review",
        str(tmp_path / SENTINEL),
    )

    assert status == command.EXIT_USAGE
    assert (out, calls) == ("", [])
    assert err == (
        "error: --face-review applies only under Clean Recognizable Visual "
        "Features: with --option clean_recognizable_visual_features\n"
    )
    assert not any(tmp_path.iterdir())


def test_the_help_names_the_face_review_argument(capsys):
    with pytest.raises(SystemExit):
        command.main(["--help"])

    text = " ".join(capsys.readouterr().out.split())
    assert "--face-review DIRECTORY" in text
    assert "under Clean Recognizable Visual Features" in text


# Two runs of the synthetic collection through the command: the first under
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


def _instances(pack):
    return json.loads((pack / qc_store.PACK_FILE).read_text("utf-8"))


def _second_run(directory):
    corpus_module.write_corpus(corpus_module.build_corpus(), directory)
    source = directory / corpus_module.INSTANCES_DIRECTORY
    first, _, err = _main(source, directory / "first", "--preset", "basic")
    assert first == command.EXIT_WITHHELD, err
    pack = directory / "first" / "qc"
    entries = _instances(pack)
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
    status, out, err = _main(
        source, directory / "second", *_OPTION, "--face-review", str(pack)
    )
    release = directory / "second" / "release"
    outcomes = {
        Path(entry["source"]).name: (
            entry["disposition"],
            None
            if entry.get("output") is None
            else pydicom.dcmread(release / entry["output"]),
        )
        for entry in _instances(directory / "second" / "qc")["instances"]
    }
    report = json.loads((release / "release-report.json").read_text("utf-8"))
    return attestation, outcomes, report, (status, out, err, str(pack))


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_the_command_releases_a_series_marked_absent_with_the_option(second_run):
    _, outcomes, _, _ = second_run

    for name in (*_CT, _STRUCTURE_SET, _PLAN):
        disposition, dataset = outcomes[name]
        assert disposition == "released", name
        assert dataset.RecognizableVisualFeatures == "NO"
        assert _codes(dataset)[-2:] == [markers.PROFILE_CODE, CODE]


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_the_command_holds_a_series_marked_present(second_run):
    _, outcomes, report, (status, _, err, _) = second_run

    for name in _DOSE:
        assert outcomes[name] == ("held-for-review", None), name
    held = {
        entry["code"]: entry["count"]
        for entry in report["held_for_review"]
        if entry["stage"] == "visual-features"
    }
    assert held["face-present"] == 2
    assert status == command.EXIT_WITHHELD, err


def test_the_commands_report_names_the_attested_pack_and_its_output_does_not(
    second_run,
):
    attestation, _, report, (_, out, err, pack) = second_run

    assert report["face_review"]["reference"] == attestation.reference
    assert report["policy"]["preset"] is None
    assert report["policy"]["options"] == [OPTION]
    assert pack not in out + err
