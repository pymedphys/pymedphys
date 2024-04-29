import re

from anthropic import AI_PROMPT, AsyncAnthropic

from pymedphys._ai.messages import Messages, PromptMap

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
<table name="
"""


@_utilities.async_cache
async def get_system_prompt():
    table_name_only_schema = await _utilities.get_schema_formatted_for_prompt(
        include_columns=False
    )

    return SYSTEM_PROMPT.format(table_name_only_schema=table_name_only_schema)


async def get_selected_table_names(
    anthropic_client: AsyncAnthropic, messages: Messages
):
    raw_table_names = await _get_raw_selected_table_names(anthropic_client, messages)

    table_names = []
    for line in raw_table_names.split("\n"):
        match = re.search(r'<table name="(.*)">', line)
        table_names.append(match.group(1))

    return table_names


async def _get_raw_selected_table_names(
    anthropic_client: AsyncAnthropic, messages: Messages
) -> str:
    result = await anthropic_client.completions.create(
        model="claude-3-haiku-20240307",
        max_tokens_to_sample=50_000,
        prompt=await _get_select_table_prompt_from_messages(messages),
        stop_sequences=["</selection>"],
    )

    return '<table name="' + result.completion


async def _get_select_table_prompt_from_messages(messages: Messages):
    prompt = await get_system_prompt()

    for message in messages:
        prompt += f"{PromptMap[message['role']]} {message['content']}"

    prompt += f"{PromptMap['user']} {APPENDED_USER_PROMPT}"
    prompt += AI_PROMPT
    prompt += START_OF_ASSISTANT_PROMPT

    return prompt
