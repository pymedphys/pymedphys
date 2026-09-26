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

"""Mosaiq delivery decoding, checked without a database.

Mosaiq stores each bank's leaf positions for a control point as a fixed-width
``binary`` record of little-endian signed 16-bit integers in units of 0.01 cm.
``TxFieldPoint.MLC_Leaves`` says how many of them are in use. The replay tests
feed the mock database's CSV rows to ``DeliveryMosaiq.from_mosaiq`` in the form
the SQL query returns them.
"""

import base64
import struct

from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import pytest

from pymedphys._mosaiq import delivery
from pymedphys._mosaiq.mock import paths

RECORD_BYTES = 200


def _record(positions_cm):
    """Encode leaf positions as a zero-padded Mosaiq leaf-set record."""
    values = [round(position * 100) for position in positions_cm]
    return struct.pack(f"<{len(values)}h", *values).ljust(RECORD_BYTES, b"\x00")


def _decode_b64(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _positions_cm(record, leaf_count):
    """Independent decoding, one leaf at a time."""
    return [
        int.from_bytes(record[2 * i : 2 * i + 2], "little", signed=True) / 100
        for i in range(leaf_count)
    ]


@pytest.fixture(name="mock_tables", scope="module")
def fixture_mock_tables():
    points = pd.read_csv(paths.DATA / "TxFieldPoint.csv")
    fields = pd.read_csv(
        paths.DATA / "TxField.csv", encoding="latin-1", low_memory=False
    )
    return points, fields


def _query_results(points, fields, field_id):
    """Rows as ``_raw_delivery_data_sql`` returns them for one field."""
    field_points = points[points["FLD_ID"] == field_id].sort_values("Point")
    meterset = fields.loc[fields["FLD_ID"] == field_id, "Meterset"].iloc[0]
    columns = ["Index", "A_Leaf_Set", "B_Leaf_Set", "Gantry_Ang", "Coll_Ang"]
    columns += ["Coll_Y1", "Coll_Y2", "MLC_Leaves"]
    rows = [
        (index, _decode_b64(bank_a), _decode_b64(bank_b), *rest)
        for index, bank_a, bank_b, *rest in field_points[columns].itertuples(
            index=False, name=None
        )
    ]
    return [(meterset,)], rows


def _from_mosaiq(monkeypatch, results):
    monkeypatch.setattr(delivery, "_raw_delivery_data_sql", lambda *_: results)
    return delivery.DeliveryMosaiq.from_mosaiq(None, None)


@pytest.mark.parametrize(
    "positions_cm",
    [
        # A small positive last leaf has a zero high byte; a closed one is
        # two zero bytes. Both sit against the record's zero padding.
        [5.0, -3.0, 1.2, 1.0],
        [5.0, -3.0, 1.2, 0.0],
        [0.0, 0.0, 0.0, 0.0],
        [-0.01, 2.55, 2.56, -20.0],
    ],
)
def test_leaf_positions_keep_trailing_zero_bytes(positions_cm):
    records = [_record(positions_cm), _record(positions_cm[::-1])]

    result = delivery.decode_msq_mlc(records, len(positions_cm))

    np.testing.assert_array_equal(result, [positions_cm, positions_cm[::-1]])


def test_unused_record_slots_are_ignored():
    record = _record([1.0, 2.0])[:4] + struct.pack("<h", 999).ljust(196, b"\x00")

    np.testing.assert_array_equal(delivery.decode_msq_mlc([record], 2), [[1.0, 2.0]])


def test_short_leaf_set_is_rejected():
    with pytest.raises(ValueError, match="fewer than the 6 bytes"):
        delivery.decode_msq_mlc([b"\x01\x00\x02\x00"], 3)


def test_a_field_without_leaves_decodes_to_no_positions():
    result = delivery.decode_msq_mlc([bytes(RECORD_BYTES), None], 0)

    assert result.shape == (2, 0)


def _expected_mlc_mm(a_records, b_records, leaf_count):
    # The established Mosaiq to bipolar convention, which the database test
    # compares with the DICOM plan: bank B then negated bank A, leaves reversed.
    bank_a = np.array([_positions_cm(r, leaf_count) for r in a_records])
    bank_b = np.array([_positions_cm(r, leaf_count) for r in b_records])
    return np.stack([10 * bank_b[:, ::-1], -10 * bank_a[:, ::-1]], axis=-1)


def test_every_mock_field_decodes_with_its_stated_leaf_count(mock_tables, monkeypatch):
    points, fields = mock_tables
    field_ids = points["FLD_ID"].unique()
    assert len(field_ids) > 500

    for field_id in field_ids:
        results = _query_results(points, fields, field_id)
        rows = results[1]
        result = _from_mosaiq(monkeypatch, results)

        leaf_count = int(rows[0][-1])
        control_points = max(len(rows), 2)
        # Delivery stores nested tuples, so a field without leaves keeps
        # only its control-point dimension.
        expected_shape = (
            (control_points, leaf_count, 2)
            if leaf_count
            else (
                control_points,
                0,
            )
        )
        assert np.shape(result.mlc) == expected_shape, field_id
        assert np.shape(result.jaw) == (control_points, 2), field_id

        expected = _expected_mlc_mm(
            [row[1] for row in rows], [row[2] for row in rows], leaf_count
        )
        if len(rows) == 1:
            expected = np.repeat(expected, 2, axis=0)
        if leaf_count:
            np.testing.assert_array_equal(result.mlc, expected, err_msg=str(field_id))


def test_static_field_delivers_its_meterset_between_two_identical_points(
    mock_tables, monkeypatch
):
    points, fields = mock_tables
    point_counts = points.groupby("FLD_ID")["Point"].count()
    leaf_counts = points.groupby("FLD_ID")["MLC_Leaves"].first()
    field_id = point_counts[(point_counts == 1) & (leaf_counts > 0)].index[0]
    results = _query_results(points, fields, field_id)
    (meterset,) = results[0][0]

    result = _from_mosaiq(monkeypatch, results)

    np.testing.assert_allclose(result.monitor_units, [0, meterset])
    for values in (result.mlc, result.jaw, result.gantry, result.collimator):
        np.testing.assert_array_equal(values[0], values[1])


def test_dynamic_field_monitor_units_follow_the_cumulative_index(
    mock_tables, monkeypatch
):
    points, fields = mock_tables
    point_counts = points.groupby("FLD_ID")["Point"].count()
    field_id = point_counts[point_counts > 5].index[0]
    results = _query_results(points, fields, field_id)
    (meterset,), rows = results[0][0], results[1]
    index_percent = np.array([row[0] for row in rows])
    assert index_percent[0] == 0 and index_percent[-1] == 100

    result = _from_mosaiq(monkeypatch, results)

    np.testing.assert_allclose(result.monitor_units, index_percent / 100 * meterset)


def test_inconsistent_leaf_counts_are_rejected(monkeypatch):
    rows = [
        (0.0, _record([1.0]), _record([1.0]), 0.0, 0.0, 5.0, 5.0, 1),
        (100.0, _record([1.0, 2.0]), _record([1.0, 2.0]), 0.0, 0.0, 5.0, 5.0, 2),
    ]

    with pytest.raises(ValueError, match="MLC_Leaves"):
        _from_mosaiq(monkeypatch, ([(10.0,)], rows))


@pytest.mark.parametrize("index", [[0.0, 0.0], [0.0, 60.0, 40.0]])
def test_invalid_cumulative_index_is_rejected(index, monkeypatch):
    rows = [
        (value, _record([1.0]), _record([1.0]), 0.0, 0.0, 5.0, 5.0, 1)
        for value in index
    ]

    with pytest.raises(ValueError, match="Index"):
        _from_mosaiq(monkeypatch, ([(10.0,)], rows))
