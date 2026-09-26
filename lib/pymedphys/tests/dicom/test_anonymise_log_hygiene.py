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

"""The legacy de-identification code must not disclose values or paths.

``pymedphys.dicom.anonymise`` and experimental pseudonymisation are being
replaced, but until they are removed they must not write source DICOM values
or original file paths to logs or the standard streams (decision D-020 in
``docs/contrib/info/deidentification-design.md``). Each test plants canary
strings in DICOM values and in file and directory names, captures stdout,
stderr, and the log records that reach the root logger with its level set to
DEBUG, and checks that no canary appears. A logger with its own level
contributes only records at or above it: pydicom's logger stays at WARNING.
One strict expected failure documents a channel that remains: pydicom quotes
invalid values in its validation messages.
"""

import io
import logging
import pathlib
import warnings

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.anonymise import api as anonymise_api
from pymedphys._dicom.anonymise import core as anonymise_core
from pymedphys._experimental import pseudonymisation
from pymedphys._experimental.pseudonymisation import strategy as pseudo_strategy
from pymedphys.cli import define_parser

RT_PLAN_STORAGE = "1.2.840.10008.5.1.4.1.1.481.5"

CANARY_NAME = "ZZCANARYFAMILY^ZZCANARYGIVEN"
CANARY_ID = "ZZCANARYID0451"
# The legacy tools keep UIDs and name their output files after the SOP
# Instance UID, so printing an output path would disclose this value.
CANARY_UID = "1.2.826.0.1.3680043.10.1234.987654321987"
CANARY_DIR = "ZZCANARYDIR"
CANARY_OUTPUT_DIR = "ZZCANARYOUTPUT"
CANARIES = ("ZZCANARY", CANARY_UID)


def _canary_dataset(sop_instance_uid=CANARY_UID):
    ds = pydicom.Dataset()
    ds.PatientName = CANARY_NAME
    ds.PatientID = CANARY_ID
    ds.SOPClassUID = RT_PLAN_STORAGE
    ds.SOPInstanceUID = sop_instance_uid
    ds.StudyInstanceUID = "1.2.826.0.1.3680043.10.1234.1"
    ds.SeriesInstanceUID = "1.2.826.0.1.3680043.10.1234.2"
    ds.Modality = "RTPLAN"

    ds.file_meta = pydicom.dataset.FileMetaDataset()
    ds.file_meta.MediaStorageSOPClassUID = ds.SOPClassUID
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    ds.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
    return ds


def _write_canary_file(path, sop_instance_uid=CANARY_UID):
    path.parent.mkdir(parents=True, exist_ok=True)
    pydicom.dcmwrite(path, _canary_dataset(sop_instance_uid), enforce_file_format=True)
    return path


def _assert_no_canaries(capsys, caplog):
    captured = capsys.readouterr()
    record_messages = "\n".join(record.getMessage() for record in caplog.records)
    for stream_name, text in (
        ("stdout", captured.out),
        ("stderr", captured.err),
        ("log records", record_messages),
    ):
        for canary in CANARIES:
            assert canary not in text, f"A canary value reached {stream_name}"
    return captured


@pytest.mark.pydicom
def test_failed_replacement_does_not_log_value(capsys, caplog):
    caplog.set_level(logging.DEBUG)

    with pytest.raises(KeyError):
        anonymise_core.get_anonymous_replacement_value(
            "PatientName", current_value=CANARY_NAME, replacement_strategy={}
        )

    _assert_no_canaries(capsys, caplog)
    assert "PatientName" in caplog.text


@pytest.mark.pydicom
def test_anonymise_file_does_not_print_paths(tmp_path, capsys, caplog):
    caplog.set_level(logging.DEBUG)
    input_path = _write_canary_file(tmp_path / CANARY_DIR / "ZZCANARYFILE.dcm")

    anon_path = anonymise_api.anonymise_file(
        input_path,
        output_filepath=str(tmp_path / CANARY_OUTPUT_DIR / "plan.dcm"),
        delete_unknown_tags=True,
    )

    assert pathlib.Path(anon_path).exists()
    _assert_no_canaries(capsys, caplog)


@pytest.mark.pydicom
@pytest.mark.parametrize("fail_fast", [True, False])
def test_anonymise_directory_failure_logs_no_paths_or_error_text(
    tmp_path, monkeypatch, capsys, caplog, fail_fast
):
    caplog.set_level(logging.DEBUG)
    input_dir = tmp_path / CANARY_DIR
    _write_canary_file(input_dir / "ZZCANARYBAD.dcm")
    _write_canary_file(
        input_dir / "ZZCANARYGOOD.dcm",
        sop_instance_uid="1.2.826.0.1.3680043.10.1234.3",
    )

    real_anonymise_file = anonymise_api.anonymise_file

    def _fail_for_bad_file(dicom_filepath, **kwargs):
        # Real errors, such as OSError, carry the path, and pydicom errors can
        # carry values; this reproduces both.
        if "BAD" in pathlib.Path(dicom_filepath).name:
            raise ValueError(f"Cannot read {dicom_filepath} for {CANARY_NAME}")
        return real_anonymise_file(dicom_filepath, **kwargs)

    monkeypatch.setattr(anonymise_api, "anonymise_file", _fail_for_bad_file)

    with pytest.raises(ValueError):
        anonymise_api.anonymise_directory(
            input_dir,
            output_dirpath=str(tmp_path / "output"),
            delete_unknown_tags=True,
            fail_fast=fail_fast,
        )

    _assert_no_canaries(capsys, caplog)
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warning_records) == 1
    assert "file 1 of 2" in warning_records[0].getMessage()
    assert "ValueError" in warning_records[0].getMessage()


@pytest.mark.pydicom
def test_pseudonymise_sequence_warning_does_not_log_value(capsys, caplog):
    caplog.set_level(logging.DEBUG)
    item = pydicom.Dataset()
    item.PatientName = CANARY_NAME

    pseudo_strategy.pseudonymisation_dispatch["SQ"](pydicom.Sequence([item]))

    _assert_no_canaries(capsys, caplog)
    assert "Sequence" in caplog.text


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "command", [["dicom", "anonymise"], ["experimental", "dicom", "pseudonymise"]]
)
def test_cli_prints_file_count_not_paths(tmp_path, capsys, caplog, command):
    caplog.set_level(logging.DEBUG)
    input_dir = tmp_path / CANARY_DIR
    _write_canary_file(input_dir / "ZZCANARYFILE1.dcm")
    _write_canary_file(
        input_dir / "ZZCANARYFILE2.dcm",
        sop_instance_uid="1.2.826.0.1.3680043.10.1234.4",
    )

    args = define_parser().parse_args(
        [*command, str(input_dir), "-o", str(tmp_path / "output"), "-u"]
    )
    args.func(args)

    captured = _assert_no_canaries(capsys, caplog)
    assert "Wrote 2 file(s)" in captured.out
    assert len(list((tmp_path / "output").glob("*.dcm"))) == 2


@pytest.mark.pydicom
def test_streamlit_pseudonymise_failure_does_not_print_file_name(
    monkeypatch, capsys, caplog
):
    from pymedphys._streamlit.apps import pseudonymise as pseudonymise_app

    caplog.set_level(logging.DEBUG)
    uploaded = io.BytesIO()
    pydicom.dcmwrite(uploaded, _canary_dataset(), enforce_file_format=True)
    uploaded.seek(0)
    # Streamlit's UploadedFile is a BytesIO with the uploaded file's name.
    uploaded.name = "ZZCANARYFILE.dcm"

    def _raise_with_value(*args, **kwargs):
        raise ValueError(f"Cannot pseudonymise {CANARY_NAME}")

    monkeypatch.setattr(pseudonymise_app, "anonymise_dataset", _raise_with_value)

    bad_data = pseudonymise_app._zip_pseudo_fifty_mbytes(  # pylint: disable = protected-access
        [uploaded], io.BytesIO()
    )

    assert bad_data
    _assert_no_canaries(capsys, caplog)
    assert "ValueError" in caplog.text


@pytest.mark.pydicom
@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "pydicom quotes an invalid value in its validation message, which it "
        "issues as a Python warning and logs through the 'pydicom' logger. "
        "This remaining channel is tracked in the de-identification design "
        "document."
    ),
)
def test_pseudonymise_invalid_value_is_not_quoted(tmp_path, capsys, caplog):
    caplog.set_level(logging.DEBUG)
    ds = _canary_dataset()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ds.StudyTime = "ZZCANARYTIME"
        input_path = tmp_path / "input.dcm"
        pydicom.dcmwrite(input_path, ds, enforce_file_format=True)
    capsys.readouterr()
    caplog.clear()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        anonymise_api.anonymise_file(
            input_path,
            output_filepath=str(tmp_path / "output.dcm"),
            delete_unknown_tags=True,
            replacement_strategy=pseudo_strategy.pseudonymisation_dispatch,
            identifying_keywords=(
                pseudonymisation.get_default_pseudonymisation_keywords()
            ),
        )

    assert not [w for w in caught if "ZZCANARY" in str(w.message)]
    _assert_no_canaries(capsys, caplog)
