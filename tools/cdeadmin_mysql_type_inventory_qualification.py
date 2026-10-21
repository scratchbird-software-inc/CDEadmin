"""Native grammar and actual storage declarations for MySQL type spellings."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def declaration(name):
    if name in ('ENUM','SET'):return name+"('owned')"
    if name=='VECTOR':return name+'(3)'
    if not name.startswith('LONG') and any(word in {'VARCHAR','VARCHARACTER','NVARCHAR','VARBINARY','VARYING'} for word in name.split()):return name+'(16)'
    return name


def qualify(output,library,browser_binary=None,driver_binary=None):
    import config  # noqa: F401
    import os
    from mysql_qualification_support import server,_root_connection
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE,MYSQL_ADMINISTRATION,_create_client
    from pgadmin.cdeadmin.providers.mysql_family.mysql_parser import native
    from pgadmin.cdeadmin.providers.mysql_family.mysql_completion import complete
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Keep evidence outside source')
    output.mkdir(parents=True,exist_ok=False);library=Path(library).resolve(strict=True)
    os.environ['CDEADMIN_MYSQL_PARSER_LIBRARY']=str(library)
    paths=['tools/cdeadmin_mysql_type_inventory_qualification.py',
        'tools/reference_engine_demos/mysql_source_inventory.py','tools/reference_engine_demos/reconcile_mysql_source_inventory.py',
        'web/pgadmin/cdeadmin/providers/native_editor.py','web/pgadmin/cdeadmin/providers/mysql_family/mysql_dialect_9_7_0.json',
        'web/pgadmin/static/js/cdeadmin_ui/editors/nativeCompletion.js','tools/cdeadmin_mysql_family_editor_workspace_qualification.py',
        'web/pgadmin/static/js/cdeadmin_ui/editors/nativeScopes.js','web/pgadmin/cdeadmin/providers/relational_admin.py']
    proof={'complete':False,'interfaces':[],'history_testing':'not run','full_mysql_product_complete':False,
        'source_sha256':{path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in paths}}
    try:
        contract=json.loads((ROOT/paths[4]).read_text());names=[row['native_name'] for row in contract['inventories']['data_types']]
        statements=[{'source':'CREATE TABLE future_native_type (`v` '+declaration(name)+')','sql_mode':''} for name in names]
        parsed=native(library,statements)
        rejected=[name for name,item in zip(names,parsed['statements']) if not item['sql_syntax_valid']]
        proof['native_parser']={key:parsed[key] for key in ('parser_version','worker_sha256','library_sha256')}
        proof['native_parser'].update(accepted=len(names)-len(rejected),rejected=rejected)
        assert not rejected,rejected
        with server(output/'fixture') as (route,_name,owned):
            oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;query=oracle.cursor()
            try:
                query.execute('CREATE DATABASE sr_workspace')
                query.execute('CREATE TABLE sr_workspace.t(id INT PRIMARY KEY)')
                query.execute('CREATE TABLE sr_workspace.pending(id INT PRIMARY KEY)')
                for pure in (True,False):
                    client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),SimpleNamespace())
                    request={'route':{**route,'database':'sr_workspace','use_pure':pure}}
                    handle=client._connect(request);cursor=handle.cursor();cases=[]
                    try:
                        native_class=type(handle).__name__;assert native_class==('CharsetMySQLConnection' if pure else 'CharsetCMySQLConnection')
                        for index,name in enumerate(names):
                            table='sr_type_'+str(index)
                            column=MYSQL_ADMINISTRATION._column_definition({'name':'v','type':declaration(name)})
                            cursor.execute('CREATE TABLE `'+table+'` ('+column+')')
                            cursor.execute('SELECT COLUMN_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s',('sr_workspace',table,'v'))
                            observed=cursor.fetchone();assert observed and isinstance(observed[0],str)
                            cases.append({'native_name':name,'declaration':declaration(name),'native_column_type':observed[0]})
                            cursor.execute('DROP TABLE `'+table+'`')
                        for mode,expected in (('', 'double'),('REAL_AS_FLOAT','float')):
                            cursor.execute('SET SESSION sql_mode=%s',(mode,));cursor.execute('CREATE TABLE sr_real_mode(v REAL)')
                            cursor.execute("SELECT COLUMN_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='sr_workspace' AND TABLE_NAME='sr_real_mode'")
                            assert cursor.fetchone()==(expected,);cursor.execute('DROP TABLE sr_real_mode')
                    finally:cursor.close();client._forget_and_close(handle)
                    handle=client.open_session(request);work=handle.cursor()
                    try:
                        client.control_transaction(handle,'autocommit_off');work.execute('INSERT INTO pending VALUES(7)');work.execute('SAVEPOINT native_types_guard')
                        metadata=complete(client,handle)
                        types={row['display_name']:row for row in metadata['resources'] if row['resource_kind']=='type'}
                        assert set(names)<=set(types) and all(types[name].get('native_type_keyword') for name in names)
                        assert not {'int_type','spatial_type','BOOL_SYM'} & set(types)
                        work.execute('ROLLBACK TO SAVEPOINT native_types_guard');work.execute('ROLLBACK')
                        if not pure:(output/'mysql-native-type-fixture.json').write_text(json.dumps({'metadata':metadata,'cases':cases},indent=2)+'\n')
                        proof['interfaces'].append({'use_pure':pure,'native_connection_class':native_class,'native_declarations':cases,
                            'private_completion_types_observed':len(names),'pending_transaction_savepoint_preserved':True,'real_as_float_mode_observed':True})
                    finally:work.close();client._forget_and_close(handle);client.close()
                if browser_binary:
                    password='native-types-'+secrets.token_urlsafe(24);query.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                    proof['browser']=workspace(output,route,password,browser_binary,driver_binary)
                    query.execute("SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='sr_workspace' AND TABLE_NAME='future_native_type'")
                    assert query.fetchone()==(0,);proof['browser_future_table_not_created']=True
                proof['complete']=True
            finally:query.close();oracle.close()
        proof['owned_server_stopped']=owned['owned_server_stopped']
    finally:(output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def workspace(output,route,password,binary,driver_binary):
    import uuid
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    app=setup_application(output)
    from flask import url_for
    from pgadmin.model import db,User,ServerGroup,Server,EndpointDatabaseTarget
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    with app.test_request_context('/'):
        uid=User.query.first().id;group=ServerGroup.query.filter_by(user_id=uid).first()
        app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True,user_id=uid)
        item=Server(user_id=uid,servergroup_id=group.id,name='Owned native type inventory',host=route['host'],port=route['port'],username='root',maintenance_db='sr_workspace',save_password=0)
        item._cde_endpoint_registration=registration_profile('mysql-native')
        item._cde_endpoint_route_configuration={**route,'user':'root','database':'sr_workspace','use_pure':False,'credential_kinds':['database_password']}
        db.session.add(item);db.session.commit();sid=item.id;target=str(uuid.uuid4())
        db.session.add(EndpointDatabaseTarget(id=target,endpoint_id=item.endpoint_profile.id,display_name='sr_workspace',database='sr_workspace',configuration='{}',active=1));db.session.commit()
        verify=url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=sid)
    client=app.test_client()
    with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
    assert client.post(verify,json={'password':password}).get_json()['success']
    from cdeadmin_mysql_family_editor_workspace_qualification import browser
    return browser(app,output,'mysql',sid,binary,driver_binary,password,private_completion=True,native_types=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);parser.add_argument('--library',required=True)
    parser.add_argument('--browser-binary');parser.add_argument('--driver-binary')
    args=parser.parse_args();value=qualify(args.output,args.library,args.browser_binary,args.driver_binary)
    print(json.dumps({'complete':value['complete'],'interfaces':len(value['interfaces'])}))
