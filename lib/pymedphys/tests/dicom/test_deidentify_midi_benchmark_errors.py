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

"""Tests of the MIDI benchmark's value-free description of internal errors (D-018).

Every DICOM file is synthetic, and every error is raised by the tests.
"""

import json

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import midi_benchmark as benchmark
from pymedphys._dicom.deidentify import midi_benchmark_errors as errors

from . import _synthetic_references as synthetic
from .test_deidentify_midi_benchmark import _benchmark_key, _source

# A run needs a base directory short enough for Windows' output path limit.
from .test_deidentify_run import (  # noqa: F401  # pylint: disable = unused-import
    _short_tmp_path,
)

SECRET = "SYNTHETIC-SECRET-VALUE"


def _raising(*_):
    raise ValueError(SECRET)


def test_an_error_is_counted_by_kind_and_raised_again():
    recorder = errors.ErrorRecorder()
    transform = recorder.transform(_raising)
    data = synthetic.written(synthetic.collection()[0])

    for _ in range(2):
        with pytest.raises(ValueError, match=SECRET):
            transform(data, None)

    (record,) = recorder.records()
    assert record["stage"] == "transform"
    assert record["exception"] == "builtins.ValueError"
    assert record["raised_at"].startswith(
        "pymedphys/tests/dicom/test_deidentify_midi_benchmark_errors.py:"
    )
    assert record["raised_at"].endswith(" in _raising")
    assert record["pymedphys_frame"] == record["raised_at"]
    assert record["sop_class"] == "CT Image Storage"
    assert record["times"] == 2
    assert SECRET not in json.dumps(record)


def test_a_gate_error_names_an_unreadable_file_as_such():
    recorder = errors.ErrorRecorder()
    with pytest.raises(ValueError):
        recorder.gate(_raising)(b"not DICOM", None, ())
    (record,) = recorder.records()
    assert (record["stage"], record["sop_class"], record["transfer_syntax"]) == (
        "gate",
        "unreadable",
        "unreadable",
    )


def test_a_benchmark_reports_its_internal_errors_without_a_value(tmp_path, monkeypatch):
    def raising(self, data, record):
        raise RuntimeError(SECRET)

    monkeypatch.setattr(benchmark.InstanceTransform, "__call__", raising)
    result = benchmark.run_benchmark(
        _source(tmp_path), _benchmark_key(tmp_path), tmp_path / "work"
    )

    found = result.document["coverage"]["internal_errors"]
    assert {row["exception"] for row in found} == {"builtins.RuntimeError"}
    assert {row["stage"] for row in found} == {"transform"}
    assert "CT Image Storage" in {row["sop_class"] for row in found}
    assert result.document["coverage"]["withheld_reasons"]["internal-error"] >= 1
    markdown = result.markdown()
    assert "Internal errors, which withhold an instance" in markdown
    assert SECRET not in markdown + result.json()
