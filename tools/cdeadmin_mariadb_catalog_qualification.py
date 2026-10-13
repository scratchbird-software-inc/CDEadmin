"""Qualify native MariaDB catalog facts without executing imported DDN."""
import argparse
import json
from pathlib import Path
import secrets

from tools.cdeadmin_mariadb_driver_gate import run
from tools.mysql_driver_gate_support import provider_access
from pgadmin.cdeadmin.providers.mysql_family.provider import (
    MariaDBPilotProvider, MARIADB_PROFILE, _create_client)
from types import SimpleNamespace


def qualify(route, evidence, *, password=None):
    import mariadb
    evidence.mkdir(parents=True, exist_ok=False)
    proof = {'complete': False, 'checks': []}
    schema = 'owned_catalog_' + secrets.token_hex(8)
    role = 'catalog_role_' + secrets.token_hex(6)
    link = 'catalog_link_' + secrets.token_hex(6)
    link_password = secrets.token_urlsafe(32)
    owner = mariadb.connect(**route, autocommit=True,
        **({'password': password} if password is not None else {}))
    cursor = owner.cursor()
    client = None
    interactive = None
    try:
        cursor.execute(f'CREATE DATABASE `{schema}`')
        owner.database = schema
        statements = [
            'CREATE SEQUENCE seq START WITH 20',
            "CREATE TABLE options_probe (id INT COMMENT 'retained field', KEY k (id) USING BTREE) ENGINE=InnoDB ROW_FORMAT=DYNAMIC COMMENT='retained table'",
            'CREATE TABLE temporal (id INT PRIMARY KEY, value VARCHAR(40)) WITH SYSTEM VERSIONING',
            'CREATE TABLE appointments (id INT, start_at DATE, end_at DATE, PERIOD FOR validity(start_at,end_at))',
            'CREATE VIEW v AS SELECT id FROM temporal',
            'CREATE PROCEDURE p(IN i INT) SELECT i',
            'CREATE PACKAGE pkg PROCEDURE hi(); END',
            'CREATE PACKAGE BODY pkg PROCEDURE hi() BEGIN SELECT 1; END; END',
            'CREATE TRIGGER tr BEFORE INSERT ON temporal FOR EACH ROW SET NEW.value=COALESCE(NEW.value,\'default\')',
            'CREATE EVENT ev ON SCHEDULE EVERY 1 DAY DISABLE DO SELECT 1',
        ]
        for statement in statements:
            cursor.execute(statement)
        interactive = mariadb.connect(**route, database=schema, autocommit=False,
            **({'password': password} if password is not None else {}))
        with interactive.cursor() as pending:
            pending.execute("INSERT INTO temporal VALUES (1,'pending')")
        native_route, permissions = provider_access(route, password)
        def require(permission_id, scope=None):
            assert (permission_id, scope) in {('data_read', 'resource'), ('execute', 'endpoint')}
        permissions.require = require
        context = SimpleNamespace(pool_namespace='catalog:' + secrets.token_hex(8))
        client = _create_client(MARIADB_PROFILE, permissions, context)
        provider = MariaDBPilotProvider(context, permissions, client)
        result = provider.capture_catalog({**native_route, 'database': schema})
        objects = {(row['resource_kind'], row['display_name']): row for row in result['resources']}
        for key in [('table', 'temporal'), ('table', 'appointments'), ('sequence', 'seq'),
                    ('view', 'v'), ('procedure', 'p'), ('package', 'pkg'),
                    ('package-body', 'pkg'), ('trigger', 'tr'), ('event', 'ev')]:
            native = objects[key]['native']
            assert native['definition_available'] and native['definition'], key
            assert objects[key]['resource_id'].startswith('mariadb:')
        assert 'WITH SYSTEM VERSIONING' in objects['table', 'temporal']['native']['definition']
        assert objects['table', 'appointments']['native']['children']['PERIODS'][0]['period'] == 'validity'
        assert objects['procedure', 'p']['native']['parameters'][0]['parameter_name'] == 'i'
        assert objects['database', schema]['native']['catalog_row']['server_uid']
        assert all(row['available'] for row in result['observations']), result['observations']
        assert result['complete'] is False
        assert len({row['resource_id'] for row in result['resources']}) == len(result['resources'])
        proof['checks'].append('native_temporal_sequence_package_routine_trigger_event_definitions')
        cursor.execute('SELECT NEXT VALUE FOR seq')
        assert cursor.fetchone()[0] == 20
        proof['checks'].append('sequence_capture_does_not_advance_native_value')
        assert interactive.server_status & 1
        cursor.execute('SELECT COUNT(*) FROM temporal')
        assert cursor.fetchone()[0] == 0
        proof['checks'].append('independent_catalog_preserves_interactive_pending_work')
        from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
        from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog, compare_catalogs
        options = {'endpoint_id': 'owned-gate', 'target_id': schema,
            'generation': result['generation'], 'engine': 'mariadb'}
        exported = build_export(result['resources'], **options)
        decoded = read_catalog(json.dumps(exported['snapshot']), engine='mariadb')
        native = build_export(result['resources'], **options, native_model=True)
        assert not compare_catalogs(decoded, native)['changes']
        assert decoded['provenance']['mapping'] == 'scratchrobin.mariadb.catalog@1'
        assert 'scratchrobin.mariadb.relations' in exported['diagram']['snapshot']['files']['relations.ddn']
        proof['checks'].append('native_ddn_catalog_roundtrip_preserves_all_native_facts')
        oracle = provider.capture_catalog({**native_route, 'database': schema,
            'init_command': "SET SESSION sql_mode='ORACLE'"})
        oracle_root = next(row['native'] for row in oracle['resources'] if row['resource_kind'] == 'database')
        assert 'ORACLE' in oracle_root['catalog_row']['sql_mode'].split(',')
        assert 'ORACLE' not in oracle_root['definition_context']['sql_mode'].split(',')
        probe = next(row['native'] for row in oracle['resources'] if row['resource_kind'] == 'table' and row['display_name'] == 'options_probe')
        for option in ['ENGINE=InnoDB', 'ROW_FORMAT=DYNAMIC', 'retained field', 'retained table']:
            assert option in probe['definition'], (option, probe['definition'])
        assert 'NO_TABLE_OPTIONS' not in probe['definition_context']['sql_mode'].split(',')
        proof['checks'].append('oracle_mode_capture_preserves_all_native_show_create_options')

        cursor.execute(f'CREATE ROLE `{role}`')
        cursor.execute(f"CREATE SERVER `{link}` FOREIGN DATA WRAPPER mysql OPTIONS (HOST 'example.invalid', DATABASE '{schema}', USER 'link-user', PASSWORD '{link_password}', PORT 3306)")
        cursor.execute('SELECT PLUGIN_NAME, PLUGIN_TYPE, PLUGIN_LIBRARY FROM information_schema.PLUGINS ORDER BY PLUGIN_NAME, PLUGIN_TYPE')
        (evidence / 'plugin-identities.json').write_text(json.dumps(cursor.fetchall(), indent=2) + '\n')
        server = provider.capture_server_catalog(native_route)
        assert server['server_uid'] == objects['database', schema]['native']['catalog_row']['server_uid']
        assert all(row['available'] for row in server['observations']), server['observations']
        assert any(row['resource_kind'] == 'role' and row['native']['catalog_row']['user'] == role for row in server['resources'])
        link_row = next(row for row in server['resources'] if row['resource_kind'] == 'server-link' and row['display_name'] == link)
        assert link_row['native']['catalog_row']['username'] == 'link-user'
        assert 'password' not in link_row['native']['catalog_row'] and 'options' not in link_row['native']['catalog_row']
        assert link_password not in json.dumps(server)
        server_export = build_export(server['resources'], endpoint_id='owned-gate',
            target_id='server:' + server['server_uid'], generation=server['generation'],
            include_system=True, engine='mariadb')
        decoded_server = read_catalog(json.dumps(server_export['snapshot']), engine='mariadb')
        assert decoded_server['provenance']['objects'] == len(server['resources'])
        proof['checks'].append('native_server_uid_roles_links_and_credential_free_ddn_inventory')
        from pgadmin.cdeadmin.providers.mysql_family.provider import _resources
        discovered = _resources(owner, {'route': {'database': schema}}, MARIADB_PROFILE)
        uuid_plugins = [row for row in discovered if row['resource_kind'] == 'plugin' and row['display_name'] == 'uuid']
        assert len(uuid_plugins) == 2 and len({row['resource_id'] for row in uuid_plugins}) == 2
        assert {row['native']['plugin_type'] for row in uuid_plugins} == {'DATA TYPE', 'FUNCTION'}
        proof['checks'].append('explorer_preserves_native_uuid_type_and_function_plugins')
        cursor.execute("SET SESSION sql_mode=''")
        cursor.execute('CREATE TABLE exact_values (id BIGINT UNSIGNED PRIMARY KEY, amount DECIMAL(65,30), d DATE, dt DATETIME(6), duration TIME(6), payload VARBINARY(20)) ENGINE=InnoDB')
        cursor.execute("INSERT INTO exact_values VALUES (18446744073709551615,12345678901234567890123456789012345.123456789012345678901234567890,'0000-00-00','0000-00-00 00:00:00.123456','-838:59:59.999999',X'00ff0100')")
        data_catalog = provider.capture_catalog({**native_route, 'database': schema})
        relation = next(row['resource_id'] for row in data_catalog['resources'] if row['resource_kind'] == 'table' and row['display_name'] == 'exact_values')
        data_options = {'endpoint_id': 'owned-gate', 'target_id': schema,
            'expected_server_uid': server['server_uid'], 'mode': 'full', 'row_limit': 10}
        data = provider.capture_data({**native_route, 'database': schema}, relation, **data_options)
        assert data['acquisition']['engine_id'] == 'mariadb'
        assert data['acquisition']['rows'] == 1 and data['acquisition']['transaction_completed']
        assert data['acquisition']['consistent_innodb_table_snapshot']
        text = json.dumps(data['snapshot'])
        for exact in ['18446744073709551615','12345678901234567890123456789012345.123456789012345678901234567890',
                      '0000-00-00','0000-00-00 00:00:00.123456','-838:59:59.999999','AP8BAA==']:
            assert exact in text, exact
        (evidence / 'exact-data.json').write_text(json.dumps(data, indent=2) + '\n')
        cursor.execute("INSERT INTO exact_values(id) VALUES (1)")
        try:
            provider.capture_data({**native_route, 'database': schema}, relation, **{**data_options, 'row_limit': 1})
        except ValueError as error:
            assert 'Full data capture exceeds' in str(error)
        else:
            raise AssertionError('Full capture returned a partial download')
        sampled = provider.capture_data({**native_route, 'database': schema}, relation,
            **{**data_options, 'mode': 'sample', 'row_limit': 1})
        assert sampled['acquisition']['more_rows_observed']
        assert sampled['acquisition']['rows'] == 1
        current = provider.capture_data({**native_route, 'database': schema}, objects['table', 'temporal']['resource_id'], **data_options)
        assert current['acquisition']['rows'] == 0 and current['acquisition']['transaction_completed']
        assert interactive.server_status & 1
        assert current['acquisition']['temporal_scope'].startswith('current-visible-rows')
        proof['checks'].append('exact_native_current_relation_data_and_bounded_sample_full_capture')




        (evidence / 'catalog.json').write_text(json.dumps(result, indent=2) + '\n')
        proof['complete'] = True
    finally:
        if client is not None:
            client.close()
        if interactive is not None:
            interactive.rollback()
            interactive.close()
        cursor.execute(f'DROP SERVER IF EXISTS `{link}`')
        cursor.execute(f'DROP ROLE IF EXISTS `{role}`')
        cursor.execute(f'DROP DATABASE IF EXISTS `{schema}`')
        cursor.close()
        owner.close()
        (evidence / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='mariadb:12.2.2')
    parser.add_argument('--evidence', type=Path, required=True)
    options = parser.parse_args()
    result = run(options.image, options.evidence, qualify)
    raise SystemExit(0 if result['complete'] else 1)
