#!/usr/bin/env python3
"""Owned PostgreSQL 18.3 logical output, artifact recovery and browser proof."""
import argparse
import base64
import builtins
import hashlib
import json
from pathlib import Path
import secrets
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'web'), str(ROOT/'tools')]


def qualify(output, *, browser_binary=None, driver_binary=None):
    import psycopg
    from psycopg import sql
    from postgresql_qualification_support import server as owned_server
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents: raise ValueError('Evidence belongs outside the source checkout')
    output.mkdir(parents=True, exist_ok=False)
    proof = {'complete': False, 'checks': [], 'history_testing': 'not run', 'full_product_complete': False,
             'source_sha256': {}}
    for directory in ('web/pgadmin/cdeadmin/providers/postgresql', 'web/pgadmin/cdeadmin/workspace'):
        for path in (ROOT/directory).glob('*.py'):
            proof['source_sha256'][str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in ('tools/cdeadmin_postgresql_slot_changes_qualification.py', 'tools/cdeadmin_postgresql_wal_capture_qualification.py',
                 'web/pgadmin/browser/server_groups/servers/__init__.py'):
        proof['source_sha256'][name] = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    builtins.SERVER_MODE = None
    import config
    config.SERVER_MODE=False; config.TESTING=True; config.WTF_CSRF_ENABLED=False
    config.MASTER_PASSWORD_REQUIRED=False; config.USE_OS_SECRET_STORAGE=False
    config.DATA_DIR=str(output/'app'); config.SQLITE_PATH=str(output/'app/application.db')
    config.SESSION_DB_PATH=str(output/'app/sessions'); config.STORAGE_DIR=str(output/'app/storage')
    config.LOG_FILE=str(output/'app/application.log'); config.AZURE_CREDENTIAL_CACHE_DIR=str(output/'app/azure')
    config.CDEADMIN_OPERATION_STORE_PATH=str(output/'app/operations.json')
    config.CDEADMIN_POSTGRESQL_CONTINUITY_ROOT=str(output/'artifacts')
    from pgadmin import create_app
    from pgadmin.model import db, User, ServerGroup, Server
    from pgadmin.cdeadmin.workspace import service_for_app
    from pgadmin.cdeadmin.workspace import postgresql_slot_changes as changes
    from flask import url_for
    app=create_app('ScratchRobin-native-logical-changes'); app.PGADMIN_RUNTIME=False; app.PGADMIN_INT_KEY=''
    app.run_before_app_start(); client=app.test_client(); jobs=None
    try:
        with owned_server(output/'fixture', server_options=('-c', 'wal_level=logical')) as (route, password, fixture):
            arguments={'host':route['host'], 'port':route['port'], 'user':route['user'], 'password':password,
                       'dbname':route['database'], 'autocommit':True}
            with psycopg.connect(**arguments) as native:
                database_name='Native logical "ü"'
                native.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database_name)))
                target='postgresql-database:'+str(native.execute('SELECT oid FROM pg_database WHERE datname=%s',(database_name,)).fetchone()[0])
                with app.test_request_context('/'):
                    user=User.query.first(); group=ServerGroup.query.filter_by(user_id=user.id).order_by(ServerGroup.id).first()
                    app.blueprints['NODE-engine_type'].connector_visibility['postgresql'].set(True,user_id=user.id)
                    registered=Server(user_id=user.id,servergroup_id=group.id,name='Owned native logical changes',host=route['host'],port=route['port'],
                        username=route['user'],maintenance_db=route['database'],connection_params={'sslmode':'disable'},save_password=0)
                    db.session.add(registered); db.session.commit()
                    uid,sid,gid,endpoint=user.id,registered.id,group.id,registered.endpoint_profile.id
                    connect_url=url_for('NODE-server.connect_id',gid=gid,sid=sid)
                    workspace_url=url_for('NODE-server.cde_workspace_id',gid=gid,sid=sid)
                with client.session_transaction() as session: session['_user_id']=str(uid); session['_fresh']=True
                assert client.post(connect_url,json={'password':password}).get_json().get('success')
                def http(operation, request):
                    response=client.post(workspace_url,json={'action':'postgresql_continuity_'+operation,'request':request})
                    value=response.get_json()
                    if response.status_code!=200 or not value.get('success'):
                        (output/'http-failure.json').write_text(json.dumps(value,indent=2).replace(password,'<redacted>')+'\n')
                        raise AssertionError('Owned native logical HTTP '+operation+' failed')
                    return value['data']
                def wait(item, expected='completed', artifact=None):
                    deadline=time.monotonic()+90
                    while True:
                        current=http('status',{'job_id':item['job_id']})
                        if (current['state']==expected and current.get('slot_observation_state')!='pending' and
                                (artifact is None or (current.get('change_artifact') or {}).get('state')==artifact)):
                            return current
                        if current['state'] in {'failed','not_dispatched'} or current['state']=='unknown' and expected!='unknown':
                            (output/'job-failure.json').write_text(json.dumps(current,indent=2)+'\n')
                            raise AssertionError('Native logical job returned '+current['state'])
                        if time.monotonic()>deadline: raise TimeoutError('Owned native logical job deadline')
                        time.sleep(.05)
                def start(suffix, options, *, expected='completed', artifact=None):
                    reviewed=http('review',{'operation':'wal_slot_sql_'+suffix,'options':options,'database_target_id':target})
                    request={'job_id':reviewed['job_id'],'review_digest':reviewed['review_digest'],'confirmed':True}
                    current=wait(http('start',request),expected,artifact)
                    assert http('start',request)['job_id']==current['job_id']
                    return current
                def download(item):
                    response=client.post(workspace_url,data={'action':'postgresql_continuity_change_download','payload':json.dumps({'job_id':item['job_id']})})
                    assert response.status_code==200
                    data=response.data
                    assert hashlib.sha256(data).hexdigest()==response.headers['X-Content-SHA256']
                    assert response.headers['X-Export-Completeness']==('incomplete' if item['change_artifact']['state']=='partial' else 'verified')
                    response.close(); return data
                text_slot='sr_text_'+secrets.token_hex(6); binary_slot='sr_binary_'+secrets.token_hex(6)
                start('logical_create',{'slot':text_slot,'plugin':'test_decoding'})
                start('logical_create',{'slot':binary_slot,'plugin':'pgoutput'})
                jobs=service_for_app(app).postgresql_continuity_jobs
                with psycopg.connect(**{**arguments,'dbname':database_name}) as source:
                    source.execute('CREATE TABLE sr_logical_data(id bigint PRIMARY KEY,body text,payload bytea)')
                    publication='Publication "ü"'
                    source.execute(sql.SQL('CREATE PUBLICATION {} FOR TABLE sr_logical_data').format(sql.Identifier(publication)))
                    quoted_publication=sql.Identifier(publication).as_string(source)
                    text_options=[{'name':'include-xids','value':'0'},{'name':'skip-empty-xacts','value':'1'}]
                    binary_options=[{'name':'proto_version','value':'4'},{'name':'publication_names','value':quoted_publication},{'name':'binary','value':'true'}]
                    source.execute('BEGIN')
                    source.execute('INSERT INTO sr_logical_data VALUES(%s,%s,%s)',(9007199254740993,'Native "ü" 😀\n'+('large😀'*250000),b'\x00\x80\xffnative'))
                    source.execute('INSERT INTO sr_logical_data VALUES(%s,%s,%s)',(9007199254740994,'second row',b'\xff\x00'))
                    source.execute('COMMIT')
                    def baseline(slot, binary, pairs, count):
                        flat=[part for pair in pairs for part in (pair['name'],pair['value'])]
                        query=('SELECT lsn::text,xid::text,'+("encode(data,'hex')" if binary else 'data')+
                            ' FROM pg_logical_slot_peek_'+('binary_changes' if binary else 'changes')+'(%s,NULL,%s,VARIADIC %s::text[])')
                        return source.execute(query,(slot,count,flat)).fetchall()
                    def compare(item, expected, binary):
                        data=download(item); rows=[json.loads(line) for line in data.splitlines()]
                        decoded=[(r['lsn'],r['xid'],base64.b64decode(r['data']).hex() if binary else r['data']) for r in rows]
                        assert decoded==expected
                        assert item['native_sql_result']['rows']==str(len(expected))
                        return hashlib.sha256(data).hexdigest()
                    expected_text=baseline(text_slot,False,text_options,1); assert len(expected_text)>1
                    before=source.execute('SELECT confirmed_flush_lsn::text FROM pg_replication_slots WHERE slot_name=%s',(text_slot,)).fetchone()[0]
                    peek=start('peek_text',{'slot':text_slot,'upto_nchanges':1,'plugin_options':text_options},artifact='verified')
                    compare(peek,expected_text,False)
                    assert source.execute('SELECT confirmed_flush_lsn::text FROM pg_replication_slots WHERE slot_name=%s',(text_slot,)).fetchone()[0]==before
                    preview=http('change_preview',{'job_id':peek['job_id'],'offset':'0','limit':50})
                    assert any(row.get('native_values_previewed') is False for row in preview['rows'])
                    assert len(json.dumps(preview))<20000
                    consumed=start('get_text',{'slot':text_slot,'upto_nchanges':1,'plugin_options':text_options},artifact='verified')
                    compare(consumed,expected_text,False)
                    assert source.execute('SELECT confirmed_flush_lsn::text FROM pg_replication_slots WHERE slot_name=%s',(text_slot,)).fetchone()[0]!=before
                    assert not baseline(text_slot,False,text_options,0)
                    proof['checks'].extend(['native-text-peek-preserves-position-and-get-consumes-exact-unicode-output',
                        'native-transaction-threshold-exceeds-requested-row-count-and-large-preview-remains-bounded'])
                    expected_binary=baseline(binary_slot,True,binary_options,100); assert expected_binary
                    binary_peek=start('peek_binary',{'slot':binary_slot,'plugin_options':binary_options},artifact='verified')
                    compare(binary_peek,expected_binary,True)
                    if browser_binary:
                        from cdeadmin_postgresql_wal_capture_qualification import qualify_capture_browser
                        def browser_observed(item): compare(item,expected_binary,True)
                        proof['browser']=qualify_capture_browser(app,output,browser_binary,driver_binary,browser_observed,password,
                            slot_name=binary_slot,sql_database=database_name,change_case={'plugin_options':binary_options})
                    binary_get=start('get_binary',{'slot':binary_slot,'plugin_options':binary_options},artifact='verified')
                    compare(binary_get,expected_binary,True)
                    assert not baseline(binary_slot,True,binary_options,0)
                    proof['checks'].append('native-pgoutput-binary-peek-and-get-export-exact-protocol-bytes')
                    wrong_type=start('get_text',{'slot':binary_slot,'plugin_options':binary_options},expected='unknown',artifact='unavailable')
                    assert wrong_type['native_sqlstate']=='0A000' and not wrong_type['native_sql_acknowledged']
                    proof['checks'].append('native-binary-plugin-refuses-text-delivery-without-a-positive-acknowledgement')
                    source.execute("INSERT INTO sr_logical_data VALUES(9007199254740995,'publication fault',decode('00ff','hex'))")
                    expected_fault=baseline(text_slot,False,text_options,100)
                    publish=changes.durable_replace
                    def fail_publication(*_args): raise OSError('owned injected publication failure')
                    changes.durable_replace=fail_publication
                    try:fault=start('get_text',{'slot':text_slot,'plugin_options':text_options},artifact='unavailable')
                    finally:changes.durable_replace=publish
                    assert fault['native_sql_acknowledged']
                    while fault['job_id'] in jobs.workers: time.sleep(.02)
                    reconciled=http('change_reconcile',{'job_id':fault['job_id']})
                    assert reconciled['change_artifact']['state']=='verified' and reconciled['change_artifact']['publication_reconciled']
                    compare(reconciled,expected_fault,False)
                    assert not baseline(text_slot,False,text_options,0)
                    proof['checks'].append('native-consumption-ack-survives-publication-failure-and-byte-reconciliation-does-not-replay')
                    source.execute("INSERT INTO sr_logical_data VALUES(9007199254740996,'unrecorded acknowledgement',decode('0080ff','hex'))")
                    expected_lost=baseline(text_slot,False,text_options,100)
                    stream=changes.stream
                    def lose_handoff(*args,**kwargs):
                        def lost(_result): raise OSError('owned injected acknowledgement handoff failure')
                        return stream(*args,**{**kwargs,'acknowledge':lost})
                    changes.stream=lose_handoff
                    try:lost=start('get_text',{'slot':text_slot,'plugin_options':text_options},expected='unknown',artifact='unavailable')
                    finally:changes.stream=stream
                    while lost['job_id'] in jobs.workers: time.sleep(.02)
                    partial=http('change_reconcile',{'job_id':lost['job_id']})
                    assert partial['state']=='unknown' and partial['change_artifact']['state']=='partial' and not partial['native_sql_acknowledged']
                    actual=[json.loads(line) for line in download(partial).splitlines()]
                    assert [(r['lsn'],r['xid'],r['data']) for r in actual]==expected_lost
                    assert not baseline(text_slot,False,text_options,0)
                    repeated=http('start',{'job_id':partial['job_id'],'review_digest':partial['review_digest'],'confirmed':True})
                    assert repeated['state']=='unknown'
                    proof['checks'].append('native-consumption-with-lost-ack-handoff-keeps-unknown-outcome-and-downloadable-incomplete-evidence')
                    proof['receipts']={'text_peek':peek['job_id'],'text_get':consumed['job_id'],'binary_peek':binary_peek['job_id'],
                        'binary_get':binary_get['job_id'],'wrong_output_type':wrong_type['job_id'],
                        'reconciled_acknowledged':reconciled['job_id'],'unconfirmed_partial':partial['job_id']}
                    for slot in (text_slot,binary_slot): start('drop',{'slot':slot})
                    proof['native_client']=peek['client_identity']; proof['native_database']=database_name
                    print('Native text/binary output, thresholds, exact downloads and both artifact-failure outcomes passed',flush=True)
        assert fixture['owned_server_stopped']
        assert download(partial)
        offline=http('change_preview',{'job_id':partial['job_id'],'offset':'0','limit':1})
        assert offline['artifact_state']=='partial' and not offline['native_sql_acknowledged']
        proof['checks'].append('offline-artifact-preview-and-exact-download-need-no-live-database')
        with app.test_request_context('/'):
            foreign=Server(user_id=uid,servergroup_id=gid,name='Owned foreign artifact scope',host=route['host'],port=route['port'],
                username=route['user'],maintenance_db=route['database'],connection_params={'sslmode':'disable'},save_password=0)
            db.session.add(foreign);db.session.commit()
            foreign_url=url_for('NODE-server.cde_workspace_id',gid=gid,sid=foreign.id)
        denied=client.post(foreign_url,data={'action':'postgresql_continuity_change_download','payload':json.dumps({'job_id':partial['job_id']})})
        assert denied.status_code==400 and not denied.get_json().get('success')
        proof['checks'].append('native-change-file-delivery-refuses-another-endpoint-owned-by-the-same-user')
        private=jobs.load(peek['job_id'],uid,endpoint)
        with (jobs.directory(private)/changes.FILENAME).open('ab') as altered:altered.write(b'changed after verification')
        changed=client.post(workspace_url,data={'action':'postgresql_continuity_change_download','payload':json.dumps({'job_id':peek['job_id']})})
        assert changed.status_code==400 and not changed.get_json().get('success')
        proof['checks'].append('native-change-file-delivery-refuses-changed-artifact-bytes')
        proof['complete']=True
    finally:
        if jobs is not None: jobs.close()
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--browser-binary'); parser.add_argument('--driver-binary')
    args=parser.parse_args()
    qualify(args.evidence,browser_binary=args.browser_binary,driver_binary=args.driver_binary)
