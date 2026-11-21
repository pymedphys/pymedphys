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


"""Verify the SQL agent does not print prompts or model responses containing PHI."""

import asyncio
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("anthropic")
pytest.importorskip("trio")

TextBlock = importlib.import_module("anthropic.types").TextBlock
sql_agent_utilities = importlib.import_module("pymedphys._ai.sql_agent._utilities")
conversation = importlib.import_module("pymedphys._ai.sql_agent.conversation")
words_in_mouth_prompting = sql_agent_utilities.words_in_mouth_prompting


def test_sql_agent_prompts_and_responses_are_not_printed(capsys):
    patient_marker = "synthetic-private-patient-marker"
    answer_marker = "synthetic-private-model-answer"
    create = AsyncMock(
        return_value=SimpleNamespace(
            content=[TextBlock(type="text", text=answer_marker)]
        )
    )
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    previous_messages = [{"role": "user", "content": patient_marker}]

    response = asyncio.run(
        words_in_mouth_prompting(
            anthropic_client=client,
            model="synthetic-model",
            system_prompt="synthetic system",
            appended_user_prompt="please help",
            start_of_assistant_prompt="Answer: ",
            messages=previous_messages,
        )
    )

    assert response == "Answer:" + answer_marker
    sent = create.await_args.kwargs["messages"]
    assert sent[0]["content"] == patient_marker + "\n\nplease help"
    assert previous_messages[0]["content"] == patient_marker

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_sql_agent_tool_results_are_not_printed(capsys, monkeypatch):
    tool_prompt_marker = "synthetic-private-sql-tool-prompt"
    tool_result_marker = "synthetic-private-sql-tool-result"
    model_marker = "synthetic-private-conversation-reply"

    tool_use = SimpleNamespace(
        type="tool_use",
        name="mosaiq_sql_agent",
        id="tool-use-id",
        input={"sub_agent_prompt": tool_prompt_marker},
    )
    first_response = SimpleNamespace(
        stop_reason="tool_use",
        content=[SimpleNamespace(type="text", text=model_marker), tool_use],
        to_dict=lambda: {"role": "assistant", "content": [tool_use]},
    )
    final_response = SimpleNamespace(
        stop_reason="end_turn",
        content=[TextBlock(type="text", text="finished")],
        to_dict=lambda: {"role": "assistant", "content": "finished"},
    )
    create = AsyncMock(side_effect=[first_response, final_response])
    tool = AsyncMock(return_value=tool_result_marker)
    monkeypatch.setattr(
        conversation,
        "create_tools_mappings",
        lambda **_kwargs: {"mosaiq_sql_agent": tool},
    )
    messages = [{"role": "user", "content": "help"}]
    asyncio.run(
        conversation._conversation_with_tool_use(
            anthropic_client=SimpleNamespace(messages=SimpleNamespace(create=create)),
            connection=None,
            model="synthetic-model",
            system_prompt="synthetic system",
            tools=[],
            messages=messages,
        )
    )

    tool.assert_awaited_once_with(sub_agent_prompt=tool_prompt_marker)
    assert create.await_count == 2
    assert messages[2]["content"][0]["content"] == tool_result_marker

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
