# Copyright (C) 2021 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import base64
import functools
import pathlib
from typing import Dict, Tuple, cast

from pymedphys._imports import pandas as pd
from pymedphys._imports import pymssql, sqlalchemy, toml

from . import mocks

HERE = pathlib.Path(__file__).parent
DATABASE = "MosaiqMimicsTest002"

# The following set is so that table types can be added and removed. In
# the case where the CSV format can't be input into the MSSQL database
# the column types can be selectively added and removed here with the
# aim to troubleshoot what conversions may be needed.
# eg 'binary' has been stored as b64 strings so that it is reproducible.
COLUMN_TYPES_TO_USE = {
    "int",
    "smallint",
    "varchar",
    "datetime",
    "tinyint",
    "bigint",
    "float",
    "decimal",
    "binary",
    "bit",
}

# Not knowing particularly why, I was unable to load values in as "char"
# or "timestamp". This is a work-a-round to just map those types to
# something else for now.
TYPE_CASTING = {
    "char": "varchar",
    "timestamp": "binary",
}


def create_mimic_tables(database):
    """Creates MSSQL tables for testing that mimic a Mosaiq DB.

    Pulls data from the *.csv files and types_map.toml file within this
    same directory and loads them into an MSSQL database.
    """
    # https://github.com/pymssql/pymssql/issues/504#issuecomment-449746112
    pymssql.Binary = bytearray

    sql_types_map = _get_sqlalchemy_types_map()
    tables, types_map = _load_csv_and_toml()
    column_types_to_use = [sql_types_map[item] for item in COLUMN_TYPES_TO_USE]
    type_casting = {
        sql_types_map[key]: sql_types_map[item] for key, item in TYPE_CASTING.items()
    }

    for table_name, table in tables.items():
        column_types = types_map[table_name]
        for column_name, a_type in column_types.items():
            try:
                column_types[column_name] = type_casting[a_type]
            except KeyError:
                pass

        index_label = table.columns[0]
        table = table.set_index(index_label)

        for column_name, a_type in column_types.items():
            if not a_type in column_types_to_use:
                table = table.drop(columns=[column_name])
                continue

            if a_type == sql_types_map["binary"]:
                table[column_name] = table[column_name].apply(
                    lambda x: base64.decodebytes(x.encode("utf-8"))
                )
                continue

        mocks.dataframe_to_sql(
            table,
            table_name,
            index_label=index_label,
            dtype=column_types,
            database=database,
            if_exists="replace",
        )


def create_db_with_tables():
    """Creates testing database if it doesn't exist, and then loads in
    the Mosaiq mimic tables.
    """
    mocks.check_create_test_db(database=DATABASE)
    create_mimic_tables(DATABASE)


@functools.lru_cache()
def _load_csv_and_toml() -> Tuple[Dict[str, "pd.DataFrame"], Dict[str, Dict[str, str]]]:
    """Loads the *.csv files and types_map.toml file that are within
    this directory.
    """
    csv_paths = HERE.glob("*.csv")
    toml_path = HERE.joinpath("types_map.toml")

    with open(toml_path) as f:
        types_map = toml.load(f)

    for table, column_type_map in types_map.items():
        for column, type_repr in column_type_map.items():
            types_map[table][column] = _get_sql_type(type_repr)

    types_map = cast(Dict[str, Dict[str, str]], types_map)

    tables: Dict[str, "pd.DataFrame"] = {}
    for path in csv_paths:
        table_name = path.stem
        # column_types = types_map[table_name]
        tables[table_name] = pd.read_csv(
            path,
            index_col=0,
            # dtype=column_types,
        )

    return tables, types_map


@functools.lru_cache()
def _get_sqlalchemy_types_map():
    """Load up a map that converts string representations of SQLAlchemy
    types and maps them to their SQLAlchemy instance.
    """
    mssql_types = sqlalchemy.dialects.mssql
    mssql_types_map = _create_types_map(mssql_types)

    pymssql_types = sqlalchemy.dialects.mssql.pymssql.sqltypes
    pymssql_types_map = _create_types_map(pymssql_types)

    sqlalchemy_types_map = {
        **mssql_types_map,
        **pymssql_types_map,
    }
    return sqlalchemy_types_map


def _create_types_map(sqltypes):
    """Take a types module and utilising the `dir` function create a
    mapping from the string value of that attribute to the SQLAlchemy
    type instance.
    """
    sql_types_map = {
        item.lower(): getattr(sqltypes, item)
        for item in dir(sqltypes)
        if item[0].isupper()
    }

    return sql_types_map


def _get_sql_type(sql_type: str):
    """Convert an SQL type labelled as a string to an SQLAlchemy type
    instance."""
    sql_type = str(sql_type).lower()
    sqlalchemy_types_map = _get_sqlalchemy_types_map()

    return sqlalchemy_types_map[sql_type]
