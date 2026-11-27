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

"""CT viewer's raw-pixel cache cannot be public or redirected by symlinks."""

import os
import stat

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._experimental.dicomrtvisualisation._private_cache import (
    open_private_ct_memmap,
)


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner-only file modes")
def test_new_and_existing_ct_cache_restrict_permissions(tmp_path):
    path = tmp_path / "volume.dat"
    mapped = open_private_ct_memmap(
        path, create=True, dtype=np.int16, shape=(2, 3)
    )
    mapped[:] = 17
    mapped.flush()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    path.chmod(0o644)
    reopened = open_private_ct_memmap(
        path, create=False, dtype=np.int16, shape=(2, 3)
    )
    assert int(reopened[0, 0]) == 17
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_existing_symlink_cannot_redirect_ct_cache_reads(tmp_path):
    target = tmp_path / "other-patient.dat"
    target.write_bytes(b"synthetic clinical bytes")
    link = tmp_path / "volume.dat"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks unavailable")

    with pytest.raises((ValueError, OSError)):
        open_private_ct_memmap(
            link, create=False, dtype=np.int16, shape=(3, 4)
        )
    assert target.read_bytes() == b"synthetic clinical bytes"


def test_existing_ct_cache_cannot_be_clobbered_by_create(tmp_path):
    path = tmp_path / "volume.dat"
    path.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        open_private_ct_memmap(
            path, create=True, dtype=np.uint8, shape=(100,)
        )
    assert path.read_bytes() == b"existing"
