"""Regression tests for untrusted iView database XML selection."""

import pytest

from pymedphys._experimental.streamlit.apps import _iviewdb_xml


def test_reads_xml_within_selected_directory(tmp_path):
    root = tmp_path / "database"
    root.mkdir()
    (root / "safe.xml").write_bytes(b"<root/>")
    assert _iviewdb_xml.read_database_xml(root, "safe.xml") == b"<root/>"


def test_rejects_parent_traversal_and_external_symlinks(tmp_path):
    root = tmp_path / "database"
    root.mkdir()
    (tmp_path / "private.xml").write_bytes(b"<secret/>")
    (root / "linked.xml").symlink_to(tmp_path / "private.xml")
    for selected in ("../private.xml", "linked.xml", tmp_path / "private.xml"):
        with pytest.raises(ValueError, match="directory"):
            _iviewdb_xml.read_database_xml(root, selected)


def test_xml_input_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(_iviewdb_xml, "MAX_XML_BYTES", 5)
    (tmp_path / "large.xml").write_bytes(b"<root/>")
    with pytest.raises(ValueError, match="size limit"):
        _iviewdb_xml.read_database_xml(tmp_path, "large.xml")
