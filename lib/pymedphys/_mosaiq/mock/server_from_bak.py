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

import json
import os
import pathlib
import re
import subprocess
import time

from pymedphys._imports import pymssql

DATA_DIR_IN_DOCKER_IMAGE = pathlib.Path("/mosaiq-data")
_MSSQL_IMAGE = "mcr.microsoft.com/mssql/server:2017-latest"


def _docker_command():
    """Pin the daemon selection across the version, inspection, and run calls."""
    if os.environ.get("DOCKER_CONTEXT"):
        return ["docker", "--context", os.environ["DOCKER_CONTEXT"]]
    if os.environ.get("DOCKER_HOST"):
        return ["docker", "--host", os.environ["DOCKER_HOST"]]

    try:
        context = subprocess.check_output(
            ["docker", "context", "show"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("Cannot determine the active Docker context.") from exc
    if not context:
        raise RuntimeError("Cannot determine the active Docker context.")
    return ["docker", "--context", context]


def _require_docker_engine_28_or_newer(docker_command):
    """Reject Engine versions with unsafe loopback port publishing."""
    try:
        version = subprocess.check_output(
            [*docker_command, "version", "--format", "{{.Server.Version}}"],
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


def _stop_previous_restore_containers(docker_command, bak_filepath):
    """Replace only recognised restore containers; never stop unrelated services."""
    try:
        container_ids = subprocess.check_output(
            [
                *docker_command,
                "ps",
                "--filter",
                "publish=1433/tcp",
                "--format",
                "{{.ID}}",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        ).split()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("Cannot check Docker containers using port 1433.") from exc

    for container_id in container_ids:
        try:
            inspected = subprocess.check_output(
                [*docker_command, "inspect", "--type", "container", container_id],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            (container,) = json.loads(inspected)
            bindings = container["NetworkSettings"]["Ports"].get("1433/tcp") or []
            if not any(binding["HostPort"] == "1433" for binding in bindings):
                continue
            matching_image = container["Config"]["Image"] == _MSSQL_IMAGE
            matching_mount = any(
                mount.get("Destination") == str(DATA_DIR_IN_DOCKER_IMAGE)
                and os.path.realpath(mount.get("Source", ""))
                == os.path.realpath(bak_filepath.parent)
                for mount in container["Mounts"]
            )
        except (
            OSError, subprocess.CalledProcessError, ValueError, TypeError, KeyError
        ) as exc:
            raise RuntimeError(
                "Cannot verify the owner of Docker port 1433; refusing to restore."
            ) from exc

        if not (matching_image and matching_mount):
            raise RuntimeError(
                "Docker port 1433 is already published by an unrelated container; "
                "stop it manually before restoring a Mosaiq database."
            )
        # The pre-fix helper launched unnamed containers with this image and mount.
        # Stop but do not remove the old container or its stored patient data.
        try:
            subprocess.run(
                [*docker_command, "stop", container_id],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RuntimeError(
                "Cannot stop the previous Mosaiq restore container; "
                "refusing to restore."
            ) from exc


def start_mssql_docker_image_with_bak_restore(
    bak_filepath: pathlib.Path, sa_password: str, database_name="PRACTICE"
):
    docker_command = _docker_command()
    _require_docker_engine_28_or_newer(docker_command)
    _stop_previous_restore_containers(docker_command, bak_filepath)
    volume_mount_string = f"{bak_filepath.parent}:{DATA_DIR_IN_DOCKER_IMAGE}"

    try:
        subprocess.run(
            [
                *docker_command,
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
                _MSSQL_IMAGE,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            "Cannot start the loopback-only Mosaiq SQL Server container; "
            "refusing to connect to an existing service on port 1433."
        ) from exc

    for i in range(5):
        try:
            connection = pymssql.connect(
                "127.0.0.1",
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
