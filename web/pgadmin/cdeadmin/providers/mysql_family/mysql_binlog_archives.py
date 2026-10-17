"""Native MySQL Shell binary-log archives on the explicit application host."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from .mysql_clone import configure,rows
from ...sdk.tooling import ProviderToolGrant
from ...security import SecretLease

CREDENTIAL_FILE='CDEADMIN_NATIVE_BINLOG_CREDENTIAL_FILE'


class BinlogArchiveError(ValueError):
    pass


def capture(connection):
    """Observe an independently owned attachment, never an editor session."""
    configure(connection)
    row=rows(connection,"SELECT VERSION() AS version,@@server_uuid AS server_uuid,CURRENT_USER() AS authenticated_principal,CURRENT_ROLE() AS active_role,@@global.log_bin AS log_bin,@@global.gtid_mode AS gtid_mode,@@global.gtid_executed AS gtid_executed,@@global.gtid_purged AS gtid_purged")[0]
    if row['version'].split('-')[0]!='9.7.0':raise BinlogArchiveError('Select native MySQL9.7.0')
    identity={key:row[key] for key in ('version','server_uuid','authenticated_principal','active_role')}
    enabled=row['log_bin'] in (1,True,'ON')
    return {'identity':identity,'state':{key:row[key] for key in ('log_bin','gtid_mode','gtid_executed','gtid_purged')},
        'status':'available' if enabled else 'native_binary_logging_disabled',
        'logs':rows(connection,'SHOW BINARY LOGS') if enabled else [],
        'current':rows(connection,'SHOW BINARY LOG STATUS')[0] if enabled else None}


def delegate_credentials(client,route):
    """Resolve provider-tool authority in the admitting request's context."""
    references=dict(route.get('credential_references') or {})
    if route.get('credential_reference_id') is not None:references.setdefault('database_password',route['credential_reference_id'])
    native={'database_password':'password','database_password_2':'password2','database_password_3':'password3'}
    kinds=[kind for kind in native if kind in references];delegated=[]
    def seal(values):
        if len(values)!=len(kinds):raise BinlogArchiveError('Native tool credential bindings changed')
        payload={'password':'',**{native[kind]:value for kind,value in zip(kinds,values)}}
        delegated.append(SecretLease(json.dumps(payload,ensure_ascii=True).encode('utf8')))
    client._tool_secrets(route,seal)
    return delegated[0]


def connection_options(client,route):
    # Preserve the provider's native TLS/compression policy. Passwords are
    # supplied separately as JSON, avoiding line-oriented credential loss.
    result={'scheme':'mysql'}
    names={'host','port','user','ssl-mode','ssl-ca','ssl-cert','ssl-key','ssl-cipher','tls-version','tls-ciphersuites'}
    for argument in client._shell_connection_arguments({**route,'host':route.get('host') or 'localhost'}):
        if '=' not in argument:continue
        name,value=argument[2:].split('=',1)
        if name in names:result[name]=int(value) if name=='port' else value
        elif name=='compress':result['compression']=value.lower()
    if route.get('unix_socket'):
        result.pop('host',None);result.pop('port',None);result['socket']=route['unix_socket']
    return result


def program_identity(client,route,workspace,*,progress=None,cancel=None):
    grant=ProviderToolGrant('mysql-shell',str(workspace),str(route.get('host') or 'localhost'),int(route.get('port',3306)),timeout_seconds=30)
    result=client._tool_runner.run(grant,['--version'],progress=progress,cancel_signal=cancel)
    if result['return_code']!=0 or not re.search(r'\bVer 9\.7\.0\b',result['stdout']):
        raise BinlogArchiveError('Native binary-log dumps require MySQL Shell9.7.0')
    return {'executable_sha256':result['executable_sha256'],'tool_version':'9.7.0',
        'execution_host':{key:result['execution_host'][key] for key in ('kind','platform')}}


def stage_continuation(source,destination,expected,identity,*,cancel=None):
    """Own a stable input before running; retained archive deletion is safe."""
    source,destination=Path(source),Path(destination)
    if destination.exists():raise BinlogArchiveError('Native continuation staging must be new')
    destination.mkdir(mode=0o700)
    for row in expected['files']:
        if cancel is not None and cancel.is_set():raise InterruptedError('Archive continuation staging cancelled')
        relative=Path(row['path'])
        if relative.is_absolute() or '..' in relative.parts:raise BinlogArchiveError('Native continuation file escapes its archive')
        original,target=source/relative,destination/relative
        target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        info=original.lstat()
        if not stat.S_ISREG(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
            raise BinlogArchiveError('Native continuation file is not regular')
        # Metadata is always independently copied. Native data files are
        # immutable and can share file bytes while owning separate names.
        if original.suffix!='.json':
            try:os.link(original,target,follow_symlinks=False);continue
            except OSError:pass
        descriptor=os.open(original,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0))
        with os.fdopen(descriptor,'rb') as incoming,target.open('xb') as outgoing:
            opened=os.fstat(incoming.fileno())
            if not stat.S_ISREG(opened.st_mode) or (info.st_dev,info.st_ino)!=(opened.st_dev,opened.st_ino):
                raise BinlogArchiveError('Native continuation file changed while opening')
            from ...operations.fileio import private_file
            private_file(target)
            while data:=incoming.read(1024*1024):
                if cancel is not None and cancel.is_set():raise InterruptedError('Archive continuation staging cancelled')
                outgoing.write(data)
            outgoing.flush();os.fsync(outgoing.fileno())
    if verify(destination,identity,cancel=cancel)!=expected:raise BinlogArchiveError('Native continuation staging postimage differs')
    return destination


def run_dump(client,route,credentials,source,selected,directory,workspace,*,since_directory=None,expected_program=None,
             dry_run=False,cancel=None,progress=None):
    directory,workspace=Path(directory),Path(workspace)
    if directory.exists() and not dry_run:raise BinlogArchiveError('A native dump destination must be new')
    # Both the new archive and any continuation must be inside the explicit
    # owner/endpoint filesystem grant, without following a caller's path.
    for path in (directory,since_directory):
        if path is not None:
            try:Path(path).resolve().relative_to(workspace.resolve())
            except ValueError:raise BinlogArchiveError('Native archive path escapes its filesystem grant') from None
    identity=program_identity(client,route,workspace,progress=progress,cancel=cancel)
    if expected_program is not None and identity!=expected_program:raise BinlogArchiveError('Native archive executable or execution host changed')
    script=('const authentication=JSON.parse(os.loadTextFile(os.getenv('+json.dumps(CREDENTIAL_FILE)+')));\n'
        'const target='+json.dumps(connection_options(client,route),ensure_ascii=True)+';\n'
        'for(const name of Object.keys(authentication))target[name]=authentication[name];\n'
        'shell.connect(target);\n'+dump_script(directory,source,selected,since_directory=since_directory,dry_run=dry_run))
    script_path=directory.parent/('review.js' if dry_run else 'archive.js')
    from ...operations.fileio import private_file
    with script_path.open('x',encoding='utf8') as stream:
        private_file(script_path);stream.write(script);stream.flush();os.fsync(stream.fileno())
    grant=ProviderToolGrant('mysql-shell',str(workspace),str(route.get('host') or 'localhost'),int(route.get('port',3306)),
        timeout_seconds=selected['timeout_seconds'],allow_unbounded_runtime=selected['timeout_seconds'] is None,
        secret_environment_names=(CREDENTIAL_FILE,))
    result=credentials.use(lambda view:client._tool_runner.run(grant,
        ['--no-defaults','--js','--log-level=none','--file='+str(script_path)],secret_config=bytes(view),
        secret_argument=None,secret_environment_name=CREDENTIAL_FILE,secret_suffix='.json',progress=progress,cancel_signal=cancel))
    observation={key:result[key] for key in ('executable_id','executable_sha256','execution_host','network_grant','return_code','process_observation')}
    if result['return_code']!=0 or 'CDEADMIN_BINLOG_DUMP_RETURNED' not in result['stdout']:
        error=BinlogArchiveError('Native binary-log dump did not return successfully');error.observation=observation;raise error
    if not dry_run and not directory.exists():
        return {'tool':observation,'program':identity,'native_operation_returned':True,'artifact':None,
            'new_snapshot_produced':False,'continuation_cursor_advanced':False}
    try:artifact=None if dry_run else verify(directory,source,cancel=cancel)
    except BaseException as error:error.observation=observation;raise
    return {'tool':observation,'program':identity,'native_operation_returned':True,
        'new_snapshot_produced':not dry_run,'artifact':artifact}


def options(value):
    allowed={'start_file','start_position','since_job_id','compression','threads','timeout_seconds'}
    if not isinstance(value,dict) or set(value)-allowed:raise BinlogArchiveError('Invalid native binary-log archive options')
    since=value.get('since_job_id');filename=value.get('start_file');position=value.get('start_position','4')
    if since is not None:
        from uuid import UUID
        try:
            if not isinstance(since,str) or str(UUID(since))!=since:raise ValueError()
        except (TypeError,ValueError,AttributeError):raise BinlogArchiveError('Select a completed archive by its job identity') from None
        if 'start_file' in value or 'start_position' in value:raise BinlogArchiveError('Select an archive continuation or a native starting position')
    elif not isinstance(filename,str) or not filename or '\x00' in filename or len(filename.encode('utf8'))>1024:
        raise BinlogArchiveError('Select an exact native binary-log filename')
    if type(position) is int:position=str(position)
    if not isinstance(position,str) or not re.fullmatch(r'[1-9][0-9]*',position) or not 4<=int(position)<=18446744073709551615:
        raise BinlogArchiveError('Select a native uint64 binary-log position of at least4')
    compression=value.get('compression','zstd;level=1')
    if not isinstance(compression,str) or not re.fullmatch(r'(?:none|gzip(?:;level=[0-9])?|zstd(?:;level=(?:[1-9]|1[0-9]|2[0-2]))?)',compression):
        raise BinlogArchiveError('Select native none, gzip or Zstandard compression and level')
    threads=value.get('threads',4);timeout=value.get('timeout_seconds',3600)
    if type(threads) is not int or not 1<=threads<=64:raise BinlogArchiveError('Select between1 and64 native dump threads')
    if timeout is not None and (type(timeout) is not int or not 1<=timeout<=2147483647):
        raise BinlogArchiveError('Select positive runtime seconds or null for no deadline')
    return {'since_job_id':since,'start_file':None if since else filename,'start_position':None if since else position,
        'compression':compression,'threads':threads,'timeout_seconds':timeout}


def dump_script(directory,source,selected,*,since_directory=None,dry_run=False):
    native={'compression':selected['compression'],'threads':selected['threads'],'showProgress':False,'dryRun':dry_run}
    if selected['since_job_id']:
        if since_directory is None:raise BinlogArchiveError('A verified native archive continuation is required')
        native['since']=str(since_directory)
    else:native['startFrom']=selected['start_file']+':'+str(selected['start_position'])
    # Role/principal checks happen on the utility's own session, before it
    # opens its native archive operation. No editor transaction is borrowed.
    expected=[source[key] for key in ('server_uuid','version','authenticated_principal','active_role')]
    return ('const observed=shell.getSession().runSql("SELECT @@server_uuid,VERSION(),CURRENT_USER(),CURRENT_ROLE()").fetchOne();\n'
        'if(!'+json.dumps(expected,ensure_ascii=True,separators=(',',':'))+'.every((value,index)=>value===observed[index]))throw new Error("Archive source identity or native role changed");\n'
        'util.dumpBinlogs('+json.dumps(str(directory))+','+json.dumps(native,separators=(',',':'))+');\n'
        'print("CDEADMIN_BINLOG_DUMP_RETURNED");\n')


def _file(path,cancel):
    before=path.lstat()
    if not stat.S_ISREG(before.st_mode) or getattr(before,'st_file_attributes',0)&0x400:
        raise BinlogArchiveError('Native archive contains a link or nonregular file')
    digest=hashlib.sha256();size=0
    descriptor=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0))
    with os.fdopen(descriptor,'rb') as stream:
        opened=os.fstat(stream.fileno())
        if (before.st_dev,before.st_ino)!=(opened.st_dev,opened.st_ino):raise BinlogArchiveError('Native archive file changed while opening')
        while data:=stream.read(1024*1024):
            if cancel is not None and cancel.is_set():raise InterruptedError('Archive verification cancelled')
            digest.update(data);size+=len(data)
        after=os.fstat(stream.fileno())
    if (opened.st_size,opened.st_mtime_ns,opened.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns) or size!=after.st_size:
        raise BinlogArchiveError('Native archive file changed during verification')
    return {'size':size,'sha256':digest.hexdigest()}


def manifest(directory,*,cancel=None):
    """Full application byte inventory; no native event-checksum claim."""
    directory=Path(directory);files=[];pending=[directory];entries=0
    while pending:
        parent=pending.pop();info=parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
            raise BinlogArchiveError('Native archive contains a directory link or reparse point')
        for path in sorted(parent.iterdir()):
            entries+=1
            if entries>100000:raise BinlogArchiveError('Native archive exceeds the file inventory limit')
            if stat.S_ISDIR(path.lstat().st_mode):pending.append(path)
            else:files.append({'path':path.relative_to(directory).as_posix(),**_file(path,cancel)})
    return sorted(files,key=lambda row:row['path'])


def _json(path):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise BinlogArchiveError('Native archive metadata contains duplicate keys')
            result[key]=value
        return result
    try:
        descriptor=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0))
        with os.fdopen(descriptor,'rb') as stream:
            info=os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400 or info.st_size>4*1024*1024:
                raise BinlogArchiveError('Native archive metadata is not a bounded regular file')
            value=json.loads(stream.read(4*1024*1024+1).decode('utf8'),object_pairs_hook=unique)
    except (OSError,UnicodeError,json.JSONDecodeError):raise BinlogArchiveError('Native archive metadata is unavailable') from None
    if not isinstance(value,dict):raise BinlogArchiveError('Native archive metadata must be an object')
    return value


def verify(directory,expected_source,*,cancel=None):
    """Verify completed9.7 Shell metadata and exact file byte postimages."""
    directory=Path(directory);files=manifest(directory,cancel=cancel)
    info=_json(directory/'@.binlog.info.json')
    if (info.get('version')!='2.0.1' or info.get('origin')!='dumpBinlogs' or
        info.get('source',{}).get('serverUuid')!=expected_source['server_uuid'] or
        info.get('source',{}).get('version')!='9.7.0'):
        raise BinlogArchiveError('Native archive source identity or format differs')
    snapshots=[path for path in directory.iterdir() if path.is_dir()]
    if len(snapshots)!=1:raise BinlogArchiveError('Native archive must contain one completed snapshot')
    root=snapshots[0];native=_json(root/'@.binlog.json');done=_json(root/'@.binlog.done.json')
    if any(path.is_dir() for path in root.iterdir()):raise BinlogArchiveError('Native archive has an unexpected nested directory')
    start=native.get('startFrom');finished_start=done.get('startFrom',start)
    # The initial file-position dump learns its starting GTID set while
    # streaming. The completion sidecar contains that final observation.
    if (native.get('version')!='2.0.1' or native.get('origin')!='dumpBinlogs' or
        not isinstance(done.get('timestamp'),str) or not isinstance(start,dict) or not isinstance(finished_start,dict) or
        any(start.get(key)!=finished_start.get(key) for key in ('file','position')) or
        start.get('gtidExecuted') and start['gtidExecuted']!=finished_start.get('gtidExecuted')):
        raise BinlogArchiveError('Native archive snapshot completion differs')
    names=native.get('binlogs');basenames=native.get('basenames')
    if not isinstance(names,list) or not names or len(set(names))!=len(names) or not isinstance(basenames,dict) or set(basenames)!=set(names):
        raise BinlogArchiveError('Native archive binary-log inventory differs')
    by_path={row['path']:row for row in files};expected={'@.binlog.info.json',root.name+'/@.binlog.json',root.name+'/@.binlog.done.json'}
    integrity=[]
    for name in names:
        base=basenames[name]
        if not isinstance(base,str) or Path(base).name!=base or base in {'.','..'} or '\x00' in base:
            raise BinlogArchiveError('Native archive basename escapes its snapshot')
        sidecar=root/(base+'.json');metadata=_json(sidecar)
        extension=metadata.get('extension')
        if not isinstance(extension,str) or not re.fullmatch(r'(?:\.[A-Za-z0-9]+)?',extension):raise BinlogArchiveError('Native archive compression suffix differs')
        relative=root.name+'/'+base+extension
        if metadata.get('binlog')!=name or type(metadata.get('fileBytes')) is not int or relative not in by_path or by_path[relative]['size']!=metadata['fileBytes']:
            raise BinlogArchiveError('Native archive binary-log file postimage differs')
        from .mysql_binlog_integrity import verify_frames
        integrity.append({'binlog':name,**verify_frames(directory/relative,metadata.get('compression'),
            metadata.get('dataBytes'),metadata.get('eventCount'),cancel=cancel)})
        expected.update({relative,root.name+'/'+base+'.json'})
    if set(by_path)!=expected:raise BinlogArchiveError('Native archive has missing or unrecorded files')
    if manifest(directory,cancel=cancel)!=files:raise BinlogArchiveError('Native archive changed during metadata verification')
    return {'format':'mysqlsh-binlog-dump@2.0.1','files':files,'file_count':len(files),'total_bytes':sum(row['size'] for row in files),
        'start_from':finished_start,'end_at':native.get('endAt'),'gtid_set':done.get('gtidSet',native.get('gtidSet')),
        'verification_scope':'application_file_hashes_native_completion_metadata_and_v4_event_framing_crc32',
        'event_integrity':integrity,'native_event_checksums_verified_where_present':True,
        'source_uuid':expected_source['server_uuid']}
