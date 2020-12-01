import pathlib
from typing import Any, Dict, Optional

import sphinx_book_theme
from docutils.nodes import document
from sphinx.application import Sphinx
from sphinx.util import logging

HERE = pathlib.Path(__file__).parent


def setup(app: Sphinx):
    app.add_html_theme("sphinx_pymedphys_theme", str(HERE))
    app.connect("html-page-context", add_to_context)

    return {"parallel_read_safe": True, "parallel_write_safe": True}


def add_to_context(
    app: Sphinx,  # pylint: disable = unused-argument
    pagename: str,  # pylint: disable = unused-argument
    templatename: str,  # pylint: disable = unused-argument
    context: Dict[str, Any],
    doctree: Optional[document],  # pylint: disable = unused-argument
):
    sbt_generate_toc_html = context["generate_toc_html"]

    def generate_toc_html():
        initial_html = sbt_generate_toc_html()

        try:
            end_list_index = initial_html.rindex("</ul>")
        except ValueError:
            return initial_html

        new_html = f"""
                {initial_html[0:end_list_index]}
                <li class="toc-h2 nav-item toc-entry">
                    <a class="reference internal nav-link" href="#comments">
                        Comments
                    </a>
                    <ul class="nav section-nav flex-column">
                    </ul>
                </li>
            </ul>
            {initial_html[end_list_index::]}
        """

        return new_html

    context["generate_toc_html"] = generate_toc_html
