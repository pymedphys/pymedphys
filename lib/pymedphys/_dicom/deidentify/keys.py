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

"""De-identification keys and the values derived from them (design decision D-004).

A key is 256 bits from a cryptographically secure generator. Each value that
de-identification generates from source data, such as a replacement UID
(D-003), is an HMAC-SHA256 of that data under the key in a named domain. The
same key therefore gives the same values in every run, while different
domains and different keys give unrelated values.

Anyone who holds a key can recompute the values for candidate source data,
and identifiers such as medical record numbers have few enough candidates to
try them all. A project key is therefore as sensitive as a crosswalk: keep it
with the custodian, outside output and QC directories, and never give it to
recipients.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import hmac
import json
import os
import pathlib
import secrets
import warnings
from collections.abc import Iterable

from pymedphys._config import config_dir_path

KEY_BYTES = 32
KEY_FILE_FORMAT = "pymedphys-deid-key/1"
# Framed first in every derivation, so a future derivation can take a new
# version without reproducing any value of this one.
DERIVATION_VERSION = b"pymedphys-deid/1"
# The domains values are derived in. Later derivations, such as patient
# identifiers and date offsets, add their own.
DOMAINS = frozenset({"key-id", "patient", "uid"})

# POSIX honours the owner-only mode a key file is created with. Elsewhere,
# such as on Windows, access depends on the directory's access control.
_OWNER_ONLY_MODE_ENFORCED = os.name == "posix"


class DeidKeyError(ValueError):
    """A key, or a key file, that cannot be used."""


def _frame(value: str | bytes) -> bytes:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return len(data).to_bytes(4, "big") + data


@dataclasses.dataclass(frozen=True, repr=False, eq=False)
class DeidKey:
    """A 256-bit de-identification key.

    Its ``repr`` shows only :attr:`key_id`, so a key does not reach logs or
    reports through formatting. It pickles, so worker processes can receive
    it.

    Attributes
    ----------
    secret : bytes
        The 32 bytes of the key.

    Raises
    ------
    DeidKeyError
        If ``secret`` is not exactly 32 bytes.

    Examples
    --------
    >>> key = DeidKey.generate()
    >>> len(key.secret)
    32
    """

    secret: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.secret, bytes) or len(self.secret) != KEY_BYTES:
            raise DeidKeyError(f"a key must be exactly {KEY_BYTES} bytes")

    @classmethod
    def generate(cls) -> DeidKey:
        """Return a new key from the operating system's secure generator."""
        return cls(secrets.token_bytes(KEY_BYTES))

    def derive(self, domain: str, *parts: str | bytes) -> bytes:
        """Return the 32-byte HMAC-SHA256 of ``parts`` in ``domain``.

        The message is the derivation version, the domain, and each part,
        each preceded by its length as four big-endian bytes, so no two
        different sequences of parts give the same message. Text is encoded
        as UTF-8.

        Parameters
        ----------
        domain : str
            One of :data:`DOMAINS`, such as ``"uid"``.
        *parts : str or bytes
            The data to derive from.

        Raises
        ------
        ValueError
            If ``domain`` is not one of :data:`DOMAINS`.
        """
        if domain not in DOMAINS:
            raise ValueError("unknown derivation domain")
        message = b"".join(
            _frame(part) for part in (DERIVATION_VERSION, domain, *parts)
        )
        return hmac.new(self.secret, message, hashlib.sha256).digest()

    @property
    def key_id(self) -> str:
        """A non-secret identifier for the key, as 32 hexadecimal digits.

        It is the first 16 bytes of the key's derivation in the ``"key-id"``
        domain, so reports can record which key was used without revealing
        it.
        """
        return self.derive("key-id")[:16].hex()

    def __repr__(self) -> str:
        return f"DeidKey(key_id={self.key_id!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DeidKey):
            return NotImplemented
        return hmac.compare_digest(self.secret, other.secret)

    def __hash__(self) -> int:
        return hash(self.key_id)


def _refuse_location(
    path: pathlib.Path, protected_dirs: Iterable[str | os.PathLike]
) -> None:
    if path.is_relative_to(config_dir_path().resolve()):
        raise DeidKeyError(
            "refusing to write a key inside the PyMedPhys configuration directory"
        )
    for directory in protected_dirs:
        if path.is_relative_to(pathlib.Path(directory).resolve()):
            raise DeidKeyError("refusing to write a key inside a protected directory")


def write_key_file(
    path: str | os.PathLike,
    key: DeidKey,
    *,
    protected_dirs: Iterable[str | os.PathLike] = (),
) -> pathlib.Path:
    """Write ``key`` to a new file that only its owner can read.

    The file is JSON holding :data:`KEY_FILE_FORMAT`, the key's identifier,
    and the key in base64. It is created exclusively, so an existing file or
    symbolic link at ``path`` is never overwritten or followed. On POSIX it
    has mode ``0o600``; elsewhere a warning says that access depends on the
    directory's access control.

    Parameters
    ----------
    path : str or os.PathLike
        The new file, in a location only the custodian can read.
    key : DeidKey
    protected_dirs : iterable of str or os.PathLike, optional
        Directories the file must not be inside, such as the output and QC
        directories of a run. The PyMedPhys configuration directory is
        always protected.

    Returns
    -------
    pathlib.Path
        The resolved path of the new file.

    Raises
    ------
    DeidKeyError
        If ``path`` is inside a protected directory or already exists.
    OSError
        If the file cannot be created, for example because its directory
        does not exist.
    """
    given = pathlib.Path(path).absolute()
    # Resolve the directory but not the file name, so that a symbolic link at
    # the file name is refused by the exclusive create, never followed.
    resolved = given.parent.resolve() / given.name
    _refuse_location(resolved, protected_dirs)
    text = json.dumps(
        {
            "format": KEY_FILE_FORMAT,
            "key_id": key.key_id,
            "key": base64.b64encode(key.secret).decode("ascii"),
        },
        indent=1,
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(resolved, flags, 0o600)
    except FileExistsError as error:
        raise DeidKeyError("the key file already exists") from error
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
            file.write(text + "\n")
    except BaseException:
        resolved.unlink(missing_ok=True)
        raise
    if not _OWNER_ONLY_MODE_ENFORCED:
        warnings.warn(
            "this platform does not apply owner-only file modes, so access to "
            "the key file depends on its directory's access control",
            UserWarning,
            stacklevel=2,
        )
    return resolved


def read_key_file(path: str | os.PathLike) -> DeidKey:
    """Read a key written by :func:`write_key_file`.

    Error messages never include the key.

    Raises
    ------
    DeidKeyError
        If the file cannot be read, is not a :data:`KEY_FILE_FORMAT` file,
        does not hold a 32-byte key in base64, or records an identifier that
        does not match its key.
    """
    try:
        document = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise DeidKeyError("the key file could not be read") from error
    if (
        not isinstance(document, dict)
        or document.keys() != {"format", "key_id", "key"}
        or document["format"] != KEY_FILE_FORMAT
    ):
        raise DeidKeyError(f"the file is not a {KEY_FILE_FORMAT} file")
    try:
        # Invalid base64 and non-ASCII text raise ValueError, of which
        # DeidKeyError is a subclass; other types raise TypeError.
        key = DeidKey(base64.b64decode(document["key"], validate=True))
    except (TypeError, ValueError):
        raise DeidKeyError("the file does not hold a 32-byte key in base64") from None
    if not hmac.compare_digest(str(document["key_id"]), key.key_id):
        raise DeidKeyError("the recorded key identifier does not match the key")
    return key
