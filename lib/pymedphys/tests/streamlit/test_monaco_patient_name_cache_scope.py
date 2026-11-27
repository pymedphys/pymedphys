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

"""Patient-identifying Monaco names are never placed in shared app caches."""

import ast
from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[2] / "_streamlit/utilities/monaco.py"
)


def test_monaco_patient_name_cache_is_session_scoped():
    syntax = ast.parse(SOURCE.read_text(encoding="utf-8"))
    function = next(
        node for node in syntax.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "read_monaco_patient_name"
    )
    assert any(
        isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and decorator.func.attr == "cache_data"
        and any(
            argument.arg == "scope"
            and isinstance(argument.value, ast.Constant)
            and argument.value.value == "session"
            for argument in decorator.keywords
        )
        for decorator in function.decorator_list
    )
