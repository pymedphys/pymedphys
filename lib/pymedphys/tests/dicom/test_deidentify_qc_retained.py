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

"""The strings that an instance's plan retains, for the QC pack's review.

Every file and value is synthetic. Values that must never appear in an error
carry the text ``SENTINEL``.
"""

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import qc_retained
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.qc_pack import QcPackError, retained_strings
from pymedphys._dicom.deidentify.qc_retained import retained_paths, retained_text
from pymedphys._dicom.deidentify.run_qc import RetainedText
from pymedphys._dicom.deidentify.walker import ElementPlan, InstancePlan

from .test_deidentify_walker import _path, _plan

pytestmark = pytest.mark.pydicom

CHARACTER_SET = _path("(0008,0005)")
FIRST_BEAM_NUMBER = _path(("(300A,00B0)", 0), "(300A,00C0)")
SECOND_BEAM_NUMBER = _path(("(300A,00B0)", 1), "(300A,00C0)")


def _element(path, vr="LO", action="K", removed_with=None, removed_for=None):
    return ElementPlan(
        path=path,
        vr=vr,
        rule=None,
        action=action,
        removed_with=removed_with,
        consumers=frozenset(),
        removed_for=removed_for,
    )


def _instance(*elements):
    return InstancePlan(elements=tuple(elements), sequestrations=())


def test_the_walker_plan_retains_its_kept_text_in_file_order():
    # The RT Plan keeps Specific Character Set and both Beam Numbers as they
    # are. Its replaced UIDs, emptied name, removed private and unlisted
    # elements, dummy label, and kept sequence and US element are not text
    # that the plan retains.
    assert retained_paths(_plan()) == (
        CHARACTER_SET,
        FIRST_BEAM_NUMBER,
        SECOND_BEAM_NUMBER,
    )


@pytest.mark.parametrize("action", ["X", "Z", "D", "U", "C"])
def test_an_element_the_plan_changes_is_not_retained(action):
    assert not retained_paths(_instance(_element(_path("(0008,1030)"), action=action)))


def test_an_element_removed_with_its_sequence_or_for_another_is_not_retained():
    sequence = _path("(0008,1110)")
    removed_for = _path("(6000,3000)")
    plan = _instance(
        _element(_path(("(0008,1110)", 0), "(0008,1150)"), removed_with=sequence),
        _element(_path("(6000,0022)"), removed_for=removed_for),
    )

    assert not retained_paths(plan)


@pytest.mark.parametrize("vr", ["UI", "SQ", "US", "OB", "FD", "AT", "UN", None])
def test_an_element_whose_value_is_not_text_is_not_retained(vr):
    assert not retained_paths(_instance(_element(_path("(0008,1030)"), vr=vr)))


@pytest.mark.parametrize("vr", sorted(qc_retained.RETAINED_TEXT_VRS))
def test_a_kept_element_of_each_text_vr_is_retained(vr):
    path = _path("(0008,1030)")

    assert retained_paths(_instance(_element(path, vr=vr))) == (path,)


def test_a_plan_must_be_an_instance_plan():
    with pytest.raises(TypeError, match="InstancePlan"):
        retained_paths(object())  # type: ignore[arg-type]


def test_retained_text_splits_multiple_values_and_skips_empty_ones():
    description = _path("(0008,1030)")
    types = _path("(0008,0008)")
    station = _path("(0008,1010)")
    plan = _instance(
        _element(description),
        _element(types, vr="CS"),
        _element(station, vr="SH"),
    )
    values = {
        description: "QUILLON CLINIC CT",
        types: pydicom.multival.MultiValue(str, ["ORIGINAL", "", "AXIAL"]),
        station: None,
    }

    found = retained_text(plan, values)

    assert [(text.value, text.path) for text in found] == [
        ("QUILLON CLINIC CT", description),
        ("ORIGINAL", types),
        ("AXIAL", types),
    ]


def test_retained_text_gives_numbers_and_names_as_they_were_written():
    number = _path("(0020,0013)")
    thickness = _path("(0018,0050)")
    operator = _path("(0008,1070)")
    plan = _instance(
        _element(number, vr="IS"),
        _element(thickness, vr="DS"),
        _element(operator, vr="PN"),
    )
    values = {
        number: pydicom.valuerep.IS("0007"),
        thickness: pydicom.valuerep.DSfloat("2.50", auto_format=False),
        operator: pydicom.valuerep.PersonName("ZEBEDEE^QUILLON"),
    }

    found = retained_text(plan, values)

    assert [text.value for text in found] == ["0007", "2.50", "ZEBEDEE^QUILLON"]


def test_retained_text_reads_a_walker_plan_with_decoded_values():
    values = {
        CHARACTER_SET: "ISO_IR 100",
        FIRST_BEAM_NUMBER: pydicom.valuerep.IS("1"),
        SECOND_BEAM_NUMBER: pydicom.valuerep.IS("2"),
    }

    assert retained_text(_plan(), values) == (
        RetainedText("ISO_IR 100", CHARACTER_SET),
        RetainedText("1", FIRST_BEAM_NUMBER),
        RetainedText("2", SECOND_BEAM_NUMBER),
    )


def test_a_retained_value_that_was_not_read_is_refused():
    with pytest.raises(QcPackError, match=r"\(300A,00C0\) was not read") as caught:
        retained_text(_plan(), {CHARACTER_SET: "ISO_IR 100"})

    assert "ISO_IR" not in str(caught.value)


@pytest.mark.parametrize(
    "value",
    [b"SENTINEL", 7, 2.5, ["SENTINEL", b"SENTINEL"]],
    ids=["bytes", "int", "float", "list holding bytes"],
)
def test_a_retained_value_that_is_not_decoded_text_is_refused(value):
    path = _path("(0008,1030)")

    with pytest.raises(QcPackError, match="not decoded text") as caught:
        retained_text(_instance(_element(path)), {path: value})

    assert "SENTINEL" not in str(caught.value)
    assert "(0008,1030)" in str(caught.value)


def test_values_for_paths_the_plan_does_not_retain_are_ignored():
    removed = _path("(0010,0010)")
    plan = _instance(_element(removed, vr="PN", action="X"))

    assert not retained_text(plan, {removed: "SENTINEL^NAME"})


def test_retained_text_becomes_the_packs_distinct_retained_strings():
    description = ElementPath((), "(0008,1030)")
    first = _instance(_element(description))
    second = _instance(_element(description))

    found = [
        *retained_text(first, {description: "QUILLON CLINIC CT"}),
        *retained_text(second, {description: "QUILLON CLINIC CT"}),
    ]
    strings = retained_strings(
        (text.value, position, text.path) for text, position in zip(found, (0, 1))
    )

    assert len(strings) == 1
    assert strings[0].value == "QUILLON CLINIC CT"
    assert strings[0].places == ((0, description), (1, description))
