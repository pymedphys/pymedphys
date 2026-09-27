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

"""Unit tests for generating the mock Mosaiq database."""

import sys
import types

from pymedphys._imports import pytest

from pymedphys._mosaiq.mock import generate


@pytest.mark.parametrize(
    "database", ["invalid-name", "name; DROP DATABASE master", "1database", ""]
)
def test_invalid_database_name_fails_before_connecting(monkeypatch, database):
    def unexpected_connect(*_args, **_kwargs):
        pytest.fail("Invalid database names must not open a server connection")

    fake_pymssql = types.SimpleNamespace(connect=unexpected_connect)
    monkeypatch.setitem(sys.modules, "pymssql", fake_pymssql)

    with pytest.raises(ValueError, match="Invalid database identifier"):
        generate.create_test_db(database)
