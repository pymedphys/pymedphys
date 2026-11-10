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

"""Residual UID findings whose source is a removed private copy of a kept UID.

A vendor can copy a UID that Retain UIDs keeps into a private element, as
GE PET images copy their Frame of Reference UID (0020,0052) into
(0009,1013) of the ``GEMS_PETD_01`` block. The run removes the private
element, so the residual search collects its value (D-027) and finds it in
the kept Frame of Reference UID. Where every instance of the subject that
collected the private value removed it, nothing in the output refers through
it, and the UID where it is found is one that the option releases anyway, so
the finding is explained (D-042). A copy that a written instance holds
replaced, one found inside a longer kept UID, in text, or outside the data
set, and every standard UID source still withhold the file.
"""

import json
import os
import shutil
import struct
import tempfile
from pathlib import Path

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import run
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
    unwritten,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import UIDS, compose_custom_policy
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.release_gate import (
    Coverage,
    Decision,
    ReasonCode,
    release_condition,
)
from pymedphys._dicom.deidentify.release_report import FORMAT
from pymedphys._dicom.deidentify.residual_exemptions import Exemption
from pymedphys._dicom.deidentify.residuals import SourceValue
from pymedphys._dicom.deidentify.run_report import RELEASE_REPORT

from . import _synthetic_references as synthetic

KEY = DeidKey(bytes(range(32)))
FRAME = "2.25.7300"  # the frame of reference that the private element copies
OTHER_FRAME = "2.25.7301"
FRAME_OF_REFERENCE_UID = "(0020,0052)"
# GEMS_PETD_01's FOR Identifier, in TCIA's private tag dictionary.
COPY = ElementPath((), "(0009,1013)")
NESTED_COPY = ElementPath((("(0009,1020)", 0),), "(0009,1013)")
# A standard reference, as an instance's Referenced Image Sequence holds it.
REFERENCE = ElementPath((("(0008,1140)", 0),), "(0008,1155)")
CREATOR = "GEMS_PETD_01"


def _element(tag, vr, value):
    """An explicit VR little endian element with a 16-bit length."""
    group, element = divmod(tag, 0x10000)
    value = value.encode("ascii")
    value += (b"\x00" if vr == "UI" else b" ") * (len(value) % 2)
    return struct.pack("<HH2sH", group, element, vr.encode(), len(value)) + value


def _written(*elements, meta=b""):
    """A written file holding ``elements``, given in the order of their tags."""
    syntax = _element(0x00020010, "UI", "1.2.840.10008.1.2.1")
    return bytes(128) + b"DICM" + meta + syntax + b"".join(elements)


KEPT_FRAME = _written(_element(0x00200052, "UI", FRAME))


def _instance(values, removed=None, options=(UIDS,)):
    """The coverage of one written instance that collected ``values``.

    Each of ``values`` is removed unless ``removed`` names those that are.
    """
    return Coverage(
        planned=frozenset(value.source for value in values),
        collected=tuple(values),
        options=options,
        removed=frozenset(values if removed is None else removed),
    )


def _exempted(condition):
    return [(f.location.element.tag, why) for f, why in condition.exempted]


def _withholds_for_the_uid(condition):
    assert condition.decision is Decision.WITHHOLD
    assert not condition.exempted
    assert [reason.code for reason in condition.reasons] == [ReasonCode.RESIDUAL_UID]


# Coverage.


def test_a_value_is_removed_only_where_every_coverage_that_collected_it_says_so():
    shared = SourceValue(COPY, "UI", FRAME)
    only = SourceValue(NESTED_COPY, "UI", OTHER_FRAME)
    removing = _instance((shared, only))
    replacing = _instance((shared,), removed=())

    assert Coverage.merge(removing).removed == {shared, only}
    assert Coverage.merge(replacing, removing).removed == {only}
    assert Coverage.merge(removing, replacing).removed == {only}
    assert not Coverage.merge(replacing).removed


def test_a_coverage_refuses_a_removed_value_that_it_did_not_collect():
    value = SourceValue(COPY, "UI", FRAME)
    with pytest.raises(ValueError):
        Coverage(planned=frozenset(), collected=(), removed=frozenset({value}))
    with pytest.raises(TypeError):
        Coverage(planned=frozenset(), collected=(value,), removed={value})
    with pytest.raises(TypeError):
        Coverage(planned=frozenset(), collected=(), removed=frozenset({FRAME}))


def test_an_unwritten_instance_gives_every_value_it_collected_as_removed():
    values = (SourceValue(COPY, "UI", FRAME), SourceValue(REFERENCE, "UI", FRAME))
    coverage = Coverage(planned=frozenset({COPY, REFERENCE}), collected=values)

    assert unwritten(coverage).removed == frozenset(values)
    # A sequestered instance writes nothing, so a written instance's removal
    # of the same value is not undone by pooling it with one.
    pooled = Coverage.merge(_instance(values[:1]), unwritten(coverage))
    assert pooled.removed == frozenset(values)


# The removed private UID (D-042).


@pytest.mark.deid_requirement("PS3.15-E.3.9-01")
@pytest.mark.parametrize("source", [COPY, NESTED_COPY], ids=["top-level", "nested"])
def test_a_removed_private_copy_of_a_kept_uid_is_explained(source):
    condition = release_condition(
        Coverage.merge(_instance((SourceValue(source, "UI", FRAME),))), KEPT_FRAME
    )

    assert condition.decision is Decision.RELEASE
    assert _exempted(condition) == [(FRAME_OF_REFERENCE_UID, Exemption.REMOVED_UID)]
    # The finding stays in the search, for the QC pack.
    assert len(condition.search.findings) == 1


@pytest.mark.deid_requirement("PS3.15-E.3.9-01")
def test_another_removed_value_of_the_copy_not_in_the_kept_uid_is_no_obstacle():
    # Another series of the subject, on another frame of reference.
    values = (SourceValue(COPY, "UI", FRAME), SourceValue(COPY, "UI", OTHER_FRAME))
    condition = release_condition(Coverage.merge(_instance(values)), KEPT_FRAME)

    assert condition.decision is Decision.RELEASE
    assert _exempted(condition) == [(FRAME_OF_REFERENCE_UID, Exemption.REMOVED_UID)]


@pytest.mark.deid_requirement("PS3.15-E.3.9-01")
@pytest.mark.parametrize(
    "coverages",
    [
        # A written instance holds the copy replaced, so its output refers
        # through the private element to the frame that is kept.
        (_instance((SourceValue(COPY, "UI", FRAME),), removed=()),),
        (
            _instance((SourceValue(COPY, "UI", FRAME),)),
            _instance((SourceValue(COPY, "UI", FRAME),), removed=()),
        ),
        # A written instance replaced another value of the copy.
        (
            _instance((SourceValue(COPY, "UI", FRAME),)),
            _instance((SourceValue(COPY, "UI", OTHER_FRAME),), removed=()),
        ),
        # Another removed value of the copy that the search finds inside the
        # kept UID, but is not the whole of it.
        (_instance((SourceValue(COPY, "UI", FRAME), SourceValue(COPY, "UI", "2.25"))),),
        # No option keeps the Frame of Reference UID.
        (_instance((SourceValue(COPY, "UI", FRAME),), options=()),),
        # A standard source, although removed with its sequence.
        (_instance((SourceValue(REFERENCE, "UI", FRAME),)),),
        # A private creator's slot, which no vendor fills with a UID.
        (_instance((SourceValue(ElementPath((), "(0009,0013)"), "UI", FRAME),)),),
    ],
    ids=[
        "replaced",
        "removed-and-replaced",
        "another-replaced",
        "another-a-prefix",
        "no-option",
        "standard-source",
        "creator-slot",
    ],
)
def test_a_uid_that_a_removed_private_copy_does_not_explain_still_withholds(
    coverages,
):
    _withholds_for_the_uid(release_condition(Coverage.merge(*coverages), KEPT_FRAME))


@pytest.mark.deid_requirement("PS3.15-E.3.9-01")
@pytest.mark.parametrize(
    "written",
    [
        # Inside a longer kept UID.
        _written(_element(0x00200052, "UI", f"{FRAME}.5")),
        # In kept text, which no option keeps as a UID.
        _written(_element(0x00204000, "LT", f"FOR {FRAME}")),
        # In a UID that no option keeps.
        _written(_element(0x00081167, "UI", FRAME)),
        # In the File Meta Information.
        _written(meta=_element(0x00020003, "UI", FRAME)),
    ],
    ids=["longer-uid", "text", "uid-not-kept", "file-meta"],
)
def test_a_removed_private_copy_anywhere_else_still_withholds(written):
    coverage = Coverage.merge(_instance((SourceValue(COPY, "UI", FRAME),)))

    _withholds_for_the_uid(release_condition(coverage, written))


@pytest.mark.deid_requirement("PS3.15-E.3.9-01")
def test_a_replaced_reference_to_a_kept_sop_instance_still_withholds():
    """D-040: a written instance's replaced reference withholds its target."""
    kept = _written(_element(0x00080018, "UI", FRAME))
    coverage = Coverage.merge(
        _instance((SourceValue(REFERENCE, "UI", FRAME),), removed=())
    )

    _withholds_for_the_uid(release_condition(coverage, kept))


# The transform's evidence.


def _with_private_copy(dataset, value=FRAME):
    """Give ``dataset`` its frame of reference and a GE PET private copy of it."""
    dataset.FrameOfReferenceUID = FRAME
    block = dataset.private_block(0x0009, CREATOR, create=True)
    block.add_new(0x13, "UI", value)
    return dataset


def _transformed(transform, dataset):
    data = synthetic.written(dataset)
    return transform(data, InstanceRecord.from_file(data))


def _collected(result):
    return result.evidence.collected


def _removed(result):
    return result.evidence.removed


def test_the_transform_gives_a_removed_value_as_removed_and_a_replaced_one_not():
    transform = InstanceTransform(
        compose_custom_policy(()), KEY, unvalidated_policy=True
    )

    result = _transformed(transform, _with_private_copy(synthetic.ct_slice(0)))

    assert isinstance(result, run.Transformed)
    collected = {value.source: value for value in _collected(result)}
    # The Basic Profile removes the private element and replaces the UIDs.
    assert collected[COPY] in _removed(result)
    frame = ElementPath((), FRAME_OF_REFERENCE_UID)
    assert collected[frame] not in _removed(result)


# Runs of CT slices whose private elements copy their frame of reference.


@pytest.fixture(name="tmp_path")
def _short_tmp_path(tmp_path):
    # A run refuses output paths that could exceed Windows' 259 characters.
    if os.name != "nt":
        yield tmp_path
        return
    directory = Path(tempfile.mkdtemp(prefix="d"))
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


def _run(tmp_path, transform):
    """Run three CT slices, each with a private copy of its frame of reference."""
    source = tmp_path / "source"
    source.mkdir()
    for number in range(3):
        dataset = _with_private_copy(synthetic.ct_slice(number))
        (source / f"{number}.dcm").write_bytes(synthetic.written(dataset))
    result = run.run(
        run.discover(source),
        tmp_path / "release",
        transform,
        ReleaseGate(),
        qc_destination=tmp_path / "qc",
        reporter=transform.reporter,
        written_check=transform.written_check,
    )
    report = json.loads((result.release / RELEASE_REPORT).read_text(encoding="utf-8"))
    return [outcome.status for outcome in result.outcomes], report


@pytest.mark.deid_requirement("PS3.15-E.3.9-01")
def test_under_retain_uids_a_removed_private_copy_of_the_frame_withholds_nothing(
    tmp_path,
):
    transform = InstanceTransform(
        compose_custom_policy((UIDS,)), KEY, unvalidated_policy=True
    )

    statuses, report = _run(tmp_path, transform)

    assert statuses == [run.Status.RELEASED] * 3
    assert report["format"] == FORMAT == "pymedphys-deid-release-report/68"
    assert [
        (entry["attribute"], entry["found_in"], entry["count"])
        for entry in report["exempted_findings"]
        if entry["exemption"] == Exemption.REMOVED_UID.value
    ] == [(COPY.tag, FRAME_OF_REFERENCE_UID, 3)]
    released = sorted((tmp_path / "release").rglob("*.dcm"))
    for path in released:
        dataset = pydicom.dcmread(path)
        assert dataset.FrameOfReferenceUID == FRAME
        assert (0x0009, 0x1013) not in dataset
