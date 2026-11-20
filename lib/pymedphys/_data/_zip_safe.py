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
import errno
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
        with _windows_pinned_directory(root, parts[:-1]) as parent:
            target = parent / parts[-1] if parts else parent
            result = target.lstat()
    else:
        with _directory_fd(root, parts[:-1]) as descriptor:
            result = (
                os.stat(parts[-1], dir_fd=descriptor, follow_symlinks=False)
                if parts
                else os.fstat(descriptor)
            )
    # A hard link can be introduced after preflight and impersonate a cache
    # member. Never accept a multiply linked regular file as cached data.
    if (
        stat.S_ISLNK(result.st_mode)
        or (
            os.name == "nt"
            and result.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
        )
        or (stat.S_ISREG(result.st_mode) and result.st_nlink > 1)
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


def _existing_regular_file(descriptor: int, leaf: str) -> None:
    """Only a local, singly linked regular file may win a creation race."""
    try:
        current = os.stat(leaf, dir_fd=descriptor, follow_symlinks=False)
    except OSError:
        raise ValueError(_UNSAFE) from None
    if not stat.S_ISREG(current.st_mode) or current.st_nlink > 1:
        raise ValueError(_UNSAFE)


def _install_missing_posix(temporary: str, leaf: str, descriptor: int) -> None:
    """Atomically link a staged file; copy exclusively if links are unsupported."""
    try:
        os.link(
            temporary,
            leaf,
            src_dir_fd=descriptor,
            dst_dir_fd=descriptor,
            follow_symlinks=False,
        )
    except FileExistsError:
        _existing_regular_file(descriptor, leaf)
    except OSError as error:
        if error.errno not in {
            errno.ENOSYS,
            errno.EOPNOTSUPP,
            errno.EPERM,
            errno.EACCES,
            errno.EXDEV,
        }:
            raise
        # O_EXCL and the pinned parent FD prevent a pre-existing user file
        # from being overwritten, without relying on hard-link support.
        try:
            output = os.open(
                leaf,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o666,
                dir_fd=descriptor,
            )
        except FileExistsError:
            _existing_regular_file(descriptor, leaf)
            return
        try:
            with (
                os.fdopen(output, "wb") as destination,
                os.fdopen(
                    os.open(temporary, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=descriptor),
                    "rb",
                ) as source,
            ):
                shutil.copyfileobj(source, destination)
        except BaseException:
            os.unlink(leaf, dir_fd=descriptor)
            raise


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
                    _install_missing_posix(temporary, leaf, descriptor)
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


def _windows_file_attributes(kernel32: object, handle: int) -> int:
    """Read basic file attributes on FAT and NTFS without following links."""
    import ctypes
    from ctypes import wintypes

    class _FileBasicInfo(ctypes.Structure):
        _fields_ = [
            ("creation_time", ctypes.c_int64),
            ("last_access_time", ctypes.c_int64),
            ("last_write_time", ctypes.c_int64),
            ("change_time", ctypes.c_int64),
            ("file_attributes", wintypes.DWORD),
        ]

    attributes = getattr(kernel32, "GetFileInformationByHandleEx")
    attributes.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    attributes.restype = wintypes.BOOL
    info = _FileBasicInfo()
    if not attributes(handle, 0, ctypes.byref(info), ctypes.sizeof(info)):
        raise ValueError(_UNSAFE)
    return int(info.file_attributes)


@contextlib.contextmanager
def _windows_pinned_directory(
    root: pathlib.Path, children: tuple[str, ...] = (), *, create: bool = False
) -> Iterator[pathlib.Path]:
    """Pin each Windows ancestor against renames and junction substitution.

    Handles are opened with FILE_FLAG_OPEN_REPARSE_POINT, checked as real
    directories with FILE_LIST_DIRECTORY access, and held without
    FILE_SHARE_DELETE until publication ends. This blocks parent renames.
    """
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    path = pathlib.Path(root).absolute()
    if not path.anchor:
        raise ValueError(_UNSAFE)
    current = pathlib.Path(path.anchor)
    handles = []
    try:
        for part in (None, *path.parts[1:], *children):
            if part is not None:
                current /= part
                if create:
                    try:
                        current.mkdir()
                    except FileExistsError:
                        pass
            handle = create_file(
                str(current),
                0x81,  # FILE_LIST_DIRECTORY | FILE_READ_ATTRIBUTES: rename guard
                0x1 | 0x2,  # FILE_SHARE_READ | FILE_SHARE_WRITE (not DELETE)
                None,
                3,  # OPEN_EXISTING
                0x02000000 | 0x00200000,  # BACKUP_SEMANTICS | OPEN_REPARSE_POINT
                None,
            )
            if handle is None or handle == ctypes.c_void_p(-1).value:
                raise ValueError(_UNSAFE)
            handles.append(handle)
            attributes = _windows_file_attributes(kernel32, handle)
            if not (attributes & 0x10) or (attributes & 0x400):
                # FILE_ATTRIBUTE_DIRECTORY, FILE_ATTRIBUTE_REPARSE_POINT
                raise ValueError(_UNSAFE)
        yield current
    except (OSError, RuntimeError):
        raise ValueError(_UNSAFE) from None
    finally:
        for handle in reversed(handles):
            close_handle(handle)


def _windows_open_regular_file(path: pathlib.Path) -> int:
    """Open an existing Windows file without dereferencing a reparse point."""
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    handle = create_file(
        str(path),
        0x80000000,  # GENERIC_READ
        0x1 | 0x2,  # Share reads/writes but not deletion
        None,
        3,  # OPEN_EXISTING
        0x00200000,  # FILE_FLAG_OPEN_REPARSE_POINT
        None,
    )
    if handle is None or handle == ctypes.c_void_p(-1).value:
        raise ValueError(_UNSAFE)
    try:
        attributes = _windows_file_attributes(kernel32, handle)
        if attributes & (0x10 | 0x400):  # Directory or reparse point
            raise ValueError(_UNSAFE)
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        handle = None  # The Python descriptor owns the native handle.
        return descriptor
    finally:
        if handle is not None:
            close_handle(handle)


def ensure_root(root: pathlib.Path) -> None:
    """Create a missing extraction root using no-follow directory traversal."""
    if os.name == "nt":
        with _windows_pinned_directory(root, create=True):
            pass
    else:
        with _directory_fd(root, create=True):
            pass


def _extract_windows(
    zip_file: zipfile.ZipFile, root: pathlib.Path, *, missing_only: bool
) -> None:
    """Install one member at a time under pinned, no-junction Windows parents."""
    root = pathlib.Path(root)
    ensure_root(root)
    for info in last_members(zip_file):
        parts = _parts(info.filename)
        with _windows_pinned_directory(root, parts[:-1], create=True) as parent:
            target = parent / parts[-1]
            if target.is_symlink() or target.is_junction():
                raise ValueError(_UNSAFE)
            try:
                existing = target.lstat()
            except FileNotFoundError:
                existing = None
            if existing is not None and (
                existing.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
            ):
                raise ValueError(_UNSAFE)
            if info.is_dir():
                if existing is not None:
                    if not stat.S_ISDIR(existing.st_mode):
                        raise ValueError(_UNSAFE)
                else:
                    try:
                        target.mkdir()
                    except FileExistsError:
                        if target.is_symlink() or target.is_junction():
                            raise ValueError(_UNSAFE) from None
                        if not target.is_dir():
                            raise ValueError(_UNSAFE) from None
                continue
            if existing is not None:
                if not stat.S_ISREG(existing.st_mode) or existing.st_nlink > 1:
                    raise ValueError(_UNSAFE)
                if missing_only:
                    continue

            # Stage only one member at a time on the same filesystem.
            descriptor, temp_name = tempfile.mkstemp(
                dir=root.parent, prefix=".pymedphys-zip-", suffix=".part"
            )
            temp_path = pathlib.Path(temp_name)
            try:
                with os.fdopen(descriptor, "wb") as destination, zip_file.open(
                    info
                ) as source:
                    shutil.copyfileobj(source, destination)

                # All ancestor handles remain open without SHARE_DELETE until
                # the replacement finishes, so a parent cannot be junction-swapped.
                if missing_only:
                    try:
                        os.link(temp_path, target)
                    except FileExistsError:
                        if target.is_symlink() or target.is_junction():
                            raise ValueError(_UNSAFE) from None
                        current = target.lstat()
                        if not stat.S_ISREG(current.st_mode) or current.st_nlink > 1:
                            raise ValueError(_UNSAFE) from None
                    except OSError as error:
                        if error.errno not in {
                            errno.ENOSYS,
                            errno.EOPNOTSUPP,
                            errno.EPERM,
                            errno.EACCES,
                            errno.EXDEV,
                        }:
                            raise
                        # Unlike POSIX, Windows os.rename refuses to overwrite
                        # an existing target, preserving caller edits atomically.
                        try:
                            os.rename(temp_path, target)
                        except FileExistsError:
                            if target.is_symlink() or target.is_junction():
                                raise ValueError(_UNSAFE) from None
                            current = target.lstat()
                            if (
                                not stat.S_ISREG(current.st_mode)
                                or current.st_nlink > 1
                            ):
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
        with _windows_pinned_directory(marker.parent):
            with os.fdopen(_windows_open_regular_file(marker), "rb") as stream:
                current = os.fstat(stream.fileno())
                if not stat.S_ISREG(current.st_mode) or current.st_nlink > 1:
                    raise ValueError(_UNSAFE)
                return stream.read(128)
    with _directory_fd(marker.parent) as descriptor:
        handle = os.open(
            marker.name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=descriptor,
        )
        with os.fdopen(handle, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError(_UNSAFE)
            return stream.read(128)


def unlink_marker(marker: pathlib.Path) -> None:
    marker = pathlib.Path(marker)
    if os.name == "nt":
        with _windows_pinned_directory(marker.parent):
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
        with _windows_pinned_directory(marker.parent):
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
