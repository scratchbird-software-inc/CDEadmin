"""Pinned SSH transport for native Router hosts independent of SQL servers."""
import hashlib
import json
from pathlib import Path
import secrets
import shlex
import time

from . import mysql_host_transport as ssh
from . import mysql_router_worker as worker, mysql_router_services, mysql_host_installation

HostError=ssh.HostError


def sources():
    host,fileio,services=ssh.sources();sdk=Path(__file__).parents[2]/'sdk'
    return {'host':host,'fileio':fileio,'services':services,'router':Path(worker.__file__).read_text(),
        'router_services':Path(mysql_router_services.__file__).read_text(),'installation':Path(mysql_host_installation.__file__).read_text(),
        **{name:(sdk/(name+'.py')).read_text() for name in ('durable_tool','tool_guardian','tool_process','tool_reconcile')}}


LOADER='''import json,sys,types
p=json.loads(sys.stdin.buffer.read(2097153))
def install(name,source):
 m=types.ModuleType(name);sys.modules[name]=m;exec(source,m.__dict__);return m
install('_cdeadmin_native_fileio',p['sources']['fileio'])
install('_cdeadmin_native_services',p['sources']['services'])
install('_cdeadmin_native_worker',p['sources']['host'])
install('_cdeadmin_native_installation',p['sources']['installation'])
install('_cdeadmin_router_services',p['sources']['router_services'])
m=install('_cdeadmin_router_worker',p['sources']['router'])
try:r=m.dispatch(p['request'],p['sources'])
except Exception as e:r={'state':'refused','error_type':type(e).__name__,'native_error':getattr(e,'native_error',None),'message':str(e) if isinstance(e,m.Refused) else 'Native Router host observation failed'}
print(p['marker']+json.dumps(r,ensure_ascii=True,separators=(',',':')),flush=True)
'''


def program():
    return {**{key+'_sha256':hashlib.sha256(value.encode()).hexdigest() for key,value in sources().items()},
        'transport_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


class Transport:
    def __init__(self,route,credentials):
        if route.get('platform')!='posix':raise HostError('Select the native Linux Router SSH host')
        self.ssh=ssh.Transport(route,credentials)
    def connect(self):return self.ssh.connect()
    def close(self):self.ssh.close()
    def request(self,request,timeout=90):
        peer=self.ssh.transport
        if peer is None or not peer.is_authenticated():raise HostError('Authenticate the pinned native Router host first')
        marker='CDEADMIN_NATIVE_ROUTER_'+secrets.token_hex(16)+':'
        payload=json.dumps({'sources':sources(),'request':request,'marker':marker},ensure_ascii=True).encode('ascii')
        if len(payload)>2097152:raise HostError('Native Router request exceeds its admitted bound')
        channel=peer.open_session(timeout=5);stdout=bytearray();stderr=bytearray();deadline=time.monotonic()+timeout
        try:
            channel.exec_command('exec '+shlex.quote(self.ssh.route['python'])+' -u -c '+shlex.quote(LOADER))
            channel.sendall(payload);channel.shutdown_write()
            while True:
                while channel.recv_ready():
                    stdout.extend(channel.recv(32768))
                    if len(stdout)>2097152:raise HostError('Native Router reply exceeds its bound; inspect the original receipt without replay')
                while channel.recv_stderr_ready():
                    data=channel.recv_stderr(32768);stderr.extend(data[:max(0,65536-len(stderr))])
                if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():break
                if time.monotonic()>deadline or not peer.is_active():raise HostError('Native Router SSH acknowledgement is unconfirmed; inspect the original receipt without replay')
                time.sleep(.01)
            status=channel.recv_exit_status();lines=[line[len(marker):] for line in stdout.decode('utf8').splitlines() if line.startswith(marker)]
            if status!=0 or len(lines)!=1:raise HostError('Native Router reply is unavailable or ambiguous; do not repeat the command')
            value=json.loads(lines[0])
            if not isinstance(value,dict):raise HostError('The native Router reply is invalid')
            if value.get('state')=='refused':
                error=HostError(value.get('message') or 'Native Router request refused');error.native_error=value.get('native_error');raise error
            return value
        finally:channel.close()
