# Copyright (C) 2024 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import json
import os
import pathlib

import httpx
import trio
from anthropic import AsyncAnthropic
from anyio.from_thread import BlockingPortal
from pymedphys._imports import streamlit as st

import pymedphys
from pymedphys._ai.sql_agent.messages import (
    Messages,
    message_content_as_plain_text,
    receive_user_messages_and_call_assistant_loop,
    write_message,
)
from pymedphys._mosaiq.mock.server_from_bak import (
    start_mssql_docker_image_with_bak_restore,
)

from ._trio import get_streamlit_trio_portal

USER = "user"

# The default Anthropic plan limits API keys to only being able to call the API twice at the same time.
# Even this Mosaiq chat application tries to call the API up to 6 times concurrently (at least). This limiter
# constant is utilised to make it so that client side the API is only ever called 2 times at once. This limiter
# is not needed if your Anthropic plan does not have a max number of concurrent limit in place, and
# if your plan is not limited this application will run and work much faster without this limiter in place.
ANTHROPIC_API_LIMIT = 2


def main():
    _key_handling()

    portal = get_streamlit_trio_portal()
    messages = _get_messages()
    message_send_channel = _get_message_send_channel(portal=portal, messages=messages)

    with st.sidebar:
        _transcript_downloads(messages)

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

    for message in messages:
        write_message(message["role"], message["content"])

    new_message = st.chat_input()

    if new_message:
        portal.start_task_soon(
            message_send_channel.send, {"role": USER, "content": new_message}
        )

    with st.sidebar:
        st.write("---")
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


def _get_messages() -> Messages:
    if "messages" not in st.session_state:
        st.session_state.messages = []

    return st.session_state.messages


def _get_message_send_channel(
    portal: BlockingPortal, messages: Messages
) -> trio.MemorySendChannel:
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
                messages=messages,
            )

        portal.start_task_soon(assistant_calling_loop)

        st.session_state.message_send_channel = message_send_channel

    return st.session_state.message_send_channel


def _key_handling():
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


def _transcript_downloads(messages: Messages):
    transcript_items = [
        f"{message['role']}: {message_content_as_plain_text(message['content'])}"
        for message in messages
    ]

    plain_text_transcript = "\n\n".join(transcript_items)
    raw_transcript = json.dumps(messages, indent=2)

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
