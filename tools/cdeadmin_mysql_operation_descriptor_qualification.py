"""Owned native/cache API qualification of descriptor-projected operation inputs.

This does not qualify OperationDialog projection, which is UI Decision12.
"""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def qualify(output):
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Keep native evidence outside source')
    output.mkdir(parents=True, exist_ok=False)
    app = setup_application(output)
    from cdeadmin_mysql_online_ddl_qualification import registration
    from mysql_qualification_support import server, _root_connection
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE, MYSQL_ADMINISTRATION, _create_client
    from pgadmin.cdeadmin.providers.mysql_family.mysql_key_cache import address
    from ui_descriptor_roundtrip import backend_draft, engine_operations, operation_draft

    operations = engine_operations('mysql')
    paths = ['web/pgadmin/cdeadmin/ui_descriptors/mysql/operations.json',
             'web/pgadmin/cdeadmin/providers/mysql_descriptor_contract.py',
             'web/pgadmin/cdeadmin/providers/mysql_family/administration.py',
             str(Path(__file__).relative_to(ROOT))]
    proof = {'complete': False, 'interfaces': [], 'application': [],
             'actual_operation_dialog_qualified': False, 'shared_projection_gap': 'Decision12',
             'history_testing': 'ScratchBird history not run',
             'source_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}}
    owned = None
    try:
        with server(output / 'fixture') as (route, _container, owned):
            oracle = _root_connection('mysql', route['port'])
            oracle.autocommit = True
            q = oracle.cursor()
            try:
                q.execute('CREATE DATABASE sr_osc')
                q.execute('CREATE TABLE sr_osc.pending(id INT PRIMARY KEY) ENGINE=InnoDB')
                q.execute('CREATE TABLE sr_osc.owned(id INT PRIMARY KEY,value INT,KEY `index . `` 雪`(value)) ENGINE=MyISAM')
                q.execute('INSERT INTO sr_osc.owned VALUES(1,10),(2,20)')
                q.execute('SELECT @@server_uuid')
                resource = {'resource_kind': 'server', 'resource_id': 'server:MySQL',
                            'display_name': 'MySQL', 'display_path': ['MySQL'], 'native': {'server_uuid': q.fetchone()[0]}}
                table = {'resource_kind': 'table', 'resource_id': address(['sr_osc', 'owned']),
                         'display_name': 'owned', 'display_path': ['sr_osc', 'owned']}

                def request(operation, **values):
                    target = table if operation in {'assign_index_cache', 'preload_index_cache'} else resource
                    declared = operations[operation + '@' + target['resource_kind']]
                    ui = operation_draft(declared, values, target['display_name'])
                    draft = backend_draft({'tabs': [{'fields': declared['fields']}]}, ui)
                    return {'resource_kind': target['resource_kind'], 'operation_id': operation,
                            'target_resource': target, 'draft': draft}

                def cases(name):
                    return [('configure_key_cache', {'cache_name': name, 'value': '4194305'}),
                            ('configure_key_cache', {'cache_name': name, 'variable': 'key_cache_block_size', 'value_mode': 'DEFAULT'}),
                            ('assign_index_cache', {'cache_name': name, 'indexes': [{'value': 'index . ` 雪'}]}),
                            ('preload_index_cache', {'indexes': [{'value': 'index . ` 雪'}], 'ignore_leaves': True}),
                            ('inspect_key_cache', {'cache_name': name}),
                            ('release_key_cache', {'cache_name': name})]

                for pure in (True, False):
                    selected = {**route, 'database': 'sr_osc', 'use_pure': pure}
                    client = _create_client(MYSQL_PROFILE, SimpleNamespace(acquire_secret=None), SimpleNamespace())
                    classes = []
                    connect = client._connect

                    def tracked(payload):
                        handle = connect(payload)
                        classes.append(type(handle).__name__)
                        return handle

                    client._connect = tracked
                    try:
                        for operation, values in cases('cache . ` 雪' + str(pure)):
                            payload = {**request(operation, **values), '_provider_route': selected}
                            assert not MYSQL_ADMINISTRATION.validate(payload)['errors']
                            oracle.autocommit = False
                            q.execute('SAVEPOINT descriptor_guard')
                            q.execute('INSERT INTO sr_osc.pending VALUES(1)')
                            planned = client.plan_admin_operation(payload)
                            result = MYSQL_ADMINISTRATION.apply(client, planned)
                            assert result['accepted']
                            q.execute('SELECT ROW_COUNT()')
                            assert q.fetchone() == (1,)
                            q.execute('ROLLBACK TO SAVEPOINT descriptor_guard')
                            oracle.rollback()
                            oracle.autocommit = True
                            if operation == 'configure_key_cache':
                                values_after = result['key_cache_observation']['after']['native_values']
                                assert values_after['key_buffer_size'] == '4194304'
                                if values.get('value_mode') == 'DEFAULT':
                                    assert values_after['key_cache_block_size'] == '1024'
                        expected = 'CharsetMySQLConnection' if pure else 'CharsetCMySQLConnection'
                        assert set(classes) == {expected}
                        proof['interfaces'].append({'native_connection_class': expected, 'operations': 6,
                                                    'descriptor_projection': True, 'diagnostics_and_savepoint_preserved': True})
                    finally:
                        client.close()
                password = secrets.token_urlsafe(24)
                q.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s', (password,))
                for pure in (True, False):
                    _sid, _target, post = registration(app, route, password, not pure)
                    for operation, values in cases('api_cache_' + str(pure)):
                        payload = request(operation, **values)
                        checked = post('visual_admin_validate', payload)
                        assert checked['valid'], checked['errors']
                        planned = post('visual_admin_plan', payload)
                        assert planned['state'] == 'ready' and planned['execution_available']
                        apply = {key: planned[key] for key in ('plan_id', 'plan_digest')} | {'confirmed': True}
                        result = post('visual_admin_apply', apply)
                        assert result['provider_result']['accepted']
                        replay = post.raw('visual_admin_apply', apply)
                        assert replay.status_code != 200 or not replay.get_json().get('success')
                    proof['application'].append({'use_pure': pure, 'authenticated_projected_inputs': True, 'consumed_plans_refused': True})
                q.execute('SELECT id,value FROM sr_osc.owned ORDER BY id')
                assert q.fetchall() == [(1, 10), (2, 20)]
                q.execute('SELECT COUNT(*) FROM sr_osc.pending')
                assert q.fetchone() == (0,)
                proof['existing_rows_preserved'] = True
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
    print(json.dumps({'complete': result['complete'], 'interfaces': len(result['interfaces'])}))
