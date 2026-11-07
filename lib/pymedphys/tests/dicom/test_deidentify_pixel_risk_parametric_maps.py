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

"""Parametric Maps, which can show the head's outline, and Real World Value
Mappings to a standardised uptake value, which may disclose body weight."""

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import pixel_risk, sop_classes

from .test_deidentify_pixel_risk import (
    EXPLICIT_LE,
    SENTINEL,
    TRANSFER_SYNTAXES,
    _assess,
    _found,
    _frame_anatomy,
    _multi_frame,
    _read_back,
    _region,
    _series_found,
    _slice,
    _with_raw,
)
from .test_deidentify_pixel_risk_mr_pet import _mapping

Indicator = pixel_risk.Indicator
Risk = pixel_risk.Risk

PARAMETRIC_MAP = "1.2.840.10008.5.1.4.1.1.30"
REAL_WORLD_VALUE_MAPPING = "1.2.840.10008.5.1.4.1.1.67"
ADC = ["DERIVED", "PRIMARY", "VOLUME", "ADC"]
SHARED_HEAD = "(5200,9229)[0] > (0020,9071)[0] > (0008,2218)[0] > (0008,0100)"


def _parametric_map(number: int, **attributes) -> "pydicom.Dataset":
    return _multi_frame(number, PARAMETRIC_MAP, ImageType=ADC, **attributes)


def _value_mapping(*items: "pydicom.Dataset") -> "pydicom.Dataset":
    """A Real World Value Mapping instance, without pixel data, whose
    Referenced Image Real World Value Mapping Sequence holds ``items``,
    each naming one image."""
    dataset = pydicom.Dataset()
    dataset.SOPClassUID = REAL_WORLD_VALUE_MAPPING
    dataset.SOPInstanceUID = "1.2.3.5"
    dataset.PatientName = SENTINEL
    dataset.Modality = "RWV"
    for item in items:
        image = pydicom.Dataset()
        image.ReferencedSOPClassUID = "1.2.840.10008.5.1.4.1.1.128"
        image.ReferencedSOPInstanceUID = "1.2.3.4"
        item.ReferencedImageSequence = [image]
    dataset.ReferencedImageRealWorldValueMappingSequence = list(items)
    return dataset


def test_the_parametric_map_class_is_the_parametric_map_iods():
    assert pixel_risk.PARAMETRIC_MAP_STORAGE == PARAMETRIC_MAP
    assert sop_classes.iod_for_sop_class(PARAMETRIC_MAP).name == "Parametric Map"


@pytest.mark.deid_requirement("MIDI-BP-15")
@TRANSFER_SYNTAXES
@pytest.mark.parametrize("frames", [1, 2, 40])
def test_every_parametric_map_can_show_the_head_s_outline(transfer_syntax, frames):
    # A map of the head shows its outline wherever the quantity differs
    # from the air around it, whatever the quantity and however many frames.
    series = [_parametric_map(0, NumberOfFrames=frames)]
    if transfer_syntax is not None:
        series = [_read_back(each, transfer_syntax) for each in series]
    findings = pixel_risk.assess_series(series)
    assert _series_found(findings) == {(Indicator.PARAMETRIC_MAP, (0,), None)}
    assert {finding.risk for finding in findings} == {Risk.RECONSTRUCTABLE_FACE}


@pytest.mark.deid_requirement("MIDI-BP-15")
def test_a_parametric_map_is_no_frame_of_a_volume_beside_it():
    series = [_slice(0), _parametric_map(1, NumberOfFrames=8)]
    assert _series_found(pixel_risk.assess_series(series)) == {
        (Indicator.PARAMETRIC_MAP, (1,), None)
    }


@pytest.mark.deid_requirement("MIDI-BP-15")
def test_parametric_maps_are_reported_after_volumes_and_segmentations():
    segmentation = _multi_frame(
        2, "1.2.840.10008.5.1.4.1.1.66.4", ImageType=["DERIVED", "PRIMARY"]
    )
    series = [_parametric_map(0), _slice(1), segmentation, _slice(3)]
    assert [(f.indicator, f.instances) for f in pixel_risk.assess_series(series)] == [
        (Indicator.CT_VOLUME, (1, 3)),
        (Indicator.SEGMENTATION, (2,)),
        (Indicator.PARAMETRIC_MAP, (0,)),
    ]


@pytest.mark.deid_requirement("MIDI-BP-15")
@TRANSFER_SYNTAXES
def test_a_parametric_map_that_names_the_head_says_so(transfer_syntax):
    by_body_part = _parametric_map(0, BodyPartExamined="HEAD")
    by_frame_anatomy = _parametric_map(1)
    by_frame_anatomy.SharedFunctionalGroupsSequence = [
        _frame_anatomy(_region("69536005", "SCT"))
    ]
    series = [by_body_part, by_frame_anatomy]
    if transfer_syntax is not None:
        series = [_read_back(each, transfer_syntax) for each in series]
    assert _series_found(pixel_risk.assess_series(series)) == {
        (Indicator.PARAMETRIC_MAP, (0, 1), None),
        (Indicator.HEAD_OR_NECK, (0,), "(0018,0015)"),
        (Indicator.HEAD_OR_NECK, (1,), SHARED_HEAD),
    }


def test_a_parametric_map_is_kept_as_series_evidence():
    dataset = _parametric_map(0, BodyPartExamined="HEAD")
    evidence = pixel_risk.series_evidence(_read_back(dataset, EXPLICIT_LE))
    assert _series_found(pixel_risk.assess_series([evidence])) == {
        (Indicator.PARAMETRIC_MAP, (0,), None),
        (Indicator.HEAD_OR_NECK, (0,), "(0018,0015)"),
    }


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_parametric_map_s_functional_group_mapping_to_suv_is_found():
    dataset = _parametric_map(0, NumberOfFrames=2)
    shared = pydicom.Dataset()
    shared.RealWorldValueMappingSequence = [_mapping("g/ml{SUVbw}")]
    dataset.SharedFunctionalGroupsSequence = [shared]
    assessment = _assess(dataset, EXPLICIT_LE)
    assert _found(assessment) == {
        (
            Indicator.SUV_MAPPING,
            "(5200,9229)[0] > (0040,9096)[0] > (0040,08EA)[0] > (0008,0100)",
        )
    }


@pytest.mark.deid_requirement("MIDI-BP-01")
@TRANSFER_SYNTAXES
@pytest.mark.parametrize(
    "code, long_code",
    [("g/ml{SUVbw}", False), ("g/ml{SUVlbm(James128)}", True)],
)
def test_a_real_world_value_mapping_to_suv_may_disclose_body_weight(
    transfer_syntax, code, long_code
):
    # A Real World Value Mapping instance maps the values of the images that
    # each item names in the item itself, so its slope to SUV, with the
    # images' Radionuclide Total Dose, gives the weight as a PET image's
    # own mapping would.
    dataset = _value_mapping(_mapping("Bq/ml"), _mapping(code, long_code))
    tag = "(0008,0119)" if long_code else "(0008,0100)"
    assessment = _assess(dataset, transfer_syntax)
    assert not assessment.pixel_data
    assert _found(assessment) == {
        (Indicator.SUV_MAPPING, f"(0040,9094)[1] > (0040,08EA)[0] > {tag}")
    }
    assert assessment.risks == {Risk.BODY_WEIGHT}
    assert SENTINEL not in repr(assessment)


def test_a_real_world_value_mapping_to_another_unit_has_no_indicator():
    dataset = _value_mapping(_mapping("Bq/ml"), _mapping("um2/s"))
    assert not pixel_risk.assess_pixel_risk(dataset).findings


@pytest.mark.parametrize(
    "where, tag, vr, value, path",
    [
        ("instance", 0x00409094, "LO", SENTINEL.encode(), "(0040,9094)"),
        (
            "item",
            0x004008EA,
            "LO",
            SENTINEL.encode(),
            "(0040,9094)[0] > (0040,08EA)",
        ),
        (
            "unit",
            0x00080100,
            "SH",
            b"g/ml\\1",
            "(0040,9094)[0] > (0040,08EA)[0] > (0008,0100)",
        ),
    ],
)
def test_an_unreadable_real_world_value_mapping_is_unreadable_evidence(
    where, tag, vr, value, path
):
    item = _mapping("Bq/ml")
    dataset = _value_mapping(item)
    held = {
        "instance": dataset,
        "item": item,
        "unit": item.MeasurementUnitsCodeSequence[0],
    }[where]
    _with_raw(held, tag, vr, value)
    assessment = pixel_risk.assess_pixel_risk(dataset)
    assert _found(assessment) == {(Indicator.UNREADABLE, path)}
    assert assessment.risks == {Risk.BODY_WEIGHT}
    assert SENTINEL not in repr(assessment)
