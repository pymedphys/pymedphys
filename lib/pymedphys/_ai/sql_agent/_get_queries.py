from anthropic import AsyncAnthropic

import pymedphys
from pymedphys._ai import model_versions
from pymedphys._ai.messages import Messages

from ._utilities import (
    async_cache,
    get_schema_formatted_for_prompt,
    words_in_mouth_prompting,
)

SYSTEM_PROMPT = """\
You are an MSSQL AI agent. You respond only with valid Microsoft SQL
Queries encompassed within <query> tags. You always provide 10 unique
and diverse queries.

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

Do NOT use queries that include the TOP command as these will likely
remove valuable information.

All queries assume the following database schema:
{schema}
"""

# NOTE: The historical transcript of user/assistant will be included
# before the final user prompt where the below will be appended.
APPENDED_USER_PROMPT = """\
You respond only with valid Microsoft SQL Queries encompassed within
<query> tags. All queries assume that the database is designed according
to the provided schema within the <database> tags that was provided
within your system prompt. You are to provide exactly 10 unique and
diverse queries. Make sure that each of your queries targets different
tables within the database.
"""

START_OF_ASSISTANT_PROMPT = """\
<query>
SELECT DISTINCT
"""


@async_cache
async def get_system_prompt(
    connection: pymedphys.mosaiq.Connection, tables_to_keep: tuple[str]
):
    filtered_tables_schema = await get_schema_formatted_for_prompt(
        connection=connection, tables_to_keep=tables_to_keep
    )

    return SYSTEM_PROMPT.format(schema=filtered_tables_schema)


async def get_queries(
    anthropic_client: AsyncAnthropic,
    connection: pymedphys.mosaiq.Connection,
    messages: Messages,
    tables_to_keep: tuple[str],
):
    raw_queries = await _get_raw_queries(
        anthropic_client=anthropic_client,
        connection=connection,
        messages=messages,
        tables_to_keep=tables_to_keep,
    )

    queries = []
    for query_with_close_tag in raw_queries.split("<query>"):
        query = query_with_close_tag.split("</query>")[0].strip()
        if query:
            queries.append(query)

    return queries


async def _get_raw_queries(
    anthropic_client: AsyncAnthropic,
    connection: pymedphys.mosaiq.Connection,
    messages: Messages,
    tables_to_keep: tuple[str],
):
    return await words_in_mouth_prompting(
        anthropic_client=anthropic_client,
        model=model_versions.FAST,
        system_prompt=await get_system_prompt(
            connection=connection, tables_to_keep=tables_to_keep
        ),
        appended_user_prompt=APPENDED_USER_PROMPT,
        start_of_assistant_prompt=START_OF_ASSISTANT_PROMPT,
        messages=messages,
    )
