"""URL rules compile their builders on first use and build werkzeug's URLs.

``LazyBuilderRule`` relies on werkzeug's ``Rule._compile_builder`` hook. These
tests compare every built URL with werkzeug's own ``Rule`` and count builder
compilations, so a werkzeug change to that hook fails here.
"""
import os
from pathlib import Path
import subprocess
import sys

import pytest
from werkzeug.routing import BuildError, Map, Rule

# The application imports config before pgadmin.utils; config itself
# imports from pgadmin.utils, so the other order is circular.
import config  # noqa: F401
from pgadmin.utils.lazy_url_rules import LazyBuilderRule

SPECS = (
    ('/', {}, 'index'),
    ('/browser/', {}, 'browser'),
    ('/node/<int:gid>/<int:sid>/<did>', {}, 'node'),
    ('/files/<path:name>', {}, 'files'),
    ('/obj/', {'oid': None}, 'obj'),
    ('/obj/<int:oid>', {}, 'obj'),
    ('/kind/<any(table, view):kind>/<uuid:ident>', {}, 'kind'),
    ('/café b/<name>', {}, 'quoted'),
    ('/fixed/<name>', {'name': 'pinned'}, 'fixed'),
)

VALUES = (
    ('index', {}),
    ('index', {'q': 'a b', 'n': 3}),
    ('browser', {}),
    ('node', {'gid': 1, 'sid': 2, 'did': 'x/y'}),
    ('node', {'gid': 1, 'sid': 2, 'did': 'd', 'extra': ['1', '2']}),
    ('node', {'gid': 1, 'sid': 2}),
    ('files', {'name': 'a/b c.sql'}),
    ('obj', {}),
    ('obj', {'oid': 7}),
    ('obj', {'oid': 7, 'v': 'z'}),
    ('kind', {'kind': 'view',
              'ident': '12345678-1234-5678-1234-567812345678'}),
    ('kind', {'kind': 'other',
              'ident': '12345678-1234-5678-1234-567812345678'}),
    ('quoted', {'name': 'ü'}),
    ('fixed', {}),
    ('fixed', {'name': 'pinned'}),
    ('fixed', {'name': 'other'}),
    ('missing', {}),
)


def _map(rule_class):
    rules = [rule_class(path, defaults=defaults or None, endpoint=endpoint)
             for path, defaults, endpoint in SPECS]
    return Map(rules).bind('example.test', script_name='/root')


def _build(adapter, endpoint, values, **options):
    try:
        return adapter.build(endpoint, values, **options)
    except BuildError as error:
        return ('BuildError', error.endpoint, sorted(error.values))
    except Exception as error:
        # A converter's refusal must be the same error from either rule.
        return (type(error).__name__, str(error))


@pytest.mark.parametrize('endpoint,values', VALUES)
@pytest.mark.parametrize('options', (
    {}, {'append_unknown': False}, {'force_external': True},
    {'method': 'GET'}))
def test_lazy_rules_build_what_werkzeug_builds(endpoint, values, options):
    assert (_build(_map(LazyBuilderRule), endpoint, values, **options) ==
            _build(_map(Rule), endpoint, values, **options))


def test_builders_compile_on_first_use_only(monkeypatch):
    compiled = []
    original = Rule._compile_builder

    def counting(self, append_unknown=True):
        compiled.append((self.rule, append_unknown))
        return original(self, append_unknown)
    monkeypatch.setattr(Rule, '_compile_builder', counting)

    stock = Map([Rule('/a/<int:x>', endpoint='a')])
    assert len(compiled) == 2

    compiled.clear()
    adapter = _map(LazyBuilderRule)
    assert compiled == []
    assert adapter.build('node', {'gid': 1, 'sid': 2, 'did': 'd'}) == \
        '/root/node/1/2/d'
    assert compiled == [('/node/<int:gid>/<int:sid>/<did>', True)]
    adapter.build('node', {'gid': 3, 'sid': 4, 'did': 'e'})
    adapter.build('node', {'gid': 3, 'sid': 4, 'did': 'e'},
                  append_unknown=False)
    assert compiled == [('/node/<int:gid>/<int:sid>/<did>', True),
                        ('/node/<int:gid>/<int:sid>/<did>', False)]
    assert stock.bind('example.test').build('a', {'x': 1}) == '/a/1'


def test_the_application_uses_lazy_rules():
    # A fresh interpreter: other tests replace pgadmin modules in this one.
    web = Path(__file__).resolve().parents[2] / 'web'
    script = ('import config\n'
              'from pgadmin import PgAdmin\n'
              'from pgadmin.utils.lazy_url_rules import LazyBuilderRule\n'
              'print(PgAdmin.url_rule_class is LazyBuilderRule)\n')
    completed = subprocess.run(
        [sys.executable, '-c', script], cwd=web, capture_output=True,
        text=True, timeout=120,
        env={**os.environ, 'PYTHONPATH': str(web)})
    assert completed.stdout.strip().splitlines()[-1:] == ['True'], \
        completed.stderr[-2000:]
