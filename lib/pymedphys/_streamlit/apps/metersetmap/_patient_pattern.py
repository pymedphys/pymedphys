"""Treat patient identifiers as literal filesystem path components."""

import glob


def escape_patient_id(patient_id: str) -> str:
    """Escape glob metacharacters after rejecting directory traversal."""
    if not isinstance(patient_id, str) or "\x00" in patient_id or any(
        separator in patient_id for separator in ("/", "\\")
    ) or patient_id in (".", ".."):
        raise ValueError("patient ID must be one literal path component")
    return glob.escape(patient_id)
