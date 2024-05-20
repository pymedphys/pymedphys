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

from pathlib import Path

from .server_from_bak import start_mssql_docker_image_with_bak_restore
from .utilities import load_tables


def extract(
    bak_filepath: Path, mssql_sa_password: str, database_name: str = "PRACTICE"
):
    start_mssql_docker_image_with_bak_restore(
        bak_filepath=bak_filepath,
        mssql_sa_password=mssql_sa_password,
        database_name=database_name,
    )


def get_currently_exposed_schema():
    current_tables = load_tables()

    schema = {}
    for table_name, dataframe in current_tables.items():
        schema[table_name] = dataframe.columns.to_list()

    return schema


if __name__ == "__main__":
    print(get_currently_exposed_schema())


# poetry run python -m pymedphys._mosaiq.mock.extract_from_bak
