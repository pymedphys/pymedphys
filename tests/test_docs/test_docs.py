import unittest
import sys
import pytest

from sphinx_testing import with_app


@pytest.mark.skipif(sys.platform.startswith("win"),
                    reason="Appears to be a path issue within Sphinx for Windows")
class SphinxBuildTest(unittest.TestCase):
    @with_app(buildername='html', srcdir='docs', warningiserror=True)
    def test_sphinx_build(self, app, status, warning):
        app.build()
