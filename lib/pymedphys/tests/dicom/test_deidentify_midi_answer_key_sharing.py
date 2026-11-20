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

"""Tests that an answer key's checks share their repeated parts (D-018).

A MIDI-B answer key holds millions of checks, so the reader keeps one copy
of each repeated place, element, category set, and text, and keeps each
field in a slot. Every answer key here is synthetic.
"""

import hashlib
import json

from pymedphys._dicom.deidentify import midi_answer_key
from pymedphys._dicom.deidentify.midi_answer_key import (
    AnswerInstance,
    AnswerKey,
    AttributePath,
    Categories,
    Category,
    Check,
    Element,
    parse_check,
    read_answer_key,
)

from .test_deidentify_midi_benchmark import _answer_key, _check, _row

NESTED = '<(0040,A730)>[<0002>]<(0040,A730)>[<0000>]<(0019,"SYNTHETIC",10)>'
TOP = "<(0040,A730)>[<0001>]<(0040,A124)>"


def _checks(instance):
    return [
        _check("text_removed", NESTED, text=f"WORD {instance}", hipaa_z="TEST-Z"),
        _check("uid_consistent", TOP, value="2.25.900", dicom_p15="TEST-U"),
        _check("tag_retained", "<(0008,0060)>", dicom_iod="TEST-IOD"),
        _check("pixels_retained", text="0" * 32),
        _check("text_removed", "(0010,0010)", text="UNREADABLE PLACE"),
    ]


def _key(tmp_path, instances):
    return _answer_key(
        tmp_path / "key.db",
        [_row(f"2.25.{1000 + n}", _checks(n)) for n in range(instances)],
    )


def test_a_keys_classes_keep_their_fields_in_slots():
    for cls in (
        Element,
        AttributePath,
        Categories,
        Category,
        Check,
        AnswerInstance,
        AnswerKey,
    ):
        assert "__slots__" in vars(cls)
    check = parse_check(_check("tag_retained", TOP, dicom_iod="TEST-IOD"))
    assert not hasattr(check, "__dict__")
    assert not hasattr(check.path, "__dict__")


def test_repeated_parts_of_checks_are_shared(tmp_path):
    key = read_answer_key(_key(tmp_path, 3))
    first, *others = [instance.checks for instance in key.instances]

    for checks in others:
        for mine, theirs in zip(first, checks):
            assert mine.path is theirs.path
            assert mine.categories is theirs.categories
            assert mine.action_name is theirs.action_name
        # The same value is shared too, wherever it is.
        assert first[1].value is checks[1].value
    # Places that hold the same element share it.
    assert first[0].path.elements[0] is first[1].path.elements[0]
    assert first[0].path.elements[0] is first[0].path.elements[1]
    # Checks without categories share one empty set.
    assert first[3].categories is first[4].categories
    assert first[3].categories == Categories()


def test_shared_checks_equal_those_read_one_by_one(tmp_path):
    key = read_answer_key(_key(tmp_path, 2))

    for number, instance in enumerate(key.instances):
        assert list(instance.checks) == [
            parse_check(json.loads(json.dumps(each))) for each in _checks(number)
        ]
    assert key.instances[0].checks[4].path_unreadable


def test_a_key_of_many_rows_is_read_whole_and_in_order(tmp_path):
    rows = 3 * midi_answer_key._ROWS_AT_ONCE + 7  # pylint: disable = protected-access
    path = _key(tmp_path, rows)

    key = read_answer_key(path)

    assert [instance.sop_instance_uid for instance in key.instances] == [
        f"2.25.{1000 + n}" for n in range(rows)
    ]
    assert [instance.checks[0].action_text for instance in key.instances] == [
        f"WORD {n}" for n in range(rows)
    ]
    assert key.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
