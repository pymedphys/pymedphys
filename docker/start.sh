#!/bin/bash

if [[ -z $PORT ]]; then
  PORT_TO_USE=8501
else
  PORT_TO_USE=$PORT
fi

LD_PRELOAD=/root/wrapper.so /opt/mssql/bin/sqlservr &
P1=$!
/pymedphys/docker/wait-for-it.sh localhost:1433 -t 120 && \
    python -m pymedphys gui --port $PORT_TO_USE &
P2=$!
wait $P1 $P2
