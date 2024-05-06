import json
import os
import pathlib

import httpx
import streamlit as st
import trio
from anthropic import AsyncAnthropic
from anthropic.types.beta.tools import ToolsBetaContentBlock

import pymedphys
from pymedphys._mosaiq.server_from_bak import start_mssql_docker_image_with_bak_restore

from .sql_agent.messages import receive_user_messages_and_call_assistant_loop

USER = "user"

ANTHROPIC_API_LIMIT = 2


def main():
    trio.run(_async_main)


async def _async_main():
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    mssql_sa_password = os.getenv("MSSQL_SA_PASSWORD")

    if not anthropic_api_key:
        anthropic_api_key = st.text_input("Anthropic API key", type="password")
        os.environ["ANTHROPIC_API_KEY"] = anthropic_api_key

    if not mssql_sa_password:
        mssql_sa_password = st.text_input("MSSQL SA Password", type="password")
        os.environ["MSSQL_SA_PASSWORD"] = mssql_sa_password

    if not anthropic_api_key or not mssql_sa_password:
        st.write(
            "To continue, please make sure both of the `ANTHROPIC_API_KEY`"
            " and `MSSQL_SA_PASSWORD` environment variables are set"
        )
        st.stop()

    await _initialise_state()

    with st.sidebar:
        if st.button("Remove last message"):
            st.session_state.messages = st.session_state.messages[:-1]

        if st.button("Remove last two messages"):
            st.session_state.messages = st.session_state.messages[:-2]

        _transcript_downloads()

        bak_filepath = (
            pathlib.Path(
                st.text_input(".bak file path", value="~/mosaiq-data/db-dump.bak")
            )
            .expanduser()
            .resolve()
        )
        if st.button("Start demo MOSAIQ server from .bak file"):
            start_mssql_docker_image_with_bak_restore(
                bak_filepath=bak_filepath,
                mssql_sa_password=os.getenv("MSSQL_SA_PASSWORD"),
            )

    print(st.session_state.messages)

    for message in st.session_state.messages:
        _write_message(message["role"], message["content"])

    chat_input_disabled = False
    try:
        previous_message = st.session_state.messages[-1]
        if previous_message["role"] is USER:
            chat_input_disabled = True
    except IndexError:
        pass

    new_message = st.chat_input(disabled=chat_input_disabled)

    if new_message:
        await st.session_state.message_send_channel.send(
            {"role": USER, "content": new_message}
        )


async def _initialise_state():
    if "messages" not in st.session_state:
        st.session_state.messages = []

    if "message_send_channel" not in st.session_state:
        message_send_channel, message_receive_channel = trio.open_memory_channel(10)

        # NOTE: This is not the "trio way" but we need a nursery that
        # encompasses the streamlit rerun loop.

        # TODO: This actually is broken.
        nursery = await trio.open_nursery().__aenter__()

        async def runner():
            await receive_user_messages_and_call_assistant_loop(
                nursery=nursery,
                tasks_record=[],
                anthropic_client=_async_anthropic(),
                connection=_mosaiq_connection(),
                message_send_channel=message_send_channel,
                message_receive_channel=message_receive_channel,
                messages=st.session_state.messages,
                reload_visuals_callback=st.rerun,
            )

        nursery.start_soon(runner)

        st.session_state.message_send_channel = message_send_channel


@st.cache_resource
def _async_anthropic():
    # TODO: Make this configurable
    limits = httpx.Limits(max_connections=ANTHROPIC_API_LIMIT)

    return AsyncAnthropic(connection_pool_limits=limits, max_retries=10)


@st.cache_resource
def _mosaiq_connection():
    connection = pymedphys.mosaiq.connect(
        "localhost",
        database="PRACTICE",
        username="sa",
        password=os.environ["MSSQL_SA_PASSWORD"],
    )
    # Needed for multi-threading?
    # https://stackoverflow.com/a/41912528
    # connection._connection.autocommit(True)

    # For now just restrict to one database call at a time.

    return connection


def _write_message(role, content: str | list[ToolsBetaContentBlock]):
    with st.chat_message(role):
        st.markdown(_message_content_as_plain_text(content))


def _message_content_as_plain_text(content: str | list[ToolsBetaContentBlock]):
    if isinstance(content, str):
        return content

    results = [item["text"] for item in content if item["type"] == "text"]

    return "\n\n".join(results)


def _transcript_downloads():
    transcript_items = [
        f"{message['role']}: {_message_content_as_plain_text(message['content'])}"
        for message in st.session_state.messages
    ]

    plain_text_transcript = "\n\n".join(transcript_items)
    raw_transcript = json.dumps(st.session_state.messages, indent=2)

    st.download_button(
        "Download plain text transcript",
        plain_text_transcript,
        file_name="plain_text_transcript.txt",
    )
    st.download_button(
        "Download raw transcript", raw_transcript, file_name="raw_api_transcript.json"
    )


def _append_message(role, content):
    st.session_state.messages.append({"role": role, "content": content})


if __name__ == "__main__":
    main()
