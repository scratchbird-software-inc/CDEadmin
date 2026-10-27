"""Native Linux option-file replacement, with a private native validation view.

This standard-library helper travels with the pinned SSH host worker. Installing
an option file does not restart a service or establish SQL readiness.
"""
import base64
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import stat
import sys
import tempfile
import uuid

# A mount namespace belongs only to this child. The bind selects the
# proposed bytes at the original native filename, preserving include semantics.
VALIDATOR = '''import ctypes,os,sys
source,target,program=sys.argv[1:]
libc=ctypes.CDLL(None,use_errno=True)
libc.mount.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_char_p,ctypes.c_ulong,ctypes.c_void_p]
libc.mount.restype=ctypes.c_int
libc.unshare.argtypes=[ctypes.c_int]
libc.unshare.restype=ctypes.c_int
if libc.unshare(0x20000)!=0:
 raise OSError(ctypes.get_errno(),'Private native mount namespace unavailable')
if libc.mount(None,b'/',None,(1<<14)|(1<<18),None)!=0:
 raise OSError(ctypes.get_errno(),'Private native mount propagation unavailable')
if libc.mount(os.fsencode(source),os.fsencode(target),None,4096,None)!=0:
 raise OSError(ctypes.get_errno(),'Private native configuration view unavailable')
os.execve(program,[program,'--defaults-file='+target,'--validate-config'],dict(os.environ))
'''


def content(request, refused):
    value=request.get('configuration_replacement')
    if not isinstance(value,dict) or set(value)!={'base64','sha256'} or not isinstance(value['base64'],str):
        raise refused('Select the exact native option-file bytes')
    try:data=base64.b64decode(value['base64'],validate=True)
    except (ValueError,TypeError):raise refused('Native option-file encoding is unavailable') from None
    if len(data)>524288 or b'\0' in data or hashlib.sha256(data).hexdigest()!=value['sha256']:
        raise refused('Native option-file bytes or their digest differ')
    return data


def attributes(path):
    return {name:os.getxattr(path,name) for name in sorted(os.listxattr(path))}


def attribute_hashes(values):
    return {name:hashlib.sha256(value).hexdigest() for name,value in values.items()}


def copy_attributes(descriptor,values):
    for name in os.listxattr(descriptor):
        if name not in values:os.removexattr(descriptor,name)
    for name,value in values.items():os.setxattr(descriptor,name,value)


def metadata(path, refused):
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode):raise refused('Select a regular resolved native option file')
    return {'device':info.st_dev,'inode':info.st_ino,'mode':stat.S_IMODE(info.st_mode),'uid':info.st_uid,'gid':info.st_gid,'extended_attributes':attribute_hashes(attributes(path))}


def stage(directory,data,permissions,extended):
    if attribute_hashes(extended)!=permissions['extended_attributes']:raise ValueError('Native option-file attributes changed')
    path=Path(directory)/('proposed-'+uuid.uuid4().hex+'.tmp')
    with path.open('xb') as stream:
        os.fchmod(stream.fileno(),0o600);stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.fchown(stream.fileno(),permissions['uid'],permissions['gid'])
        copy_attributes(stream.fileno(),extended)
        os.fchmod(stream.fileno(),permissions['mode'])
    return path


def graph(host,target,candidate,configuration):
    original=host['regular_stream']
    @contextmanager
    def projected(path):
        selected=candidate if Path(path).resolve(strict=True)==target else path
        with original(selected) as stream:yield stream
    # The SSH request worker is isolated and single threaded here. This changes
    # only metadata discovery; native mysqld performs its own file parsing.
    host['regular_stream']=projected
    try:return host['configuration_graph'](configuration['path'],configuration['context'])
    finally:host['regular_stream']=original


def inspect(request,observed,host):
    refused=host['Refused'];data=content(request,refused)
    if not sys.platform.startswith('linux'):raise refused('Native option-file installation requires the Linux host adapter')
    configuration=observed.get('configuration')
    if configuration is None:raise refused('Select the exact existing native option file to replace')
    target=Path(configuration['path']).resolve(strict=True);permissions=metadata(target,refused)
    executable=Path(sys.executable).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='scratchrobin-options-review-') as temporary:
        candidate=stage(temporary,data,permissions,attributes(target))
        proposed=graph(host,target,candidate,configuration)
    parent=target.parent.stat()
    return {'target':str(target),'original':permissions,'parent_identity':{'device':parent.st_dev,'inode':parent.st_ino},
        'replacement_sha256':hashlib.sha256(data).hexdigest(),'replacement_bytes':str(len(data)),
        'prospective_configuration_graph':proposed,'namespace_program':{'path':str(executable),'sha256':host['file_hash'](executable)},
        'native_validation_scope':'Private child mount view at the original filename; no service restart or SQL readiness assertion'}


def execute(request,observed,directory,timeout,host):
    import fcntl
    with host['regular_stream'](Path(observed['configuration_deployment']['target'])) as original:
        try:fcntl.flock(original.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise host['Refused']('The original native option file has another active installer') from None
        try:return install(request,observed,directory,timeout,host)
        finally:fcntl.flock(original.fileno(),fcntl.LOCK_UN)


def install(request,observed,directory,timeout,host):
    refused=host['Refused'];selected=observed['configuration_deployment'];configuration=observed['configuration']
    data=content(request,refused);target=Path(selected['target']);permissions=selected['original']
    extended=attributes(target);candidate=stage(directory,data,permissions,extended)
    result=host['process'](Path(selected['namespace_program']['path']),
        ['-I','-S','-c',VALIDATOR,str(candidate),str(target),observed['program']['path']],
        directory,timeout,configuration_context=configuration['context'])
    value={'native_validation':result,'installed':False,'restart_issued':False,'database_readiness_observed':False}
    if result['return_code']!=0 or result['timed_out'] or not result['streams_closed']:
        return value
    if inspect(request,observed,host)!=selected:
        raise refused('Original or prospective option-file inputs changed during native validation')
    if host['file_hash'](target)!=configuration['sha256']:
        raise refused('Original native option-file bytes changed before installation')
    # Pin the destination parent and leaf identities before the atomic replace.
    descriptor=os.open(target.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    name='.scratchrobin-options-'+uuid.uuid4().hex+'.tmp';created=False
    try:
        parent=os.fstat(descriptor)
        if {'device':parent.st_dev,'inode':parent.st_ino}!=selected['parent_identity']:
            raise refused('Native option-file parent identity changed')
        current=os.stat(target.name,dir_fd=descriptor,follow_symlinks=False)
        if (current.st_dev,current.st_ino)!=(permissions['device'],permissions['inode']):
            raise refused('Original native option-file identity changed')
        with host['regular_stream'](target) as stream:
            original=stream.read(524289)
        if len(original)>524288 or hashlib.sha256(original).hexdigest()!=configuration['sha256']:
            raise refused('Original native option-file bytes changed before installation')
        backup=Path(directory)/'original-options.private'
        with backup.open('xb') as stream:
            os.fchmod(stream.fileno(),0o600);stream.write(original);stream.flush();os.fsync(stream.fileno())
        output=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=descriptor);created=True
        with os.fdopen(output,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
            os.fchown(stream.fileno(),permissions['uid'],permissions['gid']);copy_attributes(stream.fileno(),extended);os.fchmod(stream.fileno(),permissions['mode'])
        # A changed concurrent writer is refused rather than overwritten from a
        # stale review. The remaining native read/replace interval is not frozen.
        current=os.stat(target.name,dir_fd=descriptor,follow_symlinks=False)
        if (current.st_dev,current.st_ino)!=(permissions['device'],permissions['inode']) or metadata(target,refused)!=permissions or host['file_hash'](target)!=configuration['sha256']:
            raise refused('Original native option-file changed before replacement')
        os.replace(name,target.name,src_dir_fd=descriptor,dst_dir_fd=descriptor);created=False;os.fsync(descriptor)
        value.update(installed=True,installed_sha256=hashlib.sha256(data).hexdigest(),original_private_copy=backup.name)
        return value
    finally:
        if created:os.unlink(name,dir_fd=descriptor)
        os.close(descriptor)
