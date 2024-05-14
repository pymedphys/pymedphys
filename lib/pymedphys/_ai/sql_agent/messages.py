from types import SimpleNamespace

import streamlit as st
import trio
from anthropic import AsyncAnthropic
from anthropic.types import MessageParam

import pymedphys

from .conversation import Messages, TaskRecordItem, call_assistant_in_conversation

USER = "user"
ASSISTANT = "assistant"


# TODO: Just initialise this within the app, use the task_counter to
# judge whether or not the top level streamlit app should continue to
# have a "waiting for items" spinner.
class AppContext(SimpleNamespace):
    task_counter: int
    tasks_record: list[TaskRecordItem]
    anthropic_client: AsyncAnthropic
    connection: pymedphys.mosaiq.Connection
    message_send_channel: trio.MemorySendChannel[MessageParam]
    message_receive_channel: trio.MemoryReceiveChannel[MessageParam]
    messages: Messages


async def receive_user_messages_and_call_assistant_loop(ctx: AppContext):
    async with trio.open_nursery() as nursery:
        try:
            print("Starting message receive loop...")

            async for item in ctx.message_receive_channel:
                print(f"User message received: {item}")

                # Messages should only be added to the messages object from
                # within this loop. User messages can only be appended after
                # assistant messages.
                if ctx.messages:
                    assert ctx.messages[-1]["role"] == ASSISTANT

                assert item["role"] == USER
                ctx.messages.append(item)
                write_message(role=USER, content=item["content"])

                assistant_message = await call_assistant_in_conversation(
                    nursery=nursery,
                    tasks_record=ctx.tasks_record,
                    anthropic_client=ctx.anthropic_client,
                    connection=ctx.connection,
                    message_send_channel=ctx.message_send_channel,
                    messages=ctx.messages,
                )

                print(f"Assistant message received: {assistant_message}")

                assert ctx.messages[-1]["role"] == USER
                assert assistant_message["role"] == ASSISTANT

                ctx.messages.append(assistant_message)
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
