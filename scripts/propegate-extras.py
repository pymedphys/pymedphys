# Copyright (C) 2020 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import pathlib

import tomlkit

PYPROJECT_TOML_PATH = (
    pathlib.Path(__file__).resolve().parent.parent.joinpath("pyproject.toml")
)


def main():
    with open(PYPROJECT_TOML_PATH) as f:
        pyproject_contents = tomlkit.loads(f.read())

    deps = pyproject_contents["tool"]["poetry"]["dependencies"]

    extras = {}

    for key in deps:
        value = deps[key]
        comment = value.trivia.comment

        if comment.startswith("# groups"):
            split = comment.split("=")
            assert len(split) == 2
            groups = json.loads(split[-1])

            for group in groups:
                try:
                    extras[group].append(key)
                except KeyError:
                    extras[group] = [key]

    pyproject_contents["tool"]["poetry"]["extras"] = extras

    with open(PYPROJECT_TOML_PATH, "w") as f:
        f.write(tomlkit.dumps(pyproject_contents))


if __name__ == "__main__":
    main()
