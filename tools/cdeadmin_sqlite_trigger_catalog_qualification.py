"""Owned SQLite TEMP trigger catalog, authenticated session API and DDN evidence."""
import argparse
import builtins
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def qualify(output):
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    builtins.SERVER_MODE = None
    import config
    config.SERVER_MODE = False;config.TESTING = True;config.WTF_CSRF_ENABLED = False
    config.MASTER_PASSWORD_REQUIRED = False;config.USE_OS_SECRET_STORAGE = False
    for option, value in {'DATA_DIR':'app', 'SQLITE_PATH':'app/application.db', 'SESSION_DB_PATH':'app/sessions',
            'STORAGE_DIR':'app/storage', 'LOG_FILE':'app/application.log', 'AZURE_CREDENTIAL_CACHE_DIR':'app/azure',
            'CDEADMIN_OPERATION_STORE_PATH':'app/operations.json'}.items():setattr(config, option, str(output / value))
    from pgadmin import create_app
    from pgadmin.model import db, User, ServerGroup, Server, EndpointDatabaseTarget
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
    from flask import url_for
    paths = ['tools/cdeadmin_sqlite_trigger_catalog_qualification.py',
        'web/pgadmin/cdeadmin/providers/sqlite/provider.py', 'web/pgadmin/cdeadmin/providers/sqlite/trigger_owners.py',
        'web/pgadmin/cdeadmin/providers/sqlite/driver.py', 'web/pgadmin/cdeadmin/providers/embedded_session_catalog.py',
        'web/pgadmin/cdeadmin/providers/native_editor.py', 'web/pgadmin/cdeadmin/data_studio/studio.py',
        'web/pgadmin/cdeadmin/data_studio/models.py',
        'web/pgadmin/cdeadmin/workspace/service.py', 'web/pgadmin/cdeadmin/workspace/firebird_catalog_export.py',
        'web/pgadmin/cdeadmin/workspace/firebird_catalog_import.py']
    proof = {'complete':False, 'history_testing':'not run', 'full_product_complete':False,
        'sqlite_version':sqlite3.sqlite_version,
        'source_sha256':{path:hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths}}
    assert sqlite3.sqlite_version == '3.53.0'
    database = output / 'primary.sqlite'
    with sqlite3.connect(database) as setup:
        setup.executescript('CREATE TABLE same(id INTEGER);CREATE TABLE effects(id INTEGER);')
        proof['sqlite_source_id'] = setup.execute('SELECT sqlite_source_id()').fetchone()[0]
    app = create_app('ScratchRobin owned TEMP trigger catalog');app.PGADMIN_RUNTIME = False;app.PGADMIN_INT_KEY = ''
    app.run_before_app_start();client = app.test_client();session_id = None
    try:
        with app.test_request_context('/'):
            owner = User.query.first().id;group = ServerGroup(user_id=owner, name='Owned TEMP trigger catalog')
            db.session.add(group);db.session.commit()
            server = Server(user_id=owner, servergroup_id=group.id, name='Owned SQLite triggers', host=None,
                port=1, username='', maintenance_db=str(database), save_password=0)
            server._cde_endpoint_registration = registration_profile('sqlite-native')
            server._cde_endpoint_route_configuration = {'database':str(database), 'filesystem_root':str(output)}
            db.session.add(server);db.session.commit();target = str(uuid.uuid4());other = str(uuid.uuid4())
            for identity in (target, other):
                db.session.add(EndpointDatabaseTarget(id=identity, endpoint_id=server.endpoint_profile.id,
                    display_name=identity, database=str(database), configuration='{}', active=1))
            db.session.commit()
            url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=server.id)
            verify = url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=server.id)
        with client.session_transaction() as login:login['_user_id'] = str(owner);login['_fresh'] = True
        assert client.post(verify, json={}).get_json()['success']
        def post(action, refused=False, **fields):
            response = client.post(url, json={'action':action, 'database_target_id':target, **fields})
            result = response.get_json()
            if refused:
                assert response.status_code in {400, 403}, result
                return result
            assert response.status_code == 200 and result.get('success'), result
            return result['data']
        session_id = post('open_session', language_profile='sqlite-sql')['session_id']
        def execute(source):
            started = post('execute', session_id=session_id, source=source, parameters={}, history_sensitive=True)
            deadline = time.monotonic() + 30;rows = []
            while time.monotonic() < deadline:
                occurrence = post('poll', occurrence_id=started['occurrence_id'])['occurrence']
                payload = (occurrence.get('result') or {}).get('extensions', {}).get('sqlite', {}).get('payload', {})
                rows.extend(payload.get('rows') or [])
                if occurrence['operation']['terminal']:
                    assert not payload.get('error'), payload
                    return rows
                time.sleep(.02)
            raise TimeoutError('Native SQLite session query')
        for source in ["ATTACH ':memory:' AS aux", 'CREATE TABLE aux.same(id INTEGER)',
                'CREATE TEMP TABLE same(id INTEGER)',
                'CREATE TRIGGER main.equal AFTER INSERT ON main.same BEGIN SELECT 1; END',
                'CREATE TEMP TRIGGER equal AFTER INSERT ON aux.same BEGIN INSERT INTO effects VALUES(NEW.id); END',
                'CREATE TEMP TRIGGER ambiguous AFTER INSERT ON same BEGIN SELECT 1; END',
                'BEGIN', 'INSERT INTO effects VALUES(42)']:
            execute(source)
        observed = post('source_catalog', session_id=session_id)
        temporary = next(row for row in observed['resources'] if row['resource_kind'] == 'trigger' and row['display_path'] == ['temp', 'equal'])
        binding = temporary['native']['owner_binding_observation']
        assert binding['available'] and binding['database'] == 'aux' and binding['table'] == 'same'
        assert not binding['existing_trigger_execution_observed']
        ambiguous = next(row for row in observed['resources'] if row['resource_kind'] == 'trigger' and row['display_name'] == 'ambiguous')
        assert not ambiguous['native']['owner_binding_observation']['available']
        assert len({row['resource_id'] for row in observed['resources'] if row['resource_kind'] == 'trigger'}) == 3
        model = read_catalog(json.dumps(observed['document']['snapshot']), engine='sqlite')
        assert model['rows'][temporary['resource_id']]['native']['catalog_metadata']['owner_database'] == 'aux'
        assert model['provenance']['observation_scope'] == 'retained-session'
        assert execute('SELECT * FROM effects') == [[42]]
        with sqlite3.connect(database) as independent:
            assert independent.execute('SELECT * FROM effects').fetchall() == []
        execute('INSERT INTO aux.same VALUES(73)')
        assert execute('SELECT * FROM effects ORDER BY id') == [[42], [73]]
        post('source_catalog', refused=True, session_id=session_id, database_target_id=other)
        post('transaction_action', session_id=session_id, transaction_action='rollback')
        assert execute('SELECT * FROM effects') == []
        post('close_session', session_id=session_id)
        post('source_catalog', refused=True, session_id=session_id)
        session_id = None
        proof.update(complete=True, authenticated_original_session_catalog=True,
            native_namespace_and_attached_owner_exact=True, same_name_namespaces_distinct=True,
            ambiguous_owner_explicit=True, native_ddn_preserves_owner_and_session_scope=True,
            capture_executed_neither_trigger_nor_probe_ddl=True, independent_pending_rows_invisible=True,
            actual_trigger_execution_verified=True, explicit_caller_rollback_verified=True,
            other_target_and_closed_session_refused=True)
    finally:
        if session_id is not None:
            response = client.post(url, json={'action':'close_session', 'database_target_id':target, 'session_id':session_id})
            proof['session_cleanup_failed'] = response.status_code != 200
        proof['owned_sessions_released'] = not app.extensions['cdeadmin_data_studio']._sessions
        (output / 'proof.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence', required=True, type=Path)
    value = qualify(parser.parse_args().evidence);print(json.dumps({'complete':value['complete']}))
