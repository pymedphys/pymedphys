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


from functools import partial
from itertools import chain
from typing import Callable

import trio
from anthropic import AsyncAnthropic
from anthropic.types.beta.tools import ToolsBetaMessage

import pymedphys

from ._get_queries import get_queries
from ._query_voter import get_top_k_query_ids
from ._select_tables import get_selected_table_names
from ._utilities import execute_query

# More of these improves the overall quality, but also increases cost.
# If you have a limited number of concurrents in the API, setting these
# as a multiple of your limit makes sense.
NUM_PARALLEL_QUERY_CREATION_AGENTS = 6
NUM_PARALLEL_QUERY_VOTER_AGENTS = 4

MAX_QUERY_STRING_LENGTH = 16352


async def sql_tool_pipeline(
    anthropic_client: AsyncAnthropic,
    connection: pymedphys.mosaiq.Connection,
    messages: list[ToolsBetaMessage],
    sub_agent_prompt: str,
):
    """Receives a message transcript and sub agent prompt and returns
    SQL queries and their corresponding results"""

    async def retrieval_function():
        return await get_single_set_of_query_result_pairs(
            anthropic_client=anthropic_client,
            connection=connection,
            messages=messages,
            sub_agent_prompt=sub_agent_prompt,
        )

    nested_query_result_pairs = await gather(
        [retrieval_function] * NUM_PARALLEL_QUERY_CREATION_AGENTS
    )

    query_result_pairs = list(set(chain.from_iterable(nested_query_result_pairs)))

    async def voting_function():
        return await get_top_k_query_ids(
            anthropic_client=anthropic_client,
            messages=messages,
            sub_agent_prompt=sub_agent_prompt,
            query_result_pairs=query_result_pairs,
        )

    nested_selected_query_ids = await gather(
        [voting_function] * NUM_PARALLEL_QUERY_VOTER_AGENTS
    )

    selected_query_ids = set(chain.from_iterable(nested_selected_query_ids))
    filtered_query_result_pairs = [query_result_pairs[id] for id in selected_query_ids]

    xml_output = "<mosaiq_sql_agent_result>"

    for query, result in filtered_query_result_pairs:
        xml_output += f"""\
<query>
{query}
</query>
<result>
{result}
</result>
"""
    xml_output += "</mosaiq_sql_agent_result>"

    return xml_output


async def _execute_query_with_truncated_string_result(
    connection: pymedphys.mosaiq.Connection, query: str
):
    try:
        result = await execute_query(connection, query)
        string_result = repr(result)
    except Exception as e:  # pylint: disable=broad-exception-caught
        string_result = str(e)

    if len(string_result) > MAX_QUERY_STRING_LENGTH:
        string_result = (
            string_result[0:MAX_QUERY_STRING_LENGTH]
            + "\n\n... (query result exceeded maximum length)"
        )

    return string_result


async def get_single_set_of_query_result_pairs(
    anthropic_client: AsyncAnthropic,
    connection: pymedphys.mosaiq.Connection,
    messages: list[ToolsBetaMessage],
    sub_agent_prompt: str,
):
    table_names = await get_selected_table_names(
        anthropic_client=anthropic_client,
        connection=connection,
        messages=messages,
        sub_agent_prompt=sub_agent_prompt,
    )
    queries = await get_queries(
        anthropic_client=anthropic_client,
        connection=connection,
        messages=messages,
        tables_to_keep=table_names,
        sub_agent_prompt=sub_agent_prompt,
    )

    coroutines = []

    for query in queries:
        coroutines.append(
            partial(_execute_query_with_truncated_string_result, connection, query)
        )

    results = await gather(coroutines)

    return list(zip(queries, results))


async def gather(funcs: list[Callable]):
    results = [None] * len(funcs)

    async def runner(func, i):
        results[i] = await func()

    async with trio.open_nursery() as nursery:
        for i, func in enumerate(funcs):
            nursery.start_soon(runner, func, i)

    return results
