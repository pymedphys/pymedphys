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

COPY . /pymedphys
RUN python -m pip install -e /pymedphys/.[user,tests]

RUN pyenv rehash

EXPOSE 8501
RUN chmod +x /pymedphys/docker/start.sh

ENV ACCEPT_EULA=Y \
    SA_PASSWORD=Insecure-PyMedPhys-MSSQL-Passw0rd

CMD [ "/pymedphys/docker/start.sh" ]
