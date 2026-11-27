# Copyright (C) 2026 PyMedPhys contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""TRF exports must not expand metacharacters in their input directory."""

from importlib import import_module
from pathlib import Path

trf2csv = import_module("pymedphys._trf.decode.trf2csv")


def test_trf_directory_with_brackets_does_not_read_a_sibling(tmp_path, monkeypatch):
    requested = tmp_path / "clinic[1]"
    sibling = tmp_path / "clinic1"
    requested.mkdir()
    sibling.mkdir()
    target = requested / "one.trf"
    target.write_bytes(b"synthetic TRF test data")
    (sibling / "two.trf").write_bytes(b"unrelated synthetic data")
    export = tmp_path / "exports"
    export.mkdir()

    read = []

    class Frame:
        def to_csv(self, path):
            Path(path).write_text("synthetic data", encoding="utf-8")

    def fake_parser(path):
        read.append(path)
        return Frame(), Frame()

    monkeypatch.setattr(trf2csv, "trf2pandas", fake_parser)

    trf2csv.trf2csv_by_directory(requested, export)

    assert read == [str(target)]
    assert sorted(path.name for path in export.iterdir()) == [
        "one.trf.header.csv",
        "one.trf.table.csv",
    ]
