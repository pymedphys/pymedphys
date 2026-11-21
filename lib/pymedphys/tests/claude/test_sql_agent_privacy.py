"""Verify the SQL agent does not print prompts or model responses containing PHI."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("anthropic")
pytest.importorskip("trio")
from anthropic.types import TextBlock

from pymedphys._ai.sql_agent._utilities import words_in_mouth_prompting


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
