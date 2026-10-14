"""Keep synthetic incoming logfiles until their archived copy is confirmed."""

import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize("optimization", ["", "-O"])
def test_archive_checksum_guard_with_optimized_python(tmp_path, optimization):
    script = r"""
import pathlib
import sys
from pymedphys._trf.manage.index import file_already_in_index
from pymedphys._utilities.filehash import hash_file

root = pathlib.Path(sys.argv[1])
incoming = root / "incoming.trf"
archived = root / "archived.trf"
incoming.write_bytes(b"synthetic intact record")
archived.write_bytes(b"different archived bytes")
expected_hash = hash_file(incoming)
try:
    file_already_in_index(archived, incoming, expected_hash)
except AssertionError as error:
    if str(error) != "The located file doesn't agree with the index hash.":
        raise
else:
    raise RuntimeError("Checksum mismatch was accepted")
if incoming.read_bytes() != b"synthetic intact record":
    raise RuntimeError("Incoming logfile changed after mismatch")
archived.write_bytes(incoming.read_bytes())
file_already_in_index(archived, incoming, expected_hash)
if incoming.exists():
    raise RuntimeError("Matching duplicate was not removed")
"""
    command = [sys.executable]
    if optimization:
        command.append(optimization)
    command.extend(["-c", script, str(tmp_path)])
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(sys.path)
    result = subprocess.run(command, env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
