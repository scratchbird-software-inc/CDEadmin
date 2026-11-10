"""Captured PostgreSQL resources carry the inherited route chain."""
import sys
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / 'web'
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

from pgadmin.cdeadmin.providers.postgresql import (  # noqa: E402
    legacy_identity as identity,
)
from pgadmin.cdeadmin.providers.postgresql.catalog_capture import (  # noqa: E402
    CAPTURE_RESOURCE_KINDS,
)


def captured(catalog, oid, kind, name, schema='public', parent=None,
             row=None, children=None):
    native = {'catalog': catalog, 'oid': oid, 'schema': schema,
              'catalog_row': row or {}}
    if parent:
        native['navigator_parent_resource_id'] = parent
    if children:
        native['children'] = children
    return {'resource_id': f'postgresql:{catalog}:{oid}',
            'resource_kind': kind, 'display_name': name, 'native': native}


RESOURCES = [
    captured('pg_namespace', 2200, 'schema', 'public', schema=None),
    captured('pg_namespace', 16500, 'schema', 'sales', schema=None),
    captured('pg_class', 16601, 'table', 'orders', schema='sales',
             parent='postgresql:pg_namespace:16500'),
    captured('pg_class', 16610, 'index', 'orders_pkey', schema='sales',
             parent='postgresql:pg_class:16601'),
    captured('pg_constraint', 16611, 'constraint', 'orders_pkey',
             schema='sales', parent='postgresql:pg_class:16601',
             row={'contype': 'p', 'contypid': 0}),
    captured('pg_constraint', 16612, 'constraint', 'orders_customer_fk',
             schema='sales', parent='postgresql:pg_class:16601',
             row={'contype': 'f', 'contypid': 0}),
    captured('pg_constraint', 16620, 'constraint', 'positive_amount',
             schema='sales', row={'contype': 'c', 'contypid': 16619}),
    captured('pg_trigger', 16630, 'trigger', 'orders_audit', schema='sales',
             parent='postgresql:pg_class:16601'),
    captured('pg_proc', 16640, 'function', 'orders_audit_fn',
             schema='sales', row={'prorettype': 2279}),
    captured('pg_proc', 16641, 'function', 'order_total', schema='sales',
             row={'prorettype': 1700}),
    captured('pg_class', 16650, 'table', 'orders_2026', schema='sales',
             row={'relispartition': True},
             children={'pg_inherits': [{'inhparent': 16601}]}),
    captured('pg_user_mapping', 16660, 'user-mapping', 'dalton / remote',
             schema=None, parent='postgresql:pg_foreign_server:16655'),
    captured('pg_language', 13, 'language', 'plpgsql', schema=None),
    captured('pg_conversion', 16670, 'conversion', 'latin1_to_utf8'),
]


class LegacyRouteTests(unittest.TestCase):
    def setUp(self):
        self.schemas = identity.schema_oids(RESOURCES)

    def route(self, index):
        item = RESOURCES[index]
        return identity.legacy_route(7, 10, item['resource_kind'],
                                     item['native'], self.schemas)

    def test_schema_oids_come_from_captured_namespaces(self):
        self.assertEqual({'public': 2200, 'sales': 16500}, self.schemas)

    def test_table_carries_server_database_schema_and_oid(self):
        self.assertEqual({'sid': 7, 'did': 10, 'scid': 16500, 'tid': None,
                          'oid': 16601, 'node_type': 'table'},
                         self.route(2))

    def test_schema_uses_its_own_oid_as_scid(self):
        self.assertEqual(16500, self.route(1)['scid'])
        self.assertEqual('schema', self.route(1)['node_type'])

    def test_relation_owned_objects_carry_the_owning_relation(self):
        for index, node_type in ((3, 'index'), (4, 'primary_key'),
                                 (5, 'foreign_key'), (7, 'trigger')):
            route = self.route(index)
            self.assertEqual(node_type, route['node_type'], index)
            self.assertEqual(16601, route['tid'], index)
            self.assertEqual(16500, route['scid'], index)

    def test_domain_constraint_is_owned_by_its_domain(self):
        route = self.route(6)
        self.assertEqual('domain_constraints', route['node_type'])
        self.assertEqual(16619, route['tid'])

    def test_trigger_functions_are_told_apart_by_return_type(self):
        self.assertEqual('trigger_function', self.route(8)['node_type'])
        self.assertEqual('function', self.route(9)['node_type'])

    def test_partition_is_owned_by_its_parent_table(self):
        route = self.route(10)
        self.assertEqual('partition', route['node_type'])
        self.assertEqual(16601, route['tid'])

    def test_user_mapping_is_owned_by_its_foreign_server(self):
        route = self.route(11)
        self.assertEqual('user_mapping', route['node_type'])
        self.assertEqual(16655, route['tid'])
        self.assertIsNone(route['scid'])

    def test_cluster_level_objects_have_no_schema(self):
        route = self.route(12)
        self.assertEqual('language', route['node_type'])
        self.assertIsNone(route['scid'])

    def test_kinds_without_a_legacy_node_say_so(self):
        route = self.route(13)
        self.assertIsNone(route['node_type'])
        self.assertEqual(2200, route['scid'])

    def test_every_capture_kind_is_mapped(self):
        # A new capture kind must be placed in the table, even as None,
        # so "no legacy node" is a decision rather than an omission.
        unmapped = CAPTURE_RESOURCE_KINDS - set(identity.LEGACY_NODE_TYPES)
        self.assertEqual(set(), unmapped - {'constraint'})


if __name__ == '__main__':
    unittest.main()
