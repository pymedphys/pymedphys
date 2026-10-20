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

"""Each study's series renumbered by their order."""

import io

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import run
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import InstanceTransform
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.references import (
    InstanceRecord,
    with_series_numberings,
)
from pymedphys._dicom.deidentify.series_numbers import (
    SeriesNumbering,
    SeriesNumberings,
    SeriesNumberUse,
    number_series,
    series_number,
)

from . import _synthetic_references as synthetic

# A run needs a base directory short enough for Windows' output path limit.
from .test_deidentify_run import (  # noqa: F401  # pylint: disable = unused-import
    _short_tmp_path,
)

pytestmark = pytest.mark.pydicom

KEY = DeidKey(bytes(range(32)))
SERIES_NUMBER = 0x00200011
SOURCE_SERIES_INFORMATION_SEQUENCE = 0x3006004C
OTHER_STUDY = "2.25.900"
TOP = ElementPath((), "(0020,0011)")


def _item(index):
    """Return the path of the Series Number of a Source Series item."""
    return ElementPath((("(3006,004C)", index),), "(0020,0011)")


@pytest.mark.parametrize(
    "value, number",
    [
        ("7", 7),
        ("0007", 7),
        (" 7 ", 7),
        ("+7", 7),
        ("-3", -3),
        ("0", 0),
        ("20230512", 20230512),
        ("-2147483648", -(2**31)),
        ("2147483647", 2**31 - 1),
        ("2147483648", None),
        ("000000000007", 7),
        ("0000000000007", None),  # 13 characters
        ("", None),
        ("  ", None),
        ("7.0", None),
        ("1e3", None),
        ("7 8", None),
        ("SERIES", None),
        (7, 7),
        (True, None),
        (None, None),
        (b"7", None),
        (["7"], None),
    ],
)
def test_a_series_number_is_one_integer_string(value, number):
    assert series_number(value) == number


def test_pydicoms_integer_string_gives_its_number():
    assert series_number(pydicom.valuerep.IS("0007")) == 7


def test_each_distinct_number_takes_its_rank_in_ascending_order():
    numbering = SeriesNumbering.of([20230601, 7, 20230512, 7, -1])

    assert numbering.numbers == (-1, 7, 20230512, 20230601)
    assert [numbering.rank(each) for each in (-1, 7, 20230512, 20230601)] == [
        1,
        2,
        3,
        4,
    ]
    assert numbering.rank(8) is None
    assert numbering.rank(None) is None
    assert SeriesNumbering().rank(1) is None


def test_the_repr_shows_no_number():
    numbering = SeriesNumbering.of([20230512, 7])
    use = SeriesNumberUse(TOP, 20230512, synthetic.CT_SERIES)

    assert repr(numbering) == "SeriesNumbering(2 numbers)"
    assert repr(use) == "SeriesNumberUse((0020,0011))"
    assert repr(SeriesNumberings.of({TOP: numbering})) == "SeriesNumberings(1 places)"


def test_each_series_number_takes_the_numbering_of_the_study_of_its_series():
    uses = {
        0: (SeriesNumberUse(TOP, 100, "2.25.1"),),
        1: (SeriesNumberUse(TOP, 200, "2.25.2"),),
        # A structure set of another study, naming series 2.25.1.
        2: (
            SeriesNumberUse(TOP, 20, "2.25.3"),
            SeriesNumberUse(_item(0), 100, "2.25.1"),
        ),
        # Neither series is in a study of the run.
        3: (SeriesNumberUse(TOP, 5, None), SeriesNumberUse(_item(0), 7, "2.25.9")),
    }
    studies = {"2.25.1": "2.25.10", "2.25.2": "2.25.10", "2.25.3": "2.25.30"}

    numbered = number_series(uses, studies)

    shared = SeriesNumbering.of([100, 200])
    assert numbered[0] == numbered[1] == SeriesNumberings.of({TOP: shared})
    assert numbered[2] == SeriesNumberings.of(
        {TOP: SeriesNumbering.of([20]), _item(0): shared}
    )
    assert numbered[3] == SeriesNumberings()


def _source_series(*numbers):
    items = []
    for number in numbers:
        item = pydicom.Dataset()
        item.Modality = "CT"
        item.SeriesInstanceUID = synthetic.CT_SERIES
        item.SeriesNumber = number
        items.append(item)
    return pydicom.DataElement(SOURCE_SERIES_INFORMATION_SEQUENCE, "SQ", items)


def _structure_set(number, *source_numbers):
    dataset = synthetic.structure_set()
    dataset.SeriesNumber = number
    if source_numbers:
        dataset[SOURCE_SERIES_INFORMATION_SEQUENCE] = _source_series(*source_numbers)
    return dataset


@pytest.mark.parametrize(
    "transfer_syntax",
    [synthetic.EXPLICIT_VR_LITTLE_ENDIAN, synthetic.IMPLICIT_VR_LITTLE_ENDIAN],
)
def test_a_record_holds_each_series_number_with_the_series_it_numbers(
    transfer_syntax,
):
    record = synthetic.record(
        _structure_set("20230601", "20230512", "7"), transfer_syntax
    )

    assert {(use.path, use.number, use.series) for use in record.series_numbers} == {
        (TOP, 20230601, synthetic.STRUCTURE_SET_SERIES),
        (_item(0), 20230512, synthetic.CT_SERIES),
        (_item(1), 7, synthetic.CT_SERIES),
    }
    # Built alone, it ranks only the values that number its own series.
    assert record.series_numberings == SeriesNumberings.of(
        {TOP: SeriesNumbering.of([20230601])}
    )


def test_a_record_leaves_out_a_series_number_that_is_not_one_number():
    dataset = _structure_set("20230601", "20230512")
    dataset[SERIES_NUMBER] = _integer_string(b"7\\8 ")
    dataset[SOURCE_SERIES_INFORMATION_SEQUENCE].value[0][SERIES_NUMBER] = (
        _integer_string(b"SERIES")
    )

    record = synthetic.record(dataset)

    assert {(use.path, use.number) for use in record.series_numbers} == {
        (TOP, None),
        (_item(0), None),
    }
    assert record.series_numberings == SeriesNumberings()


def test_a_record_of_an_instance_without_an_iod_ranks_nothing():
    dataset = _structure_set("20230601")
    dataset.SOPClassUID = "2.25.3"

    record = synthetic.record(dataset)

    assert record.series_numbers == ()
    assert record.series_numberings == SeriesNumberings()


def _integer_string(value):
    """Return a Series Number of ``value``, still raw, as pydicom cannot read it."""
    return pydicom.dataelem.RawDataElement(
        pydicom.tag.Tag(SERIES_NUMBER), "IS", len(value), value, 0, False, True
    )


def _ct_slice(number, value, series=synthetic.CT_SERIES):
    """Return a CT slice of the study, numbered ``value``, of ``series``."""
    dataset = synthetic.ct_slice(number)
    dataset.SeriesNumber = value
    dataset.SeriesInstanceUID = series
    return dataset


def _transformed(structure_set, *others):
    """Return a structure set as the transform writes it among ``others``."""
    data = synthetic.written(structure_set)
    records = with_series_numberings(
        {
            0: InstanceRecord.from_file(data),
            **{
                index: synthetic.record(other)
                for index, other in enumerate(others, start=1)
            },
        }
    )
    transform = InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True)
    result = transform(data, records[0])
    assert isinstance(result, run.Transformed)
    return result.data, pydicom.dcmread(io.BytesIO(result.data))


@pytest.mark.deid_requirement("MIDI-BP-03", "MIDI-BP-06")
def test_the_transform_writes_each_series_numbers_rank_in_its_studys_numbering():
    data, written = _transformed(
        _structure_set("20230601", "20230512"), _ct_slice(0, "20230512")
    )

    assert written.SeriesNumber == 2
    (item,) = written[SOURCE_SERIES_INFORMATION_SEQUENCE].value
    assert item.SeriesNumber == 1
    assert b"20230601" not in data
    assert b"20230512" not in data


@pytest.mark.deid_requirement("MIDI-BP-03", "MIDI-BP-06")
def test_a_source_series_of_another_study_takes_its_own_studys_rank():
    # The CT series of the other study is numbered 100 and 200. The structure
    # set's own study holds only its own number, 20.
    structure_set = _structure_set("20", "100")
    structure_set.StudyInstanceUID = OTHER_STUDY
    others = (
        _ct_slice(0, "100"),
        _ct_slice(1, "200", synthetic.OTHER_SERIES),
    )

    _, written = _transformed(structure_set, *others)

    assert written.SeriesNumber == 1
    # The CT series' own rank, not one in the structure set's study.
    (item,) = written[SOURCE_SERIES_INFORMATION_SEQUENCE].value
    assert item.SeriesNumber == 1


@pytest.mark.deid_requirement("MIDI-BP-06")
def test_a_source_series_that_the_run_does_not_hold_takes_ds_dummy_value():
    _, written = _transformed(_structure_set("20230601", "20230512"))

    assert written.SeriesNumber == 1
    # Type 1 in the item, so D applies, and its dummy value is not a rank.
    (item,) = written[SOURCE_SERIES_INFORMATION_SEQUENCE].value
    assert item.SeriesNumber == 0


def _record_numberings(numberings):
    """Return a transform that records each instance's numberings, then sequesters."""

    def transform(data, record):
        del data
        numberings[record.sop_instance] = record.series_numberings
        return run.Sequestered((run.RunReason.INTERNAL_ERROR,))

    return transform


def test_the_run_numbers_each_series_in_the_study_that_holds_it(tmp_path):
    plan = synthetic.rt_plan()
    plan.SeriesNumber = "1"
    structure_set = _structure_set("20", "20230512")
    structure_set.StudyInstanceUID = OTHER_STUDY
    source = tmp_path / "source"
    source.mkdir()
    for index, dataset in enumerate((_ct_slice(0, "20230512"), structure_set, plan)):
        (source / f"{index:03d}.dcm").write_bytes(synthetic.written(dataset))
    numberings = {}

    run.run(
        run.discover(source),
        tmp_path / "release",
        _record_numberings(numberings),
        lambda written, evidence, subject: run.Release(),
        qc_destination=tmp_path / "qc",
    )

    study = SeriesNumbering.of([1, 20230512])
    assert numberings == {
        synthetic.CT_SLICES[0]: SeriesNumberings.of({TOP: study}),
        synthetic.STRUCTURE_SET: SeriesNumberings.of(
            {TOP: SeriesNumbering.of([20]), _item(0): study}
        ),
        synthetic.PLAN: SeriesNumberings.of({TOP: study}),
    }
