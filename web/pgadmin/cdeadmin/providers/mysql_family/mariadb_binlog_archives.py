"""Native MariaDB12.2.2 closed binary-log retrieval and sealed verification."""
import json
import os
from pathlib import Path,PureWindowsPath
import re
import shutil
import stat

from .mysql_clone import rows
from .mysql_binlog_archives import BinlogArchiveError,manifest,_json,seal
from .mysql_binlog_integrity import verify_frames,BinlogIntegrityError
from ...operations.fileio import private_directory,private_file
from ...sdk.tooling import ProviderToolGrant
from ...security import SecretLease


def capture(connection):
    if rows(connection,'SELECT @@in_transaction AS active')[0]['active']:
        raise BinlogArchiveError('Native archives require an independently owned idle connection')
    connection.autocommit=True
    observed=rows(connection,'SELECT VERSION() AS version,@@server_uid AS server_uid,@@server_id AS server_id,CURRENT_USER() AS authenticated_principal,CURRENT_ROLE() AS active_role,@@global.log_bin AS log_bin,@@global.gtid_binlog_pos AS gtid_binlog_pos,@@global.encrypt_binlog AS encrypt_binlog')[0]
    if observed['version'].split('-')[0]!='12.2.2' or 'MariaDB' not in observed['version']:
        raise BinlogArchiveError('Select native MariaDB12.2.2')
    identity={key:observed[key] for key in ('version','server_uid','server_id','authenticated_principal','active_role')}
    enabled=observed['log_bin'] in (1,True,'ON')
    current=rows(connection,'SHOW MASTER STATUS')[0] if enabled else None
    logs=rows(connection,'SHOW BINARY LOGS') if enabled else []
    for row in logs:
        row['File_size']=str(row['File_size']);row['closed']=current is not None and row['Log_name']!=current['File']
    if current is not None:current['Position']=str(current['Position'])
    return {'identity':identity,'state':{key:observed[key] for key in ('log_bin','gtid_binlog_pos','encrypt_binlog')},
        'current':current,'logs':logs,'status':'available' if enabled else 'native_binary_logging_disabled'}


def options(value):
    if not isinstance(value,dict) or set(value)-{'log_names','timeout_seconds'}:
        raise BinlogArchiveError('Select exact native closed-log identities and runtime')
    names=value.get('log_names');timeout=value.get('timeout_seconds',3600)
    if not isinstance(names,list) or not 1<=len(names)<=512 or any(not isinstance(name,str) or not name or
        len(name.encode('utf8'))>255 or Path(name).name!=name or PureWindowsPath(name).name!=name or
        name in {'.','..','archive.json'} or any(ord(char)<32 for char in name) for name in names) or len(set(names))!=len(names):
        raise BinlogArchiveError('Select between1 and512 distinct native binary-log basenames')
    if timeout is not None and (type(timeout) is not int or not 1<=timeout<=2147483647):
        raise BinlogArchiveError('Select positive native runtime seconds or null for no deadline')
    return {'log_names':list(names),'timeout_seconds':timeout}


def selected_logs(captured,selected):
    if captured['status']!='available' or captured['identity']['server_uid']=='unknown':
        raise BinlogArchiveError('Native binary logging and a native server_uid observation are required')
    closed=[row for row in captured['logs'] if row['closed']];names=[row['Log_name'] for row in closed]
    try:first=names.index(selected['log_names'][0])
    except ValueError:raise BinlogArchiveError('A selected native closed log is unavailable or purged') from None
    if names[first:first+len(selected['log_names'])]!=selected['log_names']:
        raise BinlogArchiveError('Select a contiguous native closed-log range in server order')
    return closed[first:first+len(selected['log_names'])]


def delegate_credentials(client,route):
    delegated=[]
    client._tool_secret(route,lambda password:delegated.append(SecretLease(client._defaults_file(password))))
    return delegated[0]


def program_identity(client,route,workspace,*,cancel=None,progress=None):
    grant=ProviderToolGrant('mariadb-binlog',str(workspace),str(route.get('host') or 'localhost'),int(route.get('port',3306)),timeout_seconds=30)
    result=client._tool_runner.run(grant,['--no-defaults','--version'],cancel_signal=cancel,progress=progress)
    if result['return_code']!=0 or not re.search(r'\b12\.2\.2-MariaDB\b',result['stdout']+' '+result['stderr']):
        raise BinlogArchiveError('Native archives require mariadb-binlog12.2.2')
    return {'executable_sha256':result['executable_sha256'],'tool_version':'12.2.2-MariaDB',
        'execution_host':{key:result['execution_host'][key] for key in ('kind','platform')}}


def framing(path,*,cancel=None):
    """Count complete bounded v4 frames before the CRC verification pass."""
    descriptor=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0))
    with os.fdopen(descriptor,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
            raise BinlogIntegrityError('Native binary log is not a regular file')
        if stream.read(4)!=b'\xfebin':raise BinlogIntegrityError('Native binary-log magic differs')
        count=0;last=None;size=info.st_size
        while header:=stream.read(19):
            if cancel is not None and cancel.is_set():raise InterruptedError('Native archive verification cancelled')
            if len(header)!=19:raise BinlogIntegrityError('Native binary-log header is truncated')
            length=int.from_bytes(header[9:13],'little')
            if length<19 or length-19>size-stream.tell():raise BinlogIntegrityError('Native binary-log frame is truncated')
            stream.seek(length-19,1);last=header[4];count+=1
        if not count:raise BinlogIntegrityError('Native binary log has no format-description event')
        # A crash-closed native file can end at a complete event without a
        # STOP/ROTATE. Closure comes from the revalidated native catalog.
        return size,count,last


def verify(directory,expected_source,*,cancel=None):
    directory=Path(directory);files=manifest(directory,cancel=cancel);metadata=_json(directory/'archive.json')
    if metadata.get('format')!='mariadb-binlog@12.2.2' or metadata.get('source')!=expected_source:
        raise BinlogArchiveError('Native MariaDB archive source or format differs')
    native=metadata.get('logs')
    if not isinstance(native,list) or not native:raise BinlogArchiveError('Native archive log inventory is missing')
    names=options({'log_names':[row['name'] for row in native]})['log_names']
    if set(row['path'] for row in files)!={'archive.json',*names}:raise BinlogArchiveError('Native archive has missing or unrecorded files')
    integrity=[]
    for row in native:
        path=directory/row['name'];size,count,last=framing(path,cancel=cancel)
        if str(size)!=row['decoded_bytes'] or str(count)!=row['event_count'] or last!=row['last_event_type']:
            raise BinlogArchiveError('Native archive event/byte postimage differs')
        integrity.append({'binlog':row['name'],**verify_frames(path,'none',size,count,cancel=cancel)})
    if manifest(directory,cancel=cancel)!=files:raise BinlogArchiveError('Native archive changed during verification')
    return {'format':metadata['format'],'source_uid':expected_source['server_uid'],'files':files,'file_count':len(files),
        'total_bytes':sum(row['size'] for row in files),'event_integrity':integrity,
        'start_from':{'file':names[0],'position':'4'},'end_at':{'file':names[-1],'position':native[-1]['decoded_bytes']},
        'native_event_checksums_verified_where_present':True,'native_parser_verification':metadata['native_parser_verification'],
        'verification_scope':'sealed_file_hashes_native_closed_log_framing_crc32_and_native_parser_postimage'}


class ArchiveTransport:
    def __init__(self,client,route,credentials,observer):
        self.client,self.route,self.credentials,self.observer=client,route,credentials,observer
    def close(self):
        if self.credentials is not None:self.credentials.close();self.credentials=None
        if self.observer is not None:
            owned=self.observer;self.observer=None;self.client._discard_failed_session(owned)

    def execute(self,record,directory,cancel,progress):
        last=None
        try:
            if capture(self.observer)['identity']!=record['source']:raise BinlogArchiveError('Native MariaDB source identity changed')
            program=program_identity(self.client,self.route,directory,cancel=cancel,progress=progress)
            if program!=record['program']:raise BinlogArchiveError('Native archive program or execution host changed')
            archive=directory/'archive.incoming';archive.mkdir(mode=0o700);private_directory(archive)
            grant=ProviderToolGrant('mariadb-binlog',str(directory),str(self.route.get('host') or 'localhost'),int(self.route.get('port',3306)),
                timeout_seconds=record['options']['timeout_seconds'],allow_unbounded_runtime=record['options']['timeout_seconds'] is None)
            connection_args=[item for item in self.client._connection_arguments({**self.route,'host':self.route.get('host') or 'localhost'},
                {'compress_connection':bool(self.route.get('compress'))}) if not item.startswith(('--default-character-set=','--max-allowed-packet='))]
            native=[];tools=[]
            for selected in record['source_state']['selected_logs']:
                if cancel.is_set():raise InterruptedError('Native archive cancelled')
                result=self.credentials.use(lambda view:self.client._tool_runner.run(grant,
                    [*connection_args,'--read-from-remote-server','--raw','--verify-binlog-checksum','--result-file='+str(archive)+os.sep,'--',selected['Log_name']],
                    secret_config=bytes(view),secret_argument='--defaults-file={path}',secret_argument_position=0,
                    cancel_signal=cancel,progress=progress))
                last={key:value for key,value in result.items() if key not in {'stdout','stderr'}};tools.append(last)
                if result['return_code']!=0:raise BinlogArchiveError('Native MariaDB raw retrieval did not return successfully')
                path=archive/selected['Log_name'];private_file(path);size,count,last_kind=framing(path,cancel=cancel)
                integrity=verify_frames(path,'none',size,count,cancel=cancel)
                native.append({'name':selected['Log_name'],'decoded_bytes':str(size),'event_count':str(count),
                    'server_file_bytes':selected['File_size'],'native_integrity':integrity,'last_event_type':last_kind})
            # Native SQL decoding can materialize LOAD DATA fragments. Keep
            # those files inside a private, disposable execution-host grant;
            # one ordered parser invocation preserves cross-file load state.
            temporary=directory/'verification-load';temporary.mkdir(mode=0o700);private_directory(temporary)
            checked=self.client._tool_runner.run(grant,['--no-defaults','--verify-binlog-checksum','--short-form',
                '--local-load='+str(temporary),'--',*[str(Path('archive.incoming')/row['name']) for row in native]],
                cancel_signal=cancel,progress=progress)
            last={key:value for key,value in checked.items() if key not in {'stdout','stderr'}};tools.append(last)
            if checked['return_code']!=0:raise BinlogArchiveError('The native MariaDB parser refused the archived log range')
            if last['executable_sha256']!=program['executable_sha256']:raise BinlogArchiveError('Native archive verifier changed during execution')
            shutil.rmtree(temporary)
            after=capture(self.observer)
            if after['identity']!=record['source'] or selected_logs(after,record['options'])!=record['source_state']['selected_logs']:
                raise BinlogArchiveError('Native MariaDB source or closed-log range changed during retrieval')
            metadata={'format':'mariadb-binlog@12.2.2','source':record['source'],'logs':native,
                'source_observation_scope':'native_server_uid_before_and_after_utility_retrieval_with_registered_transport_policy',
                'native_parser_verification':{'tool_version':program['tool_version'],'executable_sha256':program['executable_sha256'],
                    'scope':'original_native_parser_postimages_bound_to_sealed_archive_bytes'}}
            path=archive/'archive.json'
            with path.open('x',encoding='utf8') as stream:
                private_file(path);json.dump(metadata,stream,ensure_ascii=True,sort_keys=True);stream.flush();os.fsync(stream.fileno())
            artifact=verify(archive,record['source'],cancel=cancel);seal(archive,directory/'archive',cancel=cancel)
            if verify(directory/'archive',record['source'],cancel=cancel)!=artifact:raise BinlogArchiveError('Native archive changed during durable publication')
            return {'artifact':artifact,'tool_observations':tools,'program':program,
                'native_operation_returned':True,'remote_database_mutation':False}
        except BaseException as error:
            if last is not None and not getattr(error,'observation',None) and not getattr(error,'process_observation',None):error.observation=last
            observed=getattr(error,'process_observation',None) or getattr(error,'observation',{})
            if observed.get('process_observation',{}).get('cleanup_confirmed') is not False:
                shutil.rmtree(directory/'verification-load',ignore_errors=True)
            raise
