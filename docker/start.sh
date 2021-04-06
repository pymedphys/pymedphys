#!/bin/bash

/opt/mssql/bin/sqlservr &
P1=$!
/pymedphys/.venv/bin/python -m pymedphys gui &
P2=$!
wait $P1 $P2
