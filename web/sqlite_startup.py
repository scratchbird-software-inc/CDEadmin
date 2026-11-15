"""Reviewed host directory policies applied before SQLite initialization.

Keep this module independent of pgadmin/sqlite3. The native runtime itself
attests that it was uninitialized before opening its sole bootstrap database.
"""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import uuid
import sqlite_native_component as component

SCHEMA='scratchrobin.sqlite-host-startup@1'
NAMES=('temp_store_directory','data_store_directory')
_APPLIED=None
_FAILED=None
MAX_POLICY_BYTES=65536


def policy_path(config):
    path=Path(getattr(config,'CDEADMIN_SQLITE_STARTUP_POLICY','') or Path(config.DATA_DIR)/'sqlite-startup-policy.json').expanduser()
    if not path.is_absolute():raise ValueError('The host startup policy filename must be absolute')
    return path


def identity(path):
    value=path.stat()
    if not stat.S_ISDIR(value.st_mode) or value.st_ino<=0:raise ValueError('A stable native directory identity is required')
    return {'device':value.st_dev,'inode':value.st_ino}


def directory_setting(mode,directory,root):
    if mode=='DEFAULT':
        if directory not in (None,''):raise ValueError('Default mode does not take a directory')
        return {'mode':'DEFAULT'}
    if mode!='DIRECTORY' or not isinstance(directory,str) or not directory or '\x00'in directory or len(directory.encode())>16384:
        raise ValueError('Select an absolute application-host directory or DEFAULT')
    path=Path(directory)
    if not path.is_absolute():raise ValueError('Startup directory must be absolute')
    if not isinstance(root,str) or not root:raise ValueError('Registered filesystem authority is required')
    authority=Path(root).resolve(strict=True);path=path.resolve(strict=True)
    if not path.is_relative_to(authority):raise ValueError('Startup directory is outside the registered filesystem root')
    return {'mode':'DIRECTORY','directory':str(path),'filesystem_root':str(authority),
        'directory_identity':identity(path),'root_identity':identity(authority)}


def validate_setting(value, *, observe_filesystem=False):
    if not isinstance(value,dict):raise ValueError('Startup setting must be typed')
    if value=={'mode':'DEFAULT'}:return ''
    keys={'mode','directory','filesystem_root','directory_identity','root_identity'}
    if set(value)!=keys or value.get('mode')!='DIRECTORY':raise ValueError('Unknown startup directory contract')
    for key in ('directory','filesystem_root'):
        text=value[key]
        if not isinstance(text,str) or not text or '\x00'in text or len(text.encode())>16384 or not Path(text).is_absolute():
            raise ValueError('Startup paths must be bounded absolute UTF-8')
    if not Path(value['directory']).is_relative_to(Path(value['filesystem_root'])):raise ValueError('Startup directory escaped its authority')
    for key in ('directory_identity','root_identity'):
        item=value[key]
        if not isinstance(item,dict) or set(item)!={'device','inode'} or any(type(number)is not int or number<0 for number in item.values()) or item['inode']==0:
            raise ValueError('Startup directory identity is unavailable')
    if observe_filesystem:
        for path_key,id_key in [('directory','directory_identity'),('filesystem_root','root_identity')]:
            path=Path(value[path_key])
            if str(path.resolve(strict=True))!=value[path_key] or identity(path)!=value[id_key]:
                raise ValueError('Startup directory/root changed since acceptance; review again')
    return value['directory']


def read_policy(path):
    path=Path(path)
    try:descriptor=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    except FileNotFoundError:return None,hashlib.sha256(b'').hexdigest()
    with os.fdopen(descriptor,'rb')as stream:
        information=os.fstat(stream.fileno())
        if not stat.S_ISREG(information.st_mode) or information.st_size>MAX_POLICY_BYTES:
            raise ValueError('Startup policy is not a bounded regular file')
        if os.name!='nt' and (information.st_mode&0o022 or information.st_uid!=os.getuid()):
            raise ValueError('Startup policy must be owned by the application OS user and not writable by others')
        data=stream.read(MAX_POLICY_BYTES+1)
    if len(data)>MAX_POLICY_BYTES:raise ValueError('Startup policy is too large')
    value=json.loads(data.decode('utf8'))
    if (not isinstance(value,dict) or set(value)-{'schema','settings','accepted_at','accepted_by_user_id','source_endpoint_id','review_id'} or
            value.get('schema')!=SCHEMA or not isinstance(value.get('settings'),dict) or set(value['settings'])-set(NAMES)):
        raise ValueError('Unknown startup policy file; preserve it for review')
    for setting in value['settings'].values():validate_setting(setting)
    return value,hashlib.sha256(data).hexdigest()


def applied_state():return dict(_APPLIED)if _APPLIED is not None else None


def publish_policy_file(path,data):
    """Durable atomic publication with cleanup limited to our own staging file."""
    path=Path(path);staging=path.with_name('.'+path.name+'.'+uuid.uuid4().hex);created=False
    try:
        with staging.open('xb')as stream:
            created=True;component.file_io().private_file(staging)
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        component.file_io().durable_replace(staging,path)
    finally:
        if created:staging.unlink(missing_ok=True)


def _write_receipt(path,receipt):
    data=(json.dumps(receipt,indent=2)+'\n').encode('utf8')
    publish_policy_file(path,data)


def apply_configured_policy(config):
    global _APPLIED,_FAILED
    if _FAILED is not None:raise RuntimeError('A failed SQLite startup policy attempt requires a fresh process; its original receipt is preserved')
    path=policy_path(config);policy,revision=read_policy(path)
    if policy is None:return None
    if _APPLIED is not None:
        if _APPLIED['policy_revision']!=revision:raise RuntimeError('A new SQLite startup policy requires a fresh process')
        return dict(_APPLIED)
    receipt={'schema':'scratchrobin.sqlite-host-startup-receipt@1','policy_revision':revision,
        'process_id':os.getpid(),'started_at':datetime.now(timezone.utc).isoformat(),
        'native_applied':False,'application_database_opened_by_startup_workflow':False,'automatic_retry':False,
        'physical_temporary_directory_observed':False,'complete':False}
    loaded=None
    try:
        settings=policy['settings']
        if not settings:
            receipt.update(complete=True,outcome='no_override_configured',native_dispatched=False)
        else:
            for setting in settings.values():validate_setting(setting,observe_filesystem=True)
            filename=getattr(config,'CDEADMIN_SQLITE_CONFIG_LIBRARY','') or component.installed_library()
            if not filename:raise RuntimeError('The native SQLite configuration component is required for the accepted startup policy')
            loaded=component.load(filename);loaded.retain()
            wanted=[validate_setting(settings[name])if name in settings else None for name in NAMES]
            native=loaded.module.startup_directories(*wanted)
            receipt.update(native=native,native_component=dict(loaded.program))
            if not native.get('complete'):raise RuntimeError('Native SQLite startup admission/configuration was not confirmed')
            # Attest that the interpreter uses the very same library instance,
            # before opening application/configuration files. The probe is
            # private :memory: state and never becomes a query session.
            import sqlite3
            class Probe(sqlite3.Connection):pass
            capsule=loaded.module.begin();probe=None;finished=False
            try:
                probe=sqlite3.connect(':memory:',factory=Probe,cached_statements=0)
                loaded.module.finish(capsule,probe);finished=True
            finally:
                if probe is not None:probe.close()
                if finished:loaded.module.closed(capsule,probe)
                else:loaded.module.cancel(capsule)
            receipt.update(complete=True,native_applied=True,native_dispatched=True,
                interpreter_library_instance_attested=True,interpreter_probe_closed=True,
                outcome='native_startup_policy_applied')
    except BaseException as error:
        receipt.update(outcome='startup_policy_not_confirmed',failure_type=type(error).__name__)
        _FAILED=dict(receipt)
        _write_receipt(path.with_suffix(path.suffix+'.receipt.json'),receipt)
        raise RuntimeError('SQLite host startup policy failed; application databases were not opened by this workflow. Inspect its current receipt.')from error
    finally:
        if loaded is not None:loaded.release()
    _write_receipt(path.with_suffix(path.suffix+'.receipt.json'),receipt)
    _APPLIED=receipt
    return dict(receipt)


def require_applied_policy(config):
    policy,revision=read_policy(policy_path(config))
    if policy is not None and (_APPLIED is None or _APPLIED['policy_revision']!=revision or not _APPLIED['complete']):
        raise RuntimeError('Accepted SQLite host policy requires the canonical startup hook in a fresh process, before importing pgadmin/sqlite3')
