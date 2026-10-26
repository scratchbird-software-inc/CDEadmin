"""Native channel configuration/status, exchange and independent access boundaries."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'web'), str(ROOT/'tools')]


def qualify(output):
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents: raise ValueError('Keep evidence outside source')
    output.mkdir(parents=True, exist_ok=False); app = setup_application(output)
    from mysql_qualification_support import server, _root_connection
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE, _create_client, _resources
    from pgadmin.cdeadmin.providers.mysql_family.mysql_server_catalog import capture
    from pgadmin.cdeadmin.providers.mysql_family.installed_catalog import CHANNEL_COLUMNS, APPLIER_COLUMNS
    from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
    from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
    from pgadmin.cdeadmin.security import SecretLease
    from cdeadmin_mysql_online_ddl_qualification import registration
    paths = ['web/pgadmin/cdeadmin/providers/mysql_family/'+p for p in
             ['provider.py','installed_catalog.py','mysql_server_catalog.py']]
    paths.append(str(Path(__file__).relative_to(ROOT)))
    proof = {'complete': False, 'interfaces': [], 'application': [], 'restricted': [], 'disabled': [], 'mixed_grants': [],
             'full_native_inventory_complete': False, 'history_testing': 'ScratchBird history not run',
             'source_sha256': {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    owned = []
    source_password = secrets.token_urlsafe(20)
    expected_status = {}
    def records(cursor, source):
        cursor.execute(source); names = [column[0].lower() for column in cursor.description]
        return [dict(zip(names,row)) for row in cursor.fetchall()]
    def observe_status(cursor):
        queries = {
            'applier': 'SELECT CHANNEL_NAME,SERVICE_STATE,REMAINING_DELAY,COUNT_TRANSACTIONS_RETRIES FROM performance_schema.replication_applier_status',
            'receiver': 'SELECT CHANNEL_NAME,SERVICE_STATE,SOURCE_UUID,RECEIVED_TRANSACTION_SET,LAST_ERROR_NUMBER,CAST(LAST_ERROR_TIMESTAMP AS CHAR) AS LAST_ERROR_TIMESTAMP FROM performance_schema.replication_connection_status'}
        result = {key:{row['channel_name']:row for row in records(cursor,query)} for key,query in queries.items()}
        for row in result['applier'].values():row['count_transactions_retries']=str(row['count_transactions_retries'])
        return result
    def configure(cursor):
        nonlocal expected_status
        policy_user="policy雪'@reader"
        cursor.execute('CREATE USER %s@%s ACCOUNT LOCK',(policy_user,'%'))
        cursor.execute('GRANT REPLICATION_APPLIER ON *.* TO %s@%s',(policy_user,'%'))
        profiles=[('', 'NULL',1,17,'ON',None,'OFF'),("catalog 雪'", "''",1,3,'GENERATE',policy_user,'OFF'),
                  ('assign_local','NULL',0,0,'STREAM',None,'LOCAL'),
                  ('assign_uuid','NULL',0,7,'OFF',None,"'01234567-89ab-cdef-0123-456789abcdef'")]
        for name, tls, auto, delay, primary, policy, assign in profiles:
            policy_source='PRIVILEGE_CHECKS_USER='+('%s@%s' if policy else 'NULL')
            source = ("CHANGE REPLICATION SOURCE TO SOURCE_HOST='example.invalid', SOURCE_PORT=3307, "
                "SOURCE_USER='source_reader', SOURCE_PASSWORD=%s, SOURCE_BIND='127.0.0.1', "
                "SOURCE_CONNECT_RETRY=17, SOURCE_RETRY_COUNT=18446744073709551615, SOURCE_HEARTBEAT_PERIOD=1.25, "
                "SOURCE_SSL=1, SOURCE_SSL_CA='/owned/ca.pem', SOURCE_SSL_CAPATH='/owned/cas', "
                "SOURCE_SSL_CERT='/owned/cert.pem', SOURCE_SSL_CIPHER='ECDHE-RSA-AES128-GCM-SHA256', "
                "SOURCE_SSL_KEY='/owned/private-key.pem', SOURCE_SSL_VERIFY_SERVER_CERT=1, "
                "SOURCE_SSL_CRL='/owned/crl.pem', SOURCE_SSL_CRLPATH='/owned/crls', "
                "SOURCE_TLS_VERSION='TLSv1.2,TLSv1.3', SOURCE_PUBLIC_KEY_PATH='/owned/public.pem', "
                "GET_SOURCE_PUBLIC_KEY=1, NETWORK_NAMESPACE='owned_catalog', "
                "SOURCE_COMPRESSION_ALGORITHMS='zstd,zlib,uncompressed', SOURCE_ZSTD_COMPRESSION_LEVEL=7, "
                "REQUIRE_ROW_FORMAT=1, SOURCE_AUTO_POSITION="+str(auto)+", SOURCE_CONNECTION_AUTO_FAILOVER="+str(auto)+
                ", GTID_ONLY="+str(auto)+", SOURCE_DELAY="+str(delay)+", REQUIRE_TABLE_PRIMARY_KEY_CHECK="+primary+
                ", ASSIGN_GTIDS_TO_ANONYMOUS_TRANSACTIONS="+assign+", "+policy_source+
                ", SOURCE_TLS_CIPHERSUITES="+tls+" FOR CHANNEL %s")
            cursor.execute(source, (source_password,policy,'%',name) if policy else (source_password,name))
        rows = records(cursor,'SELECT * FROM performance_schema.replication_connection_configuration ORDER BY CHANNEL_NAME')
        assert len(rows)==4 and set(rows[0])=={key.lower() for key in CHANNEL_COLUMNS}
        expected = {row['channel_name']:{**row,'connection_retry_count':str(row['connection_retry_count'])} for row in rows}
        assert expected['']['tls_ciphersuites'] is None and expected["catalog 雪'"]['tls_ciphersuites']==''
        assert all(row['connection_retry_count']==str(2**64-1) for row in expected.values())
        policies=records(cursor,'SELECT * FROM performance_schema.replication_applier_configuration')
        assert len(policies)==4 and set(policies[0])=={key.lower() for key in APPLIER_COLUMNS}
        for row in policies:expected[row['channel_name']]['applier_configuration']=row
        assert expected['']['applier_configuration']['privilege_checks_user'] is None
        assert policy_user.replace("'","\\'") in expected["catalog 雪'"]['applier_configuration']['privilege_checks_user']
        assert {row['applier_configuration']['assign_gtids_to_anonymous_transactions_type'] for row in expected.values()}=={'OFF','LOCAL','UUID'}
        expected_status=observe_status(cursor)
        return expected
    def explorer(rows, expected):
        channels = [row for row in rows if row['resource_kind']=='replication-channel']
        native = lambda row:row.get('native') or row.get('extensions',{}).get('mysql',{}).get('native')
        actual = {native(row)['channel_name']:native(row) for row in channels}
        assert actual.keys()==expected.keys()
        for name, facts in actual.items():
            assert {key:facts[key] for key in expected[name]}==expected[name]
            assert facts['replication_password_returned'] is False
            for field, values in expected_status.items():assert facts[field]==values[name]
        assert source_password not in json.dumps(rows)
    def ddn(captured, expected):
        exported = build_export(captured['resources'], endpoint_id='owned', target_id='server:'+captured['server_uuid'],
            generation=captured['generation'], engine='mysql')
        return snapshot(exported['snapshot'],expected)
    def snapshot(document, expected):
        parsed = read_catalog(json.dumps(document),engine='mysql')
        actual = {row['native']['catalog_row']['channel_name']:row['native']['catalog_row']
            for row in parsed['rows'].values() if row['kind']=='replication-channel'}
        assert actual==expected and source_password not in json.dumps(document)
        for row in parsed['rows'].values():
            if row['kind']=='replication-channel':
                for field, values in expected_status.items():assert row['native'][field]==values[row['native']['catalog_row']['channel_name']]
        return parsed
    try:
        with server(output/'fixture') as (route,_name,fixture):
            owned.append(fixture); oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;q=oracle.cursor()
            try:
                expected=configure(q);q.execute('CREATE DATABASE sr_osc');q.execute('CREATE TABLE sr_osc.pending(id INT PRIMARY KEY)')
                for pure in (True,False):
                    client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),SimpleNamespace())
                    handle=client._connect({'route':{**route,'database':'sr_osc','use_pure':pure,'autocommit':True}})
                    native_class=type(handle).__name__
                    assert native_class==('CharsetMySQLConnection' if pure else 'CharsetCMySQLConnection')
                    try:
                        q.execute("START REPLICA SQL_THREAD FOR CHANNEL ''")
                        deadline=time.monotonic()+10
                        while True:
                            expected_status=observe_status(q)
                            if expected_status['applier']['']['service_state']=='ON':break
                            if time.monotonic()>deadline:raise TimeoutError('Native applier did not start')
                            time.sleep(.05)
                        try:
                            explorer(_resources(handle,{'route':{'database':'sr_osc'}},MYSQL_PROFILE),expected)
                            ddn(capture(handle),expected)
                        finally:
                            q.execute("STOP REPLICA SQL_THREAD FOR CHANNEL ''");expected_status=observe_status(q)
                        oracle.autocommit=False;q.execute('SAVEPOINT channel_guard');q.execute('INSERT INTO sr_osc.pending VALUES(1)')
                        explorer(_resources(handle,{'route':{'database':'sr_osc'}},MYSQL_PROFILE),expected)
                        ddn(capture(handle),expected)
                        q.execute('SELECT ROW_COUNT()');assert q.fetchone()==(1,)
                        q.execute('ROLLBACK TO SAVEPOINT channel_guard');oracle.rollback();oracle.autocommit=True
                        q.execute("SELECT CAST('owned-warning' AS UNSIGNED)");q.fetchall();q.execute('SHOW WARNINGS');warnings=q.fetchall();assert warnings
                        ddn(capture(handle),expected);q.execute('SHOW WARNINGS');assert q.fetchall()==warnings
                        proof['interfaces'].append({'use_pure':pure,'native_connection_class':native_class,
                            'all_27_fields':True,'null_empty_and_uint64_text_exact':True,'ddn_roundtrip_exact':True,
                            'original_diagnostics_and_savepoint_preserved':True,'source_password_excluded':True,
                            'all_7_applier_configuration_fields':True,'all_4_applier_status_fields':True,
                            'native_active_and_stopped_applier_observed':True})
                    finally:client._forget_and_close(handle);client.close()
                password=secrets.token_urlsafe(24);q.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                for pure in (True,False):
                    sid,target,post=registration(app,route,password,not pure)
                    page=post('resource_page',{});rows=list(page['items'])
                    while page.get('next_cursor'):
                        page=post('resource_page',{'continuation':page['next_cursor'],'generation':page['generation']});rows.extend(page['items'])
                    selected=[row for row in rows if row['resource_kind']=='replication-channel']
                    inspected=[post('resource_inspect',{'resource_id':row['resource_id'],'generation':page['generation']}) for row in selected]
                    explorer(inspected,expected)
                    from flask import url_for
                    from pgadmin.model import User,Server,db
                    with app.test_request_context('/'):
                        saved=db.session.get(Server,sid);uid=User.query.first().id
                        url=url_for('NODE-server.cde_workspace_id',gid=saved.servergroup_id,sid=sid)
                    browser=app.test_client()
                    with browser.session_transaction() as session:session['_user_id'],session['_fresh']=str(uid),True
                    reply=browser.post(url,json={'action':'mysql_server_catalog','request':{}});value=reply.get_json()
                    assert reply.status_code==200 and value['success'] and reply.headers['Cache-Control']=='no-store',value
                    snapshot(value['data']['snapshot'],expected)
                    proof['application'].append({'use_pure':pure,'all_27_fields':True,'generation_bound_inspection':True,'authenticated_ddn_exact':True,
                        'applier_policy_and_status_exact':True})
                reader_password=secrets.token_urlsafe(24);q.execute('CREATE USER `channel_reader`@`%` IDENTIFIED BY %s',(reader_password,))
                q.execute('GRANT SELECT ON sr_osc.* TO `channel_reader`@`%`')
                for pure in (True,False):
                    client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=lambda *_:SecretLease(reader_password.encode())),SimpleNamespace())
                    handle=client._connect({'route':{**route,'database':'sr_osc','use_pure':pure,'user':'channel_reader',
                        'credential_reference_id':'owned-reader','principal_reference':'owner','autocommit':True}})
                    try:
                        captured=capture(handle);observed=next(row for row in captured['observations'] if row['section']=='replication-channels')
                        assert not observed['available'] and observed['error_code']==1142
                        rows=_resources(handle,{'route':{'database':'sr_osc'}},MYSQL_PROFILE)
                        assert not any(row['resource_kind']=='replication-channel' for row in rows)
                        coverage=next(row for row in rows if row['resource_kind']=='server')['native']['catalog_coverage']
                        assert coverage['state']=='partial' and not coverage['complete_native_inventory']
                        proof['restricted'].append({'use_pure':pure,'native_denial':1142,'partial_coverage_explicit':True})
                    finally:client._forget_and_close(handle);client.close()
                for mode, tables in [('receiver-only',['replication_connection_configuration']),
                    ('applier-only',['replication_applier_configuration','replication_applier_status']),
                    ('status-only',['replication_applier_status'])]:
                    q.execute('REVOKE ALL PRIVILEGES, GRANT OPTION FROM `channel_reader`@`%`')
                    q.execute('GRANT SELECT ON sr_osc.* TO `channel_reader`@`%`')
                    for table in tables:q.execute('GRANT SELECT ON performance_schema.'+table+' TO `channel_reader`@`%`')
                    for pure in (True,False):
                        client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=lambda *_:SecretLease(reader_password.encode())),SimpleNamespace())
                        handle=client._connect({'route':{**route,'database':'sr_osc','use_pure':pure,'user':'channel_reader',
                            'credential_reference_id':'owned-reader','principal_reference':'owner','autocommit':True}})
                        try:
                            captured=capture(handle)
                            exported=build_export(captured['resources'],endpoint_id='owned',target_id='server:'+captured['server_uuid'],
                                generation=captured['generation'],engine='mysql')
                            parsed=read_catalog(json.dumps(exported['snapshot']),engine='mysql')
                            exchanged={row['native']['catalog_row']['channel_name']:row for row in parsed['rows'].values() if row['kind']=='replication-channel'}
                            rows=_resources(handle,{'route':{'database':'sr_osc'}},MYSQL_PROFILE)
                            actual={row['native']['channel_name']:row['native'] for row in rows if row['resource_kind']=='replication-channel'}
                            assert actual.keys()==exchanged.keys()==expected.keys()
                            for name,native in actual.items():
                                values=exchanged[name]['native']['catalog_row']
                                assert exchanged[name]['native']['section']=='replication-channels'
                                if mode=='receiver-only':
                                    desired={k:v for k,v in expected[name].items() if k!='applier_configuration'}
                                    assert values==desired and {k:native[k] for k in desired}==desired
                                    assert 'applier_configuration' not in native and 'applier' not in native
                                else:
                                    assert 'host' not in native and 'host' not in values
                                    assert native['applier']==exchanged[name]['native']['applier']==expected_status['applier'][name]
                                    if mode=='applier-only':assert native['applier_configuration']==values['applier_configuration']==expected[name]['applier_configuration']
                                    else:assert 'applier_configuration' not in values and 'applier_configuration' not in native
                            denied={row['section'] for row in captured['observations'] if row.get('error_code')==1142}
                            assert ('replication-applier_configuration' in denied) is (mode!='applier-only')
                            assert ('replication-channels' in denied) is (mode!='receiver-only')
                            proof['mixed_grants'].append({'mode':mode,'use_pure':pure,'independent_native_grants_preserved':True,
                                'single_canonical_channel_identity':True,'unobserved_fields_not_fabricated':True,'ddn_exact':True})
                        finally:client._forget_and_close(handle);client.close()
            finally:q.close();oracle.close()
        with server(output/'disabled',performance_schema=False) as (route,_name,fixture):
            owned.append(fixture);oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;q=oracle.cursor()
            try:
                expected=configure(q)
                for pure in (True,False):
                    client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),SimpleNamespace())
                    handle=client._connect({'route':{**route,'use_pure':pure,'autocommit':True}})
                    try:
                        explorer(_resources(handle,{'route':{}},MYSQL_PROFILE),expected);ddn(capture(handle),expected)
                        proof['disabled'].append({'use_pure':pure,'perpetual_native_table_available':True,'all_27_fields_and_ddn_exact':True,
                            'all_applier_policy_and_status_fields_exact':True})
                    finally:client._forget_and_close(handle);client.close()
            finally:q.close();oracle.close()
        proof['complete']=True
    finally:
        proof['owned_servers_stopped']=bool(owned) and all(item['owned_server_stopped'] for item in owned)
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    print(json.dumps({'complete':qualify(parser.parse_args().output)['complete']}))
