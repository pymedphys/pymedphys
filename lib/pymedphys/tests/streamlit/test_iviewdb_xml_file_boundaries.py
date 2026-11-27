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

"""The experimental iView XML reader must stay inside its configured root."""

from pymedphys._imports import pytest

pytest.importorskip("streamlit")
pytest.importorskip("xmltodict")

from pymedphys._experimental.streamlit.apps import iviewdb  # noqa: E402


def test_xml_selection_rejects_directory_traversal(tmp_path):
    root = tmp_path / "database"
    root.mkdir()
    (tmp_path / "other.xml").write_text("<private />", encoding="utf-8")
    with pytest.raises(ValueError, match="inside the database folder"):
        iviewdb.safe_iview_xml_path(root, "../other.xml")


def test_xml_selection_rejects_symlink_escape(tmp_path):
    root = tmp_path / "database"
    root.mkdir()
    (tmp_path / "other.xml").write_text("<private />", encoding="utf-8")
    leak = root / "leak.xml"
    try:
        leak.symlink_to(tmp_path / "other.xml")
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks unavailable on this platform")
    with pytest.raises(ValueError, match="inside the database folder"):
        iviewdb.safe_iview_xml_path(root, "leak.xml")
    assert "leak.xml" not in iviewdb.get_files_for_extension(root, ".xml")


def test_xml_selection_accepts_regular_file_inside_root(tmp_path):
    root = tmp_path / "database"
    root.mkdir()
    expected = root / "export.xml"
    expected.write_text("<study />", encoding="utf-8")
    assert iviewdb.safe_iview_xml_path(root, "export.xml") == expected
