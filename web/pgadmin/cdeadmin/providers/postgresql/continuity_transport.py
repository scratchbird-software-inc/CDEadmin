"""Sealed native connection material for a single reviewed continuity job."""
from contextlib import contextmanager
from types import SimpleNamespace

from ...security import SecretLease
from .continuity import ContinuityError


class ContinuityTransport:
    def __init__(self, parameters, *, ssh=None, secrets=None):
        self._parameters = dict(parameters)
        self._ssh = ssh
        self._secrets = {key:SecretLease(value) for key,value in (secrets or {}).items() if value}
        self.closed = False

    def __repr__(self):
        return '<PostgreSQL continuity transport closed={}>'.format(self.closed)

    @contextmanager
    def parameters(self):
        if self.closed:raise ContinuityError('Native continuity credentials were released')
        tunnel = None
        values = dict(self._parameters)
        try:
            for kind,key in (('database_password','password'),('tls_private_key_password','sslpassword')):
                if kind in self._secrets:values[key]=self._secrets[kind].use(lambda value:bytes(value).decode('utf8'))
            if self._ssh:
                from .monitoring_ssh import MonitoringSSHTunnel
                references = {kind:'continuity-'+kind for kind in self._secrets if kind.startswith('ssh_')}
                route = {'ssh':self._ssh, 'credential_references':references,'principal_reference':'continuity-job'}
                def acquire(reference,principal,purpose,kind):
                    if (principal!='continuity-job' or purpose!='connect' or
                            reference!=references.get(kind) or kind not in self._secrets):
                        raise ContinuityError('Continuity transport credential scope changed')
                    return self._secrets[kind].use(lambda value:SecretLease(value))
                tunnel = MonitoringSSHTunnel(SimpleNamespace(acquire_secret=acquire),route)
                values.update(port=tunnel.start(),hostaddr='127.0.0.1')
            yield values
        finally:
            values.clear()
            if tunnel is not None:tunnel.close()

    def close(self):
        for lease in self._secrets.values():lease.close()
        self._parameters.clear()
        self.closed=True


def replication_identity(parameters):
    """Observe the authenticated native replication peer without SQL execution."""
    import psycopg
    from psycopg.rows import tuple_row
    options = {key:value for key,value in parameters.items() if key not in {'service','passfile','replication'}}
    options.update(replication='true',autocommit=True,connect_timeout=5,application_name='ScratchRobin backup admission')
    try:
        with psycopg.connect(**options) as connection:
            with psycopg.ClientCursor(connection,row_factory=tuple_row) as cursor:
                cursor.execute('IDENTIFY_SYSTEM')
                identity,timeline,lsn,_database=cursor.fetchone()
                # Replication protocol columns have unspecified OIDs. libpq
                # returns their text as bytes rather than SQL typed values.
                identity=identity.decode('ascii') if isinstance(identity,bytes) else str(identity)
                lsn=lsn.decode('ascii') if isinstance(lsn,bytes) else str(lsn)
                version=connection.info.server_version
        if version!=180003:raise ContinuityError('Physical backup requires the selected PostgreSQL 18.3 runtime')
        if not str(identity).isdigit() or not 0<int(identity)<2**64:
            raise ContinuityError('Native replication system identity is unavailable')
        return {'system_identifier':str(identity),'timeline':int(timeline),'lsn':str(lsn),'server_version':version}
    except psycopg.Error as error:
        raise ContinuityError('Native replication admission failed ('+(error.sqlstate or type(error).__name__)+')') from None


def capture(provider, route, *, server=None):
    """Freeze a private attachment in the admitting request, then release it."""
    from psycopg import Cursor
    from psycopg.rows import tuple_row
    provider.permissions.require('backup_admin')
    provider.permissions.require('secret_read')
    opened = provider.open_session({'route':route})
    transport = None
    try:
        state=provider._sessions[opened['session_id']]
        provider._ensure_native_connection(state)
        connection=state.connection.conn
        with Cursor(connection,row_factory=tuple_row) as cursor:
            cursor.execute("SELECT current_user,session_user,current_setting('summarize_wal'),version()")
            current,authenticated,summarize,version=cursor.fetchone()
            if current!=authenticated:
                raise ContinuityError('Physical replication requires an explicitly registered replication principal; SQL SET ROLE cannot govern this protocol')
            cursor.execute('SELECT oid,spcname,pg_catalog.pg_tablespace_location(oid) FROM pg_catalog.pg_tablespace ORDER BY oid')
            tablespaces=[{'oid':int(oid),'name':name,'location':location} for oid,name,location in cursor]
        info=connection.info
        parameters={key:value for key,value in info.get_parameters().items()
                    if key not in {'service','passfile','replication','fallback_application_name'}}
        # Freeze the selected peer instead of repeating a multihost/service
        # search after the review. Keep its hostname for certificate checking.
        parameters.update(host=info.host,port=info.port,user=info.user,dbname=info.dbname,
                          application_name='ScratchRobin physical backup')
        if info.hostaddr:parameters['hostaddr']=info.hostaddr
        secrets={}
        password=connection.pgconn.password
        if password:secrets['database_password']=password
        tls=parameters.pop('sslpassword',None)
        if tls:secrets['tls_private_key_password']=tls
        ssh=None
        if server is not None and server.use_ssh_tunnel:
            # This is only the existing peer-pinned transport admission helper;
            # no collector, monitoring policy or history store is invoked.
            from ...workspace.postgresql_monitoring_host import PostgreSQLMonitoringHost
            ssh,ssh_secrets=PostgreSQLMonitoringHost._ssh_admission(server,state.manager)
            secrets.update(ssh_secrets)
        transport=ContinuityTransport(parameters,ssh=ssh,secrets=secrets)
        with transport.parameters() as native:
            identity=replication_identity(native)
        source={**identity,'authenticated_principal':authenticated,'summarize_wal':summarize,
                'native_build':version,'tablespaces':tablespaces,
                'host':server.host if server is not None else info.host,
                'port':server.port if server is not None else info.port}
        return source,transport
    except BaseException:
        if transport is not None:transport.close()
        raise
    finally:
        try:provider.close_session(opened)
        except BaseException:
            if transport is not None:transport.close()
            raise
