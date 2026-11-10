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

"""Which instances the first supported release de-identifies, and which it sequesters."""

import dataclasses

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import iods, scope, sop_classes, uid_registry

Disposition = scope.Disposition

IMPLICIT_LE = "1.2.840.10008.1.2"
EXPLICIT_LE = "1.2.840.10008.1.2.1"
# The transfer syntaxes that encapsulate Pixel Data and that pydicom 3.0.2's
# decoding plugins decode (PS3.5 Section A.4).
COMPRESSED = {
    "1.2.840.10008.1.2.4.50": "JPEG Baseline (Process 1)",
    "1.2.840.10008.1.2.4.51": "JPEG Extended (Process 2 & 4)",
    "1.2.840.10008.1.2.4.57": "JPEG Lossless, Non-Hierarchical (Process 14)",
    "1.2.840.10008.1.2.4.70": (
        "JPEG Lossless, Non-Hierarchical, First-Order Prediction "
        "(Process 14 [Selection Value 1])"
    ),
    "1.2.840.10008.1.2.4.80": "JPEG-LS Lossless Image Compression",
    "1.2.840.10008.1.2.4.81": "JPEG-LS Lossy (Near-Lossless) Image Compression",
    "1.2.840.10008.1.2.4.90": "JPEG 2000 Image Compression (Lossless Only)",
    "1.2.840.10008.1.2.4.91": "JPEG 2000 Image Compression",
    "1.2.840.10008.1.2.4.201": "High-Throughput JPEG 2000 Image Compression (Lossless Only)",
    "1.2.840.10008.1.2.4.202": (
        "High-Throughput JPEG 2000 with RPCL Options Image Compression (Lossless Only)"
    ),
    "1.2.840.10008.1.2.4.203": "High-Throughput JPEG 2000 Image Compression",
    "1.2.840.10008.1.2.5": "RLE Lossless",
}

# The Storage SOP Classes of the first release's IODs, from Table B.5-1 of the
# 2026d PS3.4.
SUPPORTED = {
    "1.2.840.10008.5.1.4.1.1.2": "CT Image",  # CT Image Storage
    "1.2.840.10008.5.1.4.1.1.2.3": "CT Image",  # CT Image Storage - For Processing
    "1.2.840.10008.5.1.4.1.1.2.1": "Enhanced CT Image",
    "1.2.840.10008.5.1.4.1.1.2.4": "Enhanced CT Image",  # For Processing
    "1.2.840.10008.5.1.4.1.1.2.2": "Legacy Converted Enhanced CT Image",
    "1.2.840.10008.5.1.4.1.1.2.5": "Legacy Converted Enhanced CT Image",
    "1.2.840.10008.5.1.4.1.1.4": "MR Image",
    "1.2.840.10008.5.1.4.1.1.4.1": "Enhanced MR Image",
    "1.2.840.10008.5.1.4.1.1.4.2": "MR Spectroscopy",
    "1.2.840.10008.5.1.4.1.1.4.3": "Enhanced MR Color Image",
    "1.2.840.10008.5.1.4.1.1.4.4": "Legacy Converted Enhanced MR Image",
    "1.2.840.10008.5.1.4.1.1.20": "Nuclear Medicine Image",
    "1.2.840.10008.5.1.4.1.1.128": "Positron Emission Tomography Image",
    "1.2.840.10008.5.1.4.1.1.130": "Enhanced PET Image",
    "1.2.840.10008.5.1.4.1.1.128.1": "Legacy Converted Enhanced PET Image",
    "1.2.840.10008.5.1.4.1.1.481.1": "RT Image",
    "1.2.840.10008.5.1.4.1.1.481.2": "RT Dose",
    "1.2.840.10008.5.1.4.1.1.481.3": "RT Structure Set",
    "1.2.840.10008.5.1.4.1.1.481.4": "RT Beams Treatment Record",
    "1.2.840.10008.5.1.4.1.1.481.5": "RT Plan",
    "1.2.840.10008.5.1.4.1.1.481.6": "RT Brachy Treatment Record",
    "1.2.840.10008.5.1.4.1.1.481.7": "RT Treatment Summary Record",
    "1.2.840.10008.5.1.4.1.1.481.8": "RT Ion Plan",
    "1.2.840.10008.5.1.4.1.1.481.9": "RT Ion Beams Treatment Record",
    "1.2.840.10008.5.1.4.1.1.481.23": "Enhanced RT Image",
    "1.2.840.10008.5.1.4.1.1.481.24": "Enhanced Continuous RT Image",
    "1.2.840.10008.5.1.4.1.1.481.11": "RT Segment Annotation",
    "1.2.840.10008.5.1.4.1.1.481.12": "RT Radiation Set",
    "1.2.840.10008.5.1.4.1.1.481.13": "C-Arm Photon-Electron Radiation",
    "1.2.840.10008.5.1.4.1.1.481.14": "Tomotherapeutic Radiation",
    "1.2.840.10008.5.1.4.1.1.481.15": "Robotic-Arm Radiation",
    "1.2.840.10008.5.1.4.1.1.481.21": "RT Radiation Set Delivery Instruction",
    "1.2.840.10008.5.1.4.34.7": "RT Beams Delivery Instruction",
    "1.2.840.10008.5.1.4.34.10": "RT Brachy Application Setup Delivery Instruction",
    "1.2.840.10008.5.1.4.1.1.66.1": "Spatial Registration",
    "1.2.840.10008.5.1.4.1.1.66.3": "Deformable Spatial Registration",
    "1.2.840.10008.5.1.4.1.1.66.4": "Segmentation",
    # Label Map Segmentation Storage, which Table B.5-1 maps to the same IOD.
    "1.2.840.10008.5.1.4.1.1.66.7": "Segmentation",
    # Surface Segmentation Storage, which Table B.5-1 maps to an IOD of its own.
    "1.2.840.10008.5.1.4.1.1.66.5": "Surface Segmentation",
    "1.2.840.10008.5.1.4.1.1.88.67": "X-Ray Radiation Dose SR",
    "1.2.840.10008.5.1.4.1.1.88.68": "Radiopharmaceutical Radiation Dose SR",
    "1.2.840.10008.5.1.4.1.1.88.73": "Patient Radiation Dose SR",
    "1.2.840.10008.5.1.4.1.1.88.76": "Enhanced X-Ray Radiation Dose SR",
    "1.2.840.10008.5.1.4.1.1.88.11": "Basic Text SR",
    "1.2.840.10008.5.1.4.1.1.88.22": "Enhanced SR",
    "1.2.840.10008.5.1.4.1.1.88.33": "Comprehensive SR",
    "1.2.840.10008.5.1.4.1.1.88.34": "Comprehensive 3D SR",
    "1.2.840.10008.5.1.4.1.1.88.35": "Extensible SR",
    "1.2.840.10008.5.1.4.1.1.88.59": "Key Object Selection Document",
    "1.2.840.10008.5.1.4.1.1.88.50": "Mammography CAD SR",
    "1.2.840.10008.5.1.4.1.1.88.65": "Chest CAD SR",
    "1.2.840.10008.5.1.4.1.1.88.69": "Colon CAD SR",
    "1.2.840.10008.5.1.4.1.1.88.40": "Procedure Log",
    "1.2.840.10008.5.1.4.1.1.78.6": "Spectacle Prescription Report",
    "1.2.840.10008.5.1.4.1.1.79.1": "Macular Grid Thickness and Volume Report",
    "1.2.840.10008.5.1.4.1.1.88.77": "Waveform Annotation SR",
    "1.2.840.10008.5.1.4.1.1.30": "Parametric Map",
    "1.2.840.10008.5.1.4.1.1.67": "Real World Value Mapping",
    "1.2.840.10008.5.1.4.1.1.11.1": "Grayscale Softcopy Presentation State",
    "1.2.840.10008.5.1.4.1.1.11.2": "Color Softcopy Presentation State",
    "1.2.840.10008.5.1.4.1.1.11.3": "Pseudo-Color Softcopy Presentation State",
    "1.2.840.10008.5.1.4.1.1.11.4": "Blending Softcopy Presentation State",
    "1.2.840.10008.5.1.4.1.1.11.5": "XA/XRF Grayscale Softcopy Presentation State",
    "1.2.840.10008.5.1.4.1.1.11.12": (
        "Variable Modality LUT Softcopy Presentation State"
    ),
    "1.2.840.10008.5.1.4.1.1.104.1": "Encapsulated PDF",
}


def test_the_first_release_supports_ct_mr_pet_rt_registration_seg_sr_and_pr_objects():
    assert scope.SUPPORTED_IODS == {
        "CT Image",
        "Enhanced CT Image",
        "Legacy Converted Enhanced CT Image",
        "MR Image",
        "Enhanced MR Image",
        "Enhanced MR Color Image",
        "Legacy Converted Enhanced MR Image",
        "MR Spectroscopy",
        "Nuclear Medicine Image",
        "Positron Emission Tomography Image",
        "Enhanced PET Image",
        "Legacy Converted Enhanced PET Image",
        "RT Beams Delivery Instruction",
        "RT Beams Treatment Record",
        "RT Brachy Application Setup Delivery Instruction",
        "RT Brachy Treatment Record",
        "RT Dose",
        "RT Image",
        "Enhanced RT Image",
        "Enhanced Continuous RT Image",
        "RT Segment Annotation",
        "RT Radiation Set",
        "C-Arm Photon-Electron Radiation",
        "Tomotherapeutic Radiation",
        "Robotic-Arm Radiation",
        "RT Ion Beams Treatment Record",
        "RT Ion Plan",
        "RT Plan",
        "RT Radiation Set Delivery Instruction",
        "RT Structure Set",
        "RT Treatment Summary Record",
        "Segmentation",
        "Surface Segmentation",
        "Spatial Registration",
        "Deformable Spatial Registration",
        "X-Ray Radiation Dose SR",
        "Enhanced X-Ray Radiation Dose SR",
        "Radiopharmaceutical Radiation Dose SR",
        "Patient Radiation Dose SR",
        "Basic Text SR",
        "Enhanced SR",
        "Comprehensive SR",
        "Comprehensive 3D SR",
        "Extensible SR",
        "Key Object Selection Document",
        "Mammography CAD SR",
        "Chest CAD SR",
        "Colon CAD SR",
        "Procedure Log",
        "Spectacle Prescription Report",
        "Macular Grid Thickness and Volume Report",
        "Waveform Annotation SR",
        "Parametric Map",
        "Real World Value Mapping",
        "Grayscale Softcopy Presentation State",
        "Color Softcopy Presentation State",
        "Pseudo-Color Softcopy Presentation State",
        "Blending Softcopy Presentation State",
        "XA/XRF Grayscale Softcopy Presentation State",
        "Variable Modality LUT Softcopy Presentation State",
        "Encapsulated PDF",
    }
    assert scope.SUPPORTED_TRANSFER_SYNTAXES == {IMPLICIT_LE, EXPLICIT_LE, *COMPRESSED}


def test_every_supported_iod_has_generated_types():
    assert scope.SUPPORTED_IODS <= set(iods.load_iod_tables().iods)


def test_the_supported_transfer_syntaxes_are_current_in_ps3_6():
    registered = {
        uid.uid: uid
        for uid in uid_registry.load_uid_values().rows
        if uid.uid_type == "Transfer Syntax"
    }

    assert registered[IMPLICIT_LE].name.startswith("Implicit VR Little Endian")
    assert registered[EXPLICIT_LE].name == "Explicit VR Little Endian"
    for uid, name in COMPRESSED.items():
        assert registered[uid].name.startswith(name), uid
    assert not any(registered[uid].retired for uid in scope.SUPPORTED_TRANSFER_SYNTAXES)


def test_only_the_storage_sop_classes_of_the_supported_iods_are_supported():
    # A new edition that maps another SOP Class to a supported IOD fails
    # here once its tables are regenerated.
    supported = {
        row.uid
        for row in sop_classes.load_storage_sop_classes().rows
        if scope.classify(row.uid, EXPLICIT_LE).disposition is Disposition.SUPPORTED
    }

    assert supported == set(SUPPORTED)


@pytest.mark.parametrize("sop_class, iod", SUPPORTED.items())
@pytest.mark.parametrize("transfer_syntax", [IMPLICIT_LE, EXPLICIT_LE])
def test_a_supported_instance_is_de_identified(sop_class, iod, transfer_syntax):
    found = scope.classify(sop_class, transfer_syntax)

    assert found == scope.Classification(Disposition.SUPPORTED, iod)
    assert not found.sequestered


def test_padding_is_ignored():
    # PS3.5 Section 9.1 pads an odd-length UID with a NUL; some writers pad
    # with a space.
    found = scope.classify("1.2.840.10008.5.1.4.1.1.481.5\x00", EXPLICIT_LE + "\x00")

    assert found.disposition is Disposition.SUPPORTED
    assert scope.classify("1.2.840.10008.5.1.4.1.1.2 ", IMPLICIT_LE + " ") == (
        scope.Classification(Disposition.SUPPORTED, "CT Image")
    )


@pytest.mark.deid_requirement("MIDI-BP-06")
@pytest.mark.parametrize(
    "sop_class, iod",
    [
        # The other Structured Reports, which the design always sequesters,
        # and the volumetric, advanced blending, and waveform Presentation
        # States, which later changes are to bring into scope.
        ("1.2.840.10008.5.1.4.1.1.88.72", "Simplified Adult Echo SR"),
        ("1.2.840.10008.5.1.4.1.1.88.71", "Acquisition Context SR"),
        (
            "1.2.840.10008.5.1.4.1.1.11.6",
            "Planar MPR Volumetric Presentation State",
        ),
        (
            "1.2.840.10008.5.1.4.1.1.11.9",
            "Volume Rendering Volumetric Presentation State",
        ),
        ("1.2.840.10008.5.1.4.1.1.11.8", "Advanced Blending Presentation State"),
        ("1.2.840.10008.5.1.4.1.1.9.100.1", "Waveform Presentation State"),
        # Outside the first release: other images, CT, MR, and PET objects
        # that are not images, height map segmentations, spatial fiducials,
        # and the second-generation RT objects not yet supported, such as RT
        # Physician Intent and the radiation records.
        ("1.2.840.10008.5.1.4.1.1.6.1", "Ultrasound Image"),
        ("1.2.840.10008.5.1.4.1.1.200.2", "CT Performed Procedure Protocol"),
        ("1.2.840.10008.5.1.4.1.1.66.8", "Height Map Segmentation"),
        ("1.2.840.10008.5.1.4.1.1.66.2", "Spatial Fiducials"),
        ("1.2.840.10008.5.1.4.1.1.481.10", "RT Physician Intent"),
        ("1.2.840.10008.5.1.4.1.1.481.18", "Tomotherapeutic Radiation Record"),
        # The encapsulated documents other than PDF: a CDA document, whose
        # XML is text throughout, and the 3D models and their materials.
        ("1.2.840.10008.5.1.4.1.1.104.2", "Encapsulated CDA"),
        ("1.2.840.10008.5.1.4.1.1.104.3", "Encapsulated STL"),
        ("1.2.840.10008.5.1.4.1.1.104.4", "Encapsulated OBJ"),
        ("1.2.840.10008.5.1.4.1.1.104.5", "Encapsulated MTL"),
    ],
)
def test_a_standard_sop_class_of_another_iod_is_sequestered(sop_class, iod):
    found = scope.classify(sop_class, EXPLICIT_LE)

    assert found == scope.Classification(Disposition.UNSUPPORTED_IOD, iod)
    assert found.sequestered
    # Its reason names the IOD, for the release report (D-010).
    assert found.reason == scope.UnsupportedIod(iod)
    assert found.reason.code is Disposition.UNSUPPORTED_IOD


@pytest.mark.deid_requirement("MIDI-BP-06")
@pytest.mark.parametrize(
    "sop_class",
    [
        # A Private SOP Class under an invented root.
        "1.2.3.4.5",
        # The retired Nuclear Medicine Image Storage, Hanging Protocol Storage,
        # which another service class defines, and Verification.
        "1.2.840.10008.5.1.4.1.1.5",
        "1.2.840.10008.5.1.4.38.1",
        "1.2.840.10008.1.1",
        # Not a UID.
        "1.02",
        "CT",
    ],
)
def test_a_sop_class_that_table_b_5_1_does_not_list_is_sequestered(sop_class):
    found = scope.classify(sop_class, EXPLICIT_LE)

    assert found == scope.Classification(Disposition.UNLISTED_SOP_CLASS, None)
    assert found.sequestered


@pytest.mark.parametrize("sop_class", [None, "", " ", "\x00", 1, b"1.2"])
def test_an_instance_without_a_sop_class_is_sequestered(sop_class):
    found = scope.classify(sop_class, EXPLICIT_LE)

    assert found == scope.Classification(Disposition.NO_SOP_CLASS, None)


@pytest.mark.deid_requirement("MIDI-BP-14")
@pytest.mark.parametrize(
    "transfer_syntax",
    [
        "1.2.840.10008.1.2.2",  # Explicit VR Big Endian, retired
        "1.2.840.10008.1.2.1.98",  # Encapsulated Uncompressed Explicit VR LE
        "1.2.840.10008.1.2.1.99",  # Deflated Explicit VR Little Endian
        "1.2.840.10008.1.2.4.92",  # JPEG 2000 Part 2 Multi-component, Lossless
        "1.2.840.10008.1.2.4.94",  # JPIP Referenced
        "1.2.840.10008.1.2.4.100",  # MPEG2 Main Profile / Main Level
        "1.2.840.10008.1.2.4.110",  # JPEG XL Lossless
        "1.2.3.4.5",  # a private transfer syntax under an invented root
        "",
        None,
        1,
    ],
)
def test_a_supported_sop_class_in_another_transfer_syntax_is_sequestered(
    transfer_syntax,
):
    found = scope.classify("1.2.840.10008.5.1.4.1.1.2", transfer_syntax)

    assert found == scope.Classification(
        Disposition.UNSUPPORTED_TRANSFER_SYNTAX, "CT Image"
    )
    assert found.sequestered


@pytest.mark.deid_requirement("MIDI-BP-06")
@pytest.mark.parametrize(
    "sop_class, transfer_syntax, reason",
    [
        (None, EXPLICIT_LE, Disposition.NO_SOP_CLASS),
        ("1.2.3.4.5", EXPLICIT_LE, Disposition.UNLISTED_SOP_CLASS),
        (
            "1.2.840.10008.5.1.4.1.1.2",
            "1.2.840.10008.1.2.4.92",
            Disposition.UNSUPPORTED_TRANSFER_SYNTAX,
        ),
        ("1.2.840.10008.5.1.4.1.1.2", EXPLICIT_LE, Disposition.SUPPORTED),
    ],
)
def test_only_an_unsupported_iod_has_a_reason_with_its_iod(
    sop_class, transfer_syntax, reason
):
    assert scope.classify(sop_class, transfer_syntax).reason is reason


def test_an_unsupported_iods_reason_holds_its_iod_and_code_alone():
    reason = scope.UnsupportedIod("Ultrasound Image")

    assert repr(reason) == "UnsupportedIod(iod='Ultrasound Image')"
    assert [field.name for field in dataclasses.fields(reason)] == ["iod", "code"]
    with pytest.raises(TypeError):
        # pylint: disable-next = too-many-function-args
        scope.UnsupportedIod("Ultrasound Image", Disposition.NO_SOP_CLASS)  # type: ignore[call-arg]


def test_the_sop_class_decides_before_the_transfer_syntax():
    found = scope.classify("1.2.840.10008.5.1.4.1.1.6.1", "1.2.840.10008.1.2.4.50")

    assert found.disposition is Disposition.UNSUPPORTED_IOD


def test_the_table_can_be_given():
    table = sop_classes.load_storage_sop_classes()
    plan = next(row for row in table.rows if row.name == "RT Plan Storage")
    altered = dataclasses.replace(
        table, rows=(dataclasses.replace(plan, iod="Ultrasound Image IOD"),)
    )

    found = scope.classify(plan.uid, EXPLICIT_LE, sop_classes=altered)

    assert found == scope.Classification(
        Disposition.UNSUPPORTED_IOD, "Ultrasound Image"
    )
    # CT Image Storage is not in the altered table.
    ct = scope.classify("1.2.840.10008.5.1.4.1.1.2", EXPLICIT_LE, sop_classes=altered)
    assert ct.disposition is Disposition.UNLISTED_SOP_CLASS


@pytest.mark.pydicom
def test_pydicom_names_the_same_uids():
    # pydicom's UID dictionary is an independent transcription of PS3.6.
    from pydicom import pixels, uid

    assert scope.SUPPORTED_TRANSFER_SYNTAXES == {
        uid.ImplicitVRLittleEndian,
        uid.ExplicitVRLittleEndian,
        uid.JPEGBaseline8Bit,
        uid.JPEGExtended12Bit,
        uid.JPEGLossless,
        uid.JPEGLosslessSV1,
        uid.JPEGLSLossless,
        uid.JPEGLSNearLossless,
        uid.JPEG2000Lossless,
        uid.JPEG2000,
        uid.HTJ2KLossless,
        uid.HTJ2KLosslessRPCL,
        uid.HTJ2K,
        uid.RLELossless,
    }
    # pydicom has a decoder for each compressed one.
    for syntax in scope.SUPPORTED_TRANSFER_SYNTAXES - {
        uid.ImplicitVRLittleEndian,
        uid.ExplicitVRLittleEndian,
    }:
        assert uid.UID(syntax).is_compressed, syntax
        assert pixels.get_decoder(syntax).UID == syntax
    for sop_class in (
        uid.CTImageStorage,
        uid.EnhancedCTImageStorage,
        uid.MRImageStorage,
        uid.EnhancedMRImageStorage,
        uid.MRSpectroscopyStorage,
        uid.PositronEmissionTomographyImageStorage,
        uid.EnhancedPETImageStorage,
        uid.RTDoseStorage,
        uid.RTImageStorage,
        uid.RTStructureSetStorage,
        uid.RTPlanStorage,
        uid.RTBeamsTreatmentRecordStorage,
        uid.RTIonPlanStorage,
        uid.RTIonBeamsTreatmentRecordStorage,
        uid.RTBrachyTreatmentRecordStorage,
        uid.RTTreatmentSummaryRecordStorage,
        uid.EnhancedRTImageStorage,
        uid.EnhancedContinuousRTImageStorage,
        uid.RTBeamsDeliveryInstructionStorage,
        uid.RTBrachyApplicationSetupDeliveryInstructionStorage,
        uid.RTRadiationSetDeliveryInstructionStorage,
        uid.SpatialRegistrationStorage,
        uid.DeformableSpatialRegistrationStorage,
        uid.BasicTextSRStorage,
        uid.EnhancedSRStorage,
        uid.ComprehensiveSRStorage,
        uid.Comprehensive3DSRStorage,
        uid.ExtensibleSRStorage,
        uid.KeyObjectSelectionDocumentStorage,
        uid.MammographyCADSRStorage,
        uid.ChestCADSRStorage,
        uid.ColonCADSRStorage,
        uid.ProcedureLogStorage,
        uid.SpectaclePrescriptionReportStorage,
        uid.MacularGridThicknessAndVolumeReportStorage,
        uid.WaveformAnnotationSRStorage,
        uid.GrayscaleSoftcopyPresentationStateStorage,
        uid.ColorSoftcopyPresentationStateStorage,
        uid.PseudoColorSoftcopyPresentationStateStorage,
        uid.BlendingSoftcopyPresentationStateStorage,
        uid.XAXRFGrayscaleSoftcopyPresentationStateStorage,
        uid.VariableModalityLUTSoftcopyPresentationStateStorage,
        uid.EncapsulatedPDFStorage,
    ):
        assert scope.classify(sop_class, uid.ExplicitVRLittleEndian).disposition is (
            Disposition.SUPPORTED
        )
