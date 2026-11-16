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

from pymedphys._dicom.deidentify import iods, scope
from pymedphys._dicom.deidentify.common_instance_reference import (
    SEQUENCES,
    is_common_instance_reference,
    is_instance_reference,
)
from pymedphys._dicom.deidentify.file_layout import ElementPath

MODULE = "Common Instance Reference"
# The supported IODs that make the module mandatory, from the 2026d PS3.3
# Tables A.39.1-1, A.39.2-1, A.46-1, A.86.1.15-1, and A.86.1.16-1, the
# second-generation RT IOD Modules tables of Section A.86.1, and the IOD
# Modules table of Section A.79.
MANDATORY = {
    "Spatial Registration",
    "Deformable Spatial Registration",
    "Real World Value Mapping",
    "Enhanced RT Image",
    "Enhanced Continuous RT Image",
    "RT Segment Annotation",
    "RT Radiation Set",
    "C-Arm Photon-Electron Radiation",
    "Tomotherapeutic Radiation",
    "Robotic-Arm Radiation",
    "RT Brachy Application Setup Delivery Instruction",
    "RT Radiation Set Delivery Instruction",
}
# Required in a Segmentation where a Derivation Image functional group is
# present, in a Parametric Map where a Derivation Image or Referenced Image
# functional group is, in a Surface Segmentation where the surface was
# derived from another instance (PS3.3 Table A.57-1), and in an RT Beams
# Delivery Instruction where the instruction is not conveyed by a Unified
# Procedure Step.
CONDITIONAL = {
    "Segmentation",
    "Parametric Map",
    "Surface Segmentation",
    "RT Beams Delivery Instruction",
}
# The supported IODs without the module: the Structured Reports, whose SR
# Document General Module references their evidence instead (PS3.3 Section
# A.35), and the Encapsulated PDF, whose Encapsulated Document Module names
# its sources in Source Instance Sequence (PS3.3 Table C.24-2).
WITHOUT = {
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
    "Encapsulated PDF",
}
# The supported IODs without the module whose Presentation State
# Relationship Module makes Referenced Series Sequence (0008,1115) Type 1 at
# the top level, from the 2026d PS3.3 Section A.33 and Table C.11.11-1.
PRESENTATION_STATES = {
    "Grayscale Softcopy Presentation State",
    "Color Softcopy Presentation State",
    "Pseudo-Color Softcopy Presentation State",
    "XA/XRF Grayscale Softcopy Presentation State",
    "Variable Modality LUT Softcopy Presentation State",
}
# The supported Presentation State IOD without either module: the blending
# one names its images in its Blending Sequence (0070,0402) instead.
BLENDING = "Blending Softcopy Presentation State"


def _path(*steps):
    return ElementPath(tuple((tag, 0) for tag in steps[:-1]), steps[-1])


def test_every_supported_iod_but_the_reports_includes_the_module_and_its_sequences():
    # Where an IOD makes the module mandatory, it still holds neither
    # sequence once both conditions fail, since both are Type 1C.
    tables = iods.load_iod_tables()
    for name in scope.SUPPORTED_IODS:
        iod = tables.iods[name]
        usages = {m.usage for m in iod.modules if m.module == MODULE}
        if name in PRESENTATION_STATES:
            assert not usages, name
            assert {
                (d.tag, d.type, d.module)
                for d in iod.definitions
                if d.tag in SEQUENCES and not d.path
            } == {("(0008,1115)", "1", "Presentation State Relationship")}, name
            continue
        if name in WITHOUT | {BLENDING}:
            assert not usages, name
            assert not any(
                d.tag in SEQUENCES and not d.path for d in iod.definitions
            ), name
            continue
        (usage,) = usages
        assert usage == (
            "M" if name in MANDATORY else "C" if name in CONDITIONAL else "U"
        ), name
        assert {
            (d.tag, d.type)
            for d in iod.definitions
            if d.tag in SEQUENCES and not d.path
        } == {(tag, "1C") for tag in SEQUENCES}, name


@pytest.mark.parametrize("tag", ["(0008,1115)", "(0008,1200)"])
def test_the_modules_sequences_are_at_the_top_level_only(tag):
    assert is_common_instance_reference(_path(tag))
    # As in the Hierarchical SOP Instance Reference Macro.
    assert not is_common_instance_reference(_path("(0008,9092)", tag))


def test_a_presentation_states_referenced_series_sequence_is_not_the_modules():
    # Given its IOD, the Type 1 sequence of the Presentation State
    # Relationship Module is not the module's, so it never lapses; the
    # module's own sequences, in an IOD that includes it, still are.
    tables = iods.load_iod_tables()
    path = _path("(0008,1115)")
    for name in PRESENTATION_STATES:
        assert not is_common_instance_reference(path, tables.iods[name]), name
    assert is_common_instance_reference(path, tables.iods["CT Image"])
    assert is_common_instance_reference(
        _path("(0008,1200)"), tables.iods["Spatial Registration"]
    )
    # A report, which defines neither, is as without an IOD: the sequence is
    # removed anyway, as no module of the IOD defines it.
    assert is_common_instance_reference(path, tables.iods["Comprehensive SR"])


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
