"""Deleting original DICOM files requires an explicit descriptive option."""

import pytest

from pymedphys.cli import define_parser


@pytest.mark.parametrize(
    "command",
    [
        ["dicom", "anonymise", "input.dcm"],
        ["experimental", "dicom", "pseudonymise", "input.dcm"],
    ],
)
def test_short_debug_flag_cannot_trigger_dicom_deletion(command):
    parser = define_parser()

    with pytest.raises(SystemExit):
        parser.parse_args([*command, "-d"])

    args = parser.parse_args(["-d", *command])
    assert args.logging_debug is True
    assert args.delete_original_files is False


@pytest.mark.parametrize(
    "command",
    [
        ["dicom", "anonymise", "input.dcm"],
        ["experimental", "dicom", "pseudonymise", "input.dcm"],
    ],
)
def test_original_deletion_requires_explicit_flag(command):
    parser = define_parser()
    args = parser.parse_args(command)
    assert args.delete_original_files is False

    args = parser.parse_args([*command, "--delete_original_files"])
    assert args.delete_original_files is True
