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

import functools
import io

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    conformance,
    conformance_markdown,
    instance_transform,
    policy,
    run,
    scope,
)
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import CLEAN_DESCRIPTORS, CLEAN_PIXEL_DATA
from pymedphys._dicom.deidentify.reasons import TransformReason
from pymedphys._dicom.deidentify.walker import SequesterReason

from .corpus_runs.clean_pixel_data import _CornerFinder
from .test_deidentify_conformance import _section

KEY = DeidKey(bytes(range(32)))
PAGE_NUMBER_VECTOR = 0x00182001
FRAME_LABEL_VECTOR = 0x00182002
DISPLAY_WINDOW_LABEL_VECTOR = 0x00182006

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


@functools.lru_cache(maxsize=1)
def _two_frame_capture() -> bytes:
    """The corpus's Multi-frame Grayscale Byte Secondary Capture Image."""
    (file,) = [
        each
        for each in corpus_module.build_corpus().files
        if each.name == "67-sc-grayscale-byte.dcm"
    ]
    return file.data


def _indexed_by(pointer: int) -> bytes:
    """The two-frame capture with a label for each frame in both label
    vectors, and its frames indexed by the vector that ``pointer`` names."""
    dataset = pydicom.dcmread(io.BytesIO(_two_frame_capture()))
    dataset.FrameLabelVector = ["FIRST", "SECOND"]
    dataset.DisplayWindowLabelVector = ["NARROW", "WIDE"]
    dataset.FrameIncrementPointer = pointer
    written = io.BytesIO()
    dataset.save_as(written, enforce_file_format=True)
    return written.getvalue()


def _cleaned_without_descriptors(data: bytes):
    transform = instance_transform.InstanceTransform(
        policy.compose_custom_policy((CLEAN_PIXEL_DATA,)),
        KEY,
        finder=_CornerFinder(),
        unvalidated_policy=True,
    )
    return transform(data, run.InstanceRecord.from_file(data))


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.parametrize("pointer", [FRAME_LABEL_VECTOR, DISPLAY_WINDOW_LABEL_VECTOR])
def test_a_label_vector_that_indexes_the_frames_sequesters_without_clean_descriptors(
    pointer,
):
    # D would write one label for two frames (D-021), so the capture is
    # sequestered, and no reviewer's verdict on its pixels can release it.
    result = _cleaned_without_descriptors(_indexed_by(pointer))

    assert isinstance(result, run.Sequestered)
    (sequestration,) = result.reasons
    assert (sequestration.path, sequestration.action, sequestration.reason) == (
        ElementPath((), f"({pointer >> 16:04X},{pointer & 0xFFFF:04X})"),
        "D",
        SequesterReason.FRAME_INDEX,
    )


def test_label_vectors_that_do_not_index_the_frames_take_one_dummy_label():
    # Where Page Number Vector indexes the frames, D's one dummy label in
    # each label vector indexes nothing, so it does not sequester.
    result = _cleaned_without_descriptors(_indexed_by(PAGE_NUMBER_VECTOR))

    assert not isinstance(result, run.Sequestered)
