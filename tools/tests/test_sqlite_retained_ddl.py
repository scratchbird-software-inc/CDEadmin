"""Retained native DDL never switches handles, permissions or caller decisions."""
from contextlib import closing
from copy import deepcopy
import sqlite3
import threading
from types import SimpleNamespace

import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.driver import SQLiteConnection
from pgadmin.cdeadmin.providers.sqlite.provider import _resource_id,_resources
from pgadmin.cdeadmin.providers.sqlite import ddl_prepare
from pgadmin.cdeadmin.workspace import sqlite_retained_schema as retained


@pytest.fixture
def owned(tmp_path):
    path,attached=tmp_path/'main.sqlite',tmp_path/'attached.sqlite'
    handle=sqlite3.connect(path,factory=SQLiteConnection,check_same_thread=False)
    client=SimpleNamespace(_uncertain=set(),_busy=set(),_lock=threading.RLock())
    handle.executescript('CREATE TABLE owned(id INTEGER);CREATE TABLE audit(id INTEGER);'
        'CREATE TABLE drop_me(id INTEGER);CREATE INDEX retained_index ON owned(id);'
        'CREATE TEMP TABLE owned(id INTEGER);')
    handle.execute('ATTACH DATABASE ? AS "team.雪"',(str(attached),))
    handle.execute('CREATE TABLE "team.雪".owned(id INTEGER)');handle.commit()
    handle.execute('BEGIN');handle.execute('INSERT INTO main.owned VALUES(93)')
    handle.execute('CREATE TABLE uncommitted_definition(id INTEGER)');handle.execute('SAVEPOINT caller')
    try:yield client,handle,path,attached
    finally:handle.close()


def design(client,handle,statements):
    baseline=retained.observe(client,handle,'endpoint','native-session')
    namespaces={row[1] for row in handle.execute('PRAGMA database_list')}
    probe=retained._prototype(baseline,namespaces)
    try:
        for statement in statements:probe.execute(statement)
        desired=retained.model(_resources(probe,{}),'endpoint','native-session')
    finally:probe.close()
    return baseline,desired


def reviewed(client,handle,baseline,desired,*,deletions=()):
    preview=retained.plan(client,handle,baseline,desired,baseline,'endpoint','native-session',deletions=deletions)
    return {'plan':preview,'baseline':baseline,'desired':desired,'native_context':retained.context(handle,12)}


def test_main_temp_and_attached_creations_preserve_original_pending_schema_rows_and_savepoint(owned):
    client,handle,path,attached=owned
    baseline,desired=design(client,handle,[
        'CREATE TABLE main.added(id INTEGER)',
        'CREATE TABLE temp.added(id INTEGER)',
        'CREATE TABLE "team.雪".added(id INTEGER)',
        'CREATE INDEX "team.雪".added_index ON added(id)',
        'CREATE VIEW temp.added_view AS SELECT id FROM "team.雪".added',
        'CREATE TRIGGER temp.added_trigger INSERT ON "team.雪".owned BEGIN INSERT INTO audit VALUES(NEW.id); END',
    ])
    record=reviewed(client,handle,baseline,desired)
    assert handle.execute("SELECT name FROM main.sqlite_schema WHERE name='added'").fetchall()==[]
    assert handle.execute('SELECT * FROM main.owned').fetchall()==[(93,)]
    with closing(sqlite3.connect(path)) as observer:
        assert observer.execute('SELECT * FROM owned').fetchall()==[]
        assert observer.execute("SELECT name FROM sqlite_schema WHERE name='uncommitted_definition'").fetchall()==[]
    result=retained.apply(client,handle,record,'endpoint','native-session',12)
    assert result['state']=='applied_pending_caller_transaction' and not result['commit_dispatched'],result
    handle.execute('INSERT INTO "team.雪".owned VALUES(17)')
    assert handle.execute('SELECT * FROM main.audit').fetchall()==[(17,)]
    handle.execute('ROLLBACK TO caller');handle.execute('RELEASE caller')
    assert handle.in_transaction and handle.execute('SELECT * FROM main.owned').fetchall()==[(93,)]
    assert handle.execute("SELECT name FROM main.sqlite_schema WHERE name='added'").fetchall()==[]
    assert handle.execute("SELECT name FROM temp.sqlite_schema WHERE name='added'").fetchall()==[]
    assert handle.execute('SELECT * FROM main.audit').fetchall()==[]
    assert handle.execute('SELECT * FROM "team.雪".owned').fetchall()==[]
    assert not client._uncertain


def test_explicit_retained_drop_and_index_view_replacement_share_atomic_transaction(owned):
    client,handle,path,_=owned
    baseline,desired=design(client,handle,[
        'DROP TABLE main.drop_me','DROP INDEX main.retained_index',
        'CREATE INDEX main.retained_index ON owned(id DESC)',
        'CREATE VIEW main.projection AS SELECT id FROM owned'])
    deleted=_resource_id('table',['main'],'drop_me')
    with pytest.raises(ValueError,match='absent retained DDN fact'):
        reviewed(client,handle,baseline,desired)
    record=reviewed(client,handle,baseline,desired,deletions=[deleted])
    result=retained.apply(client,handle,record,'endpoint','native-session',12)
    assert result['state']=='applied_pending_caller_transaction',result
    assert handle.execute('SELECT * FROM projection').fetchall()==[(93,)]
    handle.commit()
    with closing(sqlite3.connect(path)) as observer:
        assert observer.execute('SELECT * FROM projection').fetchall()==[(93,)]
        assert observer.execute("SELECT name FROM sqlite_schema WHERE name='drop_me'").fetchall()==[]


def test_retained_view_replacement_derives_complete_new_projection(owned):
    client,handle,*_=owned
    handle.execute('CREATE VIEW main.projection AS SELECT id FROM owned')
    baseline,desired=design(client,handle,['DROP VIEW main.projection',
        'CREATE VIEW main.projection AS SELECT id AS changed,id*2 AS computed FROM owned'])
    record=reviewed(client,handle,baseline,desired)
    result=retained.apply(client,handle,record,'endpoint','native-session',12)
    assert result['state']=='applied_pending_caller_transaction',result
    assert handle.execute('SELECT * FROM projection').fetchall()==[(93,186)]


def test_native_policy_refusal_after_prior_drop_restores_index_and_original_pending_work(owned):
    client,handle,*_=owned
    baseline,desired=design(client,handle,['DROP INDEX main.retained_index',
        'CREATE INDEX main.retained_index ON owned(id DESC)'])
    def policy(action,first,second,database,context):
        return sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_CREATE_INDEX else sqlite3.SQLITE_OK
    handle.set_authorizer(policy)
    record=reviewed(client,handle,baseline,desired)
    result=retained.apply(client,handle,record,'endpoint','native-session',12)
    assert result['state']=='rolled_back_to_savepoint',result
    assert handle._cdeadmin_authorizer is policy
    assert handle.execute('PRAGMA main.index_xinfo(retained_index)').fetchone()[3]==0
    assert handle.execute('SELECT * FROM main.owned').fetchall()==[(93,)]
    handle.execute('ROLLBACK TO caller');handle.execute('RELEASE caller')
    assert not client._uncertain


@pytest.mark.parametrize('change',['revision','transaction','data','schema','authorization'])
def test_retained_dispatch_rejects_changed_original_context(owned,change):
    client,handle,*_=owned
    baseline,desired=design(client,handle,['CREATE TABLE temp.added(id INTEGER)'])
    record=reviewed(client,handle,baseline,desired)
    revision=12
    if change=='revision':revision=13
    if change=='transaction':handle.rollback()
    if change=='data':handle.execute('INSERT INTO main.owned VALUES(94)')
    if change=='schema':handle.execute('CREATE TABLE concurrent(id INTEGER)')
    if change=='authorization':handle.set_authorizer(lambda *_:sqlite3.SQLITE_OK)
    result=retained.apply(client,handle,record,'endpoint','native-session',revision)
    assert result['state']=='not_dispatched',result
    assert not handle.execute("SELECT name FROM temp.sqlite_schema WHERE name='added'").fetchall()


def test_retained_native_cancellation_before_first_stage_preserves_savepoint(owned):
    client,handle,*_=owned
    baseline,desired=design(client,handle,['CREATE TABLE temp.added(id INTEGER)'])
    record=reviewed(client,handle,baseline,desired);cancel=threading.Event();cancel.set()
    result=retained.apply(client,handle,record,'endpoint','native-session',12,cancel=cancel)
    assert result['state']=='rolled_back_to_savepoint' and result['completed_statements']==0,result
    handle.execute('ROLLBACK TO caller');handle.execute('RELEASE caller')
    assert handle.execute('SELECT * FROM main.owned').fetchall()==[(93,)]


def test_retained_source_from_another_session_never_authorizes_ddl(owned):
    client,handle,*_=owned
    baseline,desired=design(client,handle,['CREATE TABLE temp.added(id INTEGER)'])
    desired['provenance']['database_target_id']='retained-session:another'
    with pytest.raises(ValueError,match='exact original SQLite session'):
        reviewed(client,handle,baseline,desired)


def test_unobservable_native_authorizer_is_never_replaced():
    with closing(sqlite3.connect(':memory:')) as handle:
        def policy(action,*_):return sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_SELECT else sqlite3.SQLITE_OK
        handle.set_authorizer(policy)
        row={'kind':'table','path':['main','added'],'name':'added','native':{'ddl':'CREATE TABLE added(id INTEGER)'}}
        with pytest.raises(ValueError,match='observable native authorization'):
            ddl_prepare.prepare(SimpleNamespace(_uncertain=set()),handle,row,'CREATE TABLE added(id INTEGER)')
        with pytest.raises(sqlite3.DatabaseError):handle.execute('SELECT 1')


@pytest.mark.parametrize('namespace',['main','temp','team.雪'])
def test_structured_retained_columns_keep_aliases_generated_types_and_pending_rows(owned,namespace):
    client,handle,*_=owned
    baseline=retained.observe(client,handle,'endpoint','native-session')
    desired=retained.generate_columns(client,handle,baseline,'endpoint','native-session',
        _resource_id('table',[namespace],'owned'),[{'name':'untyped:雪'},
        {'name':'computed','generated':{'expression':'id * 2','storage':'virtual'}}])
    record=reviewed(client,handle,baseline,desired)
    result=retained.apply(client,handle,record,'endpoint','native-session',12)
    assert result['state']=='applied_pending_caller_transaction',result
    if namespace=='main':assert handle.execute('SELECT computed FROM main.owned').fetchall()==[(186,)]
    assert handle.execute('SELECT id FROM main.owned').fetchall()==[(93,)]
    handle.execute('ROLLBACK TO caller');handle.execute('RELEASE caller')
    assert [row[1] for row in handle.execute('PRAGMA "'+namespace+'".table_xinfo(owned)')]==['id']


def test_retained_stored_column_refusal_preserves_earlier_stages_and_caller_savepoint(owned):
    client,handle,*_=owned
    baseline=retained.observe(client,handle,'endpoint','native-session')
    desired=retained.generate_columns(client,handle,baseline,'endpoint','native-session',
        _resource_id('table',['main'],'owned'),[{'name':'first'},
        {'name':'stored','generated':{'expression':'id * 2','storage':'stored'}}])
    record=reviewed(client,handle,baseline,desired)
    result=retained.apply(client,handle,record,'endpoint','native-session',12)
    assert result['state']=='rolled_back_to_savepoint' and 'STORED' in result['native_error'],result
    assert [row[1] for row in handle.execute('PRAGMA main.table_xinfo(owned)')]==['id']
    assert handle.execute('SELECT * FROM main.owned').fetchall()==[(93,)]
    handle.execute('ROLLBACK TO caller');handle.execute('RELEASE caller')


def test_retained_prototype_preserves_native_temp_and_attached_fts_settings(owned):
    client,handle,*_=owned
    handle.execute('CREATE VIRTUAL TABLE temp.search USING fts5(body)')
    handle.execute('CREATE VIRTUAL TABLE "team.雪".search USING fts4(body)')
    handle.execute("INSERT INTO temp.search(search,rank) VALUES('automerge',8)")
    handle.execute("INSERT INTO \"team.雪\".search(search) VALUES('automerge=8')")
    baseline,desired=design(client,handle,['CREATE TABLE temp.added(id INTEGER)'])
    record=reviewed(client,handle,baseline,desired)
    result=retained.apply(client,handle,record,'endpoint','native-session',12)
    assert result['state']=='applied_pending_caller_transaction',result
    assert handle.execute("SELECT v FROM temp.search_config WHERE k='automerge'").fetchone()==(8,)


def test_retained_acknowledgement_survives_receipt_observation_failure(owned):
    client,handle,*_=owned
    baseline,desired=design(client,handle,['CREATE TABLE temp.added(id INTEGER)'])
    record=reviewed(client,handle,baseline,desired)
    def failed(_value):raise OSError('owned receipt storage unavailable')
    result=retained.apply(client,handle,record,'endpoint','native-session',12,acknowledge=failed)
    assert result['state']=='applied_pending_caller_transaction' and result['native_ddl_acknowledged'],result
    assert result['acknowledgement_store_error']=='OSError' and not client._uncertain


def test_retained_durable_dispatch_finishes_coherently_and_never_replays_after_close(owned,tmp_path):
    import time
    from pgadmin.cdeadmin.workspace.sqlite_retained_applications import SQLiteRetainedApplications
    client,handle,*_=owned
    baseline,desired=design(client,handle,['CREATE TABLE temp.added(id INTEGER)'])
    record=reviewed(client,handle,baseline,desired)
    archive=SQLiteRetainedApplications(tmp_path/'receipts.json')
    review=archive.review(record['plan'],baseline,desired,record['native_context'],'owner','binding','file','native-session')
    request={'review_id':review['review_id'],'review_digest':review['review_digest'],'confirmed':True}
    with client._lock:
        first=archive.start(request,'owner','binding','native-session',client,handle,'endpoint',12)
        assert first['native_session_release_confirmed'] is False
        assert id(handle) in client._busy
    deadline=time.monotonic()+10
    while True:
        value=archive.get(review['review_id'],'owner','binding')
        if value['native_session_release_confirmed'] and not value['worker_active']:break
        assert time.monotonic()<deadline;time.sleep(.01)
    assert value['state']=='applied_pending_caller_transaction' and id(handle) not in client._busy,value
    assert archive.start(request,'owner','binding','closed-session',object(),object(),'endpoint',12)['state']==value['state']
    assert archive.list('owner','binding')['total']==1
    with pytest.raises(ValueError):archive.get(review['review_id'],'other','binding')
    with pytest.raises(ValueError):archive.get(review['review_id'],'owner','other-binding')
    archive.remove(review['review_id'],'owner','binding',confirmed=True)
    assert archive.list('owner','binding')['total']==0
