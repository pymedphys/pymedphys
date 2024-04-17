# Creating the local Elekta MOSAIQ database

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

```bash
brew install sqlcmd

sqlcmd -S localhost -U "sa" -P $MSSQL_SA_PASSWORD
```

```sql
RESTORE DATABASE PRACTICE
FROM DISK = '/mosaiq-data/db-dump.bak'
WITH FILE = 1,
MOVE 'PRACTICE' TO '/mosaiq-data/data.mdf',
MOVE 'PRACTICE_log' TO '/mosaiq-data/log.ldf',
NOUNLOAD, REPLACE, STATS = 1
GO

USE PRACTICE
SELECT TABLE_NAME FROM information_schema.tables
GO
```
