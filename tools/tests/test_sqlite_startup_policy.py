"""Native host startup admission and reviewed future-policy publication."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import test_cdeadmin_relational_providers  # noqa: F401
import sqlite_startup as codec
from pgadmin.cdeadmin.providers.sqlite.driver import SQLiteConnection
from pgadmin.cdeadmin.providers.sqlite.startup_policy import action
from pgadmin.cdeadmin.sdk import RelationalClientError
from ui_descriptor_roundtrip import engine_operations, operation_draft

pytestmark=pytest.mark.skipif(not os.environ.get('CDEADMIN_SQLITE_CONFIG_LIBRARY'),reason='Native configuration helper not selected')


def test_publication_preserves_live_original_transaction_temp_and_one_use(tmp_path):
    source=SQLiteConnection(':memory:',cached_statements=0)
    directory=tmp_path/'temp 雪';directory.mkdir()
    policy=tmp_path/'accepted.json'
    common=dict(native_work_revision=7,host_authorized=True,filename=str(policy),
                filesystem_root=str(tmp_path),principal='host-admin',endpoint_id='owned')
    request={'pragma':'temp_store_directory','value_mode':'DIRECTORY','directory':str(directory)}
    try:
        source.executescript('CREATE TEMP TABLE kept(value);INSERT INTO kept VALUES(7);SAVEPOINT caller')
        calls=[];source.set_trace_callback(calls.append)
        with pytest.raises(RelationalClientError,match='Administrator'):
            action(source,{'operation':'review',**request},**{**common,'host_authorized':False})
        review=action(source,{'operation':'review',**request},**common)
        values={**request,'review_id':review['review_id'],'expected_policy_revision':review['expected_policy_revision'],
                'confirmed':True,'process_startup_change_confirmed':True}
        values.pop('pragma')
        draft=operation_draft(engine_operations('sqlite')['set_connection_pragma_temp_store_directory@database'],values)
        with pytest.raises(RelationalClientError,match='changed'):
            action(source,{'operation':'set_connection_pragma','pragma':'temp_store_directory',**draft},**{**common,'native_work_revision':8})
        result=action(source,{'operation':'set_connection_pragma','pragma':'temp_store_directory',**draft},**common)
        assert result['outcome']=='staged_for_next_process_startup' and not result['native_applied']
        assert result['source_sql_commands_sent']==0 and calls==[]
        assert source.in_transaction and source.execute('SELECT * FROM kept').fetchall()==[(7,)]
        accepted,revision=codec.read_policy(policy)
        assert revision==result['policy_revision'] and accepted['settings']['temp_store_directory']['directory']==str(directory)
        with pytest.raises(RelationalClientError,match='changed'):
            action(source,{'operation':'set_connection_pragma','pragma':'temp_store_directory',**draft},**common)
        source.execute('ROLLBACK TO caller');source.execute('RELEASE caller')
        assert codec.read_policy(policy)[1]==revision
    finally:source.close()


def test_directory_identity_and_authority_are_revalidated(tmp_path):
    directory=tmp_path/'owned';directory.mkdir()
    setting=codec.directory_setting('DIRECTORY',str(directory),str(tmp_path))
    directory.rename(tmp_path/'moved');directory.mkdir()
    with pytest.raises(ValueError,match='changed'):codec.validate_setting(setting,observe_filesystem=True)
    with pytest.raises(ValueError,match='outside'):codec.directory_setting('DIRECTORY',str(tmp_path.parent),str(tmp_path))
    with pytest.raises(ValueError):codec.directory_setting('DEFAULT',str(directory),str(tmp_path))


@pytest.mark.parametrize('scenario',['success','initialized','threaded','drift','missing-component'])
def test_native_startup_in_its_own_fresh_process(tmp_path,scenario):
    code=r'''
from pathlib import Path
from types import SimpleNamespace
import json,sys,threading
import sqlite_startup as startup
root=Path(sys.argv[1]);scenario=sys.argv[2];directory=root/'temp 雪';directory.mkdir()
policy=root/'startup.json';setting=startup.directory_setting('DIRECTORY',str(directory),str(root))
startup.publish_policy_file(policy,json.dumps({'schema':startup.SCHEMA,'settings':{'temp_store_directory':setting}}).encode())
config=SimpleNamespace(DATA_DIR=str(root),CDEADMIN_SQLITE_STARTUP_POLICY=str(policy),CDEADMIN_SQLITE_CONFIG_LIBRARY=sys.argv[3])
thread=None;event=threading.Event();initialized=None
if scenario=='initialized':
 import sqlite3
 initialized=sqlite3.connect(':memory:')
if scenario=='threaded':
 thread=threading.Thread(target=event.wait);thread.start()
if scenario=='drift':directory.rename(root/'moved');directory.mkdir()
if scenario=='missing-component':config.CDEADMIN_SQLITE_CONFIG_LIBRARY=str(root/'absent.so')
try:
 if scenario=='success':
  receipt=startup.apply_configured_policy(config)
  assert receipt['complete'] and receipt['native_applied'] and receipt['interpreter_library_instance_attested']
  assert receipt['native']['runtime_was_uninitialized'] and receipt['native']['native_global_writes_attempted']==1
  import sqlite3
  with sqlite3.connect(':memory:')as observed:
   assert observed.execute('PRAGMA temp_store_directory').fetchone()==(str(directory),)
  assert startup.apply_configured_policy(config)==receipt
 else:
  try:startup.apply_configured_policy(config)
  except RuntimeError:pass
  else:raise AssertionError('Unsafe startup was admitted')
  receipt=json.loads(policy.with_suffix('.json.receipt.json').read_text())
  assert not receipt['complete'] and not receipt['native_applied']
  assert not receipt['application_database_opened_by_startup_workflow']
  if scenario in ('initialized','threaded'):
   assert receipt['native']['native_global_writes_attempted']==0
  try:startup.apply_configured_policy(config)
  except RuntimeError as error:assert 'fresh process'in str(error)
  else:raise AssertionError('Failed startup was replayed')
 print(json.dumps(receipt))
finally:
 event.set()
 if thread:thread.join()
 if initialized:initialized.close()
'''
    result=subprocess.run([sys.executable,'-B','-c',code,str(tmp_path),scenario,os.environ['CDEADMIN_SQLITE_CONFIG_LIBRARY']],
                          env=dict(os.environ),text=True,capture_output=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr


def test_unsupported_native_lock_proxy_refuses_without_finalizing_work(tmp_path):
    from pgadmin.cdeadmin.providers.sqlite.lock_proxy import action as proxy
    source=SQLiteConnection(str(tmp_path/'owned.db'),cached_statements=0)
    try:
        names={row[0]for row in source.execute('PRAGMA pragma_list')}
        if 'lock_proxy_file'in names:pytest.skip('Platform team must qualify native locking style')
        source.executescript('CREATE TABLE owned(value);SAVEPOINT caller;INSERT INTO owned VALUES(7)')
        with pytest.raises(RelationalClientError,match='does not offer'):
            proxy(source,{'operation':'review','pragma':'lock_proxy_file','schema':'main','value_mode':'AUTO'},
                  native_work_revision=0,filesystem_root=str(tmp_path))
        assert source.in_transaction and source.execute('SELECT * FROM owned').fetchall()==[(7,)]
        source.execute('ROLLBACK TO caller');source.execute('RELEASE caller')
    finally:source.close()


def test_publication_failure_consumes_review_and_reports_uncertainty(tmp_path,monkeypatch):
    source=SQLiteConnection(':memory:',cached_statements=0)
    policy=tmp_path/'accepted.json'
    common=dict(native_work_revision=0,host_authorized=True,filename=str(policy),
                filesystem_root=str(tmp_path),principal='host-admin',endpoint_id='owned')
    try:
        review=action(source,{'operation':'review','pragma':'temp_store_directory','value_mode':'DEFAULT'},**common)
        request={'operation':'set_connection_pragma','pragma':'temp_store_directory','value_mode':'DEFAULT',
                 'review_id':review['review_id'],'expected_policy_revision':review['expected_policy_revision'],
                 'confirmed':True,'process_startup_change_confirmed':True}
        original=codec.publish_policy_file
        def unconfirmed(path,data):
            original(path,data)
            raise OSError('Injected failure after publication')
        monkeypatch.setattr(codec,'publish_policy_file',unconfirmed)
        with pytest.raises(RelationalClientError)as error:action(source,request,**common)
        assert error.value.configuration_outcome=='unknown_outcome'
        assert codec.read_policy(policy)[0]['settings']['temp_store_directory']=={'mode':'DEFAULT'}
        with pytest.raises(RelationalClientError,match='changed'):action(source,request,**common)
    finally:source.close()
