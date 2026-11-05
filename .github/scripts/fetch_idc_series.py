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

"""Download series from NCI Imaging Data Commons' public bucket.

Each series is a folder of the ``idc-open-data`` bucket named by its
``crdc_series_uuid``, served anonymously over HTTPS by Amazon S3. This lists
each folder with S3's ListObjectsV2, page by page, and downloads each file
into ``<out>/<uuid>/``, retrying a failed request. It checks nothing of the
files' content: the check that reads them compares each series' digest
with the one that it pins.

Run as ``python .github/scripts/fetch_idc_series.py --out DIR UUID ...``.
Only the standard library is used, so that it runs before the project's
environment is installed.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Sequence

BUCKET = "https://idc-open-data.s3.amazonaws.com/"
_NAMESPACE = "{http://s3.amazonaws.com/doc/2006-03-01/}"
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_ATTEMPTS = 5
_WORKERS = 16


def _get(url: str, timeout: float = 120.0) -> bytes:
    """The body of a GET, retried with a growing wait."""
    for attempt in range(_ATTEMPTS):
        try:
            # Only the fixed https bucket URL is ever opened.
            with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
                return response.read()
        except OSError:
            if attempt == _ATTEMPTS - 1:
                raise
            time.sleep(2 ** (attempt + 1))
    raise AssertionError("unreachable")


def keys(uuid: str) -> list[str]:
    """Every object key under a series' folder, page by page."""
    found: list[str] = []
    token = None
    while True:
        query = {"list-type": "2", "prefix": f"{uuid}/"}
        if token:
            query["continuation-token"] = token
        root = ET.fromstring(_get(BUCKET + "?" + urllib.parse.urlencode(query)))
        found += [key.text or "" for key in root.iter(f"{_NAMESPACE}Key") if key.text]
        truncated = root.findtext(f"{_NAMESPACE}IsTruncated") == "true"
        token = root.findtext(f"{_NAMESPACE}NextContinuationToken")
        if not truncated or not token:
            return found


def fetch(uuid: str, out: pathlib.Path) -> int:
    """Download one series into ``out / uuid``, and return its file count."""
    if not _UUID.fullmatch(uuid):
        raise SystemExit(f"Not a series UUID: {uuid!r}.")
    folder = out / uuid
    folder.mkdir(parents=True, exist_ok=False)
    names = keys(uuid)
    if not names:
        raise SystemExit(f"The bucket holds nothing for series {uuid}.")

    def download(key: str) -> None:
        name = key.rsplit("/", 1)[-1]
        if not name or name.startswith(".") or "/" in name or "\\" in name:
            raise SystemExit(f"Unexpected object name in series {uuid}.")
        (folder / name).write_bytes(_get(BUCKET + urllib.parse.quote(key)))

    with concurrent.futures.ThreadPoolExecutor(_WORKERS) as pool:
        list(pool.map(download, names))
    return len(names)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, help="A directory for the series.")
    parser.add_argument("series", nargs="+", help="Each series' crdc_series_uuid.")
    arguments = parser.parse_args(argv)
    out = pathlib.Path(arguments.out)
    for uuid in arguments.series:
        print(f"{uuid}: {fetch(uuid, out)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
