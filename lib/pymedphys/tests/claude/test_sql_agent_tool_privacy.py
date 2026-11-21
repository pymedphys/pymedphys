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
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

# This private SQL-agent test requires the optional Anthropic SDK and Trio.
pytest.importorskip("anthropic")
pytest.importorskip("trio")

from pymedphys._ai.sql_agent import _pipeline, _utilities, conversation


def test_sql_agent_does_not_print_tool_call_or_clinical_result(
    monkeypatch, capsys, caplog
):
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
    caplog.set_level(logging.INFO, logger=conversation.__name__)
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
    assert "MOSAIQ SQL agent requested 1 tool call(s)" in caplog.text
    assert patient_marker not in caplog.text
    assert prompt_marker not in caplog.text


def test_nested_sql_agent_does_not_print_transcript_or_generated_sql(
    capsys, caplog
):
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
    caplog.set_level(logging.DEBUG, logger=_utilities.__name__)

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
    assert "MOSAIQ SQL prompt step completed (message_count=2)" in caplog.text
    assert transcript_marker not in caplog.text
    assert generated_sql not in caplog.text


def test_sql_pipeline_logs_counts_without_query_or_result(monkeypatch, caplog):
    sql_marker = "SELECT 'synthetic-sensitive-query-marker'"
    result_marker = "synthetic-sensitive-result-marker"

    async def fake_retrieval(**_kwargs):
        return [(sql_marker, result_marker)]

    async def fake_vote(**_kwargs):
        return [0]

    async def gather_in_order(functions):
        return [await function() for function in functions]

    monkeypatch.setattr(
        _pipeline, "get_single_set_of_query_result_pairs", fake_retrieval
    )
    monkeypatch.setattr(_pipeline, "get_top_k_query_ids", fake_vote)
    monkeypatch.setattr(_pipeline, "gather", gather_in_order)
    monkeypatch.setattr(_pipeline, "NUM_PARALLEL_QUERY_CREATION_AGENTS", 1)
    monkeypatch.setattr(_pipeline, "NUM_PARALLEL_QUERY_VOTER_AGENTS", 1)
    caplog.set_level(logging.INFO, logger=_pipeline.__name__)

    result = asyncio.run(
        _pipeline.sql_tool_pipeline(
            anthropic_client=None,
            connection=None,
            messages=[{"role": "user", "content": "synthetic"}],
            sub_agent_prompt="synthetic",
        )
    )

    assert sql_marker in result
    assert result_marker in result
    assert "candidate_queries=1, selected_queries=1" in caplog.text
    assert sql_marker not in caplog.text
    assert result_marker not in caplog.text


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (RuntimeError(208, "synthetic-sensitive-database-message"), "208"),
        (RuntimeError("synthetic-sensitive-database-message"), "unavailable"),
    ],
)
def test_sql_query_failure_logs_only_safe_error_metadata(
    monkeypatch, caplog, error, expected_code
):
    query_marker = "SELECT 'synthetic-sensitive-query-marker'"
    error_marker = "synthetic-sensitive-database-message"

    async def fake_execute_query(_connection, _query):
        raise error

    monkeypatch.setattr(_pipeline, "execute_query", fake_execute_query)
    caplog.set_level(logging.WARNING, logger=_pipeline.__name__)

    result = asyncio.run(
        _pipeline._execute_query_with_truncated_string_result(
            connection=None, query=query_marker
        )
    )

    assert error_marker in result  # Keep failure details available to the caller.
    assert "MOSAIQ SQL query failed" in caplog.text
    assert "error_type=RuntimeError" in caplog.text
    assert f"error_code={expected_code}" in caplog.text
    assert error_marker not in caplog.text
    assert query_marker not in caplog.text
