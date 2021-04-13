# Copyright (C) 2021 Derek Lane, Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import contextlib

import pymedphys

MSQ_SERVER = "."
TEST_DB_NAME = "MosaiqTest77008"
MIMIC_DB_NAME = "MosaiqMimicTest"

SA_USER = "sa"
SA_PASSWORD = "sqlServerPassw0rd"


@contextlib.contextmanager
def connect(database=TEST_DB_NAME):
    connection = pymedphys.mosaiq.connect(
        MSQ_SERVER,
        port=1433,
        database=database,
        username=SA_USER,
        password=SA_PASSWORD,
    )

    try:
        yield connection
    finally:
        connection.close()
