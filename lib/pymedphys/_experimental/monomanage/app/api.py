# Copyright (C) 2019 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os

from .wheels import build_wheels_with_yarn, copy_wheels


def package_wheels(pymedphys_dir):
    app_directory = os.path.join(pymedphys_dir, "app")
    wheels_directory = os.path.join(app_directory, "public", "python-wheels")

    packages_directory = os.path.join(pymedphys_dir, "packages")

    build_wheels_with_yarn()
    copy_wheels(packages_directory, wheels_directory)
