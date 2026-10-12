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

"""Custom option sets chosen per run, by the library and the command line (D-033)."""

import dataclasses
import io
import json
import os
import shutil
import tempfile
from pathlib import Path

from pymedphys._imports import pytest

from pymedphys._nomenclature import tg263

from pymedphys._dicom.deidentify import (
    api,
    command,
    instance_transform,
    policy,
    roi_names,
    run_report,
    standard,
)
from pymedphys._dicom.deidentify.keys import DeidKey

from . import _synthetic_references as synthetic
from .test_deidentify_api import _NOMENCLATURE
from .test_deidentify_command import _parsed_call
from .test_deidentify_run import SENTINEL, Gate, Transform, _write

CLEAN_DESCRIPTORS = "clean_descriptors"
DEVICE_IDENTITY = "retain_device_identity"
FULL_DATES = "retain_longitudinal_full_dates"
KEY = DeidKey(bytes(range(32)))


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
        policy, "ENABLED_OPTIONS", frozenset({DEVICE_IDENTITY, CLEAN_DESCRIPTORS})
    )


@pytest.fixture(name="edition")
def _edition(monkeypatch):
    """Serve an invented edition, published for the test, in place of TG-263's."""
    entries = [dataclasses.asdict(s) for s in _NOMENCLATURE.structures]
    monkeypatch.setitem(
        roi_names.PUBLISHED_TG263, "TG263 vInvented", tg263.content_sha256(entries)
    )
    loads = []

    def load(*args, **kwargs):
        loads.append((args, kwargs))
        return _NOMENCLATURE

    monkeypatch.setattr(command.tg263_published, "load", load)
    return loads


@pytest.fixture(name="built")
def _built(monkeypatch):
    """Record the policy and the cleaning of each transform that is built."""
    built = []
    real = instance_transform.InstanceTransform

    def recording(selected, key, *args, cleaning=None, **kwargs):
        built.append((selected, cleaning))
        return real(selected, key, *args, cleaning=cleaning, **kwargs)

    monkeypatch.setattr(instance_transform, "InstanceTransform", recording)
    return built


def _deidentify(tmp_path, **arguments):
    return api.deidentify(
        tmp_path / "source", tmp_path / "release", qc_pack=tmp_path / "qc", **arguments
    )


@pytest.mark.usefixtures("enabled")
def test_transform_for_applies_an_enabled_custom_option_set(built):
    instance_transform.transform_for(key=KEY, options=[DEVICE_IDENTITY])

    ((selected, cleaning),) = built
    assert (selected.preset, selected.options, cleaning) == (
        None,
        (DEVICE_IDENTITY,),
        None,
    )
    assert selected.enabled


def test_an_enabled_option_that_the_engine_does_not_apply_is_still_refused(
    monkeypatch,
):
    # Enabling an option never overrides the engine's own refusal (D-011).
    monkeypatch.setattr(policy, "ENABLED_PRESETS", frozenset({"basic"}))
    monkeypatch.setattr(policy, "ENABLED_OPTIONS", frozenset({FULL_DATES}))

    assert policy.select_policy(options=[FULL_DATES]).enabled
    with pytest.raises(
        policy.PolicyError,
        match=f"^the engine does not yet apply the option {FULL_DATES},",
    ):
        instance_transform.transform_for(key=KEY, options=[FULL_DATES])


@pytest.mark.usefixtures("enabled")
def test_the_command_builds_the_transform_of_its_options(tmp_path, monkeypatch, built):
    status, _, err, calls = _parsed_call(
        tmp_path, monkeypatch, "--option", DEVICE_IDENTITY
    )

    assert (status, err) == (command.EXIT_RELEASED, "")
    ((selected, cleaning),) = built
    assert (selected.preset, selected.options, cleaning) == (
        None,
        (DEVICE_IDENTITY,),
        None,
    )
    (call,) = calls
    assert call["reporter"] is call["transform"].reporter


@pytest.mark.usefixtures("enabled", "edition")
def test_the_command_cleans_roi_names_under_options_with_clean_descriptors(
    tmp_path, monkeypatch, built
):
    status, _, err, _ = _parsed_call(
        tmp_path,
        monkeypatch,
        "--option",
        CLEAN_DESCRIPTORS,
        "--option",
        DEVICE_IDENTITY,
        "--empty-held-roi-names",
    )

    assert (status, err) == (command.EXIT_RELEASED, "")
    ((selected, cleaning),) = built
    assert selected.options == (DEVICE_IDENTITY, CLEAN_DESCRIPTORS)
    assert cleaning is not None and cleaning.empty_held


@pytest.mark.usefixtures("enabled")
def test_roi_name_options_with_options_without_clean_descriptors_are_a_usage_error(
    tmp_path, monkeypatch
):
    status, out, err, calls = _parsed_call(
        tmp_path, monkeypatch, "--option", DEVICE_IDENTITY, "--empty-held-roi-names"
    )

    assert status == command.EXIT_USAGE
    assert (out, calls) == ("", [])
    assert err.startswith("error: ") and "--option clean_descriptors" in err
    assert not any(tmp_path.iterdir())


@pytest.mark.parametrize(
    "arguments",
    [("--preset", "basic", "--option", CLEAN_DESCRIPTORS), ("--option", SENTINEL)],
    ids=["with-a-preset", "unknown"],
)
def test_options_with_a_preset_or_unknown_are_a_usage_error(capsys, arguments):
    with pytest.raises(SystemExit) as raised:
        command.main(["in", "out", "--qc-pack", "qc", *arguments])

    captured = capsys.readouterr()
    assert raised.value.code == command.EXIT_USAGE
    assert "error: the arguments could not be parsed" in captured.err
    assert SENTINEL not in captured.out + captured.err


def test_options_not_enabled_exit_three_before_anything_is_loaded(
    tmp_path, monkeypatch, edition
):
    # No release enables an option yet.
    monkeypatch.setattr(policy, "ENABLED_PRESETS", frozenset({"basic"}))

    status, out, err, calls = _parsed_call(
        tmp_path, monkeypatch, "--option", CLEAN_DESCRIPTORS, "--empty-held-roi-names"
    )

    assert status == command.EXIT_NOT_RUN
    assert (out, calls, edition) == ("", [], [])
    assert err == (
        "error: the custom option set is not enabled: the behaviour of the option "
        "clean_descriptors is not yet implemented and validated; no option is "
        "enabled yet\n"
    )
    assert not any(tmp_path.iterdir())


def test_the_help_names_every_option(capsys):
    with pytest.raises(SystemExit) as raised:
        command.main(["--help"], transform=Transform(), gate=Gate())

    assert raised.value.code == 0
    text = " ".join(capsys.readouterr().out.split())
    assert "--option OPTION" in text
    for option in standard.ALL_OPTIONS:
        assert option in text


@pytest.mark.usefixtures("enabled", "edition")
def test_the_command_runs_a_custom_option_set_end_to_end(tmp_path):
    _write(tmp_path / "source", synthetic.collection())
    stdout, stderr = io.StringIO(), io.StringIO()

    status = command.main(
        [
            str(tmp_path / "source"),
            str(tmp_path / "release"),
            "--qc-pack",
            str(tmp_path / "qc"),
            "--option",
            CLEAN_DESCRIPTORS,
            "--empty-held-roi-names",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert status == command.EXIT_RELEASED, stdout.getvalue() + stderr.getvalue()
    release = tmp_path / "release"
    report = json.loads(
        (release / run_report.RELEASE_REPORT).read_text(encoding="utf-8")
    )
    assert report["policy"]["preset"] is None
    assert report["policy"]["options"] == [CLEAN_DESCRIPTORS]
    statement = (release / run_report.CONFORMANCE_STATEMENT).read_text(encoding="utf-8")
    assert statement.startswith(
        "# DICOM PS3.15 conformance statement for a custom option set\n"
    )


def test_a_preset_and_options_together_are_refused(tmp_path):
    with pytest.raises(ValueError, match="^give a preset or options, not both$"):
        _deidentify(tmp_path, preset="basic", options=[CLEAN_DESCRIPTORS])

    assert not any(tmp_path.iterdir())


def test_options_as_a_single_string_are_refused(tmp_path):
    with pytest.raises(TypeError, match="not a single string"):
        _deidentify(tmp_path, options=CLEAN_DESCRIPTORS)

    assert not any(tmp_path.iterdir())


def test_options_not_enabled_raise_before_anything_is_created(
    tmp_path, monkeypatch, edition
):
    monkeypatch.setattr(policy, "ENABLED_PRESETS", frozenset({"basic"}))

    with pytest.raises(
        api.DeidentifyError, match="^the custom option set is not enabled: "
    ):
        _deidentify(tmp_path, options=[CLEAN_DESCRIPTORS], empty_held_roi_names=True)

    assert edition == []
    assert not any(tmp_path.iterdir())


@pytest.mark.usefixtures("enabled")
def test_roi_name_options_need_clean_descriptors_among_the_options(tmp_path):
    with pytest.raises(ValueError, match="options that include clean_descriptors"):
        _deidentify(tmp_path, options=[DEVICE_IDENTITY], empty_held_roi_names=True)

    assert not any(tmp_path.iterdir())


@pytest.mark.usefixtures("enabled", "edition")
def test_options_given_as_an_iterator_are_read_once(tmp_path, built):
    # The check of the ROI name options and the run see the same options.
    _write(tmp_path / "source", synthetic.collection())

    done = _deidentify(
        tmp_path, options=iter([CLEAN_DESCRIPTORS]), empty_held_roi_names=True
    )

    assert done.released, done.summary()
    ((selected, cleaning),) = built
    assert selected.options == (CLEAN_DESCRIPTORS,)
    assert cleaning is not None


@pytest.mark.usefixtures("enabled", "edition")
def test_a_custom_option_set_releases_as_the_preset_of_its_options(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        policy, "ENABLED_PRESETS", frozenset({"basic", "basic-clean-descriptors"})
    )
    _write(tmp_path / "source", synthetic.collection())
    selections = {
        "preset": {"preset": "basic-clean-descriptors"},
        "options": {"options": [CLEAN_DESCRIPTORS]},
    }

    done = {
        name: api.deidentify(
            tmp_path / "source",
            tmp_path / name,
            qc_pack=tmp_path / f"qc-{name}",
            empty_held_roi_names=True,
            **selection,
        )
        for name, selection in selections.items()
    }

    assert done["options"].released, done["options"].summary()
    statuses = {
        name: [outcome.status for outcome in deidentified.result.outcomes]
        for name, deidentified in done.items()
    }
    assert statuses["options"] == statuses["preset"]
    reported = {
        name: json.loads(
            (tmp_path / name / run_report.RELEASE_REPORT).read_text(encoding="utf-8")
        )
        for name in done
    }
    assert reported["options"]["policy"] == {
        **reported["preset"]["policy"],
        "preset": None,
    }
