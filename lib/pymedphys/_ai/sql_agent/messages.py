from typing import Callable

import trio
from anthropic import AsyncAnthropic
from anthropic.types import MessageParam

import pymedphys

from .conversation import Messages, TaskRecordItem, call_assistant_in_conversation

USER = "user"
ASSISTANT = "assistant"


async def receive_user_messages_and_call_assistant_loop(
    nursery: trio.Nursery,
    tasks_record: list[TaskRecordItem],
    anthropic_client: AsyncAnthropic,
    connection: pymedphys.mosaiq.Connection,
    message_send_channel: trio.MemorySendChannel[MessageParam],
    message_receive_channel: trio.MemoryReceiveChannel[MessageParam],
    messages: Messages,
    reload_visuals_callback: Callable,
):
    async for item in message_receive_channel:
        # Messages should only be added to the messages object from
        # within this loop. User messages can only be appended after
        # assistant messages.
        if messages:
            assert messages[-1]["role"] == ASSISTANT

        messages.append(item)
        reload_visuals_callback()

        await call_assistant_in_conversation(
            nursery=nursery,
            tasks_record=tasks_record,
            anthropic_client=anthropic_client,
            connection=connection,
            message_send_channel=message_send_channel,
            messages=messages,
        )
