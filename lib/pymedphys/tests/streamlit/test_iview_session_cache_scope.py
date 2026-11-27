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

"""Ensure iView patient and image metadata are not globally cached."""

import ast
from pathlib import Path

from pymedphys._imports import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "path, function",
    [
        (
            "_experimental/streamlit/utilities/dbf.py",
            "get_dbf_table",
        ),
        (
            "_experimental/streamlit/utilities/iview/_dbf.py",
            "_dbf_to_pandas_with_cache",
        ),
        (
            "_experimental/streamlit/apps/iviewdb.py",
            "get_files_for_extension",
        ),
    ],
)
def test_iview_patient_cache_is_session_scoped(path, function):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    item = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function
    )
    assert any(
        isinstance(dec, ast.Call)
        and isinstance(dec.func, ast.Attribute)
        and dec.func.attr == "cache_data"
        and any(
            arg.arg == "scope"
            and isinstance(arg.value, ast.Constant)
            and arg.value.value == "session"
            for arg in dec.keywords
        )
        for dec in item.decorator_list
    )
