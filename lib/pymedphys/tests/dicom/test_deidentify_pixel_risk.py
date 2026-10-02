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

"""Indicators of risk in pixel data, read from an instance's attributes."""

import io
import struct

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import pixel_risk, standard
from pymedphys._dicom.deidentify.file_layout import ElementPath

Indicator = pixel_risk.Indicator
Risk = pixel_risk.Risk
RawDataElement = pydicom.dataelem.RawDataElement

IMPLICIT_LE = "1.2.840.10008.1.2"
EXPLICIT_LE = "1.2.840.10008.1.2.1"
CT_IMAGE = "1.2.840.10008.5.1.4.1.1.2"
RT_STRUCTURE_SET = "1.2.840.10008.5.1.4.1.1.481.3"

# Synthetic text that no finding, path, or representation may contain.
SENTINEL = "ZZSENTINELZZ"


def _ct(**attributes) -> "pydicom.Dataset":
    dataset = pydicom.Dataset()
    dataset.SOPClassUID = CT_IMAGE
    dataset.SOPInstanceUID = "1.2.3.4"
    dataset.PatientName = SENTINEL
    dataset.ImageType = ["ORIGINAL", "PRIMARY", "AXIAL"]
    dataset.Rows = 2
    dataset.Columns = 2
    dataset.BitsAllocated = 16
    dataset.BitsStored = 12
    dataset.HighBit = 11
    dataset.PixelRepresentation = 0
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.PixelData = b"\x00\x00" * 4
    for keyword, value in attributes.items():
        setattr(dataset, keyword, value)
    return dataset


def _roi(number: int, interpreted_type: str) -> "pydicom.Dataset":
    observation = pydicom.Dataset()
    observation.ObservationNumber = number
    observation.ReferencedROINumber = number
    observation.RTROIInterpretedType = interpreted_type
    observation.ROIInterpreter = ""
    return observation


def _contour(number: int, contours: int) -> "pydicom.Dataset":
    item = pydicom.Dataset()
    item.ReferencedROINumber = number
    item.ROIDisplayColor = [255, 0, 0]
    if contours:
        contour = pydicom.Dataset()
        contour.ContourGeometricType = "CLOSED_PLANAR"
        contour.NumberOfContourPoints = 3
        contour.ContourData = [0, 0, 0, 1, 0, 0, 0, 1, 0]
        item.ContourSequence = [contour] * contours
    return item


def _structure_set(rois, contours) -> "pydicom.Dataset":
    dataset = pydicom.Dataset()
    dataset.SOPClassUID = RT_STRUCTURE_SET
    dataset.SOPInstanceUID = "1.2.3.5"
    dataset.PatientName = SENTINEL
    dataset.RTROIObservationsSequence = list(rois)
    dataset.ROIContourSequence = list(contours)
    return dataset


def _read_back(dataset: "pydicom.Dataset", transfer_syntax: str) -> "pydicom.Dataset":
    """Write a data set and read it again, so that its elements are raw."""
    dataset = pydicom.Dataset(dataset)
    dataset.file_meta = pydicom.dataset.FileMetaDataset()
    dataset.file_meta.TransferSyntaxUID = transfer_syntax
    dataset.file_meta.MediaStorageSOPClassUID = dataset.SOPClassUID
    dataset.file_meta.MediaStorageSOPInstanceUID = dataset.SOPInstanceUID
    buffer = io.BytesIO()
    pydicom.dcmwrite(buffer, dataset, enforce_file_format=True)
    return pydicom.dcmread(io.BytesIO(buffer.getvalue()))


TRANSFER_SYNTAXES = pytest.mark.parametrize(
    "transfer_syntax", [None, IMPLICIT_LE, EXPLICIT_LE], ids=["memory", "ivr", "evr"]
)


def _assess(dataset, transfer_syntax):
    if transfer_syntax is not None:
        dataset = _read_back(dataset, transfer_syntax)
    return pixel_risk.assess_pixel_risk(dataset)


def _found(assessment) -> set[tuple[Indicator, str]]:
    return {(finding.indicator, str(finding.path)) for finding in assessment.findings}


@TRANSFER_SYNTAXES
def test_an_original_ct_image_has_pixel_data_and_no_indicator(transfer_syntax):
    assessment = _assess(_ct(), transfer_syntax)
    assert assessment.pixel_data
    assert not assessment.findings
    assert not assessment.risks


def test_an_instance_without_pixel_data_says_so():
    assessment = pixel_risk.assess_pixel_risk(_structure_set([], []))
    assert not assessment.pixel_data


@pytest.mark.parametrize("keyword", ["FloatPixelData", "DoubleFloatPixelData"])
def test_float_pixel_data_counts_as_pixel_data(keyword):
    dataset = _ct()
    del dataset.PixelData
    setattr(dataset, keyword, b"\x00" * 16)
    assert pixel_risk.assess_pixel_risk(dataset).pixel_data


@TRANSFER_SYNTAXES
def test_a_declared_burned_in_annotation_is_an_indicator(transfer_syntax):
    assessment = _assess(_ct(BurnedInAnnotation="YES"), transfer_syntax)
    assert _found(assessment) == {(Indicator.BURNED_IN_ANNOTATION, "(0028,0301)")}
    assert assessment.risks == {Risk.BURNED_IN_TEXT}


@TRANSFER_SYNTAXES
@pytest.mark.parametrize(
    "attribute", ["BurnedInAnnotation", "RecognizableVisualFeatures"]
)
def test_a_received_no_is_no_evidence_of_safety(transfer_syntax, attribute):
    said_no = _assess(_ct(**{attribute: "NO"}), transfer_syntax)
    said_nothing = _assess(_ct(), transfer_syntax)
    assert said_no == said_nothing


@TRANSFER_SYNTAXES
def test_declared_recognizable_visual_features_are_an_indicator(transfer_syntax):
    assessment = _assess(_ct(RecognizableVisualFeatures="YES"), transfer_syntax)
    assert _found(assessment) == {
        (Indicator.RECOGNIZABLE_VISUAL_FEATURES, "(0028,0302)")
    }
    assert assessment.risks == {Risk.RECONSTRUCTABLE_FACE}


@TRANSFER_SYNTAXES
@pytest.mark.parametrize(
    "image_type",
    [["DERIVED", "SECONDARY", "AXIAL"], ["ORIGINAL", "SECONDARY"]],
)
def test_a_secondary_image_is_an_indicator(transfer_syntax, image_type):
    assessment = _assess(_ct(ImageType=image_type), transfer_syntax)
    assert _found(assessment) == {(Indicator.SECONDARY_IMAGE, "(0008,0008)")}
    assert assessment.risks == {Risk.BURNED_IN_TEXT}


@pytest.mark.parametrize(
    "image_type", [["DERIVED", "PRIMARY", "AXIAL"], ["ORIGINAL"], [], "SECONDARY"]
)
def test_only_the_second_value_of_image_type_marks_a_secondary_image(image_type):
    assessment = pixel_risk.assess_pixel_risk(_ct(ImageType=image_type))
    assert not assessment.findings


@TRANSFER_SYNTAXES
def test_a_converted_image_is_an_indicator(transfer_syntax):
    assessment = _assess(_ct(ConversionType="WSD"), transfer_syntax)
    assert _found(assessment) == {(Indicator.CONVERTED_IMAGE, "(0008,0064)")}


def test_an_empty_conversion_type_is_still_an_indicator():
    # The attribute's presence says that the image was converted or captured.
    assessment = pixel_risk.assess_pixel_risk(_ct(ConversionType=""))
    assert _found(assessment) == {(Indicator.CONVERTED_IMAGE, "(0008,0064)")}


@TRANSFER_SYNTAXES
def test_an_overlay_without_overlay_data_may_be_in_the_pixel_data(transfer_syntax):
    dataset = _ct()
    dataset.add_new(0x60020010, "US", 2)  # Overlay Rows
    dataset.add_new(0x60020011, "US", 2)  # Overlay Columns
    dataset.add_new(0x60020102, "US", 12)  # Overlay Bit Position
    assessment = _assess(dataset, transfer_syntax)
    assert _found(assessment) == {(Indicator.EMBEDDED_OVERLAY, "(6002,0010)")}
    assert assessment.risks == {Risk.BURNED_IN_TEXT}


@TRANSFER_SYNTAXES
def test_an_overlay_with_its_own_overlay_data_is_not_in_the_pixel_data(transfer_syntax):
    dataset = _ct()
    dataset.add_new(0x60000010, "US", 2)
    dataset.add_new(0x60000011, "US", 2)
    dataset.add_new(0x60003000, "OW", b"\x00\x00")
    assert not _assess(dataset, transfer_syntax).findings


def test_odd_and_out_of_range_groups_are_not_overlays():
    dataset = _ct()
    dataset.add_new(0x60010010, "LO", "CREATOR")  # a private creator
    dataset.add_new(0x60200010, "US", 2)  # beyond the 16 overlay groups
    assert not pixel_risk.assess_pixel_risk(dataset).findings


@TRANSFER_SYNTAXES
def test_an_external_roi_with_contours_is_a_patient_surface(transfer_syntax):
    dataset = _structure_set(
        [_roi(1, "ORGAN"), _roi(7, "EXTERNAL")],
        [_contour(1, 2), _contour(7, 3)],
    )
    assessment = _assess(dataset, transfer_syntax)
    assert _found(assessment) == {
        (Indicator.PATIENT_SURFACE_CONTOUR, "(3006,0039)[1] > (3006,0040)")
    }
    assert assessment.risks == {Risk.RECONSTRUCTABLE_FACE}


@TRANSFER_SYNTAXES
def test_an_external_roi_without_contours_is_no_surface(transfer_syntax):
    dataset = _structure_set([_roi(7, "EXTERNAL")], [_contour(7, 0)])
    assert not _assess(dataset, transfer_syntax).findings


def test_each_external_roi_is_reported_once_whatever_its_observations():
    dataset = _structure_set(
        [_roi(7, "EXTERNAL"), _roi(7, "EXTERNAL"), _roi(8, "EXTERNAL")],
        [_contour(7, 1), _contour(8, 1)],
    )
    assert _found(pixel_risk.assess_pixel_risk(dataset)) == {
        (Indicator.PATIENT_SURFACE_CONTOUR, "(3006,0039)[0] > (3006,0040)"),
        (Indicator.PATIENT_SURFACE_CONTOUR, "(3006,0039)[1] > (3006,0040)"),
    }


@pytest.mark.parametrize("interpreted_type", ["ORGAN", "", "BODY"])
def test_only_external_marks_a_patient_surface(interpreted_type):
    dataset = _structure_set([_roi(1, interpreted_type)], [_contour(1, 2)])
    assert not pixel_risk.assess_pixel_risk(dataset).findings


def _with_raw(dataset, tag: int, vr, value: bytes | None, length=None):
    """Put an element into a data set as pydicom holds one read from a file."""
    length = len(value) if length is None else length
    # pylint: disable = protected-access
    dataset._dict[pydicom.tag.Tag(tag)] = RawDataElement(
        pydicom.tag.Tag(tag), vr, length, value, 0, vr is None, True
    )
    return dataset


@pytest.mark.parametrize("vr", [None, "UN"])
def test_an_attribute_without_its_vr_is_read_with_its_pinned_vr(vr):
    # An Implicit VR file gives no VR, and an Explicit VR file can hold an
    # attribute as UN, whose value is then in Implicit VR Little Endian.
    dataset = _with_raw(_ct(), 0x00280301, vr, b"YES ")
    assessment = pixel_risk.assess_pixel_risk(dataset)
    assert _found(assessment) == {(Indicator.BURNED_IN_ANNOTATION, "(0028,0301)")}


def test_a_sequence_read_as_un_is_read_as_implicit_vr_items():
    source = _read_back(
        _structure_set([_roi(7, "EXTERNAL")], [_contour(7, 1)]), IMPLICIT_LE
    )
    for tag in (0x30060080, 0x30060039):
        raw = source.get_item(tag, keep_deferred=True)
        # pylint: disable-next = protected-access
        source._dict[raw.tag] = raw._replace(VR="UN", is_implicit_VR=False)
    assert _found(pixel_risk.assess_pixel_risk(source)) == {
        (Indicator.PATIENT_SURFACE_CONTOUR, "(3006,0039)[0] > (3006,0040)")
    }


@pytest.mark.parametrize(
    "tag, vr, value, risk",
    [
        (0x00280301, "US", b"\x01\x00", Risk.BURNED_IN_TEXT),
        (0x00280302, "SQ", b"", Risk.RECONSTRUCTABLE_FACE),
        (0x00080008, "UL", b"\x00\x00\x00\x00", Risk.BURNED_IN_TEXT),
        (0x00080064, "DA", SENTINEL.encode(), Risk.BURNED_IN_TEXT),
    ],
)
def test_an_attribute_held_with_another_vr_is_unreadable_evidence(tag, vr, value, risk):
    dataset = _with_raw(_ct(), tag, vr, value)
    assessment = pixel_risk.assess_pixel_risk(dataset)
    path = f"({tag >> 16:04X},{tag & 0xFFFF:04X})"
    assert [(f.indicator, f.risk, str(f.path)) for f in assessment.findings] == [
        (Indicator.UNREADABLE, risk, path)
    ]


def test_a_deferred_value_is_unreadable_evidence():
    dataset = _with_raw(_ct(), 0x00280301, "CS", None, length=4)
    assert _found(pixel_risk.assess_pixel_risk(dataset)) == {
        (Indicator.UNREADABLE, "(0028,0301)")
    }


def test_a_value_shorter_than_its_length_is_unreadable_evidence():
    dataset = _with_raw(_ct(), 0x00280301, "CS", b"YE", length=4)
    assert _found(pixel_risk.assess_pixel_risk(dataset)) == {
        (Indicator.UNREADABLE, "(0028,0301)")
    }


def test_text_that_does_not_decode_is_unreadable_evidence():
    # A byte that the Default Character Repertoire does not hold.
    dataset = _with_raw(_ct(), 0x00080008, "CS", b"ORIGINAL\\SECOND\xc4RY")
    assert _found(pixel_risk.assess_pixel_risk(dataset)) == {
        (Indicator.UNREADABLE, "(0008,0008)")
    }


def test_a_sequence_whose_items_cannot_be_read_is_unreadable_evidence():
    garbage = struct.pack("<HHI", 0xFFFE, 0xE000, 64) + SENTINEL.encode()
    dataset = _with_raw(_structure_set([], []), 0x30060039, "SQ", garbage)
    assessment = pixel_risk.assess_pixel_risk(dataset)
    assert [(f.indicator, f.risk) for f in assessment.findings] == [
        (Indicator.UNREADABLE, Risk.RECONSTRUCTABLE_FACE)
    ]


def test_an_unreadable_item_element_is_located_in_its_item():
    dataset = _structure_set([_roi(7, "EXTERNAL")], [_contour(7, 1)])
    item = dataset.RTROIObservationsSequence[0]
    _with_raw(item, 0x300600A4, "US", b"\x01\x00")
    assert _found(pixel_risk.assess_pixel_risk(dataset)) == {
        (Indicator.UNREADABLE, "(3006,0080)[0] > (3006,00A4)")
    }


@TRANSFER_SYNTAXES
def test_assessment_leaves_the_data_set_as_it_was_read(transfer_syntax):
    dataset = _ct(
        BurnedInAnnotation="YES",
        RecognizableVisualFeatures="YES",
        ImageType=["DERIVED", "SECONDARY"],
        ConversionType="WSD",
    )
    if transfer_syntax is not None:
        dataset = _read_back(dataset, transfer_syntax)
    before = {tag: dataset.get_item(tag, keep_deferred=True) for tag in dataset.keys()}
    pixel_risk.assess_pixel_risk(dataset)
    after = {tag: dataset.get_item(tag, keep_deferred=True) for tag in dataset.keys()}
    assert after.keys() == before.keys()
    for tag, element in before.items():
        assert after[tag] is element


def test_a_structure_set_is_left_as_it_was_read():
    dataset = _read_back(
        _structure_set([_roi(7, "EXTERNAL")], [_contour(7, 1)]), EXPLICIT_LE
    )
    before = {tag: dataset.get_item(tag, keep_deferred=True) for tag in dataset.keys()}
    pixel_risk.assess_pixel_risk(dataset)
    for tag, element in before.items():
        assert dataset.get_item(tag, keep_deferred=True) is element


def test_findings_show_no_source_value():
    dataset = _with_raw(_ct(), 0x00080064, "DA", SENTINEL.encode())
    dataset.BurnedInAnnotation = "YES"
    assessment = pixel_risk.assess_pixel_risk(dataset)
    assert assessment.findings
    for text in (repr(assessment), str(assessment), *map(str, assessment.findings)):
        assert SENTINEL not in text


def test_each_indicator_bears_on_one_risk_except_unreadable_evidence():
    assert {indicator.risk for indicator in Indicator} == {
        Risk.BURNED_IN_TEXT,
        Risk.RECONSTRUCTABLE_FACE,
        None,
    }
    assert Indicator.UNREADABLE.risk is None


def test_a_finding_needs_a_risk_that_its_indicator_allows():
    path = ElementPath((), "(0028,0301)")
    with pytest.raises(ValueError):
        pixel_risk.Finding(
            Indicator.BURNED_IN_ANNOTATION, path, Risk.RECONSTRUCTABLE_FACE
        )
    with pytest.raises(ValueError):
        pixel_risk.Finding(Indicator.UNREADABLE, path, None)
    finding = pixel_risk.Finding(Indicator.BURNED_IN_ANNOTATION, path)
    assert finding.risk is Risk.BURNED_IN_TEXT


def test_the_attributes_read_have_their_pinned_vrs():
    dictionary = {
        entry.tag: entry.vr for entry in standard.load_data_dictionary().attributes
    }
    for tag, vr in pixel_risk.READ_VRS.items():
        assert dictionary[tag] == vr, tag


@pytest.mark.parametrize(
    "value",
    [
        b"+-1 ",
        b"--5 ",
        b"1.0 ",
        b"  ",
        b"1\\2 ",
        # Beyond Python's limit on converting digits to an int.
        pytest.param(b"9" * 5000, id="5000-digits"),
    ],
)
@pytest.mark.parametrize("where", [0x30060080, 0x30060039])
def test_a_malformed_roi_number_is_unreadable_evidence(value, where):
    dataset = _structure_set([_roi(7, "EXTERNAL")], [_contour(7, 1)])
    item = dataset[where].value[0]
    _with_raw(item, 0x30060084, "IS", value)
    assessment = pixel_risk.assess_pixel_risk(dataset)
    assert [(f.indicator, f.risk) for f in assessment.findings] == [
        (Indicator.UNREADABLE, Risk.RECONSTRUCTABLE_FACE)
    ]
    assert SENTINEL not in repr(assessment)


def test_findings_are_in_tag_order_whatever_their_depth():
    dataset = _structure_set([_roi(7, "EXTERNAL")], [_contour(7, 1)])
    dataset.add_new(0x60000010, "US", 2)
    dataset.BurnedInAnnotation = "YES"
    assert [str(f.path) for f in pixel_risk.assess_pixel_risk(dataset).findings] == [
        "(0028,0301)",
        "(3006,0039)[0] > (3006,0040)",
        "(6000,0010)",
    ]


@pytest.mark.parametrize("value", [b"+7", b"7 ", b" 7"])
def test_a_signed_or_padded_roi_number_is_read(value):
    dataset = _structure_set([_roi(7, "EXTERNAL")], [_contour(7, 1)])
    _with_raw(dataset.ROIContourSequence[0], 0x30060084, "IS", value)
    assert _found(pixel_risk.assess_pixel_risk(dataset)) == {
        (Indicator.PATIENT_SURFACE_CONTOUR, "(3006,0039)[0] > (3006,0040)")
    }


@TRANSFER_SYNTAXES
@pytest.mark.filterwarnings("ignore:Invalid value for VR CS")
def test_lower_case_values_still_give_their_indicators(transfer_syntax):
    # CS values are upper case (PS3.5 Table 6.2-1), but a writer that breaks
    # the rule should not hide an indicator.
    dataset = _ct(
        BurnedInAnnotation="yes",
        RecognizableVisualFeatures="Yes",
        ImageType=["DERIVED", "secondary"],
    )
    assert {f.indicator for f in _assess(dataset, transfer_syntax).findings} == {
        Indicator.BURNED_IN_ANNOTATION,
        Indicator.RECOGNIZABLE_VISUAL_FEATURES,
        Indicator.SECONDARY_IMAGE,
    }


CT_FOR_PROCESSING = "1.2.840.10008.5.1.4.1.1.2.3"
# Enhanced CT Image and Legacy Converted Enhanced CT Image, and their For
# Processing classes.
MULTI_FRAME_CT = [
    "1.2.840.10008.5.1.4.1.1.2.1",
    "1.2.840.10008.5.1.4.1.1.2.4",
    "1.2.840.10008.5.1.4.1.1.2.2",
    "1.2.840.10008.5.1.4.1.1.2.5",
]
RT_DOSE = "1.2.840.10008.5.1.4.1.1.481.2"


def _slice(number: int, **attributes) -> "pydicom.Dataset":
    dataset = _ct(**attributes)
    dataset.SOPInstanceUID = f"1.2.3.4.{number}"
    return dataset


def _series_found(findings) -> set[tuple[Indicator, tuple[int, ...], str | None]]:
    return {
        (f.indicator, f.instances, None if f.path is None else str(f.path))
        for f in findings
    }


@TRANSFER_SYNTAXES
def test_every_ct_volume_may_hold_a_reconstructable_face(transfer_syntax):
    series = [_slice(n) for n in range(3)]
    if transfer_syntax is not None:
        series = [_read_back(each, transfer_syntax) for each in series]
    findings = pixel_risk.assess_ct_series(series)
    assert _series_found(findings) == {(Indicator.CT_VOLUME, (0, 1, 2), None)}
    assert {f.risk for f in findings} == {Risk.RECONSTRUCTABLE_FACE}


def test_one_ct_image_is_no_volume():
    assert not pixel_risk.assess_ct_series([_slice(0)])
    assert not pixel_risk.assess_ct_series([])


def test_localizers_and_other_iods_are_not_part_of_a_volume():
    localizer = ["ORIGINAL", "PRIMARY", "LOCALIZER"]
    dose = _slice(2)
    dose.SOPClassUID = RT_DOSE
    series = [_slice(0), _slice(1, ImageType=localizer), dose]
    assert not pixel_risk.assess_ct_series(series)
    for_processing = _slice(3)
    for_processing.SOPClassUID = CT_FOR_PROCESSING
    findings = pixel_risk.assess_ct_series([*series, for_processing])
    assert _series_found(findings) == {(Indicator.CT_VOLUME, (0, 3), None)}


def test_a_ct_image_without_image_type_counts_towards_a_volume():
    series = [_slice(0), _slice(1)]
    del series[1].ImageType
    findings = pixel_risk.assess_ct_series(series)
    assert _series_found(findings) == {(Indicator.CT_VOLUME, (0, 1), None)}


@TRANSFER_SYNTAXES
@pytest.mark.parametrize("body_part", ["HEAD", "HEADNECK", "NECKCHEST", "WHOLEBODY"])
def test_a_volume_that_names_the_head_or_neck_says_so(transfer_syntax, body_part):
    series = [_slice(0), _slice(1, BodyPartExamined=body_part), _slice(2)]
    series[2].BodyPartExamined = body_part
    if transfer_syntax is not None:
        series = [_read_back(each, transfer_syntax) for each in series]
    assert _series_found(pixel_risk.assess_ct_series(series)) == {
        (Indicator.CT_VOLUME, (0, 1, 2), None),
        (Indicator.HEAD_OR_NECK, (1, 2), "(0018,0015)"),
    }


@pytest.mark.parametrize("body_part", ["CHEST", "PELVIS", "ABDOMEN", ""])
def test_a_volume_elsewhere_is_only_a_volume(body_part):
    series = [_slice(n, BodyPartExamined=body_part) for n in range(2)]
    assert _series_found(pixel_risk.assess_ct_series(series)) == {
        (Indicator.CT_VOLUME, (0, 1), None)
    }


def _region(code: str, scheme: str) -> "pydicom.Dataset":
    item = pydicom.Dataset()
    item.CodeValue = code
    item.CodingSchemeDesignator = scheme
    item.CodeMeaning = SENTINEL
    return item


@TRANSFER_SYNTAXES
@pytest.mark.parametrize("code, scheme", [("69536005", "SCT"), ("T-D1100", "SRT")])
def test_an_anatomic_region_code_can_name_the_head(transfer_syntax, code, scheme):
    series = [_slice(0), _slice(1)]
    series[0].AnatomicRegionSequence = [
        _region("51185008", "SCT"),
        _region(code, scheme),
    ]
    if transfer_syntax is not None:
        series = [_read_back(each, transfer_syntax) for each in series]
    assert _series_found(pixel_risk.assess_ct_series(series)) == {
        (Indicator.CT_VOLUME, (0, 1), None),
        (Indicator.HEAD_OR_NECK, (0,), "(0008,2218)[1] > (0008,0100)"),
    }


def test_a_code_of_another_scheme_names_nothing():
    series = [_slice(0), _slice(1)]
    series[0].AnatomicRegionSequence = [_region("69536005", "SRT")]
    assert _series_found(pixel_risk.assess_ct_series(series)) == {
        (Indicator.CT_VOLUME, (0, 1), None)
    }


def test_one_ct_image_of_the_head_is_no_volume():
    assert not pixel_risk.assess_ct_series([_slice(0, BodyPartExamined="HEAD")])


@pytest.mark.parametrize(
    "tag, vr, value, path",
    [
        (0x00180015, "US", b"\x01\x00", "(0018,0015)"),
        (0x00080016, "CS", b"CT\\IMAGE", "(0008,0016)"),
        (0x00080016, "UI", b"1.2.\xff", "(0008,0016)"),
        (0x00082218, "LO", SENTINEL.encode(), "(0008,2218)"),
    ],
)
def test_an_unreadable_attribute_of_a_ct_series_is_unreadable_evidence(
    tag, vr, value, path
):
    series = [_slice(0), _slice(1)]
    _with_raw(series[1], tag, vr, value)
    findings = pixel_risk.assess_ct_series(series)
    assert (Indicator.UNREADABLE, (1,), path) in _series_found(findings)
    # An instance whose SOP Class cannot be read may still be a CT image.
    assert (Indicator.CT_VOLUME, (0, 1), None) in _series_found(findings)
    assert all(f.risk is Risk.RECONSTRUCTABLE_FACE for f in findings)
    assert SENTINEL not in repr(findings)


def _multi_frame(number: int, sop_class: str, **attributes) -> "pydicom.Dataset":
    dataset = _slice(number, **attributes)
    dataset.SOPClassUID = sop_class
    return dataset


@TRANSFER_SYNTAXES
@pytest.mark.parametrize("sop_class", MULTI_FRAME_CT)
def test_one_multi_frame_ct_image_can_be_a_volume(transfer_syntax, sop_class):
    series = [_multi_frame(0, sop_class, NumberOfFrames=3, BodyPartExamined="HEAD")]
    if transfer_syntax is not None:
        series = [_read_back(each, transfer_syntax) for each in series]
    assert _series_found(pixel_risk.assess_ct_series(series)) == {
        (Indicator.CT_VOLUME, (0,), None),
        (Indicator.HEAD_OR_NECK, (0,), "(0018,0015)"),
    }


@pytest.mark.parametrize("sop_class", MULTI_FRAME_CT)
def test_single_frames_of_multi_frame_ct_images_add_up_to_a_volume(sop_class):
    one = _multi_frame(0, sop_class, NumberOfFrames=1)
    assert not pixel_risk.assess_ct_series([one])
    # Number of Frames is Type 1, but one missing must not hide a volume.
    other = _multi_frame(1, sop_class)
    assert _series_found(pixel_risk.assess_ct_series([one, other])) == {
        (Indicator.CT_VOLUME, (0, 1), None)
    }
    localizer = _multi_frame(
        2, sop_class, NumberOfFrames=5, ImageType=["ORIGINAL", "PRIMARY", "LOCALIZER"]
    )
    assert not pixel_risk.assess_ct_series([one, localizer])


@pytest.mark.parametrize("value", [b"0 ", b"-3", b"2\\3", b"many"])
def test_an_unreadable_number_of_frames_may_hide_a_volume(value):
    series = [_multi_frame(0, MULTI_FRAME_CT[0])]
    _with_raw(series[0], 0x00280008, "IS", value)
    assert _series_found(pixel_risk.assess_ct_series(series)) == {
        (Indicator.CT_VOLUME, (0,), None),
        (Indicator.UNREADABLE, (0,), "(0028,0008)"),
    }


def test_unreadable_evidence_is_reported_without_a_volume():
    lone = _slice(0)
    _with_raw(lone, 0x00080016, "UI", b"1.2.\xff")
    assert _series_found(pixel_risk.assess_ct_series([lone])) == {
        (Indicator.UNREADABLE, (0,), "(0008,0016)")
    }
    lone = _slice(0)
    _with_raw(lone, 0x00180015, "US", b"\x01\x00")
    assert _series_found(pixel_risk.assess_ct_series([lone])) == {
        (Indicator.UNREADABLE, (0,), "(0018,0015)")
    }


def test_more_than_one_sop_class_is_unreadable():
    series = [_slice(0), _slice(1)]
    _with_raw(series[1], 0x00080016, "UI", b"1.2.840.10008.5.1.4.1.1.2\\1.2.3")
    assert (Indicator.UNREADABLE, (1,), "(0008,0016)") in _series_found(
        pixel_risk.assess_ct_series(series)
    )


@pytest.mark.parametrize(
    "code, scheme", [("T-D1100", "SNM3"), ("69536005", "sct"), ("t-d1100", "SRT")]
)
def test_a_legacy_or_lower_case_code_names_the_head(code, scheme):
    series = [_slice(0), _slice(1)]
    series[0].AnatomicRegionSequence = [_region(code, scheme)]
    assert _series_found(pixel_risk.assess_ct_series(series)) == {
        (Indicator.CT_VOLUME, (0, 1), None),
        (Indicator.HEAD_OR_NECK, (0,), "(0008,2218)[0] > (0008,0100)"),
    }


@pytest.mark.parametrize(
    "tag, vr, value, path",
    [
        (0x00080102, "SH", b"SCT\xff", "(0008,2218)[0] > (0008,0102)"),
        (0x00080102, "SH", b"SCT\\SRT", "(0008,2218)[0] > (0008,0102)"),
        (0x00080100, "SH", b"69536005\\1", "(0008,2218)[0] > (0008,0100)"),
    ],
)
def test_an_unreadable_code_is_located_by_its_element(tag, vr, value, path):
    item = pydicom.Dataset()
    item.CodeValue = "69536005"
    item.CodingSchemeDesignator = "SCT"
    _with_raw(item, tag, vr, value)
    series = [_slice(0), _slice(1)]
    series[0].AnatomicRegionSequence = [item]
    assert _series_found(pixel_risk.assess_ct_series(series)) == {
        (Indicator.CT_VOLUME, (0, 1), None),
        (Indicator.UNREADABLE, (0,), path),
    }


def test_assessing_a_series_leaves_its_instances_as_they_were_read():
    series = [
        _read_back(_slice(n, BodyPartExamined="HEAD"), EXPLICIT_LE) for n in range(2)
    ]
    series[0] = _read_back(series[0], EXPLICIT_LE)
    before = [
        {tag: each.get_item(tag, keep_deferred=True) for tag in each.keys()}
        for each in series
    ]
    pixel_risk.assess_ct_series(series)
    for each, elements in zip(series, before):
        for tag, element in elements.items():
            assert each.get_item(tag, keep_deferred=True) is element


def test_the_head_and_neck_regions_are_a_reviewed_list_of_the_pinned_edition():
    regions = pixel_risk.load_head_and_neck_regions()
    assert regions.edition == standard.load_data_dictionary().edition
    assert {
        "HEAD",
        "FACE",
        "NECK",
        "HEADNECK",
        "BRAIN",
        "WHOLEBODY",
    } <= regions.body_parts
    assert not {"CHEST", "ABDOMEN", "PELVIS", "KNEE"} & regions.body_parts
    assert ("SCT", "69536005") in regions.codes
    assert ("SRT", "T-D1100") in regions.codes
    assert ("SNM3", "T-D1100") in regions.codes
    # Cervico-thoracic spine, which has no SNOMED RT identifier in Table L-1.
    assert ("SCT", "1217257000") in regions.codes
    assert all(code.isdigit() for scheme, code in regions.codes if scheme == "SCT")


@pytest.mark.parametrize(
    "text",
    [
        'schema = "other/1"\nedition = "2026d"\nacknowledgement = "DICOM PS3.16 2026d, © NEMA"\n',
        'schema = "pymedphys-deid-head-and-neck-regions/1"\nedition = "2026d"\n'
        'acknowledgement = "DICOM PS3.16 2026d, © NEMA"\n'
        '[[region]]\nmeaning = "Head"\nsrt = "T-D1100"\n',
        'schema = "pymedphys-deid-head-and-neck-regions/1"\nedition = "2026d"\n'
        'acknowledgement = "DICOM PS3.16 2026d, © NEMA"\n'
        '[[region]]\nmeaning = "Head"\nsct = "69536005"\nsrt = "T-D1100"\nbody_part = "head"\n',
        "not toml [",
    ],
    ids=["schema", "missing-field", "lower-case-term", "unreadable"],
)
def test_a_malformed_regions_file_is_refused(tmp_path, text):
    path = tmp_path / "regions.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        pixel_risk.load_head_and_neck_regions(path)


def test_a_regions_file_of_another_edition_is_refused(tmp_path):
    path = tmp_path / "regions.toml"
    path.write_text(
        'schema = "pymedphys-deid-head-and-neck-regions/1"\nedition = "2025a"\n'
        'acknowledgement = "DICOM PS3.16 2025a, © NEMA"\nregion = []\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        pixel_risk.load_head_and_neck_regions(path)
