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

"""Large untrusted iView XML exports must be rejected before parsing."""

from pymedphys._imports import pytest

pytest.importorskip("streamlit")
pytest.importorskip("xmltodict")

from pymedphys._experimental.streamlit.apps import iviewdb  # noqa: E402


def test_iview_xml_reader_parses_small_xml(tmp_path, monkeypatch):
    monkeypatch.setattr(iviewdb, "MAX_XML_BYTES", 64)
    xml = tmp_path / "small.xml"
    xml.write_text("<study><id>test</id></study>", encoding="utf-8")
    assert iviewdb.read_iview_xml(xml) == {"study": {"id": "test"}}


def test_iview_xml_reader_rejects_oversized_xml_before_parser(tmp_path, monkeypatch):
    monkeypatch.setattr(iviewdb, "MAX_XML_BYTES", 64)
    xml = tmp_path / "oversized.xml"
    xml.write_bytes(b"<study>" + b"x" * 1000000 + b"</study>")
    with pytest.raises(ValueError, match="permitted size"):
        iviewdb.read_iview_xml(xml)
