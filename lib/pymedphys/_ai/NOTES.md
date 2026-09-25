# Creating the local Elekta MOSAIQ database

NOTE: All of the below is implemented within the MOSAIQ Claude Chat streamlit
app, and should be able to be undergone by clicking the "Start demo MOSAIQ
server from .bak file" button.

## Create the MSSQL database for MOSAIQ

Move the `db-dump.bak` file into `~/mosaiq-data`

```bash
export MSSQL_SA_PASSWORD=$(openssl rand -hex 24)

# Mount mosaiq-data into the docker image
docker run --platform linux/amd64 \
-v ~/mosaiq-data:/mosaiq-data \
-e "ACCEPT_EULA=Y" \
-e "MSSQL_SA_PASSWORD=$MSSQL_SA_PASSWORD" \
-p 1433:1433 \
-d mcr.microsoft.com/mssql/server:2017-latest
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
