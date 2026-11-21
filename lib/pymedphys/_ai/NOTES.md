# Creating the local Elekta MOSAIQ database

These are developer notes for the older `.bak` restoration workflow. The
current draft **MOSAIQ Claude Chat** app has a **Fill database with CSV records**
button; it does not expose the former **Start demo MOSAIQ server from .bak file**
button. See `lib/pymedphys/_mosaiq/mock/from_csv.py` for that app's database
setup. The SQL Server 2017 example below is separate from the SQL Server 2022
container used by the current database CI workflow.

## Create the MSSQL database for MOSAIQ

**Security prerequisite:** Docker Engine 28.0.0 or newer is required for this
restoration workflow. Older Engines can allow devices on the same layer-2
network to reach ports published to `127.0.0.1`. The shell commands below
check the server version and pin one Docker target for both verification and
container startup. The Python restoration helper enforces the same requirement.
If an earlier restore container already occupies host port 1433, stop that
container before running the manual steps. Do not reuse an earlier container
whose port binding has not been verified.

Move the `db-dump.bak` file into `~/mosaiq-data`.

```bash
# Pin the selected Docker target so switching contexts cannot bypass the check.
docker_cmd=(docker)
if [[ -n ${DOCKER_CONTEXT:-} ]]; then
    docker_cmd+=(--context "$DOCKER_CONTEXT")
elif [[ -n ${DOCKER_HOST:-} ]]; then
    docker_cmd+=(--host "$DOCKER_HOST")
else
    docker_context=$(docker context show) || exit 1
    [[ -n $docker_context ]] || { echo "No Docker context selected" >&2; exit 1; }
    docker_cmd+=(--context "$docker_context")
fi

engine_version=$("${docker_cmd[@]}" version --format '{{.Server.Version}}') || {
    echo "Cannot verify Docker Engine version; restore aborted" >&2
    exit 1
}
if [[ $engine_version =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)(\+[0-9A-Za-z.-]+)?$ ]]; then
    engine_major=${BASH_REMATCH[1]}
else
    engine_major=0
fi
if (( 10#$engine_major < 28 )); then
    echo "Docker Engine 28.0.0+ required; got ${engine_version}" >&2
    exit 1
fi

export MSSQL_SA_PASSWORD=$(openssl rand -hex 24)

# Mount mosaiq-data into the Docker image, exposing SQL only on loopback.
"${docker_cmd[@]}" run --platform linux/amd64 \
-v ~/mosaiq-data:/mosaiq-data \
-e "ACCEPT_EULA=Y" \
-e "MSSQL_SA_PASSWORD=$MSSQL_SA_PASSWORD" \
-p 127.0.0.1:1433:1433 \
-d mcr.microsoft.com/mssql/server:2017-latest || {
    echo "Container startup failed; do not proceed with restoration" >&2
    exit 1
}
```

Restoring the practice database from within Python

```python
import os
import pymssql

connection = pymssql.connect(
    'localhost', 'sa', password=os.environ['MSSQL_SA_PASSWORD'], port=1433)
cursor = connection.cursor()

# Enables restoring from backups with pymssql
connection.autocommit(True)

sql = """\
RESTORE DATABASE PRACTICE
FROM DISK = '/mosaiq-data/db-dump.bak'
WITH FILE = 1,
MOVE 'PRACTICE' TO '/mosaiq-data/data.mdf',
MOVE 'PRACTICE_log' TO '/mosaiq-data/log.ldf',
NOUNLOAD, REPLACE, STATS = 1\
"""

cursor.execute(sql)
connection.close()

# Test that backup worked with standard PyMedPhys tooling

from pymedphys.mosaiq import connect, execute

connection = connect(
    'localhost',
    database='PRACTICE',
    username='sa',
    password=os.environ['MSSQL_SA_PASSWORD']
)

execute(connection, "SELECT TABLE_NAME FROM information_schema.tables")
connection.close()
```

## Usage of Anthropic API

Make sure to set `ANTHROPIC_API_KEY` as environment variable.
