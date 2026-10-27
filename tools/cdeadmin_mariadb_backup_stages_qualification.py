"""Owned native backup locks, original-session transaction guards and release."""
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


def qualify(route, evidence, *, password=None):
    import config  # noqa: F401
    import mariadb
    from tools.mysql_driver_gate_support import provider_access
    from pgadmin.cdeadmin.providers.mysql_family.provider import MARIADB_PROFILE, MariaDBPilotProvider, _create_client
    from pgadmin.cdeadmin.sdk import RelationalClientError
    evidence.mkdir(parents=True, mode=0o700, exist_ok=False)
    proof = {'complete':False,'native_version':'12.2.2','full_product_complete':False,
        'history_testing':'not run','checks':[],'source_sha256':{}}
    for name in ['tools/cdeadmin_mariadb_backup_stages_qualification.py',
            'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_backup_stages.py',
            'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_execution.py',
            'web/pgadmin/cdeadmin/providers/mysql_family/provider.py',
            'web/pgadmin/cdeadmin/data_studio/studio.py', 'web/pgadmin/cdeadmin/workspace/service.py',
            'web/pgadmin/browser/server_groups/servers/__init__.py',
            'web/pgadmin/static/js/Dialogs/MariaDBBackupStages.jsx',
            'web/pgadmin/static/js/Dialogs/ProviderWorkspaceContent.jsx']:
        proof['source_sha256'][name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    owner=mariadb.connect(**route,**({'password':password} if password else {}),autocommit=True)
    cursor=owner.cursor();database='owned_backup_'+secrets.token_hex(8)
    clients=[];made=False;low_user=None
    try:
        cursor.execute('CREATE DATABASE `'+database+'`');made=True
        cursor.execute('CREATE TABLE `'+database+'`.pending(id INT)')
        cursor.execute('CREATE TABLE `'+database+'`.`backup . `` é`(id INT)')
        native_route,permissions=provider_access({**route,'database':database},password)
        def opened(pool=False):
            permissions.require=lambda *_: None
            context=SimpleNamespace(endpoint_id='owned-backup',session_namespace=secrets.token_hex(8),pool_namespace=secrets.token_hex(8))
            client=_create_client(MARIADB_PROFILE,permissions,context);clients.append(client)
            provider=MariaDBPilotProvider(context,permissions,client)
            selected={**native_route,**({'pool_name':'backup-lifetime','pool_size':1,'pool_reset_connection':False} if pool else {})}
            sid=provider.open_session({'route':selected})['session_id'];handle=provider._sessions[sid].handle
            def call(operation,**fields):
                return provider.backup_stage_action({'session_id':sid,'language_profile':'mariadb-sql',
                    'operation':operation,**fields})
            def finish(record):
                deadline=time.monotonic()+30
                while record['state']=='executing':
                    assert time.monotonic()<deadline,record
                    time.sleep(.01);record=call('receipt',review_id=record['review_id'])
                return record
            def stage(value,wait=5):
                record=call('review',draft={'stage':value,'lock_wait_seconds':wait})
                request={'review_id':record['review_id'],'review_digest':record['review_digest'],
                    'confirmation':value,'confirmed':True}
                result=finish(call('apply',**request));assert call('apply',**request)==result
                return result
            return client,provider,sid,handle,call,finish,stage
        client,provider,sid,handle,call,finish,stage=opened()
        current=handle.cursor();current.execute('INSERT INTO pending VALUES (42)');current.close()
        try:
            call('review',draft={'stage':'START','lock_wait_seconds':5})
        except RelationalClientError as error:
            assert 'implicitly commits' in str(error)
        else:
            raise AssertionError('Backup stages accepted a caller-owned active transaction')
        cursor.execute('SELECT * FROM `'+database+'`.pending');assert cursor.fetchall()==[]
        client.control_transaction(handle,'rollback')
        for mode in ('STRICT_TRANS_TABLES','ORACLE'):
            current=handle.cursor();current.execute("SET sql_mode='"+mode+"'");current.close()
            for value in ('START','FLUSH','BLOCK_DDL','BLOCK_COMMIT','END'):
                result=stage(value);assert result['state']=='acknowledged',result
                assert result['native_dispatched'] and result['native_acknowledged']
                if value=='BLOCK_DDL':
                    cursor.execute('SET SESSION lock_wait_timeout=0')
                    try:cursor.execute('ALTER TABLE `'+database+'`.pending ADD COLUMN blocked_probe INT')
                    except mariadb.Error as error:assert error.errno==1205,error
                    else:raise AssertionError('Native BLOCK_DDL did not block independent ALTER TABLE')
            for action in ('lock','unlock'):
                draft={'action':action,'lock_wait_seconds':5,**({'database':database,'table':'backup . ` é'} if action=='lock' else {})}
                reviewed=call('review',draft=draft)
                result=finish(call('apply',review_id=reviewed['review_id'],review_digest=reviewed['review_digest'],
                    confirmation=action.upper(),confirmed=True))
                assert result['state']=='acknowledged',result
                if action=='lock':
                    try:cursor.execute('ALTER TABLE `'+database+'`.`backup . `` é` ADD COLUMN table_blocked_probe INT')
                    except mariadb.Error as error:assert error.errno==1205,error
                    else:raise AssertionError('Native BACKUP LOCK did not block independent ALTER TABLE')
            proof['checks'].append({'sql_mode':mode,'all_five_native_stages':True,'independent_ddl_block_observed':True,'no_replay':True})
        assert stage('START')['state']=='acknowledged'
        assert stage('BLOCK_COMMIT')['state']=='acknowledged'  # Native forward jump.
        assert stage('END')['state']=='acknowledged'
        # A competing backup START is cancelled through the owning connector's
        # independently authenticated and peer-verified KILL QUERY channel.
        assert stage('START')['state']=='acknowledged'
        other_client,other_provider,other_sid,other_handle,other_call,other_finish,_other_stage=opened()
        reviewed=other_call('review',draft={'stage':'START','lock_wait_seconds':30})
        running=other_call('apply',review_id=reviewed['review_id'],review_digest=reviewed['review_digest'],confirmation='START',confirmed=True)
        token=other_client._backup_stage_reviews[reviewed['review_id']]['token']
        deadline=time.monotonic()+10
        while not token.native_dispatched:
            assert time.monotonic()<deadline
            time.sleep(.01)
        cancelled=other_finish(other_call('cancel',review_id=reviewed['review_id']))
        assert cancelled['state']=='cancelled' and cancelled['cancellation_requested'],cancelled
        assert stage('END')['state']=='acknowledged'
        other_provider.close_session({'session_id':other_sid})
        proof['native_wait_cancellation_and_forward_stage_jump']=True
        # Closing a pooled session must release backup locks even with native
        # pool reset disabled. It must not leave that connection for a borrower.
        pooled,pooled_provider,pooled_sid,_pooled_handle,_pooled_call,_pooled_finish,pooled_stage=opened(True)
        assert pooled_stage('START')['state']=='acknowledged'
        assert pooled_stage('BLOCK_DDL')['state']=='acknowledged'
        closed=pooled_provider.close_session({'session_id':pooled_sid})
        deadline=time.monotonic()+10
        while True:
            try:
                cursor.execute('ALTER TABLE `'+database+'`.pending ADD COLUMN released_probe INT')
                break
            except mariadb.Error as error:
                if error.errno!=1205 or time.monotonic()>deadline:raise
                time.sleep(.03)
        proof['pooled_close_releases_native_backup_locks_without_pool_reset']=True
        low_user='owned_backup_denied_'+secrets.token_hex(6);low_password=secrets.token_urlsafe(24)
        cursor.execute('CREATE USER `'+low_user+"`@'%' IDENTIFIED BY ?",[low_password])
        cursor.execute('GRANT SELECT ON `'+database+'`.* TO `'+low_user+"`@'%'")
        prior_route,prior_permissions=native_route,permissions
        native_route,permissions=provider_access({**route,'database':database,'user':low_user},low_password)
        denied_client,denied_provider,denied_sid,_denied_handle,_denied_call,_denied_finish,denied_stage=opened()
        native_route,permissions=prior_route,prior_permissions
        denied=denied_stage('START')
        assert denied['state']=='refused' and denied['error']['errno']==1227,denied
        denied_provider.close_session({'session_id':denied_sid})
        proof['native_reload_privilege_denial']=True
        provider.close_session({'session_id':sid})
        proof['active_transaction_preserved_until_explicit_rollback']=True
        proof['complete']=True
    finally:
        for client in reversed(clients):client.close()
        if low_user:cursor.execute('DROP USER IF EXISTS `'+low_user+"`@'%'")
        if made:cursor.execute('DROP DATABASE IF EXISTS `'+database+'`')
        cursor.close();owner.close()
        (evidence/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    import config  # noqa: F401
    from tools.cdeadmin_mariadb_driver_gate import run
    parser=argparse.ArgumentParser();parser.add_argument('--image',default='mariadb:12.2.2')
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=run(args.image,args.output,qualify)
    raise SystemExit(0 if result['complete'] else 1)
