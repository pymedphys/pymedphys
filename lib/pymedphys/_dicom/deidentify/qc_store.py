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

"""Where confidential QC material may be written, and how releases exclude it.

A QC pack (:mod:`~pymedphys._dicom.deidentify.qc_pack`) may identify people,
so it is written only to a location that the caller designates explicitly,
restricted to authorised reviewers, and never inside a release (D-016).
:func:`write_qc_pack` writes a pack as :data:`PACK_FILE`, beside a handling
notice, :data:`NOTICE_FILE`, and the marker :data:`MARKER_FILE`, by which
:func:`is_qc_material` recognises QC material so that a release step can
refuse it.

Errors name the check that failed, and the operating system's reason, never
a path: a caller may name a QC directory after a patient.
"""

from __future__ import annotations

import os
import stat
import sys
from collections.abc import Iterator
from pathlib import Path

from .qc_pack import FORMAT, QcPack, QcPackError, to_json

PACK_FILE = "qc-pack.json"
NOTICE_FILE = "README.txt"
# Marks a directory as QC material. It is written first, so that a pack
# whose writing stopped part way is still recognised.
MARKER_FILE = ".pymedphys-deid-qc-pack"
_DIRECTORY_MODE = 0o700
_FILE_MODE = 0o600
_POSIX = os.name == "posix"
_CHECKING = "the QC destination could not be checked"
_LOOKING = "a path could not be read to look for QC material"

NOTICE = """\
CONFIDENTIAL: DE-IDENTIFICATION QC PACK

This directory is a QC pack from a PyMedPhys de-identification run. It holds
source file paths, text found in de-identified files, and retained strings,
which may identify people. Treat it as you would the source data.

- Only reviewers whom the data custodian authorises may read it.
- Never copy it, or anything from it, into a release directory or archive,
  and never distribute it with the de-identified output.
- Keep it only as long as the review, the attestation, and the custodian's
  documented retention period require; then delete the whole directory.

The release report refers to this pack only by its opaque reference, which
is in qc-pack.json.
"""


def check_confidential_destination(
    destination: os.PathLike | str,
    *,
    release_directory: os.PathLike | str,
    staging_directory: os.PathLike | str | None = None,
) -> Path:
    """Check that a directory may receive confidential material, and return it.

    The destination must be given explicitly: there is no default. It must
    be neither inside the release directory or the staging directory nor
    contain either. Paths are compared once made absolute with their
    symbolic links resolved, without case on Windows and macOS, and also by
    the device and inode of each existing directory, which finds the same
    directory under another spelling, as on a case-insensitive share or
    through a bind mount. The destination must not exist yet, or be an empty
    directory; on POSIX, an existing one must also belong to the current
    user and grant no access to its group or to others. On Windows, access
    rests on the location's access control lists, which this does not check.

    Parameters
    ----------
    destination : path-like
    release_directory : path-like
        Where released output goes.
    staging_directory : path-like, optional
        Where output waits for its residual search (D-027).

    Returns
    -------
    pathlib.Path
        The destination, absolute, with its symbolic links resolved.

    Raises
    ------
    QcPackError
        For each reason above, naming the check, never the path.
    """
    target = _resolved(destination, "the QC destination")
    others = {
        "release directory": _resolved(release_directory, "the release directory")
    }
    if staging_directory is not None:
        others["staging directory"] = _resolved(
            staging_directory, "the staging directory"
        )
    _check_apart(target, others)
    status = path_status(target, _CHECKING)
    if status is not None:
        try:
            _check_existing(target, status)
        except OSError as error:
            raise os_error(_CHECKING, error) from None
    return target


def _check_apart(target: Path, others: dict[str, Path]) -> None:
    for name, other in others.items():
        if _within(target, other) or _within(other, target):
            raise QcPackError(
                f"the QC destination must be neither inside the {name} nor contain it"
            )


def _check_existing(target: Path, status: os.stat_result) -> None:
    if not stat.S_ISDIR(status.st_mode):
        raise QcPackError("the QC destination exists and is not a directory")
    if any(target.iterdir()):
        raise QcPackError("the QC destination must be new or an empty directory")
    if _POSIX:
        if status.st_uid != os.geteuid():  # pylint: disable = no-member
            raise QcPackError("the QC destination must belong to the current user")
        if stat.S_IMODE(status.st_mode) & 0o077:
            raise QcPackError(
                "the QC destination grants access to its group or others; "
                "restrict it to its owner (chmod 700)"
            )


def _resolved(path: object, what: str) -> Path:
    if not isinstance(path, (str, os.PathLike)) or not os.fspath(path):
        raise QcPackError(f"{what} must be given as a path")
    try:
        return Path(path).expanduser().resolve(strict=False)
    except (OSError, RuntimeError):  # RuntimeError: a symbolic link loop
        raise QcPackError(f"{what} could not be resolved") from None


def _within(path: Path, directory: Path) -> bool:
    """Return whether ``path`` is ``directory`` or below it, erring towards yes.

    Windows paths compare without case, and so do these on macOS, whose
    volumes are case-insensitive by default. Then the device and inode of
    each existing directory from ``path`` up are compared with
    ``directory``'s, if it exists.
    """
    if sys.platform == "darwin":
        folded = Path(str(path).casefold()), Path(str(directory).casefold())
        if folded[0].is_relative_to(folded[1]):
            return True
    if path.is_relative_to(directory):
        return True
    identity = path_status(directory, _CHECKING)
    if identity is None:  # a directory that does not exist yet holds nothing
        return False
    return any(
        os.path.samestat(status, identity) for status in _existing(path, _CHECKING)
    )


def _existing(path: Path, what: str) -> Iterator[os.stat_result]:
    """Yield the status of each existing path from ``path`` up."""
    for candidate in (path, *path.parents):
        status = path_status(candidate, what)
        if status is not None:
            yield status


def path_status(path: Path, what: str, *, follow: bool = True) -> os.stat_result | None:
    """Return the status of a path, or None if it does not exist.

    Unlike :meth:`pathlib.Path.exists` and its kin, which answer no when a
    path cannot be read, this raises for an inaccessible path, so that a
    check never passes for want of permission.
    """
    try:
        return os.stat(path, follow_symlinks=follow)
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError as error:
        raise os_error(what, error) from None


def os_error(what: str, error: OSError) -> QcPackError:
    reason = error.strerror or type(error).__name__
    return QcPackError(f"{what}: {reason}")


def write_qc_pack(
    pack: QcPack,
    destination: os.PathLike | str,
    *,
    release_directory: os.PathLike | str,
    staging_directory: os.PathLike | str | None = None,
) -> Path:
    """Write a QC pack to a designated, restricted directory.

    The destination is checked by :func:`check_confidential_destination`.
    A new destination is created, with any missing parents, and must not
    appear between the check and its creation; the checks against the
    release and staging directories are then repeated on what was created.
    On POSIX, the directory is opened without following a symbolic link,
    given mode 0o700, and its files are created within it, each with mode
    0o600. It receives, in this order, the marker :data:`MARKER_FILE`,
    :data:`PACK_FILE` from :func:`~.qc_pack.to_json`, and :data:`NOTICE_FILE`,
    the handling notice :data:`NOTICE`. A file is never overwritten.

    Parameters
    ----------
    pack : ~pymedphys._dicom.deidentify.qc_pack.QcPack
    destination : path-like
    release_directory, staging_directory : path-like
        As for :func:`check_confidential_destination`.

    Returns
    -------
    pathlib.Path
        The path of the written :data:`PACK_FILE`.

    Raises
    ------
    QcPackError
        If the destination is refused, or cannot be created or written.
    TypeError
        If ``pack`` is not a :class:`~.qc_pack.QcPack`.
    """
    document = to_json(pack)  # checks the pack before anything is written

    def check(path: os.PathLike | str) -> Path:
        return check_confidential_destination(
            path,
            release_directory=release_directory,
            staging_directory=staging_directory,
        )

    target = check(destination)
    if path_status(target, _CHECKING) is None:
        try:
            target.parent.mkdir(mode=_DIRECTORY_MODE, parents=True, exist_ok=True)
        except OSError as error:
            raise os_error("the QC destination could not be created", error) from None
        try:
            target.mkdir(mode=_DIRECTORY_MODE)
        except FileExistsError:
            raise QcPackError(
                "the QC destination appeared while it was checked"
            ) from None
        except OSError as error:
            raise os_error("the QC destination could not be created", error) from None
    if check(target) != target:
        raise QcPackError("the QC destination changed while it was checked")
    files = ((MARKER_FILE, FORMAT + "\n"), (PACK_FILE, document), (NOTICE_FILE, NOTICE))
    try:
        if _POSIX:
            _write_within(target, files)
        else:
            for name, text in files:
                write_new(target / name, text)
    except FileExistsError:
        raise QcPackError(
            "the QC destination gained a file while it was written"
        ) from None
    except OSError as error:
        raise os_error("the QC pack could not be written", error) from None
    return target / PACK_FILE


def _write_within(target: Path, files: tuple[tuple[str, str], ...]) -> None:
    """Write new files within a directory opened without following links."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW  # pylint: disable = no-member
    directory = os.open(target, flags)
    try:
        if not os.path.samestat(os.fstat(directory), target.stat()):
            raise QcPackError("the QC destination changed while it was written")
        os.fchmod(directory, _DIRECTORY_MODE)  # pylint: disable = no-member
        for name, text in files:
            _write_bytes(name, text.encode("ascii"), directory)
    finally:
        os.close(directory)


def write_new(path: Path, text: str) -> None:
    """Write ASCII text to a new file, mode 0o600 on POSIX, never overwriting.

    Raises
    ------
    FileExistsError
        If the file exists, or is a symbolic link.
    UnicodeEncodeError
        If the text is not ASCII, before the file is created.
    """
    _write_bytes(path, text.encode("ascii"), None)


def _write_bytes(path: Path | str, data: bytes, directory: int | None) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    if directory is None:
        descriptor = os.open(path, flags, _FILE_MODE)
    else:
        descriptor = os.open(path, flags, _FILE_MODE, dir_fd=directory)
    with os.fdopen(descriptor, "wb") as file:
        file.write(data)


def withdraw_qc_pack(destination: Path) -> bool:
    """Remove the files that :func:`write_qc_pack` wrote in ``destination``.

    For a pack whose release was not published. The pack and its notice go
    first and the marker last, only once both are gone, so that whatever
    remains is still recognised as QC material (D-016). The directory is
    kept, empty, so that a run may write to it again.

    Returns
    -------
    bool
        Whether every file is gone.
    """
    withdrawn = True
    for name in (PACK_FILE, NOTICE_FILE):
        try:
            (destination / name).unlink(missing_ok=True)
        except OSError:
            withdrawn = False
    if withdrawn:
        try:
            (destination / MARKER_FILE).unlink(missing_ok=True)
        except OSError:
            withdrawn = False
    return withdrawn


def is_qc_material(path: os.PathLike | str) -> bool:
    """Return whether a path is QC material, or a directory that holds some.

    A path is QC material if it is a QC pack directory, one of its files, or
    anything below one, or if it is a directory with a QC pack anywhere
    below it, recognised by :data:`MARKER_FILE`. A symbolic link below a
    directory counts by its target, since copying a tree often copies what
    its links point to. A release step refuses such a path, so that no
    release or archive includes QC material (D-016).

    Parameters
    ----------
    path : path-like

    Returns
    -------
    bool

    Raises
    ------
    QcPackError
        If part of the tree cannot be read, so the answer is unknown.
    """
    return _is_qc_material(Path(path).expanduser(), set())


def _is_qc_material(path: Path, seen: set[Path]) -> bool:
    try:
        resolved = path.resolve(strict=False)
    except OSError as error:
        raise os_error(_LOOKING, error) from None
    except RuntimeError:  # a symbolic link loop, before Python 3.13
        raise QcPackError(f"{_LOOKING}: a symbolic link loop") from None
    if resolved in seen:
        return False
    seen.add(resolved)
    for directory in (resolved, *resolved.parents):
        marker = path_status(directory / MARKER_FILE, _LOOKING)
        if marker is not None and stat.S_ISREG(marker.st_mode):
            return True
    status = path_status(resolved, _LOOKING)
    if status is None or not stat.S_ISDIR(status.st_mode):
        return False

    def refuse(error: OSError) -> None:
        raise os_error(_LOOKING, error) from None

    for root, directories, files in os.walk(resolved, onerror=refuse):
        if MARKER_FILE in files:
            return True
        for name in (*directories, *files):
            link = Path(root, name)
            status = path_status(link, _LOOKING, follow=False)
            if (
                status is not None
                and stat.S_ISLNK(status.st_mode)
                and _is_qc_material(link, seen)
            ):
                return True
    return False
