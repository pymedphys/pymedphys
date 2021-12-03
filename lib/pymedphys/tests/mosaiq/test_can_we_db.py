# Copyright (C) 2021 Derek Lane

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from pymedphys._imports import pymssql, pytest

from . import _connect


@pytest.mark.mosaiqdb
def test_can_we_db():
    conn = pymssql.connect(
        _connect.MSQ_SERVER,
        port=_connect.MSQ_PORT,
        user=_connect.SA_USER,
        password=_connect.SA_PASSWORD,
    )
    cursor = conn.cursor()
    cursor.execute("select * from sys.databases")

    # should print the four system databases
    databases = list(cursor)
    print(databases)

    # and check that the correct number are present
    assert len(databases) >= 4
