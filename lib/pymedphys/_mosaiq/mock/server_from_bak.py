# Copyright (C) 2026 Jeff (jdotc1)
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
import re
import subprocess
import time

from pymedphys._imports import pymssql

DATA_DIR_IN_DOCKER_IMAGE = pathlib.Path("/mosaiq-data")


def _require_docker_engine_28_or_newer():
    """Reject Engine versions with unsafe loopback port publishing."""
    try:
        version = subprocess.check_output(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            "Cannot verify Docker Engine version. Docker Engine 28.0.0 or newer "
            "is required before restoring a Mosaiq database."
        ) from exc

    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:\+[0-9A-Za-z.-]+)?", version)
    if match is None or tuple(map(int, match.groups()[:3])) < (28, 0, 0):
        raise RuntimeError(
            f"Docker Engine version {version!r} is unsupported; "
            "Docker Engine 28.0.0 or newer is required for localhost-only "
            "Mosaiq database restoration."
        )


def start_mssql_docker_image_with_bak_restore(
    bak_filepath: pathlib.Path, sa_password: str, database_name="PRACTICE"
):
    _require_docker_engine_28_or_newer()
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
            f"MSSQL_SA_PASSWORD={sa_password}",
            "-p",
            "127.0.0.1:1433:1433",
            "-d",
            "mcr.microsoft.com/mssql/server:2017-latest",
        ]
    )

    for i in range(5):
        try:
            connection = pymssql.connect(
                "localhost",
                "sa",
                password=sa_password,
                port="1433",
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
