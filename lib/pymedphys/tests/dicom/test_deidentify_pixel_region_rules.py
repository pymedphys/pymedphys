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
"""The reviewed region rules store of the Clean Pixel Data Option.

Every manufacturer and model name here is invented.
"""

import hashlib
import hmac
import json
import os
import pathlib

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import keys
from pymedphys._dicom.deidentify import pixel_region_rules as rules_module
from pymedphys._dicom.deidentify.pixel_region_rules import (
    PixelRegionRules,
    PixelRegionRulesError,
    RuleKey,
    key_of,
)
from pymedphys._dicom.deidentify.text_detection import TextBox

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")

US_IMAGE = "1.2.840.10008.5.1.4.1.1.6.1"
SECONDARY_CAPTURE = "1.2.840.10008.5.1.4.1.1.7"
KEY = RuleKey(US_IMAGE, "Acme Sonics", "Echo 5", 480, 640)
BAND = TextBox(0, 0, 40, 640)
CORNER = TextBox(440, 520, 480, 640)


@pytest.fixture(name="home", autouse=True)
def fixture_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: home))
    return home


def _dataset(**values):
    dataset = pydicom.Dataset()
    dataset.SOPClassUID = US_IMAGE
    dataset.Manufacturer = "Acme Sonics"
    dataset.ManufacturerModelName = "Echo 5"
    dataset.Rows = 480
    dataset.Columns = 640
    for keyword, value in values.items():
        if value is None:
            delattr(dataset, keyword)
        else:
            setattr(dataset, keyword, value)
    return dataset


def _store(*entries):
    store = PixelRegionRules.empty()
    for key, boxes in entries:
        store.record(key, boxes)
    return store


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_recorded_rules_are_reused_on_later_runs(tmp_path):
    path = tmp_path / "pixel-region-rules.json"
    store = PixelRegionRules.open(path)
    store.record(KEY, [CORNER, BAND, BAND])
    store.save()

    reopened = PixelRegionRules.open(path)

    assert len(reopened) == 1
    assert reopened.get(KEY) == (BAND, CORNER)
    assert reopened.boxes_for(_dataset()) == (BAND, CORNER)


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_a_key_is_read_from_the_five_attributes_without_padding():
    dataset = _dataset(Manufacturer="Acme Sonics ", ManufacturerModelName="Echo 5\x00")

    assert key_of(dataset) == KEY


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
@pytest.mark.parametrize(
    "values",
    [
        {"SOPClassUID": SECONDARY_CAPTURE},
        {"Manufacturer": "ACME SONICS"},
        {"ManufacturerModelName": "Echo 5 Pro"},
        {"Rows": 481},
        {"Columns": 512},
    ],
)
def test_a_rule_matches_only_its_exact_key(values):
    store = _store((KEY, [BAND]))

    assert store.boxes_for(_dataset()) == (BAND,)
    assert store.boxes_for(_dataset(**values)) == ()


@pytest.mark.parametrize(
    "values",
    [
        {"SOPClassUID": None},
        {"Manufacturer": None},
        {"ManufacturerModelName": None},
        {"Rows": None},
        {"Columns": None},
        {"Manufacturer": ""},
        {"ManufacturerModelName": "  "},
        {"Manufacturer": ["Acme Sonics", "Other"]},
        {"Rows": 0},
    ],
)
def test_an_instance_without_a_key_of_its_form_matches_no_rule(values):
    store = _store((KEY, [BAND]))

    assert key_of(_dataset(**values)) is None
    assert store.boxes_for(_dataset(**values)) == ()


@pytest.mark.parametrize(
    "fields",
    [
        ("1.2.03", "Acme Sonics", "Echo 5", 480, 640),
        ("1." + "2" * 64, "Acme Sonics", "Echo 5", 480, 640),
        (US_IMAGE, "", "Echo 5", 480, 640),
        (US_IMAGE, " Acme Sonics", "Echo 5", 480, 640),
        (US_IMAGE, "Acme\\Sonics", "Echo 5", 480, 640),
        (US_IMAGE, "Acme Sonics", "Echo\n5", 480, 640),
        (US_IMAGE, "Acme Sonics", "E" * 65, 480, 640),
        (US_IMAGE, "Acme Sonics", "Echo\ud8005", 480, 640),
        (US_IMAGE, "Acme Sonics", "Echo 5", 0, 640),
        (US_IMAGE, "Acme Sonics", "Echo 5", 480, 65536),
        (US_IMAGE, "Acme Sonics", "Echo 5", True, 640),
        (US_IMAGE, b"Acme Sonics", "Echo 5", 480, 640),
    ],
)
def test_a_malformed_key_is_refused_without_quoting_it(fields):
    with pytest.raises(PixelRegionRulesError) as error:
        RuleKey(*fields)

    assert "Acme" not in str(error.value) and "Echo" not in str(error.value)


def test_a_key_and_the_store_never_show_equipment():
    store = _store((KEY, [BAND]))

    assert "Acme" not in repr(KEY) and "Echo" not in repr(KEY)
    assert repr(store) == "PixelRegionRules(rules=1)"


@pytest.mark.parametrize(
    "boxes",
    [
        [],
        [TextBox(0, 0, 481, 640)],
        [TextBox(0, 0, 480, 641)],
        [(0, 0, 40, 640)],
        "boxes",
    ],
)
def test_a_rule_needs_regions_within_its_rows_and_columns(boxes):
    with pytest.raises(PixelRegionRulesError):
        PixelRegionRules.empty().record(KEY, boxes)


def test_a_rule_reaching_its_last_row_and_column_is_kept():
    whole = TextBox(0, 0, 480, 640)

    assert _store((KEY, [whole])).get(KEY) == (whole,)


def test_other_regions_replace_a_rule_only_when_asked():
    store = _store((KEY, [BAND]))
    store.record(KEY, [BAND])

    with pytest.raises(PixelRegionRulesError, match="other regions"):
        store.record(KEY, [CORNER])
    store.record(KEY, [CORNER], replace=True)

    assert store.get(KEY) == (CORNER,)
    store.remove(KEY)
    assert len(store) == 0 and store.get(KEY) == ()


def test_a_rule_needs_a_rule_key():
    with pytest.raises(PixelRegionRulesError, match="RuleKey"):
        PixelRegionRules.empty().record(  # type: ignore[arg-type]
            (US_IMAGE, "Acme Sonics", "Echo 5", 480, 640), [BAND]
        )


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
@pytest.mark.parametrize("where", ["config", "protected"])
def test_the_store_is_refused_inside_a_protected_directory(tmp_path, where):
    if where == "config":
        directory = pathlib.Path.home() / ".pymedphys"
    else:
        directory = tmp_path / "output"
    directory.mkdir()

    with pytest.raises(PixelRegionRulesError, match="refusing"):
        PixelRegionRules.open(
            directory / "rules.json", protected_dirs=[tmp_path / "output"]
        )


def _write(path, document):
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


RULE = {
    "sop_class_uid": US_IMAGE,
    "manufacturer": "Acme Sonics",
    "model_name": "Echo 5",
    "rows": 480,
    "columns": 640,
    "boxes": [[0, 0, 40, 640]],
}
GOOD = {"format": rules_module.FORMAT, "rules": [RULE]}


@pytest.mark.parametrize(
    "document",
    [
        [],
        {**GOOD, "format": "pymedphys-deid-pixel-region-rules/0"},
        {**GOOD, "extra": 1},
        {"format": rules_module.FORMAT},
        {**GOOD, "rules": {}},
        {**GOOD, "rules": [{**RULE, "extra": 1}]},
        {**GOOD, "rules": [{k: v for k, v in RULE.items() if k != "boxes"}]},
        {**GOOD, "rules": [{**RULE, "manufacturer": " Acme Sonics"}]},
        {**GOOD, "rules": [{**RULE, "model_name": 5}]},
        {**GOOD, "rules": [{**RULE, "rows": "480"}]},
        {**GOOD, "rules": [{**RULE, "boxes": []}]},
        {**GOOD, "rules": [{**RULE, "boxes": [[0, 0, 40]]}]},
        {**GOOD, "rules": [{**RULE, "boxes": [[0, 0, 0, 640]]}]},
        {**GOOD, "rules": [{**RULE, "boxes": [[0, 0, 40.0, 640]]}]},
        {**GOOD, "rules": [{**RULE, "boxes": [[0, 0, 40, 641]]}]},
        {**GOOD, "rules": [{**RULE, "boxes": [[0, 0, 40, 640], [0, 0, 40, 640]]}]},
        {**GOOD, "rules": [RULE, {**RULE, "boxes": [[0, 0, 10, 10]]}]},
        {**GOOD, "rules": ["Acme Sonics"]},
    ],
)
def test_a_malformed_store_is_refused_without_quoting_it(tmp_path, document):
    path = _write(tmp_path / "rules.json", document)

    with pytest.raises(PixelRegionRulesError) as error:
        PixelRegionRules.open(path)

    assert "Acme" not in str(error.value) and "Echo" not in str(error.value)


def test_a_store_with_a_repeated_member_is_refused(tmp_path):
    path = tmp_path / "rules.json"
    path.write_text(
        '{"format": "%s", "rules": [], "rules": []}' % rules_module.FORMAT,
        encoding="utf-8",
    )

    with pytest.raises(PixelRegionRulesError, match="repeated"):
        PixelRegionRules.open(path)


def test_a_read_error_does_not_carry_the_files_text(tmp_path):
    path = tmp_path / "rules.json"
    path.write_bytes(b'{"format": "x", "rules": [{"manufacturer": "Acme" \xff')

    with pytest.raises(PixelRegionRulesError, match="could not be read") as error:
        PixelRegionRules.open(path)

    assert error.value.__cause__ is None and error.value.__suppress_context__


def test_an_empty_store_is_never_saved():
    with pytest.raises(PixelRegionRulesError, match="no file"):
        PixelRegionRules.empty().save()


def test_the_saved_store_is_sorted_and_round_trips(tmp_path):
    path = _write(tmp_path / "rules.json", GOOD)
    store = PixelRegionRules.open(path)
    other = RuleKey(SECONDARY_CAPTURE, "Acme Imaging", "Station", 768, 1024)
    store.record(other, [TextBox(700, 0, 768, 300)])
    store.save()

    document = json.loads(path.read_text(encoding="utf-8"))
    assert [rule["sop_class_uid"] for rule in document["rules"]] == [
        US_IMAGE,
        SECONDARY_CAPTURE,
    ]
    assert PixelRegionRules.open(path).get(other) == (TextBox(700, 0, 768, 300),)


@posix_only
def test_the_saved_store_is_readable_only_by_its_owner(tmp_path):
    path = tmp_path / "rules.json"
    store = PixelRegionRules.open(path)
    store.record(KEY, [BAND])
    store.save()

    assert path.stat().st_mode & 0o777 == 0o600
    assert sorted(p.name for p in tmp_path.iterdir()) == ["home", "rules.json"]


TEST_KEY = keys.DeidKey(bytes(range(32)))
CANONICAL_STORE = (
    b'{"format":"pymedphys-deid-pixel-region-rules/1","rules":[{'
    b'"boxes":[[0,0,40,640],[440,520,480,640]],"columns":640,'
    b'"manufacturer":"Acme Sonics","model_name":"Echo 5","rows":480,'
    b'"sop_class_uid":"1.2.840.10008.5.1.4.1.1.6.1"}]}'
)


def _framed(value: bytes) -> bytes:
    return len(value).to_bytes(4, "big") + value


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_the_keyed_digest_is_the_hmac_of_the_stores_canonical_form():
    store = _store((KEY, [CORNER, BAND]))
    message = b"".join(
        _framed(part)
        for part in (b"pymedphys-deid/1", b"pixel-region-rules", CANONICAL_STORE)
    )

    assert store.canonical_bytes() == CANONICAL_STORE
    assert store.keyed_digest(TEST_KEY) == (
        hmac.new(bytes(range(32)), message, hashlib.sha256).hexdigest()
    )


def test_the_canonical_form_ignores_the_order_rules_were_recorded_in():
    other = RuleKey(SECONDARY_CAPTURE, "Acme Imaging", "Station", 768, 1024)
    first = _store((KEY, [BAND]), (other, [TextBox(0, 0, 1, 1)]))
    second = _store((other, [TextBox(0, 0, 1, 1)]), (KEY, [BAND]))

    assert first.canonical_bytes() == second.canonical_bytes()
    assert first.keyed_digest(TEST_KEY) != _store((KEY, [CORNER])).keyed_digest(
        TEST_KEY
    )


def test_the_keyed_digest_needs_a_key():
    with pytest.raises(TypeError):
        PixelRegionRules.empty().keyed_digest(bytes(32))  # type: ignore[arg-type]


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_a_snapshot_keeps_the_rules_as_they_stood_and_is_never_saved():
    store = _store((KEY, [BAND]))
    snapshot = store.snapshot()
    store.record(KEY, [CORNER], replace=True)

    assert snapshot.get(KEY) == (BAND,)
    with pytest.raises(PixelRegionRulesError):
        snapshot.save()
