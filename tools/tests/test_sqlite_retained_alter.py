"""Real SQLite3.53 ALTER effects under original namespace/transaction ownership."""
from copy import deepcopy
import sqlite3

import pytest
from test_sqlite_retained_ddl import owned  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.declarations import quote
from pgadmin.cdeadmin.providers.sqlite.provider import _resource_id
from pgadmin.cdeadmin.workspace import sqlite_retained_schema as retained
from pgadmin.cdeadmin.workspace import sqlite_retained_alter as alter


def prepare_owned(client,handle):
    for namespace in ('main','temp','team.雪'):
        name=quote(namespace)+'.native_alter'
        handle.execute('CREATE TABLE '+name+'(id INTEGER,optional TEXT,gone INTEGER,nn TEXT NOT NULL DEFAULT \'x\',CONSTRAINT positive CHECK(id>0))')
        handle.execute('INSERT INTO '+name+'(id,optional,gone) VALUES(7,\'pending\',8)')
    handle.execute('SAVEPOINT before_alter')
    return retained.observe(client,handle,'endpoint','native-session')


def review(client,handle,baseline,changes):
    desired=alter.generate(client,handle,baseline,'endpoint','native-session',changes)[0]
    preview=retained.plan(client,handle,baseline,desired,retained.observe(client,handle,'endpoint','native-session'),
        'endpoint','native-session',alterations=changes)
    return {'plan':preview,'baseline':baseline,'desired':desired,'native_context':retained.context(handle,12)}


@pytest.mark.parametrize('namespace',['main','temp','team.雪'])
@pytest.mark.parametrize('action',['rename-table','rename-column','drop-column','drop-constraint','drop-not-null','set-not-null','add-check'])
def test_all_native_alter_forms_preserve_original_rows_namespace_and_savepoint(owned,namespace,action):
    client,handle,*_=owned
    baseline=prepare_owned(client,handle)
    identity=_resource_id('table',[namespace],'native_alter')
    arguments={'rename-table':{'name':'renamed 雪'},'rename-column':{'column':'optional','name':'renamed:雪'},
        'drop-column':{'column':'gone'},'drop-constraint':{'name':'positive'},'drop-not-null':{'column':'nn'},
        'set-not-null':{'column':'optional','conflict':'ABORT'},
        'add-check':{'expression':'id < 10','name':'extra:雪','conflict':'FAIL'}}
    changes=[{'action':action,'resource_id':identity,**arguments[action]}]
    original=handle.execute('SELECT sql FROM '+quote(namespace)+'.sqlite_schema WHERE name=\'native_alter\'').fetchone()[0]
    record=review(client,handle,baseline,changes)
    assert handle.execute('SELECT sql FROM '+quote(namespace)+'.sqlite_schema WHERE name=\'native_alter\'').fetchone()[0]==original
    result=retained.apply(client,handle,record,'endpoint','native-session',12)
    assert result['state']=='applied_pending_caller_transaction' and result['rediscovery_verified'],result
    name='renamed 雪' if action=='rename-table' else 'native_alter'
    table=quote(namespace)+'.'+quote(name)
    expected=(1,7,'pending','x') if action=='drop-column' else (1,7,'pending',8,'x')
    assert handle.execute('SELECT rowid,* FROM '+table).fetchall()==[expected]
    columns={row[1]:row for row in handle.execute('PRAGMA '+quote(namespace)+'.table_xinfo('+quote(name)+')')}
    if action=='rename-column':assert 'renamed:雪' in columns and 'optional' not in columns
    if action=='drop-not-null':assert columns['nn'][3]==0
    if action=='set-not-null':assert columns['optional'][3]==1
    if action=='drop-constraint':
        handle.execute('INSERT INTO '+table+'(id) VALUES(-1)')
    if action=='add-check':
        with pytest.raises(sqlite3.IntegrityError):handle.execute('INSERT INTO '+table+'(id) VALUES(20)')
    for other in {'main','temp','team.雪'}-{namespace}:
        assert handle.execute('SELECT rowid,* FROM '+quote(other)+'.native_alter').fetchall()==[(1,7,'pending',8,'x')]
    handle.execute('ROLLBACK TO before_alter');handle.execute('RELEASE before_alter')
    assert handle.in_transaction and handle.execute('SELECT * FROM main.owned').fetchall()==[(93,)]
    assert handle.execute('SELECT sql FROM '+quote(namespace)+'.sqlite_schema WHERE name=\'native_alter\'').fetchone()[0]==original
    assert not client._uncertain


@pytest.mark.parametrize('action',['set-not-null','add-check'])
def test_native_existing_data_refusal_rolls_back_earlier_alter_and_preserves_caller_work(owned,action):
    client,handle,*_=owned
    baseline=prepare_owned(client,handle)
    handle.execute('INSERT INTO main.native_alter(id,optional,gone) VALUES(17,\'bad\',NULL)')
    baseline=retained.observe(client,handle,'endpoint','native-session')
    identity=_resource_id('table',['main'],'native_alter')
    changes=[{'action':'rename-column','resource_id':identity,'column':'optional','name':'payload'},
        {'action':action,'resource_id':identity,**({'column':'gone'} if action=='set-not-null' else {'expression':'id < 10','name':'bounded'})}]
    record=review(client,handle,baseline,changes)
    result=retained.apply(client,handle,record,'endpoint','native-session',12)
    assert result['state']=='rolled_back_to_savepoint' and result['completed_statements']==1,result
    assert 'constraint failed' in result['native_error']
    assert handle.execute('SELECT id,optional,gone FROM main.native_alter ORDER BY id').fetchall()==[(7,'pending',8),(17,'bad',None)]
    assert handle.execute('SELECT * FROM main.owned').fetchall()==[(93,)] and not client._uncertain
    handle.execute('ROLLBACK TO before_alter');handle.execute('RELEASE before_alter')


def test_ordered_table_and_column_rename_rewrites_native_view_trigger_and_foreign_key(owned):
    client,handle,*_=owned
    baseline=prepare_owned(client,handle)
    handle.execute('ALTER TABLE "team.雪".native_alter RENAME TO dependency_owner')
    handle.execute('CREATE VIEW "team.雪".dependent AS SELECT optional FROM dependency_owner')
    handle.execute('CREATE TRIGGER "team.雪".dependent_trigger AFTER UPDATE OF optional ON dependency_owner BEGIN SELECT NEW.optional; END')
    handle.execute('CREATE UNIQUE INDEX "team.雪".owner_key ON dependency_owner(optional)')
    handle.execute('CREATE TABLE "team.雪".child(owner TEXT REFERENCES dependency_owner(optional))')
    handle.execute('INSERT INTO "team.雪".child VALUES(\'pending\')')
    baseline=retained.observe(client,handle,'endpoint','native-session')
    identity=_resource_id('table',['team.雪'],'dependency_owner')
    changes=[{'action':'rename-table','resource_id':identity,'name':'renamed'},
        {'action':'rename-column','resource_id':identity,'column':'optional','name':'payload'}]
    record=review(client,handle,baseline,changes)
    result=retained.apply(client,handle,record,'endpoint','native-session',12)
    assert result['state']=='applied_pending_caller_transaction',result
    assert handle.execute('SELECT * FROM "team.雪".dependent').fetchall()==[('pending',)]
    handle.execute('UPDATE "team.雪".renamed SET payload=\'native trigger\'')
    assert handle.execute('SELECT payload FROM "team.雪".renamed').fetchone()==('native trigger',)
    assert 'payload' in handle.execute('SELECT sql FROM "team.雪".sqlite_schema WHERE name=\'dependent_trigger\'').fetchone()[0]
    foreign=handle.execute('PRAGMA "team.雪".foreign_key_list(child)').fetchone()
    assert foreign[2]=='renamed' and foreign[4]=='payload'
    assert handle.execute('SELECT * FROM "team.雪".child').fetchall()==[('pending',)]


def test_pinned_native_trigger_shadowing_refusal_does_not_mutate_original_state(owned):
    client,handle,*_=owned
    baseline=prepare_owned(client,handle)
    handle.execute('CREATE TRIGGER "team.雪".shadowed_trigger AFTER UPDATE OF optional ON native_alter BEGIN SELECT NEW.optional; END')
    baseline=retained.observe(client,handle,'endpoint','native-session')
    with pytest.raises(sqlite3.OperationalError,match='error in trigger shadowed_trigger after rename'):
        review(client,handle,baseline,[{'action':'rename-table','resource_id':_resource_id('table',['team.雪'],'native_alter'),'name':'renamed'}])
    assert handle.execute('SELECT optional FROM "team.雪".native_alter').fetchall()==[('pending',)]
    assert handle.execute('SELECT * FROM main.owned').fetchall()==[(93,)]
    assert not client._uncertain


def test_pinned_native_quoted_constraint_lookup_refusal_preserves_original_state(owned):
    client,handle,*_=owned
    handle.execute('CREATE TABLE main.quoted_constraint(id INTEGER,CONSTRAINT "name with spaces" CHECK(id>0))')
    handle.execute('INSERT INTO main.quoted_constraint VALUES(7)')
    baseline=retained.observe(client,handle,'endpoint','native-session')
    with pytest.raises(ValueError,match='exact raw name as one identifier token'):
        review(client,handle,baseline,[{'action':'drop-constraint','resource_id':_resource_id('table',['main'],'quoted_constraint'),'name':'name with spaces'}])
    assert handle.execute('SELECT * FROM main.quoted_constraint').fetchall()==[(7,)]
    with pytest.raises(sqlite3.IntegrityError):handle.execute('INSERT INTO main.quoted_constraint VALUES(-1)')
    assert handle.execute('SELECT * FROM main.owned').fetchall()==[(93,)]


def test_native_constraint_quote_characters_select_the_exact_literal_identity(owned):
    client,handle,*_=owned
    handle.execute('CREATE TABLE main.literal_constraints(id INTEGER,CONSTRAINT positive CHECK(id>0),CONSTRAINT """positive""" CHECK(id<10))')
    handle.execute('INSERT INTO main.literal_constraints VALUES(7)')
    baseline=retained.observe(client,handle,'endpoint','native-session')
    changes=[{'action':'drop-constraint','resource_id':_resource_id('table',['main'],'literal_constraints'),'name':'"positive"'}]
    record=review(client,handle,baseline,changes)
    assert record['plan']['operations'][0]['source'].endswith('DROP CONSTRAINT "positive"')
    result=retained.apply(client,handle,record,'endpoint','native-session',12)
    assert result['state']=='applied_pending_caller_transaction',result
    handle.execute('INSERT INTO main.literal_constraints VALUES(20)')
    with pytest.raises(sqlite3.IntegrityError):handle.execute('INSERT INTO main.literal_constraints VALUES(-1)')
    assert handle.execute('SELECT * FROM main.literal_constraints').fetchall()==[(7,),(20,)]
    assert handle.execute('SELECT * FROM main.owned').fetchall()==[(93,)]


def test_new_column_authorization_argument_is_preserved_on_original_policy_refusal(owned):
    client,handle,*_=owned
    baseline=prepare_owned(client,handle);seen=[]
    def policy(code,first,second,database,context):
        if code==sqlite3.SQLITE_ALTER_TABLE:
            seen.append((first,second,database))
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    handle.set_authorizer(policy)
    change={'action':'drop-not-null','resource_id':_resource_id('table',['temp'],'native_alter'),'column':'nn'}
    with pytest.raises(sqlite3.DatabaseError):review(client,handle,baseline,[change])
    assert seen==[('temp','native_alter','nn')]
    assert handle._cdeadmin_authorizer is policy
    assert handle.execute('PRAGMA temp.table_info(native_alter)').fetchall()[3][3]==1
    assert handle.execute('SELECT * FROM main.owned').fetchall()==[(93,)]


def test_native_external_content_fts_dependency_needs_preservation_but_unrelated_namespace_is_not_blocked(owned):
    client,handle,*_=owned
    baseline=prepare_owned(client,handle)
    handle.execute("CREATE VIRTUAL TABLE main.search USING fts5(optional,content='native_alter')")
    baseline=retained.observe(client,handle,'endpoint','native-session')
    with pytest.raises(ValueError,match='external-content FTS preservation'):
        review(client,handle,baseline,[{'action':'rename-column','resource_id':_resource_id('table',['main'],'native_alter'),'column':'optional','name':'payload'}])
    record=review(client,handle,baseline,[{'action':'rename-column','resource_id':_resource_id('table',['temp'],'native_alter'),'column':'optional','name':'payload'}])
    result=retained.apply(client,handle,record,'endpoint','native-session',12)
    assert result['state']=='applied_pending_caller_transaction',result
    assert handle.execute('SELECT optional FROM main.search').fetchall()==[('pending',)]


def test_native_alter_plan_requires_generated_desired_and_exact_original_scope(owned):
    client,handle,*_=owned
    baseline=prepare_owned(client,handle)
    changes=[{'action':'rename-table','resource_id':_resource_id('table',['main'],'native_alter'),'name':'new_name'}]
    desired=alter.generate(client,handle,baseline,'endpoint','native-session',changes)[0]
    changed=deepcopy(desired);changed['provenance']['database_target_id']='retained-session:other'
    with pytest.raises(ValueError,match='exact original'):alter.plan(client,handle,baseline,changed,baseline,'endpoint','native-session',changes)
    with pytest.raises(ValueError,match='Desired DDN differs'):alter.plan(client,handle,baseline,baseline,baseline,'endpoint','native-session',changes)
    with pytest.raises(ValueError,match='separately from object removal'):
        retained.plan(client,handle,baseline,desired,baseline,'endpoint','native-session',alterations=changes,deletions=['anything'])


def test_generated_native_ddl_preserves_original_file_settings_and_capability_observations(owned):
    client,handle,*_=owned
    baseline=prepare_owned(client,handle)
    changes=[{'action':'rename-column','resource_id':_resource_id('table',['main'],'native_alter'),'column':'optional','name':'payload'}]
    desired=alter.generate(client,handle,baseline,'endpoint','native-session',changes)[0]
    original={key:row for key,row in baseline['rows'].items() if row['kind'] not in retained.KINDS}
    assert original and all(desired['rows'][key]==row for key,row in original.items())
    assert all(row['native']['observation_scope']=='retained-session' for row in original.values())
    assert handle.execute('SELECT optional FROM main.native_alter').fetchall()==[('pending',)]
