# Copyright (C) 2019 Cancer Care Associates
# Copyright (C) 2026 jdotc1

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import contextlib
import errno
import os
import pathlib
import shutil
import stat
import zipfile
from glob import glob


def _validate_directory_component(value):
    """Accept exactly one portable machine/root directory component."""
    try:
        name = os.fspath(value)
    except TypeError as error:
        raise ValueError("Directory identifier must be a single safe name.") from error

    reserved_names = {"CON", "PRN", "AUX", "NUL"}
    reserved_names.update(f"COM{i}" for i in range(1, 10))
    reserved_names.update(f"LPT{i}" for i in range(1, 10))
    if (
        not isinstance(name, str)
        or name in ("", ".", "..")
        or name.endswith((" ", "."))
        or any(ord(char) < 32 or ord(char) == 127 for char in name)
        or any(char in '/\\<>:"|?*' for char in name)
        or name.split(".", 1)[0].rstrip(" .").upper() in reserved_names
    ):
        raise ValueError("Directory identifier must be a single safe name.")
    return name


def _open_child_directory(parent_fd, name):
    """Create/open a child without following a symlink or losing its parent."""
    try:
        os.mkdir(name, dir_fd=parent_fd)
    except FileExistsError:
        pass
    try:
        return os.open(
            name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=parent_fd,
        )
    except OSError as error:
        if error.errno in (errno.ELOOP, errno.ENOTDIR):
            raise ValueError(
                "Diagnostics directory is a symlink or not a directory."
            ) from error
        raise


def _pin_windows_directory(path, stack):
    """Pin a Windows directory against rename/replacement and reject reparse points."""
    import ctypes
    from ctypes import wintypes

    class FileInformation(ctypes.Structure):
        _fields_ = [
            ("attributes", wintypes.DWORD),
            ("created", wintypes.FILETIME),
            ("accessed", wintypes.FILETIME),
            ("modified", wintypes.FILETIME),
            ("volume_serial", wintypes.DWORD),
            ("size_high", wintypes.DWORD),
            ("size_low", wintypes.DWORD),
            ("links", wintypes.DWORD),
            ("file_index_high", wintypes.DWORD),
            ("file_index_low", wintypes.DWORD),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel.CreateFileW
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
    get_info = kernel.GetFileInformationByHandle
    get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(FileInformation)]
    get_info.restype = wintypes.BOOL
    close_handle = kernel.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    # No FILE_SHARE_DELETE: a checked directory cannot be renamed/replaced
    # while it is used. OPEN_REPARSE_POINT inspects the link itself.
    handle = create_file(
        str(path), 0x80, 0x1 | 0x2, None, 3, 0x02000000 | 0x00200000, None
    )
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    stack.callback(close_handle, handle)
    info = FileInformation()
    if not get_info(handle, ctypes.byref(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    if info.attributes & 0x400:
        raise ValueError("Diagnostics directory is a symlink or reparse point.")


@contextlib.contextmanager
def _anchored_machine_directories(
    storage_directory, pending_name, archive_name, machine
):
    """Hold checked directories throughout the diagnostic copy."""
    storage_root = pathlib.Path(storage_directory)
    storage_root.mkdir(parents=True, exist_ok=True)
    # The user-configured storage directory itself is the trust boundary.
    storage_root = storage_root.resolve()
    pending_path = storage_root / pending_name
    archived_path = storage_root / archive_name
    machine_pending = pending_path / machine
    machine_archived = archived_path / machine

    with contextlib.ExitStack() as stack:
        if os.name == "nt":
            _pin_windows_directory(storage_root, stack)
            for path in (pending_path, archived_path):
                path.mkdir(exist_ok=True)
                _pin_windows_directory(path, stack)
            for path in (machine_pending, machine_archived):
                path.mkdir(exist_ok=True)
                _pin_windows_directory(path, stack)
            yield str(machine_pending), str(machine_archived), None, None
        else:
            root_fd = os.open(
                storage_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            )
            stack.callback(os.close, root_fd)
            pending_fd = _open_child_directory(root_fd, pending_name)
            stack.callback(os.close, pending_fd)
            archive_fd = _open_child_directory(root_fd, archive_name)
            stack.callback(os.close, archive_fd)
            machine_pending_fd = _open_child_directory(pending_fd, machine)
            stack.callback(os.close, machine_pending_fd)
            machine_archived_fd = _open_child_directory(archive_fd, machine)
            stack.callback(os.close, machine_archived_fd)
            yield (
                str(machine_pending),
                str(machine_archived),
                machine_pending_fd,
                machine_archived_fd,
            )


def _existing_regular_file(path, directory_fd=None):
    """Check for a previously copied ZIP, refusing links and special files."""
    try:
        if directory_fd is None:
            info = os.lstat(path)
        else:
            info = os.stat(
                os.path.basename(path), dir_fd=directory_fd, follow_symlinks=False
            )
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("Diagnostics ZIP destination is not a regular file.")
    return True


def _copy_zip_exclusive(source_path, destination_path, destination_fd=None):
    """Create a destination that cannot overwrite a symlink after checking."""
    basename = os.path.basename(destination_path)
    try:
        if destination_fd is None:
            fd = os.open(destination_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        else:
            fd = os.open(
                basename,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o666,
                dir_fd=destination_fd,
            )
    except FileExistsError:
        return False

    try:
        with os.fdopen(fd, "wb") as destination, open(source_path, "rb") as source:
            shutil.copyfileobj(source, destination)
    except BaseException:
        # Remove an incomplete copy via the same anchored directory handle.
        if destination_fd is None:
            os.unlink(destination_path)
        else:
            os.unlink(basename, dir_fd=destination_fd)
        raise
    return True


def fetch_system_diagnostics(
    ip, storage_directory, other_directory=None, *, storage_fd=None, other_fd=None
):
    r"""Fetches and stores locally Linac system diagnostic files.

    For an Elekta Linac the system diagnostic backups are stored at
    \\IP\Backup\TCS\SDD+*.zip. These are copied to a defined local directory.

    Need to have logged in to this directory and ticked "remember credentials".
    You will need to use a login for the Linac NSS supplied by an Elekta
    engineer to access this file share.
    """

    backup_share_path = "\\\\{}\\Backup\\TCS\\".format(ip)
    diagnostic_file_search = "{}\\SDD+*.zip".format(backup_share_path)
    diagnostic_filepaths = glob(diagnostic_file_search)

    print("Found {} diagnostic zip files:".format(len(diagnostic_filepaths)))

    if other_directory is None:
        other_directory = storage_directory
        other_fd = storage_fd

    for nss_filepath in diagnostic_filepaths:
        basename = os.path.basename(nss_filepath)
        storage_filepath = os.path.join(storage_directory, basename)
        other_filepath = os.path.join(other_directory, basename)
        if _existing_regular_file(
            storage_filepath, storage_fd
        ) or _existing_regular_file(other_filepath, other_fd):
            print("    {} has already been copied.".format(basename))
            continue
        if _copy_zip_exclusive(nss_filepath, storage_filepath, storage_fd):
            print("    Copying {}...".format(basename))
        else:
            print("    {} has already been copied.".format(basename))


def fetch_system_diagnostics_multi_linac(
    machine_ip_map,
    storage_directory,
    to_be_indexed="to_be_indexed",
    already_indexed="already_indexed",
):
    """Run `fetch_system_diagnostics` for a set of machines and corresponding
    IPs.

    Won't redownload the diagnostic files if that diagnostics zip filename
    exists in either to_be_indexed or already_indexed.

    Example
    -------

    machine_ip_map = {
        '2619': '10.0.0.1',
        '2694': '10.0.0.2'
    }

    storage_directory = 'path/to/diagnostics/storage'

    fetch_system_diagnostics_multi_linac(machine_ip_map, storage_directory)
    """

    pending_name = _validate_directory_component(to_be_indexed)
    archive_name = _validate_directory_component(already_indexed)
    if pending_name.casefold() == archive_name.casefold():
        raise ValueError("Pending and archived diagnostics roots must differ.")

    # Validate the entire map before collecting from any machine.
    checked_machines = []
    seen_names = set()
    for machine, ip in machine_ip_map.items():
        try:
            name = _validate_directory_component(machine)
        except ValueError as error:
            raise ValueError(
                "Machine identifier must be a single safe directory name."
            ) from error
        folded = name.casefold()
        if folded in seen_names:
            raise ValueError("Machine identifiers must not alias on Windows.")
        seen_names.add(folded)
        checked_machines.append((name, ip))

    for machine, ip in checked_machines:
        print("\nFetching diagnostic zip files from {} @ {}".format(machine, ip))
        with _anchored_machine_directories(
            storage_directory, pending_name, archive_name, machine
        ) as (pending, archived, pending_fd, archived_fd):
            fetch_system_diagnostics(
                ip, pending, archived, storage_fd=pending_fd, other_fd=archived_fd
            )

    print("")


def already_indexed_path(current_location, to_be_indexed, already_indexed):
    machine_and_zip_filepath = os.path.relpath(current_location, to_be_indexed)

    path_to_be_moved_to = os.path.join(already_indexed, machine_and_zip_filepath)

    return os.path.abspath(path_to_be_moved_to)


def extract_diagnostic_zips_and_archive(logfile_data_directory):
    diagnostics_directory = os.path.join(logfile_data_directory, "diagnostics")
    diagnostics_to_be_indexed = os.path.join(diagnostics_directory, "to_be_indexed")
    diagnostics_already_indexed = os.path.join(diagnostics_directory, "already_indexed")

    logfiles_to_be_indexed = os.path.join(logfile_data_directory, "to_be_indexed")

    diagnostics_search_string = os.path.join(diagnostics_to_be_indexed, "*", "*.zip")

    diagnostics_filepaths = glob(diagnostics_search_string)

    print(
        "There are {} diagnostic zips which need to be extracted".format(
            len(diagnostics_filepaths)
        )
    )

    for diagnostic_filepath in diagnostics_filepaths:
        path_to_be_moved_to = already_indexed_path(
            diagnostic_filepath, diagnostics_to_be_indexed, diagnostics_already_indexed
        )

        pathlib.Path(os.path.dirname(path_to_be_moved_to)).mkdir(
            parents=True, exist_ok=True
        )

        print("    Extracting {}".format(diagnostic_filepath))

        with zipfile.ZipFile(diagnostic_filepath, "r") as zip_file:
            for file_name in zip_file.namelist():
                if file_name.endswith(".trf"):
                    zip_file.extract(file_name, logfiles_to_be_indexed)

        shutil.move(diagnostic_filepath, path_to_be_moved_to)
