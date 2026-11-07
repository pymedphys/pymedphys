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

"""Residual findings that lie wholly inside the run's own method digest.

Every instance that a run writes gains the method digest, 64 lowercase
hexadecimal digits, as a value of De-identification Method (0012,0063). The
digest is a SHA-256 of the policy and of the engine, never of a source
value, so its digits can hold a source value only by chance: about 3 in
10,000 digests hold one of 20,000 distinct dates. The residual search finds
such a value there (D-027), and the release gate would withhold every file
of the run for it. A finding whose every match in that element lies wholly
inside a value equal to the run's own digest is exempt (D-032); a match
anywhere else, including in another value of the same element, or in
another digest, still counts.
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
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.method_digest import method_digest
from pymedphys._dicom.deidentify.policy import compose_custom_policy
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
METHOD = "(0012,0063)"
DATE = "20190312"
# An invented digest whose digits hold DATE, then DEADBEEF, and end in letters.
DIGEST = "c0ffee" + DATE + "deadbeef" + "0" * 34 + "abcdefab"
OTHER_DIGEST = "f" * 64
READABLE = "PyMedPhys 0.42.0; PS3.15 2026d; basic"
STUDY_DATE = ElementPath((), "(0008,0020)")


def _element(tag, vr, value):
    """An explicit VR little endian element with a 16-bit length."""
    group, element = divmod(tag, 0x10000)
    value = value.encode("latin-1") if isinstance(value, str) else value
    value += b" " * (len(value) % 2)
    return struct.pack("<HH2sH", group, element, vr.encode(), len(value)) + value


def _written(*elements):
    """A written file holding ``elements``, given in the order of their tags."""
    meta = _element(0x00020010, "UI", "1.2.840.10008.1.2.1\x00")
    return bytes(128) + b"DICM" + meta + b"".join(elements)


def _method(*values):
    """De-identification Method holding ``values``."""
    return _element(0x00120063, "LO", "\\".join(values))


MARKED = _written(_method(DIGEST, READABLE))


def _coverage(*values, digest=DIGEST):
    """The coverage of one instance that collected ``values``, under a digest."""
    return Coverage(
        planned=frozenset(value.source for value in values),
        collected=tuple(values),
        method_digest=digest,
    )


def _date(value=DATE, path=STUDY_DATE):
    return SourceValue(path, "DA", value)


def _exempted(condition):
    return [(f.location.element.tag, why) for f, why in condition.exempted]


def _withholds_for_the_date(condition):
    assert condition.decision is Decision.WITHHOLD
    assert not condition.exempted
    assert [reason.code for reason in condition.reasons] == [ReasonCode.RESIDUAL_DATE]


# The coverage.


def test_a_coverage_records_a_method_digest_of_64_lowercase_hex_digits():
    assert _coverage(_date()).method_digest == DIGEST
    assert _coverage(_date(), digest=None).method_digest is None
    assert Coverage(planned=frozenset(), collected=()).method_digest is None


@pytest.mark.parametrize(
    "digest, error",
    [
        (DIGEST.upper(), ValueError),
        (DIGEST[:63], ValueError),
        (DIGEST + "0", ValueError),
        (f" {DIGEST[1:]}", ValueError),
        (DIGEST.encode("ascii"), TypeError),
    ],
    ids=["upper-case", "short", "long", "space", "bytes"],
)
def test_a_coverage_refuses_any_other_method_digest(digest, error):
    with pytest.raises(error, match="method digest") as raised:
        _coverage(_date(), digest=digest)
    assert DIGEST not in str(raised.value)


def test_a_merge_keeps_the_method_digest_only_where_every_coverage_gives_it():
    one, two = _coverage(_date()), _coverage(_date("20200101"))
    other = _coverage(_date(), digest=OTHER_DIGEST)
    none = _coverage(_date(), digest=None)

    assert Coverage.merge(one, two).method_digest == DIGEST
    assert Coverage.merge(one, other).method_digest is None
    assert Coverage.merge(one, none).method_digest is None
    assert Coverage.merge().method_digest is None


# Findings inside the digest.


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_date_found_inside_the_runs_digest_is_exempt():
    condition = release_condition(_coverage(_date()), MARKED)

    assert condition.decision is Decision.RELEASE
    assert not condition.reasons
    assert _exempted(condition) == [(METHOD, Exemption.METHOD_DIGEST)]
    # The finding stays in the search, for the QC pack.
    assert [f.location.element.tag for f in condition.search.findings] == [METHOD]


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_without_the_runs_digest_the_same_date_withholds_the_file():
    _withholds_for_the_date(release_condition(_coverage(_date(), digest=None), MARKED))


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "value",
    [
        # A date, and a datetime, by its date.
        SourceValue(STUDY_DATE, "DA", DATE),
        SourceValue(ElementPath((), "(0008,002A)"), "DT", f"{DATE}101500"),
        # A direct identifier.
        SourceValue(ElementPath((), "(0010,0020)"), "LO", "DEADBEEF"),
        # A person name, run together and by each name.
        SourceValue(ElementPath((), "(0010,0010)"), "PN", "BEEF^DEAD"),
        # A UID of digits alone.
        SourceValue(ElementPath((), "(0020,000D)"), "UI", DATE),
        # Other text.
        SourceValue(ElementPath((), "(0008,1030)"), "LO", "C0FFEE"),
    ],
    ids=["date", "datetime", "direct-identifier", "person-name", "uid", "text"],
)
def test_a_finding_of_any_kind_wholly_inside_the_runs_digest_is_exempt(value):
    condition = release_condition(_coverage(value), MARKED)

    assert condition.decision is Decision.RELEASE
    assert _exempted(condition) == [(METHOD, Exemption.METHOD_DIGEST)]


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_digest_after_values_already_present_is_still_the_runs():
    written = _written(_method("ANOTHER TOOL 2.0", DIGEST, READABLE))

    condition = release_condition(_coverage(_date()), written)

    assert condition.decision is Decision.RELEASE
    assert _exempted(condition) == [(METHOD, Exemption.METHOD_DIGEST)]


# Findings that still count.


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_date_inside_another_digest_still_withholds():
    # Such as the digest of an earlier run, which the run keeps.
    coverage = _coverage(_date(), digest=OTHER_DIGEST)
    written = _written(_method(DIGEST, READABLE, OTHER_DIGEST, READABLE))

    _withholds_for_the_date(release_condition(coverage, written))


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "values",
    [
        # Before the digest, so the search's first match is outside it.
        (f"SCANNED {DATE}", DIGEST, READABLE),
        # After it, where the search records only the first match.
        (DIGEST, READABLE, f"SCANNED {DATE}"),
        # In the same value as the digest, after it.
        (f"{DIGEST} {DATE}", READABLE),
    ],
    ids=["before", "after", "same-value"],
)
def test_the_same_date_elsewhere_in_de_identification_method_still_withholds(
    values,
):
    _withholds_for_the_date(
        release_condition(_coverage(_date()), _written(_method(*values)))
    )


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_another_value_of_the_pooled_source_elsewhere_in_the_element_withholds():
    # Another instance of the subject held another Study Date, which a value
    # already present in the element holds.
    coverage = Coverage.merge(_coverage(_date()), _coverage(_date("20200101")))
    written = _written(_method(DIGEST, READABLE, "SCANNED 20200101"))

    _withholds_for_the_date(release_condition(coverage, written))


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_match_that_runs_past_the_end_of_the_digest_is_not_exempt():
    # A comment whose text is the digest's last digits and the start of the
    # readable value: found from inside the digest, but not wholly in it.
    comment = SourceValue(
        ElementPath((), "(0020,4000)"), "LT", f"{DIGEST[-8:]}\\{READABLE[:9]}"
    )

    condition = release_condition(_coverage(comment), MARKED)

    assert condition.decision is Decision.QC_REVIEW
    assert not condition.exempted
    assert [reason.code for reason in condition.reasons] == [ReasonCode.RESIDUAL_TEXT]


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_the_digest_in_any_other_element_explains_nothing():
    written = _written(
        _element(0x00081030, "LO", DIGEST), _method(OTHER_DIGEST, READABLE)
    )

    _withholds_for_the_date(release_condition(_coverage(_date()), written))


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_the_digest_in_an_item_explains_nothing():
    item = _element(0x00120063, "LO", f"{DIGEST}\\{READABLE}")
    sequence = (
        struct.pack("<HH2sHI", 0x0040, 0xA730, b"SQ", 0, 0xFFFFFFFF)
        + struct.pack("<HHI", 0xFFFE, 0xE000, 0xFFFFFFFF)
        + item
        + struct.pack("<HHI", 0xFFFE, 0xE00D, 0)
        + struct.pack("<HHI", 0xFFFE, 0xE0DD, 0)
    )

    _withholds_for_the_date(release_condition(_coverage(_date()), _written(sequence)))


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_an_element_with_a_byte_outside_iso_646_explains_nothing():
    written = _written(_method("ANOTHER TOOL \xe9", DIGEST, READABLE))

    _withholds_for_the_date(release_condition(_coverage(_date()), written))


# Runs.


@pytest.fixture(name="tmp_path")
def _short_tmp_path(tmp_path):
    # A run refuses output paths that could exceed Windows' 259 characters.
    if os.name != "nt":
        yield tmp_path
        return
    directory = Path(tempfile.mkdtemp(prefix="d"))
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


def _basic():
    policy = compose_custom_policy(())
    transform = InstanceTransform(policy, KEY, unvalidated_policy=True)
    return transform, method_digest(policy, vocabulary=None, reviewed_roi_names=None)


def _slice(number, patient_id):
    dataset = synthetic.ct_slice(number)
    dataset.PatientID = patient_id
    return dataset


def test_the_transform_gives_the_runs_digest_in_its_evidence():
    transform, digest = _basic()
    data = synthetic.written(_slice(0, "ZQ1"))

    result = transform(data, InstanceRecord.from_file(data))

    assert isinstance(result, run.Transformed)
    assert isinstance(result.evidence, Coverage)
    assert result.evidence.method_digest == digest
    written = pydicom.dcmread(pydicom.filebase.DicomBytesIO(result.data))
    assert list(written.DeidentificationMethod)[0] == digest


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_run_releases_and_counts_a_patient_id_found_in_its_digest(tmp_path):
    # A Patient ID that is, by chance, the run's own digest.
    transform, digest = _basic()
    source = tmp_path / "source"
    source.mkdir()
    for number in range(3):
        data = synthetic.written(_slice(number, digest.upper()))
        (source / f"{number}.dcm").write_bytes(data)

    result = run.run(
        run.discover(source),
        tmp_path / "release",
        transform,
        ReleaseGate(),
        qc_destination=tmp_path / "qc",
        reporter=transform.reporter,
        written_check=transform.written_check,
    )

    assert [outcome.status for outcome in result.outcomes] == [run.Status.RELEASED] * 3
    report = json.loads((result.release / RELEASE_REPORT).read_text(encoding="utf-8"))
    assert report["format"] == FORMAT == "pymedphys-deid-release-report/54"
    assert [
        (entry["attribute"], entry["found_in"], entry["count"])
        for entry in report["exempted_findings"]
        if entry["exemption"] == Exemption.METHOD_DIGEST.value
    ] == [("(0010,0020)", METHOD, 3)]
