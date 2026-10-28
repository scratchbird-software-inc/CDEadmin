#!/usr/bin/env python3
"""Native DDN exchange/migration qualification with isolated Linux fixtures."""
import argparse
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
import os
import subprocess
import signal
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.cdeadmin_firebird_admin_mapping_gate import _create_client  # noqa: E402
from tools.cdeadmin_firebird_local_fixture import run_local, _route_arguments  # noqa: E402
from pgadmin.cdeadmin.providers.firebird.provider import FirebirdProvider, _resources  # noqa: E402
from pgadmin.cdeadmin.security.secrets import SecretLease  # noqa: E402
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export  # noqa: E402
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog  # noqa: E402
from pgadmin.cdeadmin.workspace.firebird_relational_review import handoff  # noqa: E402
from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan  # noqa: E402
from pgadmin.cdeadmin.providers.firebird.schema_application import apply_review  # noqa: E402
from pgadmin.cdeadmin.workspace.firebird_schema_apply import SchemaApplications  # noqa: E402


class Permissions:
    def __init__(self, password):
        self.password = password
    def require(self, *_):
        return True
    def acquire_secret(self, *_):
        return SecretLease(self.password)


def graphical(connection, provider, route, evidence):
    connection.execute_immediate('CREATE TABLE DDN_GRAPH (ID INTEGER PRIMARY KEY, V INTEGER, T VARCHAR(10) CHARACTER SET UTF8)')
    connection.commit()
    connection.execute_immediate("INSERT INTO DDN_GRAPH VALUES (1, 7, 'native')")
    connection.commit()
    resources = _resources(connection, {})
    connection.rollback()
    captured = build_export(resources, endpoint_id='owned', target_id='owned', generation='ddn-native')
    original = captured['diagram']['snapshot']
    edited = deepcopy(original)
    from hashlib import sha256
    field = 'n_' + sha256(b'column:DDN_GRAPH:V').hexdigest()
    edits=[{'target':{'file':'relations.ddn','id':field},'path':path,'value':value}
           for path,value in [('content.datatype','BIGINT'),('content.nullable',False),('description','Edited through DDN')]]
    changed=subprocess.run(['node',str(ROOT/'tools/ddn_edit.mjs')],input=json.dumps({'snapshot':edited,'edits':edits}),text=True,capture_output=True,timeout=30,check=True)
    edited=json.loads(changed.stdout)
    exchanged = handoff(captured['snapshot'], original, edited)
    baseline, desired = (read_catalog(exchanged[key]) for key in ('baseline', 'desired'))
    current = build_export(resources, endpoint_id='owned', target_id='owned', generation='ddn-native', include_system=True, native_model=True)
    plan = build_plan(baseline, desired, current)
    (evidence/'graphical-plan.json').write_text(json.dumps(plan, indent=2))
    assert plan['status'] == 'review-ready', plan['blockers']
    store = SchemaApplications(evidence/'graphical-receipts.json')
    reviewed = store.review(plan, baseline, desired, 'owner', 'binding', route['database'])
    response = store.apply({'review_id': reviewed['review_id'], 'review_digest': reviewed['review_digest'], 'confirmed': True},
        'owner', 'binding', lambda record: apply_review(provider, route, record))
    (evidence/'graphical-application.json').write_text(json.dumps(response, indent=2))
    assert response['outcome']['native_commit_returned'], response
    assert response['outcome']['rediscovery']['available'], response
    assert all(item['matches_reviewed_properties'] for item in response['outcome']['rediscovery']['objects']), response
    refreshed = _resources(connection, {})
    connection.rollback()
    column = next(row for row in refreshed if row['resource_id'] == 'column:DDN_GRAPH:V')
    assert str(column['native']['field_type']) == '16'
    assert str(column['native']['not_null']) == '1'
    assert column['native']['description'] == 'Edited through DDN'
    with connection.cursor() as cursor:
        cursor.execute('SELECT V FROM DDN_GRAPH')
        assert cursor.fetchone()[0] == 7
    connection.rollback()
    fresh = build_export(refreshed, endpoint_id='owned', target_id='owned', generation='ddn-native', include_system=True, native_model=True)
    assert build_plan(fresh, fresh, fresh)['status'] == 'no-op'
    # A spent durable token returns its recorded receipt and never redispatches.
    replay = store.apply({'review_id': reviewed['review_id'], 'review_digest': reviewed['review_digest'], 'confirmed': True},
        'owner', 'binding', lambda _: (_ for _ in ()).throw(AssertionError('replayed')))
    assert replay['state'] == response['state']
    return {'native_commit_and_rediscovery': True, 'data_preserved': True, 'no_automatic_replay': True}


def unknown_commit(connection, provider, route, evidence):
    connection.execute_immediate("CREATE EXCEPTION DDN_UNKNOWN 'before'")
    connection.commit()
    rows = _resources(connection, {})
    connection.rollback()
    base = build_export(rows, endpoint_id='owned', target_id='owned', generation='unknown', include_system=True, native_model=True)
    desired = deepcopy(base)
    desired['rows']['exception:DDN_UNKNOWN']['native']['message'] = 'committed'
    plan = build_plan(base, desired, base)
    assert plan['status'] == 'review-ready'
    store = SchemaApplications(evidence/'unknown-receipts.json')
    review = store.review(plan, base, desired, 'owner', 'binding', route['database'])
    request = {'review_id':review['review_id'], 'review_digest':review['review_digest'], 'confirmed':True}
    original = provider.client._connect
    def connect(request):
        native = original(request)
        commit = native.commit
        def lost_reply():
            commit()
            raise ConnectionError('Owned commit reply loss injection')
        native.commit = lost_reply
        return native
    provider.client._connect = connect
    try:
        response = store.apply(request, 'owner', 'binding', lambda record: apply_review(provider, route, record))
    finally:
        provider.client._connect = original
    outcome = response['outcome']
    assert outcome['state'] == 'unknown_outcome' and outcome['commit_requested'] and not outcome['native_commit_returned'], response
    assert store.apply(request, 'owner', 'binding', lambda _: (_ for _ in ()).throw(AssertionError('replayed'))) == response
    actual = _resources(connection, {})
    connection.rollback()
    assert next(row for row in actual if row['resource_id']=='exception:DDN_UNKNOWN')['native']['message']=='committed'
    (evidence/'unknown-application.json').write_text(json.dumps(response, indent=2))
    return {'native_commit_reply_loss':True, 'durable_unknown_outcome':True, 'no_automatic_replay':True}


def dialect_one(native, route, password, provider, evidence, temporary):
    path = str(temporary/'dialect-one.fdb')
    from pgadmin.cdeadmin.providers.firebird.provider import _database_create_arguments
    from pgadmin.cdeadmin.providers.firebird.database_creation import create_database
    from firebird.driver import core
    selected = {**route, 'database': path}
    arguments = _database_create_arguments(selected, _route_arguments(selected)['database'], {'sql_dialect': 1}, native)
    connection = create_database(native, core, password=password, **arguments)
    connection.close()
    connection = native.connect(password=password, **_route_arguments({**route, 'database': path}, native))
    try:
        connection.execute_immediate("CREATE EXCEPTION DDN_D1 'before'")
        connection.commit()
        rows = _resources(connection, {})
        connection.rollback()
        base = build_export(rows, endpoint_id='owned', target_id='owned', generation='dialect-one', include_system=True, native_model=True)
        assert str(next(row for row in base['rows'].values() if row['kind']=='database')['native']['sql_dialect']) == '1'
        wanted = deepcopy(base)
        wanted['rows']['exception:DDN_D1']['native']['message'] = 'after'
        plan = build_plan(base, wanted, base)
        assert plan['status']=='review-ready' and plan['sql_dialect']==1, plan['blockers']
        assert "ALTER EXCEPTION DDN_D1 'after'" in plan['script']
        outcome = apply_review(provider, {**route, 'database': path}, {'plan':plan,'baseline':base,'desired':wanted})
        assert outcome['native_commit_returned'] and outcome['rediscovery']['available'], outcome
        assert all(row['matches_reviewed_properties'] for row in outcome['rediscovery']['objects'])
        (evidence/'dialect-one-application.json').write_text(json.dumps(outcome,indent=2))
        return {'stored_database_dialect':1,'client_dialect':3,'native_commit_and_rediscovery':True}
    finally:
        connection.close()


SCENARIOS = ('graphical', 'embedded', 'dialect-one', 'data', 'sql-replay', 'unknown-commit', 'column', 'table', 'view', 'package', 'routine', 'trigger',
             'constraint', 'lifecycle', 'grant', 'external-function', 'import-order', 'erd')


def run(runtime, evidence, selected):
    report = {'complete': False, 'scenarios': [], 'failures': []}
    for scenario in selected:
        folder = evidence/scenario
        details = {}
        def check(native, admin, route, accounts, target, temporary):
            import secrets
            user, password = 'SYSDBA', secrets.token_urlsafe(24)
            admin.execute_immediate("ALTER USER SYSDBA PASSWORD '" + password + "' USING PLUGIN Srp")
            admin.commit()
            scoped = {**route, 'user': user, 'credential_reference_id': 'gate', 'principal_reference': 'gate'}
            permissions = Permissions(password)
            provider = object.__new__(FirebirdProvider)
            provider.client = _create_client(permissions)
            provider.permissions = permissions
            provider.attachment_mode = 'network'
            try:
                if scenario == 'graphical':
                    details.update(graphical(admin, provider, scoped, target))
                elif scenario == 'embedded':
                    from pgadmin.cdeadmin.providers.firebird.embedded_provider import PROFILE
                    path = str(temporary/'embedded-exchange.fdb')
                    from pgadmin.cdeadmin.providers.firebird.provider import _database_create_arguments
                    from pgadmin.cdeadmin.providers.firebird.database_creation import create_database
                    from firebird.driver import core
                    local_route = {'database': path, 'user':'SYSDBA', 'charset':'UTF8', 'attachment_mode':'embedded', 'filesystem_root':str(temporary)}
                    args = _database_create_arguments(local_route, path, {'sql_dialect':3}, native)
                    local = create_database(native, core, **args)
                    embedded = object.__new__(FirebirdProvider)
                    embedded.client = _create_client(permissions, attachment_mode='embedded', profile=PROFILE)
                    embedded.permissions = permissions
                    embedded.attachment_mode = 'embedded'
                    try:
                        details.update(graphical(local, embedded, {'database':path,'user':'SYSDBA','charset':'UTF8',
                            'attachment_mode':'embedded','filesystem_root':str(temporary)}, target))
                    finally:
                        local.close(); embedded.client.close()
                elif scenario == 'dialect-one':
                    details.update(dialect_one(native, scoped, password, provider, target, temporary))
                elif scenario == 'sql-replay':
                    from tools.firebird_ddn_sql_native import qualify
                    details.update(qualify(native, admin, scoped, password, target, temporary))
                elif scenario == 'unknown-commit':
                    details.update(unknown_commit(admin, provider, scoped, target))
                elif scenario == 'data':
                    from tools.firebird_data_export_native import qualify
                    destination_route = {**scoped, 'database':str(temporary/'data-import.fdb')}
                    destination = native.create_database(password=password, **_route_arguments(destination_route,native))
                    try:
                        details.update(qualify(admin, scoped, password, destination, destination_route))
                    finally:
                        destination.close()
                elif scenario == 'erd':
                    from tools.firebird_erd_native import qualify
                    details.update(qualify(admin, target))
                else:
                    module = importlib.import_module('tools.firebird_' + scenario.replace('-', '_') + ('_native' if scenario in {'lifecycle', 'import-order'} else '_plan_native'))
                    args = (admin, provider, scoped) if scenario in {'table', 'view'} else (admin, provider, scoped, target)
                    value = module.qualify(*args)
                    details.update(value if isinstance(value, dict) else {'result': value})
            finally:
                provider.client.close()
        try:
            result = run_local(runtime, folder, check)
            report['scenarios'].append({'name': scenario, 'complete': result['complete'], 'native': result, 'details': details})
            if not result['complete']:
                report['failures'].append(scenario)
        except Exception as error:
            report['failures'].append({'scenario': scenario, 'error_type': type(error).__name__})
    report['complete'] = not report['failures'] and len(report['scenarios']) == len(selected)
    (evidence/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


def isolated(runtime, evidence, selected):
    """A fresh driver/plugin loader per fixture; never reuse a removed root."""
    result = {'complete': False, 'scenarios': [], 'failures': [], 'process_isolation': True}
    for scenario in selected:
        child = evidence/scenario
        command = [sys.executable, str(Path(__file__).resolve()), '--runtime-root', str(runtime),
                   '--evidence', str(child), '--scenario', scenario]
        with (evidence/(scenario+'.log')).open('wb') as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = process.wait(timeout=1200)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL); process.wait()
                code = -1
        receipt = child/'summary.json'
        if receipt.exists():
            document = json.loads(receipt.read_text())
            result['scenarios'].extend(document['scenarios'])
            if code or not document['complete']:
                result['failures'].append(scenario)
        else:
            result['failures'].append({'scenario':scenario, 'exit_code':code})
    result['complete'] = not result['failures'] and len(result['scenarios']) == len(selected)
    (evidence/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--scenario', action='append', choices=SCENARIOS)
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=False)
    selected = args.scenario or SCENARIOS
    receipt = (run if len(selected)==1 else isolated)(args.runtime_root, args.evidence, selected)
    print(json.dumps(receipt, indent=2))
    raise SystemExit(0 if receipt['complete'] else 1)
