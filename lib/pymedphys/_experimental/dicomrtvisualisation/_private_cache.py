# Copyright (C) 2026 PyMedPhys contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Open clinical CT pixel caches with restricted permissions and no links."""

import os
import stat

import numpy as np


def open_private_ct_memmap(path, *, dtype, shape, create):
    """Create or read a raw CT cache without following a destination symlink.

    Newly created caches have owner-only permissions. Existing regular-file
    caches are restricted to owner-only access before mapping on POSIX.
    """
    flags = (os.O_RDWR | os.O_CREAT | os.O_EXCL) if create else os.O_RDONLY
    flags |= getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    if os.path.islink(path):
        raise ValueError("Linked CT cache files are not permitted")

    fd = os.open(path, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("CT cache must be a regular file")
        if os.name == "posix":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "r+b" if create else "rb") as stream:
            fd = -1
            return np.memmap(
                stream, dtype=dtype, mode="w+" if create else "r", shape=shape
            )
    finally:
        if fd >= 0:
            os.close(fd)
