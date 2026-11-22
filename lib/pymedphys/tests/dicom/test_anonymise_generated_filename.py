"""Generated legacy-anonymisation paths must not use malformed DICOM UIDs."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from pymedphys._dicom.anonymise.core import create_filename_from_dataset


def _synthetic_dataset(uid):
    return SimpleNamespace(
        SOPClassUID=SimpleNamespace(name="CT Image Storage"),
        SOPInstanceUID=uid,
    )


def test_valid_sop_instance_uid_keeps_existing_filename(tmp_path):
    result = create_filename_from_dataset(
        _synthetic_dataset("1.2.840.10008.1.2"), dirpath=tmp_path
    )

    assert Path(result) == tmp_path / "CT.1.2.840.10008.1.2.dcm"


@pytest.mark.parametrize(
    "invalid_uid",
    [
        "",
        "..",
        "../private",
        "1.2/../../outside",
        r"1.2\..\outside",
        "1.2.\n3",
        "1.2.3.",
        "1..2",
        "1.2.abc",
        "1.2.٣",
        "1." + "1" * 64,
    ],
)
def test_generated_filename_rejects_malformed_uid_without_echoing_it(
    tmp_path, invalid_uid
):
    with pytest.raises(
        ValueError, match="Invalid SOP Instance UID for generated filename"
    ) as caught:
        create_filename_from_dataset(
            _synthetic_dataset(invalid_uid), dirpath=tmp_path
        )

    assert invalid_uid not in str(caught.value) or not invalid_uid
    assert list(tmp_path.iterdir()) == []
