"""Native GLOB callbacks, sticky attachment and baseline diff semantics."""
import os
from types import SimpleNamespace
import pytest
from test_sqlite_session_api import native
from pgadmin.cdeadmin.providers.sqlite.session_api import SessionAPI,SessionAPIError
from pgadmin.cdeadmin.providers.sqlite.session_actions import action


def counts(api,key,path,tables):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:api.export(key,'changeset',fd)
    finally:os.close(fd)
    result={}
    for table in tables:
        with path.open('rb') as stream:result[table]=api.call('inspect_selection',stream.fileno(),-1,table)['native_selected_record_count']
    return result


def test_native_glob_case_unicode_future_tables_and_sticky_explicit_attachment(native):
    connection,library,tmp=native;api=SessionAPI(connection,library);key=api.open('main')
    assert api.program['native_session_revision']>=5
    api.table_filter(key,'keep*雪')
    connection.execute('BEGIN')
    for table in ('keep雪','keepLater雪','KeepCase雪','skip雪'):
        connection.execute('CREATE TABLE "'+table+'"(id INTEGER PRIMARY KEY,body TEXT)');connection.execute('INSERT INTO "'+table+'" VALUES(1,\'one\')')
    assert counts(api,key,tmp/'one',('keep雪','keepLater雪','KeepCase雪','skip雪'))=={'keep雪':'1','keepLater雪':'1','KeepCase雪':'0','skip雪':'0'}
    api.table_filter(key,'skip*')
    connection.execute('UPDATE "keep雪" SET body=\'two\'');connection.execute('UPDATE "skip雪" SET body=\'two\'')
    api.attach(key,'KeepCase雪');connection.execute('UPDATE "KeepCase雪" SET body=\'two\'')
    assert counts(api,key,tmp/'two',('keep雪','keepLater雪','KeepCase雪','skip雪'))=={'keep雪':'1','keepLater雪':'1','KeepCase雪':'1','skip雪':'1'}
    api.table_filter(key,None);connection.execute('CREATE TABLE all_future(id INTEGER PRIMARY KEY)');connection.execute('INSERT INTO all_future VALUES(1)')
    assert counts(api,key,tmp/'three',('all_future',))=={'all_future':'1'}
    assert connection.in_transaction and api.status(key)['table_filter']=={'pattern':None,'exclude':False,'automatic_attachment':True}


def test_native_exclusion_is_per_capture_and_invalid_change_preserves_prior_filter(native):
    connection,library,tmp=native;api=SessionAPI(connection,library);one=api.open('main');two=api.open('main')
    api.table_filter(one,'skip*',True);api.table_filter(two,'skip*')
    with pytest.raises(SessionAPIError):api.table_filter(one,'bad\x00pattern')
    assert api.status(one)['table_filter']['exclude']
    for name in ('skip_one','kept'):
        connection.execute('CREATE TABLE '+name+'(id INTEGER PRIMARY KEY)');connection.execute('INSERT INTO '+name+' VALUES(1)')
    assert counts(api,one,tmp/'exclude',('skip_one','kept'))=={'skip_one':'0','kept':'1'}
    assert counts(api,two,tmp/'include',('skip_one','kept'))=={'skip_one':'1','kept':'0'}
    connection.close();connection.close()


def test_diff_implicitly_attaches_exact_table_and_preserves_both_databases(native):
    connection,library,tmp=native;client=SimpleNamespace(close=connection.close)
    connection.execute('ATTACH ? AS "baseline 雪"',(':memory:',))
    connection.executescript('CREATE TABLE "native\n雪"(id INTEGER PRIMARY KEY,body TEXT);CREATE TABLE "baseline 雪"."native\n雪"(id INTEGER PRIMARY KEY,body TEXT);INSERT INTO "baseline 雪"."native\n雪" VALUES(1,\'before\');INSERT INTO "native\n雪" VALUES(1,\'after\');')
    key=action(client,connection,{'operation':'open','database':'main'},library)['capture']['capture_id']
    connection.execute('BEGIN')
    result=action(client,connection,{'operation':'diff','capture_id':key,'source_database':'baseline 雪','table_name':'native\n雪'},library)
    assert result['transaction_open'] and not result['database_mutation'] and result['capture']['tables']==['native\n雪']
    assert not result['capture']['empty'] and connection.execute('SELECT body FROM "native\n雪"').fetchone()==('after',)
    assert connection.execute('SELECT body FROM "baseline 雪"."native\n雪"').fetchone()==('before',)
    assert counts(connection._cdeadmin_session_api,key,tmp/'diff',('native\n雪',))=={'native\n雪':'1'}
    result=action(client,connection,{'operation':'table_filter','capture_id':key,'pattern':'new*','exclude':True},library)
    assert result['capture']['table_filter']=={'pattern':'new*','exclude':True,'automatic_attachment':True} and connection.in_transaction
