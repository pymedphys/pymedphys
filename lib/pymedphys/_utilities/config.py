# Copyright (C) 2026 Jeffrey D. Cooney
# Copyright (C) 2018 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import json
import os
import stat
from contextlib import ExitStack, contextmanager
from pathlib import Path


def get_gantry_tolerance(index, file_hash, config):
    machine_name = index[file_hash]["logfile_header"]["machine"]
    machine_type = config["machine_map"][machine_name]["type"]
    gantry_tolerance = config["machine_types"][machine_type]["gantry_tolerance"]

    return gantry_tolerance


def get_data_directory(config):
    return config["linac_logfile_data_directory"]


def get_cache_filepaths(config):
    metersetmap_config = config["metersetmap"]

    comparison_storage_filepath = os.path.join(
        get_data_directory(config), metersetmap_config["comparisons_cache"]["primary"]
    )
    comparison_storage_scratch = os.path.join(
        get_data_directory(config), metersetmap_config["comparisons_cache"]["scratch"]
    )

    return comparison_storage_filepath, comparison_storage_scratch


def get_metersetmap_parameters(config):
    metersetmap_config = config["metersetmap"]
    grid_resolution = metersetmap_config["grid_resolution"]
    ram_fraction = metersetmap_config["ram_fraction"]

    return grid_resolution, ram_fraction


def get_index(config):
    index_filepath = os.path.join(get_data_directory(config), "index.json")
    with open(index_filepath) as json_data_file:
        index = json.load(json_data_file)

    return index


def get_centre(config, file_info):
    machine = file_info["logfile_header"]["machine"]
    centre = config["machine_map"][machine]["centre"]
    return centre


def get_sql_servers(config):
    centres = list(config["centres"].keys())

    sql_servers = {
        centre: config["centres"][centre]["ois_specific_data"]["sql_server"]
        for centre in centres
    }

    return sql_servers


def get_sql_servers_list(config):
    sql_servers = get_sql_servers(config)

    sql_servers_list = [value for _, value in sql_servers.items()]

    return sql_servers_list


_INDEXED_PATH_ERROR = "Indexed logfile path escapes the indexed directory."


def _indexed_root_path(indexed_root):
    """Resolve the configured indexed root without allowing it to be redirected."""
    configured_root = Path(indexed_root)
    if configured_root.is_symlink() or (
        hasattr(configured_root, "is_junction") and configured_root.is_junction()
    ):
        raise ValueError

    root = configured_root.resolve()
    # A root symlink or junction must not redefine the trust boundary.
    if root != configured_root.parent.resolve() / configured_root.name:
        raise ValueError
    return root


def _relative_parts(root, candidate):
    """Get in-root components, accepting genuine case aliases on macOS."""
    if candidate.is_relative_to(root):
        parts = candidate.relative_to(root).parts
    else:
        parts = ()
        for ancestor in candidate.parents:
            try:
                if ancestor.samefile(root):
                    parts = candidate.relative_to(ancestor).parts
                    break
            except (FileNotFoundError, NotADirectoryError):
                continue

    if not parts or any(part in ("", ".", "..") for part in parts):
        raise ValueError
    return parts


def _resolve_indexed_logfile_path(indexed_root, relative_path):
    """Resolve an indexed logfile to a regular file or an as-yet-missing path.

    A returned pathname cannot protect a separate later read against concurrent
    replacement. Use _open_indexed_logfile for security-sensitive reads.
    """
    try:
        relative_path = Path(relative_path)
        if (
            relative_path.is_absolute()
            or relative_path.drive
            or ".." in relative_path.parts
        ):
            raise ValueError

        root = _indexed_root_path(indexed_root)
        candidate = (root / relative_path).resolve()
        _relative_parts(root, candidate)

        try:
            mode = candidate.stat().st_mode
        except FileNotFoundError:
            pass
        else:
            if not stat.S_ISREG(mode):
                raise ValueError

        return str(candidate)
    except (OSError, RuntimeError, TypeError, ValueError):
        raise ValueError(_INDEXED_PATH_ERROR) from None


def _windows_opened_path(fd):
    """Retrieve the actual opened file's path from its Windows handle."""
    import ctypes
    import msvcrt
    from ctypes import wintypes

    get_path = ctypes.WinDLL("kernel32", use_last_error=True).GetFinalPathNameByHandleW
    get_path.argtypes = [
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    get_path.restype = wintypes.DWORD

    handle = msvcrt.get_osfhandle(fd)
    length = get_path(handle, None, 0, 0)
    if length == 0:
        raise OSError
    buffer = ctypes.create_unicode_buffer(length + 1)
    used = get_path(handle, buffer, len(buffer), 0)
    if used == 0 or used >= len(buffer):
        raise OSError

    path = buffer.value
    if path.startswith("\\\\?\\UNC\\"):
        path = "\\\\" + path[8:]
    elif path.startswith("\\\\?\\"):
        path = path[4:]
    return Path(path)


def _open_indexed_logfile_fd(indexed_root, relative_path):
    resolved_path = Path(_resolve_indexed_logfile_path(indexed_root, relative_path))
    root = _indexed_root_path(indexed_root)
    parts = _relative_parts(root, resolved_path)

    if os.name == "nt":
        # Check the opened handle's location before reading any bytes.
        fd = os.open(resolved_path, os.O_RDONLY | os.O_BINARY)
        try:
            _relative_parts(root, _windows_opened_path(fd))
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError
        except BaseException:
            os.close(fd)
            raise
        return fd

    # On POSIX, open every component relative to a pinned directory handle.
    # No-follow prevents a replacement symlink from crossing the root.
    if not (hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY")):
        raise ValueError

    dir_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
    with ExitStack() as stack:
        # A deliberately configured alias for the data directory is permitted.
        data_fd = os.open(root.parent, os.O_RDONLY | os.O_DIRECTORY)
        stack.callback(os.close, data_fd)
        current_fd = os.open(root.name, dir_flags, dir_fd=data_fd)
        stack.callback(os.close, current_fd)
        for part in parts[:-1]:
            current_fd = os.open(part, dir_flags, dir_fd=current_fd)
            stack.callback(os.close, current_fd)

        fd = os.open(parts[-1], file_flags, dir_fd=current_fd)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError
        except BaseException:
            os.close(fd)
            raise
        return fd


@contextmanager
def _open_indexed_logfile(indexed_root, relative_path):
    """Open a pinned regular-file handle without following replacement links."""
    try:
        fd = _open_indexed_logfile_fd(indexed_root, relative_path)
    except FileNotFoundError:
        raise FileNotFoundError(
            "Indexed logfile can't be found in its declared location."
        ) from None
    except (OSError, RuntimeError, TypeError, ValueError):
        raise ValueError(_INDEXED_PATH_ERROR) from None

    with os.fdopen(fd, "rb") as stream:
        yield stream


def get_filepath(index, config, filehash):
    return _resolve_indexed_logfile_path(
        os.path.join(get_data_directory(config), "indexed"),
        index[filehash]["filepath"],
    )
