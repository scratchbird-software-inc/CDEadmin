"""The inherited PostgreSQL tools list PostgreSQL provider endpoints.

Schema Diff's server picker and the Query Tool's connection switcher
skipped every provider endpoint (parity matrix blocker 8). A PostgreSQL
server moved onto the provider tree must stay on both lists; other
engines' endpoints must stay off them.
"""
import ast
import unittest
from pathlib import Path

SERVERS = (Path(__file__).resolve().parents[2] / 'web' / 'pgadmin' /
           'browser' / 'server_groups' / 'servers' / '__init__.py')
SCHEMA_DIFF = (Path(__file__).resolve().parents[2] / 'web' / 'pgadmin' /
               'tools' / 'schema_diff' / '__init__.py')
SQLEDITOR = (Path(__file__).resolve().parents[2] / 'web' / 'pgadmin' /
             'tools' / 'sqleditor' / '__init__.py')


def _function(source, name):
    tree = ast.parse(source.read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f'{name} not found in {source}')


def _predicate():
    function = _function(SERVERS, 'inherited_postgresql_tools_apply')
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]),
                 str(SERVERS), 'exec'), namespace)
    return namespace['inherited_postgresql_tools_apply']


class InheritedToolsFilterTests(unittest.TestCase):
    def setUp(self):
        self.applies = _predicate()

    def test_preserved_postgresql_registration_is_listed(self):
        self.assertTrue(self.applies({'workflow': 'legacy_preserved',
                                      'engine_id': 'postgresql'}))

    def test_postgresql_provider_endpoint_is_listed(self):
        self.assertTrue(self.applies({'workflow': 'provider_endpoint',
                                      'engine_id': 'postgresql'}))

    def test_other_engine_provider_endpoints_stay_off(self):
        for engine in ('sqlite', 'yugabytedb', 'mysql', 'firebird'):
            self.assertFalse(self.applies({'workflow': 'provider_endpoint',
                                           'engine_id': engine}), engine)
        # A disabled provider's fallback profile has no engine id.
        self.assertFalse(self.applies({'workflow': 'provider_endpoint'}))

    def test_both_tool_listings_use_the_predicate(self):
        for source in (SCHEMA_DIFF, SQLEDITOR):
            text = source.read_text(encoding='utf-8')
            self.assertIn('inherited_postgresql_tools_apply(', text,
                          source.name)
            self.assertNotIn(
                "_cde_registration(server)['workflow'] == "
                "'provider_endpoint'", text, source.name)


if __name__ == '__main__':
    unittest.main()
