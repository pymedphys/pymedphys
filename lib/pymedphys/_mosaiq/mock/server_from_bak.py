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
import subprocess
import time

import pymssql

DATA_DIR_IN_DOCKER_IMAGE = pathlib.Path("/mosaiq-data")


def start_mssql_docker_image_with_bak_restore(
    bak_filepath: pathlib.Path, mssql_sa_password: str, database_name="PRACTICE"
):
    volume_mount_string = f"{bak_filepath.parent}:{DATA_DIR_IN_DOCKER_IMAGE}"

    subprocess.call(
        [
            "docker",
            "run",
            "--platform",
            "linux/amd64",
            "-v",
            volume_mount_string,
            "-e",
            "ACCEPT_EULA=Y",
            "-e",
            f"MSSQL_SA_PASSWORD={mssql_sa_password}",
            "-p",
            "1433:1433",
            "-d",
            "mcr.microsoft.com/mssql/server:2017-latest",
        ]
    )

    for i in range(5):
        try:
            connection = pymssql.connect(
                "localhost",
                "sa",
                password=mssql_sa_password,
                port=1433,
                autocommit=True,
            )
        except pymssql.exceptions.OperationalError as e:
            if i == 4:
                raise

            print(e)

            time.sleep(5)
            continue

        break

    cursor = connection.cursor()

    bak_path_in_docker_image = DATA_DIR_IN_DOCKER_IMAGE / bak_filepath.name
    mdf_path = DATA_DIR_IN_DOCKER_IMAGE / "data.mdf"
    ldf_path = DATA_DIR_IN_DOCKER_IMAGE / "log.ldf"

    sql = f"""\
RESTORE DATABASE {database_name}
FROM DISK = '{bak_path_in_docker_image}'
WITH FILE = 1,
MOVE '{database_name}' TO '{mdf_path}',
MOVE '{database_name}_log' TO '{ldf_path}',
NOUNLOAD, REPLACE, STATS = 1\
"""

    cursor.execute(sql)
    connection.close()
