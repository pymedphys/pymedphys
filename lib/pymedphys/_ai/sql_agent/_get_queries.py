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
You are an MSSQL AI agent. You respond only with valid Microsoft SQL
Queries encompassed within <query> tags. You always provide 10 unique
and diverse queries.

The top level AI agent has provided the following prompt / request to
your agent cluster, of which you are fulfilling the component of
"write useful, diverse, and valid MSSQL queries":
<sub_agent_prompt>
{sub_agent_prompt}
</sub_agent_prompt>

Some queries that you request may not return a result, and some tables
within the schema may just be empty. So make sure that each of your
queries targets different tables within the database so that you get
good coverage over possible solutions and are able to return something
meaningful.

Don't assume that you know the values that would be within a given
column within a given table. Make sure to try various possible values
that might be stored within the schema so that if you make a wrong
assumption about a column's contents at least one of your queries
returns a meaningful result. Be careful to not filter all of your
queries using the same assumption about what columns may contain as a
wrong assumption may make all of your queries return nothing.

Try to make the results of your queries have a reasonable amount of
verbosity to them as the top level AI agent is able to rapidly parse
large amounts information.

Try to avoid queries that utilise "FETCH FIRST 1 ROW ONLY" and "TOP 1".
Instead err on the side of choosing queries that will return at least 5
rows.

All queries assume the following database schema:
{schema}

The transcript of the conversation thus far between the top level AI
agent and the user is the following:
<transcript>
{transcript}
</transcript>
"""

USER_PROMPT = """
You respond with useful, diverse, and valid Microsoft SQL queries
encompassed within <query> tags. Using the following format:

<final>
<query>
Your first SQL query
</query>

<query>
Your second SQL query
</query>

...

<query>
Your 10th SQL query
</query>
</final>

Prior to making your final choice you go through the following steps:

1. Think through your answer inside <thinking> tags
2. Create a set of 10 draft queries inside <draft> tags
3. Undergo reflection and critique on your draft selection inside
   <reflection> tags
4. Provide a score between 0 and 10 within <score> tags for
   how well the queries within the <draft> meet the requirements.
5. Repeat steps 2, 3, and 4 multiple times until both at least 3 repeats
   have been undergone as well as a score of at least 8 has
   been achieved.
6. Provide your final selection within <final> tags.
7. Finished

All queries assume that the database is designed according
to the provided schema within the <database> tags that was provided
within your system prompt. You are to provide exactly 10 unique and
diverse queries. Make sure that each of your queries targets different
tables within the database.
"""

START_OF_ASSISTANT_PROMPT = """
<thinking>
"""


@async_cache
async def get_system_prompt(
    connection: pymedphys.mosaiq.Connection,
    transcript: str,
    sub_agent_prompt: str,
    tables_to_keep: tuple[str],
):
    filtered_tables_schema = await get_schema_formatted_for_prompt(
        connection=connection, tables_to_keep=tables_to_keep
    )

    return SYSTEM_PROMPT.format(
        schema=filtered_tables_schema,
        sub_agent_prompt=sub_agent_prompt,
        transcript=transcript,
    )


async def get_queries(
    anthropic_client: AsyncAnthropic,
    connection: pymedphys.mosaiq.Connection,
    messages: list[ToolsBetaMessage],
    sub_agent_prompt: str,
    tables_to_keep: tuple[str],
):
    raw_queries = await _get_raw_queries(
        anthropic_client=anthropic_client,
        connection=connection,
        messages=messages,
        sub_agent_prompt=sub_agent_prompt,
        tables_to_keep=tables_to_keep,
    )

    raw_queries_post_final = raw_queries.split("<final>")[1]

    queries = []
    for query_with_close_tag in raw_queries_post_final.split("<query>"):
        query = query_with_close_tag.split("</query>")[0].strip()
        if query:
            queries.append(query)

    return queries


async def _get_raw_queries(
    anthropic_client: AsyncAnthropic,
    connection: pymedphys.mosaiq.Connection,
    messages: list[ToolsBetaMessage],
    sub_agent_prompt: str,
    tables_to_keep: tuple[str],
):
    return await words_in_mouth_prompting(
        anthropic_client=anthropic_client,
        model=model_versions.FAST,
        system_prompt=await get_system_prompt(
            connection=connection,
            sub_agent_prompt=sub_agent_prompt,
            tables_to_keep=tables_to_keep,
            transcript=json.dumps(messages),
        ),
        appended_user_prompt=USER_PROMPT,
        start_of_assistant_prompt=START_OF_ASSISTANT_PROMPT,
    )
