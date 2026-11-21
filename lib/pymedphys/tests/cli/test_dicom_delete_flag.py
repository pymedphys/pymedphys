# Copyright (C) 2026 Jeff (jdotc1)

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
