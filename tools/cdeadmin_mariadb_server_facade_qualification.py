"""Qualify authenticated HTTP MariaDB server-DDN facade end-to-end on MariaDB 12.2.2."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    work = args.output.resolve()
    work.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix='mariadb-server-facade-', dir=str(work)))

    paths = [
        'web/pgadmin/cdeadmin/workspace/service.py',
        'web/pgadmin/cdeadmin/workspace/mariadb_server_plan.py',
        'web/pgadmin/cdeadmin/workspace/mariadb_server_apply.py',
        'web/pgadmin/cdeadmin/providers/mariadb_server_application.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_server_catalog.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/provider.py',
        'web/pgadmin/browser/server_groups/servers/__init__.py',
        'tools/cdeadmin_mariadb_server_facade_qualification.py',
    ]
    proof = {
        'complete': False,
        'history_testing': 'not run',
        'scope': (
            'Authenticated HTTP MariaDB 12.2.2 server-DDN end-to-end: exact '
            'mariadb-native registration, wrong-engine refusal on mysql-native, '
            'mariadb_server_catalog -> edit -> mariadb_server_plan -> stale digest '
            'and live drift conflicts -> mariadb_server_review -> mariadb_server_apply '
            '-> mariadb_server_receipt & mariadb_server_receipts -> independent native SQL read-back.'
        ),
        'checks': [],
        'source_sha256': {
            p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths
        },
    }
    try:
        from tools.cdeadmin_mysql_dump_verification_qualification import setup_application
        http_app_dir = scratch / 'http-app'
        http_app_dir.mkdir(parents=True, exist_ok=True)
        app = setup_application(http_app_dir)

        from flask import url_for
        from tools.mariadb_qualification_support import server as mariadb_server, _root_connection as maria_root
        from tools.mysql_qualification_support import server as mysql_server, _root_connection as mysql_root
        from pgadmin.cdeadmin.endpoints.profiles import registration_profile
        from pgadmin.model import db, Server, ServerGroup, User
        with mariadb_server(scratch / 'mariadb-fixture', image='mariadb:12.2.2') as (m_route, _m_name, m_fix), \
                mysql_server(scratch / 'mysql-fixture', image='mysql:9.7.0') as (my_route, _my_name, _my_fix):
            m_pw = secrets.token_urlsafe(24)
            my_pw = secrets.token_urlsafe(24)
            m_conn = maria_root('mariadb', m_route['port'])
            m_conn.autocommit = True
            my_conn = mysql_root('mysql', my_route['port'])
            my_conn.autocommit = True
            try:
                with m_conn.cursor() as cur:
                    cur.execute("CREATE USER 'sr_facade_adm'@'%' IDENTIFIED BY ?", (m_pw,))
                    cur.execute("GRANT ALL PRIVILEGES ON *.* TO 'sr_facade_adm'@'%' WITH GRANT OPTION")
                with my_conn.cursor() as cur:
                    cur.execute("CREATE USER 'sr_wrong_eng'@'%' IDENTIFIED BY %s", (my_pw,))
                    cur.execute("GRANT ALL PRIVILEGES ON *.* TO 'sr_wrong_eng'@'%' WITH GRANT OPTION")

                with app.test_request_context('/'):
                    user = User.query.first()
                    uid = user.id
                    group = ServerGroup.query.filter_by(user_id=uid).first()
                    app.blueprints['NODE-engine_type'].connector_visibility['mariadb'].set(True, user_id=uid)
                    app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True, user_id=uid)

                    m_srv = Server(
                        user_id=uid, servergroup_id=group.id, name='Owned MariaDB Server DDN',
                        host=m_route['host'], port=m_route['port'], username='sr_facade_adm',
                        maintenance_db=None, save_password=0,
                    )
                    m_srv._cde_endpoint_registration = registration_profile('mariadb-native')
                    m_srv._cde_endpoint_route_configuration = {
                        'host': m_route['host'], 'port': m_route['port'], 'user': 'sr_facade_adm',
                        'ssl': False, 'ssl_verify_cert': False,
                        'credential_kinds': ['database_password'],
                    }
                    my_srv = Server(
                        user_id=uid, servergroup_id=group.id, name='Owned MySQL Wrong Engine Check',
                        host=my_route['host'], port=my_route['port'], username='sr_wrong_eng',
                        maintenance_db=None, save_password=0,
                    )
                    my_srv._cde_endpoint_registration = registration_profile('mysql-native')
                    my_srv._cde_endpoint_route_configuration = {
                        **my_route, 'user': 'sr_wrong_eng', 'credential_kinds': ['database_password'],
                    }
                    db.session.add_all([m_srv, my_srv])
                    db.session.commit()
                    m_verify = url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=m_srv.id)
                    m_url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=m_srv.id)
                    my_verify = url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=my_srv.id)
                    my_url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=my_srv.id)

                client = app.test_client()
                with client.session_transaction() as sess:
                    sess['_user_id'] = str(uid)
                    sess['_fresh'] = True
                assert client.post(m_verify, json={'password': m_pw}).get_json()['success']
                assert client.post(my_verify, json={'password': my_pw}).get_json()['success']

                def post(url, action, req_body, denied=False, query_string=None):
                    target_url = f'{url}?{query_string}' if query_string else url
                    resp = client.post(target_url, json={'action': action, 'request': req_body})
                    assert resp.headers.get('Cache-Control') == 'no-store'
                    body = resp.get_json()
                    if denied:
                        assert resp.status_code != 200 or not body.get('success'), (action, body)
                        return resp.status_code, body
                    assert resp.status_code == 200 and body.get('success'), (action, body)
                    return body['data']

                # 1. Wrong-engine refusal on MySQL server
                for wrong_action, wrong_req in [
                    ('mariadb_server_catalog', {}),
                    ('mariadb_server_plan', {'baseline': '{}', 'source': '{}'}),
                    ('mariadb_server_review', {'baseline': '{}', 'source': '{}', 'execution_sha256': '0' * 64}),
                    ('mariadb_server_receipts', {}),
                ]:
                    status_code, _ = post(my_url, wrong_action, wrong_req, denied=True)
                    assert status_code == 400
                proof['checks'].append({'check': 'wrong_engine_mysql_refused', 'status_code': 400})

                # Helper to edit exported server DDN snapshot
                from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_own_export
                from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export

                def edit_ddn_for_var_and_role(exported, new_sbs, role_name=None):
                    decoded = read_own_export(exported['snapshot'], engine='mariadb')
                    resources = [
                        {
                            'resource_id': r['resource_id'],
                            'resource_kind': r['kind'],
                            'display_name': r['name'],
                            'display_path': r.get('path') or [r['name']],
                            'native': deepcopy(r['native']),
                        }
                        for r in decoded['rows'].values()
                    ]
                    sbs_res = next(
                        res for res in resources
                        if res['resource_kind'] == 'system-variable'
                        and res['display_name'].upper() == 'SORT_BUFFER_SIZE'
                    )
                    sbs_res['native']['mariadb_change'] = {
                        'action': 'set_global',
                        'draft': {'value_mode': 'VALUE', 'value': str(new_sbs)},
                    }
                    if role_name is not None:
                        suid = exported['server_uid']
                        rid = 'mariadb-server:' + json.dumps(
                            [suid, 'accounts', [role_name, '']],
                            ensure_ascii=False,
                            separators=(',', ':'),
                        )
                        resources.append({
                            'resource_id': rid,
                            'resource_kind': 'role',
                            'display_name': role_name + ' / ',
                            'display_path': [suid, 'accounts', role_name + ' / '],
                            'native': {
                                'catalog_row': {
                                    'account_locked': False,
                                    'default_role': '',
                                    'host': '',
                                    'is_role': 'Y',
                                    'max_connections': 0,
                                    'max_questions': 0,
                                    'max_statement_time': '0.000000',
                                    'max_updates': 0,
                                    'max_user_connections': 0,
                                    'password_expired': 'N',
                                    'plugin': '',
                                    'ssl_type': '',
                                    'user': role_name,
                                },
                                'mariadb_change': {'action': 'create', 'draft': {}},
                                'section': 'accounts',
                                'server_uid': suid,
                                'system_object': False,
                            },
                        })
                    prov = exported['provenance']
                    rebuilt = build_export(
                        resources,
                        endpoint_id=prov['endpoint_id'],
                        target_id=prov['database_target_id'],
                        generation=prov['generation'],
                        include_system=True,
                        refreshed=True,
                        engine='mariadb',
                    )
                    return json.dumps(rebuilt['snapshot'], ensure_ascii=False)

                # 2. Export server DDN, build plan, test stale execution_sha256 & live drift conflict
                exported_1 = post(m_url, 'mariadb_server_catalog', {})
                assert exported_1['server_uid'] == m_fix['server_uid']
                baseline_1 = json.dumps(exported_1['snapshot'], ensure_ascii=False)

                with m_conn.cursor() as cur:
                    cur.execute('SELECT @@GLOBAL.sort_buffer_size')
                    initial_sbs = int(cur.fetchone()[0])
                target_sbs_1 = initial_sbs + 16384
                desired_1 = edit_ddn_for_var_and_role(exported_1, target_sbs_1)

                # Also verify query-string database_target_id does not break server-scoped plan!
                plan_1 = post(
                    m_url,
                    'mariadb_server_plan',
                    {'baseline': baseline_1, 'source': desired_1},
                    query_string='database_target_id=ignored-db-scope',
                )
                assert plan_1['ready_for_review'] is True
                assert len(plan_1['operations']) == 1

                # Stale execution_sha256 conflict on review
                stale_status, _ = post(
                    m_url,
                    'mariadb_server_review',
                    {
                        'baseline': baseline_1,
                        'source': desired_1,
                        'execution_sha256': 'f' * 64,
                    },
                    denied=True,
                )
                assert stale_status == 400
                proof['checks'].append({'check': 'stale_execution_digest_refused', 'status_code': stale_status})

                # Create review_1, then cause live out-of-band drift before apply!
                review_1 = post(
                    m_url,
                    'mariadb_server_review',
                    {
                        'baseline': baseline_1,
                        'source': desired_1,
                        'execution_sha256': plan_1['execution_sha256'],
                    },
                )
                # Wrong review_digest and unknown review_id refused
                bad_digest_status, _ = post(
                    m_url,
                    'mariadb_server_apply',
                    {
                        'review_id': review_1['review_id'],
                        'review_digest': '0' * 64,
                        'confirmed': True,
                    },
                    denied=True,
                )
                assert bad_digest_status == 400
                unknown_id_status, _ = post(
                    m_url,
                    'mariadb_server_apply',
                    {
                        'review_id': '00000000-0000-0000-0000-000000000000',
                        'review_digest': review_1['review_digest'],
                        'confirmed': True,
                    },
                    denied=True,
                )
                assert unknown_id_status == 400

                # Out-of-band native mutation causes baseline_sha256 conflict!
                drift_sbs = initial_sbs + 8192
                with m_conn.cursor() as cur:
                    cur.execute(f'SET GLOBAL sort_buffer_size = {drift_sbs}')

                # Plan detects live conflict
                drift_plan = post(
                    m_url, 'mariadb_server_plan', {'baseline': baseline_1, 'source': desired_1}
                )
                assert drift_plan['conflicts'] and not drift_plan['ready_for_review']

                # Apply of pre-drift review_1 refuses dispatch (not_applied / not_dispatched)
                drift_apply = post(
                    m_url,
                    'mariadb_server_apply',
                    {
                        'review_id': review_1['review_id'],
                        'review_digest': review_1['review_digest'],
                        'confirmed': True,
                    },
                )
                assert drift_apply['state'] == 'not_applied'
                assert drift_apply['outcome']['state'] == 'not_applied'
                assert drift_apply['statement_outcomes'][0]['state'] == 'not_dispatched'
                assert drift_apply['statement_outcomes'][0]['outcome']['rejection_reason'] == (
                    'Native server object changed since review'
                )
                # Repeating apply on consumed review_1 returns stored receipt without redispatch
                replay_1 = post(
                    m_url,
                    'mariadb_server_apply',
                    {
                        'review_id': review_1['review_id'],
                        'review_digest': review_1['review_digest'],
                        'confirmed': True,
                    },
                )
                assert replay_1['state'] == 'not_applied'
                assert replay_1['finished_at'] == drift_apply['finished_at']
                proof['checks'].append({
                    'check': 'stale_generation_drift_and_replay_refused',
                    'plan_conflict_detected': True,
                    'apply_not_dispatched_on_live_drift': True,
                    'bad_digest_refused_status': bad_digest_status,
                    'unknown_review_id_refused_status': unknown_id_status,
                    'consumed_review_idempotent_non_redispatch': True,
                })

                # 3. Fresh export -> edit (SORT_BUFFER_SIZE + CREATE ROLE sr_facade_role) -> plan -> review -> apply -> receipt & receipts -> native SQL read-back!
                exported_2 = post(m_url, 'mariadb_server_catalog', {})
                baseline_2 = json.dumps(exported_2['snapshot'], ensure_ascii=False)
                final_sbs = drift_sbs + 16384
                desired_2 = edit_ddn_for_var_and_role(exported_2, final_sbs, role_name='sr_facade_role')
                plan_2 = post(
                    m_url, 'mariadb_server_plan', {'baseline': baseline_2, 'source': desired_2}
                )
                assert plan_2['ready_for_review'] is True and len(plan_2['operations']) == 2
                review_2 = post(
                    m_url,
                    'mariadb_server_review',
                    {
                        'baseline': baseline_2,
                        'source': desired_2,
                        'execution_sha256': plan_2['execution_sha256'],
                    },
                )
                applied_2 = post(
                    m_url,
                    'mariadb_server_apply',
                    {
                        'review_id': review_2['review_id'],
                        'review_digest': review_2['review_digest'],
                        'confirmed': True,
                    },
                )
                assert applied_2['state'] == 'acknowledged'
                assert applied_2['outcome']['state'] == 'acknowledged'
                assert applied_2['outcome']['rediscovery_verified'] is True

                receipt = post(m_url, 'mariadb_server_receipt', {'review_id': review_2['review_id']})
                assert receipt['review_id'] == review_2['review_id'] and receipt['state'] == 'acknowledged'
                receipts = post(
                    m_url,
                    'mariadb_server_receipts',
                    {},
                    query_string='database_target_id=ignored-db-scope',
                )['receipts']
                assert any(r['review_id'] == review_2['review_id'] for r in receipts)

                # Independent native SQL read-back!
                with m_conn.cursor() as cur:
                    cur.execute('SELECT @@GLOBAL.sort_buffer_size')
                    observed_sbs = int(cur.fetchone()[0])
                    cur.execute("SELECT User, is_role FROM mysql.user WHERE User='sr_facade_role'")
                    observed_role = cur.fetchone()
                assert observed_sbs == final_sbs
                assert observed_role == ('sr_facade_role', 'Y')

                # Verify repeat apply of review_2 does NOT re-execute SQL on MariaDB!
                post_apply_sbs = final_sbs + 4096
                with m_conn.cursor() as cur:
                    cur.execute(f'SET GLOBAL sort_buffer_size = {post_apply_sbs}')
                replay_2 = post(
                    m_url,
                    'mariadb_server_apply',
                    {
                        'review_id': review_2['review_id'],
                        'review_digest': review_2['review_digest'],
                        'confirmed': True,
                    },
                )
                assert replay_2['state'] == 'acknowledged'
                assert replay_2['finished_at'] == applied_2['finished_at']
                with m_conn.cursor() as cur:
                    cur.execute('SELECT @@GLOBAL.sort_buffer_size')
                    unchanged_sbs = int(cur.fetchone()[0])
                assert unchanged_sbs == post_apply_sbs

                proof['checks'].append({
                    'check': 'end_to_end_apply_receipt_and_independent_sql_readback',
                    'applied_operations': 2,
                    'verified_sort_buffer_size': observed_sbs,
                    'verified_created_role': 'sr_facade_role',
                    'receipt_and_receipts_verified': True,
                    'repeat_apply_non_redispatch_verified': True,
                })
            finally:
                my_conn.close()
                m_conn.close()
        proof['mariadb_fixture_cleanup'] = json.loads(
            (scratch / 'mariadb-fixture/fixture.json').read_text()
        )
        proof['mysql_fixture_cleanup'] = json.loads(
            (scratch / 'mysql-fixture/fixture.json').read_text()
        )
        assert proof['mariadb_fixture_cleanup']['owned_server_stopped']
        assert proof['mysql_fixture_cleanup']['owned_server_stopped']
        proof['complete'] = True
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        (work / 'mariadb-server-facade-http.json').write_text(
            json.dumps(proof, indent=2, default=str) + '\n'
        )
    print(json.dumps({'complete': proof['complete'], 'checks': len(proof['checks'])}))


if __name__ == '__main__':
    main()
