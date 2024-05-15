import json
import os
import pathlib
import threading
import time

import httpx
import trio
from anthropic import AsyncAnthropic
from anyio.from_thread import BlockingPortal
from pymedphys._imports import streamlit as st
from streamlit.runtime.scriptrunner.script_run_context import (
    add_script_run_ctx,
    get_script_run_ctx,
)

import pymedphys
from pymedphys._mosaiq.server_from_bak import start_mssql_docker_image_with_bak_restore

from .sql_agent.messages import (
    message_content_as_plain_text,
    receive_user_messages_and_call_assistant_loop,
    write_message,
)

USER = "user"

ANTHROPIC_API_LIMIT = 2


def main():
    ctx = get_script_run_ctx()

    if "portal" not in st.session_state or "thread" not in st.session_state:
        thread = threading.Thread(target=create_event_loop_with_portal)

        st.session_state.thread = thread
        add_script_run_ctx(thread=st.session_state.thread, ctx=ctx)

        thread.start()

        while True:
            if "portal" not in st.session_state:
                time.sleep(0.1)
                continue

            break

    add_script_run_ctx(thread=st.session_state.thread, ctx=ctx)

    _main()


def create_event_loop_with_portal():
    trio.run(create_portal)


async def create_portal():
    async with BlockingPortal() as portal:
        st.session_state.portal = portal
        await portal.sleep_until_stopped()

    del st.session_state.portal


def _main():
    portal: BlockingPortal = st.session_state.portal

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

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        write_message(message["role"], message["content"])

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

    if "message_send_channel" not in st.session_state:
        message_send_channel, message_receive_channel = portal.call(
            trio.open_memory_channel, 10
        )

        async def assistant_calling_loop():
            await receive_user_messages_and_call_assistant_loop(
                tasks_record=[],
                anthropic_client=_async_anthropic(),
                connection=_mosaiq_connection(),
                message_send_channel=message_send_channel,
                message_receive_channel=message_receive_channel,
                messages=st.session_state.messages,
            )

        portal.start_task_soon(assistant_calling_loop)

        st.session_state.message_send_channel = message_send_channel

    new_message = st.chat_input()

    if new_message:
        portal.start_task_soon(
            st.session_state.message_send_channel.send,
            {"role": USER, "content": new_message},
        )

    with st.spinner("Waiting forever for potential AI and tool use responses"):
        portal.call(trio.sleep_forever)


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


def _transcript_downloads():
    transcript_items = [
        f"{message['role']}: {message_content_as_plain_text(message['content'])}"
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


if __name__ == "__main__":
    main()
