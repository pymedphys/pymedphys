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

import httpx
import trio
from anthropic import AsyncAnthropic
from pymedphys._imports import streamlit as st

import pymedphys
from pymedphys._ai.sql_agent.conversation import recursively_append_message_responses
from pymedphys._mosaiq.mock.from_csv import (
    DATABASE_NAME,
    create_db_with_tables_from_csv,
)
from pymedphys._mosaiq.mock.utilities import SA_PASSWORD, SA_USER

USER = "user"

# The default Anthropic plan limits API keys to only being able to call the API twice at the same time.
# Even this Mosaiq chat application tries to call the API up to 6 times concurrently (at least). This limiter
# constant is utilised to make it so that client side the API is only ever called 2 times at once. This limiter
# is not needed if your Anthropic plan does not have a max number of concurrent limit in place, and
# if your plan is not limited this application will run and work much faster without this limiter in place.
ANTHROPIC_API_LIMIT = 2


def main():
    _key_handling()

    _initialise_state()

    with st.sidebar:
        if st.button("Fill database with CSV records"):
            create_db_with_tables_from_csv()

        anthropic_api_limit = int(
            st.number_input("Anthropic API concurrency limit", value=2)
        )

        if st.button("Remove last message"):
            st.session_state.messages = st.session_state.messages[:-1]

        if st.button("Remove last two messages"):
            st.session_state.messages = st.session_state.messages[:-2]

        _transcript_downloads()

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
        _append_message(USER, new_message)
        _write_message(USER, new_message)

    try:
        most_recent_message = st.session_state.messages[-1]
    except IndexError:
        return

    if most_recent_message["role"] is not USER:
        return

    trio.run(
        recursively_append_message_responses,
        _async_anthropic(anthropic_api_limit),
        _mosaiq_connection(),
        st.session_state.messages,
    )

    st.rerun()


@st.cache_resource
def _async_anthropic(anthropic_api_limit: int):
    limits = httpx.Limits(max_connections=anthropic_api_limit)

    return AsyncAnthropic(connection_pool_limits=limits, max_retries=10)


@st.cache_resource
def _mosaiq_connection():
    connection = pymedphys.mosaiq.connect(
        "localhost",
        database=DATABASE_NAME,
        username=SA_USER,
        password=SA_PASSWORD,
    )
    # Needed for multi-threading?
    # https://stackoverflow.com/a/41912528
    # connection._connection.autocommit(True)

    # For now just restrict to one database call at a time.

    return connection


def _initialise_state():
    if "messages" not in st.session_state:
        st.session_state.messages = []


def _key_handling():
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")

    if not anthropic_api_key:
        anthropic_api_key = st.text_input("Anthropic API key", type="password")
        os.environ["ANTHROPIC_API_KEY"] = anthropic_api_key
    if not anthropic_api_key:
        st.write(
            "To continue, please make sure the `ANTHROPIC_API_KEY`"
            " environment variable is set"
        )
        st.stop()


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


def _write_message(role, content: str | list):
    with st.chat_message(role):
        st.markdown(_message_content_as_plain_text(content))


def _message_content_as_plain_text(content: str | list):
    if isinstance(content, str):
        return content

    results = [item["text"] for item in content if item["type"] == "text"]

    return "\n\n".join(results)


if __name__ == "__main__":
    main()
