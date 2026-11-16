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

"""The softcopy Presentation States, de-identified as their IODs and Table E.1-1 allow.

A Grayscale Softcopy Presentation State that conforms to its IOD holds
Presentation Creation Date (0070,0082) and Time (0070,0083), Type 1 at the
top level, to which Table E.1-1 gives a plain X, so the Basic Profile
sequesters it (D-020), and the Retain Longitudinal Temporal Information
Options keep or shift them. Its Graphic Annotation Sequence (0070,0001), the
text and graphics it draws over the image, takes D, which a sequence has no
dummy value for, so an instance that holds one is sequestered under every
option (D-021, D-041). Every file is synthetic. Values that must never reach
a written file carry the text ``SENTINEL``.
"""

import io

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    icc_cleaning,
    icc_profiles,
    iods,
    policy,
    run,
    scope,
)
from pymedphys._dicom.deidentify.descriptor_cleaning import DescriptorCleaning
from pymedphys._dicom.deidentify.element_rules import ElementRules
from pymedphys._dicom.deidentify.face_review import FaceReview
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import InstanceTransform
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.reviewed_roi_names import ReviewedNames
from pymedphys._dicom.deidentify.walker import SequesterReason, Sequestration

from . import _synthetic_references as synthetic

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
GRAYSCALE_SOFTCOPY_PRESENTATION_STATE_STORAGE = "1.2.840.10008.5.1.4.1.1.11.1"
COLOR_SOFTCOPY_PRESENTATION_STATE_STORAGE = "1.2.840.10008.5.1.4.1.1.11.2"
ICC_PROFILE = 0x00282000
PRESENTATION_STATE_SERIES = "2.25.700"
PRESENTATION_STATE = "2.25.701"
PRESENTATION_CREATION_DATE = "(0070,0082)"
PRESENTATION_CREATION_TIME = "(0070,0083)"
GRAPHIC_ANNOTATION_SEQUENCE = "(0070,0001)"
REFERENCED_SERIES_SEQUENCE = "(0008,1115)"
# The presets that select a Retain Longitudinal Temporal Information Option,
# under which Presentation Creation Date and Time are kept or shifted.
DATED_PRESETS = ("tps-import", "public-release")
UNDATED_PRESETS = ("basic", "basic-clean-descriptors")
SOURCE_DATE = "20240305"
SOURCE_TIME = "101500"
CLEAN_DESCRIPTORS = "clean_descriptors"
CLEAN_RECOGNIZABLE_VISUAL_FEATURES = "clean_recognizable_visual_features"
# A face review with no verdicts, as the first run of a collection under
# Clean Recognizable Visual Features is given; a Presentation State has no
# pixel data, contours, or dose that could show a face.
NO_FACE_VERDICTS = FaceReview(
    "A-" + "0123456789abcdef" * 2,
    frozenset(),
    frozenset(),
    frozenset(),
    frozenset(),
)


def _presentation_state(*, annotated=False, color=False):
    """Return a softcopy Presentation State of the first CT slice.

    It is a Grayscale Softcopy Presentation State, or, where ``color`` is
    true, a Color Softcopy Presentation State, whose ICC Profile Module
    replaces the grayscale pipeline's Presentation LUT and VOI LUT.
    """
    dataset = synthetic.instance(
        COLOR_SOFTCOPY_PRESENTATION_STATE_STORAGE
        if color
        else GRAYSCALE_SOFTCOPY_PRESENTATION_STATE_STORAGE,
        PRESENTATION_STATE,
        PRESENTATION_STATE_SERIES,
        ReferencedSeriesSequence=[
            synthetic.item(
                SeriesInstanceUID=synthetic.CT_SERIES,
                ReferencedImageSequence=[
                    synthetic.reference(
                        synthetic.CT_IMAGE_STORAGE, synthetic.CT_SLICES[0]
                    )
                ],
            )
        ],
    )
    dataset.Modality = "PR"
    dataset.InstanceNumber = 1
    dataset.ContentLabel = "WINDOWED"
    dataset.ContentDescription = "SENTINEL DESCRIPTION"
    dataset.ContentCreatorName = "SENTINEL^CREATOR"
    dataset.PresentationCreationDate = SOURCE_DATE
    dataset.PresentationCreationTime = SOURCE_TIME
    dataset.DisplayedAreaSelectionSequence = [
        synthetic.item(
            DisplayedAreaTopLeftHandCorner=[1, 1],
            DisplayedAreaBottomRightHandCorner=[2, 2],
            PresentationSizeMode="SCALE TO FIT",
            PresentationPixelSpacing=["1", "1"],
        )
    ]
    if color:
        dataset.add_new(
            ICC_PROFILE, "OB", icc_profiles.srgb_profile("A display's profile")
        )
    else:
        dataset.PresentationLUTShape = "IDENTITY"
        dataset.SoftcopyVOILUTSequence = [
            synthetic.item(WindowCenter="40", WindowWidth="400")
        ]
    if annotated:
        dataset.GraphicLayerSequence = [
            synthetic.item(
                GraphicLayer="LAYER",
                GraphicLayerOrder=1,
                GraphicLayerDescription="SENTINEL LAYER",
            )
        ]
        dataset.GraphicAnnotationSequence = [
            synthetic.item(
                GraphicLayer="LAYER",
                TextObjectSequence=[
                    synthetic.item(
                        AnchorPointAnnotationUnits="PIXEL",
                        AnchorPoint=[1.0, 1.0],
                        AnchorPointVisibility="N",
                        UnformattedTextValue="SENTINEL NAME",
                    )
                ],
            )
        ]
    return dataset


def _transformed(preset, dataset):
    composed = policy.compose_policy(preset)
    cleaning = (
        DescriptorCleaning(None, ReviewedNames.empty())
        if CLEAN_DESCRIPTORS in composed.options
        else None
    )
    face_review = (
        NO_FACE_VERDICTS
        if CLEAN_RECOGNIZABLE_VISUAL_FEATURES in composed.options
        else None
    )
    transform = InstanceTransform(
        composed,
        KEY,
        cleaning=cleaning,
        face_review=face_review,
        unvalidated_policy=True,
    )
    data = synthetic.written(dataset)
    return transform(data, InstanceRecord.from_file(data))


def test_the_six_softcopy_presentation_states_are_supported():
    assert {
        "Grayscale Softcopy Presentation State",
        "Color Softcopy Presentation State",
        "Pseudo-Color Softcopy Presentation State",
        "Blending Softcopy Presentation State",
        "XA/XRF Grayscale Softcopy Presentation State",
        "Variable Modality LUT Softcopy Presentation State",
    } <= scope.SUPPORTED_IODS
    assert not scope.classify(
        GRAYSCALE_SOFTCOPY_PRESENTATION_STATE_STORAGE,
        synthetic.EXPLICIT_VR_LITTLE_ENDIAN,
    ).sequestered


@pytest.mark.deid_requirement("MIDI-BP-06")
@pytest.mark.parametrize("preset", UNDATED_PRESETS)
def test_the_basic_profile_sequesters_a_presentation_state_by_its_creation_date(
    preset,
):
    result = _transformed(preset, _presentation_state())

    assert isinstance(result, run.Sequestered)
    assert set(result.reasons) == {
        Sequestration(ElementPath((), tag), "X", vr, SequesterReason.REQUIRED_BY_IOD)
        for tag, vr in (
            (PRESENTATION_CREATION_DATE, "DA"),
            (PRESENTATION_CREATION_TIME, "TM"),
        )
    }


@pytest.mark.deid_requirement("MIDI-BP-06")
@pytest.mark.parametrize("preset", DATED_PRESETS)
def test_a_date_option_releases_a_presentation_state_without_annotations(preset):
    result = _transformed(preset, _presentation_state())

    assert isinstance(result, run.Transformed), result
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert b"SENTINEL" not in result.data
    # Modified Dates shifts the creation date back by whole weeks and keeps
    # the time (D-006); both stay, as the IOD requires.
    assert written.PresentationCreationDate != SOURCE_DATE
    assert len(written.PresentationCreationDate) == 8
    assert written.PresentationCreationTime == SOURCE_TIME
    assert written.Modality == "PR"
    assert written.ContentLabel == "WINDOWED"
    assert written.ContentCreatorName == ""
    # The Presentation State Relationship Module's Referenced Series
    # Sequence, which these IODs make Type 1, is kept with its UIDs replaced,
    # although no reference outside it remains: the Common Instance
    # Reference Module, whose sequence of the same tag lapses without one,
    # is not among these IODs' modules.
    (series,) = written.ReferencedSeriesSequence
    (image,) = series.ReferencedImageSequence
    assert series.SeriesInstanceUID != synthetic.CT_SERIES
    assert image.ReferencedSOPInstanceUID != synthetic.CT_SLICES[0]
    assert image.ReferencedSOPClassUID == synthetic.CT_IMAGE_STORAGE
    # The display settings, which identify no one, are kept.
    assert written.PresentationLUTShape == "IDENTITY"
    (area,) = written.DisplayedAreaSelectionSequence
    assert area.PresentationSizeMode == "SCALE TO FIT"
    (voi,) = written.SoftcopyVOILUTSequence
    assert (voi.WindowCenter, voi.WindowWidth) == (40, 400)


@pytest.mark.parametrize("preset", DATED_PRESETS)
def test_a_color_presentation_states_icc_profile_is_cleaned_to_its_colorimetry(
    preset,
):
    # ICC Profile is Type 1 in the ICC Profile Module, which the Color
    # Softcopy Presentation State requires, so X/Z/D resolves to D, which
    # writes the source profile cleaned of everything but its colorimetry,
    # as in the enhanced image IODs (D-021, D-022).
    result = _transformed(preset, _presentation_state(color=True))

    assert isinstance(result, run.Transformed), result
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert written[ICC_PROFILE].VR == "OB"
    assert written[ICC_PROFILE].value == icc_cleaning.clean_profile(
        icc_profiles.srgb_profile("A display's profile"), "DEIDENTIFIED"
    )
    assert b"SENTINEL" not in result.data


@pytest.mark.deid_requirement("PS3.15-E.3.3-01")
@pytest.mark.parametrize("preset", policy.PRESETS)
def test_every_preset_sequesters_a_presentation_state_with_graphic_annotations(
    preset,
):
    result = _transformed(preset, _presentation_state(annotated=True))

    assert isinstance(result, run.Sequestered)
    assert (
        Sequestration(
            ElementPath((), GRAPHIC_ANNOTATION_SEQUENCE),
            "D",
            "SQ",
            SequesterReason.NO_DUMMY_VALUE,
        )
        in result.reasons
    )


@pytest.mark.parametrize("preset", policy.PRESETS)
def test_the_referenced_series_sequence_is_kept_where_a_presentation_state_requires_it(
    preset,
):
    iod = iods.load_iod_tables().iods["Grayscale Softcopy Presentation State"]
    rules = ElementRules(policy.compose_policy(preset))

    rule = rules.rule(REFERENCED_SERIES_SEQUENCE, (), iod=iod)

    assert rule.action == "K", rule
    assert {
        (definition.module, definition.type)
        for definition in iod.definitions
        if definition.tag == REFERENCED_SERIES_SEQUENCE and not definition.path
    } == {("Presentation State Relationship", "1")}
