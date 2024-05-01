import json
import os

import streamlit as st
import trio
from anthropic import AsyncAnthropic
from anthropic.types.beta.tools import ToolsBetaContentBlock

import pymedphys

# from pymedphys.mosaiq import execute
from .sql_agent.conversation import recursively_append_message_responses

USER = "user"


def main():
    _initialise_state()

    # print(
    #     execute(
    #         _mosaiq_connection(), "SELECT TABLE_NAME FROM information_schema.tables"
    #     )
    # )

    with st.sidebar:
        if st.button("Remove last message"):
            st.session_state.messages = st.session_state.messages[:-1]

        if st.button("Remove last two messages"):
            st.session_state.messages = st.session_state.messages[:-2]

        _transcript_downloads()

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
        _async_anthropic(),
        _mosaiq_connection(),
        st.session_state.messages,
    )

    st.rerun()


def _initialise_state():
    if "messages" not in st.session_state:
        st.session_state.messages = []


@st.cache_resource
def _async_anthropic():
    return AsyncAnthropic()


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
        file_name="transcript.txt",
    )
    st.download_button(
        "Download raw transcript", raw_transcript, file_name="transcript.json"
    )


def _append_message(role, content):
    st.session_state.messages.append({"role": role, "content": content})


if __name__ == "__main__":
    main()
