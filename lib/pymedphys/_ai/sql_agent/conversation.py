from anthropic import AsyncAnthropic
from anthropic.types.beta.tools import ToolParam

import pymedphys
from pymedphys._ai.messages import Messages

from .pipeline import sql_tool_pipeline

SYSTEM_PROMPT = """\
You are MOSAIQ Claude Chat. Your goal is to be helpful, harmless and
honest while providing answers to questions asked about the contents of
the MOSAIQ database.

If a given set of queries did not return the results that you expected
do not critique the underlying database schema, instead come up with at
least 3 different approaches that you might be able to try for querying
the database that you would like to try in order to answer the question,
and then try again.

The user you are talking with already has access to the database in
question, and as such it is okay to provide them any information that is
found within that database.

Importantly, from the user's perspective you are the one making the SQL
queries, however it is in fact your sub agent MOSAIQ tool that will do
this for you.

Don't ever claim the data doesn't exist, you may need to just try again
in a different way."""

TOOLS_PROMPT: list[ToolParam] = [
    {
        "name": "mosaiq_sql_agent",
        "description": """\
Instantiate an Elekta MOSAIQ sub agent with a request to \
search for information and it will autonomously craft SQL queries to search \
the MOSAIQ OIS database with the intent to find relevant information for \
your request.

The subagent will be provided with the following information:

- Your custom `sub_agent_prompt`
- The sub agent's built in system prompt
- The underlying MOSAIQ SQL database schema
- The current conversation transcript

The only input component that you are required to provide to the subagent is the
`sub_agent_prompt`.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "sub_agent_prompt": {
                    "type": "string",
                    "description": """\
Your plain text sub agent prompt that will be provided to the MOSAIQ subagent. This is
to intended to be used to guide the subagent tool request.""",
                }
            },
            "required": ["sub_agent_prompt"],
        },
    }
]


def create_tools_mappings(
    anthropic_client: AsyncAnthropic,
    connection: pymedphys.mosaiq.Connection,
    messages: Messages,
):
    async def mosaiq_sql_agent(sub_agent_prompt: str):
        return await sql_tool_pipeline(
            anthropic_client=anthropic_client,
            connection=connection,
            messages=messages,
            sub_agent_prompt=sub_agent_prompt,
        )

    tools_mapping = {"mosaiq_sql_agent": mosaiq_sql_agent}

    return tools_mapping


async def conversation_with_tool_use(
    anthropic_client: AsyncAnthropic,
    model: str,
    system_prompt: str,
    tools: list[ToolParam],
    messages: Messages,
):
    api_response = await anthropic_client.beta.tools.messages.create(
        system=system_prompt,
        model=model,
        max_tokens=4096,
        tools=tools,
        messages=messages,
    )

    assert len(api_response.content) == 1
    content_response = api_response.content[0]
    assert content_response.type == "text"

    # result = start_of_assistant_prompt + content_response.text
    # print(result)

    # return result
