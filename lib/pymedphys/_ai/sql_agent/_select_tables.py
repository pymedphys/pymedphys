import re
from copy import deepcopy

from anthropic import AsyncAnthropic

import pymedphys
from pymedphys._ai.messages import Messages

from . import _utilities

SYSTEM_PROMPT = """\
You are an MSSQL SQL table selector agent.

You are a part of a wider AI cluster that is trying to be helpful,
harmless and honest while conversing with a user.

You are just one component of the cluster. It is NOT your job to respond
to the user, instead it is JUST your job to select the top 20 tables
from a database schema that might be helpful to search within in order
to answer the user's question.

You use the following xml tags to detail your chosen table names:

<selection>
<table name="A chosen table name">
<table name="Another chosen table name">

...

<table name="Your last chosen table name">
</selection>

Another AI agent within the cluster will then take these table names and
form subsequent queries. It is NOT your job to make these queries.
{table_name_only_schema}
"""

# NOTE: The historical transcript of user/assistant will be included
# before the final user prompt where the below will be appended.
APPENDED_USER_PROMPT = """\
You respond only with table name xml tags using the following format:

<selection>
<table name="A chosen table name">
<table name="Another chosen table name">

...

<table name="Your last chosen table name">
</selection>

Table names are to be chosen from the above according to the schema
within the <database> tags that was provided above within your system
prompt. You are to provide approximately 20 table names that may be
relevant to search within in order to answer the user's question.
"""
START_OF_ASSISTANT_PROMPT = """\
<selection>
<table name="\
"""


@_utilities.async_cache
async def get_system_prompt(connection: pymedphys.mosaiq.Connection):
    table_name_only_schema = await _utilities.get_schema_formatted_for_prompt(
        connection=connection, include_columns=False
    )

    return SYSTEM_PROMPT.format(table_name_only_schema=table_name_only_schema)


async def get_selected_table_names(
    anthropic_client: AsyncAnthropic,
    connection: pymedphys.mosaiq.Connection,
    messages: Messages,
):
    raw_table_names = await _get_raw_selected_table_names(
        anthropic_client=anthropic_client, connection=connection, messages=messages
    )

    table_names = []
    for line in raw_table_names.split("\n"):
        match = re.search(r'<table name="(.*)">', line)
        table_names.append(match.group(1))

    return table_names


async def _get_raw_selected_table_names(
    anthropic_client: AsyncAnthropic,
    connection: pymedphys.mosaiq.Connection,
    messages: Messages,
) -> str:
    result = await anthropic_client.messages.create(
        system=await get_system_prompt(connection=connection),
        model="claude-3-haiku-20240307",
        max_tokens=4096,
        messages=await _get_select_table_prompt_from_messages(messages=messages),
        stop_sequences=["</selection>"],
    )

    assert len(result.content) == 1
    response = result.content[0]

    assert response.type == "text"

    content = response.text

    return '<table name="' + content


async def _get_select_table_prompt_from_messages(messages: Messages):
    messages_to_submit = deepcopy(messages)

    assert messages_to_submit[-1]["role"] == "user"
    messages_to_submit[-1]["content"] += APPENDED_USER_PROMPT

    messages_to_submit.append(
        {"role": "assistant", "content": START_OF_ASSISTANT_PROMPT}
    )

    return messages_to_submit
