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
import logging

from pymedphys._imports import pymssql

from . import generate, utilities

DATABASE_NAME = "MosaiqFromCsv"

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
    "largebinary",
    "bit",
}

# Not knowing particularly why, I was unable to load values in as "char"
# or "timestamp". This is a work-a-round to just map those types to
# something else for now.
TYPE_CASTING = {
    "char": "varchar",
    "timestamp": "largebinary",
    "binary": "largebinary",
}


def create_db_with_tables_from_csv():
    """Creates testing database if it doesn't exist, and then loads in
    the Mosaiq mimic tables.
    """
    generate.create_test_db(database=DATABASE_NAME)
    create_tables_from_csv(DATABASE_NAME)


def create_tables_from_csv(database):
    """Creates MSSQL tables for testing that mimic a Mosaiq DB.

    Pulls data from the *.csv files and types_map.toml file within this
    same directory and loads them into an MSSQL database.
    """
    # https://github.com/pymssql/pymssql/issues/504#issuecomment-449746112
    pymssql.Binary = bytearray

    sql_types_map = utilities.get_sqlalchemy_types_map()
    tables, types_map = utilities.load_csv_and_toml()
    column_types_to_use = [sql_types_map[item] for item in COLUMN_TYPES_TO_USE]
    type_casting = {
        sql_types_map[key]: sql_types_map[item] for key, item in TYPE_CASTING.items()
    }

    for table_name, table in tables.items():
        logging.debug("Creating mimic table for %s", table_name)

        column_types = types_map[table_name]
        for column_name, a_type in column_types.items():
            try:
                column_types[column_name] = type_casting[a_type]
            except KeyError:
                pass

        index_label = table.columns[0]
        table = table.set_index(index_label)

        for column_name, a_type in column_types.items():
            if a_type not in column_types_to_use:
                table = table.drop(columns=[column_name])
                continue

            if a_type == sql_types_map["largebinary"]:
                table[column_name] = table[column_name].apply(
                    lambda x: base64.decodebytes(x.encode("utf-8"))
                )
                continue

        generate.dataframe_to_sql(
            table,
            table_name,
            index_label=index_label,
            dtype=column_types,
            database=database,
            if_exists="replace",
        )
