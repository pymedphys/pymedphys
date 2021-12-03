# Copyright (C) 2020 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from pymedphys._imports import natsort


def iterate_over_columns(dataframe, data, columns, callbacks, previous=tuple()):
    column = columns[0]
    callback = callbacks[0]

    sorted_items = natsort.natsorted(dataframe[column].unique())
    for item in sorted_items:
        filtered_dataframe = filter_by(dataframe, column, item)
        if len(filtered_dataframe) == 0:
            continue

        args = previous + (item,)

        if callback is not None:
            callback(filtered_dataframe, data, *args)

        if len(columns) > 1:
            iterate_over_columns(
                filtered_dataframe, data, columns[1:], callbacks[1:], previous=args
            )


def filter_by(dataframe, column, value):
    filtered = dataframe.loc[dataframe[column] == value]

    return filtered
