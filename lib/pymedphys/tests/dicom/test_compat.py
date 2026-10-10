# Copyright (C) 2025-2026 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import io
import warnings

import pytest
from pydicom import dcmread, dcmwrite
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import (
    ExplicitVRBigEndian,
    ExplicitVRLittleEndian,
    ImplicitVRLittleEndian,
)

from pymedphys._dicom.compat import ensure_transfer_syntax


def test_creates_file_meta_and_defaults_when_missing():
    """If file_meta and flags are missing, it should create file_meta and default to Implicit VR Little Endian."""
    ds = Dataset()
    out = ensure_transfer_syntax(ds)

    assert out is ds, "Function should return the same Dataset instance"
    assert ds.file_meta.TransferSyntaxUID == ImplicitVRLittleEndian


def test_does_not_set_deprecated_encoding_flags():
    """Only the Transfer Syntax UID is written: pydicom 3 deprecates the flags and pydicom 4 removes them."""
    ds = Dataset()
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        ensure_transfer_syntax(ds)

    assert ds.file_meta.TransferSyntaxUID == ImplicitVRLittleEndian


# pydicom 3 deprecates the legacy flags that these tests set.
LEGACY_FLAGS = pytest.mark.filterwarnings(
    "ignore:.*is_(implicit_VR|little_endian)' will be removed in v4:DeprecationWarning"
)


@LEGACY_FLAGS
@pytest.mark.parametrize(
    "is_implicit,is_little_endian,expected_uid",
    [
        (True, True, ImplicitVRLittleEndian),
        (False, True, ExplicitVRLittleEndian),
        (False, False, ExplicitVRBigEndian),
    ],
)
def test_sets_transfer_syntax_when_missing_and_flags_known(
    is_implicit, is_little_endian, expected_uid
):
    """When TransferSyntaxUID is missing, choose it from the (is_implicit_VR, is_little_endian) flags."""
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.is_implicit_VR = is_implicit
    ds.is_little_endian = is_little_endian

    out = ensure_transfer_syntax(ds)

    assert out is ds
    assert ds.file_meta.TransferSyntaxUID == expected_uid


@LEGACY_FLAGS
def test_does_not_overwrite_existing_transfer_syntax():
    """If TransferSyntaxUID already exists, it must not be changed even if flags are inconsistent."""
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    # Set a specific UID that is intentionally inconsistent with the flags below
    ds.file_meta.TransferSyntaxUID = ImplicitVRLittleEndian
    ds.is_implicit_VR = False
    ds.is_little_endian = (
        False  # Flags suggest ExplicitVRBigEndian, but we should not overwrite
    )

    before_uid = ds.file_meta.TransferSyntaxUID
    out = ensure_transfer_syntax(ds)
    after_uid = ds.file_meta.TransferSyntaxUID

    assert out is ds
    assert after_uid == before_uid, "Existing TransferSyntaxUID should be preserved"


@LEGACY_FLAGS
def test_unsupported_combo_raises_keyerror():
    """
    The (True, False) combo corresponds to Implicit VR Big Endian (retired),
    which is intentionally not in the map; expect a KeyError when UID is missing.
    """
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.is_implicit_VR = True
    ds.is_little_endian = False

    with pytest.raises(KeyError):
        ensure_transfer_syntax(ds)


def _read_without_file_meta(is_implicit, is_little_endian):
    """Encode a dataset with no file meta information, then decode it."""
    ds = Dataset()
    ds.PatientName = "Test^Patient"
    buffer = io.BytesIO()
    dcmwrite(buffer, ds, implicit_vr=is_implicit, little_endian=is_little_endian)
    buffer.seek(0)

    return dcmread(buffer, force=True)


@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize(
    "is_implicit,is_little_endian,expected_uid",
    [
        (True, True, ImplicitVRLittleEndian),
        (False, True, ExplicitVRLittleEndian),
        (False, False, ExplicitVRBigEndian),
    ],
)
def test_file_without_file_meta_keeps_its_encoding(
    is_implicit, is_little_endian, expected_uid
):
    """A file read without file meta keeps the encoding it was read with.

    pydicom 4 removes the legacy flags, so its original encoding decides.
    """
    ds = _read_without_file_meta(is_implicit, is_little_endian)
    assert ds.original_encoding == (is_implicit, is_little_endian)

    ensure_transfer_syntax(ds)

    assert ds.file_meta.TransferSyntaxUID == expected_uid
