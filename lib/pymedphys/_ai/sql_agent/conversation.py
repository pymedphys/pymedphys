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


from typing import Any, Awaitable, Callable

from anthropic import AsyncAnthropic
from anthropic.types import Message, MessageParam

import pymedphys
from pymedphys._ai import model_versions

from ._pipeline import sql_tool_pipeline

AsyncCallable = Callable[[Any, Any], Awaitable[Any]]


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
in a different way.

Your conversation with the user is occurring in markdown format, so
please format your responses to the user with this in mind."""

TOOLS_PROMPT: list[MessageParam] = [
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

The only input component that you are required to provide to the \
subagent is the `sub_agent_prompt`.

In your first call to this tool for any given user enquiry try to \
create a prompt that "surveys" the database giving you an overview of \
what is available, helping you to plan how to most effectively make \
subsequent follow up prompts to this tool in order to answer the \
enquiry.

This `mosaiq_sql_agent` is not able to undergo multiple steps in \
response to its result. That's your job. So, first make a plan \
regarding what you are going to do, and then ask just one step at a \
time for each call to the `mosaiq_sql_agent`.

If you have any uncertainty around whether or not you should call this \
tool, err on the side of calling it. It is better to collect information \
and improve the likelihood of a correct response than to answer with \
insufficient information.

For each user query you should expect to call this approximately three \
times, each time using the results from the previous call to improve \
your subsequent requests to this tool.

If you see any inconsistency in your results err on the side of \
collecting more information from the database before providing your \
final answer to the user.

The results from the subagent will be returned to you as a series of \
queries and their raw results in the format:
<query></query><result></result>
""",
        "input_schema": {
            "type": "object",
            "properties": {
                "sub_agent_prompt": {
                    "type": "string",
                    "description": """\
Your plain text sub agent prompt that will be provided to the MOSAIQ \
subagent. This is to intended to be used to guide the subagent tool \
request.""",
                }
            },
            "required": ["sub_agent_prompt"],
        },
    }
]

APPENDED_USER_PROMPT = ""

START_OF_ASSISTANT_PROMPT = "<thinking>"

# TODO: Potentially even have a "verification flag" that has the
# assistant try again with their response if they provided a results
# flag.

# TODO: Make both of these TypedDicts
Messages = list[Message | MessageParam]


async def recursively_append_message_responses(
    anthropic_client: AsyncAnthropic,
    connection: pymedphys.mosaiq.Connection,
    messages: list[Message],
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
    messages: list[MessageParam],
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
    tools: list[MessageParam],
    messages: list[Message],
):
    """Mutates messages in-place recursively.
    NOTE: This is probably not a good idea, likely worth refactoring."""

    tools_mappings = create_tools_mappings(
        anthropic_client=anthropic_client, connection=connection, messages=messages
    )

    messages_to_submit = [
        {"role": item["role"], "content": item["content"]} for item in messages
    ]

    api_response = await anthropic_client.messages.create(
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

                print(response_message)

        await _conversation_with_tool_use(
            anthropic_client=anthropic_client,
            connection=connection,
            model=model,
            system_prompt=system_prompt,
            tools=tools,
            messages=messages,
        )
