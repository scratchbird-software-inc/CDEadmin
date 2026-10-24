"""Pinned, independently authenticated SSH execution on an explicit DB host."""
import base64
import hashlib
import io
import json
from pathlib import Path
import secrets
import shlex
import socket
import time

from ...operations import fileio
from . import mysql_host_worker, mysql_host_services, mysql_host_configuration, mysql_host_initialization, mysql_host_installation, mysql_host_upgrade


class HostError(ValueError):
    pass


LOADER = '''import base64,json,sys,types
p=json.loads(sys.stdin.buffer.read(1048577))
m=types.ModuleType('_cdeadmin_native_fileio')
exec(p['fileio'],m.__dict__);sys.modules[m.__name__]=m
s=types.ModuleType('_cdeadmin_native_services')
exec(p['services'],s.__dict__);sys.modules[s.__name__]=s
c=types.ModuleType('_cdeadmin_native_configuration')
exec(p['configuration_worker'],c.__dict__);sys.modules[c.__name__]=c
i=types.ModuleType('_cdeadmin_native_initialization')
exec(p['initialization_worker'],i.__dict__);sys.modules[i.__name__]=i
j=types.ModuleType('_cdeadmin_native_installation')
exec(p['installation_worker'],j.__dict__);sys.modules[j.__name__]=j
u=types.ModuleType('_cdeadmin_native_upgrade')
exec(p['upgrade_worker'],u.__dict__);sys.modules[u.__name__]=u
n={'__name__':'_cdeadmin_native_worker'}
exec(p['worker'],n)
try:r=n['dispatch'](p['request'],p.get('initialization_supervisor'))
except Exception as e:r={'state':'refused','error_type':type(e).__name__,'message':str(e) if isinstance(e,n['Refused']) else 'Native host observation failed'}
print(p['marker']+json.dumps(r,ensure_ascii=True,separators=(',',':')),flush=True)
'''


INITIALIZATION_BOOTSTRAP = '''import sys,types
def install(name,source):
 m=types.ModuleType(name);sys.modules[name]=m;exec(source,m.__dict__);return m
def load(p):
 install('_cdeadmin_native_fileio',p['fileio'])
 install('_cdeadmin_native_services',p['services'])
 install('_cdeadmin_native_configuration',p['configuration'])
 install('_cdeadmin_native_initialization',p['initialization'])
 install('_cdeadmin_native_installation',p['installation'])
 install('_cdeadmin_native_upgrade',p['upgrade'])
 return install('_cdeadmin_native_worker',p['host'])
'''


def fingerprint(key):
    return 'SHA256:' + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode('ascii').rstrip('=')


def probe(host, port):
    if not isinstance(host, str) or not host or '\x00' in host or len(host) > 1024 or type(port) is not int or not 1 <= port <= 65535:
        raise HostError('Select the explicit SSH peer address')
    import paramiko
    connection = transport = None
    try:
        connection = socket.create_connection((host, port), timeout=5)
        transport = paramiko.Transport(connection); transport.start_client(timeout=5)
        key = transport.get_remote_server_key()
        return {'host': host, 'port': port, 'openssh_key': key.get_name()+' '+key.get_base64(),
                'fingerprint': fingerprint(key), 'authenticated': False, 'remote_command_executed': False}
    except Exception as error:
        raise HostError('SSH public-key inspection failed ('+type(error).__name__+')') from None
    finally:
        if transport is not None: transport.close()
        if connection is not None: connection.close()


def command(platform, executable):
    if not isinstance(executable, str) or not executable or '\x00' in executable or len(executable) > 4096:
        raise HostError('Select the Python executable on the authenticated database host')
    # Source and native tool options travel through stdin. The only command
    # text is this fixed loader and an explicitly selected Python executable.
    if platform == 'posix':
        return 'exec ' + shlex.quote(executable) + ' -u -c ' + shlex.quote(LOADER)
    if platform == 'windows':
        literal = lambda value: "'" + value.replace("'", "''") + "'"
        script = '& ' + literal(executable) + ' -u -c ' + literal(LOADER)
        encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
        return 'powershell.exe -NoProfile -NonInteractive -EncodedCommand ' + encoded
    raise HostError('Select the actual POSIX or native Windows SSH execution platform')


def sources():
    worker = Path(mysql_host_worker.__file__).read_text(encoding='utf8')
    helper = Path(fileio.__file__).read_text(encoding='utf8')
    return worker, helper, Path(mysql_host_services.__file__).read_text(encoding='utf8')


def program():
    worker, helper, services = sources()
    return {'worker_sha256': hashlib.sha256(worker.encode('utf8')).hexdigest(),
            'fileio_sha256': hashlib.sha256(helper.encode('utf8')).hexdigest(),
            'services_sha256': hashlib.sha256(services.encode('utf8')).hexdigest(),
            'configuration_worker_sha256':hashlib.sha256(Path(mysql_host_configuration.__file__).read_bytes()).hexdigest(),
            'initialization_worker_sha256':hashlib.sha256(Path(mysql_host_initialization.__file__).read_bytes()).hexdigest(),
            'installation_worker_sha256':hashlib.sha256(Path(mysql_host_installation.__file__).read_bytes()).hexdigest(),
            'upgrade_worker_sha256':hashlib.sha256(Path(mysql_host_upgrade.__file__).read_bytes()).hexdigest(),
            'transport_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def public_route(value):
    if not isinstance(value, dict) or set(value) != {'host', 'port', 'username', 'host_key', 'authentication', 'platform', 'python'}:
        raise HostError('Select an explicit database-server SSH host and pinned public key')
    for key in ('host', 'username', 'host_key', 'python'):
        if not isinstance(value[key], str) or not value[key] or '\x00' in value[key] or len(value[key]) > 32768:
            raise HostError('Native SSH host identity is unavailable')
    if type(value['port']) is not int or not 1 <= value['port'] <= 65535:
        raise HostError('Select a native SSH port')
    if value['authentication'] not in {'password', 'private_key'}:
        raise HostError('Select SSH password or private-key authentication')
    command(value['platform'], value['python'])
    return dict(value)


class Transport:
    def __init__(self, route, credentials):
        self.route = public_route(route)
        self.credentials = credentials
        self.connection = self.transport = None
        self.upgrade_secret=None

    def close(self):
        if self.upgrade_secret is not None:
            secret,self.upgrade_secret=self.upgrade_secret,None;secret.close()
        if self.transport is not None:
            self.transport.close(); self.transport = None
        if self.connection is not None:
            self.connection.close(); self.connection = None
        self.credentials = {}

    def connect(self):
        import paramiko
        route = self.route
        try:
            parts = route['host_key'].split(maxsplit=2)
            if len(parts) < 2:
                raise ValueError()
            expected = paramiko.PKey.from_type_string(parts[0], base64.b64decode(parts[1], validate=True))
            self.connection = socket.create_connection((route['host'], route['port']), timeout=5)
            self.transport = paramiko.Transport(self.connection)
            options = self.transport.get_security_options()
            allowed = ('rsa-sha2-512', 'rsa-sha2-256', 'ssh-rsa') if expected.get_name() == 'ssh-rsa' else (expected.get_name(),)
            selected = tuple(name for name in options.key_types if name in allowed)
            if not selected:
                raise HostError('The explicitly pinned SSH public-key algorithm is unavailable')
            options.key_types = selected
            self.transport.start_client(timeout=5)
            observed = self.transport.get_remote_server_key()
            if observed.get_name() != expected.get_name() or observed.asbytes() != expected.asbytes():
                raise HostError('The database-host SSH public key differs from the explicitly pinned key')
            if route['authentication'] == 'password':
                password = self.credentials.get('password')
                if not isinstance(password, str) or not password or len(password.encode('utf8')) > 16384:
                    raise HostError('Supply the selected SSH password')
                self.transport.auth_password(route['username'], password, fallback=False)
            else:
                value = self.credentials.get('private_key')
                if not isinstance(value, str) or not value or len(value.encode('utf8')) > 1024 * 1024:
                    raise HostError('Supply the selected SSH private key')
                key = None
                for name in ('Ed25519Key', 'ECDSAKey', 'RSAKey', 'DSSKey'):
                    kind = getattr(paramiko, name, None)
                    if kind is None:
                        continue
                    try:
                        key = kind.from_private_key(io.StringIO(value), password=self.credentials.get('private_key_password'))
                        break
                    except (paramiko.SSHException, ValueError):
                        continue
                if key is None:
                    raise HostError('The selected SSH private key could not be opened')
                self.transport.auth_publickey(route['username'], key)
            if not self.transport.is_authenticated():
                raise HostError('The database-host SSH identity was not authenticated')
            self.credentials = {}
            return {'host': route['host'], 'port': route['port'], 'username': route['username'],
                    'host_key_fingerprint': fingerprint(observed), 'execution_host_kind': 'database-server-ssh-host'}
        except HostError:
            self.close(); raise
        except Exception as error:
            self.close()
            raise HostError('Native database-host SSH admission failed (' + type(error).__name__ + ')') from None

    def request(self, request, timeout=90):
        if self.transport is None or not self.transport.is_authenticated():
            raise HostError('Authenticate the independently owned database-host SSH transport first')
        if request.get('upgrade') is not None and request.get('action') not in {'status','acknowledge_upgrade'}:
            if self.upgrade_secret is None:raise HostError('Supply private native upgrade-check credentials for review and dispatch')
            request={**request,'upgrade_check_secret':self.upgrade_secret.use(lambda view:json.loads(bytes(view)))}
        worker, helper, services = sources(); marker = 'CDEADMIN_NATIVE_HOST_' + secrets.token_hex(16) + ':'
        module_sources={'host':worker,'fileio':helper,'services':services,'configuration':Path(mysql_host_configuration.__file__).read_text(),'initialization':Path(mysql_host_initialization.__file__).read_text(),'installation':Path(mysql_host_installation.__file__).read_text(),'upgrade':Path(mysql_host_upgrade.__file__).read_text()}
        supervisor=INITIALIZATION_BOOTSTRAP+'\nm=load('+repr(module_sources)+')\nsys.modules[\"_cdeadmin_native_initialization\"].guardian(sys.argv[1],m.__dict__)\n'
        envelope = {'upgrade_worker':module_sources['upgrade'],'installation_worker':module_sources['installation'],'initialization_worker':module_sources['initialization'],'initialization_supervisor':supervisor,'request': request, 'worker': worker, 'fileio': helper, 'services': services, 'configuration_worker':Path(mysql_host_configuration.__file__).read_text(), 'marker': marker}
        payload = json.dumps(envelope, ensure_ascii=True).encode('utf8')
        if len(payload) > 1024 * 1024:
            raise HostError('Native host request exceeds its admitted bound')
        channel = self.transport.open_session(timeout=5)
        stdout = bytearray(); stderr = bytearray(); deadline = time.monotonic() + timeout
        try:
            channel.exec_command(command(self.route['platform'], self.route['python']))
            channel.sendall(payload); channel.shutdown_write()
            while True:
                while channel.recv_ready():
                    stdout.extend(channel.recv(32768))
                    if len(stdout) > 2 * 1024 * 1024:
                        raise HostError('Native host response exceeded its admitted bound; inspect its receipt without replay')
                while channel.recv_stderr_ready():
                    data = channel.recv_stderr(32768)
                    stderr.extend(data[:max(0, 65536 - len(stderr))])
                if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                    break
                if time.monotonic() > deadline or not self.transport.is_active():
                    raise HostError('Native host reply is unconfirmed; inspect its durable receipt without replay')
                time.sleep(.01)
            status = channel.recv_exit_status()
            lines = [line[len(marker):] for line in stdout.decode('utf8').splitlines() if line.startswith(marker)]
            if status != 0 or len(lines) != 1:
                raise HostError('Native host reply is unavailable or ambiguous; inspect its receipt without replay')
            result = json.loads(lines[0])
            if not isinstance(result, dict):
                raise HostError('Native host returned an invalid observation')
            if result.get('state') == 'refused':
                raise HostError(result.get('message') or 'Native host operation was refused')
            return result
        finally:
            channel.close()
