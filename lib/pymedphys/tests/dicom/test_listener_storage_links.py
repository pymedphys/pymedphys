# Copyright (C) 2026 PyMedPhys contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""An existing path link must not redirect received DICOM outside storage."""

from pymedphys._imports import pydicom, pytest
from pymedphys._dicom.connect.listen import hierarchical_dicom_storage_directory


def _dataset():
    dataset = pydicom.Dataset()
    dataset.PatientID = "P100"
    dataset.StudyInstanceUID = "1.2.3"
    dataset.SeriesInstanceUID = "1.2.3.4"
    return dataset


def test_hierarchy_without_links_remains_under_root(tmp_path):
    root = tmp_path / "dicom"
    root.mkdir()
    series = hierarchical_dicom_storage_directory(root, _dataset())
    assert series == root / "P100" / "1.2.3" / "1.2.3.4"


def test_hierarchy_rejects_linked_patient_folder(tmp_path):
    root = tmp_path / "dicom"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (root / "P100").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Directory symlinks are unavailable")
    with pytest.raises(ValueError, match="outside the storage directory"):
        hierarchical_dicom_storage_directory(root, _dataset())
    assert not (outside / "1.2.3").exists()


def test_hierarchy_rejects_linked_study_folder(tmp_path):
    root = tmp_path / "dicom"
    study = root / "P100"
    study.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (study / "1.2.3").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Directory symlinks are unavailable")
    with pytest.raises(ValueError, match="outside the storage directory"):
        hierarchical_dicom_storage_directory(root, _dataset())
