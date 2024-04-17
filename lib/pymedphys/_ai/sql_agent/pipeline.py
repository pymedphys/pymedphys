import trio

from ..messages import Messages


def sql_tool_pipeline():
    return trio.run(async_sql_tool_pipeline)


async def async_sql_tool_pipeline(messages: Messages):
    """Receives a message transcript and returns SQL queries in MSSQL format"""

    # Do select tables (do this in parallel ~10 times)

    # Do get queries filtered by selected tables (do this in parallel
    # for each of the above ~10 table filters)

    # Send back the 10 queries
