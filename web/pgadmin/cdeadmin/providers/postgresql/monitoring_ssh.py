"""An independently owned, peer-pinned SSH transport for PostgreSQL collection."""
import base64
import io
import logging
from contextlib import ExitStack


class MonitoringSSHError(RuntimeError):
    pass


def validate_ssh_route(value):
    required = {'host', 'port', 'username', 'remote_host', 'remote_port',
                'host_key_type', 'host_key', 'authentication', 'keep_alive'}
    if not isinstance(value, dict) or set(value) != required:
        raise MonitoringSSHError('Invalid monitoring SSH route')
    for name in ('host', 'username', 'remote_host', 'host_key_type'):
        if not isinstance(value[name], str) or not value[name] or '\x00' in value[name] or len(value[name]) > 1024:
            raise MonitoringSSHError('Invalid monitoring SSH identity')
    for name in ('port', 'remote_port'):
        if type(value[name]) is not int or not 1 <= value[name] <= 65535:
            raise MonitoringSSHError('Invalid monitoring SSH port')
    if type(value['keep_alive']) is not int or not 0 <= value['keep_alive'] <= 3600:
        raise MonitoringSSHError('Invalid monitoring SSH keepalive')
    if value['authentication'] not in {'password', 'private_key'}:
        raise MonitoringSSHError('Unsupported monitoring SSH authentication')
    try:
        if not isinstance(value['host_key'], str) or len(value['host_key']) > 32768:
            raise ValueError()
        key = base64.b64decode(value['host_key'], validate=True)
        if not key or len(key) > 16384:
            raise ValueError()
        import paramiko
        paramiko.PKey.from_type_string(value['host_key_type'], key)
    except Exception:
        raise MonitoringSSHError('Monitoring SSH peer key is unavailable') from None
    return value


def ssh_secret_kinds(route):
    ssh = validate_ssh_route(route['ssh'])
    required = {'ssh_password'} if ssh['authentication'] == 'password' else {'ssh_private_key'}
    optional = {'ssh_private_key_password'} if ssh['authentication'] == 'private_key' else set()
    return required, optional


class MonitoringSSHTunnel:
    def __init__(self, permissions, route, *, forwarder_factory=None):
        self.permissions = permissions
        self.route = route
        self.ssh = validate_ssh_route(route['ssh'])
        self._factory = forwarder_factory
        self._forwarder = None

    def start(self):
        import paramiko
        from sshtunnel import SSHTunnelForwarder
        ssh = self.ssh
        references = self.route.get('credential_references', {})
        required, _ = ssh_secret_kinds(self.route)
        if not required <= references.keys():
            raise MonitoringSSHError('Monitoring SSH credential is unavailable')
        try:
            with ExitStack() as stack:
                def secret(kind):
                    lease = stack.enter_context(self.permissions.acquire_secret(
                        references[kind], self.route['principal_reference'], 'connect', kind))
                    value = lease.use(bytes)
                    maximum = 1024 * 1024 if kind == 'ssh_private_key' else 4096
                    if not value or len(value) > maximum:
                        raise MonitoringSSHError('Invalid monitoring SSH credential')
                    return value.decode('utf8')
                credentials = {}
                if ssh['authentication'] == 'password':
                    credentials['ssh_password'] = secret('ssh_password')
                else:
                    text = secret('ssh_private_key')
                    password = secret('ssh_private_key_password') if 'ssh_private_key_password' in references else None
                    key = None
                    for key_class in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey, paramiko.DSSKey):
                        try:
                            key = key_class.from_private_key(io.StringIO(text), password=password)
                            break
                        except (paramiko.SSHException, ValueError):
                            continue
                    if key is None:
                        raise MonitoringSSHError('Monitoring SSH key could not be opened')
                    credentials['ssh_pkey'] = key
                logger = logging.getLogger('scratchrobin.monitoring.ssh')
                if not logger.handlers:
                    logger.addHandler(logging.NullHandler())
                logger.propagate = False
                logger.setLevel(logging.CRITICAL)
                peer = paramiko.PKey.from_type_string(ssh['host_key_type'], base64.b64decode(ssh['host_key']))
                self._forwarder = (self._factory or SSHTunnelForwarder)(
                    (ssh['host'], ssh['port']), ssh_username=ssh['username'], ssh_host_key=peer,
                    remote_bind_address=(ssh['remote_host'], ssh['remote_port']),
                    local_bind_address=('127.0.0.1', 0), set_keepalive=ssh['keep_alive'],
                    allow_agent=False, host_pkey_directories=[], ssh_config_file=None,
                    ssh_proxy_enabled=False, logger=logger, **credentials)
                self._forwarder.daemon_forward_servers = True
                self._forwarder.start()
                if not self._forwarder.is_active:
                    raise MonitoringSSHError('Monitoring SSH tunnel did not start')
                return self._forwarder.local_bind_port
        except Exception:
            # The owner retains this object and must confirm close even when
            # startup created only part of a transport. Never log credentials.
            raise MonitoringSSHError('Independent monitoring SSH connection failed') from None
        finally:
            if self._forwarder is not None:
                self._forwarder.ssh_password = None
                self._forwarder.ssh_pkeys = []

    def close(self):
        if self._forwarder is not None:
            try:
                self._forwarder.stop(force=True)
                if self._forwarder.is_active:
                    raise MonitoringSSHError('Monitoring SSH release remains unconfirmed')
            except Exception:
                raise MonitoringSSHError('Monitoring SSH release remains unconfirmed') from None
            self._forwarder = None
