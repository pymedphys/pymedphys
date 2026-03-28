"""JSON/TOML serialisation — stubs for future implementation."""

from __future__ import annotations

from typing import Any


def to_json(obj: Any) -> str:
    """Serialise a DVH type to JSON."""
    raise NotImplementedError("to_json() is not yet implemented")


def from_json(json_str: str, cls: type) -> Any:
    """Deserialise a DVH type from JSON."""
    raise NotImplementedError("from_json() is not yet implemented")


def to_toml(obj: Any) -> str:
    """Serialise a DVH type to TOML."""
    raise NotImplementedError("to_toml() is not yet implemented")


def from_toml(toml_str: str, cls: type) -> Any:
    """Deserialise a DVH type from TOML."""
    raise NotImplementedError("from_toml() is not yet implemented")
