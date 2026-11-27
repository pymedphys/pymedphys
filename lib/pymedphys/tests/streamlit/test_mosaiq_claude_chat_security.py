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

"""Protect secrets supplied to experimental MOSAIQ chat by a browser session."""

import ast
from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[2]
    / "_experimental/streamlit/apps/mosaiq_claude_chat/app.py"
)


def test_chat_never_writes_session_api_keys_into_process_environment():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                assert not (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Attribute)
                    and isinstance(target.value.value, ast.Name)
                    and target.value.value.id == "os"
                    and target.value.attr == "environ"
                ), "A session credential must not be stored in os.environ"


def test_anthropic_client_receives_explicit_key_and_uses_session_cache():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    target = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef)
        and node.name == "_async_anthropic"
    )
    assert any(
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "AsyncAnthropic"
        and any(key.arg == "api_key" for key in call.keywords)
        for call in ast.walk(target)
    )
    assert any(
        isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and decorator.func.attr == "cache_resource"
        and any(
            keyword.arg == "scope"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value == "session"
            for keyword in decorator.keywords
        )
        for decorator in target.decorator_list
    )
