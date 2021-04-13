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


import functools
import pathlib

from pymedphys._imports import pandas as pd
from pymedphys._imports import sqlalchemy, toml

from . import mocks

HERE = pathlib.Path(__file__).parent

DATABASE = "MosaiqMimicsTest"


def create_mimic_tables(database):
    tables, types_map = _load_csv_and_toml()

    for table_name, table in tables.items():
        column_types = types_map[table_name]
        index_label = table.columns[0]
        table = table.set_index(index_label)
        table = table.drop(columns=["RowVers"])

        mocks.dataframe_to_sql(
            table,
            table_name,
            index_label=index_label,
            dtype=column_types,
            database=database,
            if_exists="append",
        )


def create_db_with_tables():
    mocks.check_create_test_db(database=DATABASE)
    create_mimic_tables(DATABASE)


@functools.lru_cache()
def _load_csv_and_toml():
    csv_paths = HERE.glob("*.csv")
    toml_path = HERE.joinpath("types_map.toml")

    tables = {}
    for path in csv_paths:
        tables[path.stem] = pd.read_csv(path, index_col=0)

    with open(toml_path) as f:
        types_map = toml.load(f)

    for table, column_type_map in types_map.items():
        for column, type_repr in column_type_map.items():
            types_map[table][column] = _get_sql_type(type_repr)

    return tables, types_map


@functools.lru_cache()
def _get_sqlalchemy_types_map():
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
    sql_types_map = {
        item.lower(): getattr(sqltypes, item)
        for item in dir(sqltypes)
        if item[0].isupper()
    }

    return sql_types_map


def _get_sql_type(sql_type: str):
    sql_type = str(sql_type).lower()
    sqlalchemy_types_map = _get_sqlalchemy_types_map()

    return sqlalchemy_types_map[sql_type]
