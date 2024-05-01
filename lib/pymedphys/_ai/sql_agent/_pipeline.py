from functools import partial
from itertools import chain
from typing import Callable

import trio
from anthropic import AsyncAnthropic
from anthropic.types.beta.tools import ToolsBetaMessage

import pymedphys

from ._get_queries import get_queries
from ._select_tables import get_selected_table_names
from ._utilities import execute_query

NUM_PARALLEL_AGENTS = 10


async def sql_tool_pipeline(
    anthropic_client: AsyncAnthropic,
    connection: pymedphys.mosaiq.Connection,
    messages: list[ToolsBetaMessage],
    sub_agent_prompt: str,
):
    """Receives a message transcript and returns SQL queries in MSSQL format"""

    async def retrieval_function():
        return await single_retrieval_chain(
            anthropic_client=anthropic_client,
            connection=connection,
            messages=messages,
            sub_agent_prompt=sub_agent_prompt,
        )

    queries = await gather([retrieval_function] * NUM_PARALLEL_AGENTS)

    # TODO: Pass all of the possible queries + messages through to an
    # opus "query voter agent" that selects the best queries to run.

    # Shuffle the queries and get 3 separate opus agents to vote in
    # parallel. Select the best 10 queries of the lot.

    coroutines = []
    flattened_queries = list(chain.from_iterable(queries))

    for query in flattened_queries:
        coroutines.append(
            partial(_execute_query_with_forced_string_result, connection, query)
        )

    results = await gather(coroutines)

    xml_output = "<mosaiq_sql_agent_result>"

    for query, result in zip(flattened_queries, results):
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


async def _execute_query_with_forced_string_result(
    connection: pymedphys.mosaiq.Connection, query: str
):
    try:
        result = await execute_query(connection, query)
        string_result = repr(result)
    except Exception as e:  # pylint: disable=broad-exception-caught
        string_result = str(e)

    return string_result


async def single_retrieval_chain(
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

    return queries


async def gather(funcs: list[Callable]):
    results = [None] * len(funcs)

    async def runner(func, i):
        results[i] = await func()

    async with trio.open_nursery() as nursery:
        for i, func in enumerate(funcs):
            nursery.start_soon(runner, func, i)

    return results
