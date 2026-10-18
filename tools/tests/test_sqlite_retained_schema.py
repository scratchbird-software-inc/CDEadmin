"""Native changegroups use the actual transient schema without settling SQL."""
from contextlib import contextmanager
import os
import threading
import uuid

import pytest

from test_sqlite_changeset_apply import native,apply  # noqa: F401
from test_sqlite_driver import client,open_database  # noqa: F401
from test_sqlite_transform_jobs import start,wait
from pgadmin.cdeadmin.providers.sqlite.changeset_transform import options
from pgadmin.cdeadmin.providers.sqlite.session_api import SessionAPI,SessionAPIError
from pgadmin.cdeadmin.providers.sqlite.transform_context import retained_snapshot
from pgadmin.cdeadmin.workspace.sqlite_transform_jobs import SQLiteTransformJobs,TransformTransport
from pgadmin.cdeadmin.sdk import RelationalClientError


@pytest.fixture
def retained(native,client,tmp_path):
    independent,independent_api,create,_route=native
    handle,route=open_database(client,tmp_path)
    api=SessionAPI(handle,os.environ['CDEADMIN_SQLITE_SESSION_LIBRARY'])
    source=create('CREATE TABLE t(id INTEGER PRIMARY KEY)','','INSERT INTO t VALUES(9007199254740993)')
    jobs=SQLiteTransformJobs(tmp_path/'retained.json',tmp_path/'retained');endpoint=str(uuid.uuid4());session=str(uuid.uuid4())
    def review(database):
        binding={'client':client,'handle':handle,'api':api}
        snapshot=retained_snapshot(handle,api,session,database)
        selected=options({'operation':'merge','schema_database':database,'schema_session_id':session})
        observed={'inputs':[{'file':{'path':source.name}}],'schema':snapshot['schema'],'schema_binding':snapshot}
        receipt=jobs.review(1,endpoint,selected,{'identity':observed,'state':{}},'owned',api.program)
        record=jobs.load(receipt['job_id'],1,endpoint)
        @contextmanager
        def input_file():
            with source.open('rb') as stream:yield stream,{'path':source.name}
        transport=TransformTransport(jobs,os.environ['CDEADMIN_SQLITE_SESSION_LIBRARY'],[input_file],route,retained_binding=binding)
        request={'job_id':record['job_id'],'review_digest':record['review_digest'],'confirmed':True}
        return record,request,transport
    try:yield handle,api,jobs,endpoint,review,independent,independent_api
    finally:
        jobs.close()
        if handle.in_transaction:handle.rollback()


@pytest.mark.parametrize('database',['main','temp','attached 雪'])
def test_native_merge_uses_uncommitted_main_temp_and_attached_memory_schema(retained,database):
    handle,_api,jobs,endpoint,review,independent,independent_api=retained
    if database not in {'main','temp'}:handle.execute('ATTACH ? AS "attached 雪"',(':memory:',))
    handle.execute('BEGIN');handle.execute('SAVEPOINT owner_pending')
    schema="t(id INTEGER PRIMARY KEY,body TEXT DEFAULT 'retained 😀',payload BLOB DEFAULT x'0080FF')"
    handle.execute('CREATE TABLE "'+database+'".'+schema)
    handle.execute('INSERT INTO "'+database+'".t(id) VALUES(99)')
    record,request,transport=review(database)
    start(jobs,record,request,transport,endpoint);value=wait(jobs,record,endpoint)
    assert value['state']=='completed',value
    assert value['source_transaction_open'] and value['source_transaction_open_after'] and handle.in_transaction
    assert handle.execute('SELECT * FROM "'+database+'".t').fetchall()==[(99,'retained 😀',b'\x00\x80\xff')]
    independent.execute('CREATE TABLE '+schema)
    apply(independent,independent_api,jobs.directory(record)/'archive/transformed.native');independent.commit()
    assert independent.execute('SELECT * FROM t').fetchall()==[(9007199254740993,'retained 😀',b'\x00\x80\xff')]
    handle.execute('ROLLBACK TO owner_pending');handle.execute('RELEASE owner_pending')
    assert handle.in_transaction
    assert handle.execute('SELECT count(*) FROM "'+database+'".sqlite_schema WHERE name=\'t\'').fetchone()==(0,)


@pytest.mark.parametrize('mutation',[
    'ALTER TABLE t ADD COLUMN changed TEXT',"ATTACH ':memory:' AS changed",'COMMIT'])
def test_stale_retained_basis_is_refused_before_native_dispatch(retained,mutation):
    handle,_api,jobs,endpoint,review,_independent,_api2=retained
    handle.execute('CREATE TABLE t(id INTEGER PRIMARY KEY)');handle.execute('BEGIN')
    handle.execute('INSERT INTO t VALUES(99)');record,request,transport=review('main');handle.execute(mutation)
    pending=handle.in_transaction
    start(jobs,record,request,transport,endpoint);value=wait(jobs,record,endpoint)
    assert value['state']=='failed' and not value.get('native_dispatch_admitted'),value
    assert handle.in_transaction==pending and handle.execute('SELECT id FROM t').fetchall()==[(99,)]
    assert id(handle) not in transport.retained_binding['client']._busy


def test_native_cancel_releases_borrowed_connection_and_preserves_savepoint(retained,monkeypatch):
    from pgadmin.cdeadmin.workspace import sqlite_transform_jobs as module
    handle,_api,jobs,endpoint,review,_independent,_api2=retained
    handle.execute('CREATE TABLE t(id INTEGER PRIMARY KEY)');handle.execute('BEGIN');handle.execute('SAVEPOINT user_work')
    handle.execute('INSERT INTO t VALUES(99)');record,request,transport=review('main')
    entered=threading.Event();release=threading.Event();original=module.transform
    def paused(*args,**kwargs):
        entered.set();assert release.wait(5)
        return original(*args,**kwargs)
    monkeypatch.setattr(module,'transform',paused)
    start(jobs,record,request,transport,endpoint)
    try:
        assert entered.wait(5)
        with pytest.raises(RelationalClientError,match='active'):transport.retained_binding['client'].close_session(handle)
        jobs.cancel(record['job_id'],1,endpoint)
        # Observe the real cancellation pipe before allowing the native call.
        import time
        deadline=time.monotonic()+5
        while not jobs.get(record['job_id'],1,endpoint).get('progress',{}).get('elapsed_seconds'):
            assert time.monotonic()<deadline;time.sleep(.02)
    finally:release.set()
    value=wait(jobs,record,endpoint)
    assert value['state']=='cancelled' and value['worker_io_closed'],value
    assert handle.in_transaction and handle.execute('SELECT id FROM t').fetchall()==[(99,)]
    handle.execute('ROLLBACK TO user_work');handle.execute('RELEASE user_work')
    assert handle.in_transaction and handle.execute('SELECT count(*) FROM t').fetchone()==(0,)
    assert id(handle) not in transport.retained_binding['client']._busy


@pytest.mark.parametrize('selected',[
    {'operation':'merge','schema_session_id':'session'},
    {'operation':'invert','schema_database':'main','schema_session_id':'session'},
    {'operation':'merge','schema_database':'temp','schema_session_id':42}])
def test_invalid_retained_schema_selection_is_not_an_independent_fallback(selected):
    with pytest.raises(SessionAPIError):options(selected)


def test_closed_or_unavailable_studio_session_has_a_workspace_refusal(monkeypatch):
    from pgadmin.cdeadmin.workspace import sqlite_changeset_service
    from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService,ProviderWorkspaceError
    from pgadmin.cdeadmin.data_studio.models import DataStudioAccessError
    def unavailable(*_args):raise DataStudioAccessError('Data Studio session is unavailable')
    monkeypatch.setattr(sqlite_changeset_service,'action',unavailable)
    with pytest.raises(ProviderWorkspaceError,match='session is unavailable'):
        ProviderWorkspaceService.sqlite_changeset(object(),None,'transform_schemas',{})
