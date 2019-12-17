# Copyright (C) 2019 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from glob import glob


def wildcard_file_resolution(glob_search_string):
    filepaths = glob(glob_search_string)
    if len(filepaths) < 1:
        raise FileNotFoundError("No file found that matches the provided path")

    if len(filepaths) > 1:
        raise TypeError("More than one file found that matches the search string")

    found_filepath = filepaths[0]

    return found_filepath
