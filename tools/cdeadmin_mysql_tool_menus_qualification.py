"""Qualify declared native tool menus on authenticated navigator responses."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def qualify(output):
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Keep evidence outside source')
    output.mkdir(parents=True, exist_ok=False)
    app = setup_application(output)
    from mysql_qualification_support import server, _root_connection
    from flask import url_for
    from pgadmin.model import User, Server, db
    from pgadmin.cdeadmin.providers.mysql_family.provider import MySQLDBAPIClient
    from cdeadmin_mysql_online_ddl_qualification import registration
    paths = ['web/pgadmin/cdeadmin/context_menu.py',
             'web/pgadmin/cdeadmin/ui_descriptors/mysql/tools.json',
             str(Path(__file__).relative_to(ROOT))]
    proof = {'complete': False, 'interfaces': [], 'history_testing': 'ScratchBird history not run',
             'native_workflows_requalified': False, 'source_sha256': {
                 p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}}
    owned = None
    try:
        with server(output / 'fixture') as (route, _name, owned):
            native = _root_connection('mysql', route['port']); native.autocommit = True
            try:
                with native.cursor() as cursor:
                    cursor.execute('CREATE DATABASE sr_osc')
                    password = secrets.token_urlsafe(24)
                    cursor.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s', (password,))
            finally:
                native.close()
            original = MySQLDBAPIClient._connect
            for use_c in (False, True):
                classes = []
                def connect(self, request):
                    handle = original(self, request); classes.append(type(handle).__name__); return handle
                with patch.object(MySQLDBAPIClient, '_connect', connect):
                    sid, target, _post = registration(app, route, password, use_c)
                    with app.test_request_context('/'):
                        item = db.session.get(Server, sid); uid = User.query.first().id
                        endpoint = item.endpoint_profile
                        assert endpoint.runtime_identity.verification_state == 'verified'
                        node_url = url_for('NODE-server.nodes_id', gid=item.servergroup_id, sid=sid)
                        databases_url = url_for('NODE-server.children_id', gid=item.servergroup_id, sid=sid)
                    client = app.test_client()
                    with client.session_transaction() as session:
                        session['_user_id'], session['_fresh'] = str(uid), True
                    def get(url, key='data'):
                        response = client.get(url); value = response.get_json()
                        assert response.status_code == 200 and value['success'], value
                        return value[key]
                    node = get(node_url, 'result')
                    if isinstance(node, list):
                        assert len(node) == 1; node = node[0]
                    actions = {row['command_id']: row for row in node['cde_context_actions']}
                    for name, tab in [('data_drift', 'mysql-data-drift'), ('spatial', 'mysql-spatial'),
                                      ('content_search', 'mysql-content-search'), ('workload', 'mysql-workload')]:
                        row = actions['endpoint.mysql.' + name]
                        assert row['enabled'] and row['arguments'] == {'tab': tab, 'database_target_id': None}
                    databases = get(databases_url)
                    selected = next(row for row in databases if row['_id'] == target)
                    rows = {row['command_id']: row for row in selected['cde_context_actions']}
                    for name in ['monitoring', 'monitoring_policy', 'spatial', 'dashboard_editor', 'catalog_ddn', 'test_data']:
                        assert rows['database.mysql.' + name]['arguments']['database_target_id'] == target
                    # Verification loss changes reader admission, not the
                    # owner's ability to reopen independently retained jobs.
                    with app.app_context():
                        item = db.session.get(Server, sid)
                        item.endpoint_profile.runtime_identity.verification_state = 'failed'; db.session.commit()
                    failed = get(node_url, 'result')
                    if isinstance(failed, list): failed = failed[0]
                    rows = {row['command_id']: row for row in failed['cde_context_actions']}
                    assert not rows['endpoint.mysql.workload']['enabled']
                    assert rows['endpoint.mysql.physical']['enabled'] and rows['endpoint.mysql.host']['enabled']
                    assert rows['endpoint.mysql.dashboard_editor']['enabled']
                expected = 'CharsetCMySQLConnection' if use_c else 'CharsetMySQLConnection'
                assert classes and set(classes) == {expected}, classes
                proof['interfaces'].append({'use_c': use_c, 'native_connection_class': expected,
                    'authenticated_endpoint_tools': True, 'authenticated_database_scope': True,
                    'verification_loss_disables_readers': True, 'offline_owner_job_access': True})
            proof['complete'] = True
    finally:
        proof['owned_server_stopped'] = bool(owned) and owned['owned_server_stopped']
        (output / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    print(json.dumps({'complete': qualify(parser.parse_args().output)['complete']}))
