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


def schema_snapshot(connection,database):
    selected=next((row for row in connection.execute('PRAGMA database_list') if row[1]==database),None)
    if selected is None or not selected[2]:raise SessionAPIError('Select an attached registered file schema')
    quoted='"'+database.replace('"','""')+'"';info=Path(selected[2]).stat()
    rows=[list(row) for row in connection.execute('SELECT hex(type),hex(name),hex(tbl_name),typeof(sql),hex(sql) FROM '+quoted+'.sqlite_schema ORDER BY type,name')]
    return {'database':database,'filename':selected[2],'file_identity':[str(info.st_dev),str(info.st_ino)],
        'schema_version':connection.execute('PRAGMA '+quoted+'.schema_version').fetchone()[0],
        'schema_sha256':hashlib.sha256(json.dumps(rows,separators=(',',':')).encode('ascii')).hexdigest()}
