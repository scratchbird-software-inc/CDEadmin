##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Provider navigator and object-editor coverage gate tests."""

from __future__ import annotations

import copy
import unittest

from tools.cdeadmin_provider_object_coverage_gate import (
    audit, provider_catalogs,
)


class ProviderObjectCoverageGateTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.catalogs = provider_catalogs()

    def test_inventory_is_structurally_complete_and_fail_closed(self):
        result = audit(self.catalogs)
        self.assertEqual(27, result['profile_count'])
        self.assertEqual(36, result['family_slice_count'])
        self.assertEqual(515, result['concept_count'])
        self.assertEqual(
            result['concept_count'],
            result['catalogued_count'] +
            result['external_surface_count'] +
            result['not_applicable_count'],
        )
        self.assertEqual(result['concept_count'], result['declared_count'])
        self.assertEqual(0, result['undeclared_count'])
        self.assertEqual(0, result['blocking_missing_count'])
        self.assertEqual(
            result['native_graphical_operation_count'],
            result['graphical_operation_count'],
        )
        # Includes Firebird embedded and eleven native large-object operations.
        # 2026-10-31: 2405 with every shipped dialect contract passing
        # (CockroachDB 116, YugabyteDB 129). While those two contracts were
        # blocked they offered only the operations outside them (26 and 34).
        # 2026-11-01: 2415 with Dolt's table options, analyze, index rename,
        # role membership, session termination and global variables (eight
        # operations plus inspect on the session and system-variable kinds).
        # 2431 with TiDB's fourteen (table options, analyze, caching, stats
        # locks, index rename and visibility, role membership and default
        # role, account rename, sessions, global variables) plus two inspect.
        # 2434 with Vitess's table comment, index rename and visibility,
        # each confirmed on every shard's primary.
        # 2470 with the PG-wire administration shared by CockroachDB and
        # YugabyteDB: seventeen operations each (truncate, analyze, schema and
        # owner moves, constraint validation, role and user default
        # settings, database, schema and type grants, sessions) plus inspect
        # on their sessions.
        # 2474 with partitions after create: YugabyteDB create, attach and
        # detach, CockroachDB repartition.
        self.assertEqual(2474, result['graphical_operation_count'])
        large_object = next(item for item in self.catalogs['postgresql-native']['descriptor']['objects']
            if item['resource_kind'] == 'large-object')
        self.assertEqual({'inspect', 'create', 'read', 'write', 'truncate', 'alter', 'grant', 'revoke', 'drop',
                          'import-server-file', 'export-server-file'},
            {item['operation_id'] for item in large_object['operations']})
        self.assertTrue(all(item['execution_route'] == 'provider-native' for item in large_object['operations']))
        self.assertEqual(0, result['activation_permission_failure_count'])
        self.assertEqual(0, result['provider_identity_failure_count'])
        self.assertEqual(0, result['shared_semantics_failure_count'])
        self.assertEqual(0, result['support_inference_failure_count'])
        self.assertEqual([], result['failures'])
        self.assertTrue(result['complete'])
        self.assertEqual(
            ['scratchbird'], result['scope']['deferred_engine_ids']
        )
        self.assertEqual(
            'delegated-to-strict-provider-engine-gates',
            result['scope']['live_activation'],
        )

        broken = copy.deepcopy(self.catalogs)
        declaration = broken['neo4j-native']['descriptor'][
            'concept_declarations']['graph']['nodes']
        declaration['status'] = 'unfinished'
        from pgadmin.cdeadmin.visual_admin import enrich_engine_experience
        broken['neo4j-native']['descriptor'] = enrich_engine_experience(
            broken['neo4j-native']['descriptor']
        )
        failed = audit(broken)
        self.assertFalse(failed['complete'])
        self.assertTrue(any(
            value.endswith('graph.nodes:undeclared')
            for value in failed['failures']
        ))

        broken = copy.deepcopy(self.catalogs)
        graphical = broken['neo4j-native']['descriptor'][
            'graphical_interface'
        ]
        graphical['activation_state'] = 'blocked'
        graphical['graphical_operation_count'] -= 1
        graphical['missing_operations'] = [{
            'resource_kind': 'node', 'operation_id': 'update',
        }]
        failed = audit(broken)
        self.assertFalse(failed['complete'])
        self.assertIn(
            'neo4j-native:graphical-form-missing:node.update',
            failed['failures'],
        )

        broken = copy.deepcopy(self.catalogs)
        broken['neo4j-native']['descriptor']['graphical_interface'][
            'shared_engine_semantics_allowed'
        ] = True
        failed = audit(broken)
        self.assertFalse(failed['complete'])
        self.assertIn(
            'neo4j-native:shared-engine-semantics-admitted',
            failed['failures'],
        )

        broken = copy.deepcopy(self.catalogs)
        broken['firebird-native']['granted_permissions'].remove(
            'maintenance_admin'
        )
        failed = audit(broken)
        self.assertFalse(failed['complete'])
        self.assertGreater(
            failed['activation_permission_failure_count'], 0
        )
        self.assertTrue(any(
            value.startswith(
                'firebird-native:operation-permission-unadmitted:'
                'database.repair_database:maintenance_admin'
            )
            for value in failed['failures']
        ))

    def test_inventory_preserves_specialized_provider_families(self):
        result = audit(self.catalogs)

        def families(profile_id):
            return {
                item['family_id']
                for item in result['profiles'][profile_id]['concepts']
            }
        self.assertIn('columnar', families('clickhouse-native'))
        self.assertIn('time_series', families('influxdb-native'))
        self.assertIn('vector', families('milvus-native'))
        self.assertIn('wide_column', families('cassandra-native'))
        self.assertIn('graph', families('neo4j-native'))
        self.assertIn('search', families('opensearch-native'))
        self.assertEqual(
            {'wide_column'}, families('yugabytedb-ycql')
        )
        self.assertEqual(
            {'relational'}, families('yugabytedb-native')
        )

    def test_every_shipped_dialect_contract_passes(self):
        """A contract that misses an executable task blocks all its work.

        Live, 2026-10-31: CockroachDB, YugabyteDB, Vitess and Dolt gained
        operations their dialect contracts did not list, so each refused
        every contract-planned operation; only the graphical count showed it.
        """
        import importlib
        import json
        from tools import cdeadmin_provider_object_coverage_gate as gate
        absent = set()
        for relative_path, module_name in gate.BUILTIN_PACKAGES:
            manifest = json.loads(
                (gate.PROVIDER_ROOT / relative_path).read_text())
            identity = manifest['identity']
            if identity['profile_id'] == 'postgresql-native':
                continue  # preserved native surface, no generated contract
            provider = importlib.import_module(module_name).create_provider(
                gate._context(identity, manifest),
                gate._InventoryPermissions())
            dialect = provider.engine_contract_descriptor()['dialect']
            with self.subTest(profile=identity['profile_id']):
                if dialect.get('reason') == (
                        'provider_exact_dialect_contract_absent'):
                    absent.add(identity['profile_id'])
                else:
                    self.assertEqual('passed', dialect['state'],
                                     dialect.get('reason'))
        # Profiles without a generated contract; adding one must pass above.
        self.assertEqual({
            'apache-ignite-native', 'clickhouse-native', 'foundationdb-native',
            'influxdb-native', 'milvus-native', 'mongodb-native',
            'neo4j-native', 'opensearch-native', 'opensearch-sql-ppl',
            'redis-native', 'tikv-native', 'xtdb-native',
        }, absent)

    def test_mysql_family_metrics_are_graphically_reachable(self):
        for profile_id in ('mysql-native', 'mariadb-native'):
            objects = {
                item['resource_kind']: item
                for item in self.catalogs[profile_id]['descriptor']['objects']
            }
            self.assertIn('metric', objects)
            self.assertEqual(
                ['inspect'],
                [
                    operation['operation_id']
                    for operation in objects['metric']['operations']
                ],
            )


if __name__ == '__main__':
    unittest.main()
