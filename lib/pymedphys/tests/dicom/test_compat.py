import pytest
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import (
    ExplicitVRBigEndian,
    ExplicitVRLittleEndian,
    ImplicitVRLittleEndian,
)

from pymedphys._dicom.compat import ensure_transfer_syntax


def test_creates_file_meta_and_defaults_when_missing():
    """If file_meta and flags are missing, it should create them and default to Explicit VR Little Endian."""
    ds = Dataset()
    out = ensure_transfer_syntax(ds)

    assert out is ds, "Function should return the same Dataset instance"
    assert ds.file_meta.TransferSyntaxUID == ExplicitVRLittleEndian
    # Defaults should have been set on the dataset
    assert ds.is_implicit_VR is False
    assert ds.is_little_endian is True


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
