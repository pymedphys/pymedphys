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

"""MR and PET volumes, and PET values that may disclose body weight."""

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import pixel_risk, sop_classes

from .test_deidentify_pixel_risk import (
    EXPLICIT_LE,
    SENTINEL,
    TRANSFER_SYNTAXES,
    _assess,
    _ct,
    _found,
    _read_back,
    _series_found,
    _with_raw,
)

Indicator = pixel_risk.Indicator
Risk = pixel_risk.Risk

CT_IMAGE = "1.2.840.10008.5.1.4.1.1.2"
MR_IMAGE = "1.2.840.10008.5.1.4.1.1.4"
PET_IMAGE = "1.2.840.10008.5.1.4.1.1.128"
MR_SPECTROSCOPY = "1.2.840.10008.5.1.4.1.1.4.2"
# Enhanced MR Image, Enhanced MR Color Image, and Legacy Converted Enhanced
# MR Image.
MULTI_FRAME_MR = [
    "1.2.840.10008.5.1.4.1.1.4.1",
    "1.2.840.10008.5.1.4.1.1.4.3",
    "1.2.840.10008.5.1.4.1.1.4.4",
]
# Enhanced PET Image and Legacy Converted Enhanced PET Image.
MULTI_FRAME_PET = ["1.2.840.10008.5.1.4.1.1.130", "1.2.840.10008.5.1.4.1.1.128.1"]
MULTI_FRAME = [
    *((uid, Indicator.MR_VOLUME) for uid in MULTI_FRAME_MR),
    *((uid, Indicator.PET_VOLUME) for uid in MULTI_FRAME_PET),
]
LOCALIZER = ["ORIGINAL", "PRIMARY", "LOCALIZER"]


def _image(sop_class: str, number: int, **attributes) -> "pydicom.Dataset":
    dataset = _ct(**attributes)
    dataset.SOPClassUID = sop_class
    dataset.SOPInstanceUID = f"1.2.3.4.{number}"
    return dataset


def test_the_volume_classes_are_the_image_classes_of_ct_mr_and_pet():
    # Every class named here is a Standard Storage SOP Class of the pinned
    # edition, so a typing slip cannot drop a volume silently.
    for uid in [CT_IMAGE, MR_IMAGE, PET_IMAGE, *MULTI_FRAME_MR, *MULTI_FRAME_PET]:
        assert sop_classes.iod_for_sop_class(uid) is not None


@pytest.mark.deid_requirement("MIDI-BP-15")
@TRANSFER_SYNTAXES
@pytest.mark.parametrize(
    "sop_class, indicator",
    [(MR_IMAGE, Indicator.MR_VOLUME), (PET_IMAGE, Indicator.PET_VOLUME)],
)
def test_every_mr_and_pet_volume_may_hold_a_reconstructable_face(
    transfer_syntax, sop_class, indicator
):
    series = [_image(sop_class, n) for n in range(3)]
    if transfer_syntax is not None:
        series = [_read_back(each, transfer_syntax) for each in series]
    findings = pixel_risk.assess_series(series)
    assert _series_found(findings) == {(indicator, (0, 1, 2), None)}
    assert {f.risk for f in findings} == {Risk.RECONSTRUCTABLE_FACE}


@pytest.mark.parametrize("sop_class", [MR_IMAGE, PET_IMAGE])
def test_one_mr_or_pet_image_is_no_volume(sop_class):
    assert not pixel_risk.assess_series([_image(sop_class, 0)])


def test_mr_spectroscopy_is_no_volume():
    series = [_image(MR_SPECTROSCOPY, n) for n in range(3)]
    assert not pixel_risk.assess_series(series)


@pytest.mark.deid_requirement("MIDI-BP-15")
@TRANSFER_SYNTAXES
@pytest.mark.parametrize("sop_class, indicator", MULTI_FRAME)
def test_one_multi_frame_mr_or_pet_image_can_be_a_volume(
    transfer_syntax, sop_class, indicator
):
    series = [_image(sop_class, 0, NumberOfFrames=3, BodyPartExamined="HEAD")]
    if transfer_syntax is not None:
        series = [_read_back(each, transfer_syntax) for each in series]
    assert _series_found(pixel_risk.assess_series(series)) == {
        (indicator, (0,), None),
        (Indicator.HEAD_OR_NECK, (0,), "(0018,0015)"),
    }


@pytest.mark.parametrize("sop_class, indicator", MULTI_FRAME)
def test_multi_frame_mr_and_pet_frames_add_up_and_localizers_do_not(
    sop_class, indicator
):
    one = _image(sop_class, 0, NumberOfFrames=1)
    assert not pixel_risk.assess_series([one])
    other = _image(sop_class, 1)
    assert _series_found(pixel_risk.assess_series([one, other])) == {
        (indicator, (0, 1), None)
    }
    localizer = _image(sop_class, 2, NumberOfFrames=5, ImageType=LOCALIZER)
    assert not pixel_risk.assess_series([one, localizer])


def test_per_frame_anatomy_of_an_enhanced_mr_image_can_name_the_head():
    region = pydicom.Dataset()
    region.CodeValue = "69536005"
    region.CodingSchemeDesignator = "SCT"
    anatomy = pydicom.Dataset()
    anatomy.FrameLaterality = "U"
    anatomy.AnatomicRegionSequence = [region]
    named = pydicom.Dataset()
    named.FrameAnatomySequence = [anatomy]
    image = _image(MULTI_FRAME_MR[0], 0, NumberOfFrames=2)
    image.PerFrameFunctionalGroupsSequence = [pydicom.Dataset(), named]
    image = _read_back(image, EXPLICIT_LE)
    assert _series_found(pixel_risk.assess_series([image])) == {
        (Indicator.MR_VOLUME, (0,), None),
        (
            Indicator.HEAD_OR_NECK,
            (0,),
            "(5200,9230)[1] > (0020,9071)[0] > (0008,2218)[0] > (0008,0100)",
        ),
    }


def test_each_modality_of_a_series_is_its_own_volume():
    # A series holds one modality, but a malformed one that mixes them must
    # not hide a volume, nor join the frames of two into one.
    series = [
        _image(CT_IMAGE, 0),
        _image(MR_IMAGE, 1, BodyPartExamined="HEAD"),
        _image(MR_IMAGE, 2),
        _image(PET_IMAGE, 3, BodyPartExamined="HEAD"),
    ]
    assert _series_found(pixel_risk.assess_series(series)) == {
        (Indicator.MR_VOLUME, (1, 2), None),
        (Indicator.HEAD_OR_NECK, (1,), "(0018,0015)"),
    }
    series.append(_image(CT_IMAGE, 4, BodyPartExamined="HEAD"))
    assert [f.indicator for f in pixel_risk.assess_series(series)] == [
        Indicator.CT_VOLUME,
        Indicator.MR_VOLUME,
        Indicator.HEAD_OR_NECK,
    ]
    assert _series_found(pixel_risk.assess_series(series)) == {
        (Indicator.CT_VOLUME, (0, 4), None),
        (Indicator.MR_VOLUME, (1, 2), None),
        (Indicator.HEAD_OR_NECK, (1, 4), "(0018,0015)"),
    }


def test_an_unreadable_sop_class_counts_towards_each_volume_of_its_series():
    unknown = _image(MR_IMAGE, 1)
    _with_raw(unknown, 0x00080016, "UI", b"1.2.\xff")
    found = _series_found(pixel_risk.assess_series([_image(MR_IMAGE, 0), unknown]))
    assert found == {
        (Indicator.MR_VOLUME, (0, 1), None),
        (Indicator.UNREADABLE, (1,), "(0008,0016)"),
    }
    # Instances of no known class make no volume of a modality, but each is
    # reported as unreadable evidence of a reconstructable face.
    other = _image(MR_IMAGE, 2)
    _with_raw(other, 0x00080016, "UI", b"1.2.\xff")
    findings = pixel_risk.assess_series([unknown, other])
    assert _series_found(findings) == {
        (Indicator.UNREADABLE, (0,), "(0008,0016)"),
        (Indicator.UNREADABLE, (1,), "(0008,0016)"),
    }
    assert {f.risk for f in findings} == {Risk.RECONSTRUCTABLE_FACE}


def test_the_series_evidence_of_an_mr_or_pet_image_is_assessed_as_it_is():
    series = [
        _read_back(_image(PET_IMAGE, n, BodyPartExamined="HEADNECK"), EXPLICIT_LE)
        for n in range(2)
    ]
    evidence = [pixel_risk.series_evidence(each) for each in series]
    assert pixel_risk.assess_series(evidence) == pixel_risk.assess_series(series)
    assert pixel_risk.assess_series(series)[0].indicator is Indicator.PET_VOLUME


def _pet(**attributes) -> "pydicom.Dataset":
    return _image(PET_IMAGE, 0, **attributes)


def _mapping(code: str, long_code: bool = False) -> "pydicom.Dataset":
    """A Real World Value Mapping item whose values are in the given unit."""
    unit = pydicom.Dataset()
    if long_code:
        unit.LongCodeValue = code
    else:
        unit.CodeValue = code
    unit.CodingSchemeDesignator = "UCUM"
    unit.CodeMeaning = SENTINEL
    mapping = pydicom.Dataset()
    mapping.LUTExplanation = SENTINEL
    mapping.LUTLabel = "SUV"
    mapping.RealWorldValueSlope = 0.0005
    mapping.RealWorldValueIntercept = 0
    mapping.MeasurementUnitsCodeSequence = [unit]
    return mapping


SUV_UNITS = "(0054,1001)"
TOP_MAPPING = "(0040,9096)[0] > (0040,08EA)[0] > (0008,0100)"


@pytest.mark.deid_requirement("MIDI-BP-01")
@TRANSFER_SYNTAXES
@pytest.mark.filterwarnings("ignore:Invalid value for VR CS")
@pytest.mark.parametrize("units", ["GML", "CM2ML", "gml"])
def test_suv_scaled_pet_may_disclose_body_weight(transfer_syntax, units):
    assessment = _assess(_pet(Units=units), transfer_syntax)
    assert _found(assessment) == {(Indicator.SUV_UNITS, SUV_UNITS)}
    assert assessment.risks == {Risk.BODY_WEIGHT}


@pytest.mark.parametrize("units", ["BQML", "CNTS", "PROPCNTS", ""])
def test_pet_in_other_units_has_no_indicator(units):
    dataset = _pet(Units=units, SUVType="BW")
    assert not pixel_risk.assess_pixel_risk(dataset).findings


@pytest.mark.deid_requirement("MIDI-BP-01")
@TRANSFER_SYNTAXES
@pytest.mark.parametrize(
    "code, long_code",
    [
        ("g/ml{SUVbw}", False),
        ("cm2/ml{SUVbsa}", False),
        ("g/ml{suvibw}", False),
        ("g/ml{SUVlbm(James128)}", True),
    ],
)
def test_a_mapping_to_suv_may_disclose_body_weight(transfer_syntax, code, long_code):
    # A slope to SUV, with the Radionuclide Total Dose that the Basic
    # Profile keeps, gives the weight whatever the stored values' unit.
    dataset = _pet(Units="BQML")
    dataset.RealWorldValueMappingSequence = [
        _mapping("Bq/ml"),
        _mapping(code, long_code),
    ]
    tag = "(0008,0119)" if long_code else "(0008,0100)"
    path = f"(0040,9096)[1] > (0040,08EA)[0] > {tag}"
    assessment = _assess(dataset, transfer_syntax)
    assert _found(assessment) == {(Indicator.SUV_MAPPING, path)}
    assert assessment.risks == {Risk.BODY_WEIGHT}
    assert SENTINEL not in repr(assessment)


def test_a_functional_group_mapping_to_suv_is_found_where_it_is():
    image = _image(MULTI_FRAME_PET[0], 0, NumberOfFrames=2)
    shared = pydicom.Dataset()
    shared.RealWorldValueMappingSequence = [_mapping("Bq/ml")]
    frame = pydicom.Dataset()
    frame.RealWorldValueMappingSequence = [_mapping("g/ml{SUVbw}")]
    image.SharedFunctionalGroupsSequence = [shared]
    image.PerFrameFunctionalGroupsSequence = [pydicom.Dataset(), frame]
    assessment = _assess(image, EXPLICIT_LE)
    assert _found(assessment) == {
        (
            Indicator.SUV_MAPPING,
            "(5200,9230)[1] > (0040,9096)[0] > (0040,08EA)[0] > (0008,0100)",
        )
    }


def test_a_mapping_to_another_unit_has_no_indicator():
    dataset = _pet()
    dataset.RealWorldValueMappingSequence = [_mapping("Bq/ml"), _mapping("{counts}/s")]
    assert not pixel_risk.assess_pixel_risk(dataset).findings


@pytest.mark.parametrize(
    "where, tag, vr, value, path",
    [
        ("image", 0x00541001, "CS", b"GML\\BQML", SUV_UNITS),
        ("image", 0x00541001, "CS", b"G\xffML", SUV_UNITS),
        ("image", 0x00409096, "LO", SENTINEL.encode(), "(0040,9096)"),
        (
            "mapping",
            0x004008EA,
            "LO",
            SENTINEL.encode(),
            "(0040,9096)[0] > (0040,08EA)",
        ),
        ("unit", 0x00080100, "SH", b"g/ml\\1", TOP_MAPPING),
        ("unit", 0x00080100, "US", b"\x01\x00", TOP_MAPPING),
    ],
)
def test_unreadable_evidence_of_body_weight_is_reported(where, tag, vr, value, path):
    dataset = _pet()
    mapping = _mapping("Bq/ml")
    dataset.RealWorldValueMappingSequence = [mapping]
    held = {
        "image": dataset,
        "mapping": mapping,
        "unit": mapping.MeasurementUnitsCodeSequence[0],
    }[where]
    _with_raw(held, tag, vr, value)
    assessment = pixel_risk.assess_pixel_risk(dataset)
    assert _found(assessment) == {(Indicator.UNREADABLE, path)}
    assert assessment.risks == {Risk.BODY_WEIGHT}
    assert SENTINEL not in repr(assessment)


def test_assessing_body_weight_leaves_the_instance_as_it_was_read():
    dataset = _pet(Units="GML")
    dataset.RealWorldValueMappingSequence = [_mapping("g/ml{SUVbw}")]
    dataset = _read_back(dataset, EXPLICIT_LE)
    before = {tag: dataset.get_item(tag, keep_deferred=True) for tag in dataset.keys()}
    assert _found(pixel_risk.assess_pixel_risk(dataset)) == {
        (Indicator.SUV_UNITS, SUV_UNITS),
        (Indicator.SUV_MAPPING, TOP_MAPPING),
    }
    for tag, element in before.items():
        assert dataset.get_item(tag, keep_deferred=True) is element
