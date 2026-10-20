"""Physical replication admission without opening a SQL database connection."""
import re

from .continuity import ContinuityError
from .continuity_transport import ContinuityTransport


def _text(value):
    return value.decode('ascii') if isinstance(value, bytes) else str(value)


def _bytes(value):
    match = re.fullmatch(r'([1-9][0-9]*)\s*(B|kB|MB|GB)?', _text(value))
    if match is None:
        raise ContinuityError('Native WAL geometry is unavailable')
    return int(match[1]) * {'B': 1, 'kB': 1024, 'MB': 1024**2, 'GB': 1024**3, None: 1}[match[2]]


def capture(parameters):
    """Authenticate one physical walsender and seal its resolved native peer.

    IDENTIFY_SYSTEM and SHOW are replication commands here. No SQL session,
    catalog SELECT, SET ROLE, implicit reconnect or caller transaction is used.
    """
    import psycopg
    from psycopg.rows import tuple_row
    options = dict(parameters)
    options.update(replication='true', autocommit=True, connect_timeout=5,
                   application_name='ScratchRobin replication-only WAL admission')
    transport = None
    try:
        with psycopg.connect(**options) as connection:
            if connection.info.server_version != 180003:
                raise ContinuityError('Replication admission requires PostgreSQL 18.3')
            with psycopg.ClientCursor(connection, row_factory=tuple_row) as cursor:
                cursor.execute('IDENTIFY_SYSTEM')
                identity, timeline, lsn, database = cursor.fetchone()
                if database is not None:
                    raise ContinuityError('A physical replication connection is required')
                identity, lsn = _text(identity), _text(lsn)
                if not identity.isdigit() or not 0 < int(identity) < 2**64:
                    raise ContinuityError('Native replication system identity is unavailable')
                if not re.fullmatch(r'[0-9A-F]+/[0-9A-F]+', lsn) or int(timeline) < 1:
                    raise ContinuityError('Native replication position is unavailable')
                settings = {}
                for name in ('wal_segment_size', 'wal_block_size'):
                    cursor.execute('SHOW ' + name)
                    settings[name] = _bytes(cursor.fetchone()[0])
            info = connection.info
            resolved = {key: value for key, value in info.get_parameters().items()
                        if key not in {'service', 'passfile', 'replication', 'fallback_application_name'}}
            resolved.update(host=info.host, port=info.port, user=info.user, dbname=info.dbname)
            if info.hostaddr:
                resolved['hostaddr'] = info.hostaddr
            secrets = {}
            password = connection.pgconn.password
            if password:
                secrets['database_password'] = password
            tls_password = resolved.pop('sslpassword', None)
            if tls_password:
                secrets['tls_private_key_password'] = tls_password
            # Password is never retained among public parameters or receipts.
            resolved.pop('password', None)
            source = {'system_identifier': identity, 'timeline': int(timeline), 'lsn': lsn,
                      'server_version': info.server_version, 'authenticated_principal': info.user,
                      'host': info.host, 'port': info.port, 'admission_interface': 'physical-replication',
                      'sql_admission_performed': False, 'tablespace_catalog_observed': False,
                      'wal_segment_bytes': settings['wal_segment_size'],
                      'wal_block_bytes': settings['wal_block_size']}
            transport = ContinuityTransport(resolved, secrets=secrets)
        return source, transport
    except psycopg.Error as error:
        if transport is not None:
            transport.close()
        raise ContinuityError('Native replication admission failed (' +
                              (error.sqlstate or type(error).__name__) + ')') from None
    except BaseException:
        if transport is not None:
            transport.close()
        raise


def registered(server, request):
    """Resolve the saved registration, keeping credential material request-local."""
    from psycopg.conninfo import conninfo_to_dict
    from pgadmin.utils.driver.registry import DriverRegistry
    if not isinstance(request, dict) or set(request) - {'password'}:
        raise ContinuityError('Select registered physical replication credentials')
    password = request.get('password')
    if password is not None and (not isinstance(password, str) or '\x00' in password or len(password) > 8192):
        raise ContinuityError('Invalid physical replication credential')
    if server.role:
        raise ContinuityError('Physical replication cannot apply SQL SET ROLE; register the replication principal directly')
    if server.use_ssh_tunnel:
        raise ContinuityError('Replication-only SSH admission requires a separate peer-pinned tunnel; use the connected SQL route for this registration')
    manager = DriverRegistry.get('psycopg3').connection_manager(server.id)
    if password is None:
        encrypted = getattr(manager, 'password', None) or server.password
        if encrypted:
            from pgadmin.utils.master_password import get_crypt_key
            from pgadmin.utils.crypto import decrypt
            present, key = get_crypt_key()
            if not present:
                raise ContinuityError('Registered replication credential authority is unavailable')
            password = decrypt(encrypted, key)
    # Constructing conninfo resolves registered options and storage paths. It
    # does not invoke the SQL driver's connect() or its role/bootstrap queries.
    parameters = conninfo_to_dict(manager.create_connection_string(manager.db, server.username, password))
    # Native connection options may select a libpq service's principal. Record
    # the actual authenticated startup user; never invent SQL role authority.
    return capture(parameters)
