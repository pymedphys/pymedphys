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


import pathlib
from collections import defaultdict
from collections.abc import Awaitable, Callable
from copy import deepcopy
from functools import wraps
from typing import Any
from xml.sax.saxutils import quoteattr

import trio
from anthropic import AsyncAnthropic
from anthropic.types import TextBlock

import pymedphys

HERE = pathlib.Path(__file__).parent.resolve()


GET_ALL_COLUMNS_BY_TABLE_NAME = """\
SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE
FROM INFORMATION_SCHEMA.COLUMNS
"""

DATABASE_EXECUTION_LOCK = trio.Lock()


def _quote_xml_schema_attribute(value: str) -> str:
    """Quote schema metadata without emitting invalid XML 1.0 characters."""
    identifier = str(value)
    for character in identifier:
        codepoint = ord(character)
        if not (
            codepoint in (0x9, 0xA, 0xD)
            or 0x20 <= codepoint <= 0xD7FF
            or 0xE000 <= codepoint <= 0xFFFD
            or 0x10000 <= codepoint <= 0x10FFFF
        ):
            raise ValueError("SQL schema contains an XML 1.0-forbidden character")

    # quoteattr also encodes tabs, newlines and CRs as XML character references.
    return quoteattr(identifier)


_SQL_MUTATING_WORDS = frozenset(
    {
        "ALTER",
        "BACKUP",
        "BULK",
        "CREATE",
        "DBCC",
        "DELETE",
        "DENY",
        "DROP",
        "EXEC",
        "EXECUTE",
        "GO",
        "GRANT",
        "INSERT",
        "INTO",
        "KILL",
        "MERGE",
        "OPENQUERY",
        "OPENROWSET",
        "OPENDATASOURCE",
        "RECEIVE",
        "RECONFIGURE",
        "RESTORE",
        "REVOKE",
        "SET",
        "SHUTDOWN",
        "TRUNCATE",
        "UPDATE",
        "USE",
        "WAITFOR",
        "WRITETEXT",
        "UPDATETEXT",
    }
)


def _require_read_only_sql(query: str) -> None:
    """Fail closed on model-generated SQL outside a single read-only query.

    This lexical gate is defense in depth, not a SQL permission boundary.
    Connections must use a least-privileged, SELECT-only database principal.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("SQL agent requires a nonempty read-only query")

    words = []
    i = 0
    while i < len(query):
        character = query[i]

        if character in ("'", '"', "["):
            closing = "]" if character == "[" else character
            i += 1
            while i < len(query):
                if query[i] == closing:
                    if i + 1 < len(query) and query[i + 1] == closing:
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            else:
                raise ValueError("Unterminated SQL string or identifier")
            continue

        if query.startswith(("--", "/*"), i):
            raise ValueError("SQL comments are not allowed in agent queries")

        if character == ";":
            if query[i + 1 :].strip():
                raise ValueError("SQL agent queries must contain one statement")
            break

        if character.isalpha() or character == "_":
            end = i + 1
            while end < len(query) and (query[end].isalnum() or query[end] in "_@$#"):
                end += 1
            words.append(query[i:end].upper())
            i = end
        else:
            if ord(character) < 32 and character not in "\t\r\n":
                raise ValueError("SQL contains an invalid control character")
            i += 1

    if not words or words[0] not in {"SELECT", "WITH"}:
        raise ValueError("SQL agent only permits read-only SELECT queries")
    if any(word in _SQL_MUTATING_WORDS for word in words):
        raise ValueError("SQL agent query contains a prohibited operation")
    if any(
        words[index : index + 3] == ["NEXT", "VALUE", "FOR"]
        for index in range(len(words) - 2)
    ):
        raise ValueError("SQL agent query contains a sequence modification")


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
        table_strings += f"  <table name={_quote_xml_schema_attribute(table)}>\n"

        if include_columns:
            columns_string = ""
            for column_name, data_type in columns:
                columns_string += (
                    f"    <column name={_quote_xml_schema_attribute(column_name)} "
                    f"type={_quote_xml_schema_attribute(data_type)} />\n"
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
    _require_read_only_sql(query)
    async with DATABASE_EXECUTION_LOCK:
        result = await trio.to_thread.run_sync(
            pymedphys.mosaiq.execute, connection, query
        )

    return result


async def words_in_mouth_prompting(
    anthropic_client: AsyncAnthropic,
    model: str,
    system_prompt: str,
    appended_user_prompt: str,
    start_of_assistant_prompt: str,
    messages: list[dict[str, Any]] | None = None,
) -> str:
    start_of_assistant_prompt = start_of_assistant_prompt.strip()
    appended_user_prompt = appended_user_prompt.strip()

    if messages:
        messages_to_submit: list[dict[str, Any]] = [
            {"role": item["role"], "content": deepcopy(item["content"])}
            for item in messages
        ]
    else:
        messages_to_submit = []

    print(messages_to_submit)

    if messages_to_submit and messages_to_submit[-1]["role"] == "user":
        messages_to_submit[-1]["content"] += f"\n\n{appended_user_prompt}"
    else:
        messages_to_submit.append({"role": "user", "content": appended_user_prompt})

    messages_to_submit.append(
        {"role": "assistant", "content": start_of_assistant_prompt}
    )

    api_response = await anthropic_client.messages.create(
        system=system_prompt,
        model=model,
        max_tokens=4096,
        messages=messages_to_submit,  # type: ignore[arg-type]
    )

    assert len(api_response.content) == 1
    content_response = api_response.content[0]
    assert isinstance(content_response, TextBlock)

    text: str = content_response.text
    result = start_of_assistant_prompt + text
    print(result)

    return result
