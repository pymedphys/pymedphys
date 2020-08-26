# pylint: disable = pointless-statement, pointless-string-statement
# pylint: disable = no-value-for-parameter, expression-not-assigned
# pylint: disable = too-many-lines, redefined-outer-name


import pathlib

import streamlit as st

from pymedphys._streamlit import rerun as st_rerun

st_rerun.autoreload(st_rerun)

HERE = pathlib.Path(__file__).parent

base = st.config.get_option("server.baseUrlPath")

all_links = []

if len(base) != 0:
    base += "/"

for path in HERE.rglob("*.py"):
    relative_path = path.relative_to(HERE)
    suffix_removed = relative_path.with_suffix("")

    url = str(suffix_removed).replace("\\", "/")
    url = f"/{base}{url}"

    if suffix_removed.name == "index":
        url = "/".join(url.split("/")[:-1])

    all_links.append(url)

markdown_urls = "\n\n".join([f"[{link}]({link})" for link in all_links])
markdown_urls


with open(HERE.joinpath("index.py")) as f:
    file_contents = f.read()

st.write(
    f"""
```python
{file_contents}
```
    """
)
