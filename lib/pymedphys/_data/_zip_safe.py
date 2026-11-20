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

_UNSAFE = "ZIP archive contains a linked extraction path"


def _parts(name):
    return pathlib.PurePosixPath(name.replace("\\", "/")).parts


def _root_entry(info):
    return info.filename.replace("\\", "/") in {"", ".", "./"}


@contextlib.contextmanager
def _directory_fd(root, children=(), *, create=False):
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


def _windows_check_path(root, parts):
    current = pathlib.Path(root)
    for component in (None, *parts):
        if component is not None:
            current = current / component
        if current.is_symlink() or current.is_junction():
            raise ValueError(_UNSAFE)
    return current


def member_stat(root, name):
    """Inspect a member without following any archive-path symlink."""
    parts = _parts(name)
    if os.name == "nt":
        return _windows_check_path(root, parts).lstat()

    with _directory_fd(root, parts[:-1]) as descriptor:
        result = (
            os.stat(parts[-1], dir_fd=descriptor, follow_symlinks=False)
            if parts
            else os.fstat(descriptor)
        )
    if stat.S_ISLNK(result.st_mode):
        raise ValueError(_UNSAFE)
    return result


def _extract_posix(zip_file, root, *, missing_only):
    with _directory_fd(root, create=True):
        pass

    for info in zip_file.infolist():
        if _root_entry(info):
            continue
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
                0o600,
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


def _extract_windows(zip_file, root, *, missing_only):
    """Stage archive bytes; stdlib Windows lacks directory-fd operations."""
    root = pathlib.Path(root)
    root.mkdir(parents=True, exist_ok=True)
    infos = [info for info in zip_file.infolist() if not _root_entry(info)]
    with tempfile.TemporaryDirectory(
        prefix=".pymedphys-zip-", dir=root.parent
    ) as staged_root:
        zip_file.extractall(path=staged_root, members=infos)
        processed = set()
        for info in infos:
            parts = _parts(info.filename)
            if parts in processed:
                continue
            processed.add(parts)
            parent = _windows_check_path(root, parts[:-1])
            parent.mkdir(parents=True, exist_ok=True)
            target = _windows_check_path(root, parts)
            if info.is_dir():
                target.mkdir(exist_ok=True)
                continue
            if target.exists():
                if target.stat().st_nlink > 1:
                    raise ValueError(_UNSAFE)
                if missing_only:
                    continue
            staged = pathlib.Path(staged_root).joinpath(*parts)
            if missing_only:
                try:
                    os.link(staged, target)
                except FileExistsError:
                    if target.is_symlink() or target.stat().st_nlink > 1:
                        raise ValueError(_UNSAFE) from None
            else:
                os.replace(staged, target)


def extract_members(zip_file, root, *, missing_only):
    """Extract validated members, preserving edited caller-managed files."""
    if os.name == "nt":
        _extract_windows(zip_file, root, missing_only=missing_only)
    else:
        _extract_posix(zip_file, root, missing_only=missing_only)


def marker_bytes(marker):
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


def unlink_marker(marker):
    marker = pathlib.Path(marker)
    if os.name == "nt":
        marker.unlink(missing_ok=True)
    else:
        with _directory_fd(marker.parent) as descriptor:
            try:
                os.unlink(marker.name, dir_fd=descriptor)
            except FileNotFoundError:
                pass


def write_marker(marker, content):
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
