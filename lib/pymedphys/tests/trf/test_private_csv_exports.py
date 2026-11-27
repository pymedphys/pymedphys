# Copyright (C) 2026 Jeffrey D. Cooney
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

"""Clinical TRF CSV outputs must not be left with broad file permissions."""

import os
import stat
from importlib import import_module

from pymedphys._imports import pytest

trf2csv = import_module("pymedphys._trf.decode.trf2csv")


class Frame:
    def to_csv(self, destination):
        destination.write("synthetic,record\n")


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_trf_csv_creation_and_overwrite_remain_owner_only(tmp_path):
    destination = tmp_path / "clinical_table.csv"

    trf2csv._write_private_csv(Frame(), destination)
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600

    destination.chmod(0o644)
    trf2csv._write_private_csv(Frame(), destination)
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_csv_export_replaces_destination_link_not_its_target(tmp_path):
    outside = tmp_path / "outside.csv"
    outside.write_text("original", encoding="utf-8")
    destination = tmp_path / "clinical.csv"
    destination.symlink_to(outside)

    trf2csv._write_private_csv(Frame(), destination)

    assert outside.read_text(encoding="utf-8") == "original"
    assert not destination.is_symlink()
    assert destination.read_text(encoding="utf-8") == "synthetic,record\n"


def test_failed_write_keeps_previous_csv_and_removes_temporary_file(tmp_path):
    destination = tmp_path / "clinical.csv"
    destination.write_text("old,record\n", encoding="utf-8")

    class BrokenFrame:
        def to_csv(self, temporary):
            temporary.write("partial,sensitive")
            raise RuntimeError("synthetic failure")

    with pytest.raises(RuntimeError, match="synthetic failure"):
        trf2csv._write_private_csv(BrokenFrame(), destination)

    assert destination.read_text(encoding="utf-8") == "old,record\n"
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_temporary_path_replacement_is_detected_before_publication(tmp_path):
    destination = tmp_path / "clinical.csv"
    outside = tmp_path / "outside.csv"
    outside.write_text("untouched", encoding="utf-8")

    class ReplacingFrame:
        def to_csv(self, stream):
            stream.write("synthetic,private\n")
            temporary = next(tmp_path.glob(".pmp-csv-*.tmp"))
            temporary.unlink()
            temporary.symlink_to(outside)

    with pytest.raises(OSError, match="changed during export"):
        trf2csv._write_private_csv(ReplacingFrame(), destination)

    assert outside.read_text(encoding="utf-8") == "untouched"
    assert not destination.exists()
    assert list(tmp_path.iterdir()) == [outside]
