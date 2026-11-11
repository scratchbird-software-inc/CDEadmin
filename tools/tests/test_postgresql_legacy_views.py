"""Provider nodes inspect through the inherited PostgreSQL views (M3)."""
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

WEB = Path(__file__).resolve().parents[2] / 'web'
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

from pgadmin.cdeadmin.providers.postgresql import (  # noqa: E402
    legacy_views as views,
)
from pgadmin.cdeadmin.providers.postgresql.legacy_identity import (  # noqa: E402,E501
    LEGACY_NODE_TYPES, CONSTRAINT_NODE_TYPES,
)


def chain(node_type, **extra):
    base = {'gid': 1, 'sid': 7, 'did': 10, 'scid': 2200, 'tid': 16601,
            'oid': 16610, 'node_type': node_type}
    base.update(extra)
    return base


class Response:
    def __init__(self, body, status=200):
        self.status_code = status
        self._body = json.dumps(body)

    def get_data(self, as_text=False):
        return self._body


class ViewMapTests(unittest.TestCase):
    def test_every_legacy_node_type_has_a_view_or_a_declared_gap(self):
        known = set(views.VIEW_SPECS) | views.NEEDS_WRAPPER_ID
        node_types = {v for v in LEGACY_NODE_TYPES.values() if v}
        node_types |= set(CONSTRAINT_NODE_TYPES.values())
        node_types |= {'trigger_function', 'partition', 'domain_constraints'}
        self.assertEqual(set(), node_types - known)

    def test_kwargs_follow_each_view_signature(self):
        self.assertEqual(
            {'gid': 1, 'sid': 7, 'did': 10, 'scid': 2200, 'tid': 16610},
            views.view_kwargs(chain('table')))
        self.assertEqual(
            {'gid': 1, 'sid': 7, 'did': 10, 'scid': 2200, 'tid': 16601,
             'idx': 16610}, views.view_kwargs(chain('index')))
        self.assertEqual(
            {'gid': 1, 'sid': 7, 'did': 10, 'scid': 2200, 'fnid': 16610},
            views.view_kwargs(chain('trigger_function')))
        self.assertEqual({'gid': 1, 'sid': 7, 'did': 10, 'eid': 16610},
                         views.view_kwargs(chain('extension', scid=None)))
        self.assertEqual({'gid': 1, 'sid': 7, 'rid': 16610},
                         views.view_kwargs(chain('role', did=None,
                                                 scid=None)))
        self.assertEqual({'gid': 1, 'sid': 7, 'did': 16610},
                         views.view_kwargs(chain('database', oid=16610)))
        self.assertEqual(
            {'gid': 1, 'sid': 7, 'did': 10, 'scid': 2200, 'doid': 16601,
             'coid': 16610}, views.view_kwargs(chain('domain_constraints')))

    def test_server_group_defaults_when_the_chain_lacks_it(self):
        bare = chain('table')
        del bare['gid']
        self.assertEqual(1, views.view_kwargs(bare)['gid'])

    def test_missing_ids_are_named(self):
        with self.assertRaisesRegex(ValueError, 'owning object'):
            views.view_kwargs(chain('trigger', tid=None))
        with self.assertRaisesRegex(ValueError, 'schema id'):
            views.view_kwargs(chain('sequence', scid=None))
        with self.assertRaises(KeyError):
            views.view_kwargs(chain('conversion'))


class UnwrapAndRedactTests(unittest.TestCase):
    def test_text_tuple_and_response_bodies(self):
        self.assertEqual((True, 'CREATE X'), views._unwrap('CREATE X'))
        self.assertEqual((True, 'CREATE T'),
                         views._unwrap(('CREATE T', 'PART')))
        self.assertEqual((True, 'CREATE I'),
                         views._unwrap(Response('CREATE I')))
        ok, why = views._unwrap(Response({'errormsg': 'gone'}, 410))
        self.assertFalse(ok)
        self.assertIn('410', why)
        self.assertIn('gone', why)
        self.assertEqual((False, 'inherited view returned no text'),
                         views._unwrap(Response({'a': 1})))

    def test_passwords_in_inherited_sql_are_redacted(self):
        text = ("CREATE USER MAPPING FOR me SERVER s OPTIONS (user 'me', "
                "password 'it''s secret');\n"
                "CREATE SUBSCRIPTION sub CONNECTION 'host=h password=pw "
                "dbname=d' PUBLICATION p;")
        out = views.redact_sql(text)
        self.assertNotIn('secret', out)
        self.assertNotIn('password=pw', out)
        self.assertIn("password '[redacted]'", out)
        self.assertIn('password=[redacted] dbname=d', out)
        self.assertEqual(views.redact_sql(None), None)


class StatisticsTests(unittest.TestCase):
    def test_one_row_becomes_a_mapping_and_many_stay_rows(self):
        one = {'columns': [{'name': 'size'}], 'rows': [{'size': '8 kB'}]}
        self.assertEqual({'size': '8 kB'}, views.statistics_rows(one))
        many = {'columns': [], 'rows': [{'n': 1}, {'n': 2}]}
        self.assertEqual([{'n': 1}, {'n': 2}], views.statistics_rows(many))
        self.assertEqual({'other': 1}, views.statistics_rows({'other': 1}))

    def test_kinds_without_statistics_say_so(self):
        ok, why = views.inherited_statistics(chain('view'))
        self.assertFalse(ok)
        self.assertIn('no statistics', why)

    def test_statistics_come_from_the_inherited_view(self):
        class View:
            def statistics(self, **kwargs):
                assert kwargs['tid'] == 16610
                return Response({'data': {'columns': [],
                                          'rows': [{'rows': 42}]}})
        with patch.object(views, '_view', lambda spec: View()):
            self.assertEqual((True, {'rows': 42}),
                             views.inherited_statistics(chain('table')))


class InspectionTests(unittest.TestCase):
    def test_sections_come_from_the_inherited_view(self):
        calls = {}

        class View:
            def sql(self, **kwargs):
                calls['sql'] = kwargs
                return Response("CREATE INDEX i ON t (c) -- password 'x'")

            def statistics(self, **kwargs):
                return Response({'data': {'columns': [],
                                          'rows': [{'size': '16 kB'}]}})

            def get_dependencies(self, conn, oid):
                calls['deps'] = (conn, oid)
                return [{'type': 'table', 'name': 'public.t', 'field': ''}]

            def get_dependents(self, conn, oid):
                return []

        connections = []
        with patch.object(views, '_view', lambda spec: View()):
            result = views.inherited_inspection(
                chain('index'), lambda did: connections.append(did) or 'c')
        self.assertEqual(calls['sql']['idx'], 16610)
        self.assertEqual("CREATE INDEX i ON t (c) -- password '[redacted]'",
                         result['ddl'])
        self.assertEqual(('c', 16610), calls['deps'])
        self.assertEqual([10], connections)
        self.assertEqual({'ddl': 'inherited', 'statistics': 'inherited',
                          'dependencies': 'inherited'}, result['states'])
        self.assertEqual({'size': '16 kB'}, result['statistics'])
        self.assertEqual('public.t', result['dependencies'][0]['name'])
        self.assertEqual([], result['dependents'])

    def test_failures_become_states_not_errors(self):
        class View:
            def sql(self, **kwargs):
                raise RuntimeError('template missing')

            def get_dependencies(self, conn, oid):
                return []

            def get_dependents(self, conn, oid):
                return []

        with patch.object(views, '_view', lambda spec: View()):
            result = views.inherited_inspection(chain('table'), lambda d: 'c')
        self.assertNotIn('ddl', result)
        self.assertIn('RuntimeError: template missing',
                      result['states']['ddl'])
        self.assertEqual('inherited', result['states']['dependencies'])

    def test_kinds_without_a_view_say_why(self):
        self.assertIn('no inherited node', views.inherited_inspection(
            chain(None))['states']['all'])
        self.assertIn('foreign-data-wrapper id', views.inherited_inspection(
            chain('user_mapping'))['states']['all'])
        with patch.object(views, 'inherited_sql',
                          lambda c: (True, 'CREATE VIEW v AS SELECT 1')):
            result = views.inherited_inspection(chain('view'), None)
        self.assertEqual('CREATE VIEW v AS SELECT 1', result['ddl'])
        self.assertIn('no connection', result['states']['dependencies'])


class ProviderWiringTests(unittest.TestCase):
    def test_provider_enriches_a_captured_resource_inside_a_request(self):
        from pgadmin.cdeadmin.providers.postgresql import provider as module
        provider = object.__new__(module.PostgreSQLProvider)
        provider._driver = SimpleNamespace(connection_manager=lambda sid: (
            SimpleNamespace(connection=lambda did=None: f'conn:{did}')))
        resource = {'extensions': {'postgresql': {
            'native': {'dependencies': [{'objid': 1}]},
            'legacy_route': chain('sequence')}}}
        seen = {}

        def fake(chain_value, connection_for):
            seen['conn'] = connection_for(chain_value['did'])
            return {'ddl': 'CREATE SEQUENCE s', 'dependencies': ['d'],
                    'dependents': ['e'], 'statistics': {'last_value': 5},
                    'states': {'ddl': 'inherited',
                               'dependencies': 'inherited'}}
        with patch('flask.has_request_context', lambda: True), \
                patch('pgadmin.cdeadmin.providers.postgresql.legacy_views'
                      '.inherited_inspection', fake):
            out = provider._with_inherited_inspection(resource)
        native = out['extensions']['postgresql']['native']
        self.assertEqual('conn:10', seen['conn'])
        self.assertEqual('CREATE SEQUENCE s', native['ddl'])
        self.assertEqual(['d'], native['dependencies'])
        self.assertEqual(['e'], native['dependents'])
        self.assertEqual({'last_value': 5}, native['statistics'])
        self.assertEqual([{'objid': 1}], native['dependency_rows'])
        self.assertEqual('inherited',
                         native['inherited_inspection']['states']['ddl'])

    def test_outside_a_request_the_resource_is_left_alone(self):
        from pgadmin.cdeadmin.providers.postgresql import provider as module
        provider = object.__new__(module.PostgreSQLProvider)
        resource = {'extensions': {'postgresql': {
            'native': {}, 'legacy_route': chain('table')}}}
        with patch('flask.has_request_context', lambda: False):
            out = provider._with_inherited_inspection(resource)
        self.assertNotIn('ddl', out['extensions']['postgresql']['native'])
        self.assertIn('outside a request', out['extensions']['postgresql'][
            'native']['inherited_inspection']['states']['all'])


if __name__ == '__main__':
    unittest.main()
