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

"""Where an instance refers to others, from PS3.3, and what an instance record holds."""

import dataclasses
import pickle
import struct

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import iods, references, uid_roles
from pymedphys._dicom.deidentify.file_layout import ElementPath

from . import _synthetic_references as synthetic

Level = references.Level
InstanceRecord = references.InstanceRecord
ReferenceSite = references.ReferenceSite

FIRST_RELEASE_IODS = ("CT Image", "RT Dose", "RT Plan", "RT Structure Set")
# Paths from the module tables of the 2026d PS3.3, checked against its text.
RT_REFERENCES = [
    # RT Structure Set: the contour images of each referenced frame, their
    # series and study, the images of each ROI contour, the source series,
    # and the predecessor structure set.
    ("RT Structure Set", synthetic.CONTOUR_IMAGES, Level.INSTANCE),
    ("RT Structure Set", synthetic.RT_REFERENCED_STUDY, Level.STUDY),
    ("RT Structure Set", synthetic.RT_REFERENCED_SERIES, Level.SERIES),
    ("RT Structure Set", synthetic.ROI_CONTOUR_IMAGES, Level.INSTANCE),
    ("RT Structure Set", ("(3006,0039)", "(3006,004B)", "(0020,000E)"), Level.SERIES),
    ("RT Structure Set", ("(3006,004C)", "(0020,000E)"), Level.SERIES),
    ("RT Structure Set", ("(3006,0018)", "(0008,1155)"), Level.INSTANCE),
    # RT Plan: the structure set, the dose in each of its four places, and
    # another plan.
    ("RT Plan", synthetic.REFERENCED_STRUCTURE_SET, Level.INSTANCE),
    ("RT Plan", synthetic.REFERENCED_DOSE, Level.INSTANCE),
    ("RT Plan", ("(300A,0070)", "(300C,0080)", "(0008,1155)"), Level.INSTANCE),
    ("RT Plan", ("(300A,00B0)", "(300C,0080)", "(0008,1155)"), Level.INSTANCE),
    (
        "RT Plan",
        ("(300A,00B0)", "(300A,0111)", "(300C,0080)", "(0008,1155)"),
        Level.INSTANCE,
    ),
    ("RT Plan", synthetic.REFERENCED_PLAN, Level.INSTANCE),
    # RT Dose: the plan, the structure set in RT DVH and in Plan Overview, and
    # the multi-frame source of an extracted frame.
    ("RT Dose", synthetic.REFERENCED_PLAN, Level.INSTANCE),
    ("RT Dose", synthetic.REFERENCED_STRUCTURE_SET, Level.INSTANCE),
    ("RT Dose", ("(300C,0116)", "(300C,0060)", "(0008,1155)"), Level.INSTANCE),
    ("RT Dose", ("(0008,1164)", "(0008,1167)"), Level.INSTANCE),
    # CT Image: the plan in the CT Image module, and General Reference.
    ("CT Image", synthetic.REFERENCED_PLAN, Level.INSTANCE),
    ("CT Image", synthetic.REFERENCED_IMAGE, Level.INSTANCE),
    # Every IOD: Common Instance Reference, and the study in General Study
    # and in each request.
    *(
        (iod, attribute, level)
        for iod in FIRST_RELEASE_IODS
        for attribute, level in [
            (("(0008,1115)", "(0020,000E)"), Level.SERIES),
            (("(0008,1200)", "(0020,000D)"), Level.STUDY),
            (synthetic.REFERENCED_STUDY, Level.STUDY),
            (synthetic.REQUESTED_REFERENCED_STUDY, Level.STUDY),
        ]
    ),
]
# Every sequence in which a first release IOD defines Referenced SOP Instance
# UID (0008,1155), from the sequences' descriptions in the 2026d PS3.3. In
# the items of the Referenced Study Sequence and the RT Referenced Study
# Sequence, it is the Study Instance UID of a study (Sections 10.6.1 and
# C.8.8.5.4). In the others, it names an instance, a performed procedure
# step, a patient, or an HL7 document.
STUDY_SEQUENCES = {"(0008,1110)", "(3006,0012)"}
OTHER_SEQUENCES = {
    "(0008,1111)",  # Referenced Performed Procedure Step Sequence
    "(0008,1120)",  # Referenced Patient Sequence
    "(0008,1140)",  # Referenced Image Sequence
    "(0008,114A)",  # Referenced Instance Sequence
    "(0008,1156)",  # Definition Source Sequence
    "(0008,1199)",  # Referenced SOP Sequence
    "(0008,2112)",  # Source Image Sequence
    "(0018,990C)",  # Referenced Defined Protocol Sequence
    "(0018,990D)",  # Referenced Performed Protocol Sequence
    "(0020,9172)",  # Conversion Source Attributes Sequence
    "(0038,0100)",  # Pertinent Documents Sequence
    "(0040,A390)",  # HL7 Structured Document Reference Sequence
    "(0042,0013)",  # Source Instance Sequence
    "(0070,0404)",  # Referenced Spatial Registration Sequence
    "(3006,0016)",  # Contour Image Sequence
    "(3006,0018)",  # Predecessor Structure Set Sequence
    "(3008,0030)",  # Referenced Treatment Record Sequence
    "(300A,0401)",  # Referenced Setup Image Sequence
    "(300A,078C)",  # Referenced Patient Setup Photo Sequence
    "(300C,0002)",  # Referenced RT Plan Sequence
    "(300C,0042)",  # Referenced Reference Image Sequence
    "(300C,0060)",  # Referenced Structure Set Sequence
    "(300C,0080)",  # Referenced Dose Sequence
    "(3010,0007)",  # Originating SOP Instance Reference Sequence
    "(3010,0009)",  # Equivalent Conceptual Volume Instance Reference Sequence
    "(3010,004A)",  # Referenced Direct Segment Instance Sequence
}
# Every other UI attribute that uid_roles.toml marks "instance" and that a
# first release IOD defines inside a sequence, with why it is not followed.
NOT_FOLLOWED = {
    "(0008,010D)": "identifies the organisation that extended a context group",
    "(0018,1002)": "identifies a device",
    "(0040,0554)": "identifies a specimen",
    "(0040,A124)": "is the value of a content item",
    "(0040,E030)": "identifies a document repository",
    "(0040,E031)": "identifies a community of repositories",
    "(0044,0102)": "identifies an assertion within a plan",
    "(0044,0108)": "refers to an assertion within a plan",
    "(0070,031B)": "refers to a fiducial within an instance",
    "(0088,0140)": "identifies a file set",
    "(0400,0100)": "identifies a digital signature",
    "(300A,0013)": "identifies a dose reference within a plan",
    "(300A,0054)": "identifies a table top alignment event",
    "(300A,0083)": "refers to a dose reference within a plan",
    "(3010,0006)": "identifies a conceptual volume, not an instance",
    "(3010,000B)": "refers to a conceptual volume, not an instance",
    "(3010,0015)": "refers to a conceptual volume, not an instance",
    # A later change follows frames of reference.
    "(0020,0052)": "identifies a frame of reference",
    "(3006,0024)": "refers to a frame of reference",
}


def _iod(name):
    return iods.load_iod_tables().iods[name]


def _synthetic_iod(definitions):
    """Build module tables for the reference definitions under test."""
    modules = []
    tables = {}
    for index, definition in enumerate(definitions):
        label = f"Table C.0-{index + 1}"
        rows = tuple(
            iods.AttributeRow(depth, "Sequence", tag, "3", "")
            for depth, tag in enumerate(definition.path)
        ) + (
            iods.AttributeRow(
                len(definition.path),
                definition.name,
                definition.tag,
                definition.type,
                "",
            ),
        )
        modules.append(
            iods.ModuleUsage("Image", definition.module, "C.0", "M", "", label)
        )
        tables[label] = iods.AttributeTable(label, "Synthetic", rows)
    return iods.IOD("Synthetic", "Table A.0-1", tuple(modules), tables)


def _id(value):
    return ">".join(value) if isinstance(value, tuple) else None


def _only_site(monkeypatch, site):
    """Make every instance's IOD define no reference but ``site``."""
    monkeypatch.setattr(
        references, "_iod_and_sites", lambda sop_class: ("RT Plan", (site,))
    )


@pytest.mark.parametrize("iod, attribute, level", RT_REFERENCES, ids=_id)
def test_reference_sites_include_the_rt_references(iod, attribute, level):
    sites = references.reference_sites(_iod(iod))

    assert (attribute, level) in {(site.attribute, site.level) for site in sites}


@pytest.mark.parametrize(
    "iod, attribute, type_",
    [
        *((iod, synthetic.REQUESTED_STUDY, "3") for iod in FIRST_RELEASE_IODS),
        ("RT Plan", synthetic.PERTINENT_DOCUMENTS, "3"),
        ("RT Plan", synthetic.REFERENCED_STRUCTURE_SET, "1"),
        # Referenced Patient Photo Sequence > Study Instance UID, Type 1C.
        ("RT Plan", ("(0010,1100)", "(0020,000D)"), "1"),
    ],
    ids=_id,
)
def test_reference_sites_have_their_types_from_ps3_3(iod, attribute, type_):
    sites = references.reference_sites(_iod(iod))

    assert {site.attribute: site.type for site in sites}[attribute] == type_


@pytest.mark.parametrize(
    "types, strictest",
    [
        (("3", "1C"), "1"),
        (("2C", "3"), "2"),
        (("2", "1"), "1"),
        (("3", "3"), "3"),
        (("1C",), "1"),
        (("2C",), "2"),
    ],
    ids=["3-and-1C", "2C-and-3", "2-and-1", "3-and-3", "1C", "2C"],
)
def test_a_site_has_the_strictest_type_of_its_definitions(types, strictest):
    # A conditional element that is present has the requirements of Type 1
    # or Type 2 (PS3.5 Sections 7.4.2 and 7.4.4).
    iod = _synthetic_iod(
        tuple(
            iods.AttributeDefinition(
                ("(300C,0060)",),
                "(0008,1155)",
                "Referenced SOP Instance UID",
                type_,
                module,
                (),
            )
            for type_, module in zip(types, "AB")
        ),
    )

    assert references.reference_sites(iod) == (
        ReferenceSite(("(300C,0060)",), "(0008,1155)", Level.INSTANCE, strictest),
    )


@pytest.mark.parametrize("name", FIRST_RELEASE_IODS)
def test_reference_sites_are_nested_and_distinct(name):
    sites = references.reference_sites(_iod(name))

    assert sites
    assert all(site.path for site in sites)
    assert len({(site.path, site.tag) for site in sites}) == len(sites)
    assert all(
        references.REFERENCE_TAGS[site.tag] is site.level
        for site in sites
        if site.path[-1] not in STUDY_SEQUENCES
    )
    assert {site.type for site in sites} <= {"1", "2", "3"}


@pytest.mark.parametrize(
    "path, tag, level",
    [
        (("(0008,1110)",), "(0008,1155)", Level.STUDY),
        (("(0040,0275)", "(0008,1110)"), "(0008,1155)", Level.STUDY),
        (("(3006,0010)", "(3006,0012)"), "(0008,1155)", Level.STUDY),
        # Only the sequence whose items hold the attribute decides.
        (("(0008,1110)", "(0008,1199)"), "(0008,1155)", Level.INSTANCE),
        (("(3006,0012)", "(3006,0014)", "(3006,0016)"), "(0008,1155)", Level.INSTANCE),
        (("(0008,1111)",), "(0008,1155)", Level.INSTANCE),
        # Only Referenced SOP Instance UID names a study there.
        (("(0008,1110)",), "(0008,1167)", Level.INSTANCE),
        (("(3006,0012)",), "(0020,000E)", Level.SERIES),
    ],
    ids=_id,
)
def test_referenced_sop_instance_uid_names_a_study_in_a_study_sequence(
    path, tag, level
):
    # PS3.3 Sections 10.6.1 and C.8.8.5.4: in the items of the Referenced
    # Study Sequence and the RT Referenced Study Sequence, the Referenced SOP
    # Instance UID is the study's, and the Referenced SOP Class UID is the
    # study's own class, such as the retired Detached Study Management.
    definition = iods.AttributeDefinition(path, tag, "Synthetic", "1", "A", ())
    iod = _synthetic_iod((definition,))

    assert references.reference_sites(iod) == (ReferenceSite(path, tag, level, "1"),)


def test_referenced_sop_instance_uid_names_a_study_only_in_the_study_sequences():
    # A new edition that defines Referenced SOP Instance UID in another
    # sequence fails here until someone decides what its items name.
    sites = [
        site
        for name in FIRST_RELEASE_IODS
        for site in references.reference_sites(_iod(name))
        if site.tag == "(0008,1155)"
    ]

    assert {site.path[-1] for site in sites} == STUDY_SEQUENCES | OTHER_SEQUENCES
    assert {site.path[-1] for site in sites if site.level is Level.STUDY} == (
        STUDY_SEQUENCES
    )


def test_an_attribute_defined_twice_at_one_place_is_one_site():
    def definition(path, module):
        return iods.AttributeDefinition(
            path, "(0008,1155)", "Referenced SOP Instance UID", "1", module, ()
        )

    iod = _synthetic_iod(
        (
            definition((), "A"),
            definition(("(300C,0060)",), "A"),
            definition(("(300C,0060)",), "B"),
        ),
    )

    assert references.reference_sites(iod) == (
        ReferenceSite(("(300C,0060)",), "(0008,1155)", Level.INSTANCE, "1"),
    )


def test_every_first_release_nested_instance_uid_is_followed_or_reviewed():
    # A new edition that defines another instance UID inside a sequence fails
    # here until someone decides whether it is a reference.
    roles = uid_roles.load_uid_roles().rules
    nested = {
        definition.tag
        for name in FIRST_RELEASE_IODS
        for definition in _iod(name).definitions
        if definition.path
        and definition.tag in roles
        and roles[definition.tag].role is uid_roles.UIDRole.INSTANCE
    }

    assert nested == set(references.REFERENCE_TAGS) | set(NOT_FOLLOWED)
    assert not set(references.REFERENCE_TAGS) & set(NOT_FOLLOWED)


@pytest.mark.parametrize("name", FIRST_RELEASE_IODS)
def test_every_iod_requires_the_identity_attributes(name):
    iod = _iod(name)
    usage = {module.module: module.usage for module in iod.modules}

    assert references.IDENTITY_TAGS == {
        Level.INSTANCE: "(0008,0018)",
        Level.SERIES: "(0020,000E)",
        Level.STUDY: "(0020,000D)",
    }
    for tag in references.IDENTITY_TAGS.values():
        assert any(
            definition.type == "1" and usage[definition.module] == "M"
            for definition in iod.lookup(tag)
        )


@pytest.mark.pydicom
def test_a_record_holds_the_identity_without_padding():
    dataset = synthetic.rt_plan()
    synthetic.uid(dataset, "SOPClassUID", synthetic.RT_PLAN_STORAGE + "\x00")
    synthetic.uid(dataset, "SOPInstanceUID", synthetic.PLAN + "\x00")
    synthetic.uid(dataset, "SeriesInstanceUID", synthetic.PLAN_SERIES + " \x00")
    synthetic.uid(dataset, "StudyInstanceUID", synthetic.STUDY + "\x00")

    record = synthetic.record(dataset)

    assert record.iod == "RT Plan"
    assert (record.sop_instance, record.series, record.study) == (
        synthetic.PLAN,
        synthetic.PLAN_SERIES,
        synthetic.STUDY,
    )
    assert [record.identifier(level) for level in Level] == [
        synthetic.PLAN,
        synthetic.PLAN_SERIES,
        synthetic.STUDY,
    ]


@pytest.mark.pydicom
def test_a_record_finds_references_in_nested_items():
    record = synthetic.record(synthetic.structure_set())

    found = sorted(
        (reference.site.attribute, reference.site.level.value, reference.target)
        for reference in record.references
    )

    assert found == sorted(
        [
            (synthetic.RT_REFERENCED_STUDY, "study", synthetic.STUDY),
            (synthetic.RT_REFERENCED_SERIES, "series", synthetic.CT_SERIES),
            *(
                (attribute, "instance", slice_)
                for attribute in (
                    synthetic.CONTOUR_IMAGES,
                    synthetic.ROI_CONTOUR_IMAGES,
                )
                for slice_ in synthetic.CT_SLICES
            ),
        ]
    )


@pytest.mark.pydicom
def test_a_record_keeps_the_referenced_sop_class():
    dataset = synthetic.rt_plan()
    dataset.ReferencedStructureSetSequence = [
        synthetic.reference(
            synthetic.RT_STRUCTURE_SET_STORAGE + "\x00", synthetic.STRUCTURE_SET
        )
    ]
    dataset.ReferencedImageSequence = [
        synthetic.reference(None, synthetic.CT_SLICES[0])
    ]

    record = synthetic.record(dataset)

    assert {
        reference.site.attribute: reference.target_class
        for reference in record.references
    } == {
        synthetic.REFERENCED_STRUCTURE_SET: synthetic.RT_STRUCTURE_SET_STORAGE,
        synthetic.REFERENCED_DOSE: synthetic.RT_DOSE_STORAGE,
        synthetic.REFERENCED_IMAGE: None,
    }


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "type_, kept",
    [("1", True), ("2", True), ("3", False)],
    ids=["type-1", "type-2", "type-3"],
)
def test_an_empty_value_is_absent_only_where_the_site_is_type_3(
    monkeypatch, type_, kept
):
    # PS3.5 Section 7.4.5: a Type 3 element of zero length means the same as
    # an absent one. A Type 2 element of zero length has an unknown value
    # (7.4.3), and a Type 1 element must have one (7.4.1).
    _only_site(
        monkeypatch,
        ReferenceSite(("(300C,0060)",), "(0008,1155)", Level.INSTANCE, type_),
    )
    dataset = synthetic.rt_plan()
    dataset.ReferencedStructureSetSequence = [
        synthetic.reference(synthetic.RT_STRUCTURE_SET_STORAGE, value)
        for value in ["", "\x00", " \x00", [synthetic.PLAN, synthetic.PLAN]]
    ]

    record = synthetic.record(dataset)

    # Two values are not empty, whatever the Type.
    assert len(record.references) == (4 if kept else 1)
    assert {reference.target for reference in record.references} == {""}


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "sop_class",
    [
        "2.25.999",  # not a Standard SOP Class
        None,
        [synthetic.RT_PLAN_STORAGE, synthetic.RT_PLAN_STORAGE],
    ],
    ids=["unlisted", "absent", "two-values"],
)
def test_an_instance_without_generated_iod_tables_has_no_references(sop_class):
    dataset = synthetic.rt_plan()
    del dataset.SOPClassUID
    if sop_class is not None:
        synthetic.uid(dataset, "SOPClassUID", sop_class)

    record = synthetic.record(dataset)

    assert record.iod is None
    assert record.references == ()
    assert record.sop_instance == synthetic.PLAN


@pytest.mark.pydicom
def test_a_record_finds_references_of_a_generated_iod_beyond_the_first_release():
    dataset = synthetic.instance(
        synthetic.MR_IMAGE_STORAGE,
        "2.25.9001",
        "2.25.9002",
        ReferencedImageSequence=[
            synthetic.reference(synthetic.CT_IMAGE_STORAGE, synthetic.CT_SLICES[0])
        ],
    )

    record = synthetic.record(dataset)

    assert record.iod == "MR Image"
    (reference,) = record.references
    assert reference.site == ReferenceSite(
        ("(0008,1140)",), "(0008,1155)", Level.INSTANCE, "1"
    )
    assert reference.target == synthetic.CT_SLICES[0]
    assert reference.target_class == synthetic.CT_IMAGE_STORAGE


SEGMENTATION_STORAGE = "1.2.840.10008.5.1.4.1.1.66.4"
# Referenced SOP Instance UID of each source image in the Derivation Image
# Functional Group (PS3.3 C.7.6.16.2.6), in the Shared and the Per-Frame
# Functional Groups Sequences.
SHARED_SOURCE_IMAGE = ("(5200,9229)", "(0008,9124)", "(0008,2112)", "(0008,1155)")
PER_FRAME_SOURCE_IMAGE = (
    "(5200,9230)",
    "(0008,9124)",
    "(0008,2112)",
    "(0008,1155)",
)


def test_functional_group_macros_have_reference_sites():
    segmentation = _iod("Segmentation")

    sites = {site.attribute: site for site in references.reference_sites(segmentation)}

    for attribute in (SHARED_SOURCE_IMAGE, PER_FRAME_SOURCE_IMAGE):
        assert sites[attribute] == ReferenceSite(
            attribute[:-1], attribute[-1], Level.INSTANCE, "1"
        )


@pytest.mark.pydicom
def test_a_record_finds_references_in_functional_groups():
    # A segmentation of two CT slices, whose second frame names its source in
    # the Per-Frame Functional Groups Sequence, and whose first frame names
    # none.
    def frame(*slices):
        return synthetic.item(
            DerivationImageSequence=[
                synthetic.item(
                    SourceImageSequence=[
                        synthetic.reference(synthetic.CT_IMAGE_STORAGE, slice_)
                        for slice_ in slices
                    ]
                )
            ]
        )

    dataset = synthetic.instance(
        SEGMENTATION_STORAGE,
        "2.25.9101",
        "2.25.9102",
        SharedFunctionalGroupsSequence=[frame(synthetic.CT_SLICES[0])],
        PerFrameFunctionalGroupsSequence=[frame(), frame(synthetic.CT_SLICES[1])],
    )

    record = synthetic.record(dataset)

    assert record.iod == "Segmentation"
    assert [
        (reference.site.attribute, reference.target, reference.target_class)
        for reference in record.references
    ] == [
        (SHARED_SOURCE_IMAGE, synthetic.CT_SLICES[0], synthetic.CT_IMAGE_STORAGE),
        (PER_FRAME_SOURCE_IMAGE, synthetic.CT_SLICES[1], synthetic.CT_IMAGE_STORAGE),
    ]


@pytest.mark.pydicom
def test_a_record_shows_no_values():
    record = synthetic.record(synthetic.structure_set())

    assert repr(record) == "InstanceRecord(iod='RT Structure Set')"
    assert record.references
    for reference in record.references:
        assert "2.25." not in repr(reference)
        assert synthetic.CT_IMAGE_STORAGE not in repr(reference)


@pytest.mark.pydicom
def test_a_record_can_be_pickled():
    # Discovery can then build records in worker processes.
    record = synthetic.record(synthetic.structure_set())

    assert pickle.loads(pickle.dumps(record)) == record


@pytest.mark.pydicom
@pytest.mark.parametrize("kind", [bytearray, memoryview])
def test_a_record_is_built_from_a_copy_of_the_file(kind):
    data = synthetic.written(synthetic.structure_set())
    given = kind(bytearray(data))

    record = InstanceRecord.from_file(given)

    assert record == InstanceRecord.from_file(data)
    assert bytes(given) == data


def _without_digest(record):
    return dataclasses.replace(record, digest=None)


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_a_record_has_the_same_references_in_either_little_endian_syntax():
    # Only the digest, which compares source bytes, differs.
    dataset = synthetic.structure_set()
    # A UID of odd length is written with a trailing NUL (PS3.5 Section 9.1).
    dataset.PredecessorStructureSetSequence = [
        synthetic.reference(synthetic.RT_STRUCTURE_SET_STORAGE, "2.25.3011")
    ]

    implicit = synthetic.record(dataset, synthetic.IMPLICIT_VR_LITTLE_ENDIAN)
    explicit = synthetic.record(dataset, synthetic.EXPLICIT_VR_LITTLE_ENDIAN)

    assert _without_digest(implicit) == _without_digest(explicit)
    assert implicit.digest != explicit.digest
    assert len(explicit.references) == 9


ITEM_TAG = 0xFFFEE000


def _encoded(tag, value):
    """Return an element or item of defined length in Implicit VR Little Endian.

    Its tag's group and element, then the length of ``value``, each little
    endian, then ``value`` (PS3.5 Sections 7.1.3 and 7.5).
    """
    return struct.pack("<HHI", tag >> 16, tag & 0xFFFF, len(value)) + value


def _encoded_items(*items):
    """Return the value of a sequence whose items hold the encoded elements."""
    return b"".join(_encoded(ITEM_TAG, b"".join(item)) for item in items)


def _encoded_reference(sop_class, sop_instance):
    """Return the encoded elements of a synthetic.reference item."""
    # A UID of odd length has a trailing NUL (PS3.5 Section 9.1).
    return [
        _encoded(tag, uid.encode() + b"\x00" * (len(uid) % 2))
        for tag, uid in [(0x00081150, sop_class), (0x00081155, sop_instance)]
    ]


def _unknown(monkeypatch, tag, value):
    """Return an element whose VR is UN, whatever pydicom's dictionary knows."""
    # pydicom gives a UN element of an attribute it knows that attribute's VR,
    # unless replace_un_with_known_vr is off, as it can be when reading.
    with monkeypatch.context() as patch:
        patch.setattr(pydicom.config, "replace_un_with_known_vr", False)
        return pydicom.DataElement(tag, "UN", value)


def _with_rt_assertion():
    """Return an RT Plan with an RT Assertions Sequence, and its encoded value."""
    dataset = synthetic.rt_plan()
    dataset.add(
        synthetic.rt_assertions(
            synthetic.reference(synthetic.ENCAPSULATED_PDF_STORAGE, "2.25.9030")
        )
    )
    document = _encoded_reference(synthetic.ENCAPSULATED_PDF_STORAGE, "2.25.9030")
    value = _encoded_items([_encoded(0x00380100, _encoded_items(document))])
    return (
        dataset,
        synthetic.RT_ASSERTIONS_SEQUENCE,
        synthetic.PERTINENT_DOCUMENTS,
        value,
    )


def _with_dose_calculation_model():
    """Return an RT Dose with a Dose Calculation Model Sequence, and its value."""
    # Dose Calculation Model Sequence (3004,0080) > Dose Calculation Model
    # Parameter Sequence (3004,0083), neither of which pydicom 3.0.2 knows.
    parameter = synthetic.item(
        ReferencedSOPSequence=[
            synthetic.reference(synthetic.RT_PLAN_STORAGE, synthetic.PLAN)
        ]
    )
    model = synthetic.item()
    model.add(synthetic.sequence(0x30040083, [parameter]))
    dataset = synthetic.rt_dose()
    dataset.add(synthetic.sequence(0x30040080, [model]))
    attribute = ("(3004,0080)", "(3004,0083)", "(0008,1199)", "(0008,1155)")
    plan = _encoded_reference(synthetic.RT_PLAN_STORAGE, synthetic.PLAN)
    encoded_parameter = [_encoded(0x00081199, _encoded_items(plan))]
    encoded_model = [_encoded(0x30040083, _encoded_items(encoded_parameter))]
    return dataset, 0x30040080, attribute, _encoded_items(encoded_model)


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.filterwarnings("ignore:VR lookup failed:UserWarning")
@pytest.mark.parametrize(
    "build",
    [_with_rt_assertion, _with_dose_calculation_model],
    ids=["rt-assertions", "dose-calculation-model"],
)
def test_a_sequence_held_as_unknown_is_decoded_with_its_dictionary_vr(
    monkeypatch, build
):
    # PS3.5 Section 6.2.2 lets a reader that knows the VR of a UN value decode
    # it as Implicit VR Little Endian. The value is encoded here, and written
    # as UN in Explicit VR, so the test does not depend on which attributes
    # pydicom knows.
    dataset, tag, attribute, value = build()
    expected = synthetic.record(dataset)
    dataset[tag] = _unknown(monkeypatch, tag, value)
    data = synthetic.written(dataset)
    assert synthetic.read(data)[tag].VR == "UN"

    record = InstanceRecord.from_file(data)

    assert _without_digest(record) == _without_digest(expected)
    assert attribute in {reference.site.attribute for reference in record.references}


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.filterwarnings("ignore:VR lookup failed:UserWarning")
@pytest.mark.parametrize(
    "build",
    [_with_rt_assertion, _with_dose_calculation_model],
    ids=["rt-assertions", "dose-calculation-model"],
)
def test_a_record_read_from_implicit_vr_has_the_references_in_unknown_sequences(
    build,
):
    # pydicom 3.0.2 reads each of these sequences as UN from Implicit VR
    # Little Endian, since it does not know them; a pydicom that knows them
    # reads them as SQ. Either way, the record has the same references.
    dataset, _, attribute, _ = build()
    expected = synthetic.record(dataset)

    record = synthetic.record(dataset, synthetic.IMPLICIT_VR_LITTLE_ENDIAN)

    assert _without_digest(record) == _without_digest(expected)
    assert attribute in {reference.site.attribute for reference in record.references}


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "tag, found",
    [("(0044,0110)", True), ("(3004,0082)", False), ("(0009,1010)", False)],
    ids=["dictionary-sq", "dictionary-cs", "private"],
)
def test_an_unknown_value_is_decoded_only_where_the_dictionary_gives_sq(
    monkeypatch, tag, found
):
    # The encoded value of an RT Assertions Sequence, given as the UN value of
    # RT Assertions Sequence (0044,0110), of Commissioning Status (3004,0082),
    # whose dictionary VR is CS, and of a private attribute, which the
    # dictionary does not list.
    *_, value = _with_rt_assertion()
    _only_site(
        monkeypatch,
        ReferenceSite((tag, "(0038,0100)"), "(0008,1155)", Level.INSTANCE, "3"),
    )
    dataset = synthetic.rt_plan()
    number = int(tag[1:5] + tag[6:10], 16)
    dataset[number] = _unknown(monkeypatch, number, value)
    data = synthetic.written(dataset)
    assert synthetic.read(data)[number].VR == "UN"

    record = InstanceRecord.from_file(data)

    assert [reference.target for reference in record.references] == (
        ["2.25.9030"] if found else []
    )


@pytest.mark.pydicom
def test_an_unknown_value_is_decoded_as_implicit_vr_whatever_its_lengths(
    monkeypatch,
):
    # Told that an item is Explicit VR, pydicom reads it as Implicit VR only
    # if the two bytes after its first tag are not capital letters. Here they
    # begin the first element's length, 0x4A4A, which reads as "JJ", so only
    # decoding the value as Implicit VR finds the references.
    uids = [f"2.25.{10000 + n}" for n in range(292)]
    uids += [f"2.25.{1000000 + n}" for n in range(5)]
    dataset = synthetic.rt_plan()
    dataset.add(
        synthetic.rt_assertions(
            *(
                synthetic.reference(synthetic.ENCAPSULATED_PDF_STORAGE, uid)
                for uid in uids
            )
        )
    )
    expected = synthetic.record(dataset)
    documents = _encoded_items(
        *(_encoded_reference(synthetic.ENCAPSULATED_PDF_STORAGE, uid) for uid in uids)
    )
    assert len(documents) == 0x4A4A
    tag = synthetic.RT_ASSERTIONS_SEQUENCE
    dataset[tag] = _unknown(
        monkeypatch, tag, _encoded_items([_encoded(0x00380100, documents)])
    )
    data = synthetic.written(dataset)
    assert synthetic.read(data)[tag].VR == "UN"

    record = InstanceRecord.from_file(data)

    assert _without_digest(record) == _without_digest(expected)
    assert [
        reference.target
        for reference in record.references
        if reference.site.attribute == synthetic.PERTINENT_DOCUMENTS
    ] == uids


@pytest.mark.pydicom
def test_an_unknown_value_of_zero_length_has_no_items(monkeypatch):
    # pydicom reads a UN element of zero length with the value None.
    dataset = synthetic.rt_plan()
    tag = synthetic.RT_ASSERTIONS_SEQUENCE
    dataset[tag] = _unknown(monkeypatch, tag, None)
    data = synthetic.written(dataset)
    assert synthetic.read(data)[tag].VR == "UN"

    record = InstanceRecord.from_file(data)

    plain = synthetic.record(synthetic.rt_plan())
    assert record.references == plain.references
    # The empty element is still part of the source bytes.
    assert record.digest != plain.digest


UNREADABLE_ITEMS = {
    # An item whose defined length runs past the value.
    "item-past-value": struct.pack("<HHI", 0xFFFE, 0xE000, 64)
    + _encoded(0x00081155, b"SENTINEL"),
    # An element where an item belongs.
    "element-where-an-item-belongs": _encoded(0x00081155, b"SENTINEL"),
}


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize(
    "value", UNREADABLE_ITEMS.values(), ids=UNREADABLE_ITEMS.keys()
)
@pytest.mark.parametrize("nested", [False, True], ids=["top-level", "nested"])
def test_an_unknown_value_whose_items_cannot_be_read_is_refused(
    monkeypatch, value, nested
):
    # pydicom decodes each value without an error, leaving out what it holds.
    pydicom.values.convert_SQ(value, True, True)
    # Dose Calculation Model Sequence (3004,0080) > Dose Calculation Model
    # Parameter Sequence (3004,0083), neither of which pydicom 3.0.2 knows.
    dataset = synthetic.rt_dose()
    if nested:
        model = synthetic.item()
        model[0x30040083] = _unknown(monkeypatch, 0x30040083, value)
        dataset.add(synthetic.sequence(0x30040080, [model]))
        path = ElementPath((("(3004,0080)", 0),), "(3004,0083)")
    else:
        dataset[0x30040080] = _unknown(monkeypatch, 0x30040080, value)
        path = ElementPath((), "(3004,0080)")
    data = synthetic.written(dataset)

    with pytest.raises(references.UnreadableSequence) as raised:
        InstanceRecord.from_file(data)

    assert raised.value.path == path
    assert str(raised.value) == f"{path} has items that cannot be read"
    assert raised.value.__cause__ is None
    assert "SENTINEL" not in repr(raised.value)
