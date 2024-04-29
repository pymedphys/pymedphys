from itertools import chain
from typing import Callable

import trio
from anthropic import AsyncAnthropic

import pymedphys

from ..messages import Messages
from ._get_queries import get_queries
from ._select_tables import get_selected_table_names

NUM_PARALLEL_AGENTS = 10


async def sql_tool_pipeline(
    anthropic_client: AsyncAnthropic,
    connection: pymedphys.mosaiq.Connection,
    messages: Messages,
):
    """Receives a message transcript and returns SQL queries in MSSQL format"""

    async def retrieval_function():
        return await single_retrieval_chain(
            anthropic_client=anthropic_client, connection=connection, messages=messages
        )

    queries = await gather([retrieval_function] * NUM_PARALLEL_AGENTS)

    # TODO: Pass all of the possible queries + messages through to an
    # opus "query voter agent" that selects the best queries to run.

    # Shuffle the queries and get 3 separate opus agents to vote in
    # parallel. Select the best 10 queries of the lot.

    return list(chain.from_iterable(queries))


async def single_retrieval_chain(
    anthropic_client: AsyncAnthropic,
    connection: pymedphys.mosaiq.Connection,
    messages: Messages,
):
    table_names = await get_selected_table_names(
        anthropic_client=anthropic_client, connection=connection, messages=messages
    )
    queries = await get_queries(anthropic_client, messages, table_names)

    return queries


async def gather(funcs: list[Callable]):
    results = [None] * len(funcs)

    async def runner(func, i):
        results[i] = await func()

    async with trio.open_nursery() as nursery:
        for i, func in enumerate(funcs):
            nursery.start_soon(runner, func, i)

    return results
