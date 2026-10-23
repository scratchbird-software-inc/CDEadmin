"""Host-side process-bound TCP relay. Native MySQL owns its complete protocol."""
import json
import os
from pathlib import Path
import socket
import struct
import sys
import threading

try:
    import _cdeadmin_physical_worker as physical
    import _cdeadmin_recovery_worker as recovery
except ModuleNotFoundError:
    from . import mysql_physical_worker as physical, mysql_recovery_worker as recovery

Refused = physical.Refused


def listener_owned(pid, port):
    """Bind the reviewed loopback listener to the original mysqld process."""
    inodes = set()
    for path in (Path('/proc')/str(pid)/'fd').iterdir():
        try: target = os.readlink(path)
        except FileNotFoundError: continue
        if target.startswith('socket:[') and target.endswith(']'): inodes.add(target[8:-1])
    expected = format(struct.unpack('=I',socket.inet_aton('127.0.0.1'))[0],'08X')+':'+format(port,'04X')
    for line in (Path('/proc')/str(pid)/'net/tcp').read_text().splitlines()[1:]:
        fields = line.split()
        if fields[1] == expected and fields[3] == '0A' and fields[9] in inodes: return True
    return False


def open_socket(request):
    if request.get('schema') != 'cdeadmin.mysql-recovery-stream.v1': raise Refused('Select the native recovery stream protocol')
    binding = physical.host_scope(request)
    root = physical.root_directory(request['workspace'],binding)
    directory = root/physical.job_id(request['job_id'])
    record = physical.read_json(directory/'result.json')
    original = physical.read_json(directory/'request.json')
    if (record.get('input_digest') != request['input_digest'] or original.get('binding') != request['binding'] or
            original.get('phase') != 'recover' or original.get('workspace') != str(root)):
        raise Refused('Native recovery stream belongs to another reviewed instance')
    observed = recovery.observe(directory,record,'status')
    expected = request['expected']
    if (not observed.get('recovery_running_verified') or record.get('runtime_process') != expected['runtime_process'] or
            record.get('sql_identity',{}).get('server_uuid') != expected['server_uuid'] or
            record.get('data_directory') != expected['datadir']):
        raise Refused('Original native recovery instance is no longer available')
    port = original.get('recovery_port',0)
    if not port or record['sql_identity'].get('port') != port or record['sql_identity'].get('bind_address') != '127.0.0.1':
        raise Refused('Start a separately reviewed recovery instance with a loopback TCP port for editor connections')
    process = record['runtime_process']
    if not listener_owned(process['pid'],port): raise Refused('Recovery TCP listener is not owned by the original native process')
    stream = socket.create_connection(('127.0.0.1',port),timeout=5)
    try:
        if not recovery.present(process) or not listener_owned(process['pid'],port):
            raise Refused('Native recovery process changed during stream admission')
        stream.settimeout(None)
        return stream, {'server_uuid':expected['server_uuid'],'datadir':expected['datadir'],
            'runtime_process':process,'transport':'native-loopback-tcp-over-pinned-ssh'}
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
