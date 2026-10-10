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

import dataclasses
import io

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import run
from pymedphys._dicom.deidentify.instance_transform import InstanceTransform
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.series_numbers import (
    SeriesNumbering,
    number_studies,
    series_number,
)

from . import _synthetic_references as synthetic

pytestmark = pytest.mark.pydicom

KEY = DeidKey(bytes(range(32)))
SERIES_NUMBER = 0x00200011
SOURCE_SERIES_INFORMATION_SEQUENCE = 0x3006004C


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
    assert repr(SeriesNumbering.of([20230512, 7])) == "SeriesNumbering(2 numbers)"


def test_every_instance_of_a_study_takes_the_numbering_of_the_whole_study():
    own = {
        0: SeriesNumbering.of([20230512]),
        1: SeriesNumbering.of([20230601, 20230512]),
        2: SeriesNumbering.of([3]),
        3: SeriesNumbering.of([5]),
    }
    studies = {0: "2.25.1", 1: "2.25.1", 2: "2.25.2", 3: None}

    numbered = number_studies(own, studies)

    assert numbered[0] == numbered[1] == SeriesNumbering.of([20230512, 20230601])
    assert numbered[2] == SeriesNumbering.of([3])
    # No study holds an instance without a Study Instance UID.
    assert numbered[3] == own[3]


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
def test_a_record_ranks_the_series_numbers_where_its_iod_defines_them(
    transfer_syntax,
):
    record = synthetic.record(
        _structure_set("20230601", "20230512", "7"), transfer_syntax
    )

    assert record.series_numbering == SeriesNumbering.of([7, 20230512, 20230601])


def test_a_record_leaves_out_a_series_number_that_is_not_one_number():
    dataset = _structure_set("20230601", "20230512")
    dataset[SERIES_NUMBER] = _integer_string(b"7\\8 ")
    dataset[SOURCE_SERIES_INFORMATION_SEQUENCE].value[0][SERIES_NUMBER] = (
        _integer_string(b"SERIES")
    )

    record = synthetic.record(dataset)

    assert record.series_numbering == SeriesNumbering()


def test_a_record_of_an_instance_without_an_iod_ranks_nothing():
    dataset = _structure_set("20230601")
    dataset.SOPClassUID = "2.25.3"

    assert synthetic.record(dataset).series_numbering == SeriesNumbering()


def _integer_string(value):
    """Return a Series Number of ``value``, still raw, as pydicom cannot read it."""
    return pydicom.dataelem.RawDataElement(
        pydicom.tag.Tag(SERIES_NUMBER), "IS", len(value), value, 0, False, True
    )


def _written(result):
    assert isinstance(result, run.Transformed)
    return pydicom.dcmread(io.BytesIO(result.data))


@pytest.mark.deid_requirement("MIDI-BP-03", "MIDI-BP-06")
def test_the_transform_writes_each_series_numbers_rank_in_its_studys_numbering():
    data = synthetic.written(_structure_set("20230601", "20230512"))
    record = dataclasses.replace(
        InstanceRecord.from_file(data),
        series_numbering=SeriesNumbering.of([7, 20230512, 20230601]),
    )
    transform = InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True)

    result = transform(data, record)
    written = _written(result)

    assert written.SeriesNumber == 3
    (item,) = written[SOURCE_SERIES_INFORMATION_SEQUENCE].value
    assert item.SeriesNumber == 2
    assert b"20230601" not in result.data
    assert b"20230512" not in result.data


def _record_numberings(numberings):
    """Return a transform that records each instance's numbering, then sequesters."""

    def transform(data, record):
        del data
        numberings[record.sop_instance] = record.series_numbering
        return run.Sequestered((run.RunReason.INTERNAL_ERROR,))

    return transform


def test_the_run_gives_every_instance_its_studys_numbering(tmp_path):
    ct_slice = synthetic.ct_slice(0)
    ct_slice.SeriesNumber = "20230512"
    plan = synthetic.rt_plan()
    plan.SeriesNumber = "1"
    source = tmp_path / "source"
    source.mkdir()
    for index, dataset in enumerate(
        (ct_slice, _structure_set("20230601", "20230512"), plan)
    ):
        (source / f"{index:03d}.dcm").write_bytes(synthetic.written(dataset))
    numberings = {}

    run.run(
        run.discover(source),
        tmp_path / "release",
        _record_numberings(numberings),
        lambda written, evidence, subject: run.Release(),
        qc_destination=tmp_path / "qc",
    )

    study = SeriesNumbering.of([1, 20230512, 20230601])
    assert numberings == {
        synthetic.CT_SLICES[0]: study,
        synthetic.STRUCTURE_SET: study,
        synthetic.PLAN: study,
    }
