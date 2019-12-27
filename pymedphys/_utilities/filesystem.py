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


def get_detached_file_descriptor(filepath):
    try:
        import win32file  # pylint: disable = import-error

        has_win32file = True
    except ImportError:
        has_win32file = False

    if has_win32file:
        import os
        import msvcrt  # pylint: disable = import-error

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

    return filepath


@contextlib.contextmanager
def open_no_lock(filepath, *args, **kwargs):
    file_descriptor = get_detached_file_descriptor(filepath)

    try:
        a_file = open(file_descriptor, *args, **kwargs)
        yield a_file
    finally:
        a_file.close()


def make_a_valid_directory_name(proposed_directory_name):
    """In the case a field label can't be used as a file name the invalid
    characters can be dropped."""
    valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
    directory_name = "".join(c for c in proposed_directory_name if c in valid_chars)

    directory_name = directory_name.replace(" ", "-")

    return directory_name
