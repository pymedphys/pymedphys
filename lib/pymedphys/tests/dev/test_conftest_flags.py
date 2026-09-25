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

"""The selection rules behind the conftest's opt-in test flags."""

import pathlib

from pymedphys import _config as pmp_config
from pymedphys import conftest
from pymedphys._data import download


def _reason(markers, *, only=(), include=(), run_all=False):
    return conftest.skip_reason(
        set(markers), only=set(only), include=set(include), run_all=run_all
    )


def test_opt_in_markers_are_skipped_by_default():
    assert _reason(["slow"]) is not None
    assert _reason(["mosaiqdb"]) is not None
    assert _reason(["anthropic_key"]) is not None
    assert _reason([]) is None
    assert _reason(["pydicom"]) is None


def test_include_flags_add_to_the_default_selection():
    assert _reason(["slow"], include=["slow"]) is None
    assert _reason([], include=["slow"]) is None
    assert _reason(["mosaiqdb"], include=["slow"]) is not None


def test_only_flags_select_their_marker():
    assert _reason(["slow"], only=["slow"]) is None
    assert _reason([], only=["slow"]) is not None
    assert _reason(["pydicom"], only=["pydicom"]) is None
    assert _reason([], only=["pydicom"]) is not None


def test_several_only_flags_select_the_union():
    only = ["slow", "mosaiqdb"]

    assert _reason(["slow"], only=only) is None
    assert _reason(["mosaiqdb"], only=only) is None
    assert _reason(["slow", "mosaiqdb"], only=only) is None
    assert _reason([], only=only) is not None


def test_only_flag_still_needs_the_opt_in_for_other_markers():
    # A slow test that also needs the database stays skipped unless the
    # database was requested too.
    assert _reason(["slow", "mosaiqdb"], only=["slow"]) is not None
    assert _reason(["slow", "mosaiqdb"], only=["slow"], include=["mosaiqdb"]) is None


def test_all_runs_everything():
    assert _reason(["slow", "mosaiqdb", "anthropic_key"], run_all=True) is None


def test_the_suite_does_not_use_the_real_home_directory():
    real_home = conftest.REAL_HOME
    assert real_home is not None

    temporary_home = pathlib.Path.home().resolve()
    assert temporary_home != real_home.resolve()

    # Windows can place temporary directories inside the real user profile.
    assert pmp_config.get_config_dir().resolve() == temporary_home / ".pymedphys"


def test_the_data_cache_is_still_shared():
    assert download.get_data_dir().resolve() == conftest.SHARED_DATA_DIR.resolve()
