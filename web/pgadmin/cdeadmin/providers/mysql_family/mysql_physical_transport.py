"""Pinned SSH execution for independently supervised physical backup jobs."""
import hashlib
import json
from pathlib import Path
import secrets
import shlex
import time

from . import mysql_host_transport as ssh
from . import mysql_physical_worker as worker

HostError = ssh.HostError


def sources():
    host_source, file_source, service_source = ssh.sources()
    physical_source = Path(worker.__file__).read_text(encoding='utf8')
    return {'host': host_source, 'fileio': file_source, 'services': service_source, 'physical': physical_source,
        'recovery': Path(worker.__file__).with_name('mysql_recovery_worker.py').read_text(encoding='utf8')}


BOOTSTRAP = '''import json,sys,types
def install(name,source):
 m=types.ModuleType(name);sys.modules[name]=m;exec(source,m.__dict__);return m
def load(p):
 install('_cdeadmin_native_fileio',p['fileio'])
 install('_cdeadmin_native_services',p['services'])
 install('_cdeadmin_native_worker',p['host'])
 m=install('_cdeadmin_physical_worker',p['physical'])
 install('_cdeadmin_recovery_worker',p['recovery'])
 return m
'''


LOADER = BOOTSTRAP + '''p=json.loads(sys.stdin.buffer.read(2097153))
m=load(p['sources'])
try:r=m.dispatch(p['request'],p['supervisor'])
except Exception as e:r={'state':'refused','error_type':type(e).__name__,'message':str(e) if isinstance(e,m.Refused) else 'Native physical host observation failed'}
print(p['marker']+json.dumps(r,ensure_ascii=True,separators=(',',':')),flush=True)
'''


def program():
    return {**{key+'_sha256': hashlib.sha256(value.encode('utf8')).hexdigest() for key,value in sources().items()},
        'transport_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


class Transport:
    def __init__(self, route, credentials):
        if route.get('platform') != 'posix':
            raise HostError('XtraBackup requires a native Linux database host; desktop clients can use its pinned SSH transport')
        self.ssh = ssh.Transport(route, credentials)

    def connect(self): return self.ssh.connect()
    def close(self): self.ssh.close()

    def request(self, request, timeout=90):
        peer = self.ssh.transport
        if peer is None or not peer.is_authenticated():
            raise HostError('Authenticate the selected native physical SSH host first')
        module_sources = sources()
        supervisor = BOOTSTRAP + '\nm=load(' + repr(module_sources) + ')\nm.execute(sys.argv[1])\n'
        marker = 'CDEADMIN_PHYSICAL_' + secrets.token_hex(16) + ':'
        envelope = {'sources': module_sources, 'request': request, 'supervisor': supervisor, 'marker': marker}
        payload = json.dumps(envelope, ensure_ascii=True).encode('utf8')
        if len(payload) > 2 * 1024 * 1024:
            raise HostError('Native physical request exceeds its protocol bound')
        channel = peer.open_session(timeout=5)
        try:
            channel.exec_command('exec ' + shlex.quote(self.ssh.route['python']) + ' -u -c ' + shlex.quote(LOADER))
            channel.sendall(payload); channel.shutdown_write()
            stdout = bytearray(); stderr = bytearray(); deadline = time.monotonic() + timeout
            while True:
                while channel.recv_ready(): stdout.extend(channel.recv(32768))
                while channel.recv_stderr_ready(): stderr.extend(channel.recv_stderr(32768))
                if len(stdout) > 2 * 1024 * 1024 or len(stderr) > 128 * 1024:
                    raise HostError('Native physical response exceeds its observation bound')
                if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready(): break
                if time.monotonic() > deadline: raise HostError('Native physical SSH reply is unknown; inspect its original remote receipt')
                time.sleep(.02)
            response = next((line[len(marker):] for line in stdout.decode('utf8').splitlines() if line.startswith(marker)), None)
            if response is None: raise HostError('Native physical SSH reply is unavailable; the operation may still be running')
            value = json.loads(response)
            if value.get('state') == 'refused':
                raise HostError((value.get('message') or 'Native physical host refused the request') +
                    (' [' + value['error_type'] + ']' if value.get('error_type') != 'Refused' else ''))
            return value
        finally: channel.close()
