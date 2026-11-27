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

"""Limit input XML expansion before processing iView frame metadata."""

from pymedphys._imports import pytest

pytest.importorskip("streamlit")
pytest.importorskip("xmltodict")

from pymedphys._experimental.streamlit.utilities.iview import _frames  # noqa: E402


def test_small_frame_xml_remains_readable(tmp_path):
    path = tmp_path / "frames.xml"
    path.write_bytes(b"<ProjectionSet><Frames /></ProjectionSet>")

    assert _frames._load_xml(path)["ProjectionSet"]["Frames"] is None


def test_oversized_frame_xml_is_rejected_without_patient_filename(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(_frames, "MAX_IVIEW_FRAME_XML_BYTES", 128)
    marker = "SYNTHETIC-PATIENT-123"
    path = tmp_path / f"{marker}.xml"
    path.write_bytes(b"<a>" + b"x" * 1024 + b"</a>")

    with pytest.raises(ValueError, match="permitted size") as exc:
        _frames._load_xml(path)

    assert marker not in str(exc.value)


def test_exact_limit_is_allowed(tmp_path, monkeypatch):
    data = b"<a>okay</a>"
    monkeypatch.setattr(_frames, "MAX_IVIEW_FRAME_XML_BYTES", len(data))
    path = tmp_path / "exact.xml"
    path.write_bytes(data)

    assert _frames._load_xml(path) == {"a": "okay"}
