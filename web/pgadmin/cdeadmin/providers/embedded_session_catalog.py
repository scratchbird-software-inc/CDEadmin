"""Read retained embedded catalogs without adopting or ending caller work."""
import json
import sqlite3
import time
import uuid

from .sqlite.driver import uncertain_error
from ..sdk.relational import RelationalClientError

MAX_FACTS=20000
MAX_BYTES=8*1024*1024
MAX_SECONDS=30


def annotate(result, engine, session_id):
    attached={row['display_name'] for row in result['resources'] if row['resource_kind']=='attached-database'}
    for resource in result['resources']:
        native=resource.setdefault('native',{})
        native['observation_scope']='retained-session'
        path=resource.get('display_path',[])
        temporary=bool(path and path[0]=='temp' or native.get('catalog_metadata',{}).get('temporary'))
        scope='temporary' if temporary else native.get('scope') if native.get('scope') in {'connection','runtime'} else 'attached-database' if path and path[0] in attached else 'database'
        native['session_scope_kind']=scope
        native['session_local']=scope in {'temporary','connection'}
    result.update(engine=engine,observation_scope='retained-session',
                  catalog_target_id='retained-session:'+session_id,
                  transaction_preserved=True)
    return result


def sqlite_catalog(client, connection, session_id, *, include_system=False):
    from .sqlite.provider import _resources
    original=connection.in_transaction
    guard='sr_catalog_'+uuid.uuid4().hex
    generation=str(uuid.uuid4())
    restore_deferred=False
    created=False;started=time.monotonic();facts=bytes_seen=0;cursors=[]
    def account(value):
        nonlocal facts,bytes_seen
        # This measures raw native rows as well as the final encoded resources.
        # FTS config can contain damaged/unknown BLOB or nonfinite values; its
        # adapter preserves those as typed observations rather than losing the
        # complete retained catalog. Final encoded resources are counted again.
        facts+=1;bytes_seen+=len(json.dumps(value,ensure_ascii=False,allow_nan=True,
            default=lambda item: {'native_blob_hex':bytes(item).hex()} if isinstance(item,(bytes,bytearray,memoryview)) else str(item)).encode('utf8'))
        if facts>MAX_FACTS or bytes_seen>MAX_BYTES or time.monotonic()-started>MAX_SECONDS:
            raise ValueError('SQLite session catalog exceeds its observation bounds')
    class Cursor:
        def __init__(self):self.native=connection.cursor();self.closed=False;cursors.append(self)
        def execute(self,*args):self.native.execute(*args);return self
        def fetchone(self):
            value=self.native.fetchone()
            if value is not None:account(value)
            return value
        def fetchall(self):
            result=[]
            while rows:=self.native.fetchmany(128):
                for value in rows:account(value);result.append(value)
            return result
        def __iter__(self):return self
        def __next__(self):
            value=self.fetchone()
            if value is None:raise StopIteration
            return value
        def close(self):
            if not self.closed:self.native.close();self.closed=True
    class Connection:
        def cursor(self):return Cursor()
        def execute(self,*args):return Cursor().execute(*args)
    try:
        if not original:
            restore_deferred=bool(connection.execute('PRAGMA defer_foreign_keys').fetchone()[0])
            if restore_deferred:
                # An owned read transaction consumes this next-transaction
                # setting at its end. Admit its idempotent restoration before
                # opening the guard, through the caller's native authorizer.
                from .sqlite.driver import SQLiteConnection
                if isinstance(connection,SQLiteConnection):
                    previous=connection._cdeadmin_authorizer;admitted=None
                    def authorization(action,first,second,database,context):
                        nonlocal admitted
                        decision=previous(action,first,second,database,context) if previous is not None else sqlite3.SQLITE_OK
                        if action==sqlite3.SQLITE_PRAGMA and first=='defer_foreign_keys' and second is not None:admitted=decision
                        return decision
                    connection.set_authorizer(authorization)
                    try:connection.execute('PRAGMA defer_foreign_keys=ON')
                    finally:
                        try:connection.set_authorizer(previous)
                        except BaseException:
                            client._uncertain.add(id(connection))
                            raise RelationalClientError('SQLite catalog authorization cleanup is unconfirmed; close this session') from None
                    if admitted!=sqlite3.SQLITE_OK:
                        raise RelationalClientError('Native authorizer did not admit preserving the idle deferred-constraint setting')
                else:connection.execute('PRAGMA defer_foreign_keys=ON')
        connection.execute('SAVEPOINT '+guard);created=True
        resources=_resources(Connection(),{'capability_generation':generation})
        for resource in resources:account(resource)
    except sqlite3.Error as error:
        if uncertain_error(error):client._uncertain.add(id(connection))
        raise RelationalClientError('SQLite session catalog could not be observed; no caller transaction was ended') from None
    finally:
        cursor_cleanup_failed=False
        for cursor in cursors:
            try:cursor.close()
            except BaseException:
                cursor_cleanup_failed=True;client._uncertain.add(id(connection))
        if created:
            try:
                connection.execute('ROLLBACK TO SAVEPOINT '+guard)
                connection.execute('RELEASE SAVEPOINT '+guard)
                if restore_deferred:connection.execute('PRAGMA defer_foreign_keys=ON')
                if restore_deferred and connection.execute('PRAGMA defer_foreign_keys').fetchone()!=(1,):
                    raise RuntimeError('Native deferred-constraint setting was not restored')
                if connection.in_transaction!=original:raise RuntimeError('Native transaction state changed')
            except BaseException:
                client._uncertain.add(id(connection))
                raise RelationalClientError('SQLite session catalog cleanup is unconfirmed; close this session without replay') from None
        if cursor_cleanup_failed:
            raise RelationalClientError('SQLite catalog cursor cleanup is unconfirmed; close this session without replay') from None
    retained=[row for row in resources if include_system or not row['native'].get('system_object')]
    warnings=['Observes this retained connection, including attached databases, temporary objects and pending schema changes.',
        'Native CHECK expressions and table options remain in exact CREATE SQL.',
        'This session observation cannot authorize an independent database migration.']
    for resource in retained:
        if resource['resource_kind'] in {'database','attached-database'}:
            resource['native'].update(catalog_warnings=warnings,coverage_complete=False,
                catalog_observations=[{'section':'retained-native-catalog','available':True}])
    return annotate({'resources':retained,'generation':generation,'warnings':warnings,
        'complete':False,'consistency':'retained-connection-savepoint; attached database snapshots use native SQLite semantics'},'sqlite',session_id)


def duckdb_catalog(client, connection, session_id, *, include_system=False):
    from .duckdb.catalog import capture
    from .duckdb.driver import viability,uncertain
    try:prior=viability(connection)
    except Exception:
        client._states[id(connection)]['session_reuse_blocked']=True
        raise RelationalClientError('DuckDB session liveness is unconfirmed; close this session without replay') from None
    if prior=='aborted':
        raise RelationalClientError('Resolve the existing DuckDB transaction before observing its catalog')
    try:
        result=capture(connection,include_system=include_system,_in_transaction=True,session_scope=True)
        client._observe(connection)
        return annotate(result,'duckdb',session_id)
    except Exception as error:
        if uncertain(error) and not isinstance(error,ValueError):
            client._states[id(connection)]['session_reuse_blocked']=True
        else:
            try:client._observe(connection)
            except Exception:client._states[id(connection)]['session_reuse_blocked']=True
        raise RelationalClientError('DuckDB session catalog could not be observed; inspect its native transaction state before continuing') from None
