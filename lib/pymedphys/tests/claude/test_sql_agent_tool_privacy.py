"""Privacy regression: SQL agent tool events must not reach stdout/stderr."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("anthropic")
pytest.importorskip("trio")

from pymedphys._ai.sql_agent import conversation


def test_sql_agent_does_not_print_tool_call_or_clinical_result(monkeypatch, capsys):
    patient_marker = "synthetic-clinical-record-contents"
    prompt_marker = "synthetic-sensitive-tool-argument"
    tool_call = SimpleNamespace(
        type="tool_use", name="mosaiq_sql_agent",
        input={"sub_agent_prompt": prompt_marker}, id="toolu_synthetic",
    )
    first = SimpleNamespace(
        stop_reason="tool_use", content=[tool_call],
        to_dict=lambda: {"role": "assistant", "content": [{"type": "tool_use"}]},
    )
    second = SimpleNamespace(
        stop_reason="end_turn", content=[],
        to_dict=lambda: {"role": "assistant", "content": [{"type": "text", "text": "done"}]},
    )
    create = AsyncMock(side_effect=[first, second])
    client = SimpleNamespace(messages=SimpleNamespace(create=create))

    async def fake_sql_tool(sub_agent_prompt):
        assert sub_agent_prompt == prompt_marker
        return patient_marker

    monkeypatch.setattr(
        conversation, "create_tools_mappings",
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
