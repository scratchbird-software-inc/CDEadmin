"""Retained SQLite/DuckDB native facts, transaction preservation and DDN scope."""
from types import SimpleNamespace
from unittest.mock import Mock
import json
import sqlite3
import uuid

import pytest

from pgadmin.cdeadmin.providers.embedded_session_catalog import sqlite_catalog,duckdb_catalog
from pgadmin.cdeadmin.data_studio.catalog_values import exact_native_integers
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export


def sqlite_client():return SimpleNamespace(_uncertain=set())


def test_sqlite_retained_temporary_attached_and_pending_catalog_preserves_deferred_constraints(tmp_path):
    path=tmp_path/'main.db';connection=sqlite3.connect(path)
    connection.execute('PRAGMA foreign_keys=ON')
    connection.executescript('CREATE TABLE parent(id INTEGER PRIMARY KEY); CREATE TABLE child(id INTEGER REFERENCES parent(id) DEFERRABLE INITIALLY DEFERRED);')
    connection.execute('ATTACH DATABASE ? AS "attached.schema"',(str(tmp_path/'attached.db'),))
    connection.execute('CREATE TABLE "attached.schema"."odd.table"("odd.column" TEXT)')
    connection.execute('CREATE TEMP TABLE "session table"(id INTEGER)')
    connection.create_function('session_function',1,lambda value:value)
    connection.create_collation('session_collation',lambda left,right:(left>right)-(left<right))
    connection.commit();connection.execute('BEGIN');connection.execute('INSERT INTO child VALUES (99)')
    connection.execute('CREATE TABLE pending_table(id INTEGER)')
    try:
        result=sqlite_catalog(sqlite_client(),connection,str(uuid.uuid4()))
        paths={tuple(row['display_path']) for row in result['resources']}
        assert ('temp','session table') in paths
        assert ('attached.schema','odd.table','odd.column') in paths
        assert ('main','pending_table') in paths
        assert any(row['native'].get('name')=='session_function' for row in result['resources'])
        assert any(row['native'].get('native_name')=='session_collation' for row in result['resources'])
        assert connection.in_transaction and connection.execute('SELECT * FROM child').fetchall()==[(99,)]
        with sqlite3.connect(path) as observer:
            assert observer.execute('SELECT count(*) FROM child').fetchone()==(0,)
            assert not observer.execute("SELECT 1 FROM sqlite_schema WHERE name='pending_table'").fetchall()
        with pytest.raises(sqlite3.IntegrityError):connection.commit()
        assert connection.in_transaction
        connection.rollback()
    finally:connection.close()


@pytest.mark.parametrize('active',[False,True])
@pytest.mark.parametrize('tracked',[False,True])
def test_sqlite_catalog_preserves_deferred_foreign_key_setting(active,tracked):
    from pgadmin.cdeadmin.providers.sqlite.driver import SQLiteConnection
    connection=sqlite3.connect(':memory:',factory=SQLiteConnection if tracked else sqlite3.Connection)
    connection.execute('CREATE TABLE t(id INTEGER)')
    if active:connection.execute('BEGIN')
    connection.execute('PRAGMA defer_foreign_keys=ON')
    try:
        sqlite_catalog(sqlite_client(),connection,str(uuid.uuid4()))
        assert connection.in_transaction is active
        assert connection.execute('PRAGMA defer_foreign_keys').fetchone()==(1,)
    finally:connection.close()


@pytest.mark.parametrize('module',['fts3','fts4','fts5'])
def test_retained_fts_configuration_in_main_temp_and_attached_scopes_preserves_pending_work(tmp_path,module):
    connection=sqlite3.connect(tmp_path/'fts.sqlite');client=sqlite_client()
    try:
        connection.execute('ATTACH ? AS attached',(str(tmp_path/'attached.sqlite'),))
        connection.execute('CREATE TABLE pending(value)')
        for schema in ('main','temp','attached'):
            connection.execute('CREATE VIRTUAL TABLE '+schema+'.search USING '+module+'(body)')
            connection.execute('INSERT INTO '+schema+'.search(search'+(',rank' if module=='fts5' else '')+
                ') VALUES('+ ("'automerge',6" if module=='fts5' else "'automerge=6'") +')')
        connection.commit();connection.execute('INSERT INTO pending VALUES(42)');connection.execute('SAVEPOINT caller')
        connection.execute("INSERT INTO main.search(rowid,body) VALUES(9007199254740993,'pending native token')")
        result=sqlite_catalog(client,connection,'retained',include_system=True)
        tables=[row for row in result['resources'] if row['resource_kind']=='fts-table']
        assert {tuple(row['display_path']) for row in tables}=={(schema,'search') for schema in ('main','temp','attached')}
        assert all(dict(row['native']['fts_configuration']['commands'])['automerge']==6 for row in tables)
        assert connection.in_transaction and not client._uncertain
        connection.execute('ROLLBACK TO caller')
        assert connection.execute('SELECT * FROM pending').fetchall()==[(42,)]
        assert connection.execute('SELECT count(*) FROM main.search').fetchone()==(0,)
        connection.rollback()
    finally:connection.close()


def test_retained_fts_damaged_native_settings_remain_typed_and_bounded(tmp_path,monkeypatch):
    from pgadmin.cdeadmin.providers import embedded_session_catalog
    connection=sqlite3.connect(tmp_path/'fts.sqlite');client=sqlite_client()
    try:
        connection.execute('CREATE VIRTUAL TABLE search USING fts5(body)')
        connection.execute("INSERT INTO search_config VALUES('owned-unknown',?)",(b'\x00\xff',))
        connection.execute('CREATE TABLE pending(value)');connection.commit()
        connection.execute('INSERT INTO pending VALUES(42)');connection.execute('SAVEPOINT caller')
        result=sqlite_catalog(client,connection,'retained')
        table=next(row for row in result['resources'] if row['resource_kind']=='fts-table')
        assert table['native']['fts_configuration']['restorable'] is False
        assert ['owned-unknown',{'type':'blob','hex':'00ff'}] in table['native']['fts_configuration']['observed_settings']
        monkeypatch.setattr(embedded_session_catalog,'MAX_FACTS',4)
        with pytest.raises(ValueError,match='observation bounds'):sqlite_catalog(client,connection,'retained')
        connection.execute('ROLLBACK TO caller')
        assert connection.in_transaction and connection.execute('SELECT * FROM pending').fetchall()==[(42,)]
        assert not client._uncertain
    finally:connection.close()


def test_duckdb_retained_temp_schema_and_pending_native_fields_use_the_original_connection(tmp_path):
    import duckdb
    from pgadmin.cdeadmin.providers.duckdb.provider import _create_client
    client=_create_client();connection=client.open_session({'route':{'database':str(tmp_path/'main.duckdb'),'filesystem_root':str(tmp_path)}})
    try:
        connection.execute('CREATE TABLE t(id INTEGER)');connection.execute('COMMIT')
        connection.execute("ATTACH ':memory:' AS \"attached.catalog\"")
        connection.execute('CREATE TABLE "attached.catalog".main."odd.table"("odd.column" VARCHAR)')
        connection.execute('CREATE TEMP TABLE "session table"("session column" INTEGER)')
        connection.execute('CREATE TEMP MACRO "session macro"(x) AS x+1')
        connection.execute('BEGIN');connection.execute('INSERT INTO t VALUES (99)')
        connection.execute('CREATE TABLE pending_table(id INTEGER)')
        connection.execute('CREATE SEQUENCE exact_sequence START 9007199254740993 MAXVALUE 9223372036854775807')
        before=connection.execute('SELECT current_transaction_id()').fetchone()
        result=duckdb_catalog(client,connection,str(uuid.uuid4()))
        assert connection.execute('SELECT current_transaction_id()').fetchone()==before
        paths={tuple(row['display_path']) for row in result['resources']}
        assert ('temp','main') in paths
        assert ('temp','main','session table','session column') in paths
        assert ('attached.catalog','main','odd.table','odd.column') in paths
        assert any(row['display_name']=='session macro' for row in result['resources'])
        assert any(row['display_name']=='pending_table' for row in result['resources'])
        sequence=next(row for row in result['resources'] if row['display_name']=='exact_sequence')
        exact_native_integers(sequence)
        assert sequence['native']['catalog_metadata']['start_value']=='9007199254740993'
        with duckdb.connect(str(tmp_path/'main.duckdb')) as observer:
            assert observer.execute('SELECT count(*) FROM t').fetchone()==(0,)
            assert not observer.execute("SELECT 1 FROM duckdb_tables() WHERE table_name='pending_table'").fetchall()
        connection.execute('ROLLBACK')
    finally:client.close_session(connection);client.close()


@pytest.mark.parametrize('engine',['duckdb','sqlite'])
@pytest.mark.parametrize('marker',['provenance','native'])
def test_retained_documents_cannot_authorize_independent_embedded_migrations(engine,marker):
    from pgadmin.cdeadmin.workspace.duckdb_schema_plan import _root
    from pgadmin.cdeadmin.workspace.sqlite_schema_plan import _scope
    model={'provenance':{'mapping':'scratchrobin.'+engine+'.catalog@1'},'rows':{}}
    if marker=='provenance':model['provenance']['observation_scope']='retained-session'
    else:model['rows']['pending']={'native':{'observation_scope':'retained-session'}}
    with pytest.raises(ValueError,match='Retained-session'):
        (_root if engine=='duckdb' else _scope)(model)


@pytest.mark.parametrize("decision",[sqlite3.SQLITE_DENY,sqlite3.SQLITE_IGNORE])
def test_sqlite_catalog_respects_authorizer_before_consuming_idle_deferred_settings(decision):
    from pgadmin.cdeadmin.sdk.relational import RelationalClientError
    from pgadmin.cdeadmin.providers.sqlite.driver import SQLiteConnection
    connection=sqlite3.connect(':memory:',factory=SQLiteConnection);connection.execute('CREATE TABLE t(id INTEGER)')
    connection.execute('PRAGMA defer_foreign_keys=ON')
    def policy(action,name,value,_database,_context):
        return decision if action==sqlite3.SQLITE_PRAGMA and name=='defer_foreign_keys' and value is not None else sqlite3.SQLITE_OK
    connection.set_authorizer(policy);client=sqlite_client()
    try:
        with pytest.raises(RelationalClientError):sqlite_catalog(client,connection,str(uuid.uuid4()))
        assert not connection.in_transaction and not client._uncertain
        assert connection._cdeadmin_authorizer is policy
        assert connection.execute('PRAGMA defer_foreign_keys').fetchone()==(1,)
    finally:connection.close()


@pytest.mark.parametrize('engine',['sqlite','duckdb'])
def test_production_provider_and_data_studio_export_original_retained_context(tmp_path,engine):
    from pgadmin.cdeadmin.data_studio.studio import DataStudioService
    from pgadmin.cdeadmin.data_studio.models import StudioSession,DataStudioAccessError
    from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
    if engine=='sqlite':
        from pgadmin.cdeadmin.providers.sqlite.provider import create_provider,PROFILE
    else:
        from pgadmin.cdeadmin.providers.duckdb.provider import create_provider,PROFILE
    context=SimpleNamespace(endpoint_id=str(uuid.uuid4()),session_namespace=str(uuid.uuid4()),
        pool_namespace=str(uuid.uuid4()),cache_namespace=str(uuid.uuid4()),provider_id=PROFILE.provider_id,
        provider_version='0.1.0',profile_id=PROFILE.profile_id,profile_version=PROFILE.exact_version)
    provider=create_provider(context,SimpleNamespace(require=lambda *_args:None))
    opened=provider.open_session({'route':{'database':str(tmp_path/('scope.'+engine)),'filesystem_root':str(tmp_path)}})
    handle=provider._sessions[opened['session_id']].handle
    binding=SimpleNamespace(instance=provider,manifest={'identity':provider._identity()})
    studio=DataStudioService(SimpleNamespace(resolve=lambda _context:binding))
    context.isolation_key=(context.endpoint_id,context.cache_namespace)
    session=StudioSession(context.endpoint_id,PROFILE.language_profile,opened,None,None,None,
        provider_isolation_key=context.isolation_key)
    studio._sessions[session.session_id]=session
    try:
        handle.execute('CREATE TEMP TABLE "retained table"("exact column" INTEGER)')
        if engine=='duckdb':handle.execute('CREATE SEQUENCE exact START 9007199254740993 MAXVALUE 9223372036854775807')
        result=studio.session_catalog(context,session.session_id)
        assert any(row['display_name']=='exact column' and row['native']['session_local'] for row in result['resources'])
        assert result['engine']==engine and result['document']
        model=read_catalog(json.dumps(result['document']['snapshot']),engine=engine)
        assert model['provenance']['observation_scope']=='retained-session'
        assert any(row['native'].get('observation_scope')=='retained-session' for row in model['rows'].values())
        if engine=='duckdb':
            sequence=next(row for row in result['resources'] if row['display_name']=='exact')
            assert sequence['native']['catalog_metadata']['start_value']=='9007199254740993'
            assert sequence['native']['json_integer_encodings']['/catalog_metadata/start_value']=='native-integer-decimal-text'
        with pytest.raises(DataStudioAccessError,match='another endpoint'):
            studio.session_catalog(SimpleNamespace(endpoint_id=str(uuid.uuid4())),session.session_id)
    finally:provider.close()


def test_duckdb_aborted_transaction_is_refused_without_implicit_repair(tmp_path):
    import duckdb
    from pgadmin.cdeadmin.providers.duckdb.provider import _create_client
    from pgadmin.cdeadmin.sdk.relational import RelationalClientError
    client=_create_client();connection=client.open_session({'route':{'database':str(tmp_path/'aborted.duckdb'),'filesystem_root':str(tmp_path)}})
    try:
        connection.execute('CREATE TABLE t(id INTEGER PRIMARY KEY)');connection.execute('COMMIT');connection.execute('BEGIN')
        connection.execute('INSERT INTO t VALUES (1)')
        with pytest.raises(duckdb.ConstraintException):connection.execute('INSERT INTO t VALUES (1)')
        with pytest.raises(RelationalClientError,match='Resolve the existing'):
            duckdb_catalog(client,connection,str(uuid.uuid4()))
        with pytest.raises(duckdb.TransactionException):connection.execute('SELECT * FROM t')
        assert not client._states[id(connection)]['session_reuse_blocked']
        connection.execute('ROLLBACK')
        assert connection.execute('SELECT * FROM t').fetchall()==[]
    finally:client.close_session(connection);client.close()


def test_duckdb_closed_handle_is_quarantined_without_reconnection():
    import duckdb
    from pgadmin.cdeadmin.sdk.relational import RelationalClientError
    connection=duckdb.connect();connection.close()
    client=SimpleNamespace(_states={id(connection):{'session_reuse_blocked':False}})
    with pytest.raises(RelationalClientError,match='liveness is unconfirmed'):
        duckdb_catalog(client,connection,str(uuid.uuid4()))
    assert client._states[id(connection)]['session_reuse_blocked']


def test_sqlite_unknown_guard_cleanup_blocks_reuse_and_never_commits_caller_work():
    from pgadmin.cdeadmin.sdk.relational import RelationalClientError
    class NativeConnection(sqlite3.Connection):
        def execute(self,source,*args,**kwargs):
            if source.startswith('RELEASE SAVEPOINT sr_catalog_'):raise OSError('private native detail')
            return super().execute(source,*args,**kwargs)
    connection=sqlite3.connect(':memory:',factory=NativeConnection)
    connection.execute('CREATE TABLE t(id INTEGER)');connection.execute('BEGIN');connection.execute('INSERT INTO t VALUES (99)')
    client=sqlite_client()
    try:
        with pytest.raises(RelationalClientError,match='cleanup is unconfirmed') as refused:
            sqlite_catalog(client,connection,str(uuid.uuid4()))
        assert 'private' not in str(refused.value)
        assert id(connection) in client._uncertain
        assert connection.in_transaction and connection.execute('SELECT * FROM t').fetchall()==[(99,)]
        connection.rollback();assert connection.execute('SELECT * FROM t').fetchall()==[]
    finally:connection.close()
