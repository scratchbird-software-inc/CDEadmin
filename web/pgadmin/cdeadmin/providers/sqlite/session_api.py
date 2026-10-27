"""Connection-owned public SQLite session APIs and private streaming descriptors."""
from contextlib import contextmanager
import atexit
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import sqlite3
import sys
import tempfile
import uuid

from ...operations.fileio import private_directory,private_file


class SessionAPIError(ValueError):
    def __init__(self,message,code=None):
        super().__init__(message if code is None else message+' (SQLite code '+str(code)+')');self.native_result_code=code


# Keep connections with live native sessions alive until their explicit cleanup.
# SQLite requires sqlite3session_delete() before sqlite3_close().
_LIVE={}


def close_live():
    for controller in tuple(_LIVE.values()):
        try:
            if controller.owner_shutdown is not None:controller.owner_shutdown()
            else:controller.close_all()
        except Exception:pass  # Keep failed ownership pinned; never force-close.


atexit.register(close_live)


def installed_library():
    name=('cdeadmin_sqlite_sessions.dll' if os.name=='nt' else
        'libcdeadmin_sqlite_sessions.dylib' if sys.platform=='darwin' else 'libcdeadmin_sqlite_sessions.so')
    candidates=[Path(prefix)/folder/name for prefix in dict.fromkeys((sys.prefix,sys.base_prefix)) for folder in ('bin','lib','DLLs')]
    candidates.append(Path(__file__).resolve().parents[2]/'native'/name)
    return next((str(path) for path in candidates if path.is_file() and Path(str(path)+'.json').is_file()),'')


def identity(filename,component='session'):
    if not filename:raise SessionAPIError('The native SQLite '+component+' helper is not installed')
    path=Path(filename).resolve(strict=True);metadata=Path(str(path)+'.json')
    if not path.is_file() or metadata.stat().st_size>65536:raise SessionAPIError('Native SQLite '+component+' helper metadata is unavailable')
    value=json.loads(metadata.read_text(encoding='utf8'))
    if not isinstance(value,dict) or value.get('adapter_abi')!=1 or value.get('sqlite_version')!='3.53.0':
        raise SessionAPIError('Native SQLite '+component+' helper ABI or version differs')
    digest=hashlib.sha256()
    with path.open('rb') as source:
        while block:=source.read(1048576):digest.update(block)
    if digest.hexdigest()!=value.get('library_sha256'):raise SessionAPIError('Native SQLite '+component+' helper differs from its provenance')
    return path,{'adapter_abi':1,'sqlite_version':'3.53.0','library_sha256':digest.hexdigest()}


class SessionAPI:
    def __init__(self,connection,filename,*,owner_shutdown=None):
        if not hasattr(connection,'_cdeadmin_internal_sql') or not isinstance(getattr(connection,'_cdeadmin_extension_directories',None),list):
            raise SessionAPIError('Native session APIs require a driver-owned SQLite connection')
        if getattr(connection,'_cdeadmin_session_api',None) is not None:
            raise SessionAPIError('This SQLite connection already owns its native session controller')
        if not all(callable(getattr(connection,name,None)) for name in ('getconfig','setconfig','load_extension')):
            raise SessionAPIError('The native SQLite binding lacks its controlled library loader')
        source,self.program=identity(filename);self.connection=connection;self.token=secrets.token_bytes(32);self.captures={}
        self.owner_shutdown=owner_shutdown
        self.program['execution_host']={'kind':'application-host','hostname':socket.gethostname(),'platform':sys.platform}
        directory=Path(tempfile.mkdtemp(prefix='scratchrobin-sqlite-sessions-'));private_directory(directory)
        staged=directory/source.name
        try:
            with source.open('rb') as incoming,staged.open('xb') as target:
                private_file(staged);digest=hashlib.sha256()
                while block:=incoming.read(1048576):target.write(block);digest.update(block)
                target.flush();os.fsync(target.fileno())
            if digest.hexdigest()!=self.program['library_sha256']:raise SessionAPIError('Native SQLite session helper changed before loading')
            connection._cdeadmin_extension_directories.append(str(directory))
            with self.internal():
                before={row[0] for row in connection.execute('PRAGMA function_list')}
                try:
                    connection.enable_load_extension(False)
                    connection.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION,True)
                    connection.load_extension(str(staged),entrypoint='sqlite3_cdeadminsessions_init')
                finally:
                    connection.enable_load_extension(False)
                    if connection.getconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION):
                        raise SessionAPIError('Native SQLite library loader cleanup is unconfirmed')
                added={row[0] for row in connection.execute('PRAGMA function_list')}-before
                binding=[name for name in added if isinstance(name,str) and re.fullmatch(r'_cdeadmin_session_bind_[0-9a-f]{32}',name)]
                calling=[name for name in added if isinstance(name,str) and re.fullmatch(r'_cdeadmin_session_call_[0-9a-f]{32}',name)]
                if len(binding)!=1 or len(calling)!=1 or binding[0].rsplit('_',1)[1]!=calling[0].rsplit('_',1)[1]:
                    raise SessionAPIError('Native session control registration is unconfirmed')
                self._bind_name,self._call_name=binding[0],calling[0]
                value=connection.execute('SELECT "'+self._bind_name+'"(?)',(self.token,)).fetchone()[0]
                self.checked(value)
                self.program.update(self.call('identity'))
        except BaseException:
            # Loaded libraries remain staged until connection closure, including
            # Windows DLLs. Unregistered staging can be removed immediately.
            if str(directory) not in connection._cdeadmin_extension_directories:shutil.rmtree(directory)
            raise
        connection._cdeadmin_session_api=self

    @contextmanager
    def internal(self):
        scope=self.connection._cdeadmin_internal_sql
        previous=getattr(scope,'session_api',False);scope.session_api=True
        try:yield
        finally:scope.session_api=previous

    @staticmethod
    def checked(value):
        if isinstance(value,str):
            result=json.loads(value)
            if 'native_result_code' in result:raise SessionAPIError(result['message'],result['native_result_code'])
            return result
        return value

    def call(self,operation,*arguments):
        parameters=(self.token,operation,*arguments)
        with self.internal():
            return self.checked(self.connection.execute('SELECT "'+self._call_name+'"('+','.join('?' for _ in parameters)+')',parameters).fetchone()[0])

    def open(self,database,*,estimate_size=False,track_rowids=False):
        if not isinstance(database,str) or not database or '\x00' in database or type(estimate_size) is not bool or type(track_rowids) is not bool:
            raise SessionAPIError('Select an exact native database name and session switches')
        hook=getattr(self.connection,'_cdeadmin_preupdate_api',None)
        if hook is not None and hook.status()['enabled']:
            raise SessionAPIError('Stop the independent native preupdate hook before opening a session capture')
        session_id=str(uuid.uuid4());_LIVE[id(self.connection)]=self
        try:self.call('open',session_id,database,int(estimate_size),int(track_rowids))
        except BaseException:
            if not self.captures:_LIVE.pop(id(self.connection),None)
            raise
        self.captures[session_id]={'capture_id':session_id,'database':database,'estimate_size':estimate_size,'track_rowids':track_rowids,'tables':[]}
        return session_id

    def attach(self,session_id,table):
        if session_id not in self.captures:raise SessionAPIError('Native capture belongs to another or closed connection')
        if table is not None and (not isinstance(table,str) or not table or '\x00' in table):raise SessionAPIError('Select a native table name or all tables')
        self.call('attach',session_id,table)
        if table not in self.captures[session_id]['tables']:self.captures[session_id]['tables'].append(table)

    def table_filter(self,session_id,pattern,exclude=False):
        if session_id not in self.captures:raise SessionAPIError('Native capture belongs to another or closed connection')
        if self.program.get('native_session_revision',0)<5:raise SessionAPIError('The native session helper lacks table filter controls; reconnect with the current bridge')
        if (pattern is not None and (not isinstance(pattern,str) or '\x00' in pattern)) or type(exclude) is not bool or (pattern is None and exclude):
            raise SessionAPIError('Select a native SQLite GLOB filter or all future tables')
        self.call('table_filter',session_id,pattern,int(exclude))
        self.captures[session_id]['table_filter']={'pattern':pattern,'exclude':exclude,'automatic_attachment':True}

    def diff(self,session_id,source_database,table_name):
        if session_id not in self.captures:raise SessionAPIError('Native capture belongs to another or closed connection')
        if any(not isinstance(value,str) or not value or '\x00' in value for value in (source_database,table_name)):
            raise SessionAPIError('Select an attached native source database and exact table name')
        self.call('diff',session_id,source_database,table_name)
        if table_name not in self.captures[session_id]['tables']:self.captures[session_id]['tables'].append(table_name)

    def status(self,session_id):
        if session_id not in self.captures:raise SessionAPIError('Native capture belongs to another or closed connection')
        return {**self.captures[session_id],**self.call('status',session_id),
            'table_attachment_scope':'Explicit attachment/diff requests; SQLite does not expose an iterator over automatic session attachments'}

    def export(self,session_id,kind,descriptor,cancel_descriptor=-1):
        if session_id not in self.captures:raise SessionAPIError('Native capture belongs to another or closed connection')
        if kind not in {'changeset','patchset'} or type(descriptor) is not int or descriptor<0 or type(cancel_descriptor) is not int or cancel_descriptor<-1:
            raise SessionAPIError('Select a native changeset/patchset and owned streaming descriptors')
        return self.call('export',session_id,kind,descriptor,cancel_descriptor)

    def close(self,session_id):
        if session_id not in self.captures:raise SessionAPIError('Native capture belongs to another or closed connection')
        self.call('close',session_id);self.captures.pop(session_id)
        if not self.captures:_LIVE.pop(id(self.connection),None)

    def close_all(self):
        # Cleanup only deletes connection-owned session objects. It must remain
        # possible after the caller revokes SQL/SELECT authorization. The driver
        # serializes this operation after its statement workers have stopped.
        previous=self.connection._cdeadmin_authorizer
        try:
            self.connection.set_authorizer(None)
            self.call('close_all')
        finally:self.connection.set_authorizer(previous)
        self.captures.clear();_LIVE.pop(id(self.connection),None)
