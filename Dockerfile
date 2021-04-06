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


FROM python:3.9 as build

RUN useradd -m user
WORKDIR /home/user
USER user

RUN curl https://pyenv.run | bash
ENV HOME  /home/user
ENV PYENV_ROOT $HOME/.pyenv
ENV PATH $PYENV_ROOT/shims:$PYENV_ROOT/bin:$PATH

RUN pyenv install 3.9.4
RUN /home/user/.pyenv/versions/3.9.4/python -m pip install --upgrade wheel pip

FROM mcr.microsoft.com/mssql/server:latest-ubuntu
ENV ACCEPT_EULA=Y \
    SA_PASSWORD=insecure-pymedphys-mssql-password

COPY --from=build /home/user/.pyenv/versions/3.9.4/ /pymedphys/.venv/

COPY requirements-deploy.txt /pymedphys/requirements-deploy.txt
RUN /pymedphys/.venv/bin/python -m pip install -r /pymedphys/requirements-deploy.txt

COPY . /pymedphys
RUN /pymedphys/.venv/python -m pip install -e .[user,tests]

EXPOSE 80
RUN chmod +x /pymedphys/docker/start.sh

CMD [ "/pymedphys/docker/start.sh" ]
