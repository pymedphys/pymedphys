# Copyright (C) 2026

"""Missing clinical input paths must not appear in exception messages."""

import pytest

from pymedphys._experimental.pseudonymisation import pseudonymise


def test_missing_pseudonymisation_input_does_not_disclose_patient_path(tmp_path):
    patient_id = "SYNTHETIC_PATIENT_123456"
    missing_path = tmp_path / patient_id / "study.dcm"

    with pytest.raises(FileNotFoundError) as captured:
        pseudonymise(missing_path)

    message = str(captured.value)
    assert "input path" in message
    assert patient_id not in message
    assert str(missing_path) not in message
