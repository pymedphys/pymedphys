"""JSON wrappers over per-type ``to_dict()`` / ``from_dict()`` methods.

Each serialisable DVH type defines its own ``to_dict()`` and
``from_dict()`` round-trip methods. This module provides thin
convenience wrappers for converting to and from JSON strings.

TOML input (where supported) is handled by type-specific loaders
such as ``MetricRequestSet.from_toml()``, not by this module.
"""

from __future__ import annotations

import json
from typing import Any, TypeVar

T = TypeVar("T")


def to_json(obj: Any) -> str:
    """Serialise a DVH type to a JSON string.

    Parameters
    ----------
    obj
        Any DVH type with a ``to_dict()`` method.

    Returns
    -------
    str
        JSON string with 2-space indentation.
    """
    return json.dumps(obj.to_dict(), indent=2)


def from_json(json_str: str, cls: type[T]) -> T:
    """Deserialise a DVH type from a JSON string.

    Parameters
    ----------
    json_str : str
        JSON string to parse.
    cls : type
        The DVH type class (must have a ``from_dict()`` classmethod).

    Returns
    -------
    T
        Deserialised instance.
    """
    return cls.from_dict(json.loads(json_str))  # type: ignore[attr-defined,no-any-return]
