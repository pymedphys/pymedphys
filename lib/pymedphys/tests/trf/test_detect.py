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


from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

import pymedphys
from pymedphys._trf.decode import detect
from pymedphys._trf.decode.header import decode_header
from pymedphys._trf.decode.partition import split_into_header_table

# Two columns, each named by an item part pair: control point and linac state.
ITEM_PARTS = np.array([2240, 111, 2543, 111], dtype=np.int16)


def _version_3_table(rows):
    """Each row is an 8 byte timestamp then one 2 byte value per column."""
    return b"".join(
        np.array([row], dtype=np.int64).tobytes()
        + np.array([row, 3], dtype=np.int16).tobytes()
        for row in range(rows)
    )


def test_the_layouts_that_fit_a_table_are_found():
    table = _version_3_table(5)

    layouts = detect.search_for_possible_decoding_options(table, len(ITEM_PARTS))

    # Layouts 2 and 3 are identical, and a 12 byte row splits evenly into the
    # 4 byte rows of layout 1. Layout 4's 16 byte rows do not fit.
    assert layouts == [1, 2, 3]


def test_a_table_no_layout_fits_is_reported():
    table = _version_3_table(5)[:-1]

    assert not detect.search_for_possible_decoding_options(table, len(ITEM_PARTS))


def test_a_new_item_part_does_not_hide_the_layouts_that_fit():
    # A newer linac software version may log a column PyMedPhys cannot name
    # yet, in a row layout it already knows.
    item_parts = np.array([2240, 111, 1, 2], dtype=np.int16)
    table = _version_3_table(5)

    layouts = detect.search_for_possible_decoding_options(table, len(item_parts))

    assert layouts == [1, 2, 3]
    assert detect.unknown_item_parts(item_parts) == ["1_2"]


def test_item_parts_without_a_column_name_are_reported():
    item_parts = np.array([2240, 111, 1, 2], dtype=np.int16)

    assert detect.unknown_item_parts(item_parts) == ["1_2"]
    assert detect.unknown_item_parts(ITEM_PARTS) == []


def test_the_command_fails_when_no_layout_fits(tmp_path, monkeypatch):
    monkeypatch.setattr(detect, "detect_file_encoding", lambda filepath: [])

    with pytest.raises(SystemExit) as raised:
        detect.detect_cli(type("Args", (), {"filepath": tmp_path / "a.trf"})())

    assert raised.value.code != 0


def test_a_real_file_fits_the_layout_its_header_names():
    path = pymedphys.data_path("negative-metersetmap.trf")
    with open(path, "rb") as f:
        header_contents, _ = split_into_header_table(f.read())

    layouts = detect.detect_file_encoding(path)

    assert decode_header(header_contents).version in layouts
