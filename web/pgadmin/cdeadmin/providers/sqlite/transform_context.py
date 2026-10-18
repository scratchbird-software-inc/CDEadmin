"""Independent helper contexts and immutable registered schema observations."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3

from ..embedded_route import contained_database,sqlite_arguments
from .driver import SQLiteConnection
from .provider import _initialize_connection
from .session_api import SessionAPI,SessionAPIError
import uuid


@contextmanager
def context(library,route=None):
    if route is None:connection=sqlite3.connect(':memory:',factory=SQLiteConnection)
    else:
        if contained_database(route)==':memory:':raise SessionAPIError('A registered file is required for an independent schema basis')
        selected={**route,'read_only':True,'uri_mode':'ro','isolation_level':'autocommit'}
        if any(selected.get(name) is True for name in ('uri_immutable','uri_nolock')):raise SessionAPIError('Schema snapshots require native file locking')
        connection=sqlite3.connect(**sqlite_arguments(selected),factory=SQLiteConnection)
        try:_initialize_connection(connection,selected)
        except BaseException:connection.close();raise
    try:
        connection.execute('PRAGMA query_only=ON');api=SessionAPI(connection,library)
        if api.program.get('native_session_revision',0)<3:raise SessionAPIError('The native SQLite helper lacks streaming transformation support')
        yield connection,api
    finally:connection.close()


def schema_snapshot(connection,database,*,transient=False):
    selected=next((row for row in connection.execute('PRAGMA database_list') if row[1]==database),None)
    if selected is None or not transient and not selected[2]:raise SessionAPIError('Select an attached registered file schema')
    quoted='"'+database.replace('"','""')+'"';info=Path(selected[2]).stat() if selected[2] else None
    rows=[list(row) for row in connection.execute('SELECT hex(type),hex(name),hex(tbl_name),typeof(sql),hex(sql) FROM '+quoted+'.sqlite_schema ORDER BY type,name')]
    return {'database':database,'filename':selected[2],'file_identity':None if info is None else [str(info.st_dev),str(info.st_ino)],
        'schema_version':connection.execute('PRAGMA '+quoted+'.schema_version').fetchone()[0],
        'schema_sha256':hashlib.sha256(json.dumps(rows,separators=(',',':')).encode('ascii')).hexdigest()}


def retained_snapshot(connection,api,session_id,database=None):
    if not hasattr(api,'transform_basis_id'):api.transform_basis_id=str(uuid.uuid4())
    result={'studio_session_id':session_id,'native_connection_generation':api.transform_basis_id,
        'databases':[list(row) for row in connection.execute('PRAGMA database_list')],
        'transaction_open':connection.in_transaction}
    if database is not None:result['schema']=schema_snapshot(connection,database,transient=True)
    return result


@contextmanager
def retained_context(binding,expected):
    """Reserve the original connection; native file cancellation never interrupts it."""
    client,connection,api=binding['client'],binding['handle'],binding['api']
    with client._lock:
        client._require_idle(connection)
        client._busy.add(id(connection))
    try:
        if connection._cdeadmin_session_api is not api or retained_snapshot(connection,api,
                expected['studio_session_id'],expected['schema']['database'])!=expected:
            raise SessionAPIError('The reviewed retained schema, transaction or attachments changed')
        yield connection,api
        if retained_snapshot(connection,api,expected['studio_session_id'],expected['schema']['database'])!=expected:
            raise SessionAPIError('The retained schema basis changed during native transformation')
    finally:
        with client._lock:client._busy.discard(id(connection))
