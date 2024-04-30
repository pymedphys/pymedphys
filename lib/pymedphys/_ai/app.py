import os

import streamlit as st
from anthropic import AI_PROMPT, Anthropic, AsyncAnthropic

import pymedphys

from .messages import ASSISTANT, USER, PromptMap

# TODO: Collect previous error messages and queries that produced no
#  response and save them for follow up queries as a "these did not
# work". Save the ones that did work as these "did work".

# Potentially tweak this so that it always checks with the user before
# triggering the tool use?

# Or maybe it would be better to prime the SQL query with an initial
# embeddings search? And then have the embeddings search flag where it
# found the data from, and in which table?

# Also provide a embeddings based search over the database where the
# search results detail which table it came from. Do the embeddings
# based search first?


def main():
    _initialise_state()

    with st.sidebar:
        st.write("# Debug information")
        debug_mode = st.checkbox("Debug Mode")

        if st.button("Remove last message"):
            st.session_state.messages = st.session_state.messages[:-1]

        if st.button("Remove last two messages"):
            st.session_state.messages = st.session_state.messages[:-2]

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

    with st.sidebar:
        message_to_user = _get_message_completion(debug_mode)

    _append_message(ASSISTANT, message_to_user)
    _write_message(ASSISTANT, message_to_user)


def _get_message_completion(debug_mode: bool):
    query_result_pairs = _get_sql_query_and_result(debug_mode)

    base_prompt = _get_prompt_from_messages()

    anthropic = _anthropic()
    while True:
        query_and_results = "\n".join(query_result_pairs)
        prompt = (
            base_prompt
            + f"""\
<scratchpad>
{query_and_results}

Now I must remember, the user cannot see the results within this
scratchpad so I need to include any important information and results
within my response to them below.
</scratchpad>
"""
        )

        result = anthropic.completions.create(
            model="claude-3-opus-20240229",
            max_tokens_to_sample=50_000,
            prompt=prompt,
        )

        return result.completion


@st.cache_resource
def _anthropic():
    return Anthropic()


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

    return connection


def _initialise_state():
    if "messages" not in st.session_state:
        st.session_state.messages = []


def _get_prompt_from_messages():
    prompt = SYSTEM_PROMPT

    for message in st.session_state.messages:
        prompt += f"{PromptMap[message['role']]} {message['content']}"

    prompt += AI_PROMPT

    return prompt

    return query_result_pairs


def _write_message(role, content):
    with st.chat_message(role):
        st.markdown(content)


def _append_message(role, content):
    st.session_state.messages.append({"role": role, "content": content})


if __name__ == "__main__":
    main()
