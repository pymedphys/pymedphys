# Copyright (C) 2026 Jeff (jdotc1)

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Race-resistant ZIP extraction for prevalidated archive members.

POSIX operations use no-follow directory descriptors. Windows files are first
extracted to a private staging directory and installed with link/replace.
"""

import contextlib
import os
import pathlib
import secrets
import shutil
import stat
import tempfile
import zipfile
from collections.abc import Iterator

_UNSAFE = "ZIP archive contains a linked extraction path"


def _parts(name: str) -> tuple[str, ...]:
    return pathlib.PurePosixPath(name.replace("\\", "/")).parts


def _root_entry(info: zipfile.ZipInfo) -> bool:
    return info.filename.replace("\\", "/") in {"", ".", "./"}


@contextlib.contextmanager
def _directory_fd(
    root: os.PathLike[str] | str,
    children: tuple[str, ...] = (),
    *,
    create: bool = False,
) -> Iterator[int]:
    """Walk canonical paths using directory handles and no-follow flags."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    components = (*pathlib.Path(root).parts, *children)
    descriptor = os.open(components[0], flags)
    try:
        for component in components[1:]:
            try:
                if create:
                    try:
                        os.mkdir(component, dir_fd=descriptor)
                    except FileExistsError:
                        pass
                next_descriptor = os.open(component, flags, dir_fd=descriptor)
            except (OSError, RuntimeError):
                raise ValueError(_UNSAFE) from None
            os.close(descriptor)
            descriptor = next_descriptor
        yield descriptor
    finally:
        os.close(descriptor)


def _windows_check_path(
    root: os.PathLike[str] | str, parts: tuple[str, ...]
) -> pathlib.Path:
    current = pathlib.Path(root)
    for component in (None, *parts):
        if component is not None:
            current = current / component
        if current.is_symlink() or current.is_junction():
            raise ValueError(_UNSAFE)
    return current


def member_stat(root: pathlib.Path, name: str) -> os.stat_result:
    """Inspect a member without following any archive-path symlink."""
    parts = _parts(name)
    if os.name == "nt":
        result = _windows_check_path(root, parts).lstat()
    else:
        with _directory_fd(root, parts[:-1]) as descriptor:
            result = (
                os.stat(parts[-1], dir_fd=descriptor, follow_symlinks=False)
                if parts
                else os.fstat(descriptor)
            )
    # A hard link can be introduced after preflight and impersonate a cache
    # member. Never accept a multiply linked regular file as cached data.
    if stat.S_ISLNK(result.st_mode) or (
        stat.S_ISREG(result.st_mode) and result.st_nlink > 1
    ):
        raise ValueError(_UNSAFE)
    return result


def last_members(zip_file: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    """Use the last archive member at each normalized extraction location.

    Both exact duplicate names and aliases like data and ./data map to one
    physical target. Keep the last one rather than the first.
    """
    latest: dict[tuple[str, ...], zipfile.ZipInfo] = {}
    for info in zip_file.infolist():
        if not _root_entry(info):
            latest[_parts(info.filename)] = info
    return list(latest.values())


def _extract_posix(
    zip_file: zipfile.ZipFile, root: pathlib.Path, *, missing_only: bool
) -> None:
    with _directory_fd(root, create=True):
        pass

    for info in last_members(zip_file):
        parts = _parts(info.filename)
        with _directory_fd(root, parts[:-1], create=True) as descriptor:
            leaf = parts[-1]
            try:
                existing = os.stat(leaf, dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError:
                existing = None
            except OSError:
                raise ValueError(_UNSAFE) from None

            if existing is not None:
                if stat.S_ISLNK(existing.st_mode) or (
                    stat.S_ISREG(existing.st_mode) and existing.st_nlink > 1
                ):
                    raise ValueError(_UNSAFE)
                if info.is_dir():
                    if not stat.S_ISDIR(existing.st_mode):
                        raise ValueError(_UNSAFE)
                    continue
                if not stat.S_ISREG(existing.st_mode):
                    raise ValueError(_UNSAFE)
                if missing_only:
                    continue

            if info.is_dir():
                try:
                    os.mkdir(leaf, dir_fd=descriptor)
                except FileExistsError:
                    updated = os.stat(
                        leaf, dir_fd=descriptor, follow_symlinks=False
                    )
                    if not stat.S_ISDIR(updated.st_mode):
                        raise ValueError(_UNSAFE)
                continue

            temporary = f".pymedphys-zip-{secrets.token_hex(12)}.part"
            temp_fd = os.open(
                temporary,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                0o666,
                dir_fd=descriptor,
            )
            try:
                with os.fdopen(temp_fd, "wb") as destination, zip_file.open(
                    info
                ) as source:
                    shutil.copyfileobj(source, destination)
                if missing_only:
                    try:
                        os.link(
                            temporary,
                            leaf,
                            src_dir_fd=descriptor,
                            dst_dir_fd=descriptor,
                            follow_symlinks=False,
                        )
                    except FileExistsError:
                        updated = os.stat(
                            leaf, dir_fd=descriptor, follow_symlinks=False
                        )
                        if not stat.S_ISREG(updated.st_mode) or updated.st_nlink > 1:
                            raise ValueError(_UNSAFE) from None
                else:
                    os.replace(
                        temporary,
                        leaf,
                        src_dir_fd=descriptor,
                        dst_dir_fd=descriptor,
                    )
            finally:
                try:
                    os.unlink(temporary, dir_fd=descriptor)
                except FileNotFoundError:
                    pass


def _extract_windows(
    zip_file: zipfile.ZipFile, root: pathlib.Path, *, missing_only: bool
) -> None:
    """Stage one member at a time to bound temporary storage on Windows.

    Windows Python lacks dir_fd-based file creation, so ancestor directories
    are rechecked before publishing each entry. A concurrent junction swap
    between the final check and replace still requires native handle APIs
    to eliminate completely.
    """
    root = pathlib.Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for info in last_members(zip_file):
        parts = _parts(info.filename)
        parent = _windows_check_path(root, parts[:-1])
        parent.mkdir(parents=True, exist_ok=True)
        target = _windows_check_path(root, parts)

        if info.is_dir():
            if target.exists() and not target.is_dir():
                raise ValueError(_UNSAFE)
            target.mkdir(exist_ok=True)
            continue

        if target.exists():
            if not target.is_file() or target.stat().st_nlink > 1:
                raise ValueError(_UNSAFE)
            if missing_only:
                continue

        # Keep no more than one decompressed member in temporary storage.
        # mkstemp provides an unpredictable name and a handle opened O_EXCL.
        descriptor, temp_name = tempfile.mkstemp(
            dir=root.parent, prefix=".pymedphys-zip-", suffix=".part"
        )
        temp_path = pathlib.Path(temp_name)
        try:
            with os.fdopen(descriptor, "wb") as destination, zip_file.open(
                info
            ) as source:
                shutil.copyfileobj(source, destination)

            _windows_check_path(root, parts)
            if missing_only:
                try:
                    os.link(temp_path, target)
                except FileExistsError:
                    if target.is_symlink() or target.stat().st_nlink > 1:
                        raise ValueError(_UNSAFE) from None
            else:
                os.replace(temp_path, target)
        finally:
            temp_path.unlink(missing_ok=True)


def extract_members(
    zip_file: zipfile.ZipFile, root: pathlib.Path, *, missing_only: bool
) -> None:
    """Extract validated members, preserving edited caller-managed files."""
    if os.name == "nt":
        _extract_windows(zip_file, root, missing_only=missing_only)
    else:
        _extract_posix(zip_file, root, missing_only=missing_only)


def marker_bytes(marker: pathlib.Path) -> bytes:
    """Read the extraction marker without following a substituted link."""
    marker = pathlib.Path(marker)
    if os.name == "nt":
        if marker.is_symlink() or marker.is_junction():
            raise ValueError(_UNSAFE)
        return marker.read_bytes()
    with _directory_fd(marker.parent) as descriptor:
        handle = os.open(
            marker.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=descriptor
        )
        with os.fdopen(handle, "rb") as stream:
            return stream.read()


def unlink_marker(marker: pathlib.Path) -> None:
    marker = pathlib.Path(marker)
    if os.name == "nt":
        marker.unlink(missing_ok=True)
    else:
        with _directory_fd(marker.parent) as descriptor:
            try:
                os.unlink(marker.name, dir_fd=descriptor)
            except FileNotFoundError:
                pass


def write_marker(marker: pathlib.Path, content: str) -> None:
    """Publish a complete marker atomically, without opening the old target."""
    marker = pathlib.Path(marker)
    if os.name == "nt":
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=marker.parent,
            prefix=".pymedphys-marker-",
            delete=False,
        ) as stream:
            staged = pathlib.Path(stream.name)
            stream.write(content)
        try:
            os.replace(staged, marker)
        finally:
            staged.unlink(missing_ok=True)
    else:
        with _directory_fd(marker.parent) as descriptor:
            temporary = f".pymedphys-marker-{secrets.token_hex(12)}.part"
            handle = os.open(
                temporary,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                0o600,
                dir_fd=descriptor,
            )
            try:
                with os.fdopen(handle, "w", encoding="utf-8") as stream:
                    stream.write(content)
                os.replace(
                    temporary,
                    marker.name,
                    src_dir_fd=descriptor,
                    dst_dir_fd=descriptor,
                )
            finally:
                try:
                    os.unlink(temporary, dir_fd=descriptor)
                except FileNotFoundError:
                    pass
