"""Host-side process-bound TCP relay. Native MySQL owns its complete protocol."""
import json
import os
from pathlib import Path
import socket
import stat
import struct
import sys
import threading

try:
    import _cdeadmin_physical_worker as physical
    import _cdeadmin_recovery_worker as recovery
except ModuleNotFoundError:
    from . import mysql_physical_worker as physical, mysql_recovery_worker as recovery

Refused = physical.Refused


def socket_inodes(pid):
    """Kernel socket identities owned by the original native process."""
    inodes = set()
    for path in (Path('/proc')/str(pid)/'fd').iterdir():
        try: target = os.readlink(path)
        except FileNotFoundError: continue
        if target.startswith('socket:[') and target.endswith(']'): inodes.add(target[8:-1])
    return inodes


def listener_owned(pid, port):
    inodes = socket_inodes(pid)
    expected = format(struct.unpack('=I',socket.inet_aton('127.0.0.1'))[0],'08X')+':'+format(port,'04X')
    for line in (Path('/proc')/str(pid)/'net/tcp').read_text().splitlines()[1:]:
        fields = line.split()
        if fields[1] == expected and fields[3] == '0A' and fields[9] in inodes: return True
    return False


def unix_listener_owned(pid, path):
    # The filesystem inode is not the kernel socket inode from /proc/net/unix.
    path = Path(path)
    try:
        info = path.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.geteuid() or path.resolve() != path:return False
        inodes = socket_inodes(pid)
        for line in (Path('/proc')/str(pid)/'net/unix').read_text().splitlines()[1:]:
            fields = line.split(maxsplit=7)
            if (len(fields)==8 and fields[7]==str(path) and fields[6] in inodes and
                    int(fields[3],16)&0x10000 and fields[4]=='0001' and fields[5]=='01'):return True
    except FileNotFoundError:pass
    return False


def unix_peer_owned(stream, pid):
    # An unlinked original listener can retain the same /proc pathname while
    # another process binds its replacement. Check the actual connected peer.
    peer, uid, _gid = struct.unpack('3i', stream.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i')))
    return peer == pid and uid == os.geteuid()


def open_socket(request):
    if request.get('schema') != 'cdeadmin.mysql-recovery-stream.v1': raise Refused('Select the native recovery stream protocol')
    binding = physical.host_scope(request)
    root = physical.root_directory(request['workspace'],binding)
    directory = root/physical.job_id(request['job_id'])
    record = physical.read_json(directory/'result.json')
    original = physical.read_json(directory/'request.json')
    original_binding=physical.host_scope(original)
    if (record.get('input_digest') != request['input_digest'] or original_binding != binding or
            original.get('phase') != 'recover' or physical.root_directory(original['workspace'],original_binding) != root):
        raise Refused('Native recovery stream belongs to another reviewed instance')
    observed = recovery.observe(directory,record,'status')
    expected = request['expected']
    if (not observed.get('recovery_running_verified') or record.get('runtime_process') != expected['runtime_process'] or
            record.get('sql_identity',{}).get('server_uuid') != expected['server_uuid'] or
            record.get('data_directory') != expected['datadir']):
        raise Refused('Original native recovery instance is no longer available')
    port = original.get('recovery_port',0)
    process = record['runtime_process']; identity = record['sql_identity']
    if port:
        if identity.get('port')!=port or identity.get('bind_address')!='127.0.0.1' or identity.get('skip_networking')!=0:
            raise Refused('Recovery TCP listener differs from its original startup')
        owned=lambda:listener_owned(process['pid'],port)
        address=('127.0.0.1',port); family=socket.AF_INET; transport='native-loopback-tcp-over-pinned-ssh'
    else:
        path=directory/'runtime.sock'
        if identity.get('socket')!=str(path) or identity.get('skip_networking')!=1:
            raise Refused('Recovery private socket differs from its original startup')
        owned=lambda:unix_listener_owned(process['pid'],path)
        address=str(path); family=socket.AF_UNIX; transport='native-private-unix-socket-over-pinned-ssh'
    if not recovery.present(process) or not owned():raise Refused('Recovery listener is not owned by the original native process')
    stream=socket.socket(family,socket.SOCK_STREAM)
    try:
        stream.settimeout(5);stream.connect(address)
        if not recovery.present(process) or not owned() or not port and not unix_peer_owned(stream,process['pid']):
            raise Refused('Native recovery process changed during stream admission')
        stream.settimeout(None)
        return stream, {'server_uuid':expected['server_uuid'],'datadir':expected['datadir'],
            'runtime_process':process,'transport':transport}
    except BaseException:stream.close();raise


def relay(stream):
    def incoming():
        try:
            while data := os.read(0,65536):stream.sendall(data)
            stream.shutdown(socket.SHUT_WR)
        except OSError:pass
    thread=threading.Thread(target=incoming,daemon=True);thread.start()
    try:
        while data := stream.recv(65536):
            view=memoryview(data)
            while view:
                written=os.write(1,view);view=view[written:]
    finally:stream.close()


def serve(request):
    stream=None
    try:
        stream,observed=open_socket(request)
        value={'success':True,'observed':observed}
    except Exception as error:
        value={'success':False,'error_type':type(error).__name__,
            'message':str(error) if isinstance(error,Refused) else 'Native recovery stream admission failed'}
    encoded=json.dumps(value,ensure_ascii=True,separators=(',',':')).encode('ascii')
    sys.stdout.buffer.write(struct.pack('!I',len(encoded))+encoded);sys.stdout.buffer.flush()
    if stream is not None:relay(stream)
