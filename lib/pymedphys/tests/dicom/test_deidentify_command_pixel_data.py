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

"""The Clean Pixel Data Option in the command line's runs, and the library's.

A run under the option makes the text detector, and can be given a first
run's attested QC pack, whose redaction verdicts it applies, and the
custodian's reviewed region rules (D-033, D-037, D-048). Every file is
synthetic, every manufacturer and model name invented, and every detector a
stand-in that gives fixed regions.
"""

import io
import json
import os
import shutil
import tempfile
from pathlib import Path

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    api,
    command,
    instance_transform,
    policy,
    qc_store,
    run,
    run_report,
)
from pymedphys._dicom.deidentify.pixel_region_rules import PixelRegionRules, RuleKey
from pymedphys._dicom.deidentify.qc_attestation import Redaction, RedactionVerdict
from pymedphys._dicom.deidentify.text_detection import TextBox, TextDetectionError

from . import _synthetic_references as synthetic
from .test_deidentify_command import _parsed_call
from .test_deidentify_pixel_cleaning import Finder, _ct, _frame, _inside
from .test_deidentify_redaction_review import _attest, _codes, _write
from .test_deidentify_run import SENTINEL

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

CLEAN_PIXEL_DATA = policy.CLEAN_PIXEL_DATA
DEVICE_IDENTITY = "retain_device_identity"
_OPTION = ("--option", CLEAN_PIXEL_DATA)
MANUFACTURER, MODEL = "Acme Imaging", "Scanner 9"
# The bottom two rows of a frame of six rows and eight columns, where the
# invented scanner burns its text.
BAND = TextBox(4, 0, 6, 8)
RULE = RuleKey(synthetic.CT_IMAGE_STORAGE, MANUFACTURER, MODEL, 6, 8)


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


@pytest.fixture(name="enabled")
def _enabled(monkeypatch):
    """Enable the Basic Profile and two options, which no release enables yet."""
    monkeypatch.setattr(policy, "ENABLED_PRESETS", frozenset({"basic"}))
    monkeypatch.setattr(
        policy, "ENABLED_OPTIONS", frozenset({CLEAN_PIXEL_DATA, DEVICE_IDENTITY})
    )


@pytest.fixture(name="detectors")
def _detectors(monkeypatch):
    """Make a stand-in finder in place of each text detector, and list them."""
    made = []

    def detector():
        made.append(Finder())
        return made[-1]

    monkeypatch.setattr(command, "TextDetector", detector)
    return made


@pytest.fixture(name="built")
def _built(monkeypatch):
    """Record what each transform that is built is given for pixel data."""
    built = []
    real = instance_transform.InstanceTransform

    def recording(selected, key, *args, **kwargs):
        built.append(
            {
                name: kwargs.get(name)
                for name in ("finder", "redaction_review", "pixel_region_rules")
            }
        )
        return real(selected, key, *args, **kwargs)

    monkeypatch.setattr(instance_transform, "InstanceTransform", recording)
    return built


def _store(path, *boxes):
    path.parent.mkdir(exist_ok=True)
    rules = PixelRegionRules.open(path)
    rules.record(RULE, boxes or (BAND,))
    rules.save()
    return rules


def _image(number):
    """A CT slice of the invented scanner, with its own stored values."""
    dataset = _ct(_frame(start=100 * (number + 1)))
    dataset.SOPInstanceUID = synthetic.CT_SLICES[number]
    dataset.InstanceNumber = number + 1
    dataset.Manufacturer = MANUFACTURER
    dataset.ManufacturerModelName = MODEL
    return dataset


def _images(count=2):
    return {f"{n}.dcm": synthetic.written(_image(n)) for n in range(count)}


def _main(tmp_path, run_name, *options):
    stdout, stderr = io.StringIO(), io.StringIO()
    directory = tmp_path / run_name
    directory.mkdir()
    status = command.main(
        [
            str(tmp_path / "source"),
            str(directory / "release"),
            "--qc-pack",
            str(directory / "qc"),
            *options,
        ],
        stdout=stdout,
        stderr=stderr,
    )
    return status, stdout.getvalue(), stderr.getvalue()


def _instances(pack_directory):
    document = json.loads((pack_directory / qc_store.PACK_FILE).read_text("utf-8"))
    return {Path(entry["source"]).name: entry for entry in document["instances"]}


# The text detector.


@pytest.mark.usefixtures("enabled")
def test_a_run_under_the_option_makes_the_text_detector(
    tmp_path, monkeypatch, detectors, built
):
    status, _, err, calls = _parsed_call(tmp_path, monkeypatch, *_OPTION)

    assert (status, err) == (command.EXIT_RELEASED, "")
    (finder,) = detectors
    assert built == [
        {"finder": finder, "redaction_review": None, "pixel_region_rules": None}
    ]
    (call,) = calls
    assert call["reporter"] is call["transform"].reporter


@pytest.mark.usefixtures("enabled")
def test_a_run_without_the_option_makes_no_text_detector(
    tmp_path, monkeypatch, detectors, built
):
    status, _, err, _ = _parsed_call(tmp_path, monkeypatch, "--option", DEVICE_IDENTITY)

    assert (status, err) == (command.EXIT_RELEASED, "")
    assert detectors == []
    assert built == [
        {"finder": None, "redaction_review": None, "pixel_region_rules": None}
    ]


@pytest.mark.usefixtures("enabled")
def test_a_detector_that_cannot_be_made_exits_three_saying_why(
    tmp_path, monkeypatch, built
):
    def detector():
        raise TextDetectionError('text detection needs ONNX Runtime: install "x"')

    monkeypatch.setattr(command, "TextDetector", detector)

    status, out, err, calls = _parsed_call(tmp_path, monkeypatch, *_OPTION)

    assert status == command.EXIT_NOT_RUN
    assert (out, calls, built) == ("", [], [])
    assert err == (
        "error: the text detector could not be made: text detection needs ONNX "
        'Runtime: install "x"\n'
    )


@pytest.mark.usefixtures("enabled")
def test_a_model_that_cannot_be_downloaded_exits_three_naming_no_path(
    tmp_path, monkeypatch, built
):
    def detector():
        raise OSError(SENTINEL)

    monkeypatch.setattr(command, "TextDetector", detector)

    status, _, err, calls = _parsed_call(tmp_path, monkeypatch, *_OPTION)

    assert status == command.EXIT_NOT_RUN
    assert (calls, built) == ([], [])
    assert err.startswith("error: the text detector's model could not be")
    assert SENTINEL not in err


def test_the_option_not_enabled_exits_three_before_anything_is_loaded(
    tmp_path, monkeypatch, detectors
):
    monkeypatch.setattr(policy, "ENABLED_PRESETS", frozenset({"basic"}))
    path = tmp_path / "custodian" / "rules.json"
    _store(path)

    status, _, err, calls = _parsed_call(
        tmp_path,
        monkeypatch,
        *_OPTION,
        "--region-rules",
        str(path),
        "--redaction-review",
        str(tmp_path / "missing"),
    )

    assert status == command.EXIT_NOT_RUN
    assert "not enabled" in err
    assert (detectors, calls) == ([], [])


# Region rules.


@pytest.mark.usefixtures("enabled", "detectors")
def test_the_custodians_region_rules_are_used(tmp_path, monkeypatch, built):
    path = tmp_path / "custodian" / "rules.json"
    _store(path)

    status, _, err, _ = _parsed_call(
        tmp_path, monkeypatch, *_OPTION, "--region-rules", str(path)
    )

    assert (status, err) == (command.EXIT_RELEASED, "")
    ((given,),) = [[each["pixel_region_rules"]] for each in built]
    assert given.get(RULE) == (BAND,)


@pytest.mark.usefixtures("enabled")
@pytest.mark.parametrize(
    "where",
    ["custodian", "release", "qc", "source", "malformed"],
    ids=lambda where: where,
)
def test_region_rules_that_cannot_be_used_exit_three_naming_no_path(
    tmp_path, monkeypatch, detectors, built, where
):
    path = tmp_path / where / SENTINEL
    if where == "custodian":
        path = tmp_path / where / "missing.json"
    elif where == "malformed":
        path.parent.mkdir()
        path.write_text(SENTINEL, "utf-8")
    else:
        _store(path)

    status, _, err, calls = _parsed_call(
        tmp_path, monkeypatch, *_OPTION, "--region-rules", str(path)
    )

    assert status == command.EXIT_NOT_RUN
    expected = "do not exist" if where == "custodian" else "could not be used"
    assert err.startswith("error: the region rules") and expected in err
    assert SENTINEL not in err and str(tmp_path) not in err
    assert (detectors, built, calls) == ([], [], [])


@pytest.mark.usefixtures("enabled", "detectors")
def test_the_command_blacks_out_a_rules_regions_and_holds_the_image(tmp_path):
    _write(tmp_path / "source", _images(1))
    path = tmp_path / "custodian" / "rules.json"
    _store(path)

    status, _, err = _main(tmp_path, "first", *_OPTION, "--region-rules", str(path))

    assert status == command.EXIT_WITHHELD, err
    (entry,) = _instances(tmp_path / "first" / "qc").values()
    assert entry["disposition"] == run.Status.HELD_FOR_REVIEW.value
    document = json.loads(
        (tmp_path / "first" / "qc" / qc_store.PACK_FILE).read_text("utf-8")
    )
    (redaction,) = document["redactions"]
    assert redaction["rule_boxes"] == [[4, 0, 6, 8]]
    assert redaction["regions"] == [{"frame": 0, "boxes": [[1, 2, 3, 5], [4, 0, 6, 8]]}]


# Redaction verdicts.


@pytest.mark.deid_requirement("PS3.15-E.3.1-01", "PS3.15-E.3.1-02")
@pytest.mark.usefixtures("enabled", "detectors")
def test_a_second_run_given_the_attested_pack_releases_the_reviewed_images(
    tmp_path,
):
    _write(tmp_path / "source", _images())

    first, _, err = _main(tmp_path, "first", *_OPTION)

    assert first == command.EXIT_WITHHELD, err
    pack = tmp_path / "first" / "qc"
    positions = {name: entry["position"] for name, entry in _instances(pack).items()}
    _attest(
        pack,
        (
            RedactionVerdict(positions["0.dcm"], Redaction.ACCEPTED),
            RedactionVerdict(positions["1.dcm"], Redaction.REJECTED),
        ),
    )

    second, out, err = _main(
        tmp_path, "second", *_OPTION, "--redaction-review", str(pack)
    )

    assert second == command.EXIT_WITHHELD, err
    assert str(pack) not in out + err
    entries = _instances(tmp_path / "second" / "qc")
    assert entries["0.dcm"]["disposition"] == run.Status.RELEASED.value
    assert entries["1.dcm"]["disposition"] == run.Status.SEQUESTERED.value
    written = pydicom.dcmread(
        tmp_path / "second" / "release" / entries["0.dcm"]["output"]
    )
    frame = _frame(start=100)
    pixels = pydicom.pixels.pixel_array(written)
    assert np.all(pixels[_inside(frame.shape)] == frame.min())
    assert np.array_equal(pixels[~_inside(frame.shape)], frame[~_inside(frame.shape)])
    assert written.BurnedInAnnotation == "NO"
    assert "113101" in _codes(written)
    report = json.loads(
        (tmp_path / "second" / "release" / run_report.RELEASE_REPORT).read_text("utf-8")
    )
    reference = json.loads((pack / qc_store.PACK_FILE).read_text("utf-8"))
    assert report["redaction_review"] == {"reference": reference["reference"]}


@pytest.mark.usefixtures("enabled")
@pytest.mark.parametrize("problem", ["no pack", "not attested"])
def test_a_redaction_review_that_cannot_be_read_exits_three_naming_no_path(
    tmp_path, monkeypatch, detectors, built, problem
):
    pack = tmp_path / "reviewed" / SENTINEL
    pack.mkdir(parents=True)
    if problem == "not attested":
        _write(tmp_path / "source", _images(1))
        assert _main(tmp_path, "first", *_OPTION)[0] == command.EXIT_WITHHELD
        shutil.copytree(tmp_path / "first" / "qc", pack, dirs_exist_ok=True)
        detectors.clear()
        built.clear()

    status, _, err, calls = _parsed_call(
        tmp_path, monkeypatch, *_OPTION, "--redaction-review", str(pack)
    )

    assert status == command.EXIT_NOT_RUN
    assert err.startswith("error: the redaction review could not be read")
    if problem == "not attested":
        assert "the QC pack has not been attested" in err
    assert SENTINEL not in err and str(tmp_path) not in err
    assert (detectors, built, calls) == ([], [], [])


# Arguments that need the option.


@pytest.mark.parametrize(
    "option",
    [("--redaction-review", "x"), ("--region-rules", "x")],
    ids=lambda option: option[0],
)
@pytest.mark.parametrize(
    "policy_arguments",
    [(), ("--preset", "basic-clean-descriptors"), ("--option", DEVICE_IDENTITY)],
    ids=["default", "preset", "options"],
)
def test_pixel_data_arguments_without_the_option_are_a_usage_error(
    tmp_path, monkeypatch, option, policy_arguments
):
    status, out, err, calls = _parsed_call(
        tmp_path, monkeypatch, *policy_arguments, *option
    )

    assert status == command.EXIT_USAGE
    assert (out, calls) == ("", [])
    assert err.startswith("error: ") and "--option clean_pixel_data" in err
    assert not any(tmp_path.iterdir())


def test_the_option_takes_the_pixel_data_arguments():
    assert command.pixel_data_options_apply(None, [CLEAN_PIXEL_DATA])
    assert not command.pixel_data_options_apply(None, [DEVICE_IDENTITY])
    assert not command.pixel_data_options_apply(None)
    assert not command.pixel_data_options_apply("basic-clean-descriptors")


def test_the_help_names_the_pixel_data_arguments(capsys):
    with pytest.raises(SystemExit):
        command.main(["--help"])

    text = " ".join(capsys.readouterr().out.split())
    assert "--redaction-review DIRECTORY" in text
    assert "--region-rules FILE" in text


# The library, which builds its transform as the command does.


@pytest.mark.usefixtures("enabled")
def test_the_library_makes_the_text_detector_under_the_option(tmp_path, detectors):
    _write(tmp_path / "source", _images(1))

    result = api.deidentify(
        tmp_path / "source",
        tmp_path / "release",
        qc_pack=tmp_path / "qc",
        options=[CLEAN_PIXEL_DATA],
    )

    assert len(detectors) == 1
    assert [outcome.status for outcome in result.result.outcomes] == [
        run.Status.HELD_FOR_REVIEW
    ]
