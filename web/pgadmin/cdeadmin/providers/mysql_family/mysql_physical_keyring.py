"""Private native file-keyring snapshots; MySQL/XtraBackup own encryption."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil

try:
    import _cdeadmin_physical_worker as physical
except ModuleNotFoundError:
    from . import mysql_physical_worker as physical

host=physical.host
Refused=physical.Refused
DIRECTORY='.scratchrobin-keyring'
FORMAT='mysql97-component-keyring-file-v1'
TRANSITION='.scratchrobin-transition.key'
OPTIONS='keyring-native.cnf'
STAGED='native-keyring-input'


def read_key(directory):
    value=physical.metadata(directory/'transition.key')
    if not re.fullmatch('[0-9a-f]{64}',value):raise Refused('Native backup transition key is unavailable or changed')
    return value


def audit(directory):
    root=directory/DIRECTORY
    if not root.exists():return None
    if root.is_symlink() or not root.is_dir():raise Refused('Native keyring snapshot must be a private directory')
    metadata=physical.read_json(root/'metadata.json')
    if (not isinstance(metadata,dict) or set(metadata)!={'format','component','server_plugin_directory','encryption'} or
            metadata['format']!=FORMAT or metadata['component']!='component_keyring_file' or
            not isinstance(metadata['server_plugin_directory'],str) or not Path(metadata['server_plugin_directory']).is_absolute() or
            not isinstance(metadata['encryption'],dict) or set(metadata['encryption'])!={'redo','undo','binlog'} or
            any(type(value) is not bool for value in metadata['encryption'].values())):
        raise Refused('Native keyring snapshot metadata is unavailable or incompatible')
    read_key(root)
    for name in ('keyring','transition.key','metadata.json'):
        path=root/name
        if path.is_symlink():raise Refused('Native keyring material cannot be a symbolic link')
        host.regular(path)
    return {**metadata,'keyring_sha256':host.file_hash(root/'keyring'),
        'transition_key_sha256':host.file_hash(root/'transition.key'),'keyring_bytes':str((root/'keyring').stat().st_size),
        'private_key_material_retained':True}


def library_snapshot(value):
    directory=physical.absolute(value)
    if not directory.is_dir():raise Refused('Native component library directory is unavailable')
    files=[]
    for path in sorted(directory.iterdir()):
        if path.is_dir():continue
        # Package-managed library symlinks are materialized into private copies;
        # the source entry's resolved bytes, rather than its spelling, are bound.
        info=host.regular(path)
        files.append({'name':path.name,'bytes':str(info.st_size),'sha256':host.file_hash(path)})
        if len(files)>4096:raise Refused('Native component library snapshot exceeds its bound')
    return {'path':str(directory),'manifest_sha256':host.digest(files),'file_count':len(files)},files


def inspect(request, snapshot=None):
    selected=request.get('keyring')
    if selected is None:
        if snapshot is not None:raise Refused('Review retention and use of the native backup keyring material explicitly')
        return None
    if not isinstance(selected,dict) or set(selected)!={'xtrabackup_plugin_dir'}:
        raise Refused('Select the native XtraBackup component directory explicitly')
    xtra=physical.absolute(selected['xtrabackup_plugin_dir'])/'component_keyring_file.so'
    host.regular(xtra)
    source=request.get('source_keyring') if request['phase'] in {'backup','incremental'} else None
    if source is not None:
        if (not isinstance(source,dict) or set(source)!={'component','data_file','server_plugin_directory','encryption'} or
                source['component']!='component_keyring_file'):
            raise Refused('Select the initialized native GPL file-keyring component')
        data=physical.absolute(source['data_file']);host.regular(data)
        plugins=source['server_plugin_directory'];encryption=source['encryption']
    elif snapshot is not None:
        data=None;plugins=snapshot['server_plugin_directory'];encryption=snapshot['encryption']
    else:
        # A plain ancestor can precede the first encrypted incremental.
        return None
    if (not isinstance(encryption,dict) or set(encryption)!={'redo','undo','binlog'} or
            any(type(value) is not bool for value in encryption.values())):
        raise Refused('Native source encryption policy is unavailable')
    server,files=library_snapshot(plugins)
    if not any(item['name']=='component_keyring_file.so' for item in files):raise Refused('The native server file-keyring component is unavailable')
    private=Path(server['path']).parent/'private'
    dependencies=library_snapshot(str(private))[0] if private.is_dir() else None
    return {'component':'component_keyring_file','xtrabackup_plugin_dir':str(xtra.parent),
        'xtrabackup_component_sha256':host.file_hash(xtra),'server_plugins':server,
        'server_private_libraries':dependencies,'source_data_file':str(data) if data is not None else None,
        'source_manifest':str(Path(request['binding']['datadir'])/'mysqld.my') if source is not None and (Path(request['binding']['datadir'])/'mysqld.my').is_file() else None,
        'encryption':encryption,'retains_private_key_material':True}


def copy_file(source,target):
    with host.regular_stream(source) as stream:
        before=os.fstat(stream.fileno())
        with target.open('xb') as output:
            host.private_file(target);shutil.copyfileobj(stream,output,1024*1024);output.flush();os.fsync(output.fileno())
        after=os.fstat(stream.fileno())
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
        raise Refused('Native keyring or library bytes changed while copied')


def backup_key(directory, original=None):
    value=read_key(original/DIRECTORY) if original is not None and audit(original) is not None else secrets.token_hex(32)
    path=directory/TRANSITION
    with path.open('x',encoding='ascii') as stream:host.private_file(path);stream.write(value)
    return value


def capture(directory,target,context):
    root=target/DIRECTORY;root.mkdir(mode=0o700)
    copy_file(Path(context['source_data_file']),root/'keyring')
    copy_file(directory/TRANSITION,root/'transition.key')
    if context['source_manifest'] is not None:copy_file(Path(context['source_manifest']),root/'mysqld.my')
    host.save(root/'metadata.json',{'format':FORMAT,'component':'component_keyring_file',
        'server_plugin_directory':context['server_plugins']['path'],'encryption':context['encryption']})
    (directory/TRANSITION).unlink()
    return audit(target)


def native_options(directory, key):
    if not re.fullmatch('[0-9a-f]{64}',key):raise Refused('Native backup transition key is invalid')
    path=directory/OPTIONS
    with path.open('x',encoding='ascii') as stream:
        host.private_file(path);stream.write('[xtrabackup]\ntransition-key="'+key+'"\n')
    return path


def prepare_options(target, option):
    # Native prepare reads target/backup-my.cnf before defaults-file selection.
    # Include the secret section only from this private working copy.
    if any(char in str(option) for char in '\r\n'):
        raise Refused('The private native option-file path cannot contain a line break')
    path=target/'backup-my.cnf';original=path.read_bytes()
    with path.open('ab') as stream:
        host.private_file(path);stream.write(b'\n!include '+str(option).encode('utf8')+b'\n');stream.flush();os.fsync(stream.fileno())
    return original


def restore_prepare_options(target, original):
    if original is None:return
    path=target/'backup-my.cnf'
    with path.open('wb') as stream:
        host.private_file(path);stream.write(original);stream.flush();os.fsync(stream.fileno())


def stage_prepare_material(directory,target):
    # Native incremental cleanup removes unknown files from subdirectories.
    # Hold opaque application key material outside its native working datadir.
    if audit(target) is not None:(target/DIRECTORY).rename(directory/STAGED)


def restore_prepare_material(directory,target):
    stash=directory/STAGED
    if stash.exists():
        if (target/DIRECTORY).exists():raise Refused('Native preparation unexpectedly replaced the private keyring directory')
        stash.rename(target/DIRECTORY)


def apply_snapshot(target, incremental=None):
    current=audit(target)
    if incremental is not None:
        delta=audit(incremental)
        if delta is not None:
            if current is not None and current['transition_key_sha256']!=delta['transition_key_sha256']:
                raise Refused('Native incremental key material differs from its original chain')
            if (target/DIRECTORY).exists():shutil.rmtree(target/DIRECTORY)
            shutil.copytree(incremental/DIRECTORY,target/DIRECTORY)
            current=audit(target)
    return current


def copied_snapshot(original,target):
    if audit(original) is None:return
    root=target/DIRECTORY
    if not root.exists():shutil.copytree(original/DIRECTORY,root)
    if audit(target)!=audit(original) or physical.manifest(root)!=physical.manifest(original/DIRECTORY):
        raise Refused('Copied native keyring material differs from its sealed input')
    root.chmod(0o700)
    for path in root.iterdir():host.private_file(path)


def stage_libraries(selected,target):
    current,files=library_snapshot(selected['path'])
    if current!=selected:raise Refused('Native component or private libraries changed after review')
    target.mkdir(mode=0o700)
    for item in files:
        copy_file(Path(selected['path'])/item['name'],target/item['name'])
        if host.file_hash(target/item['name'])!=item['sha256']:raise Refused('Staged native library bytes changed')


def runtime(directory,data,context):
    material=audit(data)
    if material is None:raise Refused('Native encrypted recovery key material is unavailable')
    plugins=directory/'runtime-plugins';stage_libraries(context['server_plugins'],plugins)
    if context['server_private_libraries'] is not None:stage_libraries(context['server_private_libraries'],directory/'private')
    host.save(plugins/'component_keyring_file.cnf',{'path':str(data/DIRECTORY/'keyring'),'read_only':False})
    if (data/DIRECTORY/'mysqld.my').is_file():
        (data/'mysqld.my').unlink(missing_ok=True);copy_file(data/DIRECTORY/'mysqld.my',data/'mysqld.my')
    else:host.save(data/'mysqld.my',{'components':'file://component_keyring_file'})
    return ['--plugin-dir='+str(plugins),
        '--innodb-redo-log-encrypt='+('ON' if material['encryption']['redo'] else 'OFF'),
        '--innodb-undo-log-encrypt='+('ON' if material['encryption']['undo'] else 'OFF'),
        '--binlog-encryption='+('ON' if material['encryption']['binlog'] else 'OFF')]


def cleanup(directory, *, material_retained):
    (directory/OPTIONS).unlink(missing_ok=True)
    if not material_retained:(directory/TRANSITION).unlink(missing_ok=True)
