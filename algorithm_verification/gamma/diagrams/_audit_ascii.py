"""ASCII audit for the .puml files in this directory.

PlantUML on Windows defaults to a Cp1252 file decoder. UTF-8 multi-byte
characters in .puml files are read as Latin-1 and rendered as mojibake
(`â†'`, `&#8217;`, `&#65533;` in the output SVG).

This script verifies every .puml file is pure ASCII. Exit status:
  0  -- all .puml files are pure ASCII
  1  -- one or more files contain non-ASCII bytes (offending lines printed)

Run after editing any .puml; CI/quality-gate hook.
"""

import glob
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

failures = []

for path in sorted(glob.glob("*.puml")):
    with open(path, "rb") as f:
        raw = f.read()
    try:
        raw.decode("ascii")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if any(ord(ch) > 127 for ch in line):
                offending = "".join(
                    f"\\u{ord(ch):04x}" if ord(ch) > 127 else ch for ch in line
                )
                failures.append((path, line_no, offending))

if failures:
    print("FAIL -- non-ASCII bytes detected:")
    for path, line_no, line in failures:
        print(f"  {path}:{line_no}  {line}")
    sys.exit(1)

print("OK -- all puml files are pure ASCII")
