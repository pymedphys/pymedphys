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


"""Fleshes out CSV files found within the data directory from a .bak file.

By design, only tables and columns that have been defined within
`data/types_map.toml` are extracted so as to not expose any more of the
underlying database schema than what is already within the repository.
"""

import base64
import os
import secrets
from pathlib import Path

from pymedphys._imports import pandas as pd

import pymedphys

from . import paths, utilities
from .server_from_bak import start_mssql_docker_image_with_bak_restore
from .utilities import load_csv_and_toml

DEFAULT_BAK_FILEPATH = Path().home() / "mosaiq-data" / "db-dump.bak"
QUERY_TEMPLATE = """\
SELECT {columns}
FROM {table_name}
"""


def extract(
    bak_filepath: Path = DEFAULT_BAK_FILEPATH,
    sa_password: str | None = None,
    database_name: str = "PRACTICE",
):
    if sa_password is None:
        sa_password = os.getenv("MSSQL_SA_PASSWORD", default=secrets.token_urlsafe())

    start_mssql_docker_image_with_bak_restore(
        bak_filepath=bak_filepath,
        sa_password=sa_password,
        database_name=database_name,
    )

    current_tables, types_map = load_csv_and_toml()
    sql_types_map = utilities.get_sqlalchemy_types_map()

    with pymedphys.mosaiq.connect(
        "localhost",
        port=1433,
        database=database_name,
        username="sa",
        password=sa_password,
    ) as connection:
        for table_name, df in current_tables.items():
            column_names = []
            for column_name in df.columns:
                if column_name == "Index":
                    column_name = "[Index]"

                column_names.append(column_name)

            columns_string = ",".join(column_names)

            query = QUERY_TEMPLATE.format(columns=columns_string, table_name=table_name)
            print(query)
            rows = pymedphys.mosaiq.execute(connection, query)

            if not rows:
                continue

            df_with_new_rows = pd.DataFrame(data=rows, columns=df.columns)

            for column_name in df.columns:
                if types_map[table_name][column_name] == sql_types_map["largebinary"]:
                    df_with_new_rows[column_name] = df_with_new_rows[column_name].apply(
                        lambda x: base64.urlsafe_b64encode(x).decode()
                    )

            updated_df = pd.concat([df, df_with_new_rows], ignore_index=True)
            updated_df.to_csv(paths.DATA / f"{table_name}.csv")


if __name__ == "__main__":
    print(extract())


# uv run -- python -m pymedphys._mosaiq.mock.extract_from_bak
