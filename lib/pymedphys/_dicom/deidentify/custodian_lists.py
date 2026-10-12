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

"""Files of reviewers' decisions that the custodian keeps, as JSON.

The reviewed-names list (:mod:`.reviewed_roi_names`) and the reviewed
descriptors list (:mod:`.reviewed_descriptors`) hold source values verbatim,
so each is kept with the key and subject profiles, outside output and QC
directories, readable only by its owner, and no error message quotes its text
or path. These helpers locate, read, and write such a file.
"""

from __future__ import annotations

import json
import os
import pathlib
import tempfile
from collections.abc import Iterable

from .keys import custodian_location_problem


def custodian_path(
    path: str | os.PathLike,
    protected_dirs: Iterable[str | os.PathLike],
    *,
    what: str,
    error: type[ValueError],
) -> pathlib.Path:
    """Return ``path`` resolved, if a custodian file may be kept there.

    Raises
    ------
    ValueError
        ``error``, if ``path`` is inside the PyMedPhys configuration
        directory or one of ``protected_dirs``. The message names ``what``
        and not the path.
    """
    given = pathlib.Path(path).absolute()
    resolved = given.parent.resolve() / given.name
    problem = custodian_location_problem(resolved, protected_dirs)
    if problem:
        raise error(f"refusing to keep a {what} {problem}")
    return resolved


def read_document(path: pathlib.Path, *, what: str, error: type[ValueError]) -> object:
    """Return the JSON document at ``path``, refusing a repeated member.

    Raises
    ------
    ValueError
        ``error``, if the file cannot be read as UTF-8 JSON, or an object in
        it repeats a member. The message names ``what``, never the file's
        text, and the error is not chained to one that could quote it.
    """

    def unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        document: dict[str, object] = {}
        for number, (key, value) in enumerate(pairs, start=1):
            if key in document:
                raise error(f"item {number} of an object in the list is repeated")
            document[key] = value
        return document

    try:
        return json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs
        )
    except error:
        raise
    except (OSError, ValueError, RecursionError):
        # Not chained, since a decoding or parsing error holds the file's text.
        raise error(f"the {what} could not be read") from None


def save_document(path: pathlib.Path, document: object) -> None:
    """Write ``document`` to ``path`` as JSON, replacing it atomically.

    The file is created readable and writable only by its owner where the
    platform enforces file modes. If writing fails, the previous file is left
    as it was, and no partial file remains.
    """
    text = json.dumps(document, indent=1, ensure_ascii=False)
    # mkstemp creates the file readable and writable only by its owner.
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".part"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
            file.write(text + "\n")
        os.replace(temporary, path)
    except BaseException:
        pathlib.Path(temporary).unlink(missing_ok=True)
        raise
