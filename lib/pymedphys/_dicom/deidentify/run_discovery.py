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

"""Discover a run's inputs: every entry below a source directory, by run position.

This is the first step of a run, which
:mod:`~pymedphys._dicom.deidentify.run` describes, and from which
:func:`discover` and :class:`Discovery` are importable too.
"""

from __future__ import annotations

import dataclasses
import os
import stat
from collections.abc import Iterator
from pathlib import Path

from .reasons import RunReason

_DICOMDIR_NAME = "DICOMDIR"
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400


class RunError(Exception):
    """A run that cannot start, for a reason in its directories.

    Its message names the release directory or staging area, which the
    caller chose, and never a source path.
    """


@dataclasses.dataclass(frozen=True)
class _Entry:
    """An entry as discovery found it."""

    path: Path
    refusal: RunReason | None
    device: int
    inode: int


@dataclasses.dataclass(frozen=True, repr=False)
class Discovery:
    """The entries below a source directory, by run position.

    Its ``repr`` shows only how many there are.

    Attributes
    ----------
    source : Path
        The source directory, resolved.
    paths : tuple of Path
        Each entry's path, at its run position. Confidential: they are for
        the QC material alone.
    refusals : tuple of RunReason or None
        For each position, why discovery refused the entry, or ``None`` for
        a regular file.
    """

    source: Path
    entries: tuple[_Entry, ...]

    @property
    def paths(self) -> tuple[Path, ...]:
        return tuple(entry.path for entry in self.entries)

    @property
    def refusals(self) -> tuple[RunReason | None, ...]:
        return tuple(entry.refusal for entry in self.entries)

    def __repr__(self) -> str:
        refused = sum(entry.refusal is not None for entry in self.entries)
        return f"Discovery(entries={len(self.entries)}, refused={refused})"


def discover(source: str | os.PathLike[str]) -> Discovery:
    """List every entry below a source directory, by run position.

    Entries are ordered by their paths relative to ``source``, compared
    component by component as the bytes that the file system holds, so the
    order is the same on every run. A directory is descended and is not an
    entry itself. A symbolic link, to a directory or a file, or another
    link, such as a Windows junction, is an entry that is refused and not
    followed; any other entry that is not a regular file, such as a named
    pipe, is refused without being opened; and a regular file named
    ``DICOMDIR``, in any case, is refused, as is one that the first pass
    finds to be a DICOMDIR.

    Parameters
    ----------
    source : str or os.PathLike
        The source directory. A symbolic link to it is followed.

    Returns
    -------
    Discovery

    Raises
    ------
    RunError
        If ``source`` is not a directory, or a directory below it cannot be
        listed. The message names no path.
    """
    root = Path(source)
    try:
        root = root.resolve()
        is_directory = root.is_dir()
    except OSError:
        is_directory = False
    if not is_directory:
        raise RunError("the source is not a directory that can be read")
    try:
        found = list(_walk(root))
    except OSError:
        raise RunError("a directory below the source cannot be listed") from None
    found.sort(
        key=lambda entry: tuple(
            os.fsencode(part) for part in entry.path.relative_to(root).parts
        )
    )
    return Discovery(root, tuple(found))


def _walk(root: Path) -> Iterator[_Entry]:
    """Yield every entry below ``root``, without recursion or following links."""
    pending = [root]
    while pending:
        with os.scandir(pending.pop()) as listing:
            entries = list(listing)
        for entry in entries:
            path = Path(entry.path)
            details = entry.stat(follow_symlinks=False)
            refusal = None
            if _is_link(entry, details):
                refusal = RunReason.SYMBOLIC_LINK
            elif stat.S_ISDIR(details.st_mode):
                pending.append(path)
                continue
            elif not stat.S_ISREG(details.st_mode):
                refusal = RunReason.NOT_A_REGULAR_FILE
            elif entry.name.upper() == _DICOMDIR_NAME:
                refusal = RunReason.DICOMDIR
            else:
                # On Windows, a directory entry's own stat has no device or
                # inode, which reading the file compares.
                details = os.lstat(path)
            yield _Entry(path, refusal, details.st_dev, details.st_ino)


def _is_link(entry: os.DirEntry, details: os.stat_result) -> bool:
    if entry.is_symlink():
        return True
    is_junction = getattr(entry, "is_junction", None)  # Python 3.12 and later
    if is_junction is not None and is_junction():
        return True
    attributes = getattr(details, "st_file_attributes", 0)  # Windows
    return bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT)
