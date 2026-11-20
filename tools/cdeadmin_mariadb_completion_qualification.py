"""Qualify nonintrusive MariaDB completion natively & over HTTP across 12.2.2 and 11.8."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import sys
import tempfile
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def _qualify_native(image, scratch):
    import config  # noqa: F401
    from tools.mariadb_qualification_support import server, _root_connection
    from tools.mysql_driver_gate_support import provider_access
    from pgadmin.cdeadmin.providers import native_editor as ne_module
    from pgadmin.cdeadmin.providers.mysql_family.provider import _create_client, MARIADB_PROFILE
    from pgadmin.cdeadmin.providers.native_editor import NativeEditorProvider
    from pgadmin.cdeadmin.sdk import RelationalClientError

    tag_slug = image.split(':', 1)[1].replace('.', '_')
    checks = []
    with server(scratch / f'mariadb-comp-{tag_slug}', image=image) as (route, _name, fixture):
        observer = _root_connection('mariadb', route['port'])
        observer.autocommit = True
        rest_pw = secrets.token_urlsafe(24)
        client = rest_client = None
        try:
            with observer.cursor() as cur:
                cur.execute('CREATE DATABASE owned_completion')
                cur.execute('CREATE DATABASE owned_secret_db')
                cur.execute('CREATE TABLE owned_completion.pending_work(id INT) ENGINE=InnoDB')
                cur.execute('CREATE TABLE owned_secret_db.hidden_tbl(id INT) ENGINE=InnoDB')
                cur.execute("CREATE USER 'comp_restricted'@'%' IDENTIFIED BY ?", (rest_pw,))
                cur.execute("GRANT SELECT ON owned_completion.* TO 'comp_restricted'@'%'")

            db_route, perms = provider_access({**route, 'database': 'owned_completion'})
            client = _create_client(
                MARIADB_PROFILE, perms, SimpleNamespace(pool_namespace=f'owned-comp-{tag_slug}')
            )
            source = client.open_session({'route': db_route})
            orig_cid = source.connection_id
            source.autocommit = False
            cursor = source.cursor()
            cursor.execute('INSERT INTO pending_work VALUES (1)')
            cursor.execute('SAVEPOINT owned_before_completion')
            provider = SimpleNamespace(
                client=client, profile=MARIADB_PROFILE, _editor_session=lambda _req: source
            )

            # 1. Warning 1365, error 1054, uncommitted write & savepoint preserved
            for kind in ['warning', 'error', 'warning-again']:
                if kind == 'error':
                    try:
                        cursor.execute('SELECT absent_owned_column FROM pending_work')
                    except Exception as error:
                        assert getattr(error, 'errno', None) == 1054
                    else:
                        raise AssertionError('Native column error was not raised')
                else:
                    cursor.execute('SELECT 1/0')
                    assert cursor.fetchone() == (None,)
                cursor.execute('SHOW WARNINGS')
                before = cursor.fetchall()
                assert before and before[0][1] == (1054 if kind == 'error' else 1365)
                result = NativeEditorProvider.complete(provider, {})['editor_context']
                cursor.execute('SHOW WARNINGS')
                assert cursor.fetchall() == before
                assert result['original_session_commands_sent'] == 0
                assert result['original_diagnostics_preserved'] and not result['complete']
                assert 'sql_mode' not in result['context']
                assert any(row['display_name'] == 'pending_work' for row in result['resources'])
                with observer.cursor() as check:
                    check.execute('SELECT COUNT(*) FROM owned_completion.pending_work')
                    assert check.fetchone() == (0,)
                cursor.execute('ROLLBACK TO SAVEPOINT owned_before_completion')
                cursor.execute('SELECT COUNT(*) FROM pending_work')
                assert cursor.fetchone() == (1,)
                checks.append({
                    'check': 'diagnostics_and_savepoint_preserved',
                    'diagnostic_kind': kind,
                    'native_diagnostic_code': before[0][1],
                    'diagnostics_unchanged': True,
                    'savepoint_preserved': True,
                    'pending_work_uncommitted_and_preserved': True,
                })

            # 2. Peer connection interruption / KILL CONNECTION during metadata read!
            cursor.execute('SELECT 1/0')
            cursor.fetchone()
            cursor.execute('SHOW WARNINGS')
            warn_before_kill = cursor.fetchall()
            assert warn_before_kill and warn_before_kill[0][1] == 1365

            orig_metadata = ne_module.metadata

            def killed_metadata(peer_handle, engine_name, *a, **kw):
                peer_cid = peer_handle.connection_id
                assert peer_cid != orig_cid
                with observer.cursor() as kc:
                    kc.execute(f'KILL CONNECTION {int(peer_cid)}')
                return orig_metadata(peer_handle, engine_name, *a, **kw)

            ne_module.metadata = killed_metadata
            try:
                try:
                    NativeEditorProvider.complete(provider, {})
                except RelationalClientError as kill_err:
                    assert kill_err.original_session_commands_sent == 0
                    assert kill_err.original_diagnostics_preserved is True
                else:
                    raise AssertionError('Killed peer metadata read succeeded unexpectedly')
            finally:
                ne_module.metadata = orig_metadata

            # Verify source handle, warning 1365, uncommitted row and SAVEPOINT 100% untouched!
            assert source.connection_id == orig_cid
            cursor.execute('SHOW WARNINGS')
            assert cursor.fetchall() == warn_before_kill
            cursor.execute('ROLLBACK TO SAVEPOINT owned_before_completion')
            cursor.execute('SELECT COUNT(*) FROM pending_work')
            assert cursor.fetchone() == (1,)
            checks.append({
                'check': 'peer_kill_connection_during_metadata',
                'source_connection_id_unchanged': True,
                'source_warning_1365_untouched': True,
                'source_uncommitted_row_and_savepoint_untouched': True,
                'fallback_on_source_session': False,
            })
            cursor.close()
            client.close_session(source)

            # 3. Restricted-account peer metadata reader (partial visibility + 1142 on mysql.func)
            rest_rt, rest_perms = provider_access(
                {**route, 'database': 'owned_completion', 'user': 'comp_restricted'},
                password=rest_pw,
            )
            rest_client = _create_client(
                MARIADB_PROFILE, rest_perms, SimpleNamespace(pool_namespace=f'owned-comp-rest-{tag_slug}')
            )
            rest_src = rest_client.open_session({'route': rest_rt})
            rest_cur = rest_src.cursor()
            rest_cur.execute('SELECT 1/0')
            rest_cur.fetchone()
            rest_cur.execute('SHOW WARNINGS')
            rest_warn = rest_cur.fetchall()
            rest_prov = SimpleNamespace(
                client=rest_client, profile=MARIADB_PROFILE, _editor_session=lambda _req: rest_src
            )
            rest_ctx = NativeEditorProvider.complete(rest_prov, {})['editor_context']
            rest_cur.execute('SHOW WARNINGS')
            assert rest_cur.fetchall() == rest_warn
            rest_cur.close()
            rest_client.close_session(rest_src)

            schemas = {
                r['display_name'] for r in rest_ctx['resources'] if r['resource_kind'] == 'schema'
            }
            assert 'owned_completion' in schemas and 'owned_secret_db' not in schemas
            func_obs = next(
                r for r in rest_ctx['observations'] if r['section'] == 'native-loadable-functions'
            )
            assert not func_obs['available'] and func_obs['error_code'] == 1142
            assert rest_ctx['complete'] is False
            checks.append({
                'check': 'restricted_peer_metadata_reader',
                'visible_db_present': True,
                'hidden_db_omitted': True,
                'mysql_func_errno': 1142,
                'complete_reported_false': True,
                'source_warning_preserved': True,
            })
        finally:
            if rest_client is not None:
                rest_client.close()
            if client is not None:
                client.close()
            observer.close()
    cleanup = json.loads((scratch / f'mariadb-comp-{tag_slug}/fixture.json').read_text())
    assert cleanup['owned_server_stopped'] and cleanup['owned_fixture_volumes_removed']
    return {
        'image': image,
        'engine_version': fixture['engine_version'],
        'server_uid': fixture['server_uid'],
        'fixture_cleanup': cleanup,
        'checks': checks,
    }


def _qualify_http(app, scratch):
    from flask import url_for
    from tools.mariadb_qualification_support import server, _root_connection
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.cdeadmin.providers import native_editor as ne_module
    from pgadmin.model import db, EndpointDatabaseTarget, Server, ServerGroup, User

    runs = []
    for image in ['mariadb:12.2.2', 'mariadb:11.8']:
        tag_slug = image.split(':', 1)[1].replace('.', '_')
        with server(scratch / f'mariadb-comp-http-{tag_slug}', image=image) as (route, _name, fixture):
            observer = _root_connection('mariadb', route['port'])
            observer.autocommit = True
            admin_pw = secrets.token_urlsafe(24)
            rest_pw = secrets.token_urlsafe(24)
            try:
                with observer.cursor() as cur:
                    cur.execute('CREATE DATABASE http_comp_db')
                    cur.execute('CREATE DATABASE http_secret_db')
                    cur.execute('CREATE TABLE http_comp_db.tx_items(id INT) ENGINE=InnoDB')
                    cur.execute("CREATE USER 'http_comp_adm'@'%' IDENTIFIED BY ?", (admin_pw,))
                    cur.execute("GRANT ALL PRIVILEGES ON *.* TO 'http_comp_adm'@'%'")
                    cur.execute("CREATE USER 'http_comp_rst'@'%' IDENTIFIED BY ?", (rest_pw,))
                    cur.execute("GRANT SELECT, INSERT ON http_comp_db.* TO 'http_comp_rst'@'%'")

                with app.test_request_context('/'):
                    user = User.query.first()
                    uid = user.id
                    group = ServerGroup.query.filter_by(user_id=uid).first()
                    app.blueprints['NODE-engine_type'].connector_visibility['mariadb'].set(True, user_id=uid)

                    def reg(label, uname):
                        srv = Server(
                            user_id=uid, servergroup_id=group.id, name=label,
                            host=route['host'], port=route['port'], username=uname,
                            maintenance_db=None, save_password=0,
                        )
                        srv._cde_endpoint_registration = registration_profile('mariadb-native')
                        srv._cde_endpoint_route_configuration = {
                            'host': route['host'], 'port': route['port'], 'user': uname,
                            'ssl': False, 'ssl_verify_cert': False,
                            'credential_kinds': ['database_password'],
                        }
                        db.session.add(srv)
                        db.session.commit()
                        tid = str(uuid.uuid4())
                        db.session.add(EndpointDatabaseTarget(
                            id=tid, endpoint_id=srv.endpoint_profile.id,
                            display_name='http_comp_db', database='http_comp_db',
                            configuration='{}', active=1,
                        ))
                        db.session.commit()
                        return (
                            url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=srv.id),
                            url_for('NODE-server.cde_workspace_id', gid=group.id, sid=srv.id),
                            tid,
                        )

                    adm_v, adm_url, adm_tid = reg(f'Comp Admin {image}', 'http_comp_adm')
                    rst_v, rst_url, rst_tid = reg(f'Comp Rest {image}', 'http_comp_rst')

                client = app.test_client()
                with client.session_transaction() as sess:
                    sess['_user_id'] = str(uid)
                    sess['_fresh'] = True
                assert client.post(adm_v, json={'password': admin_pw}).get_json()['success']
                assert client.post(rst_v, json={'password': rest_pw}).get_json()['success']

                def call(url, payload, denied=False):
                    resp = client.post(url, json=payload)
                    assert resp.headers.get('Cache-Control') == 'no-store'
                    body = resp.get_json()
                    if denied:
                        assert resp.status_code != 200 or not body.get('success'), body
                        return body
                    assert resp.status_code == 200 and body.get('success'), (payload, body)
                    return body['data']

                def exec_sql(url, tid, sid, sql, expect_err=False):
                    occ = call(
                        url,
                        {
                            'action': 'execute',
                            'session_id': sid,
                            'database_target_id': tid,
                            'source': sql,
                        },
                    )
                    oid = occ['occurrence_id']
                    polled = call(
                        url,
                        {'action': 'poll', 'occurrence_id': oid, 'database_target_id': tid},
                    )
                    while polled['occurrence']['lifecycle_state'] == 'provider_active':
                        polled = call(
                            url,
                            {'action': 'poll', 'occurrence_id': oid, 'database_target_id': tid},
                        )
                    if not expect_err:
                        assert polled['occurrence']['lifecycle_state'] == 'provider_terminal', polled
                    return polled['occurrence']['result']['extensions']['mariadb']['payload']

                opened = call(
                    adm_url,
                    {'action': 'open_session', 'language_profile': 'mariadb-sql', 'database_target_id': adm_tid},
                )
                sid = opened['session_id']
                try:
                    call(
                        adm_url,
                        {
                            'action': 'transaction_action',
                            'session_id': sid,
                            'transaction_action': 'autocommit_off',
                            'database_target_id': adm_tid,
                        },
                    )
                    exec_sql(adm_url, adm_tid, sid, 'INSERT INTO tx_items VALUES (77)')
                    exec_sql(adm_url, adm_tid, sid, 'SAVEPOINT sp_http_comp')
                    exec_sql(adm_url, adm_tid, sid, 'SELECT 1/0')

                    comp = call(
                        adm_url,
                        {
                            'action': 'source_complete',
                            'session_id': sid,
                            'database_target_id': adm_tid,
                            'source': 'SELECT * FROM tx_',
                            'source_before_cursor': 'SELECT * FROM tx_',
                        },
                    )
                    ectx = comp['editor_context']
                    assert ectx['original_session_commands_sent'] == 0
                    assert ectx['original_diagnostics_preserved'] is True
                    assert ectx['complete'] is False

                    def _cell_int(v):
                        return int(v['data']) if isinstance(v, dict) else int(v)

                    # Verify warning 1365 & savepoint still intact on HTTP session!
                    warn_payload = exec_sql(adm_url, adm_tid, sid, 'SHOW WARNINGS')
                    assert _cell_int(warn_payload['rows'][0][1]) == 1365

                    # Peer kill over HTTP source_complete
                    exec_sql(adm_url, adm_tid, sid, 'SELECT 1/0')
                    orig_meta = ne_module.metadata

                    def http_kill_meta(peer_h, eng, *a, **kw):
                        with observer.cursor() as kc:
                            kc.execute(f'KILL CONNECTION {int(peer_h.connection_id)}')
                        return orig_meta(peer_h, eng, *a, **kw)

                    ne_module.metadata = http_kill_meta
                    try:
                        call(
                            adm_url,
                            {
                                'action': 'source_complete',
                                'session_id': sid,
                                'database_target_id': adm_tid,
                                'source': 'SELECT ',
                                'source_before_cursor': 'SELECT ',
                            },
                            denied=True,
                        )
                    finally:
                        ne_module.metadata = orig_meta

                    warn_after_kill = exec_sql(adm_url, adm_tid, sid, 'SHOW WARNINGS')
                    assert _cell_int(warn_after_kill['rows'][0][1]) == 1365
                    exec_sql(adm_url, adm_tid, sid, 'ROLLBACK TO SAVEPOINT sp_http_comp')
                    cnt = exec_sql(adm_url, adm_tid, sid, 'SELECT COUNT(*) FROM tx_items')
                    assert _cell_int(cnt['rows'][0][0]) == 1
                    call(
                        adm_url,
                        {
                            'action': 'transaction_action',
                            'session_id': sid,
                            'transaction_action': 'rollback',
                            'database_target_id': adm_tid,
                        },
                    )
                finally:
                    call(adm_url, {'action': 'close_session', 'session_id': sid, 'database_target_id': adm_tid})

                # Restricted HTTP source_complete
                r_opened = call(
                    rst_url,
                    {'action': 'open_session', 'language_profile': 'mariadb-sql', 'database_target_id': rst_tid},
                )
                r_sid = r_opened['session_id']
                try:
                    r_comp = call(
                        rst_url,
                        {
                            'action': 'source_complete',
                            'session_id': r_sid,
                            'database_target_id': rst_tid,
                            'source': 'SELECT ',
                            'source_before_cursor': 'SELECT ',
                        },
                    )['editor_context']
                    assert r_comp['complete'] is False
                    r_schemas = {
                        r['display_name'] for r in r_comp['resources'] if r['resource_kind'] == 'schema'
                    }
                    assert 'http_comp_db' in r_schemas and 'http_secret_db' not in r_schemas
                finally:
                    call(rst_url, {'action': 'close_session', 'session_id': r_sid, 'database_target_id': rst_tid})
            finally:
                observer.close()
        runs.append({
            'image': image,
            'engine_version': fixture['engine_version'],
            'http_warning_1365_savepoint_and_uncommitted_preserved': True,
            'http_peer_kill_preserved_source_session': True,
            'http_restricted_peer_incomplete_honest': True,
        })
    return runs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    work = args.output.resolve()
    work.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix='mariadb-comp-qual-', dir=str(work)))

    paths = [
        'tools/cdeadmin_mariadb_completion_qualification.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_completion.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/provider.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_installed.py',
        'web/pgadmin/cdeadmin/providers/native_editor.py',
    ]
    sha_map = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}
    native_proof = {
        'complete': False,
        'history_testing': 'not run',
        'scope': (
            'Owned MariaDB 12.2.2 and 11.8 native completion: warning 1365, error 1054, '
            'uncommitted writes, savepoints, restricted peer metadata and peer KILL CONNECTION.'
        ),
        'runs': [],
        'source_sha256': sha_map,
    }
    http_proof = {
        'complete': False,
        'history_testing': 'not run',
        'scope': (
            'Authenticated HTTP open_session -> source_complete across MariaDB 12.2.2 and 11.8 '
            'including peer KILL CONNECTION and restricted reader.'
        ),
        'runs': [],
        'source_sha256': sha_map,
    }
    try:
        from tools.cdeadmin_mysql_dump_verification_qualification import setup_application
        http_app_dir = scratch / 'http-app'
        http_app_dir.mkdir(parents=True, exist_ok=True)
        app = setup_application(http_app_dir)

        for image in ['mariadb:12.2.2', 'mariadb:11.8']:
            native_proof['runs'].append(_qualify_native(image, scratch))
        native_proof['complete'] = True

        http_proof['runs'] = _qualify_http(app, scratch)
        http_proof['complete'] = True
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        (work / 'mariadb-completion-native.json').write_text(json.dumps(native_proof, indent=2) + '\n')
        (work / 'mariadb-completion-http.json').write_text(json.dumps(http_proof, indent=2) + '\n')
    print(json.dumps({
        'complete': native_proof['complete'] and http_proof['complete'],
        'native_runs': len(native_proof['runs']),
        'http_runs': len(http_proof['runs']),
    }))


if __name__ == '__main__':
    main()
