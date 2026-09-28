# Copyright (C) 2026 Matthew Jennings
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

import contextlib
import string

# pylint: disable = import-error


def get_detached_file_descriptor(filepath):
    try:
        import win32file  # type: ignore
    except ImportError:
        return filepath

    import msvcrt  # type: ignore
    import os

    handle = win32file.CreateFile(
        str(filepath),
        win32file.GENERIC_READ,
        win32file.FILE_SHARE_DELETE
        | win32file.FILE_SHARE_READ
        | win32file.FILE_SHARE_WRITE,
        None,
        win32file.OPEN_EXISTING,
        0,
        None,
    )

    detached_handle = handle.Detach()

    file_descriptor = msvcrt.open_osfhandle(detached_handle, os.O_RDONLY)

    return file_descriptor


@contextlib.contextmanager
def open_no_lock(filepath, *args, **kwargs):
    file_descriptor = get_detached_file_descriptor(filepath)

    with open(file_descriptor, *args, **kwargs) as a_file:
        yield a_file


def make_a_valid_directory_name(proposed_directory_name):
    """In the case a field label can't be used as a file name the invalid
    characters can be dropped."""
    valid_chars = "-_.() {}{}".format(string.ascii_letters, string.digits)
    directory_name = "".join(c for c in proposed_directory_name if c in valid_chars)

    directory_name = directory_name.replace(" ", "-")

    return directory_name


# The control characters U+0000 to U+001F, such as tab and line feed. Windows
# does not allow them in names, and no platform allows U+0000 in a path.
_CONTROL_CHARACTERS = frozenset(chr(code) for code in range(0x20))

# The characters that encode_file_name encodes: those that separate or qualify
# path components on POSIX or Windows, those that Windows does not allow in
# names, and "%", so that an encoded name cannot equal a different value.
_ENCODED_NAME_CHARACTERS = frozenset('%/\\:*?"<>|') | _CONTROL_CHARACTERS


def encode_file_name(value: object) -> str:
    """Return a value, such as a patient ID, as a single file or folder name.

    Characters that could make the name refer to another folder, or that
    Windows does not allow in names, and the whole names ``.`` and ``..``, are
    replaced by ``%`` and their two-digit hexadecimal code, so ``../x``
    becomes ``..%2Fx`` and ``..`` becomes ``%2E%2E``. Different values give
    different names, and names without these characters are unchanged.

    Parameters
    ----------
    value
        The value to name the file or folder after, converted with ``str``.

    Returns
    -------
    str
        The file or folder name.
    """
    name = str(value)
    if name in (".", ".."):
        return name.replace(".", "%2E")

    return "".join(
        f"%{ord(character):02X}" if character in _ENCODED_NAME_CHARACTERS else character
        for character in name
    )
