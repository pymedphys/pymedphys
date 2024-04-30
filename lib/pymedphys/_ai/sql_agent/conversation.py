from anthropic import AsyncAnthropic
from anthropic.types.beta.tools import ToolParam, ToolsBetaMessage

import pymedphys
from pymedphys._ai import model_versions

from ._pipeline import sql_tool_pipeline

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


async def recursively_append_message_responses(
    anthropic_client: AsyncAnthropic,
    connection: pymedphys.mosaiq.Connection,
    messages: list[ToolsBetaMessage],
):
    await _conversation_with_tool_use(
        anthropic_client=anthropic_client,
        connection=connection,
        model=model_versions.INTELLIGENT,
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS_PROMPT,
        messages=messages,
    )


def create_tools_mappings(
    anthropic_client: AsyncAnthropic,
    connection: pymedphys.mosaiq.Connection,
    messages: list[ToolsBetaMessage],
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


async def _conversation_with_tool_use(
    anthropic_client: AsyncAnthropic,
    connection: pymedphys.mosaiq.Connection,
    model: str,
    system_prompt: str,
    tools: list[ToolParam],
    messages: list[ToolsBetaMessage],
):
    """Mutates messages in-place recursively. NOTE: This is probably not a good idea,
    likely worth refactoring."""

    tools_mappings = create_tools_mappings(
        anthropic_client=anthropic_client, connection=connection, messages=messages
    )

    messages_to_submit = [
        {"role": item["role"], "content": item["content"]} for item in messages
    ]

    api_response = await anthropic_client.beta.tools.messages.create(
        system=system_prompt,
        model=model,
        max_tokens=4096,
        tools=tools,
        messages=messages_to_submit,
    )

    messages.append(api_response.to_dict())

    if api_response.stop_reason == "tool_use":
        for item in api_response.content:
            print(item)

            if item.type == "tool_use":
                tool = tools_mappings[item.name]

                # TODO: Make this run in parallel
                result = await tool(**item.input)

                response_message = {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": item.id,
                            "content": result,
                        }
                    ],
                }

                messages.append(response_message)

        await _conversation_with_tool_use(
            anthropic_client=anthropic_client,
            connection=connection,
            model=model,
            system_prompt=system_prompt,
            tools=tools,
            messages=messages,
        )
