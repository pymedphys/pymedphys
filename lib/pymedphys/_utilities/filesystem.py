# Copyright (C) 2026 Jeffrey D. Cooney
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
import hashlib
import os
import string

# pylint: disable = import-error


def get_detached_file_descriptor(filepath):
    try:
        import win32file  # type: ignore
    except ImportError:
        return filepath

    import msvcrt  # type: ignore

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
_ON_WINDOWS = os.name == "nt"
_WINDOWS_MAX_COMPONENT_CODE_UNITS = 255

# Windows treats these basenames (including names with extensions) as devices.
# The superscript digits are also reserved for COM and LPT devices.
_WINDOWS_DEVICE_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
) | frozenset(
    f"{prefix}{digit}" for prefix in ("COM", "LPT") for digit in "123456789¹²³"
)


def _fits_windows_component(name: str) -> bool:
    """Check the Windows component limit in UTF-16 code units."""
    return (
        len(name.encode("utf-16-le", errors="surrogatepass")) // 2
        <= _WINDOWS_MAX_COMPONENT_CODE_UNITS
    )


def encode_file_name(value: object) -> str:
    """Return a value, such as a patient ID, as a single file or folder name.

    Characters that could make the name refer to another folder, or that
    Windows does not allow in names, and the whole names ``.`` and ``..``, are
    replaced by ``%`` and their two-digit hexadecimal code, so ``../x``
    becomes ``..%2Fx`` and ``..`` becomes ``%2E%2E``. Windows device
    basenames (such as ``CON`` or ``LPT1.txt``) are also escaped on Windows,
    but retain their original names on other systems for archive compatibility.
    If full escaping exceeds Windows' 255 UTF-16-code-unit component limit,
    compact escaping preserves case distinctions and long Unicode suffixes.
    Names still too long use a deterministic SHA-256-derived path component;
    this exceptional fallback is not reversible. Ordinary names are unchanged.

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

    encoded = "".join(
        f"%{ord(character):02X}" if character in _ENCODED_NAME_CHARACTERS else character
        for character in name
    )

    # Windows resolves reserved device names even with extensions or trailing
    # dots and spaces. The full encoding distinguishes case variants.
    # POSIX archives keep their existing paths.
    if _ON_WINDOWS:
        basename = encoded.split(".", maxsplit=1)[0].rstrip(" ")
        if basename.upper() in _WINDOWS_DEVICE_NAMES:
            escaped = "".join(f"%{ord(character):02X}" for character in encoded)

            if not _fits_windows_component(escaped):
                # Full encoding can exceed Windows' component limit for long
                # Unicode identifiers. Encode the device stem, unsafe
                # characters, noncanonical case variants, and trailing dots
                # or spaces, but leave other Unicode characters unchanged.
                stem_end = name.find(".")
                if stem_end == -1:
                    stem_end = len(name)
                trailing_start = len(name.rstrip(" ."))
                escaped = "".join(
                    f"%{ord(character):02X}"
                    if (
                        index < stem_end
                        or character in _ENCODED_NAME_CHARACTERS
                        or (index >= trailing_start and character in " .")
                        or character.upper().lower() != character
                    )
                    else character
                    for index, character in enumerate(name)
                )

                if not _fits_windows_component(escaped):
                    # A bounded, collision-resistant fallback avoids silently
                    # truncating distinct identifiers. Literal '%' is escaped
                    # by the normal path, so this prefix cannot collide with
                    # ordinary inputs.
                    digest = hashlib.sha256(
                        name.encode("utf-8", errors="surrogatepass")
                    ).hexdigest()
                    escaped = f"%FF{digest}"

            encoded = escaped

    return encoded
