import pathlib
from typing import Any, Dict, Optional

import sphinx_book_theme
from docutils.nodes import document
from sphinx.application import Sphinx
from sphinx.util import logging

HERE = pathlib.Path(__file__).parent


def setup(app: Sphinx):
    app.add_html_theme("sphinx_pymedphys_theme", str(HERE))

    return {"parallel_read_safe": True, "parallel_write_safe": True}
