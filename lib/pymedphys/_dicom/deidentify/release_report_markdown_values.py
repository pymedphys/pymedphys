# Copyright (C) 2026 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unchanged field checks and value rendering for release-report Markdown."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from .release_report import FORMAT

Block = list[str]


class ReleaseReportMarkdownError(ValueError):
    """The text is not a release report of this module's format.

    The message names the field, never its value.
    """


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> Block:
    def line(cells: Sequence[str]) -> str:
        return "|" + "".join(f" {cell} |" if cell else " |" for cell in cells)

    return [line(header), "|" + " --- |" * len(header), *(line(row) for row in rows)]


def _digest_table(field: str, digests: object) -> Block:
    if not isinstance(digests, dict):
        raise _refuse(field)
    return _table(
        ("File", "SHA-256"),
        [
            (_code(field, name), _code(field, digest))
            for name, digest in digests.items()
        ],
    )


def _fields(
    field: str, section: object, names: Mapping[str, object] | Sequence[str]
) -> dict:
    """Return the section, if it has exactly these fields, in this order."""
    if not isinstance(section, dict) or list(section) != list(names):
        raise ReleaseReportMarkdownError(
            f"The fields of the release report's {field} are not those of {FORMAT}."
        )
    return section


def _list(field: str, value: object) -> list:
    if not isinstance(value, list):
        raise _refuse(field)
    return value


def _code(field: str, value: object) -> str:
    # An empty code span, or one with space at an end, would not show the
    # value as it is.
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(c in value for c in "`|\n\r")
    ):
        raise _refuse(field)
    return f"`{value}`"


def _count(field: str, value: object) -> str:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise _refuse(field)
    return f"`{value}`"


def _tally(field: str, value: object) -> str:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise _refuse(field)
    return f"`{value}`"


def _boolean(field: str, value: object) -> str:
    if not isinstance(value, bool):
        raise _refuse(field)
    return f"`{json.dumps(value)}`"


def _optional(field: str, value: object, absent: str = "none") -> str:
    return absent if value is None else _code(field, value)


def _members(pairs: list[tuple[str, object]]) -> dict:
    """Return a JSON object's members, refusing a member named twice."""
    members = dict(pairs)
    if len(members) != len(pairs):
        raise ReleaseReportMarkdownError(
            "The release report names a member twice in one object."
        )
    return members


def _refuse(field: str) -> ReleaseReportMarkdownError:
    return ReleaseReportMarkdownError(
        f"The release report's {field} is not in the form of {FORMAT}."
    )
