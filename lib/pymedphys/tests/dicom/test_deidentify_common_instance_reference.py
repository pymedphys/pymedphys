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

"""Which paths are the Common Instance Reference Module's, and which reference instances."""

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify.common_instance_reference import (
    is_common_instance_reference,
    is_instance_reference,
)
from pymedphys._dicom.deidentify.file_layout import ElementPath


def _path(*steps):
    return ElementPath(tuple((tag, 0) for tag in steps[:-1]), steps[-1])


@pytest.mark.parametrize("tag", ["(0008,1115)", "(0008,1200)"])
def test_the_modules_sequences_are_at_the_top_level_only(tag):
    assert is_common_instance_reference(_path(tag))
    # As in the Hierarchical SOP Instance Reference Macro.
    assert not is_common_instance_reference(_path("(0008,9092)", tag))


@pytest.mark.parametrize("tag", ["(0008,1140)", "(0008,114A)", "(0008,1155)"])
def test_other_attributes_are_not_the_modules_sequences(tag):
    assert not is_common_instance_reference(_path(tag))


@pytest.mark.parametrize(
    "steps",
    [
        ("(0008,1140)", "(0008,1155)"),  # Referenced Image Sequence
        ("(0008,1111)", "(0008,1155)"),  # Referenced Performed Procedure Step
        ("(5200,9230)", "(0008,9124)", "(0008,2112)", "(0008,1155)"),
        ("(0008,9092)", "(0008,1115)", "(0008,1199)", "(0008,1155)"),
        ("(0008,1164)", "(0008,1167)"),  # Frame Extraction Sequence
    ],
)
def test_an_instance_reference_is_in_any_sequence_but_the_modules(steps):
    assert is_instance_reference(_path(*steps))


@pytest.mark.parametrize(
    "steps",
    [
        ("(0008,1115)", "(0008,114A)", "(0008,1155)"),
        ("(0008,1200)", "(0008,1115)", "(0008,114A)", "(0008,1155)"),
        # Referenced SOP Instance UID names a study in these sequences' items.
        ("(0008,1110)", "(0008,1155)"),
        ("(3006,0010)", "(3006,0012)", "(0008,1155)"),
        # At the top level, and not a reference attribute.
        ("(0008,1155)",),
        ("(0008,1140)", "(0008,1150)"),
        ("(3006,0010)", "(3006,0012)", "(3006,0014)", "(0020,000E)"),
    ],
)
def test_other_paths_are_not_instance_references(steps):
    assert not is_instance_reference(_path(*steps))
