"""Qualify packaged native statistics through owned authenticated HTTP policy."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'web'),str(ROOT/'tools'),str(ROOT)]


def qualify(output,binary_path):
    import config
    from postgresql_qualification_support import local_server
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside the source checkout')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    result={'complete':False,'checks':[],'history_testing':'not run','source_sha256':{}}
    files=list((ROOT/'web/pgadmin/cdeadmin/providers/postgresql').glob('*.py'))
    files+=list((ROOT/'web/pgadmin/cdeadmin/providers/postgresql').glob('postgresql_*18_3.json'))
    files += [ROOT/'web/pgadmin/cdeadmin/workspace'/name for name in (
        'postgresql_monitoring_host.py','monitoring.py','monitoring_delegation.py')]
    files.append(Path(__file__))
    result['source_sha256']={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    config.SERVER_MODE=False;config.TESTING=True;config.WTF_CSRF_ENABLED=False
    config.MASTER_PASSWORD_REQUIRED=False;config.USE_OS_SECRET_STORAGE=False
    config.DATA_DIR=str(output/'app');config.SQLITE_PATH=str(output/'app/application.db')
    config.SESSION_DB_PATH=str(output/'app/sessions');config.STORAGE_DIR=str(output/'app/storage')
    config.LOG_FILE=str(output/'app/application.log');config.AZURE_CREDENTIAL_CACHE_DIR=str(output/'app/azure')
    config.CDEADMIN_MONITORING_PROCESS_MODE='single'
    config.CDEADMIN_MONITORING_WORKER_KEYS={'owned':base64.b64encode(os.urandom(32)).decode()}
    config.CDEADMIN_MONITORING_WORKER_ACTIVE_KEY_ID='owned'
    config.CDEADMIN_MONITORING_LOCK_PATH=str(output/'app/monitoring.lock')
    config.CDEADMIN_MONITORING_HISTORY={'enabled':False}
    from pgadmin import create_app
    from pgadmin.model import db,User,ServerGroup,Server
    from flask import url_for
    app=create_app('ScratchRobin-native-statistics');app.PGADMIN_RUNTIME=False;app.PGADMIN_INT_KEY=''
    app.run_before_app_start();client=app.test_client()
    host=app.extensions['cdeadmin_postgresql_monitoring_host']
    try:
        with local_server(output/'fixture',binary_path) as (route,password,fixture):
            with app.test_request_context('/'):
                user=User.query.first();group=ServerGroup.query.filter_by(user_id=user.id).order_by(ServerGroup.id).first()
                registered=Server(user_id=user.id,servergroup_id=group.id,name='Owned PostgreSQL statistics',
                    host=route['host'],port=route['port'],username=route['user'],maintenance_db=route['database'],
                    connection_params={'sslmode':'disable'},save_password=0)
                db.session.add(registered);db.session.commit();uid,sid=user.id,registered.id
                connect=url_for('NODE-server.connect_id',gid=group.id,sid=sid)
                endpoint=url_for('cdeadmin_postgresql_monitoring.monitoring',sid=sid)
                sources=url_for('cdeadmin_postgresql_monitoring.sources')
            config.SERVER_MODE=True
            try:
                anonymous=app.test_client().get(sources)
                assert anonymous.status_code in {302,401,403}
            finally:config.SERVER_MODE=False
            with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
            assert client.post(connect,json={'password':password}).get_json()['success']
            catalog=client.get(sources).get_json()['data']
            assert catalog['state']=='available' and len(catalog['sources'])==52
            assert sum(len(row['columns']) for row in catalog['sources'])==604
            result['checks'].append('authenticated-packaged-source-catalog-reconciles-all-52-native-families-and-604-columns')
            refused=client.post(endpoint,json={'native_metric_sources':['pg_stat_missing']})
            assert refused.status_code==400 and not host._grants
            result['checks'].append('unknown-native-family-refused-before-collector-admission')
            selected=[row['source_id'] for row in catalog['sources']]
            started=client.post(endpoint,json={'native_metric_sources':selected}).get_json()
            if not started.get('success'):
                (output/'http-failure.json').write_text(json.dumps(started,indent=2)+'\n')
                raise RuntimeError('Native HTTP collector admission failed')
            deadline=time.monotonic()+30
            while True:
                snapshot=client.get(endpoint).get_json()['data']
                if snapshot.get('samples'):break
                if time.monotonic()>deadline:raise TimeoutError('Native HTTP collector sample deadline')
                time.sleep(.05)
            sample=snapshot['samples'][-1]
            assert sample['transaction_completed'] is True
            assert set(sample['groups']['native_metrics']['sources'])==set(selected)
            assert all(frame['status'] in {'available','partial'} for frame in sample['groups']['native_metrics']['sources'].values())
            assert snapshot['policy']['native_metric_sources']==selected
            result['checks'].append('authenticated-native-policy-opens-an-independent-collector-and-publishes-every-selected-family')
            # A new authenticated browser session can read the ongoing policy;
            # collection owns no dependency on the initiating request/session.
            viewer=app.test_client()
            with viewer.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
            assert viewer.get(endpoint).get_json()['data']['state']=='collecting'
            result['checks'].append('independent-viewer-session-observes-an-already-running-collector-without-changing-policy')
            assert client.delete(endpoint).get_json()['data']['released']
            assert not host._grants
            result['checks'].append('authenticated-stop-releases-owned-native-connections-and-collector-grant')
        assert fixture['owned_server_stopped']
        result.update(complete=True,native_version='18.3')
    finally:
        host.close()
        (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--binary-path',type=Path,required=True)
    args=parser.parse_args();qualify(args.evidence,args.binary_path)
