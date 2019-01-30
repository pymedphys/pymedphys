import unittest
from sphinx_testing import with_app


class SphinxBuildTest(unittest.TestCase):
    @with_app(buildername='html', srcdir='docs', warningiserror=True)
    def test_sphinx_build(self, app, status, warning):
        app.build()
