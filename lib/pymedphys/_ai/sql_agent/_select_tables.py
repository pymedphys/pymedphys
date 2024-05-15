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
import re

from anthropic import AsyncAnthropic
from anthropic.types.beta.tools import ToolsBetaMessage

import pymedphys
from pymedphys._ai import model_versions

from ._utilities import (
    async_cache,
    get_schema_formatted_for_prompt,
    words_in_mouth_prompting,
)

SYSTEM_PROMPT = """\
You are an MSSQL SQL table selector agent.

You are a part of a wider AI cluster that is trying to be helpful,
harmless and honest while conversing with a user.

The top level AI agent has provided the following prompt / request to
your agent cluster, of which you are fulfilling the component of
"selecting relevant tables from the MOSAIQ MSSQL database":
<sub_agent_prompt>
{sub_agent_prompt}
</sub_agent_prompt>

You are just one component of the cluster. It is NOT your job to respond
to the user, instead it is JUST your job to select the top 40 tables
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

The transcript of the conversation thus far between the top level AI
agent and the user is the following:
<transcript>
{transcript}
</transcript>
"""

USER_PROMPT = """
You respond only with table name xml tags using the following format:

<selection>
<table name="A chosen table name">
<table name="Another chosen table name">

...

<table name="Your last chosen table name">
</selection>

Table names are to be chosen from the above according to the schema
within the <database> tags that was provided above within your system
prompt. You are to provide approximately 40 table names that may be
relevant to search within in order to answer the user's question.
"""

START_OF_ASSISTANT_PROMPT = """
<selection>
<table name="
"""


@async_cache
async def get_system_prompt(
    connection: pymedphys.mosaiq.Connection, transcript: str, sub_agent_prompt: str
):
    table_name_only_schema = await get_schema_formatted_for_prompt(
        connection=connection, include_columns=False
    )

    return SYSTEM_PROMPT.format(
        table_name_only_schema=table_name_only_schema,
        sub_agent_prompt=sub_agent_prompt,
        transcript=transcript,
    )


async def get_selected_table_names(
    anthropic_client: AsyncAnthropic,
    connection: pymedphys.mosaiq.Connection,
    messages: list[ToolsBetaMessage],
    sub_agent_prompt: str,
) -> tuple[str, ...]:
    raw_table_names = await _get_raw_selected_table_names(
        anthropic_client=anthropic_client,
        connection=connection,
        messages=messages,
        sub_agent_prompt=sub_agent_prompt,
    )

    table_names = []
    for line in raw_table_names.split("\n"):
        if not line.startswith('<table name="'):
            continue

        match = re.search(r'<table name="(.*)">', line)
        table_names.append(match.group(1))

    return tuple(table_names)


async def _get_raw_selected_table_names(
    anthropic_client: AsyncAnthropic,
    connection: pymedphys.mosaiq.Connection,
    messages: list[ToolsBetaMessage],
    sub_agent_prompt: str,
) -> str:
    return await words_in_mouth_prompting(
        anthropic_client=anthropic_client,
        model=model_versions.FAST,
        system_prompt=await get_system_prompt(
            connection=connection,
            sub_agent_prompt=sub_agent_prompt,
            transcript=json.dumps(messages),
        ),
        appended_user_prompt=USER_PROMPT,
        start_of_assistant_prompt=START_OF_ASSISTANT_PROMPT,
    )
