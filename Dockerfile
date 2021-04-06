# Copyright (C) 2021 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

FROM debian:stretch-slim AS build
# Adapted from https://github.com/justin2004/mssql_server_tiny/blob/7ca5bc1eb3a302d43030c45206bf3d64da34b1d1/Dockerfile
WORKDIR /root

RUN apt-get update && apt-get install -y binutils gcc

COPY docker/wrapper.c wrapper.c
RUN gcc -shared  -ldl -fPIC -o wrapper.so wrapper.c


FROM debian:stretch-slim AS dos2unix
WORKDIR /root

RUN apt-get update && apt-get install -y dos2unix

COPY docker /pymedphys/docker
RUN dos2unix /pymedphys/docker/*.sh
RUN chmod +x /pymedphys/docker/*.sh


FROM python:3.9-slim AS downloads
WORKDIR /root

RUN pip install pymedphys tqdm
COPY lib/pymedphys/_data /usr/local/lib/python3.9/site-packages/pymedphys/_data
COPY docker/download.py /pymedphys/docker/download.py
RUN python /pymedphys/docker/download.py


FROM mcr.microsoft.com/mssql/server:latest-ubuntu

RUN \
    apt-get update --fix-missing && \
    apt-get install --fix-missing -y make build-essential libssl-dev zlib1g-dev libbz2-dev \
    libreadline-dev libsqlite3-dev wget curl llvm libncurses5-dev libncursesw5-dev \
    xz-utils tk-dev libffi-dev liblzma-dev python-openssl git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

ENV HOME /root

RUN curl https://pyenv.run | bash
ENV PYENV_ROOT $HOME/.pyenv
ENV PATH $PYENV_ROOT/shims:$PYENV_ROOT/bin:$PATH

ENV PYTHON_VERSION=3.9.4
RUN pyenv install $PYTHON_VERSION
RUN pyenv global $PYTHON_VERSION
RUN python -m pip install --upgrade wheel pip
RUN pyenv rehash

COPY requirements-deploy.txt /pymedphys/requirements-deploy.txt
RUN python -m pip install -r /pymedphys/requirements-deploy.txt

COPY --from=downloads /root/.pymedphys /root/.pymedphys
COPY --from=dos2unix /pymedphys/docker /pymedphys/docker

EXPOSE 8501

ENV ACCEPT_EULA=Y \
    SA_PASSWORD=Insecure-PyMedPhys-MSSQL-Passw0rd \
    MSSQL_MEMORY_LIMIT_MB=128

COPY --from=build /root/wrapper.so /root/wrapper.so

RUN \
    LD_PRELOAD=/root/wrapper.so /opt/mssql/bin/sqlservr & \
    /pymedphys/docker/wait-for-it.sh localhost:1433 -t 120

COPY lib /pymedphys/lib
COPY setup.py  /pymedphys/setup.py
RUN python -m pip install -e /pymedphys/.[user,tests]
RUN pyenv rehash

COPY . /pymedphys

CMD [ "/pymedphys/docker/start.sh" ]
