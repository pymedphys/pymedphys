"""Constrain experimental iView database XML reads to the selected root."""

from pathlib import Path

MAX_XML_BYTES = 64 * 1024 * 1024


def read_database_xml(directory, selected_file):
    """Read only a file within the database root, without unbounded buffering."""
    root = Path(directory).resolve()
    candidate = Path(selected_file)
    if candidate.is_absolute():
        raise ValueError("XML file must be relative to the database directory")
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("XML file is outside the database directory")
    with resolved.open("rb") as handle:
        contents = handle.read(MAX_XML_BYTES + 1)
    if len(contents) > MAX_XML_BYTES:
        raise ValueError("XML file exceeds the size limit")
    return contents
