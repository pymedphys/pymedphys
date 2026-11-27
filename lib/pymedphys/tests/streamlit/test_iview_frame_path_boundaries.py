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

"""Reject iView frame XML/JPG paths derived from unsafe clinical identifiers."""

from pathlib import Path

from pymedphys._imports import pytest

pytest.importorskip("streamlit")
pd = pytest.importorskip("pandas")

from pymedphys._experimental.streamlit.utilities.iview import _frames  # noqa: E402


@pytest.mark.parametrize(
    "column, identifier",
    [
        ("patient_id", "other/../../private"),
        ("patient_id", r"other\..\private"),
        ("DICOM_UID", "1.2/../../../escape"),
        ("DICOM_UID", "1.2\x00private"),
        ("sequence", "001/../../outside"),
    ],
)
def test_frame_paths_reject_untrusted_metadata(column, identifier):
    row = {"patient_id": "123", "DICOM_UID": "1.2.3", "sequence": "1"}
    row[column] = identifier
    table = pd.DataFrame([row])
    with pytest.raises(ValueError, match="path component"):
        _frames._calc_xml_based_jpg_filepaths(table)
    if column != "sequence":
        with pytest.raises(ValueError, match="path component"):
            _frames._calc_xml_filepaths(table)


def test_normal_frame_path_layout_is_preserved():
    table = pd.DataFrame(
        [{"patient_id": "P123", "DICOM_UID": "1.2.3", "sequence": "23"}]
    )
    assert _frames._calc_xml_filepaths(table).iloc[0] == (
        "patient_P123/MV_IMAGES/img_1.2.3/_Frame.xml"
    )
    assert _frames._calc_xml_based_jpg_filepaths(table).iloc[0] == (
        "patient_P123/MV_IMAGES/img_1.2.3/00023.1.2.3.jpg"
    )


def test_iview_frame_loader_rejects_symlink_outside_database(tmp_path):
    root = tmp_path / "iview"
    root.mkdir()
    outside = tmp_path / "private.xml"
    outside.write_text("<private />", encoding="utf-8")
    link = root / "frame.xml"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks unavailable")
    with pytest.raises(ValueError, match="database directory"):
        _frames._safe_iview_xml_path(root, "frame.xml")
    assert _frames._safe_iview_xml_path(root, "safe.xml") == root / "safe.xml"
