# Copyright (C) 2026 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Print the key of the documentation build's executed-notebook cache.

The documentation workflow keeps jupyter-cache's store between runs, so that
notebooks are not executed again when nothing they can read has changed. The
key covers everything execution can read:

- every tracked file under ``lib/pymedphys``: the package and its data
  manifest, the notebooks, the documentation configuration, and any file a
  notebook opens;
- ``pyproject.toml`` and ``uv.lock``;
- the interpreter and the runner image.

Documentation prose is left out, so that editing it reuses the outputs:
``.rst`` pages, and ``.md`` pages without YAML front matter, which is the only
way myst-nb reads a Markdown page as a notebook. The workflow restores only an
exact key, never a partial match.

Run it with the documentation environment's interpreter; it prints
``hash=<hex digest>`` for ``$GITHUB_OUTPUT``.
"""

import hashlib
import os
import platform
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping
from pathlib import PurePosixPath

INPUT_PATHS = ("pyproject.toml", "uv.lock", "lib/pymedphys")
DOC_ROOT = "lib/pymedphys/docs/"
PROSE_SUFFIXES = frozenset({".md", ".rst"})
# The runner image; its version changes when the image is updated.
IMAGE_VARIABLES = ("ImageOS", "ImageVersion")


def is_prose(path: str, read_head: Callable[[str], bytes]) -> bool:
    """Whether a tracked file is documentation prose that is never executed."""
    suffix = PurePosixPath(path).suffix
    if not path.startswith(DOC_ROOT) or suffix not in PROSE_SUFFIXES:
        return False
    return suffix == ".rst" or not read_head(path).startswith(b"---")


def cache_key(
    entries: Iterable[str],
    read_head: Callable[[str], bytes],
    interpreter: str,
    environment: Mapping[str, str],
) -> str:
    """Hash the index entries of the execution inputs and the interpreter.

    Each entry is a ``git ls-files --stage`` record, ``<mode> <object>
    <stage>\\t<path>``, so the key follows the committed content without
    reading every file.
    """
    digest = hashlib.sha256()
    for entry in entries:
        _, path = entry.split("\t", 1)
        if not is_prose(path, read_head):
            digest.update(entry.encode() + b"\0")
    digest.update(interpreter.encode() + b"\0")
    for name in IMAGE_VARIABLES:
        digest.update(f"{name}={environment.get(name, '')}".encode() + b"\0")
    return digest.hexdigest()


def tracked_entries() -> list[str]:
    listing = subprocess.check_output(
        ["git", "ls-files", "--stage", "-z", "--", *INPUT_PATHS]
    )
    return [entry.decode("utf-8") for entry in listing.split(b"\0") if entry]


def _read_head(path: str) -> bytes:
    with open(path, "rb") as file:
        return file.read(3)


def main() -> None:
    interpreter = f"{sys.version} {platform.machine()}"
    key = cache_key(tracked_entries(), _read_head, interpreter, os.environ)
    print(f"hash={key}")


if __name__ == "__main__":
    main()
