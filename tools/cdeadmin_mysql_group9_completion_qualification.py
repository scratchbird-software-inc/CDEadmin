"""Native MySQL9.7 evidence for the seven remaining Group9 backend gaps."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import secrets
from types import SimpleNamespace
from uuid import uuid4
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'web'), str(ROOT/'tools')]


def native(output, proof):
    from mysql_qualification_support import server, _root_connection
    from pgadmin.cdeadmin.providers.mysql_family.provider import _create_client, MYSQL_PROFILE
    from pgadmin.cdeadmin.providers.mysql_family.mysql_completion import complete
    from pgadmin.cdeadmin.providers.mysql_family.mysql_connections import Connector
    from pgadmin.cdeadmin.security import SecretLease
    import mysql.connector
    fixtures = []
    try:
        with server(output/'first') as (route, _name, fixture), server(output/'second', server_id=102, performance_schema=False) as (other, _other_name, second):
            fixtures += [fixture, second]
            oracle = _root_connection('mysql', route['port']); oracle.autocommit = True; q = oracle.cursor()
            alternate = _root_connection('mysql', other['port']); alternate.autocommit = True; aq = alternate.cursor()
            try:
                q.execute('CREATE DATABASE sr_osc')
                q.execute('CREATE TABLE sr_osc.pending(id INT PRIMARY KEY)')
                q.execute('CREATE TABLE sr_osc.shadow(base_column INT)')
                q.execute('CREATE TABLE sr_osc.parent(id INT PRIMARY KEY)')
                q.execute("CREATE ROLE 'group9_role'@'%'")
                q.execute("GRANT 'group9_role'@'%' TO CURRENT_USER()")
                target_password = secrets.token_urlsafe(32)
                aq.execute("CREATE USER 'group9_target'@'%' IDENTIFIED BY %s", (target_password,))
                aq.execute('CREATE DATABASE sr_osc')
                for pure in (True, False):
                    client = _create_client(MYSQL_PROFILE, SimpleNamespace(acquire_secret=lambda *_: SecretLease(target_password)), SimpleNamespace())
                    handle = client.open_session({'route': {**route, 'database': 'sr_osc', 'use_pure': pure, 'autocommit': False}})
                    work = handle.cursor()
                    session_id = str(uuid4())
                    def plan(kind, operation, draft, target=None, retained=False):
                        return client.plan_admin_operation({'resource_kind': kind, 'operation_id': operation,
                            'draft': draft, 'target_resource': target,
                            '_provider_route': {**route, 'database': 'sr_osc', 'use_pure': pure},
                            **({'session_id': session_id} if retained else {})})
                    def apply(planned, retained=False):
                        return client.apply_admin_operation({**planned, **({'_provider_session_handle': handle} if retained else {})})
                    try:
                        work.execute('INSERT INTO pending VALUES(1)'); work.execute('SAVEPOINT group9_guard')
                        create = plan('table', 'create', {'name': 'shadow', 'parent': 'sr_osc', 'temporary': True,
                            'columns': [{'name': 'temporary_column', 'type': 'INT'}]}, retained=True)
                        assert apply(create, True)['commit_requested'] is False
                        work.execute('INSERT INTO shadow VALUES(9)'); work.execute('ROLLBACK TO SAVEPOINT group9_guard')
                        q.execute('SELECT COUNT(*) FROM sr_osc.pending'); assert q.fetchone() == (0,)
                        q.execute('SHOW COLUMNS FROM sr_osc.shadow'); assert q.fetchone()[0] == 'base_column'
                        work.execute("SET ROLE 'group9_role'@'%'")
                        server_target = {'resource_kind': 'server', 'display_name': 'Owned native server', 'display_path': []}
                        refresh = plan('server', 'refresh_session_metadata', {'confirmation': server_target['display_name'],
                            'replace_diagnostics': True, 'temporary_tables': [{'database': 'sr_osc', 'name': 'shadow'}]}, server_target, True)
                        snapshot = apply(refresh, True)['session_catalog']
                        assert snapshot['active_role'] == '`group9_role`@`%`' and snapshot['original_diagnostics_preserved'] is False
                        metadata = complete(client, handle)
                        assert metadata['context']['original_active_roles_observed'] and metadata['original_session_commands_sent'] == 0
                        columns = [row['display_path'][-1] for row in metadata['resources'] if row['resource_kind'] == 'column' and row['display_path'][:2] == ['sr_osc', 'shadow']]
                        assert columns == ['temporary_column'], columns
                        work.execute('ROLLBACK TO SAVEPOINT group9_guard')
                        drop = plan('table', 'drop_temporary', {'confirmation': 'shadow'},
                            {'resource_kind': 'table', 'display_name': 'shadow', 'display_path': ['sr_osc', 'shadow']}, True)
                        assert apply(drop, True)['commit_requested'] is False
                        work.execute('SHOW COLUMNS FROM shadow'); assert work.fetchone()[0] == 'base_column'; work.fetchall()
                        work.execute('ROLLBACK TO SAVEPOINT group9_guard'); handle.rollback()
                        suffix = 'pure' if pure else 'c'
                        child = plan('table', 'create', {'name': 'child_'+suffix, 'parent': 'sr_osc',
                            'columns': [{'name': 'id', 'type': 'INT'}], 'constraints': [{'kind': 'FOREIGN KEY',
                                'columns': ['id'], 'references_table': ['sr_osc', 'parent'], 'references_columns': ['id'],
                                'on_delete': 'CASCADE', 'on_update': 'SET NULL'}]})
                        apply(child)
                        q.execute('INSERT INTO sr_osc.parent VALUES(1),(2)')
                        q.execute('INSERT INTO sr_osc.child_'+suffix+' VALUES(1),(2)')
                        q.execute('DELETE FROM sr_osc.parent WHERE id=1'); q.execute('UPDATE sr_osc.parent SET id=3 WHERE id=2')
                        q.execute('SELECT id FROM sr_osc.child_'+suffix); assert q.fetchall() == [(None,)]
                        q.execute('DROP TABLE sr_osc.child_'+suffix); q.execute('DELETE FROM sr_osc.parent')
                        unchecked = plan('table', 'create', {'name': 'unchecked_'+suffix, 'parent': 'sr_osc',
                            'columns': [{'name': 'id', 'type': 'INT'}], 'constraints': [{'kind': 'CHECK', 'expression': 'id>0', 'enforced': False}]})
                        apply(unchecked); q.execute('INSERT INTO sr_osc.unchecked_'+suffix+' VALUES(-1)')
                        q.execute("SELECT ENFORCED FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA='sr_osc' AND TABLE_NAME=%s AND CONSTRAINT_TYPE='CHECK'", ('unchecked_'+suffix,))
                        assert q.fetchone() == ('NO',)
                        q.execute('DROP TABLE sr_osc.unchecked_'+suffix)
                        leases = []
                        def acquire(reference, principal, purpose, kind):
                            assert (reference, principal, purpose, kind) == ('owned-target', 'user:7', 'connect', 'database_password')
                            lease = SecretLease(target_password); leases.append(lease); return lease
                        connector = Connector(mysql.connector, acquire)
                        try:
                            targets = [{'host': route['host'], 'port': route['port'], 'user': 'group9_target', 'priority': 100,
                                'credential_reference_id': 'owned-target', 'pool_name': 'same', 'pool_size': 1},
                                {'host': other['host'], 'port': other['port'], 'user': 'group9_target', 'priority': 50,
                                'credential_reference_id': 'owned-target', 'pool_name': 'same', 'pool_size': 1}]
                            lease = connector.connect('user:7', use_pure=pure, failover=targets)
                            cursor = lease.cursor(); cursor.execute('SELECT @@server_uuid,CURRENT_USER()'); reached = cursor.fetchone(); cursor.close()
                            aq.execute('SELECT @@server_uuid'); assert reached == (aq.fetchone()[0], 'group9_target@%')
                            cursor = lease.cursor(); cursor.execute('SET @group9_pool=9'); cursor.close(); lease.close()
                            reused = connector.connect('user:7', use_pure=pure, failover=targets)
                            cursor = reused.cursor(); cursor.execute('SELECT @group9_pool'); assert cursor.fetchone() == (None,); cursor.close(); reused.close()
                            assert len(connector._pools) == 2 and all(value.closed for value in leases)
                            replacement_password = secrets.token_urlsafe(32)
                            aq.execute("ALTER USER 'group9_target'@'%' IDENTIFIED BY %s", (replacement_password,))
                            target_password = replacement_password
                            rotated = connector.connect('user:7', use_pure=pure, failover=targets)
                            rotated.close()
                        finally: connector.close()
                        effective = _create_client(MYSQL_PROFILE, SimpleNamespace(acquire_secret=acquire), SimpleNamespace())
                        try:
                            selected_handle = effective.open_session({'route': {**route, 'use_pure': pure,
                                'principal_reference': 'user:7', 'failover': targets}})
                            selected_request = effective._session_requests[id(selected_handle)]['route']
                            assert selected_request['user'] == 'group9_target' and selected_request['credential_reference_id'] == 'owned-target'
                            assert 'failover' not in selected_request and target_password not in str(selected_request)
                            effective.close_session(selected_handle)
                        finally: effective.close()
                        from pgadmin.cdeadmin.providers.mysql_family.mysql_parser import library, native as parse
                        sources = [row['source'] for compiled in (create, refresh, drop, child, unchecked) for row in compiled['provider_payload']['compiled']['statements']]
                        sources += ['SELECT CURRENT_ROLE(), CURRENT_USER(), DATABASE()', 'SELECT ROLE_NAME, ROLE_HOST FROM information_schema.ENABLED_ROLES ORDER BY ROLE_NAME, ROLE_HOST', 'SHOW CREATE TABLE `sr_osc`.`shadow`', 'SHOW FULL COLUMNS FROM `sr_osc`.`shadow`']
                        parser = parse(library(client), [{'source': source, 'sql_mode': ''} for source in sources])
                        assert all(row['sql_syntax_valid'] for row in parser['statements'])
                        proof['parser'] = {key: parser[key] for key in ('library_sha256', 'worker_sha256', 'parser_version')}
                        proof['interfaces'].append({'native_connection_class': type(handle).__name__,
                            'temporary_lifecycle_and_savepoint': True, 'explicit_roles_and_temp_shadow': True,
                            'foreign_key_actions': True, 'unenforced_check': True, 'protected_target_failover_and_pool_reset': True,
                            'templates': {'drop_temporary': drop['provider_payload']['compiled']['statements'][0]['source'],
                                'refresh_session_metadata': sources[-4]}})
                    finally:
                        work.close(); client.close_session(handle); client.close()
                    # Explicit source inspection also works without the private
                    # observation dependency; later automatic reads use only
                    # that selected, command-invalidated native snapshot.
                    client = _create_client(MYSQL_PROFILE, SimpleNamespace(acquire_secret=None), SimpleNamespace())
                    handle = client.open_session({'route': {**other, 'database': 'sr_osc', 'use_pure': pure,
                        'pool_name': 'owned-temp', 'pool_size': 1, 'pool_reset_session': False}})
                    try:
                        request = {'resource_kind': 'table', 'operation_id': 'create', 'session_id': str(uuid4()),
                            '_provider_route': {**other, 'database': 'sr_osc', 'use_pure': pure},
                            'draft': {'name': 'without_instrumentation', 'parent': 'sr_osc', 'temporary': True,
                                'columns': [{'name': 'id', 'type': 'INT'}]}}
                        created = client.plan_admin_operation(request)
                        client.apply_admin_operation({**created, '_provider_session_handle': handle})
                        refresh = client.plan_admin_operation({**request, 'resource_kind': 'server', 'operation_id': 'refresh_session_metadata',
                            'target_resource': {'resource_kind': 'server', 'display_name': 'Owned uninstrumented server'},
                            'draft': {'confirmation': 'Owned uninstrumented server', 'replace_diagnostics': True,
                                'temporary_tables': [{'database': 'sr_osc', 'name': 'without_instrumentation'}]}})
                        client.apply_admin_operation({**refresh, '_provider_session_handle': handle})
                        assert complete(client, handle)['observation_source'] == 'explicit-source-session-snapshot'
                        first_id = handle.connection_id
                    finally:
                        client.close_session(handle)
                    replacement = client.open_session({'route': {**other, 'database': 'sr_osc', 'use_pure': pure,
                        'pool_name': 'owned-temp', 'pool_size': 1, 'pool_reset_session': False}})
                    try:
                        assert replacement.connection_id != first_id
                        check = replacement.cursor()
                        try:
                            from pgadmin.cdeadmin.providers.mysql_family.mysql_charsets import explicit_source
                            with explicit_source(replacement):
                                try: check.execute('SELECT * FROM without_instrumentation')
                                except mysql.connector.Error as error: assert error.errno == 1146
                                else: raise AssertionError('Temporary object crossed logical session close')
                            if not pure:
                                from pgadmin.cdeadmin.sdk import RelationalClientError
                                try: check.execute('SELECT 1')
                                except RelationalClientError as error: assert error.original_session_commands_sent == 0
                                else: raise AssertionError('Explicit conversion scope escaped its task')
                        finally: check.close()
                        proof['interfaces'][-1]['disabled_instrumentation_and_pool_lifetime'] = True
                    finally:
                        client.close_session(replacement); client.close()
            finally:
                q.close(); oracle.close(); aq.close(); alternate.close()
    finally:
        proof['owned_servers_stopped'] = bool(fixtures) and all(row['owned_server_stopped'] for row in fixtures)


def application(app, output, proof):
    from mysql_qualification_support import server, _root_connection
    from cdeadmin_mysql_online_ddl_qualification import registration
    from pgadmin.cdeadmin.security.generated_passwords import PasswordResults
    from unittest.mock import patch
    import mysql.connector
    owned = []
    app.config.update(CDEADMIN_GENERATED_PASSWORD_KEYS={'native': base64.b64encode(secrets.token_bytes(32)).decode('ascii')},
        CDEADMIN_GENERATED_PASSWORD_ACTIVE_KEY_ID='native', CDEADMIN_GENERATED_PASSWORD_PATH=str(output/'protected-results'))
    proof['application'] = []
    try:
        with server(output/'fixture') as (route, _name, fixture):
            owned.append(fixture)
            oracle = _root_connection('mysql', route['port']); oracle.autocommit = True; q = oracle.cursor()
            try:
                q.execute('CREATE DATABASE sr_osc')
                password = secrets.token_urlsafe(32); q.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s', (password,))
                for pure in (True, False):
                    sid, target, post = registration(app, route, password, not pure)
                    username = 'api_protected_' + ('pure' if pure else 'c')
                    request = {'resource_kind': 'user', 'operation_id': 'create',
                        'draft': {'name': username, 'host': '%', 'authentication_mode': 'RANDOM_PASSWORD'}}
                    invalid = post.raw('visual_admin_plan', {**request, 'draft': {**request['draft'], 'unknown_field': 'must-not-appear'}})
                    assert invalid.status_code == 422 and invalid.headers['Cache-Control'] == 'no-store'
                    assert 'must-not-appear' not in invalid.get_data(as_text=True)
                    plan = post('visual_admin_plan', request)
                    apply = {'plan_id': plan['plan_id'], 'plan_digest': plan['plan_digest'], 'confirmed': True}
                    result = post('visual_admin_apply', apply)
                    recovered = post('protected_password_result', {'operation': 'recover', 'plan_id': plan['plan_id']})
                    assert recovered['state'] == 'published' and len(recovered['passwords']) == 1
                    ref = recovered['passwords'][0]['secret_reference_id']
                    revealed = post('protected_password_result', {'operation': 'reveal', 'reference_id': ref, 'confirmed': True})
                    generated = revealed['password']
                    assert generated not in json.dumps(plan) + json.dumps(result) + json.dumps(recovered)
                    authenticated = mysql.connector.connect(host=route['host'], port=route['port'], user=username, password=generated, use_pure=pure)
                    authenticated.close()
                    replay = post.raw('visual_admin_apply', apply)
                    assert replay.status_code == 409 and replay.get_json()['info'] == 'VISUAL_ADMIN_PLAN_STALE'
                    assert replay.headers['Cache-Control'] == 'no-store'
                    # Fail after durable publication, before the account API returns.
                    alter = post('visual_admin_plan', {'resource_kind': 'user', 'operation_id': 'alter',
                        'target_resource': {'resource_kind': 'user', 'display_name': username+'@%', 'display_path': [username], 'native': {'user': username, 'host': '%'}},
                        'draft': {'authentication_mode': 'RANDOM_PASSWORD', 'confirmation': username+'@%'}})
                    publish = PasswordResults.publish
                    def lost(self, reservation, factor, lease):
                        publish(self, reservation, factor, lease)
                        raise OSError('owned protected publication response lost')
                    with patch.object(PasswordResults, 'publish', lost):
                        failure = post.raw('visual_admin_apply', {'plan_id': alter['plan_id'], 'plan_digest': alter['plan_digest'], 'confirmed': True})
                    assert failure.status_code == 502 and failure.headers['Cache-Control'] == 'no-store'
                    restored = post('protected_password_result', {'operation': 'recover', 'plan_id': alter['plan_id']})
                    new_password = post('protected_password_result', {'operation': 'reveal', 'reference_id': restored['passwords'][0]['secret_reference_id'], 'confirmed': True})['password']
                    authenticated = mysql.connector.connect(host=route['host'], port=route['port'], user=username, password=new_password, use_pure=pure)
                    authenticated.close()
                    assert generated != new_password
                    # Retained-session IDs travel through the real authenticated API.
                    opened = post.body('open_session', language_profile='mysql-sql').get_json()['data']
                    session_id = opened['session_id']
                    try:
                        table = post('visual_admin_plan', {'resource_kind': 'table', 'operation_id': 'create', 'session_id': session_id,
                            'draft': {'name': 'api_temporary', 'parent': 'sr_osc', 'temporary': True, 'columns': [{'name': 'id', 'type': 'INT'}]}})
                        post('visual_admin_apply', {'plan_id': table['plan_id'], 'plan_digest': table['plan_digest'], 'confirmed': True, 'session_id': session_id})
                        target_resource = {'resource_kind': 'server', 'display_name': 'Owned server'}
                        refresh = post('visual_admin_plan', {'resource_kind': 'server', 'operation_id': 'refresh_session_metadata', 'session_id': session_id,
                            'target_resource': target_resource, 'draft': {'confirmation': 'Owned server', 'replace_diagnostics': True,
                                'temporary_tables': [{'database': 'sr_osc', 'name': 'api_temporary'}]}})
                        post('visual_admin_apply', {'plan_id': refresh['plan_id'], 'plan_digest': refresh['plan_digest'], 'confirmed': True, 'session_id': session_id})
                    finally:
                        response = post.body('close_session', session_id=session_id)
                        assert response.status_code == 200 and response.get_json()['success']
                    text = ''.join(path.read_text(errors='replace') for path in (output/'protected-results').rglob('*.json'))
                    text += (output/'app/application.log').read_text(errors='replace')
                    assert generated not in text and new_password not in text
                    q.execute('DROP USER %s@%s', (username, '%'))
                    proof['application'].append({'connector': 'pure' if pure else 'c', 'generated_password_authenticated': True,
                        'encrypted_recovery_after_ack_loss': True, 'invalid_draft_422_and_stale_plan_409': True,
                        'no_store': True, 'retained_temporary_and_refresh_roundtrip': True, 'passwords_absent_from_storage_and_logs': True})
            finally:
                q.close(); oracle.close()
    finally:
        proof['owned_servers_stopped'] = bool(owned) and all(value['owned_server_stopped'] for value in owned)


def qualify(output, application_only=False):
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Keep native evidence outside source')
    output.mkdir(parents=True, exist_ok=False)
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    app = setup_application(output)
    paths = ['web/pgadmin/cdeadmin/providers/mysql_family/'+name for name in
        ('administration.py', 'provider.py', 'mysql_tables.py', 'mysql_session_catalog.py', 'mysql_completion.py', 'mysql_connections.py', 'mysql_passwords.py', 'mysql_accounts.py', 'mysql_charsets.py')]
    paths += ['web/pgadmin/cdeadmin/security/generated_passwords.py', 'web/pgadmin/cdeadmin/visual_admin/provider.py',
              'web/pgadmin/cdeadmin/visual_admin/refusals.py', 'web/pgadmin/browser/server_groups/servers/__init__.py', str(Path(__file__).relative_to(ROOT))]
    proof = {'complete': False, 'interfaces': [], 'source_sha256': {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in paths}}
    try:
        if application_only:
            application(app, output, proof)
        else:
            native(output, proof)
        proof['complete'] = True
    finally:
        (output/'summary.json').write_text(json.dumps(proof, indent=2)+'\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--application-only', action='store_true')
    args = parser.parse_args()
    print(json.dumps({'complete': qualify(args.output, args.application_only)['complete']}))
