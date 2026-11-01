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

"""The evaluation's conversion of synthetic classic CT, MR, and PET series
to Legacy Converted Enhanced instances, and the cases read from them."""

import argparse
import os

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import dicom_validators as validators
from pymedphys._dicom.deidentify import text_evaluation_command as command
from pymedphys._dicom.deidentify import text_evaluation_converted as converted
from pymedphys._dicom.deidentify import text_evaluation_idc as idc
from pymedphys._dicom.deidentify import text_evaluation_lce as lce
from pymedphys._dicom.deidentify.text_evaluation_frames import EvaluationRefused
from pymedphys._dicom.deidentify.text_evaluation_sources import (
    DicomCase,
    Skipped,
    decoded_frames,
    dicom_frames,
)

from . import _classic_images as classic

MODALITIES = ("CT", "MR", "PT")
LCE = {
    "CT": lce.LCE_CT_IMAGE,
    "MR": lce.LCE_MR_IMAGE,
    "PT": lce.LCE_PET_IMAGE,
}


def _images(datasets):
    images = []
    for dataset in datasets:
        decoded = decoded_frames(classic.encoded(dataset))
        assert not isinstance(decoded, Skipped)
        read, _, frames = decoded
        images.append(lce.ClassicImage(read, frames[0]))
    return images


def _converted(modality, **options):
    images = _images(classic.classic_series(modality, **options))
    return images, lce.convert(images, [image.dataset for image in images])


def _shared(dataset):
    (group,) = dataset.SharedFunctionalGroupsSequence
    return group


@pytest.mark.parametrize("modality", MODALITIES)
def test_each_frame_holds_its_images_stored_values(modality):
    images, dataset = _converted(modality, slices=4)
    assert dataset.SOPClassUID == LCE[modality]
    assert dataset.NumberOfFrames == 4
    data = lce.encode(dataset)
    frames = dicom_frames(data, collection="c", case="k", tier="T3")
    originals = [
        dicom_frames(classic.encoded(each), collection="c", case="k", tier="T3")[0]
        for each in classic.classic_series(modality, slices=4)
    ]
    assert [frame.number for frame in frames] == [0, 1, 2, 3]
    for frame, image, original in zip(frames, images, originals):
        assert frame.stored.dtype == image.stored.dtype
        assert np.array_equal(frame.stored, image.stored)
        assert frame.iod.startswith("Legacy Converted Enhanced")
        assert frame.iod != original.iod
        # What the detector is given beside the values is read the same.
        for name in (
            "pixel_spacing",
            "slope",
            "intercept",
            "stored_range",
            "photometric",
            "modality",
        ):
            assert getattr(frame, name) == getattr(original, name), name


def test_shared_and_per_frame_attributes_are_placed_apart():
    _, dataset = _converted("MR")
    shared = _shared(dataset)
    frames = list(dataset.PerFrameFunctionalGroupsSequence)
    # Identical in every image, so shared; differing, so per frame.
    assert shared.PixelMeasuresSequence[0].PixelSpacing == [0.8, 0.8]
    assert "PlanePositionSequence" not in shared
    assert [
        float(frame.PlanePositionSequence[0].ImagePositionPatient[2])
        for frame in frames
    ] == [1.5, 3.0, 4.5]
    unassigned = shared.UnassignedSharedConvertedAttributesSequence[0]
    assert unassigned.RepetitionTime == 500
    # The classic Series Instance UID, which the instance replaces.
    assert unassigned.SeriesInstanceUID == f"{classic.ROOT}41"
    assert dataset.SeriesInstanceUID != unassigned.SeriesInstanceUID
    per_frame = [
        frame.UnassignedPerFrameConvertedAttributesSequence[0] for frame in frames
    ]
    assert [item.InstanceNumber for item in per_frame] == [1, 2, 3]
    assert dataset.InstanceNumber == 1
    sources = [frame.ConversionSourceAttributesSequence[0] for frame in frames]
    assert [item.ReferencedSOPInstanceUID for item in sources] == [
        f"{classic.ROOT}31{number:03d}" for number in (1, 2, 3)
    ]


def test_private_attributes_keep_their_creator_in_their_own_block():
    _, dataset = _converted("CT")
    shared = _shared(dataset).UnassignedSharedConvertedAttributesSequence[0]
    block = shared.private_block(0x0009, "SYNTHETIC CONVERSION")
    assert block[0x01].value == "shared"
    for number, frame in enumerate(dataset.PerFrameFunctionalGroupsSequence, 1):
        item = frame.UnassignedPerFrameConvertedAttributesSequence[0]
        assert item.private_block(0x0009, "SYNTHETIC CONVERSION")[0x02].value == number
    assert not [element for element in dataset if element.tag.is_private]


def test_an_attribute_whose_enhanced_module_it_would_begin_is_unassigned():
    # The classic Contrast/Bolus Agent Sequence is also the Enhanced
    # Contrast/Bolus Module's, whose other Type 1 attributes the classic
    # images lack.
    _, dataset = _converted("MR")
    assert "ContrastBolusAgentSequence" not in dataset
    shared = _shared(dataset).UnassignedSharedConvertedAttributesSequence[0]
    assert shared.ContrastBolusAgentSequence[0].CodeValue == "387467008"
    assert dataset.ContrastBolusAgent == "Synthetic agent"


@pytest.mark.parametrize("modality", MODALITIES)
def test_frame_anatomy_codes_body_part_examined_by_annex_l(modality):
    _, dataset = _converted(modality)
    anatomy = _shared(dataset).FrameAnatomySequence[0]
    (region,) = anatomy.AnatomicRegionSequence
    assert (region.CodingSchemeDesignator, region.CodeValue) == ("SCT", "816094009")
    assert anatomy.FrameLaterality == "U"


def test_frame_anatomy_is_left_out_where_no_body_part_is_coded():
    # PS3.3 requires Frame Anatomy only where Body Part Examined is one of
    # Annex L's terms, or an Anatomic Region Sequence is given.
    datasets = classic.classic_series("CT")
    for dataset in datasets:
        dataset.BodyPartExamined = "NOTAPART"
    dataset = lce.convert(_images(datasets))
    assert "FrameAnatomySequence" not in _shared(dataset)
    assert "FrameAnatomySequence" not in dataset.PerFrameFunctionalGroupsSequence[0]


@pytest.mark.parametrize("other", ["NOTAPART", "FETALHEART"])
def test_frames_that_cannot_all_be_coded_are_refused(other):
    # FETALHEART is one of Annex L's terms that it gives no code.
    datasets = classic.classic_series("CT")
    datasets[1].BodyPartExamined = other
    with pytest.raises(lce.ConversionRefused) as refused:
        lce.convert(_images(datasets))
    assert refused.value.reason == "anatomic-region-not-coded"


def test_evidence_names_the_referenced_images_by_study_and_series():
    _, dataset = _converted("CT")
    (study,) = dataset.ReferencedImageEvidenceSequence
    assert study.StudyInstanceUID == classic.STUDY
    (series,) = study.ReferencedSeriesSequence
    assert series.SeriesInstanceUID == f"{classic.ROOT}41"
    assert [each.ReferencedSOPInstanceUID for each in series.ReferencedSOPSequence] == [
        f"{classic.ROOT}31001"
    ]
    # A reference whose study and series are unknown is left out.
    images = _images(classic.classic_series("CT"))
    alone = lce.convert(images[1:])
    assert "ReferencedImageEvidenceSequence" not in alone


def test_a_conversion_is_repeatable_and_its_uids_are_new():
    images, first = _converted("PT")
    second = lce.convert(images, [image.dataset for image in images])
    assert first.SOPInstanceUID == second.SOPInstanceUID
    assert first.SeriesInstanceUID == second.SeriesInstanceUID
    originals = {image.dataset.SOPInstanceUID for image in images}
    assert first.SOPInstanceUID not in originals
    assert lce.encode(first) == lce.encode(second)
    other = lce.convert(_images(classic.classic_series("PT", seed=1, series=2)))
    assert other.SOPInstanceUID != first.SOPInstanceUID


def test_images_are_grouped_by_class_study_frame_of_reference_and_layout():
    ct = classic.classic_series("CT", slices=2)
    mr = classic.classic_series("MR", slices=2, series=2)
    wider = classic.classic_series("CT", slices=1, series=3, columns=14)
    images = _images([mr[1], ct[1], *wider, ct[0], mr[0]])
    groups, refused = lce.convertible_groups(images)
    assert not refused
    assert [[image.dataset.SOPInstanceUID for image in group] for group in groups] == [
        [mr[0].SOPInstanceUID, mr[1].SOPInstanceUID],
        [ct[0].SOPInstanceUID, ct[1].SOPInstanceUID],
        [wider[0].SOPInstanceUID],
    ]
    with pytest.raises(lce.ConversionRefused) as refused_error:
        lce.convert(images)
    assert refused_error.value.reason == "not-one-group"


def _refused(change):
    (dataset,) = classic.classic_series("CT", slices=1)
    (image,) = _images([dataset])
    change(image.dataset)
    _, refused = lce.convertible_groups([image])
    return [reason for _, reason in refused]


def _bits(dataset):
    dataset.BitsStored = 14
    dataset.HighBit = 13


def _multi_energy(dataset):
    dataset.MultienergyCTAcquisition = "YES"


@pytest.mark.parametrize(
    "change, reason",
    [
        (lambda d: setattr(d, "SOPClassUID", "1.2.840.10008.5.1.4.1.1.7"),
         "not-a-classic-ct-mr-or-pet-image"),
        (lambda d: setattr(d, "NumberOfFrames", 2), "not-single-frame"),
        (lambda d: setattr(d, "PhotometricInterpretation", "MONOCHROME1"),
         "photometric-interpretation"),
        (_bits, "bits-not-allowed"),
        (lambda d: setattr(d, "HighBit", 15), "high-bit"),
        (lambda d: setattr(d, "ModalityLUTSequence", [pydicom.Dataset()]),
         "modality-lut"),
        (_multi_energy, "multi-energy"),
        (lambda d: setattr(d, "SOPInstanceUID", ""), "uid-missing"),
    ],
)  # fmt: skip
def test_an_image_the_iod_cannot_hold_unchanged_is_refused(change, reason):
    assert _refused(change) == [reason]


def test_an_image_without_its_geometry_is_refused():
    datasets = classic.classic_series("MR")
    for dataset in datasets:
        del dataset.SliceThickness
    with pytest.raises(lce.ConversionRefused) as refused:
        lce.convert(_images(datasets))
    assert refused.value.reason == "slice-thickness-missing"


def _folder(tmp_path, datasets):
    paths = []
    for number, dataset in enumerate(datasets):
        path = tmp_path / f"{number}.dcm"
        path.write_bytes(classic.encoded(dataset))
        paths.append(str(path))
    return paths


def test_a_converted_case_reads_the_frames_of_its_converted_instances(tmp_path):
    ct = classic.classic_series("CT", slices=3)
    refused = classic.classic_series("MR", slices=1, series=2)
    refused[0].PhotometricInterpretation = "MONOCHROME1"
    paths = _folder(tmp_path, [*ct, *refused])
    source = DicomCase("c", "k", tuple(paths), known_text="none", tier="T3")
    case = converted.ConvertedCase(source)
    assert (case.collection, case.case) == ("c", "k")
    read = list(case.read())
    skipped = [each.reason for each in read if isinstance(each, Skipped)]
    frames = [each for each in read if not isinstance(each, Skipped)]
    assert skipped == ["conversion-refused/photometric-interpretation"]
    assert {frame.iod for frame in frames} == {
        "Legacy Converted Enhanced CT Image Storage"
    }
    assert {(frame.tier, frame.known_text) for frame in frames} == {("T3", "none")}
    unconverted = [
        each
        for each in DicomCase("c", "k", tuple(paths[:3]), tier="T3").read()
        if not isinstance(each, Skipped)
    ]
    assert len(frames) == len(unconverted) == 3
    for frame, original in zip(frames, unconverted):
        assert np.array_equal(frame.stored, original.stored)


def test_a_group_too_large_to_convert_is_skipped_image_by_image(tmp_path, monkeypatch):
    paths = _folder(tmp_path, classic.classic_series("PT", slices=2))
    monkeypatch.setattr(converted, "MAX_CONVERTED_BYTES", 16 * 12 * 2)
    read = list(converted.ConvertedCase(DicomCase("c", "k", tuple(paths))).read())
    assert [each.reason for each in read] == ["conversion-refused/too-large"] * 2


def test_a_converted_case_may_not_carry_annotations():
    source = DicomCase("c", "k", (), annotations=object())
    with pytest.raises(EvaluationRefused):
        converted.ConvertedCase(source)


def _series(tmp_path, datasets, number=1, sop_class=classic.MODALITIES["CT"]):
    uuid = f"0123abcd-0000-4000-8000-{number:012d}"
    series = idc.IdcSeries(
        collection_id="lidc_idri",
        series_instance_uid=datasets[0].SeriesInstanceUID,
        crdc_series_uuid=uuid,
        modality=datasets[0].Modality,
        sop_class_uid=sop_class,
        licence="CC BY 3.0",
        doi="10.7937/K9/TCIA.2015.LO9QL9SX",
        size_mb=1.0,
        aws_url=f"s3://idc-open-data/{uuid}/*",
    )
    folder = tmp_path / uuid
    folder.mkdir()
    _folder(folder, datasets)
    return series


def test_an_idc_series_is_read_converted_where_asked(tmp_path):
    series = _series(tmp_path, classic.classic_series("CT"))
    plain = list(idc.IdcSeriesCase(series, tmp_path).read())
    as_converted = list(idc.IdcSeriesCase(series, tmp_path, converted=True).read())
    assert {frame.iod for frame in plain} == {"CT Image Storage"}
    assert {frame.iod for frame in as_converted} == {
        "Legacy Converted Enhanced CT Image Storage"
    }
    for frame, original in zip(as_converted, plain, strict=True):
        assert np.array_equal(frame.stored, original.stored)


def test_the_converted_measurement_takes_classic_ct_mr_and_pet_series_alone(
    tmp_path, monkeypatch
):
    ct = _series(tmp_path, classic.classic_series("CT"), 1)
    other = _series(
        tmp_path,
        classic.classic_series("MR", series=2),
        2,
        sop_class="1.2.840.10008.5.1.4.1.1.1.1",
    )
    monkeypatch.setattr(command, "read_series", lambda _: (ct, other))
    arguments = argparse.Namespace(series="s", downloads=str(tmp_path), converted=True)
    (case,) = command._cases(arguments)  # pylint: disable = protected-access
    assert case.series == ct and case.converted
    arguments.converted = False
    assert len(command._cases(arguments)) == 2  # pylint: disable = protected-access


def _dciodvfy():
    executable = validators.find_executable(validators.DCIODVFY)
    if executable is None:
        if os.environ.get("PYMEDPHYS_DICOM_VALIDATORS") == "required":
            pytest.fail("dciodvfy is not on the PATH.")
        pytest.skip("dciodvfy is not on the PATH.")
    return executable


def _errors(executable, path):
    validation = validators.run_dciodvfy(executable, path)
    assert validation.status == validators.Status.VALIDATED
    return sorted(
        f"{finding.path} {finding.message}"
        for finding in validation.findings
        if finding.severity == validators.ERROR
    )


@pytest.mark.pydicom
@pytest.mark.dicom_validators
@pytest.mark.parametrize("modality", MODALITIES)
def test_dciodvfy_finds_no_error_in_a_converted_instance(modality, tmp_path):
    executable = _dciodvfy()
    datasets = classic.classic_series(modality)
    for number, dataset in enumerate(datasets):
        path = tmp_path / f"classic-{number}.dcm"
        path.write_bytes(classic.encoded(dataset))
        assert not _errors(executable, path)
    _, dataset = _converted(modality)
    path = tmp_path / "converted.dcm"
    path.write_bytes(lce.encode(dataset))
    validation = validators.run_dciodvfy(executable, path)
    assert validation.iod.startswith("LegacyConvertedEnhanced"), validation.iod
    assert not _errors(executable, path)
