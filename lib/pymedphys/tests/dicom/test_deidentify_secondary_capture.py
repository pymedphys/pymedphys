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

"""Secondary Capture images, released only through Clean Pixel Data."""

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    conformance,
    conformance_markdown,
    instance_transform,
    policy,
    scope,
)
from pymedphys._dicom.deidentify.policy import CLEAN_DESCRIPTORS, CLEAN_PIXEL_DATA
from pymedphys._dicom.deidentify.reasons import TransformReason

from .test_deidentify_conformance import _section

CUSTOM_OPTION_SETS = (
    (),
    (CLEAN_DESCRIPTORS,),
    (CLEAN_PIXEL_DATA,),
    (CLEAN_PIXEL_DATA, CLEAN_DESCRIPTORS),
)
SECONDARY_CAPTURE_IODS = (
    "Secondary Capture Image",
    "Multi-frame Single Bit Secondary Capture Image",
    "Multi-frame Grayscale Byte Secondary Capture Image",
    "Multi-frame Grayscale Word Secondary Capture Image",
    "Multi-frame True Color Secondary Capture Image",
)


def _policies():
    return [policy.compose_policy(preset) for preset in sorted(policy.PRESETS)] + [
        policy.compose_custom_policy(options) for options in CUSTOM_OPTION_SETS
    ]


def _uncleaned(iod, composed):
    return instance_transform._uncleaned_secondary_capture(  # pylint: disable = protected-access
        iod, composed
    )


def test_the_five_secondary_capture_iods_are_supported():
    assert scope.SECONDARY_CAPTURE_IODS == frozenset(SECONDARY_CAPTURE_IODS)
    assert scope.SECONDARY_CAPTURE_IODS <= scope.SUPPORTED_IODS


@pytest.mark.deid_requirement("PS3.15-E.3.1-01", "MIDI-BP-10")
@pytest.mark.parametrize("iod", SECONDARY_CAPTURE_IODS)
def test_a_secondary_capture_is_sequestered_unless_clean_pixel_data_is_selected(
    iod,
):
    # No preset selects Clean Pixel Data, so every preset sequesters it.
    assert not any(CLEAN_PIXEL_DATA in options for options in policy.PRESETS.values())
    for composed in _policies():
        reasons = _uncleaned(iod, composed)
        expected = (
            []
            if CLEAN_PIXEL_DATA in composed.options
            else [TransformReason.SECONDARY_CAPTURE_NOT_CLEANED]
        )
        assert isinstance(reasons, tuple)
        assert list(reasons) == expected


@pytest.mark.parametrize("iod", ["CT Image", "RT Image", "Segmentation"])
def test_other_images_are_not_sequestered_for_it(iod):
    for composed in _policies():
        reasons = _uncleaned(iod, composed)
        assert isinstance(reasons, tuple)
        assert not reasons


def test_the_reason_has_its_own_code():
    assert (
        TransformReason.SECONDARY_CAPTURE_NOT_CLEANED.value
        == "secondary-capture-not-cleaned"
    )


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
@pytest.mark.parametrize("options", CUSTOM_OPTION_SETS)
def test_the_conformance_statement_says_how_a_secondary_capture_is_handled(
    options,
):
    statement = conformance.conformance_statement(
        policy.compose_custom_policy(options), vocabulary=None
    )
    section = _section(
        conformance_markdown.render_markdown(statement), "Supported instances"
    )

    assert set(SECONDARY_CAPTURE_IODS) <= set(statement.iods)
    if CLEAN_PIXEL_DATA in options:
        assert "An instance of a Secondary Capture IOD" in section
        assert "released only on a reviewer's verdict" in section
        assert "`uncleanable-pixel-data`" in section
        assert "`secondary-capture-not-cleaned`" not in section
    else:
        assert "sequestered as `secondary-capture-not-cleaned`" in section
        assert "released only on a reviewer's verdict" not in section
