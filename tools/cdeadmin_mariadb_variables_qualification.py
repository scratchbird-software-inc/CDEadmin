"""Qualify MariaDB GLOBAL & original-session SET SESSION across 12.2.2 and 11.8 (native + HTTP)."""
import argparse
from contextlib import closing
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


def _qualify_native_image(image, scratch):
    import config  # noqa: F401
    import mariadb
    from tools.mariadb_qualification_support import server, _root_connection
    from tools.mysql_driver_gate_support import provider_access
    from pgadmin.cdeadmin.providers.mysql_family.provider import (
        _create_client,
        MARIADB_ADMINISTRATION,
        MARIADB_PROFILE,
        MariaDBPilotProvider,
    )
    from pgadmin.cdeadmin.sdk import RelationalClientError
    from ui_descriptor_roundtrip import engine_operations, operation_draft

    tag_slug = image.split(':', 1)[1].replace('.', '_')
    run_checks = []
    with server(scratch / f'mariadb-var-{tag_slug}', image=image) as (route, _name, fixture):
        native = _root_connection('mariadb', route['port'])
        native.autocommit = True
        native.cursor().execute('CREATE DATABASE owned_variables')
        native.cursor().execute(
            'CREATE TABLE owned_variables.pending_rows(id INT PRIMARY KEY) ENGINE=InnoDB'
        )
        restricted_pw = secrets.token_urlsafe(24)
        with native.cursor() as cur:
            cur.execute(
                "CREATE USER 'owned_var_restricted'@'%' IDENTIFIED BY ?",
                (restricted_pw,),
            )
            cur.execute(
                "GRANT SELECT, INSERT ON owned_variables.* TO 'owned_var_restricted'@'%'"
            )
        db_route = {**route, 'database': 'owned_variables'}
        admin_route, admin_perms = provider_access(db_route)
        rest_route, rest_perms = provider_access(
            {**db_route, 'user': 'owned_var_restricted'}, password=restricted_pw
        )
        client = _create_client(
            MARIADB_PROFILE,
            admin_perms,
            SimpleNamespace(pool_namespace=f'owned-var-admin-{tag_slug}'),
        )
        rest_client = _create_client(
            MARIADB_PROFILE,
            rest_perms,
            SimpleNamespace(pool_namespace=f'owned-var-rest-{tag_slug}'),
        )
        try:
            def meta_for(var_name):
                cur = native.cursor(dictionary=True)
                cur.execute(
                    'SELECT VARIABLE_NAME,VARIABLE_SCOPE,VARIABLE_TYPE,READ_ONLY,'
                    'NUMERIC_MIN_VALUE,NUMERIC_MAX_VALUE,ENUM_VALUE_LIST,GLOBAL_VALUE,'
                    'SESSION_VALUE,DEFAULT_VALUE '
                    'FROM information_schema.SYSTEM_VARIABLES WHERE VARIABLE_NAME=?',
                    (var_name,),
                )
                row = cur.fetchone()
                cur.close()
                return {k.lower(): v for k, v in row.items()} if row else {}

            # 1. set_global across SESSION (global+session) & GLOBAL variables
            for variable, requested in [
                ('SORT_BUFFER_SIZE', None),
                ('MAX_CONNECTIONS', None),
                ('OPTIMIZER_SWITCH', 'mrr=on'),
                ('OPTIMIZER_TRACE', 'enabled=on'),
            ]:
                metadata = meta_for(variable)
                if requested is None:
                    requested = str(int(metadata['global_value']) + (1024 if variable == 'SORT_BUFFER_SIZE' else 5))
                target = {
                    'resource_kind': 'system-variable',
                    'display_name': variable,
                    'display_path': ['Configuration', variable],
                    'native': metadata,
                }
                req = {
                    'resource_kind': 'system-variable',
                    'operation_id': 'set_global',
                    'draft': {'value_mode': 'VALUE', 'value': requested},
                    'target_resource': target,
                    '_provider_route': admin_route,
                }
                assert not client.validate_admin_operation(req)['errors']
                planned = client.plan_admin_operation(req)
                applied = client.apply_admin_operation(planned)
                assert applied['accepted']
                with native.cursor() as cur:
                    cur.execute('SELECT @@GLOBAL.' + variable)
                    observed = str(cur.fetchone()[0])
                assert requested in observed if '=' in requested else observed == requested
                run_checks.append({
                    'check': 'set_global_value',
                    'variable': variable,
                    'native_scope': metadata['variable_scope'],
                    'native_type': metadata['variable_type'],
                    'verified_global_readback': True,
                })

            # 2. FLAGSET BITMASK and FLAGS on set_global
            ot_meta = meta_for('OPTIMIZER_TRACE')
            for mask in ['0', '1', '2', '3']:
                req = {
                    'resource_kind': 'system-variable',
                    'operation_id': 'set_global',
                    'draft': {'value_mode': 'BITMASK', 'bitmask': mask},
                    'target_resource': {
                        'resource_kind': 'system-variable',
                        'display_name': 'OPTIMIZER_TRACE',
                        'display_path': ['Configuration', 'OPTIMIZER_TRACE'],
                        'native': ot_meta,
                    },
                    '_provider_route': admin_route,
                }
                assert not client.validate_admin_operation(req)['errors']
                assert client.apply_admin_operation(client.plan_admin_operation(req))['accepted']
            req['draft']['bitmask'] = '4'
            assert client.validate_admin_operation(req)['errors']

            global_desc = engine_operations('mariadb')['set_global@system-variable']
            os_meta = meta_for('OPTIMIZER_SWITCH')
            os_draft = operation_draft(
                global_desc,
                {'value_mode': 'FLAGS', 'flags': [{'flag': 'mrr', 'state': 'off'}], 'reset_defaults': False},
            )
            os_req = {
                'resource_kind': 'system-variable',
                'operation_id': 'set_global',
                'draft': os_draft,
                'target_resource': {
                    'resource_kind': 'system-variable',
                    'display_name': 'OPTIMIZER_SWITCH',
                    'display_path': ['Configuration', 'OPTIMIZER_SWITCH'],
                    'native': os_meta,
                },
                '_provider_route': admin_route,
            }
            assert client.apply_admin_operation(client.plan_admin_operation(os_req))['accepted']

            # 3. Refusal of SESSION ONLY, READ_ONLY='YES', and unknown variables on set_global
            so_meta = meta_for('PSEUDO_THREAD_ID')
            ro_meta = meta_for('VERSION')
            assert any(
                e['code'] == 'mariadb_system_variable_not_global'
                for e in MARIADB_ADMINISTRATION._validate_mariadb_system_variable(
                    {'value_mode': 'DEFAULT'}, {'display_name': 'PSEUDO_THREAD_ID', 'native': so_meta}
                )
            )
            assert any(
                e['code'] == 'mariadb_system_variable_read_only'
                for e in MARIADB_ADMINISTRATION._validate_mariadb_system_variable(
                    {'value_mode': 'DEFAULT'}, {'display_name': 'VERSION', 'native': ro_meta}
                )
            )
            assert any(
                e['code'] == 'unknown_mariadb_system_variable'
                for e in MARIADB_ADMINISTRATION._validate_mariadb_system_variable(
                    {'value_mode': 'DEFAULT'}, {'display_name': 'NONEXISTENT_OWNED', 'native': {}}
                )
            )
            # Forged metadata precheck before dispatch
            forged_plan = client.plan_admin_operation({
                'resource_kind': 'system-variable',
                'operation_id': 'set_global',
                'draft': {'value_mode': 'VALUE', 'value': '99'},
                'target_resource': {
                    'resource_kind': 'system-variable',
                    'display_name': 'PSEUDO_THREAD_ID',
                    'display_path': ['Configuration', 'PSEUDO_THREAD_ID'],
                    'native': {'read_only': 'NO', 'variable_scope': 'SESSION', 'variable_type': 'INT UNSIGNED'},
                },
                '_provider_route': admin_route,
            })
            try:
                client.apply_admin_operation(forged_plan)
            except RelationalClientError as err:
                assert err.native_dispatched is False
            else:
                raise AssertionError('Forged SESSION ONLY variable reached SET GLOBAL')
            run_checks.append({
                'check': 'set_global_refusals',
                'session_only_refused': True,
                'read_only_refused': True,
                'unknown_variable_refused': True,
                'forged_metadata_blocked_before_dispatch': True,
            })

            # 4. Original-session SET SESSION preserving transaction, savepoint, global & peer
            session_desc = engine_operations('mariadb')['set_session@system-variable']
            sess_handle = client.open_session({'route': admin_route})
            provider = SimpleNamespace(
                client=client, _require=lambda *_a: None, _editor_session=lambda _r: sess_handle
            )
            try:
                sess_handle.autocommit = False
                scur = sess_handle.cursor()
                scur.execute('INSERT INTO pending_rows VALUES (101)')
                scur.execute('SAVEPOINT sp_before_session_vars')
                scur.execute('INSERT INTO pending_rows VALUES (102)')
                with closing(mariadb.connect(user='root', host='127.0.0.1', port=route['port'], database='owned_variables')) as peer_conn:
                    pcur = peer_conn.cursor()
                    pcur.execute('SELECT @@GLOBAL.sort_buffer_size, @@SESSION.sort_buffer_size')
                    global_sbs, peer_sbs = [str(v) for v in pcur.fetchone()]

                    for var_name, mode_vals in [
                        ('sort_buffer_size', {'value_mode': 'VALUE', 'value': str(int(global_sbs) + 4096)}),
                        ('sql_mode', {'value_mode': 'VALUE', 'value': 'ANSI_QUOTES'}),
                        ('default_master_connection', {'value_mode': 'VALUE', 'value': 'sr_owned_chan'}),
                        ('pseudo_thread_id', {'value_mode': 'VALUE', 'value': '77777'}),
                    ]:
                        rev = MariaDBPilotProvider.native_session_variables_action(
                            provider,
                            {
                                'session_id': 'owned',
                                'language_profile': 'mariadb-sql',
                                'operation': 'review',
                                'variable': var_name,
                                'diagnostics_change_confirmed': True,
                                **mode_vals,
                            },
                        )
                        draft = operation_draft(
                            session_desc,
                            {
                                'variable': var_name,
                                **mode_vals,
                                'expected_value': rev['expected_value'],
                                'diagnostics_change_confirmed': True,
                                'confirmed': True,
                            },
                        )
                        applied_sess = MariaDBPilotProvider.native_session_variables_action(
                            provider,
                            {
                                'session_id': 'owned',
                                'language_profile': 'mariadb-sql',
                                'operation': 'set_session',
                                **draft,
                            },
                        )
                        assert applied_sess['outcome'] == 'native_acknowledged_with_readback'
                        assert not applied_sess['commit_requested'] and not applied_sess['rollback_requested']
                        run_checks.append({
                            'check': 'set_session_original_handle',
                            'variable': var_name,
                            'native_scope': applied_sess['native_scope'],
                            'effective_value': applied_sess['effective_value'],
                        })

                    # Verify global & peer untouched
                    pcur.execute('SELECT @@GLOBAL.sort_buffer_size, @@SESSION.sort_buffer_size, COUNT(*) FROM pending_rows')
                    after_global, after_peer, committed_rows = pcur.fetchone()
                    assert str(after_global) == global_sbs and str(after_peer) == peer_sbs
                    assert committed_rows == 0
                    pcur.close()

                # Verify savepoint & uncommitted rows intact on original session!
                scur.execute("SET SESSION sql_mode=''")
                scur.execute('ROLLBACK TO SAVEPOINT sp_before_session_vars')
                scur.execute('SELECT id FROM pending_rows ORDER BY id')
                assert scur.fetchall() == [(101,)]
                sess_handle.rollback()
                scur.close()
                run_checks.append({
                    'check': 'set_session_transaction_savepoint_and_peer_isolation',
                    'uncommitted_preserved': True,
                    'savepoint_preserved': True,
                    'global_and_peer_unchanged': True,
                })
            finally:
                client.close_session(sess_handle)

            # 5. Restricted non-admin user: 1227 denial on set_global, allowed on SESSION & SESSION ONLY
            sbs_meta = meta_for('SORT_BUFFER_SIZE')
            rest_global_plan = rest_client.plan_admin_operation({
                'resource_kind': 'system-variable',
                'operation_id': 'set_global',
                'draft': {'value_mode': 'VALUE', 'value': str(int(sbs_meta['global_value']) + 2048)},
                'target_resource': {
                    'resource_kind': 'system-variable',
                    'display_name': 'SORT_BUFFER_SIZE',
                    'display_path': ['Configuration', 'SORT_BUFFER_SIZE'],
                    'native': sbs_meta,
                },
                '_provider_route': rest_route,
            })
            try:
                rest_client.apply_admin_operation(rest_global_plan)
            except RelationalClientError as err:
                assert err.errno == 1227, err.errno
            else:
                raise AssertionError('Restricted user was allowed to SET GLOBAL')

            rest_sess = rest_client.open_session({'route': rest_route})
            rest_provider = SimpleNamespace(
                client=rest_client, _require=lambda *_a: None, _editor_session=lambda _r: rest_sess
            )
            try:
                for var_name, val in [
                    ('sort_buffer_size', '524288'),
                    ('default_master_connection', 'rest_chan'),
                ]:
                    insp = MariaDBPilotProvider.native_session_variables_action(
                        rest_provider,
                        {
                            'session_id': 'rest',
                            'language_profile': 'mariadb-sql',
                            'operation': 'inspect',
                            'variable': var_name,
                            'diagnostics_change_confirmed': True,
                        },
                    )
                    res = MariaDBPilotProvider.native_session_variables_action(
                        rest_provider,
                        {
                            'session_id': 'rest',
                            'language_profile': 'mariadb-sql',
                            'operation': 'set_session',
                            'variable': var_name,
                            'value_mode': 'VALUE',
                            'value': val,
                            'expected_value': insp['before_value'],
                            'diagnostics_change_confirmed': True,
                            'confirmed': True,
                        },
                    )
                    assert res['outcome'] == 'native_acknowledged_with_readback'
                    assert res['effective_value'] == val

                # Privileged SESSION ONLY variable (sql_log_bin) refused with 1227 without breaking session
                slb = MariaDBPilotProvider.native_session_variables_action(
                    rest_provider,
                    {
                        'session_id': 'rest',
                        'language_profile': 'mariadb-sql',
                        'operation': 'inspect',
                        'variable': 'sql_log_bin',
                        'diagnostics_change_confirmed': True,
                    },
                )
                try:
                    MariaDBPilotProvider.native_session_variables_action(
                        rest_provider,
                        {
                            'session_id': 'rest',
                            'language_profile': 'mariadb-sql',
                            'operation': 'set_session',
                            'variable': 'sql_log_bin',
                            'value_mode': 'VALUE',
                            'value': 'OFF',
                            'expected_value': slb['before_value'],
                            'diagnostics_change_confirmed': True,
                            'confirmed': True,
                        },
                    )
                except RelationalClientError as err:
                    assert err.errno == 1227
                else:
                    raise AssertionError('Restricted user was allowed to SET SESSION sql_log_bin')

                # Session remains usable after 1227 refusal!
                still_ok = MariaDBPilotProvider.native_session_variables_action(
                    rest_provider,
                    {
                        'session_id': 'rest',
                        'language_profile': 'mariadb-sql',
                        'operation': 'inspect',
                        'variable': 'sort_buffer_size',
                        'diagnostics_change_confirmed': True,
                    },
                )
                assert still_ok['effective_value'] == '524288'
                run_checks.append({
                    'check': 'restricted_user_scope_separation',
                    'set_global_denied_errno': 1227,
                    'set_session_allowed_for_session_and_session_only': True,
                    'set_session_sql_log_bin_denied_errno': 1227,
                    'session_usable_after_denial': True,
                })
            finally:
                rest_client.close_session(rest_sess)
        finally:
            rest_client.close()
            client.close()
            native.close()
    cleanup = json.loads((scratch / f'mariadb-var-{tag_slug}/fixture.json').read_text())
    assert cleanup['owned_server_stopped'] and cleanup['owned_fixture_volumes_removed']
    return {
        'image': image,
        'engine_version': fixture['engine_version'],
        'server_uid': fixture['server_uid'],
        'fixture_cleanup': cleanup,
        'checks': run_checks,
    }


def _qualify_http_all(app, scratch):
    from flask import url_for
    from tools.mariadb_qualification_support import server, _root_connection
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.model import db, EndpointDatabaseTarget, Server, ServerGroup, User

    http_runs = []
    for image in ['mariadb:12.2.2', 'mariadb:11.8']:
        tag_slug = image.split(':', 1)[1].replace('.', '_')
        with server(scratch / f'mariadb-var-http-{tag_slug}', image=image) as (route, _name, fixture):
            native = _root_connection('mariadb', route['port'])
            native.autocommit = True
            admin_pw = secrets.token_urlsafe(24)
            rest_pw = secrets.token_urlsafe(24)
            try:
                with native.cursor() as cur:
                    cur.execute('CREATE DATABASE owned_http_vars')
                    cur.execute(
                        'CREATE TABLE owned_http_vars.tx_guard(id INT PRIMARY KEY) ENGINE=InnoDB'
                    )
                    cur.execute("CREATE USER 'http_admin'@'%' IDENTIFIED BY ?", (admin_pw,))
                    cur.execute("GRANT ALL PRIVILEGES ON *.* TO 'http_admin'@'%' WITH GRANT OPTION")
                    cur.execute("CREATE USER 'http_rest'@'%' IDENTIFIED BY ?", (rest_pw,))
                    cur.execute("GRANT SELECT, INSERT ON owned_http_vars.* TO 'http_rest'@'%'")
                cur_dict = native.cursor(dictionary=True)
                cur_dict.execute(
                    "SELECT VARIABLE_NAME,VARIABLE_SCOPE,VARIABLE_TYPE,READ_ONLY,"
                    "NUMERIC_MIN_VALUE,NUMERIC_MAX_VALUE,ENUM_VALUE_LIST,GLOBAL_VALUE,"
                    "DEFAULT_VALUE FROM information_schema.SYSTEM_VARIABLES "
                    "WHERE VARIABLE_NAME='SORT_BUFFER_SIZE'"
                )
                sbs_meta = {k.lower(): v for k, v in cur_dict.fetchone().items()}
                cur_dict.close()
            finally:
                native.close()

            with app.test_request_context('/'):
                user = User.query.first()
                uid = user.id
                group = ServerGroup.query.filter_by(user_id=uid).first()
                app.blueprints['NODE-engine_type'].connector_visibility['mariadb'].set(True, user_id=uid)

                def register_srv(label, uname):
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
                        display_name='owned_http_vars', database='owned_http_vars',
                        configuration='{}', active=1,
                    ))
                    db.session.commit()
                    return (
                        url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=srv.id),
                        url_for('NODE-server.cde_workspace_id', gid=group.id, sid=srv.id),
                        tid,
                    )

                adm_verify, adm_url, adm_tid = register_srv(f'MariaDB Admin {image}', 'http_admin')
                rst_verify, rst_url, rst_tid = register_srv(f'MariaDB Restricted {image}', 'http_rest')

            client = app.test_client()
            with client.session_transaction() as sess:
                sess['_user_id'] = str(uid)
                sess['_fresh'] = True
            v_adm = client.post(adm_verify, json={'password': admin_pw}).get_json()
            assert v_adm['success'], v_adm
            v_rst = client.post(rst_verify, json={'password': rest_pw}).get_json()
            assert v_rst['success'], v_rst

            def call(url, payload, denied=False):
                resp = client.post(url, json=payload)
                assert resp.headers.get('Cache-Control') == 'no-store'
                body = resp.get_json()
                if denied:
                    assert resp.status_code != 200 or not body.get('success'), body
                    return body
                assert resp.status_code == 200 and body.get('success'), (payload, body)
                return body['data']

            # Admin HTTP set_global on SESSION variable SORT_BUFFER_SIZE
            new_global = str(int(sbs_meta['global_value']) + 8192)
            g_req = {
                'database_target_id': adm_tid,
                'resource_kind': 'system-variable',
                'operation_id': 'set_global',
                'target_resource': {
                    'resource_kind': 'system-variable',
                    'display_name': 'SORT_BUFFER_SIZE',
                    'display_path': ['Configuration', 'SORT_BUFFER_SIZE'],
                    'native': sbs_meta,
                },
                'draft': {'value_mode': 'VALUE', 'value': new_global},
            }
            assert call(adm_url, {'action': 'visual_admin_validate', 'request': g_req})['valid']
            g_plan = call(adm_url, {'action': 'visual_admin_plan', 'request': g_req})
            call(
                adm_url,
                {
                    'action': 'visual_admin_apply',
                    'request': {
                        'database_target_id': adm_tid,
                        'plan_id': g_plan['plan_id'],
                        'plan_digest': g_plan['plan_digest'],
                        'confirmed': True,
                    },
                },
            )

            # Restricted HTTP set_global denied (1227), while HTTP set_session allowed!
            r_req = {**g_req, 'database_target_id': rst_tid}
            r_plan = call(rst_url, {'action': 'visual_admin_plan', 'request': r_req})
            call(
                rst_url,
                {
                    'action': 'visual_admin_apply',
                    'request': {
                        'database_target_id': rst_tid,
                        'plan_id': r_plan['plan_id'],
                        'plan_digest': r_plan['plan_digest'],
                        'confirmed': True,
                    },
                },
                denied=True,
            )

            opened = call(
                rst_url,
                {
                    'action': 'open_session',
                    'language_profile': 'mariadb-sql',
                    'database_target_id': rst_tid,
                },
            )
            sid = opened['session_id']
            try:
                for var_name, val in [
                    ('sort_buffer_size', '655360'),
                    ('default_master_connection', 'http_rest_chan'),
                ]:
                    reviewed = call(
                        rst_url,
                        {
                            'action': 'mariadb_session_variables',
                            'session_id': sid,
                            'database_target_id': rst_tid,
                            'request': {
                                'operation': 'review',
                                'variable': var_name,
                                'value_mode': 'VALUE',
                                'value': val,
                                'diagnostics_change_confirmed': True,
                            },
                        },
                    )
                    applied = call(
                        rst_url,
                        {
                            'action': 'mariadb_session_variables',
                            'session_id': sid,
                            'database_target_id': rst_tid,
                            'request': {
                                'operation': 'set_session',
                                'variable': var_name,
                                'value_mode': 'VALUE',
                                'value': val,
                                'expected_value': reviewed['expected_value'],
                                'diagnostics_change_confirmed': True,
                                'confirmed': True,
                            },
                        },
                    )
                    assert applied['outcome'] == 'native_acknowledged_with_readback'
                    assert applied['effective_value'] == val
            finally:
                call(
                    rst_url,
                    {'action': 'close_session', 'session_id': sid, 'database_target_id': rst_tid},
                )

            check_conn = _root_connection('mariadb', route['port'])
            try:
                with check_conn.cursor() as cur:
                    cur.execute('SELECT @@GLOBAL.sort_buffer_size')
                    assert str(cur.fetchone()[0]) == new_global
            finally:
                check_conn.close()

            http_runs.append({
                'image': image,
                'engine_version': fixture['engine_version'],
                'http_admin_set_global_verified': True,
                'http_restricted_set_global_denied': True,
                'http_restricted_set_session_and_session_only_verified': True,
                'cache_control_no_store': True,
            })
    return http_runs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    W = args.output.resolve()
    W.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix='mariadb-vars-qual-', dir=str(W)))

    sources = [
        'web/pgadmin/cdeadmin/providers/relational_admin.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_variables.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_session_variables.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_administration.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/provider.py',
        'web/pgadmin/cdeadmin/data_studio/studio.py',
        'web/pgadmin/cdeadmin/workspace/service.py',
        'web/pgadmin/cdeadmin/ui_descriptors/mariadb/operations.json',
        'tools/cdeadmin_mariadb_variables_qualification.py',
    ]
    sha_map = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources}
    native_proof = {
        'complete': False,
        'history_testing': 'not run',
        'scope': (
            'Owned MariaDB 12.2.2 and 11.8 fixtures; native set_global and '
            'original-session set_session across SESSION, SESSION ONLY, GLOBAL, '
            'READ_ONLY, unknown variables, transaction/savepoint preservation '
            'and restricted non-admin user separation.'
        ),
        'runs': [],
        'source_sha256': sha_map,
    }
    http_proof = {
        'complete': False,
        'history_testing': 'not run',
        'scope': (
            'Authenticated HTTP MariaDB 12.2.2 and 11.8 registration/verify, '
            'visual_admin set_global and original-session mariadb_session_variables '
            'across admin and restricted users.'
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
            native_proof['runs'].append(_qualify_native_image(image, scratch))
        native_proof['complete'] = True

        http_proof['runs'] = _qualify_http_all(app, scratch)
        http_proof['complete'] = True
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        (W / 'mariadb-variable-native.json').write_text(
            json.dumps(native_proof, indent=2, default=str) + '\n'
        )
        (W / 'mariadb-variable-http.json').write_text(
            json.dumps(http_proof, indent=2, default=str) + '\n'
        )
    print(json.dumps({
        'complete': native_proof['complete'] and http_proof['complete'],
        'native_runs': len(native_proof['runs']),
        'http_runs': len(http_proof['runs']),
    }))


if __name__ == '__main__':
    main()
