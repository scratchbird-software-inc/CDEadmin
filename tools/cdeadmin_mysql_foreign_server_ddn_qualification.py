"""Native foreign-server DDN roundtrip, reviewed application and rediscovery."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'web'), str(ROOT/'tools')]


def qualify(output):
    import config  # noqa: F401
    from mysql_qualification_support import server, _root_connection
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE, MySQLPilotProvider, _create_client
    from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
    from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
    from pgadmin.cdeadmin.workspace.mysql_server_plan import plan
    from pgadmin.cdeadmin.workspace.mysql_server_apply import MySQLServerApplications
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Evidence belongs outside source')
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    proof = {'complete': False, 'history_testing': 'not run', 'full_product_complete': False,
        'checks': [], 'source_sha256': {}}
    for name in ['tools/cdeadmin_mysql_foreign_server_ddn_qualification.py',
            'web/pgadmin/cdeadmin/workspace/mysql_server_plan.py',
            'web/pgadmin/cdeadmin/providers/mysql_server_application.py',
            'web/pgadmin/cdeadmin/providers/mysql_family/foreign_servers.py',
            'web/pgadmin/cdeadmin/providers/mysql_family/mysql_server_catalog.py',
            'web/pgadmin/cdeadmin/providers/mysql_family/provider.py']:
        proof['source_sha256'][name] = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    try:
        with server(output/'fixture') as (route, _name, owned):
            observer = _root_connection('mysql', route['port']);observer.autocommit = True
            cursor = observer.cursor();name = 'DDN : . ` é'
            try:
                for pure in (True, False):
                    for mode in ('', 'NO_BACKSLASH_ESCAPES,ANSI_QUOTES'):
                        selected = {**route, 'use_pure': pure, 'sql_mode': mode}
                        permissions = SimpleNamespace(acquire_secret=None, require=lambda *_: None)
                        client = _create_client(MYSQL_PROFILE, permissions, None)
                        provider = MySQLPilotProvider(SimpleNamespace(endpoint_id='owned-native'), permissions, client)
                        directory = output/('pure' if pure else 'cext')/('strict' if mode else 'default');directory.mkdir(parents=True)
                        store = directory/'reviews.json';applications = MySQLServerApplications(store)
                        def model():
                            captured = provider.capture_server_catalog(selected)
                            exported = build_export(captured['resources'], endpoint_id='owned-native',
                                target_id='server:'+captured['server_uuid'], generation=captured['generation'],
                                include_system=True, refreshed=True, engine='mysql')
                            encoded = json.dumps(exported['snapshot'], ensure_ascii=False)
                            assert 'never-export-password' not in encoded
                            return read_catalog(encoded, engine='mysql')
                        def prepare(action, draft):
                            baseline = model();desired = deepcopy(baseline)
                            uuid = next(row['native']['server_uuid'] for row in baseline['rows'].values() if row['kind']=='server')
                            key = 'mysql-server:'+json.dumps([uuid,'foreign-servers',[name]],ensure_ascii=False,separators=(',',':'))
                            if key not in desired['rows']:
                                desired['rows'][key] = {'resource_id':key,'kind':'server-link','name':name,
                                    'system':'false','native':{'section':'foreign-servers','server_uuid':uuid,
                                        'system_object':False,'catalog_row':{'server_name':name,'wrapper':'mysql'}}}
                            desired['rows'][key]['native']['mysql_change'] = {
                                'action':action,'draft':draft,'confirmation':name}
                            preview = plan(baseline, desired, model());preview['endpoint_id']='owned-native'
                            assert preview['ready_for_review'],preview
                            return applications.review(preview, baseline, desired, 1, 'owned-server')
                        calls = []
                        def execute(record, operation):
                            calls.append(operation['resource_id'])
                            return provider.apply_server_operation(selected, record, operation)
                        def apply(receipt):
                            request = {'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True}
                            result = applications.apply(request,1,'owned-server',execute)
                            count = len(calls)
                            repeated = MySQLServerApplications(store).apply(request,1,'owned-server',execute)
                            assert repeated['state']==result['state'] and len(calls)==count
                            return result
                        def observed():
                            cursor.execute('SELECT Server_name,Host,Db,Username,Password,Port,Socket,Wrapper,Owner '
                                'FROM mysql.servers WHERE CAST(Server_name AS BINARY)=CAST(%s AS BINARY)',(name,))
                            return cursor.fetchone()
                        try:
                            draft = {'name':name,'wrapper':'mysql','include_host':True,'host':"host ' \\",
                                'include_database':True,'database':"db ' é \\",'include_username':True,'username':'remote-user',
                                'include_port':True,'port':'2147483647','include_socket':True,'socket':'socket',
                                'include_owner':True,'owner':"owner ' é \\"}
                            result = apply(prepare('create',draft));assert result['state']=='acknowledged' and result['outcome']['rediscovery_verified']
                            assert observed()==(name,draft['host'],draft['database'],draft['username'],'',2147483647,'socket','mysql',draft['owner'])
                            cursor.execute('ALTER SERVER `DDN : . `` é` OPTIONS (PASSWORD %s)',('never-export-password',))
                            stale = prepare('alter',{'include_host':True,'host':'must not overwrite'})
                            cursor.execute('ALTER SERVER `DDN : . `` é` OPTIONS (HOST %s)',('external change',))
                            refusal = apply(stale);assert refusal['state']=='not_applied'
                            assert refusal['statement_outcomes'][0]['outcome']['state']=='not_dispatched'
                            assert observed()[1]=='external change'
                            result = apply(prepare('alter',{'include_owner':True,'owner':'reviewed owner'}))
                            assert result['state']=='acknowledged' and result['outcome']['rediscovery_verified']
                            assert observed()==(name,'external change',draft['database'],draft['username'],'never-export-password',2147483647,'socket','mysql','reviewed owner')
                            result = apply(prepare('drop',{'if_exists':True}));assert result['state']=='acknowledged' and result['outcome']['rediscovery_verified'] and observed() is None
                            assert 'never-export-password' not in store.read_text() and client._connections==[]
                            proof['checks'].append({'use_pure':pure,'sql_mode':mode,
                                'paired_ddn_roundtrip_verified':True,'native_create_alter_drop_verified':True,
                                'all_attributes_and_omitted_credential_preserved':True,
                                'changed_baseline_refused_before_dispatch':True,
                                'durable_receipt_restart_does_not_redispatch':True})
                        finally:
                            client.close()
                proof['native_engine']=owned;proof['complete']=True
            finally:
                cursor.close();observer.close()
    finally:
        (output/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',required=True,type=Path)
    qualify(parser.parse_args().evidence)
