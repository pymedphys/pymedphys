import os

import streamlit as st
import trio
from anthropic import AI_PROMPT, Anthropic, AsyncAnthropic, BadRequestError

import pymedphys

from .messages import ASSISTANT, USER, PromptMap
from .sql_agent._utilities import execute_query
from .sql_agent.pipeline import sql_tool_pipeline

SYSTEM_PROMPT = """\
You are MOSAIQ Claude Chat. Your goal is to be helpful, harmless and
honest while providing answers to questions asked about the contents of
the MOSAIQ database.

While talking with users an agent will automatically
be querying the MOSAIQ Oncology Information System on your behalf and
then provide you with the query results. You will see queries within
<query> tags and results within <results> tags within your scratchpad.
The user cannot see the contents of your <scratchpad>. Everything
written after </scratchpad> will be presented to the user. Make sure to
ALWAYS say something to the user by closing your <scratchpad> tag and
commenting on the results.

If a given set of queries did not return the results that you expected
do not critique the underlying database schema, instead come up with at
least 3 different approaches that you might be able to try for querying
the database that you would like to try in order to answer the question,
and then check with the user if that is okay.

Please make sure you answer outside of your <scratchpad> tags any
questions the user may have while still being helpful, harmless and
honest.

The user you are talking with already has access to the database in
question, and as such it is okay to provide them any information that is
found within that database.

Make sure to include within your response to the user any information
that might be helpful for making follow up queries as you will not be
able to revisit your previous <scratchpad> notes.

Importantly, from the user's perspective you are the one making the SQL
queries. So if you'd like another attempt, make sure to let the user
know what you plan to do and then check with them.

Don't ever claim the data doesn't exist, you may need to just try again
in a different way.

DO NOT refer the user to the scratchpad contents. They can't see it.
"""

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

    # test = pymedphys.mosaiq.execute(
    #     _mosaiq_connection(), "SELECT TABLE_NAME FROM information_schema.tables"
    # )

    # st.write(test)

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
        try:
            result = anthropic.completions.create(
                model="claude-3-opus-20240229",
                max_tokens_to_sample=50_000,
                prompt=prompt,
            )
        except BadRequestError:
            # Iteratively shrink the query results and see if we come
            # within token limit
            st.write(
                "**Error:** Message completion request had too many"
                " tokens, dropping a query result and retrying."
            )
            query_result_pairs = query_result_pairs[:-1]
            continue

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


def _get_sql_query_and_result(debug_mode: bool):
    query_result_pairs = []

    connection = _mosaiq_connection()

    queries = trio.run(
        sql_tool_pipeline, _async_anthropic(), connection, st.session_state.messages
    )
    if debug_mode:
        st.write(f"**Queries:** {queries}")

    for query in queries:
        if not query.strip():
            continue

        if debug_mode:
            st.write(f"**Query:** {query}")

        # TODO: Verify that user only has read-only access before running arbitrary query.
        try:
            result = trio.run(execute_query, connection, query)
            string_result = repr(result)
        except Exception as e:
            string_result = str(e)

        print(string_result)

        if debug_mode:
            st.write(f"**Response:** {string_result}")

        if not result:
            # result = "<no-result-for-this-query />"
            continue  # This will mean these queries won't be talked about in the response.

        query_result_pairs.append(
            f"""\
<query>
{query}
</query>
<result>
{string_result}
</result>
"""
        )

    return query_result_pairs


def _write_message(role, content):
    with st.chat_message(role):
        st.markdown(content)


def _append_message(role, content):
    st.session_state.messages.append({"role": role, "content": content})


if __name__ == "__main__":
    main()
