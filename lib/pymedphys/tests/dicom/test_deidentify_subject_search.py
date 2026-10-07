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

"""The residual search over every file of a subject, done once for each value.

A subject's values are searched for in each of its files, so the search
derives each value's forms once, and the release gate merges each subject's
coverage once. These tests show that neither changes what a file's gate is
given or what its search finds. Every value is invented.
"""

import dataclasses
import gc
import struct
import weakref
from unittest import mock

from pymedphys._imports import hypothesis, pytest

from pymedphys._dicom.deidentify import residuals
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import ReleaseGate
from pymedphys._dicom.deidentify.release_gate import (
    NOT_REPORTED,
    Coverage,
    Decision,
    SubjectCoverages,
    Uncollected,
)
from pymedphys._dicom.deidentify.residuals import (
    ResidualSearch,
    SourceValue,
    find_residuals,
    not_searched_of,
)

st = hypothesis.strategies

EXPLICIT = b"1.2.840.10008.1.2.1\x00"
NAME = "ZEBEDEE^QUILLON"
YAMADA = "Yamada^Tarou=山田^太郎=やまだ^たろう"


def _path(tag, *items):
    return ElementPath(tuple(items), tag)


def _source(tag, vr, value, codecs=()):
    return SourceValue(_path(tag), vr, value, codecs)


def _element(tag, vr, value):
    """An explicit VR element with a 2-byte length, or a 4-byte one for UT."""
    group, element = divmod(tag, 0x10000)
    if vr == "UT":
        return struct.pack("<HH2sHI", group, element, b"UT", 0, len(value)) + value
    return struct.pack("<HH2sH", group, element, vr.encode(), len(value)) + value


def _private(*values):
    """A file with each ``(vr, bytes)`` in its own private element, padded."""
    data_set = _element(0x00190010, "LO", b"PRIVATE ")
    for number, (vr, value) in enumerate(values):
        data_set += _element(0x00191000 + number, vr, value + b" " * (len(value) % 2))
    return bytes(128) + b"DICM" + _element(0x00020010, "UI", EXPLICIT) + data_set


# Values of each kind the search derives forms from, with values equal to a
# constant the engine writes, a value of a VR it does not search, and values
# in several character sets.
VALUES = (
    _source("(0010,0010)", "PN", NAME),
    _source("(0010,0020)", "LO", "ZQ7741093"),
    _source("(0010,0030)", "DA", "19710203"),
    _source("(0020,000D)", "UI", "1.2.999.4417.1.20240517.1"),
    _source("(0008,002A)", "DT", "20240517093000"),
    _source("(0008,0090)", "PN", "MÜLLER^JÖRG", ("latin_1",)),
    _source("(0008,1070)", "PN", "WU^LI"),
    _source("(0010,1001)", "PN", YAMADA, ("iso8859", "iso2022_jp")),
    _source("(0010,1002)", "PN", "DEIDENTIFIED\\ZEBEDEE^QUILLON"),
    _source("(0008,0050)", "SH", "DEIDENTIFIED"),
    _source("(0010,0040)", "CS", "F"),
    _source("(0008,1030)", "LO", "ZARQUON ÄRZTE STUDIE", ("latin_1",)),
)

# Files that hold some of the values, in some of their forms and encodings.
FILES = (
    _private(),
    _private(
        ("LT", b"Dr Zebedee Quillon, 1971-02-03"),
        ("LO", b"ZQ7741093"),
        ("UT", b"1.2.999.4417.1.20240517.1\\20240517"),
    ),
    _private(
        ("LT", YAMADA.encode("iso2022_jp")),
        ("LT", "MÜLLER JÖRG".encode("latin-1")),
        ("LT", "Wu Li".encode("utf-16-le")),
        ("LT", "ZARQUON ÄRZTE STUDIE".encode()),
    ),
    _private(("LT", b"DEIDENTIFIED^DEIDENTIFIED 19000101")),
)


@hypothesis.settings(deadline=None)
@hypothesis.given(
    picks=st.lists(
        st.tuples(st.integers(0, len(VALUES) - 1), st.booleans()), max_size=16
    ),
    file=st.sampled_from(FILES),
)
def test_a_search_with_its_values_derived_already_finds_what_the_first_did(picks, file):
    # Repeated values, some equal but not the same, in any order, as a
    # subject's instances collect them.
    values = [
        dataclasses.replace(VALUES[index]) if copy else VALUES[index]
        for index, copy in picks
    ]
    with mock.patch.object(residuals, "_PREPARED", weakref.WeakKeyDictionary()):
        first = find_residuals(file, values)
        first_omitted = not_searched_of(values)
        again = [find_residuals(file, values) for _ in range(2)]
        again_omitted = not_searched_of(values)

    assert isinstance(first, ResidualSearch)
    assert again == [first, first]
    assert again_omitted == first_omitted == first.not_searched


def test_the_values_find_what_they_should_in_the_files():
    # So that the comparison above is between searches that find things.
    found = {
        str(finding.source)
        for file in FILES
        for finding in find_residuals(file, VALUES).findings
    }
    assert found == {
        "(0010,0010)",
        "(0010,0020)",
        "(0010,0030)",
        "(0020,000D)",
        "(0008,002A)",
        "(0008,0090)",
        "(0008,1070)",
        "(0010,1001)",
        "(0010,1002)",
        "(0008,1030)",
    }


def test_each_value_is_derived_once_for_every_file_searched():
    values = [
        _source("(0010,0010)", "PN", "QUAGGA^ZEPHYRINE"),
        _source("(0010,0020)", "LO", "QZ55190327"),
    ]
    # The same values, as a sibling instance collects them.
    copies = [dataclasses.replace(value) for value in values]
    file = _private(("LT", b"Quagga QZ55190327"))

    derive_forms = residuals._derive  # pylint: disable = protected-access
    with mock.patch.object(residuals, "_derive", wraps=derive_forms) as derive:
        results = [find_residuals(file, [*values, *copies]) for _ in range(3)]
        not_searched_of(copies)

    assert derive.call_count == len(values)
    assert len(results[0].findings) == 2
    assert results[1:] == results[:1] * 2


def test_a_values_forms_are_kept_only_while_an_equal_value_is():
    prepared = residuals._PREPARED  # pylint: disable = protected-access
    value = _source("(0010,0010)", "PN", "OKAPI^XENOCRATES")
    find_residuals(b"", [value])
    assert _source("(0010,0010)", "PN", "OKAPI^XENOCRATES") in prepared

    del value
    gc.collect()

    assert _source("(0010,0010)", "PN", "OKAPI^XENOCRATES") not in prepared


def test_anything_but_a_source_value_is_still_refused():
    with pytest.raises(TypeError, match="SourceValue"):
        find_residuals(b"", [NAME])
    with pytest.raises(TypeError, match="SourceValue"):
        not_searched_of([NAME])


# The gate merges a subject's coverages once, and gives each file's condition
# the coverage that merging them all, its own first, gives.

TAGS = ("(0010,0010)", "(0010,0020)", "(0008,0050)", "(0020,000D)", "(0008,1030)")
_paths = st.sampled_from(
    [_path(tag) for tag in TAGS] + [_path("(0010,0020)", ("(0010,1002)", 0))]
)
_values = st.builds(
    SourceValue, _paths, st.just("LO"), st.sampled_from(["ZQ1", "ZQ2", "ZQ3"])
)
_gaps = st.builds(
    Uncollected, _paths, st.sampled_from(["could not be decoded", NOT_REPORTED])
)
_coverages = st.builds(
    lambda planned, collected, uncollected, latin_1: Coverage(
        planned=frozenset(planned),
        collected=tuple(collected),
        uncollected=tuple(uncollected),
        decoded_as_bytes=frozenset(latin_1),
    ),
    st.lists(_paths, max_size=4),
    st.lists(_values, max_size=4),
    st.lists(_gaps, max_size=2),
    st.lists(_paths, max_size=1),
)


class _Released:
    decision = Decision.RELEASE
    reasons = ()
    search = ResidualSearch((), (), True)


@hypothesis.settings(deadline=None)
@hypothesis.given(
    subjects=st.lists(st.lists(_coverages, min_size=1, max_size=5), max_size=4),
    order=st.randoms(use_true_random=False),
    kept=st.integers(1, 3),
)
def test_each_files_coverage_is_what_merging_all_of_them_gives(subjects, order, kept):
    pools = SubjectCoverages(kept)
    # The files of several subjects, interleaved, as a run's positions may be.
    files = [(subject, own) for subject in subjects for own in subject]
    order.shuffle(files)
    for subject, own in files:
        others = [each for each in subject if each is not own]
        if order.random() < 0.25:  # not in the order of the first file's
            order.shuffle(others)
        assert pools.merge((own, *others)) == Coverage.merge(own, *others)


def test_no_coverages_merge_to_nothing_and_only_coverages_merge():
    pools = SubjectCoverages()
    assert pools.merge(()) == Coverage.merge()
    with pytest.raises(TypeError):
        pools.merge((Coverage.merge(), "SENTINEL"))
    with pytest.raises(ValueError):
        SubjectCoverages(0)
    assert repr(pools) == "SubjectCoverages(kept=64)"


def test_the_gate_gives_each_file_the_coverage_of_its_subject():
    seen = []

    def condition(coverage, _written):
        seen.append(coverage)
        return _Released()

    gate = ReleaseGate(condition)
    subject = [
        Coverage(planned=frozenset({_path(tag)}), collected=(value,))
        for tag, value in zip(TAGS, VALUES)
    ]
    for own in subject:
        others = [each for each in subject if each is not own]
        gate(b"written", own, (own, *others))
        assert seen.pop() == Coverage.merge(own, *others)


def test_the_gate_merges_a_subjects_coverages_once():
    subject = [
        Coverage(planned=frozenset({_path(tag)}), collected=()) for tag in TAGS[:3]
    ]
    gate = ReleaseGate(lambda coverage, written: _Released())

    with mock.patch.object(Coverage, "merge", wraps=Coverage.merge) as merge:
        for own in subject:
            others = [each for each in subject if each is not own]
            gate(b"written", own, (own, *others))

    whole = [call for call in merge.call_args_list if len(call.args) == len(subject)]
    assert len(whole) == 1
