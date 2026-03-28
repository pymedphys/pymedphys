"""JSON/TOML serialisation for DVH types.

- **TOML** for human-edited inputs (metric requests, configuration).
- **JSON** for machine-generated results (DVHResultSet output).

Each serialisable type has its own ``to_dict()`` and ``from_dict()``
methods. This module provides thin wrappers for JSON string conversion.
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
    return cls.from_dict(json.loads(json_str))  # type: ignore[attr-defined, no-any-return]
