"""Owned MariaDB installed-metadata, scalar+aggregate UDF, and explicit refresh_completion qualification (12.2.2 & 11.8, native + HTTP)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]

UDF_SOURCE = '''#include <mysql.h>
#include <stdlib.h>

my_bool sr_completion_udf_init(UDF_INIT *state, UDF_ARGS *args, char *message) {
  return args->arg_count != 0;
}
long long sr_completion_udf(UDF_INIT *state, UDF_ARGS *args, char *is_null, char *error) {
  return 42;
}

my_bool sr_agg_udf_init(UDF_INIT *state, UDF_ARGS *args, char *message) {
  if (args->arg_count != 1) return 1;
  args->arg_type[0] = INT_RESULT;
  long long *acc = (long long *)calloc(1, sizeof(long long));
  if (!acc) return 1;
  state->ptr = (char *)acc;
  return 0;
}
void sr_agg_udf_deinit(UDF_INIT *state) {
  if (state->ptr) free(state->ptr);
}
void sr_agg_udf_clear(UDF_INIT *state, char *is_null, char *error) {
  *((long long *)state->ptr) = 0;
  *is_null = 0;
}
void sr_agg_udf_add(UDF_INIT *state, UDF_ARGS *args, char *is_null, char *error) {
  if (args->args[0]) {
    *((long long *)state->ptr) += *((long long *)args->args[0]);
  }
}
long long sr_agg_udf(UDF_INIT *state, UDF_ARGS *args, char *is_null, char *error) {
  *is_null = 0;
  return *((long long *)state->ptr);
}
'''


def _compile_udf_library(scratch):
    code = scratch / 'sr_completion_udf.c'
    library = scratch / 'sr_completion_udf.so'
    code.write_text(UDF_SOURCE)
    subprocess.run(
        ['cc', '-shared', '-fPIC', '-I/usr/include/mariadb', str(code), '-o', str(library)],
        check=True,
        env={**os.environ, 'TMPDIR': str(scratch)},
    )
    return library, hashlib.sha256(library.read_bytes()).hexdigest()


def _qualify_native(image, library, scratch):
    import config  # noqa: F401
    from tools.mariadb_qualification_support import server, _root_connection
    from tools.mysql_driver_gate_support import provider_access
    from pgadmin.cdeadmin.providers import native_editor as ne_module
    from pgadmin.cdeadmin.providers.mysql_family.provider import (
        _create_client,
        MARIADB_PROFILE,
        MariaDBPilotProvider,
    )
    from pgadmin.cdeadmin.providers.native_editor import NativeEditorProvider

    tag_slug = image.split(':', 1)[1].replace('.', '_')
    checks = []
    with server(scratch / f'mariadb-inst-{tag_slug}', image=image) as (route, name, fixture):
        native = _root_connection('mariadb', route['port'])
        native.autocommit = True
        clients = []
        try:
            cursor = native.cursor()
            cursor.execute('CREATE DATABASE owned_installed')
            cursor.execute('CREATE DATABASE owned_installed_alt')
            cursor.execute('CREATE TABLE owned_installed.agg_inputs(val INT) ENGINE=InnoDB')
            cursor.execute('INSERT INTO owned_installed.agg_inputs VALUES (10), (20), (15)')
            cursor.execute('CREATE TABLE owned_installed_alt.tx_hold(id INT) ENGINE=InnoDB')
            cursor.execute("CREATE ROLE 'sr_inst_role'")
            cursor.execute("GRANT 'sr_inst_role' TO 'root'@'%'")
            cursor.execute('SELECT @@plugin_dir')
            plugin_dir = cursor.fetchone()[0]
            subprocess.run(
                ['docker', 'cp', str(library), f'{name}:{plugin_dir}/sr_completion_udf.so'],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )

            base_rt = {**route, 'database': 'owned_installed'}

            def connect(settings):
                settings = dict(settings)
                pw = settings.pop('password', None)
                settings, perms = provider_access(settings, password=pw)
                c = _create_client(
                    MARIADB_PROFILE, perms, SimpleNamespace(pool_namespace=f'owned-inst-{tag_slug}-{len(clients)}')
                )
                clients.append(c)
                src = c.open_session({'route': settings})
                prov = SimpleNamespace(
                    client=c, profile=MARIADB_PROFILE, _require=lambda *_a: None, _editor_session=lambda _r: src
                )
                return c, src, prov

            client, source, provider = connect(base_rt)

            def passive():
                return NativeEditorProvider.complete(provider, {})['editor_context']

            def explicit_refresh():
                return MariaDBPilotProvider.native_editor_context_action(
                    provider,
                    {
                        'session_id': 'owned',
                        'language_profile': 'mariadb-sql',
                        'operation': 'refresh_completion',
                        'diagnostics_change_confirmed': True,
                    },
                )

            def dynamic_vars(ctx):
                return {
                    r['display_name'].upper(): r for r in ctx['resources']
                    if r['resource_kind'] == 'system-variable'
                }

            # 1. Explicit refresh_completion vs passive completion + invalidation after source execution
            source.autocommit = False
            scur = source.cursor()
            scur.execute('USE owned_installed_alt')
            scur.execute('INSERT INTO tx_hold VALUES (1)')
            scur.execute('SAVEPOINT sp_inst')
            scur.execute("SET ROLE 'sr_inst_role'")
            scur.execute("SET SESSION sql_mode='ORACLE'")
            scur.close()

            pass_before = passive()
            assert pass_before['context']['original_session_context_observed'] is False
            assert 'sql_mode' not in pass_before['context']
            assert pass_before['context']['explicit_context_snapshot_valid'] is False
            assert pass_before['complete'] is False

            refreshed = explicit_refresh()['editor_context']
            assert refreshed['context']['original_session_context_observed'] is True
            assert refreshed['context']['active_role'] == 'sr_inst_role'
            assert 'ORACLE' in refreshed['context']['sql_mode'].split(',')
            assert refreshed['context']['default_schema'] == 'owned_installed_alt'
            assert refreshed['snapshot_invalidated_by_next_source_command'] is True
            assert refreshed['context']['explicit_context_snapshot_valid'] is True
            rev_at_refresh = refreshed['context']['source_work_revision']

            # Passive completion still keeps overlays unobserved, while reporting snapshot valid until next source command
            pass_mid = passive()
            assert pass_mid['context']['original_session_context_observed'] is False
            assert pass_mid['context']['explicit_context_snapshot_valid'] is True

            # Subsequent source execution invalidates snapshot!
            tok = client.execute(source, {'source': 'SELECT 1'})
            client.describe_result(tok)
            pass_after = passive()
            assert pass_after['context']['explicit_context_snapshot_valid'] is False
            assert pass_after['context']['source_work_revision'] > rev_at_refresh
            assert pass_after['complete'] is False

            # Peer interruption during refresh_completion does not disturb source transaction/savepoint!
            orig_meta = ne_module.metadata

            def kill_peer_meta(peer_h, eng, *a, **kw):
                with native.cursor() as kc:
                    kc.execute(f'KILL CONNECTION {int(peer_h.connection_id)}')
                return orig_meta(peer_h, eng, *a, **kw)

            ne_module.metadata = kill_peer_meta
            try:
                unavailable = explicit_refresh()
                assert unavailable['outcome'] == 'context_refresh_unavailable'
                assert unavailable['accepted'] is False
                assert unavailable['close_session_required'] is False
                assert unavailable['automatic_retry'] is False
            finally:
                ne_module.metadata = orig_meta

            scur = source.cursor()
            scur.execute("SET SESSION sql_mode=''")
            scur.execute('ROLLBACK TO SAVEPOINT sp_inst')
            scur.execute('SELECT id FROM tx_hold')
            assert scur.fetchall() == [(1,)]
            source.rollback()
            scur.execute('USE owned_installed')
            scur.close()
            checks.append({
                'check': 'explicit_refresh_overlay_invalidation_and_peer_kill',
                'observed_role': 'sr_inst_role',
                'observed_sql_mode_oracle': True,
                'observed_default_schema': 'owned_installed_alt',
                'invalidated_after_source_execute': True,
                'peer_kill_preserved_source_transaction_and_savepoint': True,
            })

            # 2. Invalid/missing .so failure lifecycle (INSTALL SONAME & CREATE FUNCTION)
            baseline = set(dynamic_vars(passive()))
            for bad_sql in [
                "INSTALL SONAME 'sr_nonexistent_plugin_so'",
                "CREATE FUNCTION sr_missing_udf RETURNS INTEGER SONAME 'sr_nonexistent_udf.so'",
            ]:
                try:
                    cursor.execute(bad_sql)
                except Exception as err:
                    assert getattr(err, 'errno', None) in {1126, 1127}, getattr(err, 'errno', None)
                else:
                    raise AssertionError(f'Missing shared library SQL unexpectedly succeeded: {bad_sql}')
            after_failed_install = passive()
            assert not any(r['display_name'] == 'sr_missing_udf' for r in after_failed_install['resources'])
            checks.append({'check': 'missing_so_failure_lifecycle_clean', 'verified': True})

            # 3. Dynamic plugin server_audit variable lifecycle + scalar UDF + AGGREGATE UDF + ACTIVE FUNCTION plugins
            cursor.execute("INSTALL SONAME 'server_audit'")
            installed = passive()
            added_vars = set(dynamic_vars(installed)) - baseline
            assert added_vars and all(v.startswith('SERVER_AUDIT_') for v in added_vars)

            cursor.execute("CREATE FUNCTION sr_completion_udf RETURNS INTEGER SONAME 'sr_completion_udf.so'")
            cursor.execute("CREATE AGGREGATE FUNCTION sr_agg_udf RETURNS INTEGER SONAME 'sr_completion_udf.so'")
            registered = passive()

            scalar_udf = next(r for r in registered['resources'] if r['display_name'] == 'sr_completion_udf')
            agg_udf = next(r for r in registered['resources'] if r['display_name'] == 'sr_agg_udf')
            assert scalar_udf['native_function']['origin'] == 'mysql.func'
            assert scalar_udf['native_function']['kind'] == 'function'
            assert scalar_udf['native_function']['return_type'] == 'INT_RESULT'
            assert scalar_udf['native_function']['invocation_verified'] is False

            assert agg_udf['native_function']['origin'] == 'mysql.func'
            assert agg_udf['native_function']['kind'] == 'aggregate'
            assert agg_udf['native_function']['return_type'] == 'INT_RESULT'
            assert agg_udf['native_function']['invocation_verified'] is False

            cursor.execute('SELECT sr_completion_udf()')
            assert cursor.fetchone() == (42,)
            cursor.execute('SELECT sr_agg_udf(val) FROM owned_installed.agg_inputs')
            assert cursor.fetchone() == (45,)

            active_fn_plugins = [
                r['display_name'] for r in registered['resources']
                if r.get('native_function', {}).get('origin') == 'information_schema.PLUGINS'
                and r['native_function']['plugin_status'] == 'ACTIVE'
            ]
            assert active_fn_plugins

            cursor.execute('DROP FUNCTION sr_completion_udf')
            cursor.execute('DROP FUNCTION sr_agg_udf')
            cursor.execute("UNINSTALL SONAME 'server_audit'")
            removed = passive()
            assert not (set(dynamic_vars(removed)) & added_vars)
            assert not any(
                r['display_name'] in {'sr_completion_udf', 'sr_agg_udf'}
                for r in removed['resources']
            )
            checks.append({
                'check': 'plugin_and_scalar_plus_aggregate_udf_lifecycle',
                'dynamic_plugin_variables_count': len(added_vars),
                'scalar_udf_result': 42,
                'aggregate_udf_kind': 'aggregate',
                'aggregate_udf_sum_result': 45,
                'active_function_plugins': sorted(active_fn_plugins),
                'dropped_and_uninstalled_absent': True,
            })
            cursor.execute("DROP ROLE 'sr_inst_role'")
            cursor.close()
        finally:
            for c in reversed(clients):
                c.close()
            native.close()
    cleanup = json.loads((scratch / f'mariadb-inst-{tag_slug}/fixture.json').read_text())
    assert cleanup['owned_server_stopped'] and cleanup['owned_fixture_volumes_removed']
    return {
        'image': image,
        'engine_version': fixture['engine_version'],
        'server_uid': fixture['server_uid'],
        'fixture_cleanup': cleanup,
        'checks': checks,
    }


def _qualify_http(app, library, scratch):
    from flask import url_for
    from tools.mariadb_qualification_support import server, _root_connection
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.model import db, EndpointDatabaseTarget, Server, ServerGroup, User

    runs = []
    for image in ['mariadb:12.2.2', 'mariadb:11.8']:
        tag_slug = image.split(':', 1)[1].replace('.', '_')
        with server(scratch / f'mariadb-inst-http-{tag_slug}', image=image) as (route, name, fixture):
            native = _root_connection('mariadb', route['port'])
            native.autocommit = True
            pw = secrets.token_urlsafe(24)
            try:
                with native.cursor() as cur:
                    cur.execute('CREATE DATABASE http_inst_db')
                    cur.execute('CREATE DATABASE http_inst_alt')
                    cur.execute('CREATE TABLE http_inst_db.agg_vals(v INT) ENGINE=InnoDB')
                    cur.execute('INSERT INTO http_inst_db.agg_vals VALUES (4), (6), (11)')
                    cur.execute("CREATE USER 'http_inst_adm'@'%' IDENTIFIED BY ?", (pw,))
                    cur.execute("GRANT ALL PRIVILEGES ON *.* TO 'http_inst_adm'@'%' WITH GRANT OPTION")
                    cur.execute("CREATE ROLE 'http_inst_role'")
                    cur.execute("GRANT 'http_inst_role' TO 'http_inst_adm'@'%'")
                    cur.execute('SELECT @@plugin_dir')
                    plugin_dir = cur.fetchone()[0]
                subprocess.run(
                    ['docker', 'cp', str(library), f'{name}:{plugin_dir}/sr_completion_udf.so'],
                    check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                )

                with app.test_request_context('/'):
                    user = User.query.first()
                    uid = user.id
                    group = ServerGroup.query.filter_by(user_id=uid).first()
                    app.blueprints['NODE-engine_type'].connector_visibility['mariadb'].set(True, user_id=uid)
                    srv = Server(
                        user_id=uid, servergroup_id=group.id, name=f'Inst HTTP {image}',
                        host=route['host'], port=route['port'], username='http_inst_adm',
                        maintenance_db=None, save_password=0,
                    )
                    srv._cde_endpoint_registration = registration_profile('mariadb-native')
                    srv._cde_endpoint_route_configuration = {
                        'host': route['host'], 'port': route['port'], 'user': 'http_inst_adm',
                        'ssl': False, 'ssl_verify_cert': False,
                        'credential_kinds': ['database_password'],
                    }
                    db.session.add(srv)
                    db.session.commit()
                    tid = str(uuid.uuid4())
                    db.session.add(EndpointDatabaseTarget(
                        id=tid, endpoint_id=srv.endpoint_profile.id,
                        display_name='http_inst_db', database='http_inst_db',
                        configuration='{}', active=1,
                    ))
                    db.session.commit()
                    v_url = url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=srv.id)
                    w_url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=srv.id)

                client = app.test_client()
                with client.session_transaction() as sess:
                    sess['_user_id'] = str(uid)
                    sess['_fresh'] = True
                assert client.post(v_url, json={'password': pw}).get_json()['success']

                def call(payload):
                    resp = client.post(w_url, json=payload)
                    assert resp.headers.get('Cache-Control') == 'no-store'
                    body = resp.get_json()
                    assert resp.status_code == 200 and body.get('success'), (payload, body)
                    return body['data']

                def exec_sql(sid, sql):
                    occ = call({
                        'action': 'execute', 'session_id': sid,
                        'database_target_id': tid, 'source': sql,
                    })
                    oid = occ['occurrence_id']
                    polled = call({'action': 'poll', 'occurrence_id': oid, 'database_target_id': tid})
                    while polled['occurrence']['lifecycle_state'] == 'provider_active':
                        polled = call({'action': 'poll', 'occurrence_id': oid, 'database_target_id': tid})
                    assert polled['occurrence']['lifecycle_state'] == 'provider_terminal', polled
                    return polled['occurrence']['result']['extensions']['mariadb']['payload']

                opened = call({
                    'action': 'open_session',
                    'language_profile': 'mariadb-sql',
                    'database_target_id': tid,
                })
                sid = opened['session_id']
                try:
                    exec_sql(sid, 'USE http_inst_alt')
                    exec_sql(sid, "SET ROLE 'http_inst_role'")
                    exec_sql(sid, "SET SESSION sql_mode='ORACLE'")

                    p1 = call({
                        'action': 'source_complete', 'session_id': sid, 'database_target_id': tid,
                        'source': 'SELECT ', 'source_before_cursor': 'SELECT ',
                    })['editor_context']
                    assert p1['context']['original_session_context_observed'] is False
                    assert p1['complete'] is False

                    ref = call({
                        'action': 'mariadb_editor_context',
                        'session_id': sid,
                        'database_target_id': tid,
                        'request': {
                            'operation': 'refresh_completion',
                            'diagnostics_change_confirmed': True,
                        },
                    })['editor_context']
                    assert ref['context']['original_session_context_observed'] is True
                    assert ref['context']['active_role'] == 'http_inst_role'
                    assert ref['context']['default_schema'] == 'http_inst_alt'
                    assert 'ORACLE' in ref['context']['sql_mode'].split(',')
                    assert ref['context']['explicit_context_snapshot_valid'] is True

                    # Execute invalidates explicit snapshot
                    exec_sql(sid, "SET SESSION sql_mode=''")
                    p2 = call({
                        'action': 'source_complete', 'session_id': sid, 'database_target_id': tid,
                        'source': 'SELECT ', 'source_before_cursor': 'SELECT ',
                    })['editor_context']
                    assert p2['context']['explicit_context_snapshot_valid'] is False

                    # Scalar + aggregate UDF + server_audit observed over HTTP source_complete
                    with native.cursor() as cur:
                        cur.execute("INSTALL SONAME 'server_audit'")
                        cur.execute("CREATE FUNCTION sr_completion_udf RETURNS INTEGER SONAME 'sr_completion_udf.so'")
                        cur.execute("CREATE AGGREGATE FUNCTION sr_agg_udf RETURNS INTEGER SONAME 'sr_completion_udf.so'")
                    p_udf = call({
                        'action': 'source_complete', 'session_id': sid, 'database_target_id': tid,
                        'source': 'SELECT sr_', 'source_before_cursor': 'SELECT sr_',
                    })['editor_context']
                    agg = next(r for r in p_udf['resources'] if r['display_name'] == 'sr_agg_udf')
                    assert agg['native_function']['kind'] == 'aggregate' and not agg['native_function']['invocation_verified']
                    assert any(
                        r['resource_kind'] == 'system-variable' and r['display_name'].upper().startswith('SERVER_AUDIT_')
                        for r in p_udf['resources']
                    )
                    sum_payload = exec_sql(sid, 'SELECT sr_agg_udf(v) FROM http_inst_db.agg_vals')
                    cell = sum_payload['rows'][0][0]
                    val = int(cell['data']) if isinstance(cell, dict) else int(cell)
                    assert val == 21
                    with native.cursor() as cur:
                        cur.execute('DROP FUNCTION sr_completion_udf')
                        cur.execute('DROP FUNCTION sr_agg_udf')
                        cur.execute("UNINSTALL SONAME 'server_audit'")
                finally:
                    call({'action': 'close_session', 'session_id': sid, 'database_target_id': tid})
            finally:
                native.close()
        runs.append({
            'image': image,
            'engine_version': fixture['engine_version'],
            'http_refresh_completion_and_invalidation_verified': True,
            'http_scalar_and_aggregate_udf_and_plugin_verified': True,
        })
    return runs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    work = args.output.resolve()
    work.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix='mariadb-inst-qual-', dir=str(work)))

    paths = [
        'tools/cdeadmin_mariadb_installed_completion_qualification.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_installed.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_editor_context.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_completion.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/provider.py',
        'web/pgadmin/cdeadmin/providers/native_editor.py',
    ]
    sha_map = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}
    native_proof = {'complete': False, 'history_testing': 'not run', 'runs': [], 'source_sha256': sha_map}
    http_proof = {'complete': False, 'history_testing': 'not run', 'runs': [], 'source_sha256': sha_map}
    try:
        from tools.cdeadmin_mysql_dump_verification_qualification import setup_application
        http_app_dir = scratch / 'http-app'
        http_app_dir.mkdir(parents=True, exist_ok=True)
        app = setup_application(http_app_dir)

        library, lib_sha = _compile_udf_library(scratch)
        native_proof['owned_udf_library_sha256'] = lib_sha
        http_proof['owned_udf_library_sha256'] = lib_sha
        for image in ['mariadb:12.2.2', 'mariadb:11.8']:
            native_proof['runs'].append(_qualify_native(image, library, scratch))
        native_proof['complete'] = True

        http_proof['runs'] = _qualify_http(app, library, scratch)
        http_proof['complete'] = True
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        (work / 'mariadb-installed-native.json').write_text(
            json.dumps(native_proof, indent=2, default=str) + '\n'
        )
        (work / 'mariadb-installed-http.json').write_text(
            json.dumps(http_proof, indent=2, default=str) + '\n'
        )
    print(json.dumps({
        'complete': native_proof['complete'] and http_proof['complete'],
        'native_runs': len(native_proof['runs']),
        'http_runs': len(http_proof['runs']),
    }))


if __name__ == '__main__':
    main()
