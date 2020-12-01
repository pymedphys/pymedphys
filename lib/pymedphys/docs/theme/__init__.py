import sphinx_book_theme
from sphinx.application import Sphinx


def setup(app: Sphinx):
    results = sphinx_book_theme.setup(app)

    app.connect("html-page-context", add_to_context)

    return results


def add_to_context(
    app, pagename, templatename, context, doctree  # pylint: disable = unused-argument
):
    sbt_generate_toc_html = context["generate_toc_html"]

    def generate_toc_html():
        initial_html = sbt_generate_toc_html()
        initial_html += "<h1>FOOBAR</h1>"
        return "<h1>FOOBAR</h1>"

    context["generate_toc_html"] = generate_toc_html
