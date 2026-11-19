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

"""Count what candidate exemptions from the text search would release (D-018).

Every DICOM file here is synthetic.
"""

import collections

from pymedphys._imports import pydicom

from pymedphys._dicom.deidentify import midi_benchmark as benchmark
from pymedphys._dicom.deidentify import midi_benchmark_exemptions as exemptions
from pymedphys._dicom.deidentify.file_layout import ElementPath, Location, Region
from pymedphys._dicom.deidentify.reasons import RunReason
from pymedphys._dicom.deidentify.release_gate import (
    Decision,
    ReasonCode,
    ReleaseReason,
)

from . import _synthetic_references as synthetic
from .test_deidentify_midi_benchmark import STUDY_DESCRIPTION, _benchmark_key
from .test_deidentify_midi_benchmark import _source as _benchmark_source
from .test_deidentify_run import (  # noqa: F401  # pylint: disable = unused-import
    _short_tmp_path,
)

CODE_MEANING = ElementPath(
    items=(("(0054,0016)", 0), ("(0054,0304)", 1)), tag="(0008,0104)"
)
EVERY = (exemptions.CODED, exemptions.EQUIPMENT, exemptions.BOTH)


def _text(found_in, vr):
    return ReleaseReason(
        Decision.QC_REVIEW,
        ReasonCode.RESIDUAL_TEXT,
        ElementPath(items=(), tag="(0009,1004)"),
        Location(Region.DATA_SET, found_in, vr),
    )


def _top(tag):
    return ElementPath(items=(), tag=tag)


def _source(tmp_path, designators):
    """Write a synthetic PET header whose second radiopharmaceutical code
    item has the given designator."""
    items = []
    for designator in designators:
        code = pydicom.Dataset()
        code.CodeValue = "SYNTHETIC-CODE"
        code.CodingSchemeDesignator = designator
        code.CodeMeaning = "SYNTHETIC MEANING"
        items.append(code)
    information = pydicom.Dataset()
    information.RadiopharmaceuticalCodeSequence = items
    dataset = pydicom.Dataset()
    dataset.RadiopharmaceuticalInformationSequence = [information]
    dataset.SOPClassUID = pydicom.uid.PositronEmissionTomographyImageStorage
    dataset.SOPInstanceUID = "2.25.1"
    dataset.file_meta = pydicom.dataset.FileMetaDataset()
    dataset.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
    dataset.file_meta.MediaStorageSOPClassUID = dataset.SOPClassUID
    dataset.file_meta.MediaStorageSOPInstanceUID = dataset.SOPInstanceUID
    path = tmp_path / "source.dcm"
    dataset.save_as(path, enforce_file_format=True)
    return path


def test_a_text_found_in_a_code_string_is_a_coded_value():
    reasons = [_text(_top("(0054,0202)"), "CS")]

    assert exemptions.would_release(reasons, None) == (
        exemptions.CODED,
        exemptions.BOTH,
    )


def test_a_text_found_in_a_coding_scheme_designator_is_a_coded_value():
    designator = ElementPath(items=CODE_MEANING.items, tag="(0008,0102)")

    assert exemptions.would_release([_text(designator, "SH")], None) == (
        exemptions.CODED,
        exemptions.BOTH,
    )


def test_a_text_found_in_equipment_names_is_equipment():
    reasons = [_text(_top("(0008,1090)"), "LO"), _text(_top("(0008,0070)"), "LO")]

    assert exemptions.would_release(reasons, None) == (
        exemptions.EQUIPMENT,
        exemptions.BOTH,
    )


def test_a_code_meaning_counts_only_under_a_standard_designator(tmp_path):
    reasons = [_text(CODE_MEANING, "LO")]

    standard = _source(tmp_path, ["99SYNTHETIC", "SCT"])
    assert exemptions.would_release(reasons, standard) == (
        exemptions.CODED,
        exemptions.BOTH,
    )
    standard.unlink()
    local = _source(tmp_path, ["SCT", "99SYNTHETIC"])
    assert not exemptions.would_release(reasons, local)
    assert not exemptions.would_release(reasons, None)


def test_a_code_meaning_whose_item_the_source_lacks_is_not_exempt(tmp_path):
    reasons = [_text(CODE_MEANING, "LO")]

    assert not exemptions.would_release(reasons, _source(tmp_path, ["SCT"]))


def test_each_reason_must_be_covered_by_the_same_exemption():
    reasons = [_text(_top("(0054,0202)"), "CS"), _text(_top("(0018,1020)"), "LO")]

    assert exemptions.would_release(reasons, None) == (exemptions.BOTH,)


def test_any_other_text_or_reason_releases_nothing():
    text = _text(_top("(0054,0202)"), "CS")
    others = [
        _text(_top("(0008,103E)"), "LO"),
        ReleaseReason(
            Decision.QC_REVIEW,
            ReasonCode.RESIDUAL_TEXT,
            _top("(0008,1030)"),
            Location(Region.TRAILING),
        ),
        ReleaseReason(Decision.WITHHOLD, ReasonCode.UNCOLLECTED, _top("(0028,1101)")),
        RunReason.INTERNAL_ERROR,
    ]

    for other in others:
        assert not exemptions.would_release([text, other], None)
    assert not exemptions.would_release([], None)


def test_the_counts_are_rows_in_the_exemptions_order():
    counted = collections.Counter(
        {
            (exemptions.BOTH, "PT"): 3,
            (exemptions.CODED, "PT"): 2,
            (exemptions.CODED, "CT"): 1,
        }
    )

    assert exemptions.exemption_rows(counted) == [
        {"exemption": exemptions.CODED, "modality": "CT", "instances": 1},
        {"exemption": exemptions.CODED, "modality": "PT", "instances": 2},
        {"exemption": exemptions.BOTH, "modality": "PT", "instances": 3},
    ]
    assert set(EVERY) == set(exemptions.EXEMPTIONS)


def test_a_benchmark_counts_what_each_exemption_would_release(tmp_path):
    source = _benchmark_source(tmp_path)
    # The removed Study Description's text, kept in Manufacturer, holds the
    # CT image for review.
    path = source / "0.dcm"
    ct = pydicom.dcmread(path)
    ct.Manufacturer = STUDY_DESCRIPTION
    path.write_bytes(synthetic.written(ct))

    result = benchmark.run_benchmark(
        source, _benchmark_key(tmp_path), tmp_path / "work"
    )

    assert result.document["coverage"]["would_release"] == [
        {"exemption": exemptions.EQUIPMENT, "modality": "CT", "instances": 1},
        {"exemption": exemptions.BOTH, "modality": "CT", "instances": 1},
    ]
    assert "| equipment | CT | 1 |" in result.markdown()
