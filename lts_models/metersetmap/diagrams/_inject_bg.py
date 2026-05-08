"""Inject an opaque white background into each SVG produced by PlantUML.

PlantUML emits SVGs with a transparent canvas. On dark IDE themes the
diagram's black text becomes invisible. This script walks every .svg in
the directory, inserts a white rect after the first <defs> or <g>, and
marks the file as patched so re-running the script is a no-op.

Idempotent via the <!--bg-injected--> sentinel comment. Re-running
PlantUML strips the sentinel, so this script must run AFTER every render.
"""

import glob
import os
import re

os.chdir(os.path.dirname(os.path.abspath(__file__)))

for path in glob.glob("*.svg"):
    with open(path, encoding="utf-8") as f:
        content = f.read()

    if "<!--bg-injected-->" in content:
        continue

    new_content = re.sub(
        r"(<defs/>\s*<g>|</defs>\s*<g>)",
        r'\1<!--bg-injected--><rect x="0" y="0" width="100%" height="100%" fill="#FFFFFF"/>',
        content,
        count=1,
    )

    if new_content != content:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(new_content)
        print(f"injected bg into {path}")
    else:
        print(f"no <defs>/<g> match in {path}; skipped")
