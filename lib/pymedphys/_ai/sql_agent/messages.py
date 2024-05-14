import streamlit as st
import trio
from anthropic import AsyncAnthropic
from anthropic.types import MessageParam

import pymedphys

from .conversation import Messages, TaskRecordItem, call_assistant_in_conversation

USER = "user"
ASSISTANT = "assistant"


async def receive_user_messages_and_call_assistant_loop(
    tasks_record: list[TaskRecordItem],
    anthropic_client: AsyncAnthropic,
    connection: pymedphys.mosaiq.Connection,
    message_send_channel: trio.MemorySendChannel[MessageParam],
    message_receive_channel: trio.MemoryReceiveChannel[MessageParam],
    messages: Messages,
):
    async with trio.open_nursery() as nursery:
        try:
            print("Starting message receive loop...")

            async for item in message_receive_channel:
                print(f"User message received: {item}")

                # Messages should only be added to the messages object from
                # within this loop. User messages can only be appended after
                # assistant messages.
                if messages:
                    assert messages[-1]["role"] == ASSISTANT

                assert item["role"] == USER
                messages.append(item)
                write_message(role=USER, content=item["content"])

                assistant_message = await call_assistant_in_conversation(
                    nursery=nursery,
                    tasks_record=tasks_record,
                    anthropic_client=anthropic_client,
                    connection=connection,
                    message_send_channel=message_send_channel,
                    messages=messages,
                )

                print(f"Assistant message received: {assistant_message}")

                assert messages[-1]["role"] == USER
                assert assistant_message["role"] == ASSISTANT

                messages.append(assistant_message)
                write_message(role=ASSISTANT, content=assistant_message["content"])
        finally:
            print("Closing message receive loop...")


def write_message(role, content: str | list):
    with st.chat_message(role):
        st.markdown(message_content_as_plain_text(content))


def message_content_as_plain_text(content: str | list):
    if isinstance(content, str):
        return content

    results = [item["text"] for item in content if item["type"] == "text"]

    return "\n\n".join(results)
