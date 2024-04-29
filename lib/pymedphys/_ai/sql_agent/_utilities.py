import pathlib
from collections import defaultdict
from collections.abc import Awaitable, Callable
from functools import wraps

import trio

import pymedphys

HERE = pathlib.Path(__file__).parent.resolve()


# TODO: Need to rework this to use PyMedPhys mosaiq connection logic

GET_ALL_COLUMNS_BY_TABLE_NAME = """\
SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE
FROM INFORMATION_SCHEMA.COLUMNS
"""


async def get_schema_formatted_for_prompt(
    connection: pymedphys.mosaiq.Connection,
    include_columns: bool = True,
    tables_to_keep: list[str] | None = None,
):
    columns_by_table_name = await _get_columns_by_table_name(connection)

    exported_schema: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for table_name, column_name, data_type in columns_by_table_name:
        if tables_to_keep is not None and table_name not in tables_to_keep:
            continue

        exported_schema[table_name].append((column_name, data_type))

    table_strings = ""
    for table, columns in exported_schema.items():
        table_strings += f'  <table name="{table}">\n'

        if include_columns:
            columns_string = ""
            for column_name, data_type in columns:
                columns_string += (
                    f'    <column name="{column_name}" type="{data_type}" />\n'
                )

            table_strings += columns_string
        table_strings += "  </table>\n"

    database_string = f'<?xml version="1.0" encoding="UTF-8"?>\n<database>\n{table_strings}</database>'

    return database_string


def async_cache(f: Callable[..., Awaitable]):
    cache = {}

    @wraps(f)
    async def inner(*args, **kwargs):
        key = args + tuple(sorted(kwargs.items()))
        if key in cache:
            await trio.lowlevel.checkpoint()
        else:
            cache[key] = await f(*args, **kwargs)
        return cache[key]

    return inner


@async_cache
async def _get_columns_by_table_name(connection):
    return await execute_query(connection, GET_ALL_COLUMNS_BY_TABLE_NAME)


async def execute_query(connection: pymedphys.mosaiq.Connection, query: str):
    result = await trio.to_thread.run_sync(pymedphys.mosaiq.execute, connection, query)

    return result
