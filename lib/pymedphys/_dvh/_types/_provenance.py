"""Provenance types — re-exported from _results.py for convenience.

The actual ProvenanceRecord, InputMetadata, and PlatformInfo types
are defined in _results.py to avoid circular imports. This module
exists as a named entry point per the RFC task list.
"""

from pymedphys._dvh._types._results import (
    InputMetadata,
    PlatformInfo,
    ProvenanceRecord,
)

__all__ = ["InputMetadata", "PlatformInfo", "ProvenanceRecord"]
