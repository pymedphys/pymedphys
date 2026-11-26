# Copyright (C) 2026 PyMedPhys contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""The centre name from configuration is a single logfile path component."""

from pathlib import PurePath
from types import SimpleNamespace

from pymedphys._trf.manage.index import create_logfile_directory_name


def _directory(centre):
    delivery = SimpleNamespace(
        patient_id="P123",
        last_name="Sample",
        first_name="Test",
        qa_mode=False,
        field_id="F1",
        field_type="Static",
    )
    header = SimpleNamespace(
        field_label="Field",
        field_name="Beam",
        machine="LINAC1",
    )
    return create_logfile_directory_name(centre, delivery, header, "2026-11-26T010101")


def test_normal_centre_name_remains_unchanged():
    assert PurePath(_directory("SITE-ONE")).parts[0] == "SITE-ONE"


def test_centre_name_with_parent_navigation_stays_one_component():
    path = PurePath(_directory("../../outside"))
    assert len(path.parts) == 5
    assert path.parts[0] == "..%2F..%2Foutside"
    assert ".." not in path.parts


def test_parent_only_centre_name_is_escaped():
    assert PurePath(_directory("..")).parts[0] == "%2E%2E"


def test_centre_name_with_separator_does_not_add_path_levels():
    assert len(PurePath(_directory("Site/North")).parts) == 5
