"""Native external-file metadata and private Linux recovery mount plans."""
import ctypes
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import sys

try:
    import _cdeadmin_physical_worker as physical
except ModuleNotFoundError:
    from . import mysql_physical_worker as physical

Refused=physical.Refused
host=physical.host
READONLY=1
RECURSIVE=0x8000
BIND=0x1000
MOUNT_REC=0x4000
PRIVATE=0x40000
NEW_MOUNT_NAMESPACE=0x20000


def alias_kind(row):
    kind=row.get('kind','directory')
    if kind not in {'directory','file'}:raise Refused('Select a native directory or file alias')
    return kind


def compatible_source(path,kind):
    if not path.exists():return True
    mode=path.stat().st_mode
    return stat.S_ISDIR(mode) if kind=='directory' else stat.S_ISREG(mode) or stat.S_ISBLK(mode)


def tablespaces(directory):
    """Validate native metadata without rewriting catalog or page contents."""
    value=physical.read_json(directory/'xtrabackup_tablespaces')
    if not isinstance(value,dict) or set(value)!={'version','external_tablespaces'} or value['version']!=3:
        raise Refused('Native external tablespace metadata is unavailable or incompatible')
    entries=value['external_tablespaces']
    if not isinstance(entries,list) or len(entries)>4096:raise Refused('Native external tablespace list exceeds its bound')
    files=set();names=set()
    for entry in entries:
        if (not isinstance(entry,dict) or set(entry)!={'file_name','tablespace_name','tablespace_type'} or
                entry['tablespace_type'] not in {'TABLESPACE','UNDO_LOG'}):
            raise Refused('External native tablespace entry is unavailable or incompatible')
        filename=host.text(entry['file_name']);name=host.text(entry['tablespace_name']);path=PurePosixPath(name)
        if (not filename.startswith('/') or '..' in PurePosixPath(filename).parts or '\\' in name or path.is_absolute() or
                any(part in {'.','..'} for part in name.split('/')) or
                filename in files or name in names):raise Refused('Native external file identity is ambiguous')
        files.add(filename);names.add(name)
    return value


PROBE='''import ctypes,json,os,platform,sys
if not sys.platform.startswith('linux') or platform.machine().lower() not in {'x86_64','aarch64','arm64'}:raise RuntimeError('Linux64 required')
c=ctypes.CDLL(None,use_errno=True)
c.syscall.restype=ctypes.c_long
def checked(rc):
 if rc:raise OSError(ctypes.get_errno(),'Native mount capability unavailable')
class Attr(ctypes.Structure):_fields_=[('set',ctypes.c_uint64),('clear',ctypes.c_uint64),('propagation',ctypes.c_uint64),('userns',ctypes.c_uint64)]
mode=sys.argv[1];uid=os.geteuid();kernel=platform.release()
checked(c.unshare(0x20000));checked(c.mount(None,b'/',None,0x40000|0x4000,None))
if mode!='existing':
 checked(c.mount(b'tmpfs',b'/tmp',b'tmpfs',2,('mode=0700,uid='+str(uid)+',size=1m').encode()))
 os.mkdir('/tmp/source');os.mkdir('/tmp/target')
 fd=int(c.syscall(428,-100,b'/tmp/source',1|0x80000|0x8000))
 if fd<0:raise OSError(ctypes.get_errno(),'Native detached mount unavailable')
 try:checked(c.syscall(429,fd,b'',-100,b'/tmp/target',4))
 finally:os.close(fd)
 if mode=='root':os.chdir('/tmp/target');os.chroot('.');os.chdir('/')
else:checked(c.mount(b'/',b'/',None,0x1000|0x4000,None))
a=Attr(1,0,0,0);checked(c.syscall(442,-100,b'/',0x8000,ctypes.byref(a),ctypes.sizeof(a)))
if not os.statvfs('/').f_flag&os.ST_RDONLY:raise RuntimeError('Read-only mount unavailable')
print(json.dumps({'backend':'linux-mount-setattr-v1','uid':uid,'kernel':kernel,'private_mount_namespace':True,'readonly_host_view':True,'projection':mode!='existing','private_root_switch':mode=='root'}))
'''


def capability(*,projection=False,root_projection=False):
    mode='root' if root_projection else 'project' if projection else 'existing'
    result=subprocess.run([sys.executable,'-B','-c',PROBE,mode],capture_output=True,timeout=15,check=False)
    if result.returncode or len(result.stdout)>4096:
        raise Refused('Native external recovery requires Linux mount-namespace and mount_setattr privileges on the selected SSH account')
    value=json.loads(result.stdout)
    if value.get('backend')!='linux-mount-setattr-v1' or value.get('private_mount_namespace') is not True or value.get('readonly_host_view') is not True:
        raise Refused('Native external recovery filesystem capability was not observed')
    if projection and value.get('projection') is not True or root_projection and value.get('private_root_switch') is not True:
        raise Refused('Native missing-directory projection capability was not observed')
    return value


def admission(request,entries,*,storage=None):
    if not entries and storage is None:return None
    if request.get('isolate_external_paths') is not True:
        raise Refused('Review native external-path isolation explicitly before using this physical artifact')
    if storage is None and any(entry['tablespace_type']=='UNDO_LOG' for entry in entries):
        raise Refused('External undo files require separate native system/undo geometry admission')
    additional,directories=physical.geometry_module().external_entries(storage)
    combined={row['file_name']:row for row in additional}
    combined.update({row['file_name']:row for row in entries})
    selected=plan(list(combined.values()),directories)
    result={'plan':selected,'original_datadir':request['binding']['datadir'],
        'host_root_readonly':True,'native_datadir_uses_private_alias':True}
    if storage is not None:result['storage']=storage
    if request['phase']=='recover':
        workspace=physical.absolute(request['workspace']);missing=[];root_projection=False
        for row in [{'source_root':result['original_datadir']},*selected]:
            source=physical.absolute(row['source_root'])
            if (not compatible_source(source,alias_kind(row)) or workspace.is_relative_to(source) or source.is_relative_to(workspace)):
                raise Refused('Native recovery aliases must have their retained kind and be separate from the private workspace')
            if not source.exists():
                missing.append(str(source));parent=source.parent
                while not parent.exists():parent=parent.parent
                root_projection=root_projection or parent==Path('/')
        result['missing_alias_directories']=missing
        result['capability']=capability(projection=bool(missing),root_projection=root_projection)
    return result


def runtime(directory,data,context):
    external=directory/'runtime-external'
    (data/'external-data').rename(external)
    selected=[{'source_root':context['original_datadir'],'private_root':str(data)}]
    selected.extend({'source_root':row['source_root'],'private_root':str(external/Path(row['relative_root']).relative_to('external-data')),
        **({'kind':'file'} if alias_kind(row)=='file' else {})} for row in context['plan'])
    storage=context.get('storage')
    scan=[row['source_root'] for row in context['plan']]
    if storage is not None:
        entries=[{'file_name':file['source_file'],'tablespace_name':file['tablespace_name'],'tablespace_type':file['tablespace_type']}
            for row in context['plan'] for file in row['files'] if file['tablespace_type'] not in {'SYSTEM','RAW_SYSTEM'}]
        scan=sorted(set(storage['scan_directories'])|{str(path) for path in roots(entries)})
    data_home=context['original_datadir'] if storage is None else storage['variables']['innodb_data_home_dir']
    if storage is not None and data_home not in {'','.', './'}:data_home=storage['data_home']
    arguments=['--datadir='+context['original_datadir'],
        '--innodb-data-home-dir='+data_home,
        '--innodb-undo-directory='+(context['original_datadir'] if storage is None else storage['undo_home']),
        '--innodb-directories='+';'.join(scan)]
    if storage is not None and (storage.get('resolved_paths') or any(row.get('raw_mode') for row in storage['system_files'])):
        arguments.append('--innodb-data-file-path='+';'.join(row['source_file']+':'+row.get('regular_suffix',row['suffix']) for row in storage['system_files']))
    return selected,arguments


def roots(entries):
    """Keep native per-table DATA DIRECTORY schema subdirectories together."""
    selected=set()
    for entry in entries:
        path=Path(entry['file_name']);name=PurePosixPath(entry['tablespace_name'])
        root=path.parent
        if len(name.parts)==2 and path.parent.name==name.parts[0]:root=root.parent
        # Native innodb_directories splits on semicolons without quoting.
        # Select a containing directory; keep literal child names unchanged.
        while ';' in str(root):root=root.parent
        if root==Path('/'):raise Refused('Select an external data layout with a dedicated native directory')
        selected.add(root)
    return sorted((path for path in selected if not any(path!=other and path.is_relative_to(other) for other in selected)),key=str)


def plan(entries,directories=()):
    raw=[entry for entry in entries if entry['tablespace_type']=='RAW_SYSTEM']
    entries=[entry for entry in entries if entry['tablespace_type']!='RAW_SYSTEM']
    candidates=set(roots(entries))|{Path(root) for root in directories}
    selected=sorted((path for path in candidates if not any(path!=other and path.is_relative_to(other) for other in candidates)),key=str)
    result=[]
    for index,root in enumerate(selected):
        members=[entry for entry in entries if Path(entry['file_name']).is_relative_to(root)]
        result.append({'source_root':str(root),'relative_root':'external-data/'+str(index),
            'files':[{'source_file':entry['file_name'],
                'relative_file':str(Path(entry['file_name']).relative_to(root)),
                'tablespace_name':entry['tablespace_name'],'tablespace_type':entry['tablespace_type']} for entry in members]})
    for index,entry in enumerate(raw):
        source=Path(entry['file_name'])
        if any(source.is_relative_to(root) for root in selected):
            raise Refused('Raw system-file aliases require a separate native device path')
        result.append({'source_root':str(source),'relative_root':'external-data/files/'+str(index)+'/'+source.name,
            'kind':'file','files':[{'source_file':str(source),'relative_file':'.',
                'tablespace_name':entry['tablespace_name'],'tablespace_type':'RAW_SYSTEM'}]})
    return result


def stage_copy_back(directory,original,target,expected,context=None):
    """Remap only a verified private native copy-back input."""
    staged=directory/'copy-back-input';shutil.copytree(original,staged)
    if physical.public(physical.artifact(staged))!=expected:
        raise Refused('Staged copy-back bytes differ from the immutable prepared input')
    value=tablespaces(staged);selected=plan(value['external_tablespaces']) if context is None else context['plan']
    destinations={item['source_file']:str(target/row['relative_root']/item['relative_file'])
        for row in selected for item in row['files']}
    host.save(staged/'xtrabackup_tablespaces',{'version':3,'external_tablespaces':[
        {**entry,'file_name':destinations[entry['file_name']]} for entry in value['external_tablespaces']]})
    return staged,selected


class MountAttributes(ctypes.Structure):
    _fields_=[('set',ctypes.c_uint64),('clear',ctypes.c_uint64),
        ('propagation',ctypes.c_uint64),('user_namespace',ctypes.c_uint64)]


def checked(value):
    if value:raise Refused('Native private filesystem setup refused; OS errno '+str(ctypes.get_errno()))


def library():
    if not sys.platform.startswith('linux') or platform.machine().lower() not in {'x86_64','aarch64','arm64'}:
        raise Refused('This native external-path backend requires Linux64 mount namespaces and mount_setattr')
    native=ctypes.CDLL(None,use_errno=True);native.syscall.restype=ctypes.c_long
    return native


def attributes(native,path,*,add=0,remove=0):
    value=MountAttributes(add,remove,0,0)
    checked(native.syscall(442,-100,os.fsencode(path),RECURSIVE,ctypes.byref(value),ctypes.sizeof(value)))


def validate_roots(workspace,selected):
    workspace=physical.absolute(str(workspace));result=[];seen=set()
    if not isinstance(selected,list) or len(selected)>256:raise Refused('Native mount plan exceeds its bound')
    for row in selected:
        if not isinstance(row,dict) or not {'source_root','private_root'}<=set(row) or set(row)-{'source_root','private_root','kind'}:
            raise Refused('Select exact native source/private alias pairs and their retained kind')
        kind=alias_kind(row)
        source=physical.absolute(row['source_root']);target=physical.absolute(row['private_root'])
        if (source in seen or source==Path('/') or workspace.is_relative_to(source) or
                source.is_relative_to(workspace) or not target.is_relative_to(workspace) or
                not compatible_source(source,kind) or not (target.is_dir() if kind=='directory' else target.is_file())):
            raise Refused('Native external aliases must have their retained kind and be separate from the private workspace')
        if any(Path(name).is_relative_to(source) for name in (sys.executable,'/proc','/sys','/dev','/etc/passwd','/etc/group')):
            raise Refused('Native external aliases cannot hide required host runtime paths')
        seen.add(source);result.append({'source_root':str(source),'private_root':str(target),**({'kind':'file'} if kind=='file' else {})})
    return sorted(result,key=lambda row:(len(Path(row['source_root']).parts),row['source_root']))


def project_parent(native,workspace,parent,index,cancel=None,*,directory=None):
    """Build a complete private parent before atomically changing its view."""
    entries=[];destination=(directory or workspace)/'namespace-projections'/str(index)
    def cancelled():
        if cancel is not None and cancel.exists():raise InterruptedError('Native filesystem setup cancelled before server dispatch')
    try:
        cancelled()
        if parent.is_relative_to(Path('/proc')):
            raise Refused('Native storage projection cannot replace the process filesystem')
        children=[]
        with os.scandir(parent) as listing:
            for entry in listing:
                if len(children)>=4096:raise Refused('Native parent projection exceeds its entry bound')
                children.append(Path(entry.path))
        for child in sorted(children):
            cancelled();info=child.lstat()
            if stat.S_ISLNK(info.st_mode):entries.append((child.name,'link',os.readlink(child)));continue
            kind='directory' if stat.S_ISDIR(info.st_mode) else 'file'
            descriptor=int(native.syscall(428,-100,os.fsencode(child),1|0x80000|(RECURSIVE if kind=='directory' else 0)))
            if descriptor<0:raise Refused('Native detached directory projection refused; OS errno '+str(ctypes.get_errno()))
            entries.append((child.name,kind,descriptor))
        cancelled();destination.mkdir(mode=0o700,parents=True)
        options=('mode=0700,uid='+str(os.geteuid())+',gid='+str(os.getegid())+',size=16m').encode()
        checked(native.mount(b'tmpfs',os.fsencode(destination),b'tmpfs',2,options))
        for name,kind,value in entries:
            cancelled();target=destination/name
            if kind=='link':target.symlink_to(value)
            else:
                if kind=='directory':target.mkdir()
                else:target.touch(mode=0o600,exist_ok=False)
                checked(native.syscall(429,value,b'',-100,os.fsencode(target),4))
        if workspace.is_relative_to(parent):
            a=(destination/workspace.relative_to(parent)).stat();b=workspace.stat()
            if (a.st_dev,a.st_ino)!=(b.st_dev,b.st_ino):raise Refused('Private parent projection did not preserve its workspace')
        info=destination.stat();cancelled()
        if parent==Path('/'):
            descriptor=os.open(destination,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fchdir(descriptor);os.chroot('.');os.chdir('/')
            finally:os.close(descriptor)
        else:checked(native.mount(os.fsencode(destination),os.fsencode(parent),None,BIND|MOUNT_REC,None))
        return {'parent':str(parent),'device':str(info.st_dev),'inode':str(info.st_ino),
            'original_entries':len(entries),'private_root_switch':parent==Path('/')}
    finally:
        for _name,kind,value in entries:
            if kind!='link':os.close(value)


def activate(workspace,selected,*,directory=None):
    """Change only this independent supervisor's namespace and native child."""
    native=library();workspace=physical.absolute(str(workspace));selected=validate_roots(workspace,selected)
    before=os.readlink('/proc/self/ns/mnt')
    checked(native.unshare(NEW_MOUNT_NAMESPACE))
    checked(native.mount(None,b'/',None,PRIVATE|MOUNT_REC,None))
    checked(native.mount(b'/',b'/',None,BIND|MOUNT_REC,None))
    attributes(native,'/',add=READONLY)
    checked(native.mount(os.fsencode(workspace),os.fsencode(workspace),None,BIND|MOUNT_REC,None))
    attributes(native,workspace,remove=READONLY)
    mounted=[];projections=[];cancel=directory/'cancel' if directory is not None else None
    for row in selected:
        source=Path(row['source_root'])
        if not source.exists():
            parent=source.parent
            while not parent.exists():parent=parent.parent
            private_parent=any(parent.is_relative_to(Path(prior['source_root'])) for prior in mounted)
            if not private_parent:
                device=str(parent.stat().st_dev)
                private_parent=any(parent.is_relative_to(Path(prior['parent'])) and device==prior['device'] for prior in projections)
            if not private_parent:
                projections.append(project_parent(native,workspace,parent,len(projections),cancel,directory=directory))
            if alias_kind(row)=='directory':source.mkdir(parents=True)
            else:source.parent.mkdir(parents=True,exist_ok=True);source.touch(mode=0o600,exist_ok=False)
        checked(native.mount(os.fsencode(row['private_root']),os.fsencode(source),None,BIND|MOUNT_REC,None))
        a=source.stat();b=Path(row['private_root']).stat()
        if (a.st_dev,a.st_ino)!=(b.st_dev,b.st_ino):raise Refused('Native mounted directory differs from its private target')
        mounted.append(row)
    if projections:
        attributes(native,'/',add=READONLY);attributes(native,workspace,remove=READONLY)
        for row in mounted:attributes(native,row['source_root'],remove=READONLY)
    if (not os.statvfs('/').f_flag&os.ST_RDONLY or os.statvfs(workspace).f_flag&os.ST_RDONLY):
        raise Refused('Native host-read-only/private-workspace-writable isolation was not established')
    after=os.readlink('/proc/self/ns/mnt')
    if before==after:raise Refused('Native recovery did not receive a separate mount namespace')
    return {'backend':'linux-mount-setattr-v1','original_namespace':before,'private_namespace':after,
        'host_root_readonly':True,'private_workspace_writable':True,'workspace':str(workspace),'roots':mounted,
        **({'private_parent_projections':projections} if projections else {})}


def observe(pid,expected):
    """Independently observe the original native process's actual mount view."""
    base=Path('/proc')/str(pid)
    if os.readlink(base/'ns/mnt')!=expected['private_namespace']:
        raise Refused('Original native process filesystem namespace changed')
    root=base/'root'
    for row in expected.get('private_parent_projections',[]):
        info=(root/row['parent'].lstrip('/')).stat()
        if (str(info.st_dev),str(info.st_ino))!=(row['device'],row['inode']):
            raise Refused('Original native process parent projection changed')
    for row in expected['roots']:
        a=(root/row['source_root'].lstrip('/')).stat();b=Path(row['private_root']).stat()
        if (a.st_dev,a.st_ino)!=(b.st_dev,b.st_ino):raise Refused('Original native process external alias no longer selects its private bytes')
    decode=lambda value:re.sub(r'\\([0-7]{3})',lambda match:chr(int(match.group(1),8)),value)
    entries=[line.split() for line in (base/'mountinfo').read_text().splitlines()]
    mounts={decode(row[4]):set(row[5].split(',')) for row in entries}
    if 'ro' not in mounts.get('/',set()) or 'rw' not in mounts.get(expected['workspace'],set()):
        raise Refused('Original native process host/private mount permissions changed')
    files=sum(alias_kind(row)=='file' for row in expected['roots'])
    return {'native_filesystem_isolation_observed':True,'private_namespace':expected['private_namespace'],
        'host_root_readonly':True,'private_workspace_writable':True,'external_directory_aliases':len(expected['roots'])-files,
        **({'external_file_aliases':files} if files else {})}
