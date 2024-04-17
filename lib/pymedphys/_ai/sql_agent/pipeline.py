import trio

from ..messages import Messages


def sql_tool_pipeline():
    return trio.run(async_sql_tool_pipeline)


async def async_sql_tool_pipeline(messages: Messages):
    """Receives a message transcript and returns SQL queries in MSSQL format"""
