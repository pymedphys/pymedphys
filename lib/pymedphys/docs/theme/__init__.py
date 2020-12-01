from typing import Any, Dict, Optional

import sphinx_book_theme
from docutils.nodes import document
from sphinx.application import Sphinx
from sphinx.util import logging

SPHINX_LOGGER = logging.getLogger(__name__)


def setup(app: Sphinx):
    raise ValueError("Make noise")

    results = sphinx_book_theme.setup(app)

    app.connect("html-page-context", add_to_context)

    return results


def add_to_context(
    app: Sphinx,  # pylint: disable = unused-argument
    pagename: str,  # pylint: disable = unused-argument
    templatename: str,  # pylint: disable = unused-argument
    context: Dict[str, Any],
    doctree: Optional[document],  # pylint: disable = unused-argument
):
    SPHINX_LOGGER.error("a test")

    sbt_generate_toc_html = context["generate_toc_html"]
    print(context)

    def generate_toc_html():
        initial_html = sbt_generate_toc_html()
        initial_html += "<h1>FOOBAR</h1>"
        return "<h1>FOOBAR</h1>"

    context["generate_toc_html"] = generate_toc_html
