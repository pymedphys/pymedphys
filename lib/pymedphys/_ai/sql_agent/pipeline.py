from itertools import chain

import trio
from anthropic import AsyncAnthropic

from ..messages import Messages
from ._get_queries import get_queries
from ._select_tables import get_selected_table_names


def sql_tool_pipeline():
    return trio.run(async_sql_tool_pipeline)


NUM_PARALLEL_AGENTS = 10


async def async_sql_tool_pipeline(anthropic_client: AsyncAnthropic, messages: Messages):
    """Receives a message transcript and returns SQL queries in MSSQL format"""

    async def retrieval_function():
        return await single_retrieval_chain(anthropic_client, messages)

    queries = await gather([retrieval_function] * NUM_PARALLEL_AGENTS)
    return list(chain.from_iterable(queries))


async def single_retrieval_chain(anthropic_client: AsyncAnthropic, messages: Messages):
    table_names = await get_selected_table_names(anthropic_client, messages)
    queries = await get_queries(anthropic_client, messages, table_names)

    return queries


async def gather(*funcs):
    results = [None] * len(funcs)

    async def runner(func, i):
        results[i] = await func()

    async with trio.open_nursery() as nursery:
        for i, func in enumerate(funcs):
            nursery.start_soon(runner, func, i)

    return results
