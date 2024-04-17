from anthropic import AI_PROMPT, AsyncAnthropic

from pymedphys._ai.messages import Messages, PromptMap

from . import _utilities

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


@_utilities.async_cache
async def get_system_prompt(tables_to_keep: list[str]):
    filtered_tables_schema = await _utilities.get_schema_formatted_for_prompt(
        tables_to_keep=tables_to_keep
    )

    return SYSTEM_PROMPT.format(schema=filtered_tables_schema)


async def get_queries(
    anthropic_client: AsyncAnthropic, messages: Messages, tables_to_keep: list[str]
):
    raw_queries = await _get_raw_queries(anthropic_client, messages, tables_to_keep)

    queries = []
    for query_with_close_tag in raw_queries.split("<query>"):
        query = query_with_close_tag.split("</query>")[0].strip()
        if query:
            queries.append(query)

    return queries


async def _get_raw_queries(
    anthropic_client: AsyncAnthropic, messages: Messages, tables_to_keep: list[str]
):
    result = await anthropic_client.completions.create(
        model="claude-3-haiku-20240307",
        max_tokens_to_sample=50_000,
        prompt=await _get_queries_prompt_from_messages(
            messages, tables_to_keep=tables_to_keep
        ),
    )

    return START_OF_ASSISTANT_PROMPT + result.completion


async def _get_queries_prompt_from_messages(
    messages: Messages, tables_to_keep: list[str]
):
    prompt = await get_system_prompt(tables_to_keep=tables_to_keep)

    for message in messages:
        prompt += f"{PromptMap[message['role']]} {message['content']}"

    prompt += f"{PromptMap['user']} {APPENDED_USER_PROMPT}"
    prompt += AI_PROMPT
    prompt += START_OF_ASSISTANT_PROMPT

    return prompt
