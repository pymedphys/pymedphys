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


# import pathlib
import functools

from pymedphys._imports import sqlalchemy


@functools.lru_cache()
def _get_sqlalchemy_types_map():
    sqltypes = sqlalchemy.dialects.mssql.pymssql.sqltypes
    sqlalchemy_types_map = {item.lower() for item in dir(sqltypes) if item[0].isupper()}
    return sqlalchemy_types_map


def _get_sql_type(sql_type: str):
    sql_type = str(sql_type).lower()
    sqlalchemy_types_map = _get_sqlalchemy_types_map()

    return sqlalchemy_types_map[sql_type]
