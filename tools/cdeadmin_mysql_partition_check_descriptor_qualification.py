"""Owned partition/CHECK descriptor qualification with both drivers and APIs.

Projected native inputs are qualified separately from the shared dialog,
whose projection dispatch remains UI Decision12.
"""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def qualify(output):
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Keep native evidence outside source')
    output.mkdir(parents=True, exist_ok=False)
    app = setup_application(output)
    from mysql_qualification_support import server, _root_connection
    from cdeadmin_mysql_partition_qualification import qualify as partitions
    from cdeadmin_mysql_constraints_qualification import qualify as checks
    from cdeadmin_mysql_online_ddl_qualification import registration
    from pgadmin.cdeadmin.providers.mysql_family.provider import _resources, MYSQL_PROFILE
    from pgadmin.cdeadmin.providers.mysql_tablespaces import identifier
    from ui_descriptor_roundtrip import backend_draft, engine_operations, operation_draft
    paths = ['web/pgadmin/cdeadmin/ui_descriptors/mysql/operations.json',
             'web/pgadmin/cdeadmin/providers/relational_admin.py',
             'web/pgadmin/cdeadmin/providers/mysql_descriptor_contract.py',
             str(Path(__file__).relative_to(ROOT))]
    declarations = engine_operations('mysql')
    proof = {'complete': False, 'native_interfaces': [], 'application': [],
             'actual_operation_dialog_qualified': False, 'history_testing': 'ScratchBird history not run',
             'source_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}}
    owned = None
    try:
        with server(output / 'fixture') as (route, _name, owned):
            import mysql.connector
            for pure in (True, False):
                options = {'host': route['host'], 'port': route['port'], 'user': 'root', 'use_pure': pure}
                handle = mysql.connector.connect(**options)
                try:
                    connection_class = type(handle).__name__
                    assert connection_class == ('MySQLConnection' if pure else 'CMySQLConnection'), connection_class
                finally:
                    handle.close()
                partitions(options, output / ('partitions-' + str(pure)), descriptor_inputs=True)
                checks(options, output / ('checks-' + str(pure)), descriptor_inputs=True)
                proof['native_interfaces'].append({'use_pure': pure, 'native_connection_class': connection_class,
                                                   'partition_and_check_native_data_semantics': True})
            oracle = _root_connection('mysql', route['port'])
            oracle.autocommit = True
            q = oracle.cursor()
            try:
                q.execute('CREATE DATABASE sr_osc')
                q.execute('CREATE TABLE sr_osc.pending(id INT PRIMARY KEY)')
                password = secrets.token_urlsafe(24)
                q.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s', (password,))
                for pure in (True, False):
                    _sid, _target, post = registration(app, route, password, not pure)
                    tag = str(pure)
                    constraint = 'c_positive_' + tag
                    name, swap, checked = 't . ` 雪' + tag, 'swap . ` 雪' + tag, 'check . ` 雪' + tag
                    address = 'sr_osc.' + identifier(name)
                    other = 'sr_osc.' + identifier(swap)
                    check_table = 'sr_osc.' + identifier(checked)
                    q.execute('CREATE TABLE ' + address + ' (id INT PRIMARY KEY) PARTITION BY RANGE(id) '
                              '(PARTITION p0 VALUES LESS THAN (10), PARTITION p1 VALUES LESS THAN (20))')
                    q.execute('INSERT INTO ' + address + ' VALUES(1),(11)')
                    q.execute('CREATE TABLE ' + other + ' (id INT PRIMARY KEY)')
                    q.execute('INSERT INTO ' + other + ' VALUES(5)')
                    q.execute('CREATE TABLE ' + check_table + ' (id INT PRIMARY KEY, CONSTRAINT ' + identifier(constraint) + ' CHECK(id > 0))')
                    operations = []

                    def run(kind, operation, values=None, leaf=None):
                        path = ['sr_osc', checked if kind == 'constraint' else name] + ([leaf] if leaf else [])
                        resources = _resources(oracle, {'route': {**route, 'database': 'sr_osc'}}, MYSQL_PROFILE)
                        target = next(row for row in resources if row['resource_kind'] == kind and row['display_path'] == path)
                        if operation == 'drop':
                            draft = {'confirmation': target['display_name']}
                        else:
                            declaration = declarations[operation + '@' + kind]
                            ui = operation_draft(declaration, values, target['display_name'])
                            draft = backend_draft({'tabs': [{'fields': declaration['fields']}]}, ui)
                        request = {'resource_kind': kind, 'operation_id': operation, 'target_resource': target, 'draft': draft}
                        oracle.autocommit = False
                        q.execute('SAVEPOINT descriptor_guard')
                        q.execute('INSERT INTO sr_osc.pending VALUES(1)')
                        validated = post('visual_admin_validate', request)
                        assert validated['valid'], validated['errors']
                        planned = post('visual_admin_plan', request)
                        assert planned['state'] == 'ready' and planned['execution_available']
                        apply = {key: planned[key] for key in ('plan_id', 'plan_digest')} | {'confirmed': True}
                        result = post('visual_admin_apply', apply)
                        assert result['provider_result']['accepted']
                        replay = post.raw('visual_admin_apply', apply)
                        assert replay.status_code != 200 or not replay.get_json().get('success')
                        q.execute('SELECT ROW_COUNT()')
                        assert q.fetchone() == (1,)
                        q.execute('ROLLBACK TO SAVEPOINT descriptor_guard')
                        oracle.rollback()
                        oracle.autocommit = True
                        operations.append(kind + '.' + operation)

                    for operation in ('analyze', 'check', 'optimize', 'rebuild'):
                        run('partition', operation, leaf='p0')
                    exchange = {'exchange_database': 'sr_osc', 'exchange_table': swap}
                    run('partition', 'exchange', exchange, 'p0')
                    q.execute('SELECT id FROM ' + other)
                    assert q.fetchall() == [(1,)]
                    run('partition', 'exchange', {**exchange, 'validation': 'WITHOUT VALIDATION'}, 'p0')
                    run('partition', 'reorganize', {'partitions': [{'value': 'p1'}],
                                                  'definitions': 'PARTITION pa VALUES LESS THAN(15), PARTITION pb VALUES LESS THAN(20)'}, 'p1')
                    run('table', 'add_partitions', {'definitions': 'PARTITION p2 VALUES LESS THAN(30)'})
                    q.execute('INSERT INTO ' + address + ' VALUES(25)')
                    run('partition', 'drop', leaf='p2')
                    run('partition', 'truncate', leaf='p0')
                    run('table', 'remove_partitioning')
                    run('table', 'partition_by', {'partition_clause': 'PARTITION BY HASH(id) PARTITIONS 4'})
                    run('table', 'coalesce_partitions', {'count': 2})
                    run('table', 'add_partitions', {'mode': 'COUNT', 'count': 2})
                    q.execute('SELECT id FROM ' + address)
                    assert q.fetchall() == [(11,)]
                    run('constraint', 'enforcement', {'enforcement': 'NOT ENFORCED'}, constraint)
                    q.execute('INSERT INTO ' + check_table + ' VALUES(-1)')
                    q.execute('DELETE FROM ' + check_table)
                    run('constraint', 'enforcement', {'enforcement': 'ENFORCED'}, constraint)
                    try:
                        q.execute('INSERT INTO ' + check_table + ' VALUES(-1)')
                    except mysql.connector.Error as error:
                        assert error.errno == 3819
                    else:
                        raise AssertionError('Native CHECK accepted invalid data after enforcement')
                    proof['application'].append({'use_pure': pure, 'operations': operations,
                                                'data_effects_verified': True, 'diagnostics_and_savepoint_preserved': True,
                                                'consumed_plans_refused': True})
                proof['complete'] = True
            finally:
                q.close()
                oracle.close()
    finally:
        proof['owned_server_stopped'] = bool(owned and owned['owned_server_stopped'])
        (output / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    result = qualify(parser.parse_args().output)
    print(json.dumps({'complete': result['complete'], 'native_interfaces': len(result['native_interfaces'])}))
