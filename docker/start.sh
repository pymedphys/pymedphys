#!/bin/bash

/opt/mssql/bin/sqlservr &
P1=$!
python -m pymedphys gui --port $PORT &
P2=$!
wait $P1 $P2
