# Copyright (C) 2026 Jeff (jdotc1)

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Privacy regression: SQL agent tool events must not reach stdout/stderr."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

# This private SQL-agent test requires the optional Anthropic SDK and Trio.
pytest.importorskip("anthropic")
pytest.importorskip("trio")

from pymedphys._ai.sql_agent import _utilities, conversation


def test_sql_agent_does_not_print_tool_call_or_clinical_result(monkeypatch, capsys):
    patient_marker = "synthetic-clinical-record-contents"
    prompt_marker = "synthetic-sensitive-tool-argument"
    tool_call = SimpleNamespace(
        type="tool_use",
        name="mosaiq_sql_agent",
        input={"sub_agent_prompt": prompt_marker},
        id="toolu_synthetic",
    )
    first = SimpleNamespace(
        stop_reason="tool_use",
        content=[tool_call],
        to_dict=lambda: {"role": "assistant", "content": [{"type": "tool_use"}]},
    )
    second = SimpleNamespace(
        stop_reason="end_turn",
        content=[],
        to_dict=lambda: {
            "role": "assistant",
            "content": [{"type": "text", "text": "done"}],
        },
    )
    create = AsyncMock(side_effect=[first, second])
    client = SimpleNamespace(messages=SimpleNamespace(create=create))

    async def fake_sql_tool(sub_agent_prompt):
        assert sub_agent_prompt == prompt_marker
        return patient_marker

    monkeypatch.setattr(
        conversation,
        "create_tools_mappings",
        lambda **_kwargs: {"mosaiq_sql_agent": fake_sql_tool},
    )
    messages = [{"role": "user", "content": "synthetic request"}]
    asyncio.run(
        conversation._conversation_with_tool_use(
            anthropic_client=client,
            connection=None,
            model="synthetic",
            system_prompt="synthetic",
            tools=[],
            messages=messages,
        )
    )

    assert create.await_count == 2
    assert messages[2]["content"][0]["content"] == patient_marker
    assert capsys.readouterr() == ("", "")


def test_nested_sql_agent_does_not_print_transcript_or_generated_sql(capsys):
    transcript_marker = "synthetic-clinical-transcript-marker"
    generated_sql = (
        "SELECT PatientName FROM Patient "
        "WHERE PatientId = 'synthetic-clinical-sql-marker'"
    )
    response = SimpleNamespace(
        content=[_utilities.TextBlock(type="text", text=generated_sql)]
    )
    create = AsyncMock(return_value=response)
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    messages = [{"role": "user", "content": transcript_marker}]

    result = asyncio.run(
        _utilities.words_in_mouth_prompting(
            anthropic_client=client,
            model="synthetic",
            system_prompt="synthetic",
            appended_user_prompt="generate synthetic SQL",
            start_of_assistant_prompt="<thinking>",
            messages=messages,
        )
    )

    assert create.await_count == 1
    assert transcript_marker in create.await_args.kwargs["messages"][0]["content"]
    assert generated_sql in result
    assert messages == [{"role": "user", "content": transcript_marker}]
    assert capsys.readouterr() == ("", "")
