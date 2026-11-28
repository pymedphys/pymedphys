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

"""Monaco patient IDs are literal directory suffixes, never glob patterns."""

from pymedphys._imports import pytest

pytest.importorskip("streamlit")

from pymedphys._streamlit.utilities import monaco  # noqa: E402


def test_patient_id_glob_characters_do_not_select_unrelated_patient(tmp_path):
    (tmp_path / "clinic~PAT123" / "plan").mkdir(parents=True)
    (tmp_path / "clinic~PAT456" / "plan").mkdir(parents=True)

    assert monaco.find_monaco_patient_plans(tmp_path, "PAT*") == []
    assert monaco.find_monaco_patient_plans(tmp_path, "PAT[123]") == []
    assert monaco.find_monaco_patient_plans(tmp_path, "../PAT123") == []
    assert monaco.find_monaco_patient_plans(tmp_path, "PAT123") == [
        tmp_path / "clinic~PAT123" / "plan"
    ]


def test_literal_bracketed_id_matches_only_its_own_plan_folder(tmp_path):
    literal_plan = tmp_path / "clinic~PAT[1]" / "plan"
    decoy_plan = tmp_path / "clinic~PAT1" / "plan"
    literal_plan.mkdir(parents=True)
    decoy_plan.mkdir(parents=True)

    assert monaco.find_monaco_patient_plans(tmp_path, "PAT[1]") == [
        literal_plan
    ]
