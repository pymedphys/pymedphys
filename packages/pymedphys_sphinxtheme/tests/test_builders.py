import os
from io import StringIO
import tempfile
import shutil
from contextlib import contextmanager

import pytest
import sphinx
from sphinx import addnodes
from sphinx.builders.html import SingleFileHTMLBuilder, DirectoryHTMLBuilder
from sphinx.application import Sphinx


@contextmanager
def build(root, builder='html', **kwargs):
    tmpdir = tempfile.mkdtemp()

    srcdir = os.path.join(os.path.dirname(__file__), 'roots', root)
    destdir = os.path.join(tmpdir, builder)
    doctreedir = os.path.join(tmpdir, 'doctree/')

    status = StringIO()
    warning = StringIO()

    kwargs.update({
        'status': status,
        'warning': warning,
    })

    confoverrides = kwargs.pop('confoverrides', {})
    confoverrides['html_theme'] = 'pymedphys_sphinxtheme'
    extensions = confoverrides.get('extensions', [])
    extensions.append('readthedocs_ext.readthedocs')
    confoverrides['extensions'] = extensions
    kwargs['confoverrides'] = confoverrides

    try:
        app = Sphinx(srcdir, srcdir, destdir, doctreedir, builder, **kwargs)
        app.builder.build_all()
        yield (app, status.getvalue(), warning.getvalue())
    except Exception as e:
        print('# root:', root)
        print('# builder:', builder)
        print('# source:', srcdir)
        print('# destination:', destdir)
        print('# status:', '\n' + status.getvalue())
        print('# warning:', '\n' + warning.getvalue())
        raise
    finally:
        shutil.rmtree(tmpdir)


def build_all(root, **kwargs):
    for builder in ['html', 'singlehtml', 'readthedocs', 'readthedocsdirhtml',
                    'readthedocssinglehtml', 'readthedocssinglehtmllocalmedia']:
        with build(root, builder, **kwargs) as ret:
            yield ret


def test_basic():
    for (app, status, warning) in build_all('test-basic'):
        assert app.env.get_doctree('index').traverse(addnodes.toctree)
        content = open(os.path.join(app.outdir, 'index.html')).read()

        if isinstance(app.builder, DirectoryHTMLBuilder):
            search = (
                '<div class="toctree-wrapper compound">\n'
                '<ul>\n'
                '<li class="toctree-l1">'
                '<a class="reference internal" href="foo/">foo</a>'
                '<ul>\n'
                '<li class="toctree-l2">'
                '<a class="reference internal" href="bar/">bar</a></li>\n'
                '</ul>\n'
                '</li>\n'
                '</ul>\n'
                '</div>'
            )
            assert search in content
        elif isinstance(app.builder, SingleFileHTMLBuilder):
            search = (
                '<div class="local-toc"><ul>\n'
                '<li class="toctree-l1">'
                '<a class="reference internal" href="index.html#document-foo">foo</a>'
                '<ul>\n'
                '<li class="toctree-l2">'
                '<a class="reference internal" href="index.html#document-bar">bar</a>'
                '</li>\n'
                '</ul>'
            )
            assert search in content
        else:
            search = (
                '<div class="toctree-wrapper compound">\n'
                '<ul>\n'
                '<li class="toctree-l1">'
                '<a class="reference internal" href="foo.html">foo</a>'
                '<ul>\n'
                '<li class="toctree-l2">'
                '<a class="reference internal" href="bar.html">bar</a></li>\n'
                '</ul>\n'
                '</li>\n'
                '</ul>\n'
                '</div>'
            )
            assert search in content, ('Missing search with builder {0}'
                                       .format(app.builder.name))


def test_empty():
    """Local TOC is showing, as toctree was empty"""
    for (app, status, warning) in build_all('test-empty'):
        assert app.env.get_doctree('index').traverse(addnodes.toctree)
        content = open(os.path.join(app.outdir, 'index.html')).read()
        if sphinx.version_info < (1, 4):
            if isinstance(app.builder, SingleFileHTMLBuilder):
                assert '<div class="toctree-wrapper compound">\n</div>' in content
                assert '<div class="local-toc">' in content
            else:
                global_toc = (
                    '<div class="toctree-wrapper compound">\n'
                    '<ul class="simple">\n</ul>\n'
                    '</div>'
                )
                local_toc = (
                    '<div class="local-toc"><ul class="simple">'
                    '</ul>\n</div>'
                )
                assert global_toc in content
                assert local_toc not in content
        else:
            global_toc = '<div class="toctree-wrapper compound">\n</div>'
            local_toc = (
                '<div class="local-toc"><ul>\n'
                '<li><a class="reference internal" href="#">test-empty</a></li>'
                '</ul>\n</div>'
            )
            assert global_toc in content
            assert local_toc not in content


def test_missing_toctree():
    """Local TOC is showing, as toctree was missing"""
    for (app, status, warning) in build_all('test-missing-toctree'):
        assert app.env.get_doctree('index').traverse(addnodes.toctree) == []
        content = open(os.path.join(app.outdir, 'index.html')).read()
        assert '<div class="toctree' not in content
        assert '<div class="local-toc">' in content
