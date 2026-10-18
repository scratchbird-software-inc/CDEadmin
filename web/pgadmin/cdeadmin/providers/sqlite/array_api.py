"""Connection-owned protected CARRAY values; opaque SQLite pointers stay native."""
from contextlib import contextmanager
import atexit
import hashlib
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
from .session_api import SessionAPIError,identity,SessionAPI

_LIVE={}


def close_live():
    for api in tuple(_LIVE.values()):
        try:
            if api.owner_shutdown is not None:api.owner_shutdown()
            else:api.close_all()
        except Exception:pass


atexit.register(close_live)


def installed_library():
    name='cdeadmin_sqlite_arrays.dll' if os.name=='nt' else 'libcdeadmin_sqlite_arrays.dylib' if sys.platform=='darwin' else 'libcdeadmin_sqlite_arrays.so'
    candidates=[Path(prefix)/directory/name for prefix in dict.fromkeys((sys.prefix,sys.base_prefix)) for directory in ('bin','lib','DLLs')]
    candidates.append(Path(__file__).resolve().parents[2]/'native'/name)
    return next((str(path) for path in candidates if path.is_file() and Path(str(path)+'.json').is_file()),'')


class ArrayAPI:
    def __init__(self,connection,filename,owner_shutdown=None):
        if not hasattr(connection,'_cdeadmin_array_api') or connection._cdeadmin_array_api is not None:
            raise SessionAPIError('The retained query connection already has an array controller or lacks native ownership')
        source,self.program=identity(filename,'array');self.connection=connection;self.owner_shutdown=owner_shutdown
        self.token=secrets.token_bytes(32);self.arrays={}
        self.program['execution_host']={'kind':'application-host','hostname':socket.gethostname(),'platform':sys.platform}
        directory=Path(tempfile.mkdtemp(prefix='scratchrobin-sqlite-arrays-'));private_directory(directory);target=directory/source.name
        try:
            hashed=hashlib.sha256()
            with source.open('rb') as incoming,target.open('xb') as outgoing:
                private_file(target)
                while block:=incoming.read(1048576):outgoing.write(block);hashed.update(block)
                outgoing.flush();os.fsync(outgoing.fileno())
            if hashed.hexdigest()!=self.program['library_sha256']:raise SessionAPIError('Native array helper changed before loading')
            connection._cdeadmin_extension_directories.append(str(directory))
            with self.internal():
                before={row[0] for row in connection.execute('PRAGMA function_list')}
                try:
                    connection.enable_load_extension(False);connection.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION,True)
                    connection.load_extension(str(target),entrypoint='sqlite3_cdeadminarrays_init')
                finally:
                    connection.enable_load_extension(False)
                    if connection.getconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION):raise SessionAPIError('Native array loader cleanup is unconfirmed')
                added={row[0] for row in connection.execute('PRAGMA function_list')}-before
                names={}
                for kind in ('bind','call','value'):
                    matched=[name for name in added if isinstance(name,str) and re.fullmatch('_cdeadmin_array_'+kind+'_[0-9a-f]{32}',name)]
                    if len(matched)!=1:raise SessionAPIError('Native array control registration is unconfirmed')
                    names[kind]=matched[0]
                if len({name.rsplit('_',1)[1] for name in names.values()})!=1:raise SessionAPIError('Native array alias ownership differs')
                self._bind_name,self._call_name,self.getter_name=(names[kind] for kind in ('bind','call','value'))
                SessionAPI.checked(connection.execute('SELECT "'+self._bind_name+'"(?)',(self.token,)).fetchone()[0])
                self.program.update(self.call('identity'))
        except BaseException:
            if str(directory) not in connection._cdeadmin_extension_directories:shutil.rmtree(directory)
            raise
        connection._cdeadmin_array_api=self

    @contextmanager
    def internal(self):
        scope=self.connection._cdeadmin_internal_sql;previous=getattr(scope,'array_api',False);scope.array_api=True
        try:yield
        finally:scope.array_api=previous

    def call(self,operation,*arguments):
        values=(self.token,operation,*arguments)
        with self.internal():
            return SessionAPI.checked(self.connection.execute('SELECT "'+self._call_name+'"('+','.join('?' for _value in values)+')',values).fetchone()[0])

    def create(self,kind,count,payload):
        if type(kind) is not int or not 0<=kind<=4 or type(count) is not int or not 0<=count<=2147483647 or not isinstance(payload,bytes):
            raise SessionAPIError('Select exact native array type, count and encoded values')
        identity=str(uuid.uuid4());_LIVE[id(self.connection)]=self
        try:self.call('create',identity,kind,count,payload)
        except BaseException:
            if not self.arrays:_LIVE.pop(id(self.connection),None)
            raise
        self.arrays[identity]={'array_id':identity};return self.status(identity)

    def status(self,identity):
        if identity not in self.arrays:raise SessionAPIError('Native array belongs to another or closed query connection')
        return {**self.arrays[identity],**self.call('status',identity)}

    def expression(self,identity):
        if identity not in self.arrays:raise SessionAPIError('Native array belongs to another or closed query connection')
        return '"'+self.getter_name+'"(\''+identity+'\')'

    def close(self,identity):
        if identity not in self.arrays:raise SessionAPIError('Native array belongs to another or closed query connection')
        self.call('close',identity);self.arrays.pop(identity)
        if not self.arrays:_LIVE.pop(id(self.connection),None)

    def close_all(self):
        previous=self.connection._cdeadmin_authorizer
        try:self.connection.set_authorizer(None);self.call('close_all')
        finally:self.connection.set_authorizer(previous)
        self.arrays.clear();_LIVE.pop(id(self.connection),None)
