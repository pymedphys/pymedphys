# Copyright (C) 2026 Jeffrey D. Cooney
# Copyright (C) 2018 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Create a reproducible hash from a filepath."""

import hashlib


def hash_fileobj(file_obj, dot_feedback=False):
    """Hash a preopened binary file without resolving or reopening its path."""
    hasher = hashlib.sha1(usedforsecurity=False)
    while chunk := file_obj.read(65536):
        hasher.update(chunk)

    if dot_feedback:
        print(".", end="", flush=True)

    return hasher.hexdigest()


def hash_file(filename, dot_feedback=False):
    """Hash a file by pathname; prefer hash_fileobj for validated open handles."""
    with open(filename, "rb") as afile:
        return hash_fileobj(afile, dot_feedback=dot_feedback)
