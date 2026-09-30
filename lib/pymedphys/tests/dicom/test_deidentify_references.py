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

import io
import pickle

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import iods, references, uid_roles

from . import _synthetic_references as synthetic

Level = references.Level
InstanceRecord = references.InstanceRecord
ReferenceSite = references.ReferenceSite

FIRST_RELEASE_IODS = ("CT Image", "RT Dose", "RT Plan", "RT Structure Set")
# Paths from the module tables of the 2026d PS3.3, checked against its text.
RT_REFERENCES = [
    # RT Structure Set: the contour images of each referenced frame, their
    # series, the images of each ROI contour, the source series, and the
    # predecessor structure set.
    ("RT Structure Set", synthetic.CONTOUR_IMAGES, Level.INSTANCE),
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
    # Every IOD: Common Instance Reference.
    *(
        (iod, attribute, level)
        for iod in FIRST_RELEASE_IODS
        for attribute, level in [
            (("(0008,1115)", "(0020,000E)"), Level.SERIES),
            (("(0008,1200)", "(0020,000D)"), Level.STUDY),
        ]
    ),
]
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


def _id(value):
    return ">".join(value) if isinstance(value, tuple) else None


@pytest.mark.parametrize("iod, attribute, level", RT_REFERENCES, ids=_id)
def test_reference_sites_include_the_rt_references(iod, attribute, level):
    site = ReferenceSite(attribute[:-1], attribute[-1], level)

    assert site in references.reference_sites(_iod(iod))
    assert site.attribute == attribute


@pytest.mark.parametrize("name", FIRST_RELEASE_IODS)
def test_reference_sites_are_nested_and_distinct(name):
    sites = references.reference_sites(_iod(name))

    assert sites
    assert all(site.path for site in sites)
    assert len({(site.path, site.tag) for site in sites}) == len(sites)
    assert all(references.REFERENCE_TAGS[site.tag] is site.level for site in sites)


def test_an_attribute_defined_twice_at_one_place_is_one_site():
    def definition(path, module):
        return iods.AttributeDefinition(
            path, "(0008,1155)", "Referenced SOP Instance UID", "1", module, ()
        )

    iod = iods.IOD(
        "Synthetic",
        "Table A.0-1",
        (),
        (
            definition((), "A"),
            definition(("(300C,0060)",), "A"),
            definition(("(300C,0060)",), "B"),
        ),
    )

    assert references.reference_sites(iod) == (
        ReferenceSite(("(300C,0060)",), "(0008,1155)", Level.INSTANCE),
    )


def test_every_nested_instance_uid_is_followed_or_reviewed():
    # A new edition that defines another instance UID inside a sequence fails
    # here until someone decides whether it is a reference.
    roles = uid_roles.load_uid_roles().rules
    nested = {
        definition.tag
        for iod in iods.load_iod_tables().iods.values()
        for definition in iod.definitions
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

    record = InstanceRecord.from_dataset(dataset)

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
    record = InstanceRecord.from_dataset(synthetic.structure_set())

    found = sorted(
        (reference.site.attribute, reference.site.level.value, reference.target)
        for reference in record.references
    )

    assert found == sorted(
        [
            (synthetic.RT_REFERENCED_STUDY, "instance", synthetic.STUDY),
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

    record = InstanceRecord.from_dataset(dataset)

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
    "sop_class",
    [
        synthetic.MR_IMAGE_STORAGE,
        "2.25.999",  # not a Standard SOP Class
        None,
        [synthetic.RT_PLAN_STORAGE, synthetic.RT_PLAN_STORAGE],
    ],
    ids=["another-iod", "unlisted", "absent", "two-values"],
)
def test_an_instance_of_another_iod_has_no_references(sop_class):
    dataset = synthetic.rt_plan()
    del dataset.SOPClassUID
    if sop_class is not None:
        synthetic.uid(dataset, "SOPClassUID", sop_class)

    record = InstanceRecord.from_dataset(dataset)

    assert record.iod is None
    assert record.references == ()
    assert record.sop_instance == synthetic.PLAN


@pytest.mark.pydicom
def test_a_record_shows_no_values():
    record = InstanceRecord.from_dataset(synthetic.structure_set())

    assert repr(record) == "InstanceRecord(iod='RT Structure Set')"
    assert record.references
    for reference in record.references:
        assert "2.25." not in repr(reference)
        assert synthetic.CT_IMAGE_STORAGE not in repr(reference)


@pytest.mark.pydicom
def test_a_record_can_be_pickled():
    # Discovery can then build records in worker processes.
    record = InstanceRecord.from_dataset(synthetic.structure_set())

    assert pickle.loads(pickle.dumps(record)) == record


@pytest.mark.pydicom
def test_recording_leaves_the_data_set_unchanged():
    def padded_structure_set():
        dataset = synthetic.structure_set()
        synthetic.uid(dataset, "SOPInstanceUID", synthetic.STRUCTURE_SET + "\x00")
        return dataset

    dataset = padded_structure_set()

    InstanceRecord.from_dataset(dataset)

    assert dataset == padded_structure_set()
    assert dataset.SOPInstanceUID == synthetic.STRUCTURE_SET + "\x00"


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize(
    "transfer_syntax",
    ["1.2.840.10008.1.2", "1.2.840.10008.1.2.1"],
    ids=["implicit-vr", "explicit-vr"],
)
def test_a_record_read_from_a_file_matches_the_data_set(transfer_syntax):
    dataset = synthetic.structure_set()
    # A UID of odd length is written with a trailing NUL (PS3.5 Section 9.1).
    dataset.PredecessorStructureSetSequence = [
        synthetic.reference(synthetic.RT_STRUCTURE_SET_STORAGE, "2.25.3011")
    ]
    expected = InstanceRecord.from_dataset(dataset)
    dataset.file_meta = pydicom.dataset.FileMetaDataset()
    dataset.file_meta.TransferSyntaxUID = transfer_syntax
    written = io.BytesIO()
    pydicom.dcmwrite(written, dataset, enforce_file_format=True)

    read = pydicom.dcmread(io.BytesIO(written.getvalue()))

    assert InstanceRecord.from_dataset(read) == expected
    assert len(expected.references) == 9
