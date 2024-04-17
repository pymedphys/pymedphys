import logging
import os
import pathlib
import tempfile
from collections import defaultdict
from functools import wraps
from collections.abc import (
    Awaitable,
    Callable,
)

import trio


HERE = pathlib.Path(__file__).parent.resolve()

QUERY_PREPEND = """\
SET NOCOUNT ON;
USE PRACTICE;
"""
GET_ALL_COLUMNS_BY_TABLE_NAME = """\
SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE
FROM INFORMATION_SCHEMA.COLUMNS
GO
"""


# Used Claude to see what XML format it would prefer:
# https://claude.ai/share/00f9529a-e30c-46a5-9344-2237b5435bcc


async def get_schema_formatted_for_prompt(
    include_columns: bool = True, tables_to_keep: list[str] | None = None
):
    columns_by_table_name = await _get_columns_by_table_name()

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
async def _get_columns_by_table_name():
    return await run_query_with_nested_list_output(GET_ALL_COLUMNS_BY_TABLE_NAME)


async def run_query(query: str, extra_cmd_args: list[str] | None = None):
    password = os.environ["MSSQL_SA_PASSWORD"]

    with tempfile.TemporaryDirectory() as d:
        file_path = f"{d}/query.sql"

        async with await trio.open_file(file_path, "w") as f:
            await f.write(QUERY_PREPEND + query)

        cmd = [
            "sqlcmd",
            "-S",
            "localhost",
            "-U",
            "sa",
            "-P",
            password,
            "-i",
            file_path,
        ]

        if extra_cmd_args:
            cmd += extra_cmd_args

        proc = await trio.run_process(cmd, capture_stdout=True, capture_stderr=True)

    # strips out the first item which is the result from the QUERY_PREPEND
    output_with_first_line_removed = proc.stdout.decode().splitlines()[1:]
    output_with_empty_lines_removed = [
        row.strip() for row in output_with_first_line_removed if row.strip()
    ]

    return "\n".join(output_with_empty_lines_removed)


async def run_query_with_nested_list_output(query: str):
    query_result = await run_query(
        query,
        extra_cmd_args=[
            "-b",
            "-s",
            ",",
            "-h",
            "-1",
        ],
    )

    return [
        [item.strip() for item in row.split(",")] for row in query_result.splitlines()
    ]


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    from belt.cli import run

    run([get_schema_formatted_for_prompt])

"""
Make a schema dump file for browsing:

python -m pymedphys._ai.sql_agent._utilities > ~/mosaiq-data/schema.xml
"""
