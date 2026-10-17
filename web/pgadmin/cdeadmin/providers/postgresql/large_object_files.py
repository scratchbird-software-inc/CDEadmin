"""Owned PostgreSQL large-object file transfers, independent of editor sessions."""
import hashlib
import re

from .continuity_transport import ContinuityTransport
from .large_objects import CHUNK_BYTES, MAX_LENGTH


class LargeObjectFileError(ValueError):
    pass


def decimal(value,label,maximum=MAX_LENGTH,minimum=0):
    if not isinstance(value,str) or not re.fullmatch(r'0|[1-9][0-9]{0,19}',value) or not minimum<=int(value)<=maximum:
        raise LargeObjectFileError(label+' requires exact bounded decimal text')
    return int(value)


def options(value):
    if not isinstance(value,dict) or set(value)-{'operation','oid','length','filename'}:
        raise LargeObjectFileError('Invalid PostgreSQL file transfer options')
    operation=value.get('operation')
    if operation not in {'import','export'}:raise LargeObjectFileError('Select native large-object import or export')
    oid=decimal(value.get('oid','0'),'Large-object OID',2**32-1,minimum=0 if operation=='import' else 1)
    filename=value.get('filename')
    try:filename_bytes=filename.encode('utf8') if isinstance(filename,str) else b''
    except UnicodeError:raise LargeObjectFileError('Client filename requires valid UTF-8 text') from None
    if (not isinstance(filename,str) or not filename or any(ord(char)<32 or char in '/\\\x7f' for char in filename)
        or len(filename_bytes)>255 or filename in {'.','..'}):
        raise LargeObjectFileError('Select a bounded client filename without directory components')
    result={'operation':operation,'oid':str(oid),'filename':filename}
    if operation=='import':result['length']=str(decimal(value.get('length'),'File length'))
    elif 'length' in value:raise LargeObjectFileError('Native export determines its own file length')
    return result


def cursor(connection):
    from psycopg import Cursor
    from psycopg.rows import tuple_row
    return Cursor(connection,row_factory=tuple_row)


def identity(connection):
    with cursor(connection) as query:
        query.execute("SELECT current_setting('server_version_num'),current_database(),"
            "(SELECT oid::text FROM pg_catalog.pg_database WHERE datname=current_database()),"
            "session_user,current_user,extract(epoch FROM pg_catalog.pg_postmaster_start_time())::text,"
            "inet_server_addr()::text,inet_server_port()::text")
        row=query.fetchone()
    if int(row[0])!=180003:raise LargeObjectFileError('File transfers require the selected native PostgreSQL 18.3 profile')
    return dict(zip(('server_version','database','database_oid','authenticated_principal','effective_principal',
                     'postmaster_started_epoch','server_address','server_port'),(str(v) if v is not None else None for v in row)))


def capture(provider,route,server):
    """Seal a private attachment while the admitting request owns its context."""
    provider.permissions.require('execute');provider.permissions.require('secret_read')
    opened=provider.open_session({'route':route});transport=None
    try:
        state=provider._sessions[opened['session_id']];provider._ensure_native_connection(state)
        native=state.connection.conn
        source=identity(native);info=native.info
        parameters={key:value for key,value in info.get_parameters().items() if key not in
                    {'service','passfile','replication','fallback_application_name'}}
        parameters.update(host=info.host,port=info.port,user=info.user,dbname=info.dbname,
                          application_name='ScratchRobin large-object files')
        if info.hostaddr:parameters['hostaddr']=info.hostaddr
        secrets={};password=native.pgconn.password
        if password:secrets['database_password']=password
        password=parameters.pop('sslpassword',None)
        if password:secrets['tls_private_key_password']=password
        ssh=None
        if server.use_ssh_tunnel:
            from ...workspace.postgresql_monitoring_host import PostgreSQLMonitoringHost
            ssh,values=PostgreSQLMonitoringHost._ssh_admission(server,state.manager);secrets.update(values)
        transport=ContinuityTransport(parameters,ssh=ssh,secrets=secrets)
        return source,transport
    except BaseException:
        if transport is not None:transport.close()
        raise
    finally:
        try:provider.close_session(opened)
        except BaseException:
            if transport is not None:transport.close()
            raise


def attach(parameters,source):
    import psycopg
    from psycopg import sql
    from psycopg.types.string import ByteaLoader
    connection=psycopg.connect(**{**parameters,'connect_timeout':5},autocommit=True)
    try:
        # pgAdmin installs display loaders globally. File transfer bytes must
        # retain native bytea semantics on this separately owned connection.
        connection.adapters.register_loader(17,ByteaLoader)
        if source['effective_principal']!=source['authenticated_principal']:
            with cursor(connection) as query:query.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(source['effective_principal'])))
        if identity(connection)!=source:raise LargeObjectFileError('Native large-object transfer identity changed after review')
        return connection
    except BaseException:connection.close();raise


def metadata(connection,oid):
    with cursor(connection) as query:
        query.execute('SELECT oid::text,lomowner::text,lomacl::text,xmin::text,ctid::text FROM pg_catalog.pg_largeobject_metadata WHERE oid=%s::oid',(oid,))
        row=query.fetchone()
        if row is None:raise LargeObjectFileError('Native large object is unavailable')
        result=dict(zip(('oid','owner_oid','privileges','row_transaction','row_location'),row))
        # The descriptor functions apply native LO SELECT permission, including
        # lo_compat_privileges. Seeking does not allocate sparse object pages.
        query.execute('SELECT pg_catalog.lo_open(%s::oid,262144)',(oid,));fd=int(query.fetchone()[0])
        try:
            query.execute('SELECT pg_catalog.lo_lseek64(%s,0,2)',(fd,));result['length']=str(query.fetchone()[0])
        finally:query.execute('SELECT pg_catalog.lo_close(%s)',(fd,))
    decimal(result['length'],'Native large-object length')
    return result


def read_chunks(connection,oid,length,*,cancel=None,progress=None):
    size=decimal(length,'Native large-object length');offset=0
    with cursor(connection) as query:
        while offset<size:
            if cancel is not None and cancel.is_set():raise InterruptedError('File transfer cancellation requested')
            count=min(CHUNK_BYTES,size-offset)
            query.execute('SELECT pg_catalog.lo_get(%s::oid,%s::bigint,%s::integer)',(oid,offset,count))
            data=bytes(query.fetchone()[0])
            if len(data)!=count:raise LargeObjectFileError('Native large-object read returned an unexpected length')
            offset+=count
            if progress is not None:progress(offset)
            yield data


def import_file(connection,stream,selected,expected_sha256,*,cancel=None,progress=None,created=None,verifying=None):
    size=decimal(selected['length'],'File length');checksum=hashlib.sha256();offset=0
    with cursor(connection) as query:
        query.execute('SELECT pg_catalog.lo_create(%s::oid),pg_catalog.pg_current_xact_id()::text',(selected['oid'],))
        oid,transaction=query.fetchone();oid=str(oid)
        if created is not None:created(oid,str(transaction))
        while offset<size:
            if cancel is not None and cancel.is_set():raise InterruptedError('File transfer cancellation requested')
            data=stream.read(min(CHUNK_BYTES,size-offset))
            if not data:raise LargeObjectFileError('Staged import ended before its reviewed length')
            query.execute('SELECT pg_catalog.lo_put(%s::oid,%s::bigint,%s::bytea)',(oid,offset,data))
            checksum.update(data);offset+=len(data)
            if progress is not None:progress(offset)
        if stream.read(1) or checksum.hexdigest()!=expected_sha256:
            raise LargeObjectFileError('Staged import changed after review')
    observed=hashlib.sha256()
    for data in read_chunks(connection,oid,str(size),cancel=cancel,progress=verifying):observed.update(data)
    if observed.hexdigest()!=expected_sha256:raise LargeObjectFileError('Native large-object checksum differs before commit')
    return {'oid':oid,'transaction_id':str(transaction),'length':str(size),'sha256':observed.hexdigest(),
            'native_postimage_verified':True}
